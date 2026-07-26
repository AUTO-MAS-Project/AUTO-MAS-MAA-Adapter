from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.task import UserItem
from app.plugins import ScriptAdapterHooks, ScriptAdapterRuntime
from app.plugins.schema_utils import (
    SchemaDecorationContext,
    set_schema_field_options,
    set_schema_field_state,
)
from app.utils import get_logger

from .constants import TASK_MODE_ZH
from .template_renderer import render_template

logger = get_logger("MAA 专项适配")


def _read_notify_channels(script_config: Any | None) -> list[str]:
    """Read the plugin-owned channel selection without interpreting it."""

    # 读取脚本配置中选择的通知频道。
    if script_config is None:
        return []
    try:
        raw_channels = script_config.get("Notify", "Channels")
    except Exception:
        return []
    return raw_channels if isinstance(raw_channels, list) else []


def _build_proxy_result_payload(
    title: str, result: dict[str, Any]
) -> dict[str, Any]:
    # 将 MAA 汇总结果转换为 notify 服务的通用 payload。
    message_text = (
        f"任务开始时间: {result['start_time']}, "
        f"结束时间: {result['end_time']}\n"
        f"已完成数: {result['completed_count']}, "
        f"未完成数: {result['uncompleted_count']}\n\n"
        f"{result['result']}"
    )
    serverchan_message = message_text.replace("\n", "\n\n")
    return {
        "kind": "proxy_result",
        "title": title,
        "text": message_text,
        "serverchan_content": f"{serverchan_message}\nAUTO-MAS 敬上",
        "koishi_message": f"{title}\n\n{message_text}\nAUTO-MAS 敬上",
        "mail_mode": "网页",
        "mail_content": render_template("MAA_result.html", result),
        "data": result,
    }


async def _push_system_notification(
    notify_service: Any | None,
    *,
    title: str,
    message: str,
    ticker: str,
    timeout: int,
    channels: list[str] | None = None,
) -> bool:
    # 通过 notify 服务发送系统通知。
    if notify_service is None:
        return False

    try:
        result = await notify_service.send_payload(
            {
                "kind": "system",
                "title": title,
                "text": message,
                "ticker": ticker,
                "timeout": timeout,
            },
            channels=channels,
        )
        return isinstance(result, dict) and any(bool(ok) for ok in result.values())
    except Exception as exc:
        logger.warning(f"notify 系统通知发送失败: {type(exc).__name__}: {exc}")
        return False


def _build_infrast_plan_options(config_data: dict[str, Any]) -> list[dict[str, str]]:
    # 从自定义基建配置生成排班选项。
    data_group = config_data.get("Data")
    if not isinstance(data_group, dict):
        return []
    custom_infrast = data_group.get("CustomInfrast")
    if not isinstance(custom_infrast, dict):
        return []
    plans = custom_infrast.get("plans")
    if not isinstance(plans, list):
        return []
    options: list[dict[str, str]] = []
    for index, plan in enumerate(plans):
        if isinstance(plan, dict):
            label = str(plan.get("name") or f"排班 {index + 1}")
        else:
            label = f"排班 {index + 1}"
        options.append({"label": label, "value": str(index)})
    return options


