from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from script_maa.adapter import MaaAdapterHooks
from script_maa.maa_task.AutoProxy import AutoProxyTask
from script_maa.maa_task.ManualReview import ManualReviewTask
from script_maa.maa_task.ScriptConfig import ScriptConfigTask


class ConfigStub:
    def __init__(self) -> None:
        self.values = {
            "Info": {
                "Name": "测试用户",
                "Status": True,
                "RemainedDay": -1,
            }
        }

    def get(self, group: str, name: str):
        return self.values[group][name]

    async def set(self, group: str, name: str, value: object) -> None:
        self.values[group][name] = value


@pytest.mark.asyncio
async def test_prepare_unlocks_storage_when_initialization_fails() -> None:
    storage = SimpleNamespace(
        lock=AsyncMock(),
        unlock=AsyncMock(),
    )
    runtime = SimpleNamespace(storage=storage)
    hooks = MaaAdapterHooks()
    hooks._prepare_locked = AsyncMock(side_effect=RuntimeError("prepare failed"))

    with pytest.raises(RuntimeError, match="prepare failed"):
        await hooks.prepare(runtime)

    storage.lock.assert_awaited_once()
    storage.unlock.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_uses_runtime_type_key_without_legacy_model_lookup() -> None:
    runtime = SimpleNamespace(
        mode="AutoProxy",
        type_key="SRC",
        script_config=None,
        build_script_model=AsyncMock(return_value=ConfigStub()),
    )

    result = await MaaAdapterHooks().check(runtime)

    assert result == "脚本配置类型错误, 不是 MAA 脚本类型"
    assert runtime.script_config is not None


@pytest.mark.parametrize(
    "task_class",
    (AutoProxyTask, ManualReviewTask, ScriptConfigTask),
)
def test_task_constructors_accept_mapping_user_collection(task_class) -> None:
    user_id = uuid.uuid4()
    user_config = ConfigStub()
    script_info = SimpleNamespace(
        task_info=SimpleNamespace(),
        user_list=[SimpleNamespace(user_id=str(user_id))],
        current_index=0,
    )

    task = task_class(
        script_info,
        ConfigStub(),
        {user_id: user_config},
        SimpleNamespace(),
    )

    assert task.user_config[user_id] is user_config
    if task_class is not ScriptConfigTask:
        assert task.cur_user_config is user_config


@pytest.mark.parametrize(
    "relative_path",
    (
        "AutoProxy.py",
        "ManualReview.py",
        "ScriptConfig.py",
    ),
)
def test_task_modules_do_not_import_legacy_config_models(
    relative_path: str,
) -> None:
    module_path = (
        Path(__file__).parents[1]
        / "src"
        / "script_maa"
        / "maa_task"
        / relative_path
    )
    source = module_path.read_text(encoding="utf-8")

    assert "app.models.ConfigBase" not in source
    assert "app.models.config" not in source


def test_adapter_does_not_call_legacy_config_compatibility_lookup() -> None:
    adapter_path = (
        Path(__file__).parents[1] / "src" / "script_maa" / "adapter.py"
    )
    source = adapter_path.read_text(encoding="utf-8")

    assert "app.core.script_types" not in source
    assert "app.models.ConfigBase" not in source
    assert "app.models.config" not in source
