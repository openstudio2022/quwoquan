"""Codex protocol declarations must not impersonate real-host evidence.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#open-001
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
PROBE = ROOT / "quwoquan_ops/cli/agent_host_protocol_probe.py"
HOOKS = ROOT / ".codex/hooks.json"
AFTER_EDIT = ROOT / "quwoquan_ops/hooks/local_readiness_after_edit.py"
SPEC = (
    "specs/feature-tree/runtime/development-workflow-governance/"
    "agent-skill-review-context-organization/spec.md#open-001"
)


def _load_probe():
    spec = importlib.util.spec_from_file_location("agent_host_protocol_probe", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _by_event(report: dict[str, object]) -> dict[str, dict[str, object]]:
    return {item["event"]: item for item in report["capabilities"]}


def test_report_is_honest_when_codex_cli_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _load_probe()
    monkeypatch.setattr(probe, "_host_available", lambda: (False, None))

    report = probe.build_report()
    capabilities = _by_event(report)
    assert report["host"] == {"name": "codex", "cli_available": False, "version": None}
    assert {item["capability_status"] for item in capabilities.values()} == {
        "declared",
        "unsupported",
    }
    assert capabilities["SessionStart"]["capability_status"] == "unsupported"
    assert capabilities["SessionStart"]["reason"] == "awaiting_live_sample"
    assert capabilities["PreToolUse"]["hypothesis"]["input"] == "tool_input.command:string"
    assert capabilities["PostToolUse"]["capability_status"] == "unsupported"
    assert capabilities["PostToolUse"]["reason"] == "not_wired"
    assert capabilities["PostToolUse"]["wired"] is False
    assert capabilities["PostToolUse"]["hypothesis"] == {
        "input": "unsupported", "output": "unsupported"
    }
    assert report["output_shape"]["additionalContext"]["capability_status"] == "declared"
    assert report["output_shape"]["post_tool_use"] == {
        "capability_status": "unsupported",
        "reason": "not_wired",
        "producer": "explicit_or_future_only",
    }
    assert report["recovery"] == "install/access Codex host and run explicit smoke command"
    assert report["documentation"].endswith("spec.md#req-005")
    assert report["capability_matrix"] == SPEC
    assert report["host_precheck_command"] == "command -v codex && codex --version"
    assert report["explicit_smoke_command"].startswith(
        "command -v codex && codex --version && python3 "
    )
    assert "verified" not in {item["capability_status"] for item in capabilities.values()}


def test_unmarked_saved_sample_can_only_validate_declared_hypothesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _load_probe()
    monkeypatch.setattr(probe, "_host_available", lambda: (False, None))
    sample = {"event": "PreToolUse", "payload": {"tool_input": {"command": "git status"}}}

    capability = _by_event(probe.build_report(sample))["PreToolUse"]
    assert capability["sample_valid"] is True
    assert capability["live_source_marker_valid"] is False
    assert capability["capability_status"] == "declared"
    assert capability["reason"] == "sample_not_live_host_marked"


def test_post_tool_use_stays_unsupported_when_not_wired(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _load_probe()
    monkeypatch.setattr(probe, "_host_available", lambda: (False, None))
    sample = {
        "event": "PostToolUse",
        "payload": {"file_path": "README.md"},
        "source": {
            "capture": "live",
            "host": "codex",
            "marker": probe.LIVE_SOURCE_MARKER,
            "redacted": True,
        },
    }

    capability = _by_event(probe.build_report(sample))["PostToolUse"]
    assert capability["sample_valid"] is False
    assert capability["live_source_marker_valid"] is False
    assert capability["capability_status"] == "unsupported"
    assert capability["reason"] == "not_wired"
    assert capability["validation_errors"] == ["post_tool_use_not_wired"]



def test_session_start_stays_unsupported_even_with_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    probe = _load_probe()
    monkeypatch.setattr(probe, "_host_available", lambda: (True, "codex test-host"))
    sample = {
        "event": "SessionStart",
        "payload": {},
        "source": {
            "capture": "live",
            "host": "codex",
            "marker": probe.LIVE_SOURCE_MARKER,
            "redacted": True,
        },
    }

    capability = _by_event(probe.build_report(sample))["SessionStart"]
    assert capability["capability_status"] == "unsupported"
    assert capability["reason"] == "awaiting_live_sample"
    assert capability["validation_errors"] == ["awaiting_live_sample"]


@pytest.mark.parametrize(
    "sample",
    [
        {"event": "PreToolUse", "payload": {"command": "git status"}},
        {"event": "PreToolUse", "payload": {"tool_input": {"command": "git status", "other": 1}}},
        {"event": "PostToolUse", "payload": {"tool_input": {"file_path": "README.md"}}},
        {"event": "PostToolUse", "payload": {"file_path": "README.md", "cursor_field": True}},
    ],
)
def test_payload_validation_requires_minimal_codex_hypothesis(
    monkeypatch: pytest.MonkeyPatch, sample: dict[str, object]
) -> None:
    probe = _load_probe()
    monkeypatch.setattr(probe, "_host_available", lambda: (True, "codex test-host"))

    capability = _by_event(probe.build_report(sample))[sample["event"]]
    assert capability["sample_valid"] is False
    assert capability["capability_status"] == "unsupported"


def test_current_cwd_locator_and_unwired_after_edit_script_are_explicit(tmp_path: Path) -> None:
    probe = _load_probe()
    report = probe.build_report()
    cwd_matrix = {item["cwd"]: item for item in report["cwd_resolution"]}
    hooks = json.loads(HOOKS.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for entries in hooks["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    ]

    assert commands and all("git rev-parse --show-toplevel" in command for command in commands)
    for workdir in (ROOT, ROOT / "quwoquan_ops"):
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=workdir,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0
        assert Path(completed.stdout.strip()).resolve() == ROOT
    outside = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert outside.returncode != 0

    assert report["hook_locator"]["all_commands_use_git_rev_parse"] is True
    assert cwd_matrix["repository_root"]["capability_status"] == "declared"
    assert cwd_matrix["repository_child"]["capability_status"] == "declared"
    assert cwd_matrix["outside_repository"]["capability_status"] == "unsupported"
    assert "config-root absolute or manifest-relative" in cwd_matrix["outside_repository"]["recovery"]
    assert "machine-local path" in cwd_matrix["outside_repository"]["recovery"]

    source = AFTER_EDIT.read_text(encoding="utf-8")
    assert 'for key in ("file_path", "filePath", "path", "file")' in source
    assert '"additional_context"' in source
    assert "PostToolUse" not in hooks["hooks"]
    assert "local_readiness_after_edit.py" not in json.dumps(hooks)
    assert report["output_shape"]["post_tool_use"]["capability_status"] == "unsupported"
    assert report["output_shape"]["post_tool_use"]["reason"] == "not_wired"


def test_cli_rejects_nonminimal_envelope_with_stable_recovery(tmp_path: Path) -> None:
    sample = tmp_path / "sample.json"
    sample.write_text(
        json.dumps(
            {
                "event": "PreToolUse",
                "payload": {"tool_input": {"command": "git status"}},
                "invented_provenance": "fixture",
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(PROBE), "validate", "--sample", str(sample)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )

    assert completed.returncode == 2
    output = json.loads(completed.stdout)
    assert output["capability_status"] == "unsupported"
    assert output["recovery"] == "install/access Codex host and run explicit smoke command"


def test_cli_validates_unmarked_saved_sample_without_upgrading(tmp_path: Path) -> None:
    sample = tmp_path / "sample.json"
    sample.write_text(
        json.dumps(
            {
                "event": "PreToolUse",
                "payload": {"tool_input": {"command": "git status"}},
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, str(PROBE), "validate", "--sample", str(sample)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": "", "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )

    assert completed.returncode == 0
    output = json.loads(completed.stdout)
    assert output["host"]["cli_available"] is False
    capability = _by_event(output)["PreToolUse"]
    assert capability["sample_valid"] is True
    assert capability["capability_status"] == "declared"
    assert all(
        item["capability_status"] in {"declared", "unsupported"}
        for item in output["capabilities"]
    )
