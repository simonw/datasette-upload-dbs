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

    is_xhr = False

    async def error(msg):
        if is_xhr:
            return Response.json({"ok": False, "error": msg})

        return Response.html(
            await datasette.render_template(
                "upload_dbs.html",
                {
                    "error": msg,
                },
                request=request,
            )
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
        return await error(str(e))

    async with formdata:
        db_file = formdata["db"]
        is_xhr = formdata.get("xhr")
        db_name = (formdata.get("db_name") or "").strip()

        if not db_name:
            db_name = db_file.filename.split(".")[0]

        db_name = to_css_class(db_name) or "db"

        first_16 = await db_file.read(16)
        if first_16 != b"SQLite format 3\x00":
            return await error("File is not a valid SQLite database (invalid header)")

        path.mkdir(parents=True, exist_ok=True)

        # Copy it to its final destination
        filepath = path / (db_name + ".db")
        await db_file.seek(0)
        with open(filepath, "wb") as target_file:
            while True:
                chunk = await db_file.read(COPY_CHUNK_SIZE)
                if not chunk:
                    break
                target_file.write(chunk)

    # Now really verify it
    conn = sqlite3.connect(str(filepath))
    try:
        conn.execute("select * from sqlite_master")
    except sqlite3.Error as e:
        # Delete file, it is invalid
        filepath.unlink()
        return await error(f"File is not a valid SQLite database ({e})")

    # File is valid - add it to this Datasette instance
    db = Database(datasette, path=str(filepath), is_mutable=True)
    datasette.add_database(db)

    redirect_url = datasette.urls.database(db.name)
    if is_xhr:
        return Response.json({"ok": True, "redirect": redirect_url})
    else:
        return Response.redirect(redirect_url)
