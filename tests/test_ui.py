"""验证 MAA 的宿主编辑块、面板产物和插件 API。"""

from html.parser import HTMLParser
from pathlib import Path

import maa_adapter
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from maa_adapter.config.plan import MaaPlanConfig
from maa_adapter.config.script import MaaConfig
from maa_adapter.plugin import Plugin as Adapter

from app.api import plugin_router
from app.api._config_editors import config_detail_ui
from app.api.plan import router as plan_router
from app.api.scripts import router as scripts_router
from app.config import ConfigCollection, config_manager
from app.core import Config, Plugin
from app.core.i18n import I18nManager
from app.models.config import PluginRecord, PluginRegistryCollection
from app.models.schema import DeclarativeBlockOut, HostBlockOut, PluginBlockOut
from app.plugin.calls import CallGate
from app.plugin.frontend import MountedFrontend
from app.plugin.http import HttpRegistry
from app.plugin.types import PluginState

PACKAGE = Path(maa_adapter.__file__).resolve().parent
pytestmark = pytest.mark.asyncio


class PanelAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.files = {"script-src": [], "style-src": []}

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        assert tag != "style"
        assert not any(name == "style" or name.startswith("on") for name in fields)
        if tag == "script":
            assert fields.get("type") != "module" and "crossorigin" not in fields
            assert fields["src"].startswith("./")
            if fields["src"] != "./_host/panel-sdk.js":
                assert "defer" in fields
            self.files["script-src"].append(fields["src"][2:])
        if tag == "link" and fields.get("rel") == "stylesheet":
            assert fields["href"].startswith("./")
            self.files["style-src"].append(fields["href"][2:])


async def mount_frontend(monkeypatch, *routers):
    registry = PluginRegistryCollection.build()
    await registry.activate()
    record_id = registry.add(
        PluginRecord,
        payload={"info": {"plugin_name": "maa_adapter", "state": PluginState.ENABLED}},
    )
    await registry.commit()
    record = registry[record_id]
    record._plugin_cls = Adapter
    monkeypatch.setattr(Config, "plugin_registry", registry)
    monkeypatch.setattr(Plugin, "script_types", {record.uid: Adapter.decl})

    gate = CallGate()
    monkeypatch.setitem(Plugin._calls, record.uid, gate)
    frontend = MountedFrontend.load(
        PACKAGE, "maa_adapter", "MAA", "MaaPlanConfig", gate, block_pages={"user"}
    )
    assert frontend is not None
    assert frontend.diagnostics == []
    assert frontend.block_pages == {"user"}
    assert [(item.surface, item.planType, item.page) for item in frontend.bindings] == [
        ("plan", "MaaPlanConfig", "plan")
    ]
    app = FastAPI()
    app.include_router(plugin_router)
    for router in routers:
        app.include_router(router)
    http = HttpRegistry()
    monkeypatch.setattr(Plugin, "http", http)
    http.bind_app(app)
    http.mount(
        "maa_adapter", [], router=Adapter.api_router, frontend=frontend, gate=gate
    )
    return app, frontend


async def test_compiled_panels_load_under_host_csp(monkeypatch):
    app, frontend = await mount_frontend(monkeypatch)
    root = f"/api/plugin/maa_adapter/ui/{frontend.revision}"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        for page in ("user", "plan"):
            response = await client.get(f"{root}/{page}.html")
            assert response.status_code == 200
            policy = dict(
                directive.split(" ", 1)
                for directive in response.headers["Content-Security-Policy"].split("; ")
            )
            assert policy["default-src"] == "'none'"
            assert all(
                source.startswith(f"http://test{root}/")
                for source in policy["connect-src"].split()
            )
            assert policy["sandbox"] == "allow-scripts allow-forms"
            assets = PanelAssets()
            assets.feed(response.text)
            assert assets.files["script-src"][0] == "_host/panel-sdk.js"
            assert "_host/panel-base.css" in assets.files["style-src"]
            for directive, mime in (
                ("script-src", "text/javascript"),
                ("style-src", "text/css"),
            ):
                assert any(
                    path.startswith("assets/") for path in assets.files[directive]
                )
                for path in assets.files[directive]:
                    target = f"http://test{root}/{path}"
                    assert target in policy[directive].split()
                    asset = await client.get(target)
                    assert asset.status_code == 200
                    assert asset.headers["Content-Type"].startswith(mime)
                assert "'unsafe-inline'" not in policy[directive].split()

    manager = I18nManager(Config.resource_path / "i18n")
    manager.set_package_roots({"maa_adapter": PACKAGE})
    for locale in ("zh-CN", "en-US", "ja-JP"):
        messages, _ = await manager.get_messages(locale)
        labels = messages["plugins"]["maa_adapter"]["panel"]["editor"]
        assert labels["IfCultivate"] and labels["pipeline"] and labels["plan"]


