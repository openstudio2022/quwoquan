# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-003.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/on-demand-content-pool-admission/spec.md#gwt-003.t7
"""media workUnit 复合验收的子句级直接断言。

覆盖数量三值（`targetObjectCount` / `targetEntityCount` / `approvedQuota`）、
每个 workUnit 的 manifest/receipt exact pair、brief 与 content object 保持同一
`workUnitId`，以及无法唯一映射时只排除该资产的 partial/blocked 分界。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from content.execution.controller import content_plan_items
from content.execution.planning.media_work_units import (
    media_work_unit_object_bindings,
    project_media_work_units,
    validate_frozen_work_units,
    work_unit_object_binding,
)
from content.execution.planning.selection import build_execution_spec
from support.capacity_calibration_fixture import synthetic_capacity_source_binding

AMBIGUOUS = "DATA.SOURCE.ENTITY_CATALOG_AMBIGUOUS"
ENTITY_TYPE = "地点/景区"


def _sha(token: str) -> str:
    filler = token.encode("utf-8").hex()
    return "sha256:" + (filler * 64)[:64]


def _candidate(*, asset_id: str, entity: str) -> dict[str, object]:
    return {
        "carrier": "image",
        "manifestRef": "acquisition/image/manifest.json",
        "manifestDigest": _sha("m"),
        "receiptRef": f"acquisition/image/receipt-{asset_id}.json",
        "receiptDigest": _sha(f"r{asset_id}"),
        "assetId": asset_id,
        "contentSha256": _sha(asset_id),
        "sourceEntityId": entity,
    }


def _target(name: str) -> dict[str, object]:
    return {"name": name, "entityType": ENTITY_TYPE}


def _projection():
    """三张可映射资产（两个实体）+ 一张目录外资产。"""

    return project_media_work_units(
        [
            _candidate(asset_id="a1", entity="青城山"),
            _candidate(asset_id="a2", entity="青城山"),
            _candidate(asset_id="a3", entity="都江堰"),
            _candidate(asset_id="a4", entity="不在目录中的实体"),
        ],
        [_target("青城山"), _target("都江堰")],
    )


def _spec(*, approved_quota: int):
    projection = _projection()
    admitted = set(projection.coverage_target_names)
    targets = [_target(name) for name in ("青城山", "都江堰") if name in admitted]
    spec = build_execution_spec(
        execution_id="20260827--travel-image-workunit--china--pilot-001",
        name="media workUnit 复合验收",
        title="media workUnit 复合验收",
        region="中国/四川省",
        category="景区",
        targets=targets,
        created_by="test",
        entity_articles_per_target=0,
        entity_homepages_per_target=0,
        image_works_per_target=1,
        video_works_per_target=0,
        target_entity_count=len(targets),
        approved_quota=approved_quota,
        oversample_factor=1.0,
        capacity_calibration=synthetic_capacity_source_binding(),
        frozen_at_epoch_seconds=2_000_000_000,
        media_work_units=projection.work_units,
        media_work_unit_exclusions=projection.exclusions,
    )
    return projection, spec


class _Scheduler:
    def assign(self, **_kwargs: object) -> dict[str, object]:
        return {"authorId": "image-author"}

    def schedule(self, _assignment: dict[str, object]) -> dict[str, object]:
        return {"mode": "test"}


def _plan_objects(monkeypatch, *, target: str, candidates: list[dict[str, object]]):
    """跑一次真实 plan item 物化，捕获 brief 与 content object 两侧载荷。"""

    briefs: dict[str, dict[str, object]] = {}
    monkeypatch.setattr(
        content_plan_items,
        "write_brief_object",
        lambda _execution_id, ref, brief, **_kwargs: briefs.__setitem__(
            str(ref), dict(brief)
        ),
    )
    items: list[dict[str, object]] = []
    content_plan_items.append_image_plan_items(
        ctx=SimpleNamespace(execution_id="20260827--travel-image-workunit--china--pilot-001"),
        scheduler=_Scheduler(),
        entity_type=ENTITY_TYPE,
        target=target,
        candidates=candidates,
        items=items,
    )
    return briefs, items


def _plan_candidate(binding) -> dict[str, object]:
    return {
        "workUnitId": binding.work_unit_id,
        "manifestRef": "acquisition/image/manifest.json",
        "manifestDigest": _sha("m"),
        "receiptRef": binding.receipt_ref,
        "receiptDigest": _sha(f"r{binding.asset_id}"),
        "assetId": binding.asset_id,
        "contentSha256": binding.content_sha256,
        "sourceEntityId": binding.coverage_target_name,
        "coverageTarget": {
            "name": binding.coverage_target_name,
            "entityType": binding.coverage_target_type,
        },
        "title": binding.asset_id,
        "sourceId": "openverse",
        "caption": "青城山前山山门",
        "collectionId": f"acquisition:image:{binding.asset_id}",
        "sourceRef": "sources/openverse/source.md",
        "assetRef": f"sources/openverse/assets/{binding.asset_id}.jpg",
    }


def test_object_and_entity_counts_come_from_the_mapped_projection() -> None:
    """t1：targetObjectCount 等于可映射 accepted assets 数，targetEntityCount 等于唯一 coverage target 数。"""

    projection, spec = _spec(approved_quota=5)
    policy = spec["executionPolicy"]

    assert projection.mapped_object_count == 3
    assert policy["targetObjectCount"] == 3 == len(projection.work_units)
    assert projection.coverage_target_names == ("青城山", "都江堰")
    assert policy["targetEntityCount"] == 2 == len(projection.coverage_target_names)


def test_approved_quota_is_not_silently_lowered_to_the_entity_count() -> None:
    """t2：approvedQuota 保留请求对象下限，不按实体数静默降低。"""

    projection, spec = _spec(approved_quota=5)
    policy = spec["executionPolicy"]

    assert policy["approvedQuota"] == 5
    assert policy["approvedQuota"] > policy["targetEntityCount"]
    assert policy["approvedQuota"] > policy["targetObjectCount"]
    # 对象下限只留在 approvedQuota；实体维度不得改写它，因此 shortfall 仍按 5 算。
    assert projection.shortfall(policy["approvedQuota"]) == 2
    assert spec["acceptance"]["minPostsPerEntity"] == 0


def test_each_work_unit_binds_one_exact_pair_and_one_coverage_target() -> None:
    """t3：每个 workUnit 精确绑定一个 receipt/asset/content digest 与一个 coverage target。"""

    projection, _spec_result = _spec(approved_quota=5)
    work_units = projection.work_units

    pairs = {(unit["receiptRef"], unit["assetId"]) for unit in work_units}
    assert len(pairs) == len(work_units)
    assert len({unit["contentSha256"] for unit in work_units}) == len(work_units)
    for unit in work_units:
        assert unit["coverageTarget"]["entityType"] == ENTITY_TYPE
        assert unit["coverageTarget"]["name"] in {"青城山", "都江堰"}
    assert validate_frozen_work_units([dict(unit) for unit in work_units]) == work_units


def test_brief_and_content_object_share_one_work_unit_identity(monkeypatch) -> None:
    """t4：一个 workUnit 只生成一个 brief/content object，且两侧同一 workUnitId。"""

    projection, _spec_result = _spec(approved_quota=5)
    bindings = [
        binding
        for binding in media_work_unit_object_bindings(
            projection.work_units, carrier="image"
        ).bindings
        if binding.coverage_target_name == "青城山"
    ]
    assert len(bindings) == 2

    briefs, items = _plan_objects(
        monkeypatch,
        target="青城山",
        candidates=[_plan_candidate(binding) for binding in bindings],
    )

    assert len(items) == 2 == len(briefs)
    for item in items:
        brief = briefs[str(item["ref"])]
        assert brief["workUnitId"] == item["workUnitId"]
    assert {str(item["workUnitId"]) for item in items} == {
        binding.work_unit_id for binding in bindings
    }
    assert {str(item["ref"]) for item in items} == {
        binding.object_ref(target="青城山") for binding in bindings
    }


def test_a_work_unit_that_cannot_map_uniquely_excludes_only_that_asset() -> None:
    """t7：无法唯一映射的单资产写 typed exclusion，同批其它资产照常绑定。"""

    projection, _spec_result = _spec(approved_quota=5)
    rows = [dict(unit) for unit in projection.work_units]
    rows[0]["assetId"] = "tampered"

    binding_set = media_work_unit_object_bindings(rows, carrier="image")

    assert len(binding_set.bindings) == 2
    assert len(binding_set.exclusions) == 1
    assert binding_set.exclusions[0]["code"] == AMBIGUOUS
    assert binding_set.exclusions[0]["assetId"] == "tampered"


def test_a_declared_work_unit_identity_never_degrades_to_an_unidentified_object() -> None:
    """声明了 workUnitId 但无法唯一映射时判否，不静默产出无身份对象。"""

    projection, _spec_result = _spec(approved_quota=5)
    drifted = dict(projection.work_units[0])
    drifted["assetId"] = "tampered"

    with pytest.raises(ValueError, match="cannot be bound to exactly one content object"):
        work_unit_object_binding(drifted, carrier="image")


def test_partial_keeps_real_objects_and_only_zero_objects_is_blocked() -> None:
    """t7：仍有真实对象时保持 partial，零对象才 blocked。"""

    partial = _projection()
    assert partial.mapped_object_count == 3
    assert partial.shortfall(5) == 2
    assert len(partial.exclusions) == 1

    blocked = project_media_work_units(
        [_candidate(asset_id="a9", entity="不在目录中的实体")],
        [_target("青城山")],
    )
    assert blocked.mapped_object_count == 0
    assert blocked.shortfall(5) == 5
    assert len(blocked.exclusions) == 1
