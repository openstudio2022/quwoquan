"""Canonical CLI reachability and selector-denial for runtime evidence."""
from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from content.execution.runtime_evidence import cli as cli
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.runtime_evidence.contract import (
    RuntimeEvidenceError,
    RuntimeEvidenceIdentity,
)
from core.runtime_policy import active_runtime_policy

ROOT_ID = "20260805--travel-homepage-m3--china--scale-301"
IDENTITY = RuntimeEvidenceIdentity(
    root_execution_id=ROOT_ID,
    run_id="runtime-evidence-cli-run",
    generation=3,
    fencing_token="sha256:" + "a" * 64,
)


def _runtime(tmp_path: Path) -> CampaignRuntimePaths:
    output = tmp_path / "output"
    return CampaignRuntimePaths(
        repo_root=tmp_path / "repo",
        output_root=output,
        publish_root=tmp_path / "publish",
        campaigns_root=output / "data/local/workspace/campaigns",
        workspaces_root=output / "data/local/cache/workspaces",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="task_command", required=True)
    cli.register_runtime_evidence_parser(commands)
    return parser


def _action_parser(name: str) -> argparse.ArgumentParser:
    runtime_parser = _parser()._subparsers._group_actions[0].choices[
        "runtime-evidence"
    ]
    action = runtime_parser._subparsers._group_actions[0]
    return action.choices[name]


def test_facade_has_one_fixed_action_tree_and_no_free_provider_or_shell_selector() -> None:
    parser = _parser()
    runtime_parser = parser._subparsers._group_actions[0].choices[
        "runtime-evidence"
    ]
    actions = runtime_parser._subparsers._group_actions[0]
    assert tuple(actions.choices) == (
        "create-session",
        "sample",
        "inject-worker-termination",
        "inject-lease-expiry",
        "inject-redis-restart",
        "inject-mongo-reconnect",
        "inject-provider-timeout",
        "inject-provider-rate-limit",
        "finalize",
    )

    option_strings = {
        option
        for action_parser in actions.choices.values()
        for action in action_parser._actions
        for option in action.option_strings
    }
    assert not {
        "--environment",
        "--output-root",
        "--runtime-root",
        "--run-id",
        "--generation",
        "--fencing-token",
        "--fault-type",
        "--provider",
        "--provider-id",
        "--command",
        "--argv",
        "--shell",
    }.intersection(option_strings)

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "runtime-evidence",
                "inject-worker-termination",
                "--campaign-root-execution-id",
                ROOT_ID,
                "--session-id",
                "session-001",
                "--case-id",
                "case-001",
                "--carrier",
                "homepage",
                "--job-id",
                "job-homepage-001",
                "--fault-type",
                "provider_timeout",
            ]
        )


def test_identity_is_derived_only_from_the_canonical_runtime_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(
        cli,
        "read_runtime_snapshot",
        lambda _runtime, _root: {
            "rootExecutionId": ROOT_ID,
            **IDENTITY.as_document(),
        },
    )
    assert cli._identity_from_snapshot(runtime, ROOT_ID) == IDENTITY

    monkeypatch.setattr(
        cli,
        "read_runtime_snapshot",
        lambda _runtime, _root: {
            "runId": "run",
            "generation": 0,
            "fencingToken": "caller-selected-token",
        },
    )
    with pytest.raises(RuntimeEvidenceError, match="identity is incomplete"):
        cli._identity_from_snapshot(runtime, ROOT_ID)


def test_create_session_freezes_only_the_built_in_queue_and_worker_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = _runtime(tmp_path)
    captured: dict[str, Any] = {}
    monkeypatch.setattr(cli, "_runtime_paths", lambda: runtime)
    monkeypatch.setattr(cli, "_identity_from_snapshot", lambda *_args: IDENTITY)
    monkeypatch.setattr(
        cli,
        "plan_path",
        lambda *_args: runtime.campaigns_root / ROOT_ID / "campaign_plan.json",
    )
    monkeypatch.setattr(
        cli,
        "_execution_ids_from_plan",
        lambda _path: {carrier: f"execution-{carrier}" for carrier in cli.CARRIERS},
    )
    queue = SimpleNamespace(
        binding=SimpleNamespace(
            provider_id="local_object_queue_v1",
            configuration_digest="sha256:" + "d" * 64,
        )
    )
    monkeypatch.setattr(
        cli,
        "resolve_frozen_queue_evidence_provider",
        lambda _execution_ids: queue,
    )

    def fake_create(**kwargs: Any) -> tuple[dict[str, str], Path]:
        captured.update(kwargs)
        return {"receiptDigest": "sha256:" + "b" * 64}, tmp_path / "session.json"

    monkeypatch.setattr(cli, "create_runtime_evidence_session", fake_create)
    monkeypatch.setattr(cli, "_summary", lambda **_kwargs: {"ok": True})
    cli._handle_create_session(
        SimpleNamespace(
            campaign_root_execution_id=ROOT_ID,
            session_id="session-001",
        )
    )

    assert captured["identity"] == IDENTITY
    assert captured["inspector"]._timeout_seconds == (
        active_runtime_policy().runtime_evidence.process_inspection_timeout_seconds
    )
    assert captured["queue_evidence_provider"].provider_id == "local_object_queue_v1"
    fault_bindings = captured["fault_providers"]
    assert len(fault_bindings) == 6
    assert fault_bindings[0].fault_type == "worker_termination"
    assert {row.fault_type for row in fault_bindings} == {
        "worker_termination",
        "lease_expiry",
        "redis_restart",
        "mongo_reconnect",
        "provider_timeout",
        "provider_rate_limit",
    }
    assert "ok" in capsys.readouterr().out