async def test_editor_blocks_and_scoped_routes(monkeypatch, isolated_app_paths):
    scripts = ConfigCollection.build([MaaConfig])
    plans = ConfigCollection.build([MaaPlanConfig])
    for collection in (scripts, plans):
        await collection.activate()

    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    monkeypatch.setitem(config_manager._collections, "ScriptConfig", scripts)
    monkeypatch.setattr(Config, "PlanConfig", plans)
    monkeypatch.setitem(config_manager._collections, "PlanConfig", plans)
    app, frontend = await mount_frontend(monkeypatch, scripts_router, plan_router)

    await Adapter().pre_enable()
    script_uid, script = await Config.add_script("MAA")
    script_id = str(script_uid)
    _, script_documents = await Config.get_script(script_id)
    assert config_detail_ui(script, script_documents).blocks == [
        DeclarativeBlockOut(groups=["Info"]),
        HostBlockOut(name="game_binding"),
        DeclarativeBlockOut(groups=["Run", "Update"]),
    ]

    user_uid, user = await Config.add_user(script_id)
    user_id = str(user_uid)
    _, documents = await Config.get_user(script_id, user_id)
    ui = config_detail_ui(user, documents)
    assert ui.blocks == [
        HostBlockOut(name="config_restore"),
        HostBlockOut(name="native_session"),
        DeclarativeBlockOut(groups=["Info"]),
        PluginBlockOut(
            pageId="user",
            fallbackGroups=["Stage", "Task"],
            mount=frontend.surface_mount(name="maa_adapter", page="user"),
        ),
        DeclarativeBlockOut(groups=["Notify"]),
        HostBlockOut(name="webhooks"),
    ]
    assert [(pool.key, pool.kind) for pool in ui.backupTargets] == [
        ("mas", "user"),
        ("native", "script"),
    ]
    assert ui.nativeSession == "config"
    assert {"CultivateTargets", "DepotMaintainPlans", "EventDepotMaintainPlans"} <= {
        hint["field"] for hint in ui.hints["Task"] if hint["editable"]
    }
    for pool in ui.backupTargets:
        assert (await Config.list_config_backups(script_id, user_id, pool.key))[
            "items"
        ] == []

    plan_uid, plan = await Config.add_plan("MaaPlanConfig")
    plan_id = str(plan_uid)
    _, plan_documents = await Config.get_plan(plan_id)
    assert config_detail_ui(plan, plan_documents).frontendSurfaces["plan"] == (
        frontend.surface_mount(name="maa_adapter", page="plan")
    )

    headers = {
        "X-Plugin-Ui-Provider": "maa_adapter",
        "X-Plugin-Ui-Activation": frontend.activation_id,
        "X-Plugin-Ui-Page": "user",
    }
    ids = {"scriptId": script_id, "userId": user_id}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        prefix = "/api/plugin/maa_adapter"
        for path in ("/api/scripts", prefix):
            result = await client.post(f"{path}/user/combox/infrastructure", json=ids)
            assert result.status_code == result.json()["code"] == 200
        context = await client.get(
            f"{prefix}/editor/user/{script_id}/{user_id}", headers=headers
        )
        assert context.json() == {
            "server": "Official",
            "quickConfig": True,
            "plans": [{"label": plan.Info.Name, "value": plan_id}],
        }

        user_save = await client.post(
            "/api/scripts/user/update",
            json={
                **ids,
                "data": {
                    "Stage": {"StageMode": plan_id},
                    "Task": {"IfCultivate": True},
                },
            },
            headers=headers,
        )
        assert user_save.status_code == user_save.json()["code"] == 200, user_save.text
        assert str(user.Stage.StageMode) == plan_id
        assert user.Task.IfCultivate is True

        plan_save = await client.post(
            "/api/plan/update",
            json={"planId": plan_id, "data": {"ALL": {"Stage": "CUSTOM-42"}}},
            headers={**headers, "X-Plugin-Ui-Page": "plan"},
        )
        assert plan_save.status_code == plan_save.json()["code"] == 200, plan_save.text
        stage = await client.get(
            f"{prefix}/editor/plan/{plan_id}/active?server=Official"
        )
        assert stage.json()["Stage"] == "CUSTOM-42"
