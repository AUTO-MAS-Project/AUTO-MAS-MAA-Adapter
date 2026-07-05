from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from script_maa.adapter import MaaAdapterHooks


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
