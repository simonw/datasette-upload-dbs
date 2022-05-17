from datasette.app import Datasette
import pytest


@pytest.mark.asyncio
async def test_plugin_is_installed():
    datasette = Datasette([], memory=True)
    response = await datasette.client.get("/-/plugins.json")
    assert response.status_code == 200
    installed_plugins = {p["name"] for p in response.json()}
    assert "datasette-upload-dbs" in installed_plugins


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
