"""GWT-011：零合格终态携带唯一 typed 原因与可行动证据。

绑定 `specs/feature-tree/discovery-content/object-homepage-coverage-scaling/`
`multi-carrier-release/spec.md` 的 `GWT-011.t3`、`GWT-011.t4`
与 L2 `design.md` 的 `DEC-005`。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-011
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
if str(DATA_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(DATA_ROOT / "scripts"))

from core.paths import SCHEMA_ROOT  # noqa: E402
from core.schema import load_schema, validate_strict  # noqa: E402

DEFINITION_PATH = SCHEMA_ROOT / "_common" / "zero_qualified_reason.schema.json"

NON_RESUMABLE_CODES = (
    "SOURCE_POOL_EMPTY",
    "SOURCE_ACCESS_DENIED_OR_UNREACHABLE",
    "BATCH_DEADLINE_EXHAUSTED",
    "ALL_OBJECTS_QUALITY_REJECTED",
)
RESUMABLE_CODE = "RESUMABLE_INTERRUPTION"
CLOSED_SET = (*NON_RESUMABLE_CODES, RESUMABLE_CODE)
OBSERVED_STAGE_BY_CODE = {
    "SOURCE_POOL_EMPTY": "source_discovery",
    "SOURCE_ACCESS_DENIED_OR_UNREACHABLE": "source_discovery",
    "ALL_OBJECTS_QUALITY_REJECTED": "review",
    "BATCH_DEADLINE_EXHAUSTED": "delivery",
    RESUMABLE_CODE: "delivery",
}


def _definition() -> dict[str, Any]:
    """按消费者内联后的形态取出共享值对象。"""
    return load_schema("_common", "zero_qualified_reason")["$defs"][
        "zeroQualifiedReason"
    ]


def _reason(code: str, **overrides: Any) -> dict[str, Any]:
    reason: dict[str, Any] = {
        "code": code,
        "observedStage": OBSERVED_STAGE_BY_CODE[code],
        "determinedAt": "2026-08-16T00:10:00Z",
    }
    if code == RESUMABLE_CODE:
        reason["operatorAction"] = "resume"
        reason["resumableRefs"] = ["posts/article/乐山大佛__001"]
    else:
        reason["operatorAction"] = "repair_source"
        reason["nonResumableBasis"] = {
            "summary": "本次冻结目标集内无任何可用来源单元",
            "evidenceRef": "evidence/source_discovery/report.json",
            "evidenceDigest": "sha256:" + "c" * 64,
        }
    reason.update(overrides)
    return reason


def _issues(reason: dict[str, Any]) -> list[str]:
    return validate_strict(reason, _definition())


@pytest.mark.parametrize("code", CLOSED_SET)
def test_each_typed_reason_is_individually_constructible(code: str) -> None:
    """GWT-011.t3：五个原因分别成立，不合并成同一个 blocked 汇总值。"""
    assert _issues(_reason(code)) == []


def test_closed_set_has_exactly_five_typed_reasons() -> None:
    """GWT-011.t3：闭集只有五个值。"""
    assert _definition()["properties"]["code"]["enum"] == list(CLOSED_SET)


def test_reason_outside_the_closed_set_is_rejected() -> None:
    reason = _reason(RESUMABLE_CODE)
    reason["code"] = "BLOCKED"

    assert _issues(reason) != []


def test_resumable_interruption_requires_precise_resumable_refs() -> None:
    """GWT-011.t4：可续跑中断给出精确可续跑 refs。"""
    reason = _reason(RESUMABLE_CODE)
    del reason["resumableRefs"]

    assert _issues(reason) != []
    assert _issues(_reason(RESUMABLE_CODE, resumableRefs=[])) != []


@pytest.mark.parametrize("code", NON_RESUMABLE_CODES)
def test_non_resumable_reason_requires_a_determination_basis(code: str) -> None:
    """GWT-011.t4：其余原因给出不可续跑的判定依据。"""
    reason = _reason(code)
    del reason["nonResumableBasis"]

    assert _issues(reason) != []


@pytest.mark.parametrize("code", NON_RESUMABLE_CODES)
def test_non_resumable_reason_must_not_carry_resumable_refs(code: str) -> None:
    """判定依据与可续跑 refs 互斥，避免同一原因同时声明两种去向。"""
    reason = _reason(code, resumableRefs=["posts/article/乐山大佛__001"])

    assert _issues(reason) != []


def test_resumable_reason_must_not_carry_a_determination_basis() -> None:
    reason = _reason(RESUMABLE_CODE)
    reason["nonResumableBasis"] = {
        "summary": "占位",
        "evidenceRef": "evidence/x.json",
        "evidenceDigest": "sha256:" + "c" * 64,
    }

    assert _issues(reason) != []


@pytest.mark.parametrize("code", CLOSED_SET)
def test_operator_action_follows_resumability(code: str) -> None:
    """GWT-011.t4：运营者只读回执即可决定续跑、修来源还是重新冻结时间预算。"""
    expected_actions = (
        ["resume"] if code == RESUMABLE_CODE else ["repair_source", "refreeze_time_budget"]
    )
    for action in expected_actions:
        assert _issues(_reason(code, operatorAction=action)) == []

    illegal_action = "repair_source" if code == RESUMABLE_CODE else "resume"
    assert _issues(_reason(code, operatorAction=illegal_action)) != []


@pytest.mark.parametrize(
    ("code", "stage"),
    (
        ("SOURCE_POOL_EMPTY", "delivery"),
        ("SOURCE_ACCESS_DENIED_OR_UNREACHABLE", "delivery"),
        ("ALL_OBJECTS_QUALITY_REJECTED", "delivery"),
        ("BATCH_DEADLINE_EXHAUSTED", "source_discovery"),
    ),
)
def test_reason_is_bound_to_the_stage_that_can_observe_it(
    code: str,
    stage: str,
) -> None:
    """DEC-005：写者按观测者定，截止耗尽只有交付阶段能观测。"""
    assert _issues(_reason(code, observedStage=stage)) != []


def test_definition_lives_in_exactly_one_place() -> None:
    """DEC-005：三层引用同一定义，不各自声明枚举。"""
    restating = [
        path.relative_to(SCHEMA_ROOT).as_posix()
        for path in sorted(SCHEMA_ROOT.rglob("*.schema.json"))
        if path != DEFINITION_PATH
        and RESUMABLE_CODE in path.read_text(encoding="utf-8")
    ]

    assert restating == []


def test_definition_is_inlinable_by_every_consuming_layer() -> None:
    """外部引用的 $defs 不得含内部 $ref，否则被内联到消费者后无法解析。"""
    raw = json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))

    assert _internal_refs(raw["$defs"]["zeroQualifiedReason"]) == []


def _internal_refs(node: Any) -> list[str]:
    if isinstance(node, dict):
        found = [
            value
            for key, value in node.items()
            if key == "$ref" and isinstance(value, str) and value.startswith("#/")
        ]
        for value in node.values():
            found.extend(_internal_refs(value))
        return found
    if isinstance(node, list):
        return [ref for item in node for ref in _internal_refs(item)]
    return []
