from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest
from content.execution.campaign import plan as campaign_plan
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.planning import semantic_preflight_admission
from content.execution.preflight import handler as preflight_handler
from content.execution.preflight import receipt as preflight_receipt
from content.execution.preflight import runtime as preflight_runtime
from content.execution.preflight.handler import register_task_preflight_parser
from content.execution.preflight.receipt import (
    build_semantic_preflight_receipt,
    validate_semantic_preflight_receipt,
    write_semantic_preflight_receipt,
)
from content.execution.preflight.selection import (
    CALIBRATION_SEMANTIC_SELECTION_ID,
    bind_semantic_preflight_selection,
    resolve_semantic_preflight_selection,
)
from core.control_types import AgentProvider
from core.cursor_credentials import CURSOR_SENSITIVE_PROCESS_ENV_KEYS
from core.io import read_json, write_json
from core.runtime_policy import active_runtime_policy
from support.semantic_preflight_fixture import ready_semantic_preflight


def _requested_probe_attempts() -> int:
    """Probe 数是显式诊断请求，不是 Provider 或主机并发上限。"""
    return active_runtime_policy().startup_probe_suite_attempts


def _args(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "semantic_selection_id": "cursor_auto",
        "json": True,
        "no_semantic_agent_credential": False,
        "no_network": False,
        "endpoint": None,
        "no_semantic_agent_startup": False,
        "semantic_agent_startup": True,
        "soak": True,
        "workspace_smoke": True,
        "workspace_smoke_carrier": ["homepage", "video"],
        "report_out": str(tmp_path / "compact.json"),
        "receipt_out": str(tmp_path / "receipt.json"),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _ready_preflight(**kwargs: object) -> dict[str, object]:
    provider = kwargs["provider"]
    model = kwargs["startup_model"]
    runtime = kwargs["startup_runtime"]
    return {
        "schema": "quwoquan_data.environment_preflight",
        "provider": provider.value,
        "runtime": {"ready": True, "resolvedPython": sys.executable},
        "semanticAgentCredential": {
            "provider": provider.value,
            "source": "fake",
            "present": True,
            "valid": True,
            "issues": [],
        },
        "network": {"checked": True, "ready": True, "issues": []},
        "semanticAgentStartup": {
            "checked": True,
            "ready": True,
            "provider": provider.value,
            "model": model.model_id,
            "runtime": runtime,
            "issues": [],
        },
        "ready": True,
        "issues": [],
    }


def _ready_workspace_probe(**kwargs: object) -> dict[str, object]:
    workspaces = tuple(kwargs.get("workspaces") or ())
    count = len(workspaces)
    return {
        "ready": True,
        "workspaceCount": count,
        "successCount": count,
        "configuredConcurrency": count,
        "effectiveConcurrency": count,
        "issues": [],
    }


def test_selector_resolves_default_sol_grok_and_auto_without_fallback() -> None:
    default = resolve_semantic_preflight_selection("default")
    calibration = resolve_semantic_preflight_selection(
        CALIBRATION_SEMANTIC_SELECTION_ID
    )
    grok = resolve_semantic_preflight_selection("cursor_grok")
    cursor = resolve_semantic_preflight_selection("cursor_auto")

    assert default.provider is AgentProvider.CODEX_SDK
    assert default.model_selection.model_id == "gpt-5.6-terra"
    assert default.requires_new_retry_of is False
    assert calibration.provider is AgentProvider.CODEX_SDK
    assert calibration.model_selection.model_id == "gpt-5.6-sol"
    assert calibration.requires_new_retry_of is False
    assert grok.provider is AgentProvider.CURSOR_SDK
    assert grok.model_selection.model_id.startswith("grok-")
    assert all(
        set(row) == {"id", "value"} and row["id"] and row["value"]
        for row in grok.model_selection.parameters_document()
    )
    assert grok.requires_new_retry_of is False
    assert cursor.provider is AgentProvider.CURSOR_SDK
    assert cursor.model_selection.model_id == "auto"
    assert cursor.requires_new_retry_of is True
    assert len(
        {
            default.selection_digest,
            calibration.selection_digest,
            grok.selection_digest,
            cursor.selection_digest,
        }
    ) == 4
    with pytest.raises(ValueError, match="unknown explicit semantic selection"):
        resolve_semantic_preflight_selection("unmanaged")


def test_cli_parser_exposes_governed_sol_calibration_selection() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="task_command", required=True)
    register_task_preflight_parser(commands)

    parsed = parser.parse_args(
        [
            "preflight",
            "--semantic-selection-id",
            CALIBRATION_SEMANTIC_SELECTION_ID,
            "--no-semantic-agent-startup",
        ]
    )

    assert parsed.semantic_selection_id == CALIBRATION_SEMANTIC_SELECTION_ID


