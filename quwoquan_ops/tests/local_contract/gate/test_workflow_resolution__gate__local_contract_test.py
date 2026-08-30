from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SPEC = "specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md"
MANIFEST = ".qwq_output/env/repo/runs/feature-tree/context-manifest.json"
EXPLICIT = ("explore", "prd", "design", "dev", "continue", "plan-next", "review", "commit")
AUTOMATIC = ("environment-ops", "content-production", "incident-inspection", "distill")


def regenerate_manifest() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "quwoquan_ops/cli/feature_tree.py"), "context", "--target", SPEC, "--format", "manifest"],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_workflow_resolution_gate_passes() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/workflow-resolution/spec.md#gwt-003.t1
    result = subprocess.run(
        [sys.executable, str(ROOT / "quwoquan_ops/gate/verify_workflow_resolution.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "real Cursor/Codex discovery remains OPEN" in result.stdout


@pytest.mark.parametrize("workflow", EXPLICIT)
def test_cursor_command_shell_invokes_neutral_adapter_before_skill_pre(workflow: str) -> None:
    text = (ROOT / f".cursor/commands/{workflow}.md").read_text(encoding="utf-8")
    assert "quwoquan_ops/cli/workflow_host_adapter.py" in text
    assert "--schema-version 1" in text
    assert "--adapter cursor-command-shell" in text
    assert f"--canonical-command /{workflow}" in text
    assert "--manifest-ref <repo-relative-manifest.json>" in text
    assert "--expected-target <target>" in text
    assert f".agents/skills/{workflow}/SKILL.md" in text
    assert "verification valid" in text
    assert text.index("workflow_host_adapter.py") < text.index(f".agents/skills/{workflow}/SKILL.md")


@pytest.mark.parametrize("workflow", ("continue", "plan-next", "review", "commit"))
def test_host_adapter_routes_control_workflow_and_exposes_verified_pre(workflow: str) -> None:
    for _ in range(3):
        regenerate_manifest()
        result = subprocess.run(
            [
                sys.executable, str(ROOT / "quwoquan_ops/cli/workflow_host_adapter.py"),
                "--schema-version", "1", "--host", "cursor", "--adapter", "cursor-command-shell",
                "--canonical-command", f"/{workflow}", "--manifest-ref", MANIFEST, "--expected-target", SPEC,
            ],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )
        if result.returncode == 0:
            break
    assert result.returncode == 0, result.stdout + result.stderr
    value = json.loads(result.stdout)
    assert value["result"] == "selected"
    assert value["selected_workflow"] == workflow
    assert value["skill_ref"] == f".agents/skills/{workflow}/SKILL.md"
    assert value["next_segment"] == "PRE"
    assert value["verification"]["result"] == "valid"
    assert value["receipt"]["authorization_effect"] == "none"


def test_four_automatic_workflows_do_not_invent_explicit_host_entries() -> None:
    contract = json.loads(subprocess.run(
        [sys.executable, str(ROOT / "quwoquan_ops/cli/workflow_resolver.py"), "contract-inspect"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    ).stdout)
    for workflow in AUTOMATIC:
        definition = contract["workflows"][workflow]
        assert definition["canonical_command"] == f"/{workflow}"
        assert definition["host_explicit_entry_available"] is False
        assert definition["automatic_only"] is True
        skill_text = (ROOT / definition["skill_ref"]).read_text(encoding="utf-8")
        frontmatter = skill_text.split("---", 2)[1]
        assert "command:" not in frontmatter
        assert not (ROOT / f".cursor/commands/{workflow}.md").exists()


def test_codex_repository_adapter_smoke_is_local_but_native_discovery_unproven() -> None:
    regenerate_manifest()
    result = subprocess.run(
        [
            sys.executable, str(ROOT / "quwoquan_ops/cli/workflow_host_adapter.py"),
            "--schema-version", "1", "--host", "codex", "--adapter", "codex-repository-adapter",
            "--canonical-command", "/review", "--manifest-ref", MANIFEST, "--expected-target", SPEC,
        ],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    value = json.loads(result.stdout)
    assert value["receipt"]["host_audit"] == {
        "claimed_host": "codex",
        "adapter": "codex-repository-adapter",
        "discovery_status": "unproven",
        "discovery_evidence_ref": None,
    }