class MaaAdapterHooks(ScriptAdapterHooks):
    """MAA 专项适配钩子。"""

    async def decorate_user_schema(
        self,
        schema: dict[str, Any],
        config_data: dict[str, Any],
        ctx: SchemaDecorationContext,
    ) -> dict[str, Any]:
        # 根据用户模式动态调整表单字段状态。
        _ = ctx

        info_group = config_data.get("Info")
        if not isinstance(info_group, dict):
            info_group = {}
        stage_mode = str(info_group.get("StageMode") or "Fixed")
        if stage_mode != "Fixed":
            plan_help = "当前由计划表控制，请前往计划表修改。"
            for field_key in (
                "Stage.MedicineNumb",
                "Stage.SeriesNumb",
                "Stage.Stage",
                "Stage.Stage_1",
                "Stage.Stage_2",
                "Stage.Stage_3",
                "Stage.Stage_Remain",
            ):
                set_schema_field_state(
                    schema,
                    field_key,
                    readonly=True,
                    help_text=plan_help,
                )

        infrast_mode = str(info_group.get("InfrastMode") or "Normal")
        infrast_options = _build_infrast_plan_options(config_data)
        if infrast_options:
            set_schema_field_options(schema, "Data.InfrastIndex", infrast_options)

        if infrast_mode != "Custom":
            custom_help = "当前不是自定义基建模式，此区域仅保留已保存数据。"
            set_schema_field_state(
                schema,
                "Data.InfrastIndex",
                readonly=True,
                help_text=custom_help,
            )
            set_schema_field_state(
                schema,
                "Data.CustomInfrast",
                readonly=True,
                help_text=custom_help,
                rows=12,
                size="large",
            )
        else:
            infrast_help = "可直接粘贴自定义基建配置 JSON，保存后会按当前排班生效。"
            if not infrast_options:
                infrast_help = "请先在下方填写有效的自定义基建 JSON，保存后即可选择排班。"
            set_schema_field_state(
                schema,
                "Data.InfrastIndex",
                help_text=infrast_help,
            )
            set_schema_field_state(
                schema,
                "Data.CustomInfrast",
                help_text="直接编辑或粘贴完整的自定义基建 JSON。",
                rows=12,
                size="large",
            )
        return schema

    async def check(self, runtime: ScriptAdapterRuntime) -> str:
        # 校验任务模式与脚本配置是否可运行。
        if runtime.mode not in ("AutoProxy", "ManualReview", "ScriptConfig"):
            return "不支持的任务模式，请检查任务配置！"

        script_config = await runtime.build_script_model()
        runtime.script_config = script_config
        if runtime.type_key != "MAA":
            return "脚本配置类型错误, 不是 MAA 脚本类型"

        if script_config.get("Emulator", "Id") == "-" or script_config.get(
            "Emulator", "Index"
        ) in ("", "-"):
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"

        maa_root_path = runtime.script_root_path(script_config)
        maa_config_path = runtime.script_config_dir(script_config)

        if not (maa_root_path / "MAA.exe").exists():
            return "MAA.exe 文件不存在，请检查 MAA 路径设置！"

        if not (
            (maa_config_path / "gui.json").exists()
            and (maa_config_path / "gui.new.json").exists()
        ):
            return "MAA 配置文件不存在，请检查 MAA 路径设置或先启动 MAA 生成配置文件！"

        if (
            runtime.mode != "ScriptConfig"
            and not runtime.default_config_file_path().exists()
        ):
            return "未完成 MAA 全局配置，请先配置 MAA！"

        return "Pass"

    async def prepare(self, runtime: ScriptAdapterRuntime) -> None:
        # 锁定脚本配置。
        await runtime.storage.lock()
        try:
            await self._prepare_locked(runtime)
        except Exception:
            await runtime.storage.unlock()
            raise

    async def _prepare_locked(self, runtime: ScriptAdapterRuntime) -> None:
        # 构建运行时脚本配置与用户配置。
        script_config = runtime.script_config or await runtime.storage.load_script_model()
        runtime.script_config = script_config
        runtime.user_config = await runtime.storage.load_user_collection()
        logger.success(f"{runtime.script_info.script_id} 已锁定, MAA 配置提取完成")

        # 记录配置目录并获取模拟器实例。
        workspace = runtime.create_script_config_workspace(script_config)
        await runtime.initialize_emulator_manager(
            script_config.get("Emulator", "Id")
        )
        # 备份 MAA 原始配置。
        workspace.backup()

        # 构建本次任务需要执行的用户列表。
        if runtime.mode == "ScriptConfig":
            runtime.script_info.user_list = [
                UserItem(
                    user_id=runtime.task_info.user_id or "Default",
                    name="",
                    status="等待",
                )
            ]
        else:
            runtime.script_info.user_list = [
                UserItem(
                    user_id=str(uid),
                    name=config.get("Info", "Name"),
                    status="等待",
                )
                for uid, config in runtime.user_config.items()
                if config.get("Info", "Status")
                and config.get("Info", "RemainedDay") != 0
            ]

        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(runtime.script_info.user_list)}"
        )

    def run_auto_proxy(self, runtime: ScriptAdapterRuntime):
        # 创建自动代理任务。
        from .maa_task.AutoProxy import AutoProxyTask

        return AutoProxyTask(
            runtime.script_info,
            runtime.script_config,
            runtime.user_config,
            runtime.require_emulator_manager(),
            notify_service=runtime.get_service("notify"),
            notify_channels=_read_notify_channels(runtime.script_config),
        )

    def run_manual_review(self, runtime: ScriptAdapterRuntime):
        # 创建人工排查任务。
        from .maa_task.ManualReview import ManualReviewTask

        return ManualReviewTask(
            runtime.script_info,
            runtime.script_config,
            runtime.user_config,
            runtime.require_emulator_manager(),
        )

    def run_script_config(self, runtime: ScriptAdapterRuntime):
        # 创建脚本配置任务。
        from .maa_task.ScriptConfig import ScriptConfigTask

        return ScriptConfigTask(
            runtime.script_info,
            runtime.script_config,
            runtime.user_config,
            runtime.require_emulator_manager(),
        )

    async def finalize(self, runtime: ScriptAdapterRuntime) -> None:
        # 执行任务结束后的统一收尾。
        if runtime.check_result != "Pass":
            runtime.script_info.status = "异常"
            return

        script_config = runtime.script_config
        if script_config is None:
            runtime.script_info.status = "异常"
            return

        # 解锁脚本配置并读取通知设置。
        logger.info("MAA 主任务已结束, 开始执行后续操作")
        notify_service = runtime.get_service("notify")
        notify_channels = _read_notify_channels(script_config)
        await runtime.storage.unlock()
        logger.success(f"已解锁脚本配置 {runtime.script_info.script_id}")

        if runtime.mode in ("AutoProxy", "ManualReview"):
            # 关闭模拟器并写回用户运行数据。
            emulator_manager = runtime.emulator_manager
            if emulator_manager is not None:
                await emulator_manager.close(script_config.get("Emulator", "Index"))

            await runtime.storage.save_user_models(runtime.user_config)

            # 汇总用户执行结果并发送任务报告。
            error_user = [
                user.name for user in runtime.script_info.user_list if user.status == "异常"
            ]
            over_user = [
                user.name for user in runtime.script_info.user_list if user.status == "完成"
            ]
            wait_user = [
                user.name for user in runtime.script_info.user_list if user.status == "等待"
            ]

            title = (
                f"{datetime.now().strftime('%m-%d')} | "
                f"{runtime.script_info.name or '空白'}的{TASK_MODE_ZH[runtime.mode]}任务报告"
            )
            result = {
                "title": f"{TASK_MODE_ZH[runtime.mode]}任务报告",
                "script_name": runtime.script_info.name or "空白",
                "start_time": runtime.begin_time,
                "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "completed_count": len(over_user),
                "uncompleted_count": len(error_user) + len(wait_user),
                "result": runtime.script_info.result,
            }

            system_message = (
                f"已完成用户数: {len(over_user)}, "
                f"未完成用户数: {len(error_user) + len(wait_user)}"
            )
            await _push_system_notification(
                notify_service,
                title=title.replace("报告", "已完成！"),
                message=system_message,
                ticker=system_message,
                timeout=10,
                channels=notify_channels,
            )
            if notify_service is not None:
                try:
                    if await notify_service.should_send_task_result(result):
                        await notify_service.send_payload(
                            _build_proxy_result_payload(title, result),
                            channels=notify_channels,
                        )
                except Exception as error:
                    logger.warning(
                        f"notify 代理结果发送失败: {type(error).__name__}: {error}"
                    )

        # 恢复 MAA 原始配置并清理临时目录。
        if runtime.config_workspace is not None:
            runtime.config_workspace.restore()

        runtime.script_info.status = "完成"

    async def on_crash(self, runtime: ScriptAdapterRuntime, error: Exception) -> None:
        # 标记异常状态并上报错误信息。
        from app.core.config import Config

        runtime.script_info.status = "异常"
        logger.exception(f"MAA 任务出现异常: {error}")
        await Config.send_websocket_message(
            id=runtime.task_info.task_id,
            type="Info",
            data={"Error": f"MAA 任务出现异常: {error}"},
        )
