from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops" / "cli" / "feature_tree.py"
SPEC = importlib.util.spec_from_file_location("feature_tree_manifest", MODULE_PATH)
assert SPEC and SPEC.loader
feature_tree = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = feature_tree
SPEC.loader.exec_module(feature_tree)

from quwoquan_ops.cli.lib.feature_tree import commands as ft_commands  # noqa: E402
from quwoquan_ops.cli.lib.feature_tree import context as ft_context  # noqa: E402
from quwoquan_ops.cli.lib.feature_tree import gitio as ft_gitio  # noqa: E402
from quwoquan_ops.cli.lib.evidence_fingerprint import (  # noqa: E402
    validate_evidence_fingerprint,
)
from quwoquan_ops.cli.lib.feature_context_fingerprint import (  # noqa: E402
    validate_content_addressed_ref,
    validate_current_feature_context_fingerprint,
)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    tree = root / "specs" / "feature-tree"
    write(tree / "spec.md", "# AppRoot Spec：演示\n")
    write(tree / "design.md", "# AppRoot Design：演示\n")
    write(tree / "domain" / "spec.md", "# L1 Domain Service：领域 (`domain`)\n")
    write(tree / "domain" / "design.md", "# L1 Design：领域 (`domain`)\n")
    write(
        tree / "domain" / "capability" / "spec.md",
        "# L2 Business Capability：能力 (`capability`)\n",
    )
    write(
        tree / "domain" / "capability" / "story" / "spec.md",
        "# L3 Story：故事 (`story`)\n",
    )
    return root


