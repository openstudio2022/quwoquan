"""stackctl status observes a runtime without materializing provider state.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import json

from quwoquan_ops.cli import stackctl


_LAYERS = (
    "build_ready",
    "runtime_full_ready",
    "provider_ready",
    "release_active",
    "content_exact_queries_ready",
    "device_bound",
    "content_live_passed",
)


def _availability_report(*, first_blocker_class: str) -> dict[str, object]:
    layers = [
        {
            "name": name,
            "status": "blocked",
            "issues": [f"{name} unavailable"],
        }
        for name in _LAYERS
    ]
    return {
        "schema": "stackctl.read_only_user_availability/v1",
        "target": "gamma-local",
        "environment": "gamma",
        "observedAt": "2026-08-18T00:00:00Z",
        "status": "failed",
        "firstBlockerClass": first_blocker_class,
        "firstBlocker": layers[0]["issues"][0],
        "userAvailability": layers,
        "metrics": [],
        "evidence": {},
    }


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
    monkeypatch.setattr(
        stackctl,
        "_health_checks_for_target",
        lambda *_args, **_kwargs: [],
    )
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
    monkeypatch.setattr(
        stackctl,
        "_read_only_user_availability_report",
        lambda _target: _availability_report(first_blocker_class="release"),
    )

    result = stackctl.command_status(
        argparse.Namespace(
            target="gamma-local",
            output_format="json",
            report_dir=str(report_dir),
        )
    )

    assert result["exitCode"] == 1
    assert "build_ready unavailable" in result["details"][0]
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["readOnly"] is True
    assert report["checks"] == []
    assert report["candidateWorkspace"]["status"] == "drifted"
    assert report["firstBlockerClass"] == "release"
    assert [item["name"] for item in report["userAvailability"]] == list(_LAYERS)
    assert result["candidateWorkspace"]["drifted"] is True
    assert result["firstBlockerClass"] == "release"


def test_status__reports_unsafe_active_candidate_without_traceback__local_contract(
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
    monkeypatch.setattr(
        stackctl,
        "_health_checks_for_target",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("deployment candidate payload tree is unsafe")
        ),
    )
    monkeypatch.setattr(stackctl, "_script_probe_plan_for_target", lambda *_args: [])
    monkeypatch.setattr(
        stackctl,
        "_candidate_workspace_report",
        lambda _target: {
            "status": "unavailable",
            "drifted": None,
            "issues": ["candidate/workspace identity is unavailable"],
        },
    )
    monkeypatch.setattr(
        stackctl,
        "_script_probes_for_target",
        lambda *_args: (_ for _ in ()).throw(
            AssertionError("status must stop before stateful probes")
        ),
    )
    monkeypatch.setattr(
        stackctl,
        "_read_only_user_availability_report",
        lambda _target: _availability_report(first_blocker_class="startup_identity"),
    )

    result = stackctl.command_status(
        argparse.Namespace(
            target="gamma-local",
            output_format="json",
            report_dir=str(report_dir),
        )
    )

    assert result["exitCode"] == 1
    assert any("payload tree is unsafe" in detail for detail in result["details"])
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["readOnly"] is True
    assert report["checks"] == [
        {
            "name": "active-candidate",
            "scope": "config",
            "type": "candidate",
            "url": "candidate://gamma-local",
            "ok": False,
            "statusCode": None,
            "bodyPreview": (
                "health check resolution blocked: "
                "deployment candidate payload tree is unsafe"
            ),
            "skipped": False,
        }
    ]
    assert report["candidateWorkspace"]["status"] == "unavailable"
    assert report["firstBlockerClass"] == "startup_identity"


def test_status__reports_stale_provider_runtime_identity_without_traceback__local_contract(
    monkeypatch,
    tmp_path,
) -> None:
    report_dir = tmp_path / "status"
    topology = {"targets": {"beta-local": {"env": "beta"}}}

    monkeypatch.setattr(stackctl, "load_environment_topology", lambda: topology)
    monkeypatch.setattr(
        stackctl,
        "get_target",
        lambda _topology, _target: {"env": "beta"},
    )
    monkeypatch.setattr(stackctl, "resolve_report_dir", lambda *_args: report_dir)
    monkeypatch.setattr(stackctl, "_current_runtime_health_scope", lambda _target: "full")
    monkeypatch.setattr(
        stackctl,
        "_health_checks_for_target",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("GATE_BLOCK: beta-local startup Provider runtime identity is not current")
        ),
    )
    monkeypatch.setattr(stackctl, "_script_probe_plan_for_target", lambda *_args: [])
    monkeypatch.setattr(
        stackctl,
        "_candidate_workspace_report",
        lambda _target: {"status": "stale", "drifted": True, "issues": []},
    )
    monkeypatch.setattr(
        stackctl,
        "_read_only_user_availability_report",
        lambda _target: _availability_report(first_blocker_class="provider"),
    )

    result = stackctl.command_status(
        argparse.Namespace(
            target="beta-local",
            output_format="json",
            report_dir=str(report_dir),
        )
    )

    assert result["exitCode"] == 1
    assert result["details"] == [
        "config/active-candidate failed: ERR candidate://beta-local: "
        "health check resolution blocked: GATE_BLOCK: beta-local startup Provider "
        "runtime identity is not current"
    ]
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["readOnly"] is True
    assert report["checks"] == [
        {
            "name": "active-candidate",
            "scope": "config",
            "type": "candidate",
            "url": "candidate://beta-local",
            "ok": False,
            "statusCode": None,
            "bodyPreview": (
                "health check resolution blocked: GATE_BLOCK: beta-local startup "
                "Provider runtime identity is not current"
            ),
            "skipped": False,
        }
    ]
    assert report["firstBlockerClass"] == "provider"
