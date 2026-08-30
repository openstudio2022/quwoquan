"""唯一「可发布」谓词：环境 release readiness 收据的单轨判定。

「可发布」在数据工程内只有本模块一个定义点。其他层的 readiness 是不同谓词，
不得与本谓词混用措辞：

- 对象池准入（`content_pool_record.is_pool_record_admitted`）：进 release 候选；
- 素材可发布（`core.media_normalization.publishable_media_issue`）：权利与像素准入；
- execution 准出（`verify_execution_readiness.execution_readiness_outcome`）：工作包能否 release；
- Ops 能力探针（`content.release.environment.readiness.ShipReadinessPhase`）：含 `import`
  一值，是 stackctl 适配层，不是本收据谓词；
- Ops CI 身份校验（`quwoquan_ops/ci/generate_release_bound_environment_identity.py`）：
  跨仓以 wire schema 为锚验证收据身份（schema/来源/checksum/passed 一体），
  是已登记消费方，不重复定义 phase 闭集或对齐规则。

凡判定「这份环境 readiness 收据是否表示可发布」，一律 import 本模块；
禁止再写 phase 闭集、phase↔lifecycle 对齐或 passed 判定的第二份实现。
wire 契约真相源是 `schema/release/environment_release_readiness.schema.json`，
本模块判定规则与该 schema 的 allOf 条件一一对应，由 local_contract 测试锁定。

CLI 入口（唯一）：
    python3 quwoquan_data/scripts/cli.py verify release-publishability --receipt <path>
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

READINESS_PHASES: frozenset[str] = frozenset({"research", "consumer", "commercial"})

# consumer 收据介于两态之间，lifecycle 跟随 release header，不强制对齐。
_LIFECYCLE_BOUND_PHASES: dict[str, str] = {
    "research": "research",
    "commercial": "commercial",
}

_RESEARCH_REQUIRED_FIELDS: tuple[str, ...] = (
    "internalSubjectHash",
    "researchIsolationVerificationRef",
    "researchIsolationVerificationDigest",
)


@dataclass(frozen=True)
class ReleasePublishabilityVerdict:
    """单轨可发布裁定：issues 为空即 publishable。"""

    publishable: bool
    phase: str
    issues: tuple[str, ...]


def readiness_phase_issue(phase: str) -> str | None:
    """phase 不在闭集时返回问题描述；合法返回 None。"""
    if phase in READINESS_PHASES:
        return None
    allowed = ", ".join(sorted(READINESS_PHASES))
    return f"readinessPhase must be one of {allowed}; got {phase!r}"


def phase_lifecycle_alignment_issue(
    phase: str,
    release_class: str,
    product_lifecycle_state: str,
) -> str | None:
    """research/commercial 收据必须与 immutable release lifecycle 同值。"""
    expected = _LIFECYCLE_BOUND_PHASES.get(phase)
    if expected is None:
        return None
    if release_class == expected and product_lifecycle_state == expected:
        return None
    return (
        f"readinessPhase={phase} requires releaseClass=productLifecycleState="
        f"{expected}; got releaseClass={release_class!r} "
        f"productLifecycleState={product_lifecycle_state!r}"
    )


def evaluate_release_readiness_receipt(
    receipt: Mapping[str, Any],
) -> ReleasePublishabilityVerdict:
    """判定一份环境 readiness 收据是否表示「可发布」。

    只裁定收据自含的可发布语义（phase 闭集、lifecycle 对齐、research 隔离
    证据在场、passed）；身份精确匹配（releaseId、digest、环境序）与深度完整性
    （counts、closure、checksum）由各调用方按自身职责另行校验。
    """
    phase = str(receipt.get("readinessPhase") or "")
    issues: list[str] = []
    phase_issue = readiness_phase_issue(phase)
    if phase_issue is not None:
        issues.append(phase_issue)
    else:
        alignment_issue = phase_lifecycle_alignment_issue(
            phase,
            str(receipt.get("releaseClass") or ""),
            str(receipt.get("productLifecycleState") or ""),
        )
        if alignment_issue is not None:
            issues.append(alignment_issue)
        if phase == "research":
            for field in _RESEARCH_REQUIRED_FIELDS:
                if not str(receipt.get(field) or ""):
                    issues.append(
                        f"research readiness requires non-empty {field}"
                    )
    if receipt.get("passed") is not True:
        issues.append("readiness receipt must carry passed: true")
    return ReleasePublishabilityVerdict(
        publishable=not issues,
        phase=phase,
        issues=tuple(issues),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="唯一「可发布」谓词：判定一份环境 readiness 收据是否可发布"
    )
    parser.add_argument("--receipt", required=True, help="release-readiness.json 路径")
    args = parser.parse_args(argv)

    receipt_path = Path(args.receipt)
    try:
        value = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[release_publishability] FAIL: unreadable receipt {receipt_path}: {exc}")
        return 1
    if not isinstance(value, Mapping):
        print(f"[release_publishability] FAIL: receipt must be an object: {receipt_path}")
        return 1

    from core.schema import assert_valid

    try:
        assert_valid(
            dict(value),
            "release",
            "environment_release_readiness",
            label="environment release readiness",
        )
    except (FileNotFoundError, TypeError, ValueError) as exc:
        print(f"[release_publishability] FAIL: schema violation: {exc}")
        return 1

    verdict = evaluate_release_readiness_receipt(value)
    if not verdict.publishable:
        print(f"[release_publishability] FAIL: phase={verdict.phase or '<missing>'}")
        for issue in verdict.issues:
            print(f"  - {issue}")
        return 1
    print(
        f"[release_publishability] OK: phase={verdict.phase} "
        f"environment={value.get('environment')} releaseId={value.get('releaseId')}"
    )
    return 0


__all__ = [
    "READINESS_PHASES",
    "ReleasePublishabilityVerdict",
    "evaluate_release_readiness_receipt",
    "main",
    "phase_lifecycle_alignment_issue",
    "readiness_phase_issue",
]
