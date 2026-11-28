"""为面板提供作用域外的只读编辑信息。"""

from uuid import UUID

from auto_mas_core import Config
from auto_mas_core.host.models_schema import ComboBoxItem
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from maa_adapter.config.access import _maa_script_config
from maa_adapter.config.plan import MaaPlanConfig

router = APIRouter(prefix="/api/plugin/maa_adapter/editor", include_in_schema=False)


class UserEditorContext(BaseModel):
    server: str
    quickConfig: bool
    plans: list[ComboBoxItem]


@router.get("/user/{script_id}/{user_id}")
async def user_editor_context(script_id: UUID, user_id: UUID) -> UserEditorContext:
    """返回本账号的区服、覆写开关和可关联的 MAA 计划。"""
    try:
        user = _maa_script_config(str(script_id)).users[user_id]
    except (KeyError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="MAA 账号不存在") from exc
    return UserEditorContext(
        server=user.Info.Server,
        quickConfig=user.Info.IfQuickConfig,
        plans=[
            ComboBoxItem(label=plan.Info.Name, value=str(uid))
            for uid, plan in Config.PlanConfig.items()
            if isinstance(plan, MaaPlanConfig)
        ],
    )


@router.get("/plan/{plan_id}/active")
async def active_plan_fields(plan_id: UUID, server: str) -> dict[str, str | int]:
    """只读投影账号关联计划当前游戏日的作战配置。"""
    try:
        plan = Config.PlanConfig[plan_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="MAA 计划不存在") from exc
    if not isinstance(plan, MaaPlanConfig):
        raise HTTPException(status_code=404, detail="MAA 计划不存在")
    day = getattr(plan, plan.current_game_group(server))
    return day.model_dump()
