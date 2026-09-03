"""stackctl status observes a runtime without materializing provider state.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-001
"""
from __future__ import annotations

import argparse
import json

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import read_only_user_availability


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
        "schema": read_only_user_availability.SCHEMA,
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
    runtime_holder = {
        "path": "/tmp/host-locks/local-runtime/workstation-commercial-runtime.lock",
        "record": "pid=42 worktree=/tmp/integration lane=dev1.0",
        "pid": "42",
        "worktree": "/tmp/integration",
        "lane": "dev1.0",
    }
    monkeypatch.setattr(
        stackctl,
        "local_runtime_lock_holders",
        lambda: [runtime_holder],
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
    assert result["localRuntimeLocks"] == [runtime_holder]
    assert any(
        "worktree=/tmp/integration lane=dev1.0" in detail
        for detail in result["details"]
    )
    assert report["localRuntimeLocks"] == [runtime_holder]


def test_status__currentness_timeout_stays_fail_closed_without_false_drift__local_contract(
    monkeypatch,
    tmp_path,
) -> None:
    report_dir = tmp_path / "status"
    topology = {"targets": {"gamma-local": {"env": "gamma"}}}
    currentness = {
        "status": "currentness_unavailable",
        "purpose": "currentness",
        "selfVerified": True,
        "currentSourceClaim": "not_evaluated",
        "nonPromotable": True,
        "drifted": None,
        "candidate": {"baselineId": "sha256:" + "a" * 64},
        "current": {
            "detail": (
                "verification_timeout: fingerprint rejected: "
                "deployment input currentness check timed out"
            )
        },
        "mismatchedFields": [],
        "issues": [],
        "warnings": ["deployment input currentness check timed out"],
        "firstBlockerClass": "verification_timeout",
    }

    monkeypatch.setattr(stackctl, "load_environment_topology", lambda: topology)
    monkeypatch.setattr(
        stackctl,
        "get_target",
        lambda _topology, _target: {"env": "gamma"},
    )
    monkeypatch.setattr(stackctl, "resolve_report_dir", lambda *_args: report_dir)
    monkeypatch.setattr(
        stackctl, "_current_runtime_health_scope", lambda _target: "full"
    )

    def command_health(args):
        stackctl.write_json(
            report_dir / "report.json",
            {"command": "health", "readOnly": True, "checks": []},
        )
        return {
            "exitCode": 0,
            "summary": "stackctl health gamma-local: ready",
            "details": [],
        }

    monkeypatch.setattr(stackctl, "command_health", command_health)

    def candidate_report(_target, *, purpose="self_verify"):
        assert purpose == "currentness"
        return currentness

    monkeypatch.setattr(stackctl, "_candidate_workspace_report", candidate_report)

    result = stackctl.command_status(
        argparse.Namespace(
            target="gamma-local",
            currentness=True,
            output_format="json",
            report_dir=str(report_dir),
        )
    )

    assert result["exitCode"] == 1
    assert "verification_timeout" in result["details"][0]
    assert result["candidateWorkspace"]["status"] == "currentness_unavailable"
    assert result["candidateWorkspace"]["drifted"] is None
    assert result["candidateWorkspace"]["mismatchedFields"] == []
    assert result["candidateWorkspace"]["firstBlockerClass"] == "verification_timeout"
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["candidateWorkspace"]["currentSourceClaim"] == "not_evaluated"
    assert report["candidateWorkspace"]["drifted"] is None
    assert report["candidateWorkspace"]["mismatchedFields"] == []


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
