"""stackctl status observes a runtime without materializing provider state.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import json

from quwoquan_ops.cli import stackctl


def test_status__does_not_execute_stateful_script_probes__local_contract(
    monkeypatch,
    tmp_path,
) -> None:
    report_dir = tmp_path / "status"
    topology = {"targets": {"gamma-local": {"env": "gamma"}}}

    monkeypatch.setattr(stackctl, "load_environment_topology", lambda: topology)
    monkeypatch.setattr(
        stackctl,
        "get_target",
        lambda _topology, _target: {"env": "gamma"},
    )
    monkeypatch.setattr(stackctl, "resolve_report_dir", lambda *_args: report_dir)
    monkeypatch.setattr(stackctl, "_current_runtime_health_scope", lambda _target: "full")
    monkeypatch.setattr(stackctl, "_health_checks_for_target", lambda *_args: [])
    monkeypatch.setattr(stackctl, "_script_probe_plan_for_target", lambda *_args: [])
    monkeypatch.setattr(
        stackctl,
        "_candidate_workspace_report",
        lambda _target: {
            "status": "drifted",
            "drifted": True,
            "issues": ["managed inputs changed"],
        },
    )
    monkeypatch.setattr(
        stackctl,
        "_script_probes_for_target",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("status must not execute provider or secret materialization probes")
        ),
    )

    result = stackctl.command_status(
        argparse.Namespace(
            target="gamma-local",
            output_format="json",
            report_dir=str(report_dir),
        )
    )

    assert result["exitCode"] == 0
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["readOnly"] is True
    assert report["checks"] == []
    assert report["candidateWorkspace"]["status"] == "drifted"
    assert result["candidateWorkspace"]["drifted"] is True
