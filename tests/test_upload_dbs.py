from datasette.app import Datasette
import sqlite3
import pytest
from io import BytesIO


@pytest.mark.asyncio
@pytest.mark.parametrize("auth", [True, False])
async def test_menu(auth):
    ds = Datasette(
        memory=True, metadata={"plugins": {"datasette-upload-dbs": {"directory": "."}}}
    )
    cookies = {}
    if auth:
        cookies = {"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")}
    response = await ds.client.get("/", cookies=cookies)
    assert response.status_code == 200
    if auth:
        assert "/-/upload-dbs" in response.text
    else:
        assert "/-/upload-dbs" not in response.text


@pytest.mark.asyncio
async def test_redirect():
    ds = Datasette(memory=True)
    response = await ds.client.get("/-/upload-db")
    assert response.status_code == 302
    assert response.headers["location"] == "/-/upload-dbs"


@pytest.mark.asyncio
@pytest.mark.parametrize("skip_startup_scan", (False, True))
async def test_databases_loaded_on_startup(tmp_path_factory, skip_startup_scan):
    uploads_directory = tmp_path_factory.mktemp("uploads")
    for name in ("test1.db", "test2.db"):
        db_path = uploads_directory / name
        sqlite3.connect(str(db_path)).execute("create table t (id integer primary key)")
    config = {"directory": str(uploads_directory)}
    if skip_startup_scan:
        config["skip_startup_scan"] = True

    ds = Datasette(
        memory=True,
        metadata={"plugins": {"datasette-upload-dbs": config}},
    )
    await ds.invoke_startup()
    db_names = {"test1", "test2"}
    if skip_startup_scan:
        # Should not have any DBs
        assert set(ds.databases.keys()) == {"_internal", "_memory"}
    else:
        assert set(ds.databases.keys()).issuperset(db_names)
        for name in db_names:
            assert ds.databases[name].is_mutable


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authed,configured,expected_error",
    (
        (False, False, "Permission denied for upload-dbs"),
        (False, True, "Permission denied for upload-dbs"),
        (True, False, "datasette-upload-dbs plugin has not been correctly configured"),
    ),
)
async def test_errors(authed, configured, expected_error):
    ds = Datasette(
        memory=True,
        metadata={
            "plugins": {"datasette-upload-dbs": {"directory": "."}}
            if configured
            else {}
        },
    )
    cookies = {}
    if authed:
        cookies = {"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")}
    response = await ds.client.get("/-/upload-dbs", cookies=cookies)
    assert response.status_code == 403
    assert expected_error in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bytes,expected_error",
    (
        (b"bad_bytes", "File is not a valid SQLite database (invalid header)"),
        (
            b"SQLite format 3\x00invalid",
            "File is not a valid SQLite database (file is not a database)",
        ),
    ),
)
@pytest.mark.parametrize("xhr", (True, False))
async def test_invalid_files(tmp_path_factory, bytes, expected_error, xhr):
    uploads_directory = tmp_path_factory.mktemp("uploads")
    ds = Datasette(
        memory=True,
        metadata={
            "plugins": {"datasette-upload-dbs": {"directory": str(uploads_directory)}}
        },
    )
    csrftoken = await _get_csrftoken(ds)
    # write to database
    response = await ds.client.post(
        "/-/upload-dbs",
        cookies={
            "ds_actor": ds.sign({"a": {"id": "root"}}, "actor"),
            "ds_csrftoken": csrftoken,
        },
        data={"csrftoken": csrftoken, "xhr": "1" if xhr else ""},
        files={"db": BytesIO(bytes)},
    )
    if xhr:
        assert response.json() == {"ok": False, "error": expected_error}
    else:
        assert f'<p class="message-error">{expected_error}</p>' in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("xhr", (True, False))
@pytest.mark.parametrize(
    "db_file_name,db_name,expected_path",
    (
        ("temp.db", None, "/temp"),
        (".db", None, "/d41d8c"),
        ("temp.db", "custom", "/custom"),
        ("temp.db", "a + b + c ~ d", "/a--b--c--d-26e27e"),
    ),
)
async def test_upload(tmp_path_factory, xhr, db_file_name, db_name, expected_path):
    uploads_directory = tmp_path_factory.mktemp("uploads")
    tmp_directory = tmp_path_factory.mktemp("tmp")
    ds = Datasette(
        memory=True,
        metadata={
            "plugins": {"datasette-upload-dbs": {"directory": str(uploads_directory)}}
        },
    )
    csrftoken = await _get_csrftoken(ds)

    temp = str(tmp_directory / db_file_name)
    sqlite3.connect(temp).execute("create table t (id integer primary key)")

    upload_data = {"csrftoken": csrftoken, "xhr": "1" if xhr else ""}
    if db_name:
        upload_data["db_name"] = db_name

    response = await ds.client.post(
        "/-/upload-dbs",
        cookies={
            "ds_actor": ds.sign({"a": {"id": "root"}}, "actor"),
            "ds_csrftoken": csrftoken,
        },
        data=upload_data,
        files={"db": open(temp, "rb")},
    )
    if xhr:
        assert response.json() == {"ok": True, "redirect": expected_path}
    else:
        assert response.status_code == 302
        assert response.headers["location"] == expected_path

    # Datasette should serve that file
    table_response = await ds.client.get(f"{expected_path}/t.json?_shape=array")
    assert table_response.status_code == 200
    assert table_response.json() == []

    # Uploaded file should exist
    conn = sqlite3.connect(temp)
    assert conn.execute("select sql from sqlite_master").fetchall() == [
        ("CREATE TABLE t (id integer primary key)",)
    ]
    # And it should be mutable
    new_db = [db for db in ds.databases.values() if not db.name.startswith("_")][0]
    assert new_db.is_mutable


async def _get_csrftoken(ds):
    return (
        await ds.client.get(
            "/-/upload-dbs",
            cookies={"ds_actor": ds.sign({"a": {"id": "root"}}, "actor")},
        )
    ).cookies["ds_csrftoken"]
