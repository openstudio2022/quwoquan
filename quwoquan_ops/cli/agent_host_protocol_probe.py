"""Validate saved, redacted Codex hook samples without inventing host evidence.

This probe is host-neutral: it never invokes Codex and never creates fixtures. A
sample may reach ``verified`` only when it carries the explicit live-host source
marker and satisfies the declared event hypothesis. Static declarations and
unsupported capabilities remain visible when no sample is supplied.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "quwoquan.agent-host-protocol-probe/v1"
LIVE_SOURCE_MARKER = "codex-live-host-capture/v1"
RECOVERY = "install/access Codex host and run explicit smoke command"
EXPLICIT_SMOKE_COMMAND = (
    "command -v codex && codex --version && "
    "python3 quwoquan_ops/cli/agent_host_protocol_probe.py validate "
    "--sample <redacted-live-sample.json>"
)
DOCUMENTATION = (
    "specs/feature-tree/runtime/development-workflow-governance/"
    "agent-skill-review-context-organization/spec.md#req-005"
)
CAPABILITY_MATRIX = (
    "specs/feature-tree/runtime/development-workflow-governance/"
    "agent-skill-review-context-organization/spec.md#open-001"
)
HOOKS_CONFIG = ".codex/hooks.json"
_ALLOWED_EVENTS = ("SessionStart", "PreToolUse", "PostToolUse")


def _host_available() -> tuple[bool, str | None]:
    try:
        completed = subprocess.run(
            ["codex", "--version"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return False, None
    version = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, version or None


def _declared_shape(event: str) -> dict[str, object]:
    if event == "PreToolUse":
        return {"input": "tool_input.command:string", "output": "hookSpecificOutput.additionalContext:string"}
    if event == "PostToolUse":
        return {"input": "unsupported", "output": "unsupported"}
    return {"input": "unknown", "output": "hookSpecificOutput.additionalContext:string (declared only)"}


def _validate_payload(event: str, payload: dict[str, Any]) -> tuple[bool, list[str]]:
    if event == "PreToolUse":
        if set(payload) != {"tool_input"}:
            return False, ["payload_must_be_minimal:tool_input"]
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict) or set(tool_input) != {"command"}:
            return False, ["tool_input_must_be_minimal:command"]
        if not isinstance(tool_input.get("command"), str) or not tool_input["command"]:
            return False, ["missing_non_empty_string:tool_input.command"]
        return True, []
    if event == "PostToolUse":
        if set(payload) != {"file_path"}:
            return False, ["payload_must_be_minimal:file_path"]
        if not isinstance(payload.get("file_path"), str) or not payload["file_path"]:
            return False, ["missing_non_empty_string:file_path"]
        return True, []
    return False, ["awaiting_live_sample"]


def _live_source_marker_valid(sample: dict[str, Any]) -> bool:
    source = sample.get("source")
    return isinstance(source, dict) and source == {
        "capture": "live",
        "host": "codex",
        "marker": LIVE_SOURCE_MARKER,
        "redacted": True,
    }


def _event_result(event: str, sample: dict[str, Any] | None) -> dict[str, object]:
    not_wired = event == "PostToolUse"
    base: dict[str, object] = {
        "event": event,
        "hypothesis": _declared_shape(event),
        "capability_status": "unsupported" if event in {"SessionStart", "PostToolUse"} else "declared",
        "reason": (
            "not_wired" if not_wired
            else "awaiting_live_sample" if event == "SessionStart"
            else "declared_hypothesis_only"
        ),
        "wired": False if not_wired else None,
        "sample_valid": None,
        "live_source_marker_valid": False,
    }
    if sample is None:
        return base
    if not_wired:
        base.update(
            capability_status="unsupported",
            reason="not_wired",
            sample_valid=False,
            validation_errors=["post_tool_use_not_wired"],
        )
        return base
    sample_event = sample.get("event")
    payload = sample.get("payload")
    if sample_event != event or not isinstance(payload, dict):
        base.update(
            capability_status="unsupported",
            reason="sample_envelope_invalid",
            sample_valid=False,
            validation_errors=["event_mismatch_or_payload_not_object"],
        )
        return base
    valid, errors = _validate_payload(event, payload)
    live_marker = _live_source_marker_valid(sample)
    base["sample_valid"] = valid
    base["live_source_marker_valid"] = live_marker
    if event == "SessionStart":
        base["validation_errors"] = errors
        return base
    if not valid:
        base.update(capability_status="unsupported", reason="sample_payload_invalid", validation_errors=errors)
    elif live_marker:
        base.update(capability_status="verified", reason="live_host_sample_validated")
    else:
        base.update(capability_status="declared", reason="sample_not_live_host_marked")
    return base


def _hook_locator_report() -> dict[str, object]:
    config_path = ROOT / HOOKS_CONFIG
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {"capability_status": "unsupported", "reason": f"hooks_config_unreadable:{error}"}
    commands: list[str] = []
    hooks = config.get("hooks") if isinstance(config, dict) else None
    if isinstance(hooks, dict):
        for entries in hooks.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                for hook in entry.get("hooks", []) if isinstance(entry, dict) else []:
                    command = hook.get("command") if isinstance(hook, dict) else None
                    if isinstance(command, str):
                        commands.append(command)
    depends_on_git = bool(commands) and all(
        "git rev-parse --show-toplevel" in command for command in commands
    )
    return {
        "capability_status": "declared" if depends_on_git else "unsupported",
        "command_count": len(commands),
        "all_commands_use_git_rev_parse": depends_on_git,
        "config": HOOKS_CONFIG,
    }


def _cwd_matrix() -> list[dict[str, str]]:
    recovery = (
        "replace git-rev-parse discovery with a host-supported config-root absolute or "
        "manifest-relative locator after live host rules are known; do not commit a machine-local path"
    )
    return [
        {
            "cwd": "repository_root",
            "capability_status": "declared",
            "reason": "git_rev_parse_expected_to_resolve",
        },
        {
            "cwd": "repository_child",
            "capability_status": "declared",
            "reason": "git_rev_parse_expected_to_resolve",
        },
        {
            "cwd": "outside_repository",
            "capability_status": "unsupported",
            "reason": "git_rev_parse_must_fail",
            "recovery": recovery,
        },
    ]


def build_report(sample: dict[str, Any] | None = None) -> dict[str, object]:
    available, version = _host_available()
    by_event: dict[str, dict[str, Any]] = {}
    if sample is not None:
        event = sample.get("event")
        if event not in _ALLOWED_EVENTS:
            raise ValueError("sample.event must be SessionStart, PreToolUse, or PostToolUse")
        by_event[str(event)] = sample
    capabilities = [_event_result(event, by_event.get(event)) for event in _ALLOWED_EVENTS]
    if not available:
        for capability in capabilities:
            if capability["capability_status"] == "verified":
                capability.update(capability_status="declared", reason="codex_cli_unavailable")
    return {
        "schema": SCHEMA,
        "host": {"name": "codex", "cli_available": available, "version": version},
        "source_marker_required_for_verified": {
            "capture": "live",
            "host": "codex",
            "marker": LIVE_SOURCE_MARKER,
            "redacted": True,
        },
        "capabilities": capabilities,
        "hook_locator": _hook_locator_report(),
        "cwd_resolution": _cwd_matrix(),
        "output_shape": {
            "additionalContext": {
                "capability_status": "declared",
                "reason": "awaiting_live_host_output_sample",
            },
            "post_tool_use": {
                "capability_status": "unsupported",
                "reason": "not_wired",
                "producer": "explicit_or_future_only",
            },
        },
        "hooks_config": HOOKS_CONFIG,
        "documentation": DOCUMENTATION,
        "capability_matrix": CAPABILITY_MATRIX,
        "recovery": RECOVERY,
        "host_precheck_command": "command -v codex && codex --version",
        "explicit_smoke_command": EXPLICIT_SMOKE_COMMAND,
        "limitations": [
            "static validation is not a real Codex host smoke",
            "SessionStart input payload is unknown",
            "PostToolUse edit readiness is not wired",
            "outside-repository hook cwd is unsupported by current git rev-parse commands",
            "natural-language and explicit skill discovery remain unverified",
        ],
    }


def _load_sample(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot read sample: {error}") from error
    if not isinstance(value, dict):
        raise TypeError("sample must be a JSON object")
    unknown = sorted(set(value) - {"event", "payload", "source"})
    if unknown:
        raise ValueError("sample contains unsupported envelope fields: " + ", ".join(unknown))
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("report", help="report declarations and unsupported capabilities")
    validate = subparsers.add_parser("validate", help="validate one saved redacted sample")
    validate.add_argument("--sample", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        sample = _load_sample(args.sample) if args.command == "validate" else None
        print(json.dumps(build_report(sample), ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (TypeError, ValueError) as error:
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "capability_status": "unsupported",
                    "reason": str(error),
                    "recovery": RECOVERY,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