def test_cli_parser_exposes_exact_cursor_grok_selection() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="task_command", required=True)
    register_task_preflight_parser(commands)

    parsed = parser.parse_args(
        [
            "preflight",
            "--semantic-selection-id",
            "cursor_grok",
            "--no-semantic-agent-startup",
        ]
    )

    assert parsed.semantic_selection_id == "cursor_grok"


def test_cli_parser_routes_pool_delivery_without_semantic_provider(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from content.execution.preflight import pool_delivery

    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="task_command", required=True)
    register_task_preflight_parser(commands)
    execution_id = "20260811--travel-article-m100--china--scale-001"
    args = parser.parse_args(
        [
            "preflight",
            "--profile",
            "pool-delivery",
            "--execution-id",
            execution_id,
            "--json",
        ]
    )
    monkeypatch.setattr(
        pool_delivery,
        "run_pool_delivery_preflight",
        lambda actual_args: {
            "schema": "quwoquan_data.pool_delivery_preflight",
            "preflightProfile": "pool-delivery",
            "executionId": actual_args.execution_id,
            "poolDeliveryReady": True,
            "ready": True,
            "issueCode": None,
            "issues": [],
        },
    )
    monkeypatch.setattr(
        preflight_handler,
        "prepare_data_runtime_cache",
        lambda **_kwargs: pytest.fail("pool delivery must not prepare semantic runtime"),
    )

    preflight_handler.handle_ready(args)

    report = json.loads(capsys.readouterr().out)
    assert report["preflightProfile"] == "pool-delivery"
    assert report["executionId"] == execution_id


