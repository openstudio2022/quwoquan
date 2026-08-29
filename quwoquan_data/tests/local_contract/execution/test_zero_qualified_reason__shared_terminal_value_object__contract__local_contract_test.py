"""GWT-011：零合格终态携带唯一 typed 原因与可行动证据。

绑定 `specs/feature-tree/discovery-content/object-homepage-coverage-scaling/`
`multi-carrier-release/spec.md` 的 `GWT-011.t3`、`GWT-011.t4`
与 L2 `design.md` 的 `DEC-005`、`DEC-013`。
"""
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-011.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-011.t4
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

from content.execution.closure.publish_outcome import (  # noqa: E402
    OBJECT_ASSET_OVER_BUDGET,
    OBJECT_CLOSURE_OVER_BUDGET,
    PUBLISH_APPLY_FAILED,
)
from content.execution.closure.zero_qualified_reason import (  # noqa: E402
    ZeroQualifiedReasonError,
    non_resumable_reason_payload,
    observed_stages,
    operator_actions,
    parse_zero_qualified_reason,
    publish_admission_over_budget,
    reason_codes,
    resumable_reason_payload,
)
from core.paths import SCHEMA_ROOT  # noqa: E402
from core.schema import load_schema, validate_strict  # noqa: E402

DEFINITION_PATH = SCHEMA_ROOT / "_common" / "zero_qualified_reason.schema.json"

RESUMABLE_CODE = "RESUMABLE_INTERRUPTION"
SELECTOR_CODE = "ALL_CANDIDATE_ENTITIES_SELECTOR_EXCLUDED"
OVER_BUDGET_CODE = "ALL_OBJECTS_OVER_PUBLISH_STORAGE_BUDGET"

# 七个原因值各自的唯一观测阶段与唯一运营动作。断言方向是「代码侧期望 == schema
# 声明」：闭集只在 schema 声明一次，本表是读者对那一次声明的复核清单。
TERMINAL_CONTRACT: dict[str, tuple[str, str]] = {
    "SOURCE_POOL_EMPTY": ("source_discovery", "repair_source"),
    "SOURCE_ACCESS_DENIED_OR_UNREACHABLE": ("source_discovery", "repair_source"),
    "BATCH_DEADLINE_EXHAUSTED": ("delivery", "refreeze_time_budget"),
    "ALL_OBJECTS_QUALITY_REJECTED": ("review", "repair_source"),
    RESUMABLE_CODE: ("delivery", "resume"),
    OVER_BUDGET_CODE: ("publish_admission", "reduce_object_footprint"),
    SELECTOR_CODE: ("selector_admission", "broaden_candidate_scope"),
}
NON_RESUMABLE_CODES = tuple(
    code for code in TERMINAL_CONTRACT if code != RESUMABLE_CODE
)


def _definition() -> dict[str, Any]:
    """按消费者内联后的形态取出共享值对象。"""
    return load_schema("_common", "zero_qualified_reason")["$defs"][
        "zeroQualifiedReason"
    ]


def _reason(code: str, **overrides: Any) -> dict[str, Any]:
    stage, action = TERMINAL_CONTRACT[code]
    reason: dict[str, Any] = {
        "code": code,
        "observedStage": stage,
        "determinedAt": "2026-08-16T00:10:00Z",
        "operatorAction": action,
    }
    if code == RESUMABLE_CODE:
        reason["resumableRefs"] = ["posts/article/乐山大佛__001"]
    else:
        reason["nonResumableBasis"] = {
            "summary": f"{code} 的判定依据",
            "evidenceRef": "receipts/article-review-zero-qualified-basis.json",
            "evidenceDigest": "sha256:" + "c" * 64,
        }
    if code == SELECTOR_CODE:
        reason["admissionExclusionRefs"] = [
            {
                "entityRef": "地点/景区/乐山大佛",
                "exclusionRef": "receipts/selection-exclusions.json#/0",
            }
        ]
    reason.update(overrides)
    return reason