def test_l2_dec_owner_manifest_is_shared_by_pageflip_code_and_projected_test(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    write(root / "AGENTS.md", "# root agent\n")
    write(root / "quwoquan_app/AGENTS.md", "# app agent\n")
    code_path = root / "quwoquan_app/lib/design_system/pageflip/geometry.dart"
    test_path = (
        root
        / "quwoquan_app/test/local_contract/design_system/pageflip/"
        "geometry__local_contract_test.dart"
    )
    write(code_path, "class Geometry {}\n")
    write(test_path, "void main() {}\n")
    write(
        root
        / "quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml",
        "enable_pageflip: true\n",
    )
    write(
        root
        / "quwoquan_service/services/content-service/contracts/content/post/operations.yaml",
        "GetUnrelated: {}\n",
    )
    (tree / "domain/spec.md").write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- App：`quwoquan_app/lib/design_system/pageflip`\n",
        encoding="utf-8",
    )
    write(
        tree / "domain/capability/design.md",
        "# L2 Design：能力 (`capability`)\n\n"
        '<a id="dec-002"></a>\n'
        "### DEC-002 pageflip 唯一 owner\n\n"
        "- 适用工程根：`quwoquan_app/lib/design_system/pageflip`\n"
        "- 影响 Story：[`story`](./story/spec.md)\n"
        "- 关联要求：`REQ-003`\n"
        "- 关联验收：`GWT-003`\n",
    )
    write(
        tree / "domain/capability/story/spec.md",
        "# L3 Story：故事 (`story`)\n\n"
        '<a id="req-003"></a>\n'
        "### REQ-003 pageflip 主路径\n\n"
        "- 行为。\n"
        "- canonical：`quwoquan_service/services/content-service/contracts/"
        "content/post/ui_config.yaml#enable_pageflip`\n\n"
        '<a id="gwt-003"></a>\n'
        "### GWT-003 pageflip 验收\n\n"
        "- GIVEN 已进入阅读器。\n"
        "- WHEN 用户翻页。\n"
        "- THEN 路径落到唯一 Story。\n\n"
        '<a id="req-004"></a>\n'
        "### REQ-004 未选要求\n\n"
        "- canonical：`quwoquan_service/services/content-service/contracts/"
        "content/post/operations.yaml#GetUnrelated`\n",
    )
    write(
        root / ".agents/skills/review/references/registry.yaml",
        "profiles:\n"
        "  dart-app:\n"
        "    paths: [quwoquan_app/lib/**, quwoquan_app/test/**]\n"
        "  pageflip:\n"
        "    paths: [quwoquan_app/lib/design_system/pageflip/**]\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(ft_gitio, "git_changed_paths", list)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    write(root / "quwoquan_ops/cli/lib/feature_tree/commands.py", "# fixture generator\n")
    write(root / "quwoquan_ops/policies/agent_governance_contract.yaml", "schema_version: 1\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )
    monkeypatch.setattr(
        ft_context, "OUTPUT_ROOT",
        root / ".qwq_output/env/repo/runs/feature-tree",
    )
    nodes = feature_tree.discover_nodes()

    code_owner = feature_tree.resolve_target(code_path, nodes)
    test_owner = feature_tree.resolve_target(test_path, nodes)
    exit_code = feature_tree.command_context(
        argparse.Namespace(target=str(test_path), format="manifest")
    )

    assert exit_code == 0
    assert code_owner == test_owner
    assert test_owner.node_id == "story"
    ref = capsys.readouterr().out.strip()
    manifest = json.loads((root / ref).read_bytes())
    assert manifest["resolved_owner"].endswith("/capability/story/spec.md")
    assert manifest["applicable_agents"] == ["AGENTS.md", "quwoquan_app/AGENTS.md"]
    assert "profiles" not in manifest
    assert {
        (item["kind"], item["anchor"])
        for item in manifest["canonical_contexts"]
        if item["anchor"]
    } == {
        ("decision", "dec-002"),
        ("requirement", "req-003"),
        ("acceptance", "gwt-003"),
        ("contract", "enable_pageflip"),
    }
    receipt = validate_evidence_fingerprint(
        manifest["evidence_fingerprint"]["receipt"]
    )
    assert receipt["captured_by"] == "feature_tree"
    assert len((root / ref).read_bytes()) <= 8192

    first_digest = receipt["digest"]
    code_path.write_text("class Geometry { int changed = 1; }\n", encoding="utf-8")
    assert feature_tree.command_context(
        argparse.Namespace(target=str(code_path), format="manifest")
    ) == 0
    changed_ref = capsys.readouterr().out.strip()
    changed_manifest = json.loads((root / changed_ref).read_bytes())
    assert (
        changed_manifest["evidence_fingerprint"]["digest"] != first_digest
    )

    legacy = dict(changed_manifest)
    legacy["schema_version"] = 1
    contract_module = sys.modules[ft_commands.declared_object.__module__]
    with pytest.raises(ValueError, match="schema_version"):
        contract_module.validate_feature_context_manifest(legacy)

    contract_module = sys.modules[ft_commands.declared_object.__module__]
    original_declared_fields = contract_module.declared_fields

    def drift(section: str, declaration: str) -> tuple[str, ...]:
        fields = original_declared_fields(section, declaration)
        if section == "feature_context_manifest" and declaration == "context_fields":
            return (*fields, "new_context_field")
        return fields

    monkeypatch.setattr(contract_module, "declared_fields", drift)
    assert (
        feature_tree.command_context(
            argparse.Namespace(target=str(test_path), format="manifest")
        )
        == 2
    )


def test_selected_dec_direct_refs_include_canonical_contracts_and_feature_specs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    code_path = root / "quwoquan_ops/cli/lib/objective_execution/executor.py"
    write(code_path, "# objective executor\n")
    write(
        root / "quwoquan_ops/policies/objective_execution_contract.yaml",
        "schema_id: objective-execution-contract\n",
    )
    write(
        root / "quwoquan_ops/policies/hotl_admission_contract.yaml",
        "schema_id: hotl-admission-contract\n",
    )
    write(
        root / "quwoquan_ops/policies/branch_policy.yaml",
        "integration_branch: dev1.0\n",
    )
    write(
        tree / "domain/capability/related/spec.md",
        "# L3 Story：关联 (`related`)\n",
    )
    write(
        tree / "domain/capability/design.md",
        "# L2 Design：能力 (`capability`)\n\n"
        '<a id="dec-009"></a>\n'
        "### DEC-009 Objective direct refs\n\n"
        "- 决策：直接消费 `quwoquan_ops/policies/objective_execution_contract.yaml`、"
        "`quwoquan_ops/policies/hotl_admission_contract.yaml`、`branch_policy.yaml` "
        "与关联 L3 [`related`](./related/spec.md)，并保留 repo-relative "
        "`specs/feature-tree/domain/capability/story/spec.md#req-003`。\n"
        "- 适用工程根：`quwoquan_ops/cli/lib/objective_execution`\n"
        "- 影响 Story：[`story`](./story/spec.md)\n"
        "- 关联要求：`REQ-003`\n"
        "- 关联验收：`GWT-003`\n\n"
        '<a id="dec-010"></a>\n'
        "### DEC-010 Unselected refs\n\n"
        "- 决策：不应加载 `specs/feature-tree/domain/capability/unselected/spec.md`。\n",
    )
    write(
        tree / "domain/capability/story/spec.md",
        "# L3 Story：故事 (`story`)\n\n"
        '<a id="req-003"></a>\n'
        "### REQ-003 Objective context\n\n- 行为。\n\n"
        '<a id="gwt-003"></a>\n'
        "### GWT-003 Objective context\n\n"
        "- GIVEN 已选中 Objective DEC。\n"
        "- WHEN 生成 manifest。\n"
        "- THEN 直达 canonical context。\n",
    )
    (tree / "domain/spec.md").write_text(
        "# L1 Domain Service：领域 (`domain`)\n\n"
        "## 7. 工程归属\n\n"
        "- Ops：`quwoquan_ops`\n",
        encoding="utf-8",
    )
    write(
        root / ".agents/skills/review/references/registry.yaml",
        "profiles: {}\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(ft_gitio, "git_changed_paths", list)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    write(root / "quwoquan_ops/cli/lib/feature_tree/commands.py", "# fixture generator\n")
    write(root / "quwoquan_ops/policies/agent_governance_contract.yaml", "schema_version: 1\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-qm", "fixture",
        ],
        cwd=root,
        check=True,
    )
    outputs: dict[str, str] = {}

    def capture_output(name: str, content: str) -> Path:
        outputs[name] = content
        return root / name

    monkeypatch.setattr(ft_commands, "write_output", capture_output)
    monkeypatch.setattr(
        ft_commands,
        "_write_content_addressed_bytes",
        lambda content, **_: capture_output(
            "captured-manifest.json", content.decode("utf-8")
        ),
    )
    assert feature_tree.command_context(
        argparse.Namespace(target=str(code_path), format="manifest")
    ) == 0
    manifest = json.loads(outputs["captured-manifest.json"])
    contexts = {
        (item["kind"], item["path"], item["anchor"])
        for item in manifest["canonical_contexts"]
    }
    assert (
        "contract", "quwoquan_ops/policies/objective_execution_contract.yaml", None,
    ) in contexts
    assert (
        "contract", "quwoquan_ops/policies/hotl_admission_contract.yaml", None,
    ) in contexts
    assert (
        "contract", "quwoquan_ops/policies/branch_policy.yaml", None,
    ) in contexts
    assert (
        "spec", "specs/feature-tree/domain/capability/related/spec.md", None,
    ) in contexts
    assert (
        "spec", "specs/feature-tree/domain/capability/story/spec.md", "req-003",
    ) in contexts
    assert not any("unselected" in item[1] for item in contexts)
    assert len((outputs["captured-manifest.json"] + "\n").encode("utf-8")) <= 8192


def test_service_contract_directory_direct_ref_is_preserved_as_one_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    contract_directory = (
        root
        / "quwoquan_service/services/user-service/contracts/"
        "persona_management/profile_update_proposal"
    )
    write(contract_directory / "fields.yaml", "fields: {}\n")
    write(contract_directory / "operations.yaml", "operations: {}\n")
    write(
        tree / "domain/capability/spec.md",
        "# L2 Business Capability：能力 (`capability`)\n\n"
        "## 契约依赖\n\n"
        "- Contracts：`quwoquan_service/services/user-service/contracts/"
        "persona_management/profile_update_proposal`\n",
    )
    write(
        root / ".agents/skills/review/references/registry.yaml",
        "profiles: {}\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(ft_gitio, "git_changed_paths", list)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-qm", "fixture",
        ],
        cwd=root,
        check=True,
    )
    outputs: dict[str, str] = {}

    def capture_output(name: str, content: str) -> Path:
        outputs[name] = content
        return root / name

    monkeypatch.setattr(ft_commands, "write_output", capture_output)
    monkeypatch.setattr(
        ft_commands,
        "_write_content_addressed_bytes",
        lambda content, **_: capture_output(
            "captured-manifest.json", content.decode("utf-8")
        ),
    )
    assert feature_tree.command_context(
        argparse.Namespace(
            target="specs/feature-tree/domain/capability/spec.md",
            format="manifest",
        )
    ) == 0
    manifest = json.loads(outputs["captured-manifest.json"])
    contract_contexts = [
        item
        for item in manifest["canonical_contexts"]
        if item["kind"] == "contract"
    ]
    assert contract_contexts == [
        {
            "path": (
                "quwoquan_service/services/user-service/contracts/"
                "persona_management/profile_update_proposal"
            ),
            "anchor": None,
            "kind": "contract",
        }
    ]
    assert ft_commands._direct_canonical_references(
        tree / "domain/capability/spec.md",
        "`quwoquan_service/services/user-service/contracts/` "
        "`quwoquan_service/services/user-service/contracts/"
        "persona_management/profile_update_proposal/**`",
    ) == {
        (
            "quwoquan_service/services/user-service/contracts",
            None,
            "contract",
        ),
        (
            "quwoquan_service/services/user-service/contracts/"
            "persona_management/profile_update_proposal",
            None,
            "contract",
        ),
    }
    metadata_root = root / "quwoquan_service/contracts/metadata/_shared"
    write(metadata_root / "app_routes.yaml", "routes: {}\n")
    write(metadata_root / "ui_surfaces.yaml", "surfaces: {}\n")
    assert ft_commands._direct_canonical_references(
        tree / "domain/capability/spec.md",
        "`quwoquan_service/contracts/metadata/_shared/"
        "{app_routes,ui_surfaces}.yaml`",
    ) == {
        (
            "quwoquan_service/contracts/metadata/_shared/app_routes.yaml",
            None,
            "contract",
        ),
        (
            "quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml",
            None,
            "contract",
        ),
    }


def test_missing_service_contract_directory_direct_ref_is_gate_block(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    source = root / "specs/feature-tree/domain/capability/spec.md"
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    with pytest.raises(ValueError, match="canonical 直接引用不存在"):
        ft_commands._direct_canonical_references(
            source,
            "`quwoquan_service/services/user-service/contracts/"
            "persona_management/missing_contract_directory`",
        )



def test_direct_spec_does_not_expand_sibling_design_refs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    write(root / "quwoquan_ops/policies/design_only.yaml", "value: true\n")
    write(
        tree / "domain/capability/spec.md",
        "# L2 Business Capability：能力 (`capability`)\n",
    )
    write(
        tree / "domain/capability/design.md",
        "# L2 Design：能力 (`capability`)\n\n"
        "- `quwoquan_ops/policies/design_only.yaml`\n",
    )
    write(
        root / ".agents/skills/review/references/registry.yaml",
        "profiles: {}\n",
    )
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(ft_gitio, "git_changed_paths", list)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=Fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-qm", "fixture",
        ],
        cwd=root,
        check=True,
    )
    outputs: dict[str, str] = {}

    def capture_output(name: str, content: str) -> Path:
        outputs[name] = content
        return root / name

    monkeypatch.setattr(ft_commands, "write_output", capture_output)
    monkeypatch.setattr(
        ft_commands,
        "_write_content_addressed_bytes",
        lambda content, **_: capture_output(
            "captured-manifest.json", content.decode("utf-8")
        ),
    )
    assert feature_tree.command_context(
        argparse.Namespace(
            target="specs/feature-tree/domain/capability/spec.md",
            format="manifest",
        )
    ) == 0
    manifest = json.loads(outputs["captured-manifest.json"])
    assert not any(
        item["path"].endswith("design_only.yaml")
        for item in manifest["canonical_contexts"]
    )



