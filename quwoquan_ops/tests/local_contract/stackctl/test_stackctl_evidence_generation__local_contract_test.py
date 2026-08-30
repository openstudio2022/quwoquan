"""Evidence generation closure for package/up/health/verify and hosted read-only.

spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-003
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import hosted_read_only, up_domain
from quwoquan_ops.cli.lib import output_paths
from quwoquan_ops.cli.lib.evidence_generation import (
    build_evidence_generation_envelope,
    validate_evidence_generation_envelope,
)


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def test_generation_mismatch_is_rejected() -> None:
    envelope = build_evidence_generation_envelope(
        command="health",
        candidate_snapshot={"baselineId": _digest("1")},
        startup_receipt={"attemptId": "attempt-1"},
    )
    with pytest.raises(ValueError, match="candidate mismatch"):
        validate_evidence_generation_envelope(
            envelope, expected_candidate_digest=_digest("2")
        )
    with pytest.raises(ValueError, match="startup attempt mismatch"):
        validate_evidence_generation_envelope(
            envelope, expected_startup_attempt_id="attempt-2"
        )


def test_stale_upstream_report_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        report = Path(temporary) / "report.json"
        report.write_text('{"status":"ok"}\n', encoding="utf-8")
        envelope = build_evidence_generation_envelope(
            command="verify", upstream_report=report
        )
        validate_evidence_generation_envelope(envelope)
        report.write_text('{"status":"changed"}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="upstream report is stale"):
            validate_evidence_generation_envelope(envelope)


def test_typed_absence_never_uses_empty_evidence_values() -> None:
    envelope = build_evidence_generation_envelope(command="package")
    validate_evidence_generation_envelope(envelope)
    assert envelope["candidateDigest"]["status"] == "not_applicable"
    assert envelope["startupAttemptId"]["status"] == "not_executed"
    assert envelope["upstreamReport"]["status"] == "not_applicable"
    assert all("value" not in envelope[field] for field in (
        "candidateDigest", "startupAttemptId", "upstreamReport"
    ))


def test_skip_app_is_explicit_and_service_step_cannot_backfill_it() -> None:
    projection = up_domain._app_launch_projection(
        skip_app=True,
        steps=[
            {
                "name": "service-startup",
                "argv": ["docker", "compose", "up"],
                "exitCode": 0,
            }
        ],
    )
    assert projection == {
        "status": "not_executed",
        "reason": "--skip-app explicitly disabled App launch",
    }


def test_non_skip_without_attempt_is_not_executed() -> None:
    projection = up_domain._app_launch_projection(
        skip_app=False,
        steps=[{"name": "service-startup", "exitCode": 0}],
    )
    assert projection["status"] == "not_executed"


def test_actual_app_attempt_is_executed() -> None:
    projection = up_domain._app_launch_projection(
        skip_app=False,
        steps=[
            {
                "name": "app-launch",
                "argv": ["python3", "supervise_app_launch.py"],
                "exitCode": 0,
            }
        ],
    )
    assert projection == {"status": "executed", "attempts": 1, "passed": True}


def test_up_projection_persists_skip_app_and_candidate_envelope() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        output_root = root / "output"
        report_dir = output_root / "env" / "alpha" / "runs" / "up-report"
        report_dir.mkdir(parents=True)
        (report_dir / "report.json").write_text(
            json.dumps(
                {
                    "command": "up",
                    "status": "ok",
                    "steps": [{"name": "service-startup", "exitCode": 0}],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        candidate = {"baselineId": _digest("a")}
        with (
            mock.patch.dict(
                os.environ,
                {"QWQ_OUTPUT_ROOT": str(output_root)},
            ),
            mock.patch.object(
                stackctl,
                "active_deployment_candidate_snapshot",
                return_value=candidate,
            ),
            mock.patch.object(stackctl, "read_startup_attempt", return_value=None),
            mock.patch.object(
                stackctl,
                "startup_attempt_path",
                return_value=root / "missing-startup.json",
            ),
        ):
            result = up_domain._up_evidence_projection(
                argparse.Namespace(target="alpha-local", env="", skip_app=True),
                {
                    "exitCode": 0,
                    "summary": "up",
                    "details": [],
                    "reportDir": str(report_dir),
                },
            )
        persisted = json.loads(
            (report_dir / "report.json").read_text(encoding="utf-8")
        )
    assert result["appLaunch"]["status"] == "not_executed"
    assert persisted["appLaunch"]["status"] == "not_executed"
    assert persisted["startupReadback"]["status"] == "not_executed"
    assert persisted["runtimeLiveness"]["status"] == "not_applicable"
    assert persisted["evidenceEnvelope"]["candidateDigest"] == {
        "status": "executed",
        "value": _digest("a"),
    }


def test_selector_conflict_is_typed_without_root_write_or_stale_projection(
    tmp_path: Path,
) -> None:
    root_report = tmp_path / "report.json"
    original = b'{"owner":"human-confirmation-required"}\n'
    root_report.write_bytes(original)
    with (
        mock.patch.object(stackctl, "ROOT", tmp_path),
        mock.patch.object(
            stackctl,
            "active_deployment_candidate_snapshot",
        ) as candidate_readback,
        mock.patch.object(stackctl, "read_startup_attempt") as startup_readback,
    ):
        result = up_domain.command_up(
            argparse.Namespace(env="alpha", target="alpha-local")
        )

    assert result["exitCode"] == 2
    assert result["details"] == ["provide exactly one of --env or --target"]
    assert "reportDir" not in result
    assert "startupReadback" not in result
    assert "runtimeLiveness" not in result
    assert root_report.read_bytes() == original
    candidate_readback.assert_not_called()
    startup_readback.assert_not_called()


def test_missing_report_dir_is_pure_and_does_not_read_runtime_evidence(
    tmp_path: Path,
) -> None:
    payload = {
        "exitCode": 2,
        "summary": "stackctl up failed",
        "details": ["typed early failure"],
    }
    with (
        mock.patch.object(stackctl, "ROOT", tmp_path),
        mock.patch.object(
            stackctl,
            "active_deployment_candidate_snapshot",
        ) as candidate_readback,
        mock.patch.object(stackctl, "read_startup_attempt") as startup_readback,
    ):
        result = up_domain._up_evidence_projection(
            argparse.Namespace(target="alpha-local", env="", skip_app=True),
            dict(payload),
        )

    assert result == payload
    assert not (tmp_path / "report.json").exists()
    candidate_readback.assert_not_called()
    startup_readback.assert_not_called()


def test_up_report_dir_rejects_absolute_outside_and_parent_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output_root))
    outside = tmp_path / "outside-run"
    traversal = output_root / "env" / "alpha" / "runs" / ".." / "escaped"

    with pytest.raises(ValueError, match="canonical environment runs subtree"):
        stackctl.validate_up_report_dir(outside, env_name="alpha")
    with pytest.raises(ValueError, match="parent traversal"):
        stackctl.validate_up_report_dir(str(traversal), env_name="alpha")
    assert not outside.exists()


def test_up_report_dir_rejects_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    runs_root = output_root / "env" / "alpha" / "runs"
    outside = tmp_path / "outside"
    runs_root.mkdir(parents=True)
    outside.mkdir()
    (runs_root / "linked").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output_root))

    with pytest.raises(ValueError, match="canonical environment runs subtree"):
        stackctl.validate_up_report_dir(
            runs_root / "linked" / "attempt",
            env_name="alpha",
        )
    assert not (outside / "attempt").exists()


def test_projection_rejects_explicit_outside_report_dir_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    outside = tmp_path / "outside"
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output_root))
    with (
        mock.patch.object(
            stackctl,
            "active_deployment_candidate_snapshot",
        ) as candidate_readback,
        mock.patch.object(stackctl, "read_startup_attempt") as startup_readback,
    ):
        result = up_domain._up_evidence_projection(
            argparse.Namespace(target="alpha-local", env="", skip_app=True),
            {
                "exitCode": 2,
                "summary": "stackctl up failed",
                "details": ["typed failure"],
                "reportDir": str(outside),
            },
        )

    assert result["exitCode"] == 2
    assert result["details"][0].startswith("unsafe up report directory:")
    assert not outside.exists()
    candidate_readback.assert_not_called()
    startup_readback.assert_not_called()


def test_canonical_up_run_dir_persists_report_and_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "output"
    report_dir = (
        output_root
        / "env"
        / "alpha"
        / "runs"
        / "20260830T000000000000Z-test-up-alpha-local"
    )
    report_dir.mkdir(parents=True)
    monkeypatch.setenv("QWQ_OUTPUT_ROOT", str(output_root))
    with (
        mock.patch.object(
            stackctl,
            "active_deployment_candidate_snapshot",
            return_value=None,
        ),
        mock.patch.object(stackctl, "read_startup_attempt", return_value=None),
        mock.patch.object(
            stackctl,
            "startup_attempt_path",
            return_value=output_root / "env/alpha/local/alpha-local/process/startup.json",
        ),
    ):
        result = up_domain._up_evidence_projection(
            argparse.Namespace(target="alpha-local", env="", skip_app=True),
            {
                "exitCode": 0,
                "summary": "stackctl up completed for alpha-local",
                "details": [],
                "reportDir": str(report_dir),
            },
        )

    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert result["exitCode"] == 0
    assert report["status"] == "ok"
    assert report["appLaunch"]["status"] == "not_executed"
    assert (report_dir / "summary.json").is_file()
    assert (report_dir / "summary.md").is_file()
    assert output_paths.validate_env_run_evidence_dir(
        report_dir,
        env_name="alpha",
    ) == report_dir.resolve()


def test_prod_hosted_mutations_are_rejected_before_runtime_or_network() -> None:
    for action in hosted_read_only.PROHIBITED_ACTIONS:
        result = hosted_read_only.rejection(action)
        assert result["exitCode"] == 2
        assert result["profile"] == "hosted-read-only"
        assert result["prohibitedAction"] == action

    with mock.patch.object(stackctl, "_runtime_command_up_impl", create=True) as runtime:
        result = up_domain.command_up(
            argparse.Namespace(
                target="prod-hosted", env="", skip_app=True, workload="full"
            )
        )
    assert result["exitCode"] == 2
    runtime.assert_not_called()


def test_hosted_read_only_default_plan_has_only_remote_read_checks() -> None:
    with (
        mock.patch.object(stackctl, "command_status", return_value={"exitCode": 0, "summary": "status"}),
        mock.patch.object(stackctl, "command_health", return_value={"exitCode": 0, "summary": "health"}),
        mock.patch.object(stackctl, "command_verify", return_value={"exitCode": 0, "summary": "verify"}),
        mock.patch.object(stackctl, "command_inspect", return_value={"exitCode": 0, "summary": "inspect"}),
    ):
        result = hosted_read_only.command_hosted_read_only(
            argparse.Namespace(target="prod-hosted", check=[])
        )
    assert result["exitCode"] == 0
    assert [item["check"] for item in result["checks"]] == list(
        hosted_read_only.ALLOWED_CHECKS
    )
    assert result["remoteMutationPerformed"] is False
    assert result["devicePatrol"]["status"] == "not_executed"
    assert result["localApp"]["status"] == "not_executed"
    assert result["actorMutation"]["status"] == "not_executed"


def test_hosted_read_only_parser_surface_is_explicit() -> None:
    args = stackctl.build_parser().parse_args(["hosted-read-only"])
    assert args.target == "prod-hosted"
    assert args.check == []
