from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.alpha.content_release_runtime import (
    _materialize_observability_run,
)
from quwoquan_ops.cli.alpha.content_release_runtime import (
    _paths as alpha_content_release_paths,
)
from quwoquan_ops.cli.lib.common import artifact_run_dir
from quwoquan_ops.cli.lib.local_run import resolve_local_run
from quwoquan_ops.cli.lib.observability import (
    append_log_line,
    canonical_log_record,
    parse_log_records,
    run_dir,
    validate_log_payload,
    write_run_manifest,
)
from quwoquan_ops.cli.lib.runtime_log_process import run_logged_process
from quwoquan_ops.gate.verify_observability_envelope import envelope_issues
from quwoquan_ops.gate.verify_observability_layout import (
    layout_issues,
    materialize_repo_gate_observability_run,
)


def test_canonical_deploy_log_accepts_canonical_writer_fields(tmp_path: Path) -> None:
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
            "severity": "INFO",
            "step": "package",
            "result": "ok",
            "message": "package ready, with comma",
        },
    )

    assert layout_issues(root) == []
    assert envelope_issues(root) == []


def test_repo_gate_materializes_real_canonical_observability_before_validation(
    tmp_path: Path,
) -> None:
    root = tmp_path / ".qwq_output"

    run = materialize_repo_gate_observability_run(root)

    assert run.is_dir()
    assert layout_issues(root) == []
    assert envelope_issues(root) == []


def test_version_and_release_identifiers_are_rejected() -> None:
    record = canonical_log_record(
        "event",
        {
            "occurredAt": "2026-07-08T10:00:00Z",
            "severity": "INFO",
            "message": "too chatty",
            "event": "open",
            "result": "ok",
        },
        resource={"sourceType": "ops", "service": "stackctl"},
    )
    record["schema" + "Version"] = "1"
    record["protocolVersion"] = "1"
    record["releaseVersion"] = "1"
    record["releaseId"] = "release-1"
    issues = validate_log_payload("event", record)

    assert any("forbidden field" in issue for issue in issues)


def test_attrs_are_string_only_sanitized_and_secret_keys_dropped() -> None:
    record = canonical_log_record(
        "exception",
        {
            "occurredAt": "2026-07-08T10:00:00Z",
            "severity": "ERROR",
            "message": "failed",
            "errorCode": "RuntimeError",
            "attributes": {
                "apiToken": "should-not-appear",
                "protocolVersion": "must-not-appear",
                "releaseVersion": "must-not-appear",
                "releaseId": "must-not-appear",
                "inputKv": {"nested": "retained as text"},
            },
        },
        resource={"sourceType": "ops", "service": "stackctl"},
    )
    issues = validate_log_payload("exception", record)

    assert issues == []
    assert record["attributes"] == {
        "inputKv": '{"nested":"retained as text"}'
    }


def test_canonical_log_rejects_signal_kind_mismatch_and_normalizes_status() -> None:
    record = canonical_log_record(
        "access",
        {
            "schema": "observability.slim",
            "logKind": "access",
            "signal": "service.access.http",
            "method": "GET",
            "route": "/content/content/posts/{postId}",
            "status": 200,
            "durationMs": 12,
        },
        resource={"sourceType": "service", "service": "content-service"},
    )

    assert record["status"] == "200"
    assert validate_log_payload("access", record) == []
    record["signal"] = "service.runtime.process"
    assert any("does not match" in issue for issue in validate_log_payload("access", record))


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


def test_json_log_parser_preserves_message_commas_and_stack_lines() -> None:
    record = canonical_log_record(
        "exception",
        {
            "occurredAt": "2026-07-08T10:00:00Z",
            "severity": "ERROR",
            "errorCode": "APP.SYSTEM.failed",
            "message": "message, with comma\nat frame one\nat frame two",
        },
        resource={"sourceType": "ops", "service": "stackctl"},
    )
    records, issues = parse_log_records(
        "exception",
        [json.dumps(record)],
    )

    assert issues == []
    assert records[0]["message"] == "message, with comma\nat frame one\nat frame two"


