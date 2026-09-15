# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md#gwt-002
"""退役术语零容忍门的行为合约。

258 处存量清零后,这道门的价值在于「不回流」:任何新的 legacy/compat 运行时
标识直接 BLOCK,且不存在可以扩大的豁免名单——历史上这类债正是靠豁免名单
悄悄增长起来的。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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


@pytest.fixture
def runtime_tree(tmp_path: Path) -> Path:
    """只复制扫描器及路径依赖，生产实现保持 exact bytes。"""
    for source in (GATE, ROOT / "quwoquan_app/scripts/_common/paths.py"):
        target = tmp_path / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    runtime = tmp_path / "quwoquan_ops/cli"
    runtime.mkdir(parents=True)
    (runtime / "value.py").write_text("legacyAvailable = True\n", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("entry", ["scanner", "l0", "readiness"])
def test_real_retired_terms_failure_propagates(runtime_tree: Path, entry: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t2
    from quwoquan_ops.ci.local_readiness_planner import STATIC_COMMANDS

    command = STATIC_COMMANDS["retired_terms_zero"][0]
    if entry == "l0":
        source = (ROOT / "quwoquan_ops/gate/commit_gate.sh").read_text()
        function = source.split("run_static_check() {", 1)[1].split("\nexport -f", 1)[0]
        command = ["bash", "-c", "set -e\nrun_static_check() {" + function + "\nrun_static_check retired_terms_zero\nprintf unexpected-success"]
    elif entry == "readiness":
        sys.path.insert(0, str(ROOT / "quwoquan_ops/cli"))
        from lib.local_readiness.core import _run_check

        result = _run_check(
            {"id": "static:retired_terms_zero", "command": command, "cwd": ".", "timeout_seconds": 30},
            runtime_tree / ".qwq_output/check.log",
            repo_root=runtime_tree,
        )
        assert result["status"] == "FAIL", result
        assert result["exit_code"] == 1
        assert "value.py:1:legacyAvailable" in Path(result["log"]).read_text()
        return
    completed = subprocess.run(command, cwd=runtime_tree, capture_output=True, text=True, timeout=30)
    assert completed.returncode != 0
    assert "value.py:1:legacyAvailable" in completed.stdout
    assert "unexpected-success" not in completed.stdout


def test_scanner_accepts_current_names_comments_and_test_exclusion(runtime_tree: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t2
    runtime = runtime_tree / "quwoquan_ops/cli"
    (runtime / "value.py").write_text("# legacyAvailable is retired\navailability = True\n", encoding="utf-8")
    (runtime / "test_value.py").write_text("legacyFixture = True\n", encoding="utf-8")
    completed = subprocess.run([sys.executable, "-B", str(runtime_tree / GATE.relative_to(ROOT))], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("scope,phase", [("all", "all"), ("app", "all"), ("service", "all"), ("service", "packaging"), ("data", "all"), ("portal", "all"), ("ops-portal", "all"), ("patrol", "all")])
def test_gate_prefix_fails_before_heavy_commands(runtime_tree: Path, scope: str, phase: str) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/local-continuous-integration/spec.md#gwt-006.t4
    source = ROOT / "quwoquan_ops/gate/gate_repo.sh"
    target = runtime_tree / source.relative_to(ROOT)
    target.parent.mkdir(parents=True)
    shutil.copyfile(source, target)
    text = source.read_text()
    assert text.count("verify_retired_terms_zero.py") == 1
    assert text.index("verify_retired_terms_zero.py") < text.index("run_vertical_architecture_ratchet()")
    assert "verify_retired_terms_zero.py" not in text.split("run_app()", 1)[1]
    completed = subprocess.run(
        ["bash", str(target), "--scope", scope], cwd=runtime_tree,
        env={**os.environ, "GATE_SERVICE_PHASE": phase, "GATE_DATA_PHASE": "all"},
        capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode != 0
    assert "value.py:1:legacyAvailable" in completed.stdout, completed.stdout + completed.stderr
    assert "vertical architecture static ratchet" not in completed.stdout


def test_gate_has_no_allowlist_escape() -> None:
    """禁止通过扩大豁免名单达成归零(OPEN-002 收口时的硬约束)。"""
    source = GATE.read_text(encoding="utf-8")
    for escape in ("ALLOWLIST", "allowlist_path", "exempt_paths", "baseline_path"):
        assert escape not in source, f"retired-terms gate must not grow {escape}"
