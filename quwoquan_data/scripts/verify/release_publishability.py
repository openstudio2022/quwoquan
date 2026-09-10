"""环境 release readiness 的唯一可发布谓词，不带类别或命名相位。

收据自含语义要求完整 guest 证据与 passed；身份、摘要、探针与闭包由
严格 schema 和调用边界校验，不以删去类别而减少 required 证据。
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_GUEST_REQUIRED_FIELDS = ("guestActorHash", "guestLogin")


@dataclass(frozen=True)
class ReleasePublishabilityVerdict:
    publishable: bool
    issues: tuple[str, ...]


def evaluate_release_readiness_receipt(
    receipt: Mapping[str, Any],
) -> ReleasePublishabilityVerdict:
    """裁定自含语义；不替代完整身份、checksum 和 required probes 校验。"""
    from core.schema import assert_valid

    issues: list[str] = []
    try:
        assert_valid(dict(receipt), "release", "environment_release_readiness", label="environment release readiness")
    except (FileNotFoundError, TypeError, ValueError) as exc:
        issues.append(str(exc))
    for field in _GUEST_REQUIRED_FIELDS:
        if not receipt.get(field):
            issues.append(f"readiness requires non-empty {field}")
    if receipt.get("passed") is not True:
        issues.append("readiness receipt must carry passed: true")
    return ReleasePublishabilityVerdict(publishable=not issues, issues=tuple(issues))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="判定环境 release readiness 收据是否可发布")
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
    verdict = evaluate_release_readiness_receipt(value)
    if not verdict.publishable:
        print("[release_publishability] FAIL")
        for issue in verdict.issues:
            print(f"  - {issue}")
        return 1
    print(f"[release_publishability] OK: environment={value.get('environment')} releaseId={value.get('releaseId')}")
    return 0


__all__ = ["ReleasePublishabilityVerdict", "evaluate_release_readiness_receipt", "main"]
