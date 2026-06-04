"""Phase 0 复核口径：清债扫描限定到代码/任务真相源，避免验收文档自命中。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_migrate_history_removed_from_code_and_task_truth_sources():
    needle = "migrate" + "_history"
    targets = [ROOT / "quwoquan_data" / "scripts", ROOT / "quwoquan_data" / "tasks"]
    offenders: list[str] = []
    for root in targets:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if needle in text:
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_task_help_has_no_migrate_history_subcommand():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "quwoquan_data" / "scripts" / "cli.py"), "task", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "migrate-history" not in proc.stdout


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"phase0 reverify tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