def test_cursor_runtime_dependency_gap_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    python = tmp_path / "python"
    python.touch()
    observed: dict[str, object] = {}

    def fake_prepare(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return {"ready": True, "python": str(python), "missing": []}

    monkeypatch.setattr(
        preflight_runtime,
        "python_has_modules",
        lambda *_args: (False, ["cursor_sdk: missing"]),
    )
    report = preflight_runtime.prepare_selected_runtime(
        resolve_semantic_preflight_selection("cursor_auto"),
        prepare=fake_prepare,
    )

    assert str(observed["requirements"]).endswith("requirements-cursor.txt")
    assert report["provider"] == "cursor_sdk"
    assert report["providerModulesReady"] is False
    assert report["ready"] is False
    assert report["missing"] == ["cursor_sdk: missing"]


def test_cursor_auto_preflight_and_soak_bind_exact_runtime_and_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: list[dict[str, object]] = []
    prepared: dict[str, object] = {}

    def fake_prepare(**kwargs: object) -> dict[str, object]:
        prepared.update(kwargs)
        return {"ready": True, "python": sys.executable, "missing": []}

    monkeypatch.setattr(
        preflight_handler,
        "prepare_data_runtime_cache",
        fake_prepare,
    )
    monkeypatch.setattr(
        preflight_runtime,
        "python_has_modules",
        lambda *_args: (True, []),
    )
    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_environment_preflight",
        lambda **kwargs: observed.append(dict(kwargs)) or _ready_preflight(**kwargs),
    )

    def fake_soak(**kwargs: object) -> dict[str, object]:
        observed.append(dict(kwargs))
        return {
            "attempts": 8,
            "successCount": 8,
            "effectiveConcurrency": _requested_probe_attempts(),
            "bridgeDisconnectCount": 0,
            "issues": [],
            "ready": True,
        }

    monkeypatch.setattr(preflight_handler, "semantic_agent_probe_suite", fake_soak)
    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_workspace_probe_suite",
        _ready_workspace_probe,
    )

    preflight_handler.handle_ready(_args(tmp_path))

    output = json.loads(capsys.readouterr().out)
    assert output["semanticSelectionId"] == "cursor_auto"
    assert output["provider"] == "cursor_sdk"
    assert output["model"] == "auto"
    assert output["semanticRuntime"] == "local"
    assert output["fallbackPolicy"] == "forbidden"
    assert output["prepare"]["provider"] == "cursor_sdk"
    assert str(prepared["requirements"]).endswith("requirements-cursor.txt")
    assert output["capacitySoak"]["semanticSelectionId"] == "cursor_auto"
    assert observed[0]["provider"] is AgentProvider.CURSOR_SDK
    assert observed[0]["startup_model"].model_id == "auto"
    assert observed[1]["provider"] is AgentProvider.CURSOR_SDK
    assert observed[1]["model"].model_id == "auto"

    compact = json.loads((tmp_path / "compact.json").read_text(encoding="utf-8"))
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert compact["semanticSelectionId"] == "cursor_auto"
    assert compact["runtimeProfileDigest"] == receipt["runtimeProfileDigest"]
    assert receipt["semanticSelectionId"] == "cursor_auto"
    assert receipt["selectionDigest"] == output["selectionDigest"]
    assert receipt["provider"] == "cursor_sdk"
    assert receipt["model"] == "auto"
    assert receipt["soakRequested"] is True
    assert receipt["schema"] == "quwoquan_data.semantic_provider_preflight_receipt"
    assert receipt["preflightProfile"] == "semantic"
    assert compact["workspaceSmoke"]["workspaceCount"] == 2
    assert compact["workspaceSmoke"]["successCount"] == 2
    assert "reliableTaskFleet" not in receipt["evidence"]
    validate_semantic_preflight_receipt(
        receipt,
        expected_selection=resolve_semantic_preflight_selection("cursor_auto"),
    )
    expired_receipt = {
        **receipt,
        "recordedAt": "2020-01-01T00:00:00Z",
        "validUntil": "2020-01-01T00:10:00Z",
    }
    expired_receipt["receiptId"] = preflight_receipt._digest(
        {key: value for key, value in expired_receipt.items() if key != "receiptId"}
    )
    validate_semantic_preflight_receipt(
        expired_receipt,
        expected_selection=resolve_semantic_preflight_selection("cursor_auto"),
    )


def test_existing_manifest_review_to_run_and_resume_reuse_expired_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    selection = resolve_semantic_preflight_selection("cursor_auto")
    receipt_path = tmp_path / "data/local/cache/semantic-preflight/receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt = {
        "receiptId": "sha256:" + "1" * 64,
        "selectionDigest": selection.selection_digest,
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    binding = {
        "receiptRef": receipt_path.relative_to(tmp_path).as_posix(),
        "receiptFileSha256": semantic_preflight_admission.file_sha256(receipt_path),
        "receiptId": receipt["receiptId"],
        "selectionDigest": receipt["selectionDigest"],
    }
    validation_checks: list[str] = []

    def validate(
        _receipt: object,
        *,
        expected_selection: object,
    ) -> None:
        assert expected_selection == selection
        validation_checks.append(selection.selection_digest)

    monkeypatch.setattr(
        semantic_preflight_admission,
        "validate_semantic_preflight_receipt",
        validate,
    )

    for _phase in ("run", "resume"):
        resolved = semantic_preflight_admission.resolve_cli_preflight_binding(
            existing_manifest={"semanticPreflightReceipt": binding},
            requested_receipt_ref=binding["receiptRef"],
            semantic_selection_id="cursor_auto",
            output_root=tmp_path,
        )
        assert resolved == binding
    assert validation_checks == [selection.selection_digest] * 6