def test_missing_bare_policy_basename_is_typed_gate_block_without_manifest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    write(
        tree / "domain/capability/spec.md",
        "# L2 Business Capability：能力 (`capability`)\n",
    )
    write(
        tree / "domain/capability/design.md",
        "# L2 Design：能力 (`capability`)\n\n"
        "- canonical policy：`renamed_or_missing_policy.yaml`\n",
    )
    write(
        root / ".agents/skills/review/references/registry.yaml",
        "profiles: {}\n",
    )
    write(root / "docs/ordinary.yaml", "value: true\n")
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(ft_gitio, "git_changed_paths", list)
    writes: list[str] = []

    def capture_output(name: str, content: str) -> Path:
        writes.append(name)
        return root / name

    monkeypatch.setattr(ft_commands, "write_output", capture_output)
    monkeypatch.setattr(
        ft_commands,
        "_write_content_addressed_bytes",
        lambda content, **_: capture_output(
            "captured-manifest.json", content.decode("utf-8")
        ),
    )
    assert feature_tree.command_context(
        argparse.Namespace(
            target="specs/feature-tree/domain/capability/design.md",
            format="manifest",
        )
    ) == 2
    captured = capsys.readouterr()
    assert "GATE_BLOCK:" in captured.err
    assert "renamed_or_missing_policy.yaml" in captured.err
    assert "quwoquan_ops/policies/renamed_or_missing_policy.yaml" in captured.err
    assert "by-fingerprint" not in captured.out
    assert writes == []
    assert ft_commands._direct_canonical_references(
        tree / "domain/capability/spec.md",
        "`docs/ordinary.yaml`",
    ) == set()



