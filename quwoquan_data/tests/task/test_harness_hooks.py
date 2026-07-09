"""Harness sensor 钩子 contract tests（subagentStart / beforeShellExecution / afterFileEdit）。

校验三个 hook 脚本：合法 JSON 输入/输出、observe-only 始终 allow、命中场景给出提示。
可直接运行：python3 quwoquan_data/tests/task/test_harness_hooks.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "quwoquan_ops").is_dir())
HOOKS = REPO_ROOT / "quwoquan_ops" / "hooks"


def _run(script: str, payload: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout or "{}")


def test_subagent_start_allows_and_injects_isolation():
    out = _run("subagent_start_guard.py", {"subagentType": "generalPurpose"})
    assert out["permission"] == "allow"
    assert "single-ref" in out["user_message"]


def test_shell_guard_allows_cli_first():
    out = _run("shell_cli_first_guard.py", {"command": "qwq-data verify --scope current"})
    assert out["permission"] == "allow"
    assert "agent_message" not in out


def test_shell_guard_flags_direct_run_but_does_not_block():
    out = _run("shell_cli_first_guard.py", {"command": "python3 quwoquan_data/scripts/produce/handler.py"})
    assert out["permission"] == "allow"  # observe-only：不阻断
    assert "CLI-first" in out["agent_message"]


def test_draft_quickcheck_flags_contact_and_heading():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "article.md"
        f.write_text("## 节点顺序\n\n咨询电话：0836-6966022。", encoding="utf-8")
        out = _run("draft_quickcheck.py", {"file_path": str(f)})
        assert "additional_context" in out
        assert "contactInfo" in out["additional_context"]
        assert "mechanicalHeading" in out["additional_context"]


def test_draft_quickcheck_ignores_non_draft():
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "notes.txt"
        f.write_text("任意内容", encoding="utf-8")
        assert _run("draft_quickcheck.py", {"file_path": str(f)}) == {}


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"harness hooks tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