def test_frozen_and_direct_admission_reuse_expired_receipt_identity(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "output"
    receipt_path, _binding = ready_semantic_preflight(
        "cursor_auto",
        output_root=output_root,
    )
    receipt = read_json(receipt_path)
    receipt["recordedAt"] = "2020-01-01T00:00:00Z"
    receipt["validUntil"] = "2020-01-01T00:10:00Z"
    receipt["receiptId"] = preflight_receipt._digest(
        {key: value for key, value in receipt.items() if key != "receiptId"}
    )
    write_json(receipt_path, receipt)
    binding = semantic_preflight_admission.bind_semantic_preflight_receipt(
        receipt_path,
        semantic_selection_id="cursor_auto",
        output_root=output_root,
    )
    direct_binding = semantic_preflight_admission.bind_semantic_preflight_receipt(
        receipt_path,
        semantic_selection_id="cursor_auto",
        output_root=output_root,
    )
    assert direct_binding == binding

    root_id = "20200101--travel-homepage-m1--china--scale-001"
    execution_ids = {
        carrier: root_id.replace("-homepage-", f"-{carrier}-")
        for carrier in ("homepage", "article", "image", "video")
    }
    runtime = CampaignRuntimePaths(
        repo_root=tmp_path,
        output_root=output_root,
        publish_root=tmp_path / "publish",
        campaigns_root=tmp_path / "campaigns",
        workspaces_root=tmp_path / "workspaces",
    )
    stable = {
        "schema": "quwoquan_data.content_campaign_plan",
        "rootExecutionId": root_id,
        "executionMode": "central",
        "scale": "M1",
        "workloadMode": "explicit",
        "activeCarriers": list(execution_ids),
        "workloads": {carrier: 1 for carrier in execution_ids},
        "gitBranch": "dev1.0",
        "gitCommitSha": "a" * 40,
        "sourceRevision": "sha256:" + "b" * 64,
        "sourceDigest": "sha256:" + "c" * 64,
        "executionBundle": {
            "algorithm": "sha256",
            "digest": "sha256:" + "9" * 64,
            "inputs": ["semantic-preflight-test-fixture"],
        },
        "entityCatalogDigest": "sha256:" + "d" * 64,
        "semanticSelectionId": "cursor_auto",
        "semanticPreflightReceipt": binding,
        "laneExternalInputs": {
            carrier: {
                "executionId": execution_ids[carrier],
                "externalInputRefs": [],
                "externalInputsDigest": "sha256:" + "e" * 64,
            }
            for carrier in execution_ids
        },
        "externalInputsDigest": "sha256:" + "f" * 64,
        "submissionDigests": {
            carrier: "sha256:" + str(index) * 64
            for index, carrier in enumerate(execution_ids, start=1)
        },
        "executionIds": execution_ids,
        "frozenAt": "2020-01-01T00:05:00Z",
    }
    plan = {**stable, "planDigest": campaign_plan.sha256_payload(stable)}
    path = campaign_plan.plan_path(runtime, root_id)
    path.parent.mkdir(parents=True)
    write_json(path, plan)

    admitted = campaign_plan.require_frozen_campaign_preflight_admission(
        runtime,
        root_id,
        execution_id=execution_ids["image"],
        semantic_selection_id="cursor_auto",
        requested_receipt_ref=binding["receiptRef"],
        expected_plan_digest=plan["planDigest"],
    )
    assert admitted == binding
    first_manifest_binding = (
        semantic_preflight_admission.resolve_manifest_preflight_binding(
            existing_manifest=None,
            requested_binding=admitted,
            semantic_selection_id="cursor_auto",
            output_root=output_root,
        )
    )
    assert first_manifest_binding == binding


def test_semantic_preflight_ignores_queue_environment_and_diagnostic_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from content.execution.queue.reliabletask import fleet

    monkeypatch.setattr(
        fleet,
        "reliabletask_fleet_preflight",
        lambda: pytest.fail("semantic preflight must not probe ReliableTask"),
    )
    monkeypatch.setattr(
        preflight_handler,
        "prepare_data_runtime_cache",
        lambda **_kwargs: {"ready": True, "python": sys.executable, "missing": []},
    )
    monkeypatch.setattr(
        preflight_runtime,
        "python_has_modules",
        lambda *_args: (True, []),
    )

    def provider_ready_with_hostile_fleet(**kwargs: object) -> dict[str, object]:
        report = _ready_preflight(**kwargs)
        report["reliableTaskFleet"] = {
            "checked": True,
            "ready": False,
            "target": "beta-local",
            "mongo": False,
            "redis": False,
            "owned": False,
            "issues": ["beta-local has no active immutable candidate"],
        }
        return report

    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_environment_preflight",
        provider_ready_with_hostile_fleet,
    )
    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_probe_suite",
        lambda **_kwargs: {
            "attempts": 8,
            "successCount": 1,
            "effectiveConcurrency": 1,
            "bridgeDisconnectCount": 1,
            "issues": ["diagnostic capacity probe observed failures"],
            "ready": False,
        },
    )

    def failed_workspace_probe(**kwargs: object) -> dict[str, object]:
        workspaces = tuple(kwargs.get("workspaces") or ())
        assert [Path(workspace).name for workspace in workspaces] == [
            "homepage",
            "video",
        ]
        return {
            "ready": False,
            "workspaceCount": len(workspaces),
            "successCount": 1,
            "configuredConcurrency": len(workspaces),
            "effectiveConcurrency": 1,
            "issues": ["diagnostic workspace probe observed failures"],
        }

    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_workspace_probe_suite",
        failed_workspace_probe,
    )

    preflight_handler.handle_ready(_args(tmp_path))

    output = json.loads(capsys.readouterr().out)
    compact = json.loads((tmp_path / "compact.json").read_text(encoding="utf-8"))
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert output["ready"] is True
    assert compact["capacitySoak"]["ready"] is False
    assert compact["workspaceSmoke"]["ready"] is False
    assert compact["workspaceSmoke"]["workspaceCount"] == 2
    assert "reliableTaskFleet" not in compact
    assert "reliableTaskFleet" not in receipt["evidence"]
    assert receipt["ready"] is True
    validate_semantic_preflight_receipt(receipt)
    mixed_receipt = {
        **receipt,
        "evidence": {**receipt["evidence"], "mongoReady": False},
    }
    with pytest.raises(ValueError, match="mongoReady"):
        validate_semantic_preflight_receipt(mixed_receipt)


