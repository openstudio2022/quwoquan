#!/usr/bin/env python3
"""校验 accepted ContractGraph 与 generated operation contract 鉴权一致。"""
from __future__ import annotations


import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

import json
import re
import sys
from pathlib import Path

REPO_ROOT = _PATHS.REPO_ROOT
CONTRACT_LOCK = (
    REPO_ROOT
    / "quwoquan_app"
    / "tool"
    / "cloud_codegen"
    / "contract_graph.lock.json"
)
OPERATION_CONTRACTS_DART = (
    REPO_ROOT
    / "quwoquan_app"
    / "packages"
    / "quwoquan_cloud_contracts"
    / "lib"
    / "src"
    / "generated"
    / "operation_contracts.g.dart"
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


def parse_generated_operations() -> dict[str, str]:
    if not OPERATION_CONTRACTS_DART.exists():
        print(
            "FAIL: 未找到 generated operation contract "
            f"{OPERATION_CONTRACTS_DART}，请先运行 make codegen-app"
        )
        sys.exit(1)
    text = OPERATION_CONTRACTS_DART.read_text(encoding="utf-8")
    blocks = re.findall(
        r'^  "([A-Za-z0-9_.]+)": CloudOperationContract\(\n'
        r"([\s\S]*?)^  \),$",
        text,
        flags=re.MULTILINE,
    )
    result: dict[str, str] = {}
    for canonical_id, block in blocks:
        mode_match = re.search(
            r'^    authMode: "(public|optional|required)",$',
            block,
            flags=re.MULTILINE,
        )
        if mode_match is None:
            raise ValueError(
                f"generated operation {canonical_id} 缺少合法 authMode"
            )
        if canonical_id in result:
            raise ValueError(
                f"generated operation contract 重复: {canonical_id}"
            )
        result[canonical_id] = mode_match.group(1)
    return result


def main() -> int:
    errors: list[str] = []
    op_to_mode = collect_operations()

    for op, mode in op_to_mode.items():
        if mode not in VALID_MODES:
            errors.append(f"operation {op} 的 auth_mode 非法: {mode}")

    generated = parse_generated_operations()
    if generated != op_to_mode:
        errors.append(
            "generated operation contracts 与 accepted ContractGraph "
            "canonical operations 漂移"
        )

    if errors:
        print("FAIL: API 鉴权契约校验未通过：")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        f"OK: canonical operation 鉴权契约一致（operations={len(op_to_mode)}, "
        f"required={sum(1 for m in op_to_mode.values() if m == 'required')}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
