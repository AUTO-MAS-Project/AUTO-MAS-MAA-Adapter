from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from script_maa.adapter import _build_proxy_result_payload
from script_maa.maa_task.AutoProxy import AutoProxyTask


class FakeUserConfig:
    def __init__(self, notify: dict[str, Any]) -> None:
        self.notify = notify

    def get(self, group: str, key: str) -> Any:
        assert group == "Notify"
        return self.notify.get(key)


class FakeNotifyService:
    def __init__(
        self,
        *,
        send_statistic: bool = True,
        send_six_star: bool = True,
        fail: bool = False,
    ) -> None:
        self.send_statistic = send_statistic
        self.send_six_star = send_six_star
        self.fail = fail
        self.payloads: list[tuple[dict[str, Any], Any]] = []
        self.mails: list[dict[str, Any]] = []
        self.serverchan: list[dict[str, Any]] = []

    async def should_send_statistic(self) -> bool:
        return self.send_statistic

    async def should_send_six_star(self) -> bool:
        return self.send_six_star

    async def send_payload(
        self, payload: dict[str, Any], *, channels: Any = None
    ) -> dict[str, bool]:
        if self.fail:
            raise RuntimeError("send failed")
        self.payloads.append((payload, channels))
        if channels == []:
            return {}
        return {"test": True}

    @staticmethod
    def is_channel_selected(channels: Any, channel: str) -> bool:
        if channels == []:
            return False
        if channels is None or "all" in channels:
            return True
        return channel in channels

    async def send_mail(self, **payload: Any) -> bool:
        if self.fail:
            raise RuntimeError("mail failed")
        self.mails.append(payload)
        return True

    async def send_serverchan(self, **payload: Any) -> bool:
        if self.fail:
            raise RuntimeError("serverchan failed")
        self.serverchan.append(payload)
        return True


def make_task(
    service: FakeNotifyService | None,
    *,
    channels: list[str] | None,
    notify: dict[str, Any] | None = None,
) -> AutoProxyTask:
    task = AutoProxyTask.__new__(AutoProxyTask)
    task.notify_service = service
    task.notify_channels = channels
    task.cur_user_item = SimpleNamespace(name="测试用户")
    task.cur_user_config = FakeUserConfig(
        notify
        or {
            "Enabled": True,
            "IfSendStatistic": True,
            "IfSendSixStar": True,
            "IfSendMail": True,
            "ToAddress": "user@example.com",
            "IfServerChan": True,
            "ServerChanKey": "SCT_TEST",
        }
    )
    return task


def test_proxy_result_payload_contains_rendered_business_content() -> None:
    result = {
        "title": "自动代理任务报告",
        "script_name": "测试脚本",
        "start_time": "2026-06-23 09:00:00",
        "end_time": "2026-06-23 09:10:00",
        "completed_count": 2,
        "uncompleted_count": 1,
        "result": "用户 A 完成",
    }

    payload = _build_proxy_result_payload("测试标题", result)

    assert payload["kind"] == "proxy_result"
    assert payload["data"] is result
    assert "已完成数: 2" in payload["text"]
    assert "未完成数: 1" in payload["text"]
    assert "测试脚本" in payload["mail_content"]


def test_statistic_uses_global_service_and_user_direct_channels() -> None:
    service = FakeNotifyService()
    task = make_task(service, channels=["all"])
    statistics = {
        "start_time": "2026-06-23 09:00:00",
        "end_time": "2026-06-23 09:10:00",
        "sanity": 100,
        "sanity_full_at": "12:00",
        "maa_result": "代理任务全部完成",
        "drop_statistics": {"1-7": {"固源岩": 2}},
        "recruit_statistics": {"六星": 1},
    }

    asyncio.run(task._send_statistic_notification(statistics, "√"))

    payload, channels = service.payloads[0]
    assert payload["kind"] == "statistic"
    assert payload["data"] is statistics
    assert "固源岩: 2" in payload["text"]
    assert channels == ["all"]
    assert service.mails[0]["to_address"] == "user@example.com"
    assert service.serverchan[0]["send_key"] == "SCT_TEST"


def test_disabled_global_policy_keeps_user_direct_notification() -> None:
    service = FakeNotifyService(send_six_star=False)
    task = make_task(service, channels=["mail", "serverchan"])

    asyncio.run(task._send_six_star_notification())

    assert service.payloads == []
    assert len(service.mails) == 1
    assert len(service.serverchan) == 1


def test_empty_channel_selection_suppresses_user_direct_notification() -> None:
    service = FakeNotifyService()
    task = make_task(service, channels=[])

    asyncio.run(task._send_six_star_notification())

    assert service.payloads[0][1] == []
    assert service.mails == []
    assert service.serverchan == []


def test_missing_or_failing_notify_service_does_not_raise() -> None:
    no_service_task = make_task(None, channels=["all"])
    asyncio.run(no_service_task._send_six_star_notification())

    failing_service = FakeNotifyService(fail=True)
    failing_task = make_task(failing_service, channels=["all"])
    asyncio.run(failing_task._send_six_star_notification())
