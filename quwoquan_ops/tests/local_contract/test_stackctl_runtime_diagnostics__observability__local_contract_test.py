from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.observability import append_log_line


def test_stackctl_runtime_log_inspection_summarizes_without_messages(
    tmp_path: Path,
) -> None:
    root = (
        tmp_path
        / ".qwq_output"
        / "env"
        / "gamma"
        / "observability"
        / "run-1"
        / "logs"
        / "service"
    )
    append_log_line(
        root / "runtime.log",
        {
            "severity": "ERROR",
            "event": "process.exit",
            "result": "failed",
            "message": "authorization=secret-token must never reach inspection",
        },
    )

    report = stackctl._runtime_log_evidence_report(root)

    assert report["availability"] == "available"
    assert report["recordCount"] == 1
    assert report["severityCounts"] == {"ERROR": 1}
    assert report["topSignals"] == [{"signal": "ops.runtime.process", "count": 1}]
    assert "secret-token" not in str(report)