def test_local_run_uses_immutable_id_and_persists_manifest(tmp_path: Path) -> None:
    output_root = tmp_path / ".qwq_output"

    started = resolve_local_run(
        env="alpha",
        target="alpha-local",
        action="up",
        root=output_root,
    )
    resumed = resolve_local_run(
        env="alpha",
        target="alpha-local",
        action="status",
        root=output_root,
    )

    assert started.run_id != "current"
    assert resumed == started
    manifest = json.loads(
        (started.observability_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == "observability.slim"
    # 禁止契约信封字段：manifest 不得含已退休标识。
    forbidden_envelope_fields = {
        "schema" + "Version",
        "event" + "Version",
        "releaseId",
        "dataReleaseId",
    }
    assert set(manifest).isdisjoint(forbidden_envelope_fields)
    assert manifest["runId"] == started.run_id
    assert manifest["target"] == "alpha-local"


def test_repeated_local_up_runs_cannot_overwrite_prior_evidence(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / ".qwq_output"

    first = resolve_local_run(
        env="alpha",
        target="alpha-local",
        action="up",
        root=output_root,
    )
    second = resolve_local_run(
        env="alpha",
        target="alpha-local",
        action="up",
        root=output_root,
    )

    assert first.run_id != second.run_id
    assert first.run_root != second.run_root
    assert first.observability_root != second.observability_root
    assert (first.observability_root / "manifest.json").is_file()
    assert (second.observability_root / "manifest.json").is_file()


def test_alpha_content_release_materializes_manifest_before_runtime_logs(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_root = tmp_path / ".qwq_output"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output_root))
    monkeypatch.delenv("QWQ_RUN_ROOT", raising=False)
    monkeypatch.delenv("QWQ_OBSERVABILITY_RUN_ROOT", raising=False)
    monkeypatch.setattr(
        "quwoquan_ops.cli.alpha.content_release_runtime."
        "legal_static_deployment_package_dir",
        lambda *_args, **_kwargs: tmp_path / "deploy" / "legal-static",
    )

    paths = alpha_content_release_paths(new_run=True)
    _materialize_observability_run(paths)

    manifest = json.loads(
        (paths.observability_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert paths.observability_root.name == paths.run_root.name
    assert paths.observability_root.name != "alpha-content-release-local"
    assert manifest["env"] == "alpha"
    assert manifest["target"] == "alpha-local"
    assert manifest["runId"] == paths.observability_root.name
    assert not paths.logs_root.exists()


def test_observability_manifest_never_accepts_release_identifiers(
    tmp_path: Path,
) -> None:
    """禁止契约信封：manifest 不得接受退休 release/version 字段。"""
    run = tmp_path / ".qwq_output" / "env" / "repo" / "observability" / "run-1"

    write_run_manifest(
        run,
        env_name="repo",
        run_id="run-1",
        command="verify",
        target="repo",
        report_dir=tmp_path / ".qwq_output" / "env" / "repo" / "runs" / "run-1",
    )

    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    forbidden_envelope_fields = {
        "schema" + "Version",
        "event" + "Version",
        "releaseId",
        "dataReleaseId",
    }
    assert set(manifest).isdisjoint(forbidden_envelope_fields)


def test_data_runtime_logs_share_the_repo_observability_root() -> None:
    assert run_dir("repo", "run-1").parts[-4:] == (
        "env",
        "repo",
        "observability",
        "run-1",
    )
    try:
        run_dir("data", "run-1")
    except ValueError:
        pass
    else:
        raise AssertionError("data must not create a separate observability root")


def test_baseline_report_uses_the_repo_run_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(tmp_path / ".qwq_output"))

    report_dir = artifact_run_dir("repo", "verify", target="repo")

    assert report_dir.parent.parts[-3:] == ("env", "repo", "runs")
    assert report_dir.name.endswith("-verify-repo")


def test_runtime_stdout_adapter_emits_valid_runtime_records(tmp_path: Path) -> None:
    root = tmp_path / ".qwq_output"
    run = root / "env" / "alpha" / "observability" / "run-1"
    write_run_manifest(
        run,
        env_name="alpha",
        run_id="run-1",
        command="local up",
        target="alpha-local",
        report_dir=root / "env" / "alpha" / "runs" / "run-1",
    )
    log_path = run / "logs" / "service" / "api-edge" / "local" / "runtime.log"

    result = run_logged_process(
        [sys.executable, "-c", "print('ready, with comma')"],
        log_path=log_path,
        event="api-edge",
    )

    assert result == 0
    assert layout_issues(root) == []
    assert envelope_issues(root) == []
    records = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert all(
        record["resource"] == {
            "sourceType": "service",
            "service": "api-edge",
            "environment": "alpha",
        }
        for record in records
    )


def test_runtime_stdout_adapter_never_copies_raw_process_output_into_runtime_logs(
    tmp_path: Path,
) -> None:
    log_path = (
        tmp_path
        / ".qwq_output"
        / "env"
        / "gamma"
        / "observability"
        / "run-1"
        / "logs"
        / "service"
        / "api-edge"
        / "local"
        / "runtime.log"
    )

    result = run_logged_process(
        [sys.executable, "-c", "print('WARN authorization=secret-token')"],
        log_path=log_path,
        event="api-edge",
    )

    assert result == 0
    rendered = log_path.read_text(encoding="utf-8")
    assert "secret-token" not in rendered
    assert "managed process emitted a non-info line" in rendered


def test_runtime_stdout_adapter_writes_explicit_diagnostic_output_outside_observability(
    tmp_path: Path,
) -> None:
    log_path = (
        tmp_path
        / ".qwq_output"
        / "env"
        / "beta"
        / "observability"
        / "run-1"
        / "logs"
        / "service"
        / "app-beta"
        / "local"
        / "runtime.log"
    )
    diagnostic_path = (
        tmp_path
        / ".qwq_output"
        / "env"
        / "beta"
        / "local"
        / "beta-local"
        / "process"
        / "stdout"
        / "app-beta.log"
    )

    result = run_logged_process(
        [sys.executable, "-c", "print('GATE_BLOCK authorization=secret-token')"],
        log_path=log_path,
        event="app-beta",
        diagnostic_log_path=diagnostic_path,
    )

    assert result == 0
    assert "secret-token" not in log_path.read_text(encoding="utf-8")
    assert diagnostic_path.read_text(encoding="utf-8") == "GATE_BLOCK authorization=secret-token\n"
    assert diagnostic_path.stat().st_mode & 0o777 == 0o600


def test_runtime_stdout_adapter_preserves_canonical_service_records(
    tmp_path: Path,
) -> None:
    log_path = (
        tmp_path
        / ".qwq_output"
        / "env"
        / "gamma"
        / "observability"
        / "run-1"
        / "logs"
        / "service"
        / "api-edge"
        / "local"
        / "runtime.log"
    )
    service_record = {
        "schema": "observability.slim",
        "recordId": "srv-1",
        "occurredAt": "2026-07-19T00:00:00Z",
        "observedAt": "2026-07-19T00:00:01Z",
        "logKind": "exception",
        "severity": "ERROR",
        "signal": "service.exception.runtime",
        "message": "request processing failed authorization=secret-token",
        "resource": {
            "sourceType": "service",
            "service": "api-edge",
            "environment": "gamma",
            "service.version": "2026.07.19",
        },
        "errorCode": "SERVICE.RUNTIME.log_encoding_failed",
    }

    result = run_logged_process(
        [sys.executable, "-c", f"print({json.dumps(service_record)!r})"],
        log_path=log_path,
        event="api-edge",
    )

    assert result == 0
    records = [
        json.loads(line)
        for line in log_path.with_name("exception.log").read_text(encoding="utf-8").splitlines()
    ]
    assert records[0] | {"message": service_record["message"]} == service_record
    assert records[0]["message"] == "request processing failed authorization=***"
    assert "secret-token" not in json.dumps(records)
    assert "managed process emitted a non-info line" not in log_path.read_text(
        encoding="utf-8"
    )
