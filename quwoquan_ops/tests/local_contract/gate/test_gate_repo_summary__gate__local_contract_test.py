#!/usr/bin/env python3
"""gate_repo 结构化 summary 合约：pass/block 语义、失败命令留痕与 bash 接线锁。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EMITTER = ROOT / "quwoquan_ops/gate/emit_gate_repo_summary.py"
GATE_REPO_SH = ROOT / "quwoquan_ops/gate/gate_repo.sh"


def _run_emitter(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", str(EMITTER), "--repo-root", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _read_summary(repo_root: Path, scope: str) -> dict:
    path = repo_root / f".qwq_output/env/repo/runs/gate/gate-repo-{scope}.json"
    return json.loads(path.read_text(encoding="utf-8"))


class GateRepoSummaryContractTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001

    def test_zero_exit_writes_pass_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_emitter(Path(tmp), "--scope", "all", "--exit-code", "0")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = _read_summary(Path(tmp), "all")
            self.assertEqual(payload["gate"], "gate-repo-all")
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["findings"], [])

    def test_nonzero_exit_writes_block_with_failed_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_emitter(
                Path(tmp),
                "--scope",
                "service",
                "--exit-code",
                "1",
                "--failed-command",
                "python3 quwoquan_ops/gate/verify_service_architecture.py",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = _read_summary(Path(tmp), "service")
            self.assertEqual(payload["status"], "block")
            [item] = payload["findings"]
            self.assertIn("exit=1", item["message"])
            self.assertIn("verify_service_architecture.py", item["message"])
            self.assertIn("gate_repo.sh --scope service", item["fix"])

    def test_scopes_land_in_distinct_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _run_emitter(Path(tmp), "--scope", "all", "--exit-code", "0")
            _run_emitter(Path(tmp), "--scope", "data", "--exit-code", "2")
            self.assertEqual(_read_summary(Path(tmp), "all")["status"], "pass")
            self.assertEqual(_read_summary(Path(tmp), "data")["status"], "block")

    def test_gate_repo_sh_wires_exit_trap_to_emitter(self) -> None:
        """接线锁：gate_repo.sh 必须经 EXIT trap 调发射器，且 ERR trap 记录失败命令。"""
        text = GATE_REPO_SH.read_text(encoding="utf-8")
        self.assertIn("emit_gate_repo_summary.py", text)
        self.assertIn("trap emit_structured_summary EXIT", text)
        self.assertIn("trap '_gate_failed_command=$BASH_COMMAND' ERR", text)
        # 发射器失败不得改变门禁退出语义。
        self.assertIn('--failed-command "$_gate_failed_command" || true', text)


if __name__ == "__main__":
    unittest.main()
