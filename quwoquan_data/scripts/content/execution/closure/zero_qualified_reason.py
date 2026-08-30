"""批次级零合格原因的唯一代码侧入口（`DEC-005` / `DEC-013`）。

闭集只在 `quwoquan_data/schema/_common/zero_qualified_reason.schema.json` 声明一次，
本模块从该 schema 读出三个闭集，不在代码里重述枚举。任何消费者读到闭集之外的取值
一律判否：`blocked` 不是可以兜住未知原因的汇总值，缺声明时不得替观测者选一个原因。
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.schema import load_schema, validate_strict

from content.execution.closure.publish_outcome import (
    OBJECT_ASSET_OVER_BUDGET,
    OBJECT_CLOSURE_OVER_BUDGET,
)

SOURCE_POOL_EMPTY = "SOURCE_POOL_EMPTY"
SOURCE_ACCESS_DENIED_OR_UNREACHABLE = "SOURCE_ACCESS_DENIED_OR_UNREACHABLE"
BATCH_DEADLINE_EXHAUSTED = "BATCH_DEADLINE_EXHAUSTED"
ALL_OBJECTS_QUALITY_REJECTED = "ALL_OBJECTS_QUALITY_REJECTED"
RESUMABLE_INTERRUPTION = "RESUMABLE_INTERRUPTION"
ALL_OBJECTS_OVER_PUBLISH_STORAGE_BUDGET = "ALL_OBJECTS_OVER_PUBLISH_STORAGE_BUDGET"
ALL_CANDIDATE_ENTITIES_SELECTOR_EXCLUDED = (
    "ALL_CANDIDATE_ENTITIES_SELECTOR_EXCLUDED"
)

# 媒体侧只产出对象级排除码，批次级原因引用它们而不复制（`DEC-013`）。批次内每个
# 对象都被这两个码之一拦下时，批次级原因才是「全批超出单对象存储预算」。
PUBLISH_STORAGE_BUDGET_OBJECT_ISSUE_CODES = frozenset(
    {OBJECT_ASSET_OVER_BUDGET, OBJECT_CLOSURE_OVER_BUDGET}
)

_DEFINITION_KEY = "zeroQualifiedReason"


class ZeroQualifiedReasonError(ValueError):
    """闭集之外的取值或缺声明的证据字段，一律在此判否。"""


@lru_cache(maxsize=1)
def reason_definition() -> dict[str, Any]:
    """取出共享值对象，形态与被消费者内联后完全一致。"""

    definition = load_schema("_common", "zero_qualified_reason")["$defs"][
        _DEFINITION_KEY
    ]
    if not isinstance(definition, dict):
        raise ZeroQualifiedReasonError(
            "zero_qualified_reason.schema.json 未声明 $defs/zeroQualifiedReason"
        )
    return definition


def _closed_set(field: str) -> tuple[str, ...]:
    declaration = reason_definition()["properties"][field]
    values = declaration.get("enum")
    if not isinstance(values, list) or not values:
        raise ZeroQualifiedReasonError(
            f"zeroQualifiedReason.{field} 必须以 enum 声明闭集"
        )
    return tuple(str(value) for value in values)


def reason_codes() -> tuple[str, ...]:
    return _closed_set("code")


def observed_stages() -> tuple[str, ...]:
    return _closed_set("observedStage")


def operator_actions() -> tuple[str, ...]:
    return _closed_set("operatorAction")


@dataclass(frozen=True, slots=True)
class ZeroQualifiedReason:
    """一个批次级零合格终态的 typed 原因。"""

    code: str
    observed_stage: str
    determined_at: str
    operator_action: str
    resumable_refs: tuple[str, ...] = ()
    admission_exclusion_refs: tuple[tuple[str, str], ...] = ()
    non_resumable_summary: str = ""
    non_resumable_evidence_ref: str = ""
    non_resumable_evidence_digest: str = ""

    @property
    def resumable(self) -> bool:
        return self.code == RESUMABLE_INTERRUPTION


def parse_zero_qualified_reason(
    value: object,
    *,
    label: str,
) -> ZeroQualifiedReason:
    """按共享值对象解码一个原因；闭集之外的取值与缺声明的证据都判否。

    未知 code / observedStage / operatorAction 不映射为任何既有原因，也不退化成不带
    原因的 `blocked`：判否文本点名闭集本身，读者据此去改 schema 或改写者。
    """

    if not isinstance(value, Mapping):
        raise ZeroQualifiedReasonError(
            f"{label}: zeroQualifiedReason 必须是对象，实得 "
            f"{type(value).__name__}"
        )
    issues = validate_strict(dict(value), reason_definition())
    if issues:
        raise ZeroQualifiedReasonError(
            f"{label}: zeroQualifiedReason 不满足共享值对象契约："
            + "；".join(issues[:8])
            + "。闭集只在 quwoquan_data/schema/_common/"
            "zero_qualified_reason.schema.json 声明，"
            f"code 闭集为 {list(reason_codes())}，"
            f"observedStage 闭集为 {list(observed_stages())}，"
            f"operatorAction 闭集为 {list(operator_actions())}"
        )
    basis = value.get("nonResumableBasis") or {}
    return ZeroQualifiedReason(
        code=str(value["code"]),
        observed_stage=str(value["observedStage"]),
        determined_at=str(value["determinedAt"]),
        operator_action=str(value["operatorAction"]),
        resumable_refs=tuple(str(ref) for ref in value.get("resumableRefs") or ()),
        admission_exclusion_refs=tuple(
            (str(row["entityRef"]), str(row["exclusionRef"]))
            for row in value.get("admissionExclusionRefs") or ()
        ),
        non_resumable_summary=str(basis.get("summary") or ""),
        non_resumable_evidence_ref=str(basis.get("evidenceRef") or ""),
        non_resumable_evidence_digest=str(basis.get("evidenceDigest") or ""),
    )


def non_resumable_reason_payload(
    *,
    code: str,
    observed_stage: str,
    operator_action: str,
    determined_at: str,
    summary: str,
    evidence_ref: str,
    evidence_digest: str,
    admission_exclusion_refs: Sequence[Mapping[str, str]] | None = None,
    label: str,
) -> dict[str, Any]:
    """构造一个不可续跑原因；构造即按共享值对象校验，构造不出的原因不落盘。"""

    payload: dict[str, Any] = {
        "code": code,
        "observedStage": observed_stage,
        "determinedAt": determined_at,
        "operatorAction": operator_action,
        "nonResumableBasis": {
            "summary": summary,
            "evidenceRef": evidence_ref,
            "evidenceDigest": evidence_digest,
        },
    }
    if admission_exclusion_refs is not None:
        payload["admissionExclusionRefs"] = [
            {
                "entityRef": str(row["entityRef"]),
                "exclusionRef": str(row["exclusionRef"]),
            }
            for row in admission_exclusion_refs
        ]
    parse_zero_qualified_reason(payload, label=label)
    return payload


def resumable_reason_payload(
    *,
    determined_at: str,
    resumable_refs: Sequence[str],
    label: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": RESUMABLE_INTERRUPTION,
        "observedStage": "delivery",
        "determinedAt": determined_at,
        "operatorAction": "resume",
        "resumableRefs": [str(ref) for ref in resumable_refs],
    }
    parse_zero_qualified_reason(payload, label=label)
    return payload


def evidence_digest(path: Path) -> str:
    """按证据文件真实字节算摘要；证据缺席时判否而不落空摘要。"""

    if not path.is_file():
        raise ZeroQualifiedReasonError(
            f"zeroQualifiedReason.nonResumableBasis 的证据文件不在场：{path}"
        )
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def publish_admission_over_budget(
    publish_discards: Sequence[Mapping[str, Any]],
) -> bool:
    """全批对象是否都被单对象存储预算拦下。

    这是「引用对象级排除码」而不是复制它们：判定只读媒体侧已写下的 issue code，
    批次级闭集里不出现任何对象级码。有任一对象因其它码被拦下时返回 False，由调用方
    按其观测到的事实另选原因，而不是让本原因兜住全部 publish 失败。
    """

    if not publish_discards:
        return False
    return all(
        {str(issue) for issue in (row.get("issues") or ())}
        <= PUBLISH_STORAGE_BUDGET_OBJECT_ISSUE_CODES
        and bool(row.get("issues"))
        for row in publish_discards
    )


__all__ = [
    "ALL_CANDIDATE_ENTITIES_SELECTOR_EXCLUDED",
    "ALL_OBJECTS_OVER_PUBLISH_STORAGE_BUDGET",
    "ALL_OBJECTS_QUALITY_REJECTED",
    "BATCH_DEADLINE_EXHAUSTED",
    "PUBLISH_STORAGE_BUDGET_OBJECT_ISSUE_CODES",
    "RESUMABLE_INTERRUPTION",
    "SOURCE_ACCESS_DENIED_OR_UNREACHABLE",
    "SOURCE_POOL_EMPTY",
    "ZeroQualifiedReason",
    "ZeroQualifiedReasonError",
    "evidence_digest",
    "non_resumable_reason_payload",
    "observed_stages",
    "operator_actions",
    "parse_zero_qualified_reason",
    "publish_admission_over_budget",
    "reason_codes",
    "reason_definition",
    "resumable_reason_payload",
]