def test_development_workflow_l2_manifest_reaches_objective_hotl_specs_and_contracts(
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    outputs: dict[str, str] = {}

    def capture_output(name: str, content: str) -> Path:
        outputs[name] = content
        return ROOT / ".qwq_output/env/repo/runs/feature-tree" / name

    monkeypatch.setattr(ft_commands, "write_output", capture_output)
    monkeypatch.setattr(
        ft_commands,
        "_write_content_addressed_bytes",
        lambda content, **_: capture_output(
            "captured-manifest.json", content.decode("utf-8")
        ),
    )
    target = (
        ROOT
        / "specs/feature-tree/runtime/development-workflow-governance/design.md"
    )
    assert feature_tree.command_context(
        argparse.Namespace(target=str(target), format="manifest")
    ) == 0
    manifest = json.loads(outputs["captured-manifest.json"])
    contexts = {
        (item["kind"], item["path"], item["anchor"])
        for item in manifest["canonical_contexts"]
    }
    expected_stories = {
        "directory-native-sdd",
        "agent-skill-review-context-organization",
        "human-agent-delivery-interaction",
        "objective-execution",
        "hotl-expansion-control",
    }
    assert {
        (
            "spec",
            "specs/feature-tree/runtime/development-workflow-governance/"
            f"{story}/spec.md",
            None,
        )
        for story in expected_stories
    } <= contexts
    assert {
        (
            "contract",
            f"quwoquan_ops/policies/{contract}",
            None,
        )
        for contract in {
            "branch_policy.yaml",
            "agent_governance_contract.yaml",
            "human_agent_delivery_contract.yaml",
            "objective_execution_contract.yaml",
            "hotl_admission_contract.yaml",
        }
    } <= contexts
    assert len((outputs["captured-manifest.json"] + "\n").encode("utf-8")) <= 8192



def test_runtime_l1_compact_manifest_preserves_owner_and_fingerprint_semantics(
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t1
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    outputs: dict[str, str] = {}

    def capture_output(name: str, content: str) -> Path:
        outputs[name] = content
        return ROOT / ".qwq_output/env/repo/runs/feature-tree" / name

    monkeypatch.setattr(ft_commands, "write_output", capture_output)
    monkeypatch.setattr(
        ft_commands,
        "_write_content_addressed_bytes",
        lambda content, **_: capture_output(
            "captured-manifest.json", content.decode("utf-8")
        ),
    )
    target = "specs/feature-tree/runtime/spec.md"
    assert feature_tree.command_context(
        argparse.Namespace(target=target, format="manifest")
    ) == 0

    raw_manifest = outputs["captured-manifest.json"]
    manifest = json.loads(raw_manifest)
    assert "\n" not in raw_manifest
    assert len((raw_manifest + "\n").encode("utf-8")) <= 8192
    assert manifest["resolved_owner"] == target
    assert manifest["owner_chain"][-1]["path"] == target
    receipt = validate_current_feature_context_fingerprint(manifest, repo_root=ROOT)
    assert receipt["ref"] == manifest["evidence_fingerprint"]["ref"]
    assert receipt["digest"] == manifest["evidence_fingerprint"]["digest"]

    nodes = feature_tree.discover_nodes()
    direct = ft_commands._context_manifest(
        target,
        feature_tree.resolve_target_details(target, nodes),
        nodes,
    )
    assert {
        key: value for key, value in direct.items() if key != "evidence_fingerprint"
    } == {
        key: value for key, value in manifest.items() if key != "evidence_fingerprint"
    }
    assert (
        direct["evidence_fingerprint"]["digest"]
        == manifest["evidence_fingerprint"]["digest"]
    )

    assert feature_tree.command_context(
        argparse.Namespace(target=target, format="expanded")
    ) == 0
    assert f"- 归属节点：`{target}`" in outputs["context.md"]


def test_contract_detection_has_no_static_policy_allowlist() -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    source = Path(ft_commands.__file__).read_text(encoding="utf-8")
    assert "CANONICAL_CONTRACT_PATHS" not in source
    assert "path in CANONICAL_CONTRACT_PATHS" not in source


def test_explicit_spec_ref_validates_canonical_path_without_context_expansion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    source = root / "specs/feature-tree/domain/capability/story/spec.md"
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")
    canonical_ref = "specs/feature-tree/domain/capability/story/spec.md#gwt-001"

    assert ft_commands._direct_canonical_references(
        source,
        f"绑定 `spec_ref: {canonical_ref}`。",
    ) == set()


@pytest.mark.parametrize(
    ("reference", "error"),
    [
        ("../../../../../spec.md#gwt-001", "越出仓库"),
        ("../../../../docs/spec.md#gwt-001", "不属于 canonical"),
    ],
)
def test_spec_like_direct_reference_traversal_and_out_of_boundary_fail_closed(
    tmp_path: Path,
    monkeypatch,
    reference: str,
    error: str,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t2
    root = build_tree(tmp_path)
    source = root / "specs/feature-tree/domain/capability/design.md"
    write(root / "docs/spec.md", "# 非 canonical spec\n")
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    with pytest.raises(ValueError, match=error):
        ft_commands._direct_canonical_references(
            source,
            f"绑定 `spec_ref: {reference}`。",
        )


def test_canonical_direct_reference_fail_closed_for_invalid_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    source = root / "specs/feature-tree/domain/capability/design.md"
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", root / "specs/feature-tree")

    with pytest.raises(ValueError, match="canonical 直接引用不存在"):
        ft_commands._direct_canonical_references(
            source,
            "[missing](./missing/spec.md)",
        )
    with pytest.raises(ValueError, match="越出仓库"):
        ft_commands._direct_canonical_references(
            source,
            "[outside](../../../../../spec.md)",
        )
    write(root / "docs/spec.md", "# 非 canonical spec\n")
    with pytest.raises(ValueError, match="不属于 canonical"):
        ft_commands._direct_canonical_references(
            source,
            "[wrong](../../../../docs/spec.md)",
        )
    write(root / "quwoquan_ops/policies/gates/baseline.json", "{}\n")
    write(root / "quwoquan_service/services/user-service/internal/object/marker", "x\n")
    write(root / "quwoquan_service/contracts/metadata/_shared/marker.yaml", "x: 1\n")
    assert ft_commands._direct_canonical_references(
        source,
        "`quwoquan_ops/policies/gates/baseline.json` "
        "`quwoquan_service/services/user-service/internal/object` "
        "`quwoquan_service/contracts/metadata/_shared` "
        "`quwoquan_service/services/*/contracts`",
    ) == set()


def test_review_registry_missing_or_malformed_does_not_block_feature_context(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
    root = build_tree(tmp_path)
    tree = root / "specs/feature-tree"
    write(root / ".agents/skills/review/references/registry.yaml", "- invalid\n")
    monkeypatch.setattr(ft_context, "REPO_ROOT", root)
    monkeypatch.setattr(ft_context, "TREE_ROOT", tree)
    monkeypatch.setattr(
        ft_context, "OUTPUT_ROOT",
        root / ".qwq_output/env/repo/runs/feature-tree",
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    write(root / "quwoquan_ops/cli/lib/feature_tree/commands.py", "# fixture generator\n")
    write(root / "quwoquan_ops/policies/agent_governance_contract.yaml", "schema_version: 1\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-qm", "fixture"],
        cwd=root, check=True,
    )

    assert feature_tree.command_context(
        argparse.Namespace(target="specs/feature-tree/spec.md", format="manifest")
    ) == 0
    ref = capsys.readouterr().out.strip()
    assert re.fullmatch(
        r"\.qwq_output/env/repo/runs/feature-tree/by-fingerprint/[0-9a-f]{64}\.json",
        ref,
    )
    raw = (root / ref).read_bytes()
    validate_content_addressed_ref(ref, raw_bytes=raw, repo_root=root)
    assert "profiles" not in json.loads(raw)



def test_large_manifest_uses_verifiable_receipt_reference(
    tmp_path: Path, monkeypatch
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t1
    receipt = {
        "schema_version": 2,
        "serialization_version": "evidence-fingerprint-v1",
        "ref": "evidence-fingerprint-v1:sha256:" + "a" * 64,
        "digest": "sha256:" + "a" * 64,
        "digest_payload": {},
        "captured_at": "2026-08-29T00:00:00Z",
        "captured_by": "fixture",
        "captured_metadata": {},
    }
    manifest = {
        "schema_version": 3,
        "target": "x" * 7000,
        "resolved_owner": "specs/feature-tree/spec.md",
        "owner_chain": [],
        "canonical_contexts": [],
        "applicable_agents": [],
        "open_items": [],
        "evidence_fingerprint": ft_commands.embedded_fingerprint_binding(
            validate_evidence_fingerprint(
                ft_commands.build_feature_context_fingerprint(
                    {
                        "schema_version": 3,
                        "target": "README.md",
                        "resolved_owner": "specs/feature-tree/spec.md",
                        "owner_chain": [],
                        "canonical_contexts": [],
                        "applicable_agents": ["AGENTS.md"],
                                        "open_items": [],
                    },
                    repo_root=ROOT,
                )
            )
        ),
    }
    embedded_size = len(
        (ft_commands._serialize_context_manifest(manifest) + "\n").encode("utf-8")
    )
    assert embedded_size > 8192
    canonical_receipt = manifest["evidence_fingerprint"]["receipt"]
    manifest["evidence_fingerprint"] = ft_commands.referenced_fingerprint_binding(
        canonical_receipt,
        receipt_ref=(
            ".qwq_output/env/repo/runs/feature-tree/by-fingerprint/receipts/"
            + hashlib.sha256(
                ft_commands.canonical_json_bytes(canonical_receipt)
            ).hexdigest()
            + ".json"
        ),
    )
    assert len(
        (ft_commands._serialize_context_manifest(manifest) + "\n").encode("utf-8")
    ) <= 8192

def test_manifest_over_budget_after_receipt_compaction_fails_closed(
    monkeypatch,
    capsys,
) -> None:
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t1
    receipt = validate_evidence_fingerprint(
        ft_commands.build_feature_context_fingerprint(
            {
                "schema_version": 3,
                "target": "README.md",
                "resolved_owner": "specs/feature-tree/spec.md",
                "owner_chain": [],
                "canonical_contexts": [],
                "applicable_agents": ["AGENTS.md"],
                        "open_items": [],
            },
            repo_root=ROOT,
        )
    )
    manifest = {
        "schema_version": 3,
        "target": "x" * 9000,
        "resolved_owner": "specs/feature-tree/spec.md",
        "owner_chain": [],
        "canonical_contexts": [],
        "applicable_agents": [],
        "open_items": [],
        "evidence_fingerprint": ft_commands.embedded_fingerprint_binding(receipt),
    }
    writes: list[str] = []

    monkeypatch.setattr(ft_commands, "discover_nodes", list)
    monkeypatch.setattr(ft_commands, "resolve_target_details", lambda *_: object())
    monkeypatch.setattr(ft_commands, "_context_manifest", lambda *_: manifest)
    monkeypatch.setattr(
        ft_commands,
        "write_output",
        lambda name, content: writes.append(name) or ROOT / name,
    )
    monkeypatch.setattr(
        ft_commands,
        "_write_content_addressed_bytes",
        lambda content, **_: writes.append("content-addressed-manifest")
        or ROOT / "content-addressed-manifest",
    )

    assert feature_tree.command_context(
        argparse.Namespace(target="fixture", format="manifest")
    ) == 2
    assert "feature context manifest 超出 8KiB 预算" in capsys.readouterr().err
    assert writes == []
