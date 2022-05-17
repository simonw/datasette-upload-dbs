from datasette.app import Datasette
import sqlite3
import pytest


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
async def test_databases_loaded_on_startup(tmp_path_factory):
    uploads_directory = tmp_path_factory.mktemp("uploads")
    for name in ("test1.db", "test2.db"):
        db_path = uploads_directory / name
        sqlite3.connect(str(db_path)).execute("create table t (id integer primary key)")
    ds = Datasette(
        memory=True,
        metadata={
            "plugins": {"datasette-upload-dbs": {"directory": str(uploads_directory)}}
        },
    )
    await ds.invoke_startup()
    assert set(ds.databases.keys()).issuperset({"test1", "test2"})