def test_inject_action_hard_codes_worker_termination_and_session_execution_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = _runtime(tmp_path)
    captured: dict[str, Any] = {}
    worker_id = "20260805--travel-image-m3--china--scale-302"
    monkeypatch.setattr(cli, "_runtime_paths", lambda: runtime)
    monkeypatch.setattr(cli, "_identity_from_snapshot", lambda *_args: IDENTITY)
    session = {
        "workers": [
            {
                "carrier": carrier,
                "executionId": worker_id if carrier == "image" else f"execution-{carrier}",
            }
            for carrier in cli.CARRIERS
        ]
    }
    monkeypatch.setattr(cli, "load_runtime_evidence_session", lambda *_args: session)
    queue = SimpleNamespace(binding=SimpleNamespace(as_document=dict))
    monkeypatch.setattr(
        cli,
        "resolve_frozen_queue_evidence_provider",
        lambda _execution_ids: queue,
    )

    def fake_inject(**kwargs: Any) -> tuple[dict[str, str], Path]:
        captured.update(kwargs)
        return {"receiptDigest": "sha256:" + "c" * 64}, tmp_path / "receipt.json"

    monkeypatch.setattr(cli, "inject_fault", fake_inject)
    monkeypatch.setattr(cli, "_summary", lambda **_kwargs: {"ok": True})
    cli._handle_inject_worker_termination(
        SimpleNamespace(
            campaign_root_execution_id=ROOT_ID,
            session_id="session-001",
            case_id="case-001",
            carrier="image",
            job_id="job-image-001",
            confirm_active_worker_termination=True,
        )
    )

    assert captured["fault_type"] == "worker_termination"
    assert captured["execution_id"] == worker_id
    assert captured["inspector"]._timeout_seconds == (
        active_runtime_policy().runtime_evidence.process_inspection_timeout_seconds
    )
    assert captured["queue_event_timeout_seconds"] == (
        active_runtime_policy().runtime_evidence.queue_fault_event_timeout_seconds
    )
    assert set(captured["providers"]) == {"worker_termination"}
    assert captured["providers"]["worker_termination"].binding.fault_type == (
        "worker_termination"
    )
    assert "ok" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("action", "handler", "fault_type"),
    (
        ("inject-lease-expiry", cli._handle_inject_lease_expiry, "lease_expiry"),
        ("inject-redis-restart", cli._handle_inject_redis_restart, "redis_restart"),
        ("inject-mongo-reconnect", cli._handle_inject_mongo_reconnect, "mongo_reconnect"),
        ("inject-provider-timeout", cli._handle_inject_provider_timeout, "provider_timeout"),
        ("inject-provider-rate-limit", cli._handle_inject_provider_rate_limit, "provider_rate_limit"),
    ),
)
def test_fixed_fault_actions_have_no_free_selector_and_require_confirmation(
    action: str,
    handler: Any,
    fault_type: str,
) -> None:
    parser = _action_parser(action)
    options = {
        option
        for item in parser._actions
        for option in item.option_strings
    }
    assert "--fault-type" not in options
    assert "--provider" not in options
    assert "--confirm-governed-fault-request" in options
    with pytest.raises(RuntimeEvidenceError, match=fault_type):
        handler(SimpleNamespace(confirm_governed_fault_request=False))


def test_finalize_refuses_an_active_campaign_lease(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(cli, "_runtime_paths", lambda: runtime)
    monkeypatch.setattr(cli, "_identity_from_snapshot", lambda *_args: IDENTITY)
    monkeypatch.setattr(cli, "assert_campaign_fence", lambda *_args, **_kwargs: {"status": "active"})
    monkeypatch.setattr(
        cli,
        "finalize_resource_samples",
        lambda **_kwargs: pytest.fail("active session must not finalize resources"),
    )
    monkeypatch.setattr(
        cli,
        "finalize_fault_cases",
        lambda **_kwargs: pytest.fail("active session must not finalize faults"),
    )
    with pytest.raises(RuntimeEvidenceError, match="lease is active"):
        cli._handle_finalize(
            SimpleNamespace(
                campaign_root_execution_id=ROOT_ID,
                session_id="session-001",
            )
        )


def test_worker_termination_requires_explicit_confirmation() -> None:
    inject = _action_parser("inject-worker-termination")
    confirmation = [
        action
        for action in inject._actions
        if "--confirm-active-worker-termination" in action.option_strings
    ]
    assert len(confirmation) == 1
    assert confirmation[0].required is True

    with pytest.raises(RuntimeEvidenceError, match="explicit confirmation"):
        cli._handle_inject_worker_termination(
            SimpleNamespace(confirm_active_worker_termination=False)
        )