def test_sol_calibration_preflight_binds_exact_model_without_real_provider_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: list[dict[str, object]] = []
    monkeypatch.setattr(
        preflight_handler,
        "prepare_data_runtime_cache",
        lambda **_kwargs: {"ready": True, "python": sys.executable, "missing": []},
    )
    monkeypatch.setattr(
        preflight_runtime,
        "python_has_modules",
        lambda *_args: (True, []),
    )
    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_environment_preflight",
        lambda **kwargs: observed.append(dict(kwargs)) or _ready_preflight(**kwargs),
    )
    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_probe_suite",
        lambda **kwargs: observed.append(dict(kwargs))
        or {
            "attempts": 8,
            "successCount": 8,
            "effectiveConcurrency": _requested_probe_attempts(),
            "bridgeDisconnectCount": 0,
            "issues": [],
            "ready": True,
        },
    )
    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_workspace_probe_suite",
        _ready_workspace_probe,
    )

    preflight_handler.handle_ready(
        _args(tmp_path, semantic_selection_id=CALIBRATION_SEMANTIC_SELECTION_ID)
    )

    output = json.loads(capsys.readouterr().out)
    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    selection = resolve_semantic_preflight_selection(
        CALIBRATION_SEMANTIC_SELECTION_ID
    )
    assert output["semanticSelectionId"] == CALIBRATION_SEMANTIC_SELECTION_ID
    assert output["provider"] == "codex_sdk"
    assert output["model"] == "gpt-5.6-sol"
    assert output["fallbackPolicy"] == "forbidden"
    assert output["capacitySoak"]["selectionDigest"] == selection.selection_digest
    assert output["capacitySoak"]["model"] == "gpt-5.6-sol"
    assert observed[0]["provider"] is AgentProvider.CODEX_SDK
    assert observed[0]["startup_model"].model_id == "gpt-5.6-sol"
    assert observed[1]["provider"] is AgentProvider.CODEX_SDK
    assert observed[1]["model"].model_id == "gpt-5.6-sol"
    validate_semantic_preflight_receipt(
        receipt,
        expected_selection=selection,
    )


