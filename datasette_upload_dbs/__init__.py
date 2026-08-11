from datasette import hookimpl
from datasette.permissions import Action
from datasette.database import Database
from datasette.utils.asgi import BadRequest, Response, Forbidden
from datasette.utils import to_css_class
from datasette.utils.sqlite import sqlite3
import pathlib

# Uploads are unlimited unless max_file_size_mb is configured
NO_LIMIT = 1 << 60
# Allowance for non-file form fields and multipart framing
REQUEST_OVERHEAD = 1024 * 1024
COPY_CHUNK_SIZE = 1024 * 1024


@hookimpl
def register_actions(datasette):
    return [
        Action(
            name="upload-dbs",
            description="Upload SQLite database files",
        )
    ]


@hookimpl
def register_routes():
    return [
        (r"^/-/upload-dbs$", upload_dbs),
        (r"^/-/upload-db$", lambda: Response.redirect("/-/upload-dbs")),
    ]


@hookimpl
def menu_links(datasette, actor):
    async def inner():
        if await datasette.allowed(
            actor=actor,
            action="upload-dbs",
        ) and _configured(datasette):
            return [
                {
                    "href": datasette.urls.path("/-/upload-dbs"),
                    "label": "Upload database",
                },
            ]

    return inner


@hookimpl
def startup(datasette):
    # Load any databases located in the directory folder
    config = datasette.plugin_config("datasette-upload-dbs") or {}
    if config.get("skip_startup_scan"):
        return
    directory = config.get("directory")
    if not directory:
        return
    path = pathlib.Path(directory)
    database_files = path.glob("*.db")
    for file_path in database_files:
        # Needs to set is_mutable=True here because the default was False
        # in Datasette versions up to and including 0.62
        datasette.add_database(
            Database(datasette, path=str(file_path), is_mutable=True),
        )


def _configured(datasette):
    return (datasette.plugin_config("datasette-upload-dbs") or {}).get("directory")


async def upload_dbs(datasette, request):
    if not await datasette.allowed(
        actor=request.actor,
        action="upload-dbs",
    ):
        raise Forbidden("Permission denied for upload-dbs")

    config = datasette.plugin_config("datasette-upload-dbs") or {}
    directory = config.get("directory")

    if not directory:
        raise Forbidden("datasette-upload-dbs plugin has not been correctly configured")

    path = pathlib.Path(directory)

    if request.method != "POST":
        return Response.html(
            await datasette.render_template("upload_dbs.html", request=request)
        )

    return_json = "application/json" in (request.headers.get("accept") or "")

    async def error(msg, status=400):
        if return_json:
            return Response.json({"ok": False, "error": msg}, status=status)

        return Response.html(
            await datasette.render_template(
                "upload_dbs.html",
                {
                    "error": msg,
                },
                request=request,
            ),
            status=status,
        )

    max_file_size_mb = config.get("max_file_size_mb")
    if max_file_size_mb:
        max_file_size = max_file_size_mb * 1024 * 1024
        max_request_size = max_file_size + REQUEST_OVERHEAD
    else:
        max_file_size = NO_LIMIT
        max_request_size = NO_LIMIT

    try:
        formdata = await request.form(
            files=True,
            max_file_size=max_file_size,
            max_request_size=max_request_size,
        )
    except BadRequest as e:
        msg = str(e)
        return await error(msg, status=413 if "too large" in msg else 400)

    async with formdata:
        if formdata.get("xhr"):
            return_json = True
        db_file = formdata.get("db")
        if db_file is None or isinstance(db_file, str):
            return await error('No file was uploaded in the "db" field')
        db_name = (formdata.get("db_name") or "").strip()

        if not db_name:
            db_name = db_file.filename.split(".")[0]

        db_name = to_css_class(db_name) or "db"

        first_16 = await db_file.read(16)
        if first_16 != b"SQLite format 3\x00":
            return await error("File is not a valid SQLite database (invalid header)")

        path.mkdir(parents=True, exist_ok=True)

        # Copy it to a temporary file next to its final destination, so an
        # invalid upload can never damage an existing database
        filepath = path / (db_name + ".db")
        tmp_filepath = path / (db_name + ".db.tmp")
        await db_file.seek(0)
        with open(tmp_filepath, "wb") as target_file:
            while True:
                chunk = await db_file.read(COPY_CHUNK_SIZE)
                if not chunk:
                    break
                target_file.write(chunk)

    # Now really verify it
    conn = sqlite3.connect(str(tmp_filepath))
    try:
        conn.execute("select * from sqlite_master")
    except sqlite3.Error as e:
        tmp_filepath.unlink()
        return await error(f"File is not a valid SQLite database ({e})")
    finally:
        conn.close()

    # File is valid - if it replaces an existing database, remove that
    # from the Datasette instance first, closing its connections
    resolved = filepath.resolve()
    existing_names = [
        name
        for name, existing_db in datasette.databases.items()
        if existing_db.path and pathlib.Path(existing_db.path).resolve() == resolved
    ]
    for name in existing_names:
        datasette.remove_database(name)

    # Remove any stale WAL files belonging to the previous database, then
    # atomically move the new database into place
    for suffix in ("-wal", "-shm"):
        stale = pathlib.Path(str(filepath) + suffix)
        if stale.exists():
            stale.unlink()
    tmp_filepath.replace(filepath)

    db = Database(datasette, path=str(filepath), is_mutable=True)
    datasette.add_database(db)

    redirect_url = datasette.urls.database(db.name)
    if return_json:
        return Response.json(
            {"ok": True, "database": db.name, "redirect": redirect_url}
        )
    else:
        return Response.redirect(redirect_url)
