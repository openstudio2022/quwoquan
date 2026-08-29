"""BehaviorFingerprint：UAT CaseResult 的 derived projection（DEC-004）。

对同一环境与服务端状态，各安装启动入口（launch provenance、install
channel、BuildMode、设备形态）的规范化行为指纹必须一致：配置完成态、
首个安全终态、canonical terminal、release identity、恢复动作、无 fatal
recovery。指纹刻意**排除**时序毫秒值、attemptId、设备身份与入口维度，
因此"改变入口、行为不变"可以被逐字节比较。

本模块只服务 UAT 证据层，不是业务 aggregate，也不回写 App。
"""

from __future__ import annotations

import json
from typing import Any

BEHAVIOR_FINGERPRINT_SCHEMA = "qwq.startup-behavior-fingerprint"

# 指纹显式排除的入口/身份/时序维度；出现在这里的键改变不得影响指纹。
EXCLUDED_ENTRY_DIMENSIONS = frozenset(
    {
        "launchProvenance",
        "deviceKind",
        "deviceId",
        "attemptId",
        "buildMode",
        "installChannel",
        "distributionClass",
    }
)


def derive_behavior_fingerprint(
    sample: dict[str, Any],
    *,
    release_id: str = "",
    release_digest: str = "",
) -> dict[str, Any]:
    """从单次启动 sample 派生规范化行为指纹。

    只投影行为语义位；缺席的键投影为显式 None（缺席也属于行为的一部分，
    两个入口一个报告、一个缺席即行为不一致）。
    """
    launcher_resolution = sample.get("launcherResolution")
    resolution_matches = (
        launcher_resolution.get("matchesExpectedGate")
        if isinstance(launcher_resolution, dict)
        else None
    )
    return {
        "schema": BEHAVIOR_FINGERPRINT_SCHEMA,
        "runtimeEnv": sample.get("runtimeEnv"),
        "runtimeTarget": sample.get("runtimeTarget"),
        "platform": sample.get("platform"),
        "configurationComplete": sample.get("runtimeConfigurationState")
        == "complete",
        "missingDefineKeys": sorted(
            str(key) for key in (sample.get("missingDefineKeys") or [])
        ),
        "canonicalTerminal": sample.get("canonicalTerminal"),
        "watchdogOutcome": sample.get("watchdogOutcome"),
        "failureCode": sample.get("failureCode"),
        "launcherResolvedToGate": resolution_matches,
        "releaseId": release_id,
        "releaseDigest": release_digest,
    }


def canonical_fingerprint_text(fingerprint: dict[str, Any]) -> str:
    return json.dumps(
        fingerprint, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def fingerprint_equivalence_issues(
    samples: list[dict[str, Any]],
    *,
    label: str,
    release_id: str = "",
    release_digest: str = "",
) -> list[str]:
    """断言同一证据文件内所有入口 sample 的行为指纹逐字节一致。

    平台差异是真实行为差异的一部分，只在同 platform 内比较；
    每个 platform 组内出现第二种指纹即违规。
    """
    issues: list[str] = []
    by_platform: dict[str, dict[str, str]] = {}
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            continue
        platform = str(sample.get("platform") or "")
        fingerprint = canonical_fingerprint_text(
            derive_behavior_fingerprint(
                sample,
                release_id=release_id,
                release_digest=release_digest,
            )
        )
        group = by_platform.setdefault(platform, {})
        entry = (
            f"run-{index + 1:02d}"
            f"(launchProvenance={sample.get('launchProvenance')},"
            f"deviceKind={sample.get('deviceKind')})"
        )
        if fingerprint not in group:
            group[fingerprint] = entry
            if len(group) > 1:
                issues.append(
                    f"{label}: behavior fingerprint diverged on {platform}: "
                    f"{entry} does not match {next(iter(group.values()))}"
                )
    return issues