def _issues(reason: dict[str, Any]) -> list[str]:
    return validate_strict(reason, _definition())


def test_closed_set_has_exactly_seven_typed_reasons() -> None:
    """GWT-011.t3：闭集恰好七个值，且代码侧不另立一份枚举。"""
    assert list(reason_codes()) == list(TERMINAL_CONTRACT)


@pytest.mark.parametrize("code", tuple(TERMINAL_CONTRACT))
def test_each_typed_reason_is_individually_constructible(code: str) -> None:
    """GWT-011.t3：七个原因分别成立，不合并成同一个 blocked 汇总值。"""
    assert _issues(_reason(code)) == []
    assert parse_zero_qualified_reason(_reason(code), label=code).code == code


@pytest.mark.parametrize(
    ("code", "stage"),
    tuple(
        (code, stage)
        for code, (bound_stage, _action) in TERMINAL_CONTRACT.items()
        for stage in observed_stages()
        if stage != bound_stage
    ),
)
def test_each_reason_binds_exactly_one_observed_stage(
    code: str,
    stage: str,
) -> None:
    """GWT-011.t3：每个原因值只绑定一个观测阶段，阶段取值范围不得被放宽。

    这一条同时覆盖 `DEC-013` 的两个方向：review 阶段的质量被拒取不到 publish
    准入，publish 准入的超预算结论也取不到 review；`selector_admission` 与
    `source_discovery` 互相取不到。
    """
    assert _issues(_reason(code, observedStage=stage)) != []


@pytest.mark.parametrize(
    ("code", "action"),
    tuple(
        (code, action)
        for code, (_stage, bound_action) in TERMINAL_CONTRACT.items()
        for action in operator_actions()
        if action != bound_action
    ),
)
def test_each_reason_binds_exactly_one_operator_action(
    code: str,
    action: str,
) -> None:
    """GWT-011.t4：运营者只读回执即可决定唯一动作。

    缩减对象体量只由超预算原因取到，扩大候选范围只由准入零通过原因取到，两者都
    取不到修来源，也取不到改写预算或阈值数值这种不在闭集里的动作。
    """
    assert _issues(_reason(code, operatorAction=action)) != []


def test_resumable_interruption_requires_precise_resumable_refs() -> None:
    """GWT-011.t4：可续跑中断给出精确可续跑 refs。"""
    reason = _reason(RESUMABLE_CODE)
    del reason["resumableRefs"]

    assert _issues(reason) != []
    assert _issues(_reason(RESUMABLE_CODE, resumableRefs=[])) != []


@pytest.mark.parametrize("code", NON_RESUMABLE_CODES)
def test_the_other_six_reasons_require_a_determination_basis(code: str) -> None:
    """GWT-011.t4：其余六种原因给出不可续跑的判定依据。"""
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


def test_selector_admission_reason_requires_per_entity_exclusion_refs() -> None:
    """GWT-011.t4：准入零通过原因在判定依据之外给出逐实体准入排除 refs。"""
    reason = _reason(SELECTOR_CODE)
    del reason["admissionExclusionRefs"]

    assert _issues(reason) != []
    assert _issues(_reason(SELECTOR_CODE, admissionExclusionRefs=[])) != []


@pytest.mark.parametrize(
    "code",
    tuple(code for code in TERMINAL_CONTRACT if code != SELECTOR_CODE),
)
def test_only_the_selector_reason_carries_admission_exclusion_refs(
    code: str,
) -> None:
    reason = _reason(
        code,
        admissionExclusionRefs=[
            {
                "entityRef": "地点/景区/乐山大佛",
                "exclusionRef": "receipts/selection-exclusions.json#/0",
            }
        ],
    )

    assert _issues(reason) != []


@pytest.mark.parametrize(
    "unknown",
    ("BLOCKED", "blocked", "ALL_OBJECTS_QUALITY_REJECTED_V2", ""),
)
def test_reason_outside_the_closed_set_fails_closed(unknown: str) -> None:
    """闭集之外的入站 code 判否，不映射为任何既有原因，也不退回 generic blocked。"""
    reason = _reason(RESUMABLE_CODE)
    reason["code"] = unknown

    assert _issues(reason) != []
    with pytest.raises(ZeroQualifiedReasonError) as failure:
        parse_zero_qualified_reason(reason, label="unknown-code")
    assert "zero_qualified_reason.schema.json" in str(failure.value)


