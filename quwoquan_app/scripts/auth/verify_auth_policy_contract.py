#!/usr/bin/env python3
"""校验 accepted ContractGraph canonical operation 鉴权快照。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_LOCK = (
    REPO_ROOT
    / "quwoquan_app"
    / "tool"
    / "cloud_codegen"
    / "contract_graph.lock.json"
)
POLICY_DART = (
    REPO_ROOT
    / "quwoquan_app"
    / "lib"
    / "cloud"
    / "runtime"
    / "generated"
    / "auth"
    / "auth_policy.g.dart"
)

VALID_MODES = {"public", "optional", "required"}

def collect_operations() -> dict[str, str]:
    lock = json.loads(CONTRACT_LOCK.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for operation in lock.get("appExposedOperations", []):
        canonical_id = str(operation.get("canonicalOperationId", "")).strip()
        mode = str(operation.get("authMode", "")).strip()
        if not canonical_id or canonical_id in result:
            raise ValueError(
                f"canonical operation 缺失或重复: {canonical_id!r}"
            )
        result[canonical_id] = mode
    return result


def parse_generated_policy() -> dict[str, str]:
    if not POLICY_DART.exists():
        print(f"FAIL: 未找到生成的鉴权快照 {POLICY_DART}，请先运行 make codegen-app")
        sys.exit(1)
    text = POLICY_DART.read_text(encoding="utf-8")
    pairs = re.findall(
        r"'([A-Za-z0-9_.]+)':\s*'(public|optional|required)'",
        text,
    )
    return {op: mode for op, mode in pairs}


def main() -> int:
    errors: list[str] = []
    op_to_mode = collect_operations()

    for op, mode in op_to_mode.items():
        if mode not in VALID_MODES:
            errors.append(f"operation {op} 的 auth_mode 非法: {mode}")

    generated = parse_generated_policy()
    if generated != op_to_mode:
        errors.append("生成快照与 accepted ContractGraph canonical operations 漂移")

    if errors:
        print("FAIL: API 鉴权契约校验未通过：")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        f"OK: canonical 鉴权契约一致（operations={len(op_to_mode)}, "
        f"required={sum(1 for m in op_to_mode.values() if m == 'required')}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