def test_preflight_receipt_is_create_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "receipt.json"
    monkeypatch.setattr(
        preflight_handler,
        "prepare_data_runtime_cache",
        lambda **_kwargs: {"ready": True, "python": sys.executable, "missing": []},
    )
    monkeypatch.setattr(
        preflight_runtime,
        "python_has_modules",
        lambda *_args: (True, []),
    )
    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_environment_preflight",
        _ready_preflight,
    )
    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_probe_suite",
        lambda **_kwargs: {
            "attempts": 8,
            "successCount": 8,
            "effectiveConcurrency": _requested_probe_attempts(),
            "bridgeDisconnectCount": 0,
            "issues": [],
            "ready": True,
        },
    )
    monkeypatch.setattr(
        preflight_handler,
        "semantic_agent_workspace_probe_suite",
        _ready_workspace_probe,
    )
    args = _args(tmp_path, json=False, report_out=None, receipt_out=str(destination))
    preflight_handler.handle_ready(args)
    preflight_handler.handle_ready(args)
    receipt = json.loads(destination.read_text(encoding="utf-8"))
    tampered = dict(receipt)
    tampered["ready"] = False
    with pytest.raises(ValueError, match="receiptId mismatch"):
        write_semantic_preflight_receipt(tmp_path / "tampered.json", tampered)

    default = resolve_semantic_preflight_selection("default")
    default_report = {
        **default.document(),
        "selectionDigest": default.selection_digest,
        "fallbackPolicy": "forbidden",
        "prepare": {"ready": True, "python": sys.executable},
        "preflight": {
            "provider": default.provider.value,
            "ready": True,
            "runtime": {"ready": True, "resolvedPython": sys.executable},
            "semanticAgentCredential": {},
            "network": {},
            "semanticAgentStartup": {},
            "issues": [],
        },
        "provider": default.provider.value,
        "semanticAgentCredential": {},
        "semanticAgentStartup": {
            "provider": default.provider.value,
            "checked": True,
            "ready": True,
            "runtime": default.runtime.value,
            "model": default.model_selection.model_id,
            "issues": [],
        },
        "capacitySoak": bind_semantic_preflight_selection(
            {
                "ready": True,
                "attempts": 8,
                "successCount": 8,
                "effectiveConcurrency": _requested_probe_attempts(),
                "bridgeDisconnectCount": 0,
                "issues": [],
            },
            default,
        ),
        "workspaceSmoke": {
            "ready": True,
            "workspaceCount": 2,
            "successCount": 2,
            "configuredConcurrency": 2,
            "effectiveConcurrency": 2,
            "cleanupStatus": "cleaned",
            "issues": [],
        },
        "startupRequested": True,
        "soakRequested": True,
        "workspaceSmokeRequested": True,
        "ready": True,
    }
    inconsistent_report = {
        **default_report,
        "preflight": {**default_report["preflight"], "ready": False},
    }
    with pytest.raises(ValueError, match="overall ready requires preflightReady"):
        build_semantic_preflight_receipt(
            selection=default,
            report=inconsistent_report,
        )
    diagnostic_failure_report = {
        **default_report,
        "capacitySoak": bind_semantic_preflight_selection(
            {
                "ready": False,
                "attempts": 8,
                "successCount": 1,
                "effectiveConcurrency": 1,
                "bridgeDisconnectCount": 1,
                "issues": ["diagnostic capacity probe observed failures"],
            },
            default,
        ),
        "workspaceSmoke": {
            **default_report["workspaceSmoke"],
            "ready": False,
            "successCount": 1,
            "effectiveConcurrency": 1,
            "issues": ["diagnostic workspace probe observed failures"],
        },
    }
    diagnostic_failure = build_semantic_preflight_receipt(
        selection=default,
        report=diagnostic_failure_report,
    )
    assert diagnostic_failure["ready"] is True
    assert diagnostic_failure["evidence"]["capacitySoak"]["ready"] is False
    assert diagnostic_failure["evidence"]["workspaceSmoke"]["ready"] is False
    validate_semantic_preflight_receipt(diagnostic_failure)
    skipped_startup = build_semantic_preflight_receipt(
        selection=default,
        report={
            **default_report,
            "semanticAgentStartup": {
                **default_report["semanticAgentStartup"],
                "checked": False,
                "ready": False,
            },
            "startupRequested": False,
        },
    )
    assert skipped_startup["ready"] is True
    validate_semantic_preflight_receipt(skipped_startup)
    conflicting = build_semantic_preflight_receipt(
        selection=default,
        report=default_report,
    )
    with pytest.raises(FileExistsError, match="create-once conflict"):
        write_semantic_preflight_receipt(destination, conflicting)


