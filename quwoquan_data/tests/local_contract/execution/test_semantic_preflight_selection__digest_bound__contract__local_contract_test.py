from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from content.execution.preflight import handler as preflight_handler
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
from core.runtime_policy import active_runtime_policy


def _cursor_required_concurrency() -> int:
    """cursor_auto 的容量契约是主机级 bridge 数，跟随 runtime policy 而非常量。"""
    return active_runtime_policy().cursor_bridge_instances


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
        "workspace_smoke": False,
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
        "reliableTaskFleet": {
            "checked": True,
            "ready": True,
            "target": "beta-local",
            "mongo": True,
            "redis": True,
            "owned": True,
            "issues": [],
        },
        "ready": True,
        "issues": [],
    }


def test_selector_resolves_default_sol_and_cursor_auto_without_fallback() -> None:
    default = resolve_semantic_preflight_selection("default")
    calibration = resolve_semantic_preflight_selection(
        CALIBRATION_SEMANTIC_SELECTION_ID
    )
    cursor = resolve_semantic_preflight_selection("cursor_auto")

    assert default.provider is AgentProvider.CODEX_SDK
    assert default.model_selection.model_id == "gpt-5.6-terra"
    assert default.requires_new_retry_of is False
    assert calibration.provider is AgentProvider.CODEX_SDK
    assert calibration.model_selection.model_id == "gpt-5.6-sol"
    assert calibration.requires_new_retry_of is False
    assert cursor.provider is AgentProvider.CURSOR_SDK
    assert cursor.model_selection.model_id == "auto"
    assert cursor.requires_new_retry_of is True
    assert len(
        {
            default.selection_digest,
            calibration.selection_digest,
            cursor.selection_digest,
        }
    ) == 3
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
            "effectiveConcurrency": _cursor_required_concurrency(),
            "bridgeDisconnectCount": 0,
            "issues": [],
            "ready": True,
        }

    monkeypatch.setattr(preflight_handler, "semantic_agent_probe_suite", fake_soak)

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
    assert receipt["capacitySoakReady"] is True
    assert receipt["executionAdmissionReady"] is True
    validate_semantic_preflight_receipt(
        receipt,
        expected_selection=resolve_semantic_preflight_selection("cursor_auto"),
        require_execution_admission=True,
    )
    with pytest.raises(ValueError, match="outside its validity window"):
        validate_semantic_preflight_receipt(
            receipt,
            require_execution_admission=True,
            now=datetime.now(timezone.utc) + timedelta(hours=1),
        )


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
            "effectiveConcurrency": 4,
            "bridgeDisconnectCount": 0,
            "issues": [],
            "ready": True,
        },
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
        require_execution_admission=True,
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
            "effectiveConcurrency": _cursor_required_concurrency(),
            "bridgeDisconnectCount": 0,
            "issues": [],
            "ready": True,
        },
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
                "reliableTaskFleet": {
                    "checked": True,
                    "ready": True,
                    "target": "beta-local",
                    "mongo": True,
                    "redis": True,
                    "owned": True,
                    "issues": [],
                },
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
                "effectiveConcurrency": 4,
                "bridgeDisconnectCount": 0,
                "issues": [],
            },
            default,
        ),
        "workspaceSmoke": {},
        "startupRequested": True,
        "soakRequested": True,
        "workspaceSmokeRequested": False,
        "ready": True,
    }
    unwritable_fleet_report = {
        **default_report,
        "preflight": {
            **default_report["preflight"],
            "reliableTaskFleet": {
                **default_report["preflight"]["reliableTaskFleet"],
                "ready": False,
                "redis": False,
            },
        },
    }
    with pytest.raises(ValueError, match="requires writable ReliableTask fleet"):
        build_semantic_preflight_receipt(
            selection=default,
            report=unwritable_fleet_report,
        )
    unowned_fleet_report = {
        **default_report,
        "preflight": {
            **default_report["preflight"],
            "reliableTaskFleet": {
                **default_report["preflight"]["reliableTaskFleet"],
                "owned": False,
            },
        },
    }
    with pytest.raises(ValueError, match="requires writable ReliableTask fleet"):
        build_semantic_preflight_receipt(
            selection=default,
            report=unowned_fleet_report,
        )
    inconsistent_report = {
        **default_report,
        "preflight": {**default_report["preflight"], "ready": False},
    }
    with pytest.raises(ValueError, match="overall ready requires preflightReady"):
        build_semantic_preflight_receipt(
            selection=default,
            report=inconsistent_report,
        )
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
