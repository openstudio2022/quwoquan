from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.observability import (
    append_log_line,
    parse_log_records,
    validate_log_payload,
    write_run_manifest,
)
from quwoquan_ops.gate.verify_observability_envelope import envelope_issues
from quwoquan_ops.gate.verify_observability_layout import layout_issues


def test_compact_deploy_log_accepts_short_fields(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    run = root / "env" / "gamma" / "observability" / "run-1"
    write_run_manifest(
        run,
        env_name="gamma",
        run_id="run-1",
        command="package",
        target="gamma-local",
        report_dir=tmp_path / ".qwq_output" / "env" / "gamma" / "runs" / "run-1",
    )
    append_log_line(
        run / "logs" / "ci" / "stackctl" / "deploy.log",
        {
            "level": "INFO",
            "step": "package",
            "result": "ok",
            "msg": "package ready, with comma",
        },
    )

    assert layout_issues(root) == []
    assert envelope_issues(root) == []


def test_repeated_context_fields_are_rejected() -> None:
    issues = validate_log_payload(
        "event",
        {
            "ts": "2026-07-08T10:00:00Z",
            "level": "INFO",
            "msg": "too chatty",
            "event": "open",
            "result": "ok",
            "schema" + "Version": "1",
            "runId": "run-1",
        },
    )

    assert any("forbidden repeated field" in issue for issue in issues)


def test_attrs_are_size_limited_and_secret_keys_blocked() -> None:
    issues = validate_log_payload(
        "exception",
        {
            "ts": "2026-07-08T10:00:00Z",
            "level": "ERROR",
            "msg": "failed",
            "err": "RuntimeError",
            "attrs": {"apiToken": "should-not-appear"},
        },
    )

    assert any("secret-like" in issue for issue in issues)


def test_layout_rejects_unknown_log_kind(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    run = root / "env" / "gamma" / "observability" / "run-1"
    write_run_manifest(
        run,
        env_name="gamma",
        run_id="run-1",
        command="verify",
        target="gamma-local",
        report_dir=tmp_path / ".qwq_output" / "env" / "gamma" / "runs" / "run-1",
    )
    unknown = run / "logs" / "service" / "content-service" / "1" / "profile.log"
    unknown.parent.mkdir(parents=True)
    unknown.write_text(json.dumps({"ts": "t", "level": "INFO", "msg": "x"}) + "\n")

    assert any("unknown log kind" in issue for issue in layout_issues(root))


def test_layout_rejects_root_side_channel(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    (root / "observability" / "runs").mkdir(parents=True)

    assert any("old observability root" in issue for issue in layout_issues(root))


def test_delimited_log_parser_keeps_message_commas_and_stack_lines() -> None:
    records, issues = parse_log_records(
        "exception",
        [
            "2026-07-08T10:00:00Z,ERROR,APP.SYSTEM.failed,req-1,trace-1,message, with comma",
            "\tat frame one",
            "\tat frame two",
        ],
    )

    assert issues == []
    assert records[0]["msg"] == "message, with comma\nat frame one\nat frame two"
