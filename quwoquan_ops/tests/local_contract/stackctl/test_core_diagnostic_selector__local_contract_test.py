# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-045.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-045.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-045.t3
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-045.t4
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-045.t5
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.commands import verify_domain


def _args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "verification_purpose": "core-diagnostic",
        "feature": ["identity"],
        "env": "gamma",
        "target": "gamma-local",
        "deployment_instance": "",
        "data_mode": "",
        "data_release_id": "release-a",
        "data_verify_run_id": "verify-a",
        "data_manifest_digest": "sha256:" + "a" * 64,
        "app_core_diagnostic_report": "",
        "report_dir": str(tmp_path / "report"),
        "kind": "all",
        "profile": "release",
        "service": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_core_diagnostic_selector_preserves_non_promotable_contract(tmp_path: Path) -> None:
    data_report = tmp_path / "data-release" / "release-a" / "verify-a" / "core-diagnostic-report.json"
    data_report.parent.mkdir(parents=True)
    data_report.write_text(json.dumps({
        "releaseId": "release-a",
        "manifestDigest": "sha256:" + "a" * 64,
        "nonPromotable": True,
        "releaseEligibility": "GATE_BLOCK",
        "readinessWritten": False,
        "caseResults": [{"feature": "identity", "status": "passed", "detail": "ok"}],
    }))
    with mock.patch("quwoquan_ops.cli.stackctl.env_runs_root", return_value=tmp_path), mock.patch(
        "quwoquan_ops.cli.stackctl.resolve_report_dir", return_value=tmp_path / "report"
    ):
        result = verify_domain.command_verify(_args(tmp_path))
    assert result["exitCode"] == 0
    assert result["nonPromotable"] is True
    assert result["releaseEligibility"] == "GATE_BLOCK"
    assert result["readinessWritten"] is False


def test_formal_verify_does_not_enter_core_diagnostic_selector(tmp_path: Path) -> None:
    args = _args(tmp_path, verification_purpose="formal-readiness")
    with mock.patch.object(verify_domain, "_command_core_diagnostic") as diagnostic, mock.patch(
        "quwoquan_ops.cli.stackctl._selected_verify_commands", return_value=[]
    ), mock.patch("quwoquan_ops.cli.stackctl._run_static_verify_wave", return_value=([], None, 0)), mock.patch(
        "quwoquan_ops.cli.stackctl._selected_profile_commands", return_value=[]
    ), mock.patch("quwoquan_ops.cli.stackctl._run_profile_commands_parallel", return_value=[]), mock.patch(
        "quwoquan_ops.cli.stackctl.can_reuse_package", return_value=(True, "ok")
    ), mock.patch("quwoquan_ops.cli.stackctl.resolve_report_dir", return_value=tmp_path / "formal"):
        verify_domain.command_verify(args)
    diagnostic.assert_not_called()


def test_selected_write_case_requires_exact_app_diagnostic(tmp_path: Path) -> None:
    data_report = tmp_path / "data-release" / "release-a" / "verify-a" / "core-diagnostic-report.json"
    data_report.parent.mkdir(parents=True)
    data_report.write_text(json.dumps({
        "releaseId": "release-a",
        "manifestDigest": "sha256:" + "a" * 64,
        "nonPromotable": True,
        "releaseEligibility": "GATE_BLOCK",
        "readinessWritten": False,
        "caseResults": [{"feature": "post-write-readback", "status": "not_executed", "detail": "Data boundary"}],
    }))
    app_report = tmp_path / "app-core.json"
    app_report.write_text(json.dumps({
        "status": "diagnostic_complete",
        "verificationPurpose": "core_diagnostic",
        "nonPromotable": True,
        "suitePlan": {"selected": ["post-write-readback"]},
        "evidenceRefs": [{"suite": "post-write-readback", "reportRef": "env/prod/run.json"}],
        "diagnosticBindings": {"releaseReadbacks": {"prod-hosted": {
            "releaseId": "release-a",
            "manifestDigest": "sha256:" + "a" * 64,
            "activationEnvelopeDigest": "sha256:" + "b" * 64,
        }}},
    }))
    args = _args(
        tmp_path,
        feature=["post-write-readback"],
        app_core_diagnostic_report=str(app_report),
    )
    with mock.patch("quwoquan_ops.cli.stackctl.env_runs_root", return_value=tmp_path), mock.patch(
        "quwoquan_ops.cli.stackctl.output_root", return_value=tmp_path
    ), mock.patch(
        "quwoquan_ops.cli.stackctl.resolve_report_dir", return_value=tmp_path / "report"
    ):
        result = verify_domain.command_verify(args)
    assert result["exitCode"] == 0
