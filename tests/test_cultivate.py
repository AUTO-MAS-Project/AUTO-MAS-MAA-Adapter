"""自动培养选人和下发顺序。"""

import json

import pytest
from maa_adapter.cultivate.service import DepotCultivateService
from maa_adapter.cultivate.task_builder import _build_auto_cultivate_task
from maa_adapter.cultivate.types import (
    CultivateDataSet,
    DemandEntry,
    Goal,
    OperatorTarget,
    Progression,
    Recipe,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("count", "expected_indices"),
    [(3, [0, 1, 2]), (10, list(range(10))), (11, [0, *range(2, 11)])],
)
async def test_auto_cultivate_injects_selected_operators_in_target_order(
    tmp_path, count, expected_indices
):
    operator_ids = [f"char_{index}" for index in range(count)]
    targets = [
        OperatorTarget(operator_id, (Goal("elite", "", 1),))
        for operator_id in operator_ids
    ]
    # 前两名的现成材料各满足 50%，剩余材料都能从库存合成。
    dataset = CultivateDataSet(
        demands={
            operator_id: (
                DemandEntry(
                    "elite", "", 1, {"crafted": 10} if index < 2 else {"ready": 1}
                ),
            )
            for index, operator_id in enumerate(operator_ids)
        },
        drops=(),
        stages={},
        recipes=(Recipe("crafted", {"ingredient": 1}),),
        material_class={"crafted": "synthesizable"},
    )
    (tmp_path / "DepotData.json").write_text(
        json.dumps(
            {
                "data": {"crafted": 5, "ingredient": 15, "ready": count - 2},
                "syncTime": 1,
            }
        ),
        encoding="utf-8",
    )

    async def load_dataset(config_path, proxy):
        return dataset

    _, _, _, selected = await DepotCultivateService(
        dataset_loader=load_dataset
    ).prepare_cultivate(
        targets=targets,
        maa_data_dir=tmp_path,
        config_path=tmp_path,
        skland=({key: Progression.default() for key in operator_ids}, 1),
        require_observations=True,
        auto_raise=True,
    )
    task = _build_auto_cultivate_task(
        targets=selected,
        catalog=[
            {
                "value": operator_id,
                "label": operator_id,
                "profession": "guard",
                "skills": [],
            }
            for operator_id in operator_ids
        ],
        source_task=None,
    )

    assert task is not None
    assert [plan["Name"] for plan in task["Plans"]] == [
        operator_ids[index] for index in expected_indices
    ]