def test_runtime_child_command_preserves_semantic_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["cmd"] = cmd
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"provider": "cursor_sdk", "ready": True, "issues": []}),
            stderr="",
        )

    monkeypatch.setattr(preflight_handler.subprocess, "run", fake_run)
    python = tmp_path / "python"
    python.touch()
    report = preflight_handler._preflight_in_python(_args(tmp_path), python)

    command = observed["cmd"]
    selector_index = command.index("--semantic-selection-id")
    assert command[selector_index + 1] == "cursor_auto"
    assert report["provider"] == "cursor_sdk"
    assert report["ready"] is False
    assert "omitted governed semantic identity" in report["issues"][0]


def test_runtime_child_scrubs_cursor_secrets_from_environment_and_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    secrets = {
        name: f"opaque-secret-{index}"
        for index, name in enumerate(
            sorted(CURSOR_SENSITIVE_PROCESS_ENV_KEYS), start=1
        )
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("QWQ_CURSOR_API_KEY_FILE", str(tmp_path / "missing-key"))
    observed: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        observed["env"] = kwargs["env"]
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout=json.dumps(
                {
                    "provider": "cursor_sdk",
                    "ready": False,
                    "issues": [" ".join(secrets.values())],
                }
            ),
            stderr=" ".join(secrets.values()),
        )

    monkeypatch.setattr(preflight_handler.subprocess, "run", fake_run)
    python = tmp_path / "python"
    python.touch()

    report = preflight_handler._preflight_in_python(_args(tmp_path), python)

    child_environment = observed["env"]
    assert isinstance(child_environment, dict)
    assert not CURSOR_SENSITIVE_PROCESS_ENV_KEYS.intersection(child_environment)
    assert child_environment["QWQ_CURSOR_API_KEY_FILE"] == str(
        tmp_path / "missing-key"
    )
    serialized = json.dumps(report, ensure_ascii=False)
    assert all(secret not in serialized for secret in secrets.values())
    assert "<redacted-cursor-process-secret>" in serialized