@pytest.mark.parametrize(
    "field",
    ("code", "observedStage", "determinedAt", "operatorAction"),
)
def test_absent_required_declaration_fails_closed(field: str) -> None:
    """缺声明时不替观测者选一个原因：四个必填项缺任一即判否。"""
    reason = _reason("SOURCE_POOL_EMPTY")
    del reason[field]

    assert _issues(reason) != []
    with pytest.raises(ZeroQualifiedReasonError):
        parse_zero_qualified_reason(reason, label=f"absent-{field}")


@pytest.mark.parametrize("value", (None, "SOURCE_POOL_EMPTY", 7, []))
def test_reason_must_be_an_object(value: object) -> None:
    with pytest.raises(ZeroQualifiedReasonError):
        parse_zero_qualified_reason(value, label="non-object")


def test_unknown_evidence_field_fails_closed() -> None:
    """契约未声明的字段是死分支：多写一个键即判否。"""
    reason = _reason("SOURCE_POOL_EMPTY", retryHint="expand-region")

    assert _issues(reason) != []


def test_production_payload_builders_refuse_illegal_pairings() -> None:
    """生产侧构造器与读侧同一判据：构造不出的原因不落盘。"""
    with pytest.raises(ZeroQualifiedReasonError):
        non_resumable_reason_payload(
            code="ALL_OBJECTS_QUALITY_REJECTED",
            observed_stage="publish_admission",
            operator_action="reduce_object_footprint",
            determined_at="2026-08-16T00:10:00Z",
            summary="review 结论借用 publish 准入阶段",
            evidence_ref="receipts/article-review-zero-qualified-basis.json",
            evidence_digest="sha256:" + "c" * 64,
            label="illegal-stage",
        )
    with pytest.raises(ZeroQualifiedReasonError):
        resumable_reason_payload(
            determined_at="2026-08-16T00:10:00Z",
            resumable_refs=[],
            label="empty-refs",
        )
    payload = resumable_reason_payload(
        determined_at="2026-08-16T00:10:00Z",
        resumable_refs=["posts/article/乐山大佛__001"],
        label="resumable",
    )
    assert parse_zero_qualified_reason(payload, label="resumable").resumable is True


def test_publish_storage_budget_reason_only_covers_budget_exclusions() -> None:
    """DEC-013：批次级原因引用对象级排除码而不复制，也不兜住其它 publish 失败。"""
    budget_only = [
        {"objectRef": "posts/article/a", "issues": [OBJECT_CLOSURE_OVER_BUDGET]},
        {"objectRef": "posts/article/b", "issues": [OBJECT_ASSET_OVER_BUDGET]},
    ]
    mixed = [
        *budget_only,
        {"objectRef": "posts/article/c", "issues": [PUBLISH_APPLY_FAILED]},
    ]

    assert publish_admission_over_budget(budget_only) is True
    assert publish_admission_over_budget(mixed) is False
    assert publish_admission_over_budget([]) is False


def test_object_level_codes_stay_out_of_the_batch_closed_set() -> None:
    """对象级排除码不得成为批次级原因值。"""
    assert "OBJECT_CLOSURE_OVER_BUDGET" not in reason_codes()
    assert "OBJECT_ASSET_OVER_BUDGET" not in reason_codes()


def test_definition_lives_in_exactly_one_place() -> None:
    """DEC-005：三层引用同一定义，不各自声明枚举。"""
    restating = [
        path.relative_to(SCHEMA_ROOT).as_posix()
        for path in sorted(SCHEMA_ROOT.rglob("*.schema.json"))
        if path != DEFINITION_PATH
        and any(code in path.read_text(encoding="utf-8") for code in reason_codes())
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
