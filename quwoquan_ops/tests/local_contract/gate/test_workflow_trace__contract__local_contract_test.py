from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops/cli/workflow_trace.py"
SPEC = importlib.util.spec_from_file_location("workflow_trace_contract", MODULE_PATH)
assert SPEC and SPEC.loader
workflow_trace = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workflow_trace
SPEC.loader.exec_module(workflow_trace)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def fixture_repo(tmp_path: Path, *, skill_count: int = 12, command_count: int = 8) -> Path:
    root = tmp_path / "repo"
    for index in range(skill_count):
        skill = f"skill-{index:02d}"
        write(root / ".agents/skills" / skill / "SKILL.md", f"---\nname: {skill}\n---\n# {skill}\n")
        if index < command_count:
            write(
                root / ".cursor/commands" / f"{skill}.md",
                f"加载并按 `.agents/skills/{skill}/SKILL.md` 执行。\n",
            )
    write(root / "quwoquan_ops/policies/workflow_trace_contract.yaml", "schema_version: 1\n")
    return root


def test_real_inventory_has_twelve_skills_and_eight_cursor_entries() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-008.t1
    matrix = workflow_trace.capability_matrix(repo_root=ROOT, generated_at="2026-09-03T00:00:00Z")
    assert matrix["summary"] == {
        "skill_count": 12,
        "cursor_explicit_entry_count": 8,
        "codex_explicit_entry_count": 0,
        "verified_count": 0,
    }
    assert len(matrix["skill_inventory"]) == 12
    cursor = matrix["hosts"]["cursor"]
    assert sum(row["explicit_entry_status"] == "declared" for row in cursor) == 8
    assert sum(row["explicit_entry_status"] == "unsupported" for row in cursor) == 4
    assert all(row["skill_discovery_status"] == "declared" for row in cursor)
    codex = matrix["hosts"]["codex"]
    assert all(row["explicit_entry_status"] == "unsupported" for row in codex)
    assert all(row["skill_discovery_status"] == "declared" for row in codex)
    assert not any(row["verified"] for row in cursor + codex)


def test_natural_language_cannot_be_recorded_as_verified(tmp_path: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-008.t2
    repo = fixture_repo(tmp_path)
    output = tmp_path / "trace-output"
    result = workflow_trace.start_trace(
        repo_root=repo,
        output_root=output,
        entry_kind="natural_language",
        host="cursor",
        selected_skill="skill-00",
        capability_status="verified",
        actual_host_sample_ref="opaque:real-host-sample",
        started_at="2026-09-03T00:00:00Z",
    )
    assert result["schema_id"] == workflow_trace.ADVISORY_SCHEMA_ID
    assert result["code"] == "WORKFLOW_TRACE_START_FAILED"
    assert result["blocking"] is False
    assert not output.exists()


def test_start_finish_readback_and_opaque_refs(tmp_path: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-008.t3
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-008.t7
    repo = fixture_repo(tmp_path)
    output = tmp_path / "trace-output"
    started = workflow_trace.start_trace(
        repo_root=repo,
        output_root=output,
        entry_kind="cursor_command",
        host="cursor",
        selected_skill="skill-00",
        capability_status="declared",
        owner_identity_ref="opaque:owner-ref",
        started_at="2026-09-03T00:00:00Z",
    )
    assert started["status"] == "recorded"
    finished = workflow_trace.finish_trace(
        output_root=output,
        start_ref=started["ref"],
        terminal="PASS",
        capability_status="verified",
        candidate_evidence_ref="opaque:candidate-ref",
        actual_host_sample_ref="opaque:cursor-live-sample",
        explicit_command_evidence_ref="opaque:cursor-command-sample",
        finished_at="2026-09-03T00:01:00Z",
    )
    assert finished["status"] == "recorded"
    readback = workflow_trace.readback_trace(output_root=output, ref=finished["ref"])
    assert readback["status"] == "valid"
    assert readback["trace"]["start_ref"] == started["ref"]
    assert readback["start"]["owner_identity_ref"] == "opaque:owner-ref"
    assert readback["trace"]["candidate_evidence_ref"] == "opaque:candidate-ref"


def test_tamper_and_second_finish_are_fail_open_advisories(tmp_path: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-008.t4
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-008.t6
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-008.t8
    repo = fixture_repo(tmp_path)
    output = tmp_path / "trace-output"
    started = workflow_trace.start_trace(
        repo_root=repo,
        output_root=output,
        entry_kind="host_event",
        host="codex",
        selected_skill="skill-00",
        capability_status="declared",
        started_at="2026-09-03T00:00:00Z",
    )
    first = workflow_trace.finish_trace(
        output_root=output,
        start_ref=started["ref"],
        terminal="PASS",
        capability_status="declared",
        finished_at="2026-09-03T00:01:00Z",
    )
    second = workflow_trace.finish_trace(
        output_root=output,
        start_ref=started["ref"],
        terminal="FAILED",
        capability_status="unsupported",
        finished_at="2026-09-03T00:02:00Z",
    )
    assert first["status"] == "recorded"
    assert second["code"] == "WORKFLOW_TRACE_FINISH_FAILED"
    assert second["blocking"] is False

    trace_path = workflow_trace._path_for_ref(output, started["ref"])
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    payload["host"] = "unknown"
    trace_path.write_text(json.dumps(payload), encoding="utf-8")
    tampered = workflow_trace.readback_trace(output_root=output, ref=started["ref"])
    assert tampered["code"] == "WORKFLOW_TRACE_READBACK_FAILED"
    assert tampered["blocking"] is False


def test_trace_write_failure_returns_typed_advisory(tmp_path: Path) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-008.t5
    repo = fixture_repo(tmp_path)
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("occupied", encoding="utf-8")
    result = workflow_trace.start_trace(
        repo_root=repo,
        output_root=blocked,
        entry_kind="skill_explicit",
        host="unknown",
        selected_skill="skill-00",
        capability_status="declared",
        started_at="2026-09-03T00:00:00Z",
    )
    assert result == {
        "schema_id": workflow_trace.ADVISORY_SCHEMA_ID,
        "schema_version": 1,
        "code": "WORKFLOW_TRACE_START_FAILED",
        "operation": "start",
        "detail": f"unsafe trace output directory: {blocked}",
        "retryable": True,
        "blocking": False,
    }
