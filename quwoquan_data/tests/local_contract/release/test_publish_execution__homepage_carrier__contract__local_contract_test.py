# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-023.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-023.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-023.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-023.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-023.t5
"""homepage 走 receipt 协议 publish 的目标发现与准入判据（DEC-027）。

homepage 此前在 publish 段被直接拒绝，于是四载体里唯一能解开 article entityRefs
闭包的那一个永远进不了池：article 可以先进池，但它的 publishable 要求所引用的
homepage 已 admitted，三篇已 approved 的 article 就一直卡在 REFERENCE_MISSING。

homepage 的对象身份是实体路径，没有 publishAngle/publishTitle/seq 这组发表坐标，
因此它需要自己的目标发现；它不需要的是自己的准入判据——qualify 一个 post 的那份
5.review attestation 同样 qualify 一个 entity，实体事务读的就是同一份文档。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from content.release.canonical import publish_execution
from content.release.canonical.publish_execution import (
    ReceiptPublishError,
    _homepage_targets,
    _publish_homepage_execution,
    publish_receipt_execution,
)
from core.paths import execution_root

EXECUTION_ID = "20260824--travel-homepage-wire--leshan--pilot-001"
ENTITY_REL = "地点/景区/乐山大佛"


def _entity_object(
    execution_id: str,
    *,
    entity_rel: str = ENTITY_REL,
    decision: str = "approved",
    frozen_inputs: tuple[str, ...] = ("_entity.json", "manifest.json", "page.md"),
) -> Path:
    object_dir = execution_root(execution_id) / "entities" / entity_rel
    (object_dir / "5.review").mkdir(parents=True, exist_ok=True)
    for name in frozen_inputs:
        body = (
            f"# {entity_rel.rsplit('/', 1)[-1]}\n"
            if name.endswith(".md")
            else json.dumps({"entityRef": f"/entity/{entity_rel}"}, ensure_ascii=False)
        )
        (object_dir / name).write_text(body, encoding="utf-8")
    (object_dir / "5.review/attestation.json").write_text(
        json.dumps({"decision": decision}, ensure_ascii=False), encoding="utf-8"
    )
    return object_dir


def test_targets_come_from_the_execution_entity_objects(tmp_path: Path) -> None:
    _entity_object(EXECUTION_ID)

    targets = _homepage_targets(EXECUTION_ID)

    # The canonical ref is the entity path itself, with no publish coordinates
    # projected onto it.
    assert [ref for ref, _dir in targets] == [ENTITY_REL]
    assert targets[0][1].name == "乐山大佛"


def test_an_execution_without_entity_objects_fails_closed() -> None:
    execution_id = "20260824--travel-homepage-empty--leshan--pilot-001"
    execution_root(execution_id).mkdir(parents=True, exist_ok=True)

    with pytest.raises(ReceiptPublishError, match="carries no entity object"):
        _homepage_targets(execution_id)


def test_plan_reports_an_approved_entity_as_publishable(tmp_path: Path) -> None:
    execution_id = "20260824--travel-homepage-plan--leshan--pilot-001"
    _entity_object(execution_id)

    report = _publish_homepage_execution(execution_id, apply=False)

    assert report["carrier"] == "homepage"
    assert report["mode"] == "plan"
    assert [row["status"] for row in report["objects"]] == ["planned"]
    assert report["objects"][0]["entityRef"] == f"/entity/{ENTITY_REL}"


def test_an_unapproved_entity_is_excluded_not_promoted() -> None:
    execution_id = "20260824--travel-homepage-unapproved--leshan--pilot-001"
    _entity_object(execution_id, decision="rejected")

    report = _publish_homepage_execution(execution_id, apply=False)

    # Excluded, not blocked: the object is a legitimate non-candidate rather than
    # a defect in the publish chain.
    assert [row["status"] for row in report["objects"]] == ["excluded"]
    assert report["excluded"] == 1
    assert "not approved" in report["objects"][0]["reason"]


def test_an_approved_entity_missing_frozen_inputs_is_blocked() -> None:
    execution_id = "20260824--travel-homepage-partial--leshan--pilot-001"
    _entity_object(execution_id, frozen_inputs=("_entity.json", "page.md"))

    report = _publish_homepage_execution(execution_id, apply=False)

    assert [row["status"] for row in report["objects"]] == ["blocked"]
    assert "manifest.json" in report["objects"][0]["reason"]


def test_the_publish_chain_dispatches_homepage_to_the_entity_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The anchor for the wiring itself: homepage reaches a publish decision.

    The receipt chain and layout preconditions are stubbed because this is about
    which path a frozen carrier is dispatched to, not about those preconditions —
    they are anchored where they are enforced.
    """

    execution_id = "20260824--travel-homepage-dispatch--leshan--pilot-001"
    _entity_object(execution_id)
    monkeypatch.setattr(
        publish_execution, "_receipt_chain_precondition", lambda _id: None
    )
    monkeypatch.setattr(publish_execution, "_frozen_carrier", lambda _id: "homepage")
    monkeypatch.setattr(
        "verify.verify_content_execution_layout.content_execution_layout_issues",
        lambda **_kwargs: [],
    )

    report = publish_receipt_execution(execution_id, apply=False)

    assert report["carrier"] == "homepage"
    assert [row["entityRef"] for row in report["objects"]] == [
        f"/entity/{ENTITY_REL}"
    ]


def test_apply_refuses_to_report_success_with_zero_promoted_objects() -> None:
    execution_id = "20260824--travel-homepage-zero--leshan--pilot-001"
    _entity_object(execution_id, decision="rejected")

    with pytest.raises(ReceiptPublishError, match="promoted zero objects"):
        _publish_homepage_execution(execution_id, apply=True)
