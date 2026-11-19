"""真实配置、运行树和调度入口；仅替换 MAA 进程与模拟器边界。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from maa_adapter import PLUGIN
from maa_adapter.config.script import MaaConfig

from app.models.task import TaskMode
from tests.support.maa_runtime import dispatch
from tests.support.maa_runtime import runtime as runtime


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [TaskMode.SCRIPT_CONFIG, TaskMode.SCRIPT_VIEW])
@pytest.mark.parametrize("account", [True, False])
async def test_session_uses_real_dispatch_and_preserves_native_config(
    runtime, mode, account
):
    """验证配置与查看会话经过真实 L2 至 L4 调度，并在结束后保留原安装的原生配置。"""
    runtime.user.Info.Status = False
    runtime.user.Info.RemainedDay = 0
    await runtime.user.commit()
    execution = await dispatch(runtime, mode, account=account)
    await asyncio.wait_for(execution.accomplish.wait(), timeout=10)
    assert execution.error is None
    assert execution.task_info.info.status == "success", [
        (x.info.status, x.current.log) for x in execution.task_info.scripts.values()
    ]
    assert len(runtime.opened) == 1
    assert not runtime.script.is_locked
    assert not runtime.user.is_locked
    assert {
        name: (runtime.install / "config" / name).read_bytes()
        for name in runtime.original
    } == runtime.original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome, check_game_update",
    [("success", False), ("error", False), ("cancelled", False), ("success", True)],
)
async def test_auto_proxy_through_real_dispatch(
    runtime, monkeypatch, outcome, check_game_update
):
    """使用受控日志驱动自动代理成功、异常或取消结果，验证真实调度及原生配置恢复。"""
    import maa_adapter.tasks.auto_proxy as auto_module
    import maa_adapter.tasks.manager as manager_module

    from app.core import Publisher
    from app.core.ws import protocol
    from app.models.emulator import DeviceStatus
    from app.utils.common.game_update import GameUpdateResult

    startup_logs = []
    maa_start_logs = []
    monitor_ready_logs = []
    runtime.script.Run.IfCheckGameUpdate = check_game_update
    runtime.emulator.getStatus = AsyncMock(return_value=DeviceStatus.OFFLINE)
    monkeypatch.setattr(
        manager_module,
        "ensure_game_updated",
        AsyncMock(
            return_value=GameUpdateResult(status="UpToDate", message="Game up to date")
        ),
    )

    async def open_emulator(*args, **kwargs):
        """在模拟器启动边界保存当前可见日志，核对启动提示已先于设备等待推送。"""
        snapshot = runtime.manager.get_runtime_snapshot().tasks[0]
        pushed = [
            call.kwargs["data"].log
            for call in Publisher.send.await_args_list
            if call.kwargs["type"] == protocol.TASK_LOG_UPDATED
        ]
        startup_logs.append((snapshot.log, pushed[-1] if pushed else None))
        await asyncio.sleep(0)
        startup_logs.append(
            (
                runtime.manager.get_runtime_snapshot().tasks[0].log,
                pushed[-1] if pushed else None,
            )
        )
        return SimpleNamespace(adb_address="127.0.0.1:5555")

    runtime.emulator.open.side_effect = open_emulator

    class Process(runtime.process):
        async def open_process(self, executable, *args, **kwargs):
            """记录 MAA 启动入口的正文，确认模拟器提示保留到真正启动 MAA。"""
            maa_start_logs.append(runtime.manager.get_runtime_snapshot().tasks[0].log)
            await super().open_process(executable, *args, **kwargs)

        async def is_running(self):
            """报告模拟 MAA 进程正在运行，允许自动代理进入日志观察流程。"""
            return True

    monkeypatch.setattr(auto_module, "ProcessManager", Process)

    class Monitor:
        def __init__(self, interval, fmt, callback, **kwargs):
            """保存来源日志回调，供测试注入本次运行结果。"""
            self.callback = callback

        async def start_monitor_file(self, *args, **kwargs):
            """标记自动代理已启动，并向实际日志回调注入当前场景的 MAA 输出。"""
            runtime.started.set()
            monitor_ready_logs.append(
                runtime.manager.get_runtime_snapshot().tasks[0].log
            )
            line = {
                "success": "任务已全部完成！",
                "error": "未选择任务",
                "cancelled": "正在执行任务",
            }[outcome]
            await self.callback([line], datetime.now().astimezone())

        async def stop(self):
            """提供测试日志观察器的空停止入口，保持正常收尾协议。"""
            pass

    monkeypatch.setattr(auto_module, "LogMonitor", Monitor)
    runtime.script.Run.RunTimesLimit = 1
    await runtime.script.commit()
    execution = await dispatch(runtime, TaskMode.AUTO_PROXY)
    if outcome == "cancelled":
        await asyncio.wait_for(runtime.started.wait(), timeout=10)
        await execution.stop()
    await asyncio.wait_for(execution.accomplish.wait(), timeout=10)
    assert execution.error is None
    assert execution.task_info.info.status == outcome, [
        (
            x.info.status,
            x.current.log,
            [(u.info.status, u.info.result) for u in x.users.values()],
        )
        for x in execution.task_info.scripts.values()
    ]
    assert runtime.emulator.open.await_count == (2 if check_game_update else 1)
    assert startup_logs == [("正在启动模拟器\n", "正在启动模拟器\n")] * (
        4 if check_game_update else 2
    )
    assert maa_start_logs == ["正在启动模拟器\n"]
    assert monitor_ready_logs == [""]
    native_log = {
        "success": "任务已全部完成！",
        "error": "未选择任务",
        "cancelled": "正在执行任务",
    }[outcome]
    assert any(
        call.kwargs["type"] == protocol.TASK_LOG_UPDATED
        and call.kwargs["data"].log == native_log
        for call in Publisher.send.await_args_list
    )
    assert runtime.emulator.close.await_count >= 1
    assert not runtime.script.is_locked
    assert not runtime.user.is_locked
    assert runtime.user.Data.ProxyTimes == (1 if outcome == "success" else 0)
    assert runtime.record_history.await_count == 1
    record = runtime.record_history.call_args.args[0]
    assert record.status == outcome
    assert {
        name: (runtime.install / "config" / name).read_bytes()
        for name in runtime.original
    } == runtime.original


def test_plugin_declares_only_real_modes_and_prefetch():
    """验证插件只声明实际实现的自动代理、配置和查看模式，同时绑定预下载及真实配置类型。"""
    plugin = PLUGIN()
    assert plugin.decl.supported_modes == (
        TaskMode.AUTO_PROXY,
        TaskMode.SCRIPT_CONFIG,
        TaskMode.SCRIPT_VIEW,
    )
    assert plugin.decl.prefetch_check is not None
    assert plugin.decl.script_type is MaaConfig


@pytest.mark.asyncio
async def test_maintenance_skips_without_opening_device(runtime, monkeypatch):
    """验证处于维护时段的账号直接跳过，不打开模拟器且任务结束后释放配置锁。"""
    from app.core import GameMaintenance

    monkeypatch.setattr(
        GameMaintenance,
        "get_active",
        AsyncMock(return_value=SimpleNamespace(reason="维护中")),
    )
    execution = await dispatch(runtime, TaskMode.AUTO_PROXY)
    await asyncio.wait_for(execution.accomplish.wait(), timeout=10)
    assert execution.task_info.info.status == "success"
    script = next(iter(execution.task_info.scripts.values()))
    assert script.info.status == "跳过"
    assert next(iter(script.users.values())).info.status == "跳过"
    runtime.emulator.open.assert_not_awaited()
    assert not runtime.script.is_locked


@pytest.mark.asyncio
async def test_cancel_gui_with_unconfirmed_save_preserves_source(runtime, monkeypatch):
    """验证 GUI 取消后保存尚未确认时保留源配置，同时完成宿主锁的收尾。"""
    import maa_adapter.tasks.session as worker_module

    class Process(runtime.process):
        opened = False

        async def open_process(self, *args, **kwargs):
            """复用启动记录并标记 GUI 已打开，通知测试可以发起停止。"""
            await super().open_process(*args, **kwargs)
            self.opened = True
            runtime.started.set()

        async def is_running(self):
            """返回模拟 GUI 是否已打开，供停止保存确认检查使用。"""
            return self.opened

        async def close(self):
            """让已打开 GUI 的关闭持续等待，模拟无法确认正常保存退出的场景。"""
            if self.opened:
                await asyncio.Event().wait()

    monkeypatch.setattr(worker_module, "ProcessManager", Process)
    monkeypatch.setattr(worker_module.MaaGuiSession, "GUI_CLOSE_TIMEOUT", 0.01)
    execution = await dispatch(runtime, TaskMode.SCRIPT_CONFIG, account=False)
    await asyncio.wait_for(runtime.started.wait(), timeout=10)
    await asyncio.wait_for(execution.stop(), timeout=5)
    assert execution.task_info.info.status == "cancelled"
    assert {
        name: (runtime.install / "config" / name).read_bytes()
        for name in runtime.original
    } == runtime.original
    assert not runtime.script.is_locked


@pytest.mark.asyncio
async def test_migrated_maa_keeps_native_notification_policy(runtime):
    """验证迁入插件的 MAA 仍采用来源 Notify 分组控制用户统计通知。"""
    from app.core.notify.manager import NotificationManager

    runtime.user.Notify.Enabled = True
    runtime.user.Notify.IfSendStatistic = True
    await runtime.user.commit()
    assert not runtime.user.notify.enabled
    notify = NotificationManager()
    assert len(notify.user_statistic_targets(runtime.user)) == 1
    runtime.user.Notify.Enabled = False
    await runtime.user.commit()
    assert notify.user_statistic_targets(runtime.user) == []
