# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
"""退役术语零容忍门的行为合约。

258 处存量清零后,这道门的价值在于「不回流」:任何新的 legacy/compat 运行时
标识直接 BLOCK,且不存在可以扩大的豁免名单——历史上这类债正是靠豁免名单
悄悄增长起来的。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_app/scripts/runtime/architecture/verify_retired_terms_zero.py"


def test_repository_has_zero_retired_runtime_identifiers() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", str(GATE)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "OK" in completed.stdout


def test_gate_has_no_allowlist_escape() -> None:
    """禁止通过扩大豁免名单达成归零(OPEN-002 收口时的硬约束)。"""
    source = GATE.read_text(encoding="utf-8")
    for escape in ("ALLOWLIST", "allowlist_path", "exempt_paths", "baseline_path"):
        assert escape not in source, f"retired-terms gate must not grow {escape}"
