"""渐进 Agent 上下文门禁的负例合约。"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[4]
_GATE = _REPO_ROOT / "quwoquan_ops/gate/verify_agent_context_budget.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_agent_context_budget", _GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentContextBudgetGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_gate()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _use_fixture_root(self, *, git: bool = True) -> None:
        self.module.ROOT = self.root
        if git:
            subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def _write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _track(self, *rels: str) -> None:
        subprocess.run(["git", "add", "--", *rels], cwd=self.root, check=True)

    def _governance_contract(self, *, manifest_max_bytes: int = 8192) -> None:
        self._write(
            "quwoquan_ops/policies/agent_governance_contract.yaml",
            self.module.yaml.safe_dump(
                {
                    "schema_version": 1,
                    "feature_context_manifest": {
                        "schema_version": 1,
                        "max_bytes": manifest_max_bytes,
                        "required_fields": [
                            "schema_version",
                            "target",
                            "resolved_owner",
                            "owner_chain",
                            "canonical_contexts",
                            "applicable_agents",
                            "profiles",
                            "open_items",
                        ],
                        "owner_chain_fields": ["level", "node_id", "path"],
                        "context_fields": ["path", "anchor", "kind"],
                        "open_item_fields": [
                            "path",
                            "id",
                            "title",
                            "release_impact",
                        ],
                    },
                },
                sort_keys=False,
            ),
        )

    def _workflow(self, name: str, *, headings: tuple[str, ...] | None = None) -> None:
        headings = headings or self.module.REQUIRED_SKILL_SECTIONS
        command = f"  command: /{name}\n" if name in self.module.COMMAND_BOUND_WORKFLOWS else ""
        sections = "\n\n".join(f"## {heading}\n\n内容" for heading in headings)
        self._write(
            f".agents/skills/{name}/SKILL.md",
            "---\n"
            f"name: {name}\n"
            "description: d\n"
            "metadata:\n"
            "  kind: workflow\n"
            f"{command}"
            "---\n\n"
            f"# {name}\n\n{sections}\n",
        )

    def _checklist(self, text: str, *, role: str = "probe", workflow: str = "dev") -> str:
        rel = f"roles/{role}/checklists/{workflow}/base.md"
        self._write(f".agents/skills/review/references/{rel}", text)
        self._write(f".agents/skills/review/references/roles/{role}/ROLE.md", f"# {role}\n")
        return rel

    def _valid_registry(self) -> dict:
        self._write("Makefile", "verify-x:\n\t@true\n")
        checklist = self._checklist("# probe\n\n- [MUST] 要求\n\nevidence: proof\n")
        workflows: dict[str, dict] = {}
        for workflow in self.module.WORKFLOW_SKILLS:
            if workflow in self.module.CONTROL_WORKFLOWS_WITHOUT_AUTOMATIC_REVIEW:
                workflows[workflow] = {
                    "segments": ["PRE", "POST"],
                    "deliverable": "x",
                    "automatic_review": False,
                }
            else:
                workflows[workflow] = {
                    "segments": ["PRE", "POST"],
                    "deliverable": "x",
                    "primary": {
                        "role": "probe",
                        "required": True,
                        "checklist": checklist,
                    },
                }
        registry = {
            "schema_version": 2,
            "limits": {
                "max_parallel": 2,
                "max_role_invocations": 4,
                "per_role_timeout_minutes": 10,
                "reviewer_context_bytes": 24 * 1024,
            },
            "evidence": {
                "proof": {
                    "command": "make verify-x",
                    "segment": "POST",
                    "required": True,
                    "covers": [],
                }
            },
            "profiles": {},
            "workflows": workflows,
        }
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, allow_unicode=True, sort_keys=False),
        )
        return registry

    def test_real_repository_passes_every_check(self) -> None:
        for label, check in self.module.CHECKS:
            with self.subTest(check=label):
                self.assertEqual([], check(), f"{label} 在真实仓库上应为绿")

    def test_detects_agents_chain_over_16_kib(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t1
        self._use_fixture_root()
        self._write("AGENTS.md", "a" * 9000)
        self._write("nested/AGENTS.md", "b" * 9000)
        self._track("AGENTS.md", "nested/AGENTS.md")
        issues = self.module.check_agents_budget()
        self.assertTrue(any("超过 16384 bytes" in issue for issue in issues), issues)

    def test_accepts_agents_chain_at_budget(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t1
        self._use_fixture_root()
        self._write("AGENTS.md", "a" * 8000)
        self._write("nested/AGENTS.md", "b" * 8000)
        self._track("AGENTS.md", "nested/AGENTS.md")
        self.assertEqual([], self.module.check_agents_budget())

    def test_detects_untracked_third_party_agents(self) -> None:
        self._use_fixture_root()
        self._write("vendor/AGENTS.md", "third party")
        issues = self.module.check_agents_budget()
        self.assertTrue(any("非第一方" in issue for issue in issues), issues)

    def test_git_index_failure_is_not_silently_accepted(self) -> None:
        self._use_fixture_root(git=False)
        self._write("AGENTS.md", "root")
        issues = self.module.check_agents_budget()
        self.assertTrue(any("不可执行" in issue for issue in issues), issues)

    def test_dependency_caches_are_pruned_from_agents_scan(self) -> None:
        self._use_fixture_root()
        for name in self.module.PRUNED_DIR_NAMES:
            self._write(f"{name}/AGENTS.md", "cache")
        self.assertEqual([], self.module.check_agents_budget())

    def test_detects_manifest_budget_constant_drift(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t1
        self._use_fixture_root()
        self._governance_contract(manifest_max_bytes=9 * 1024)
        self._write("quwoquan_ops/cli/lib/feature_tree/commands.py", "# fixture\n")
        self._write(
            "quwoquan_ops/cli/lib/feature_tree/cli_entry.py",
            'parser.add_argument("--format", default="manifest")\n',
        )
        issues = self.module.check_manifest_budget()
        self.assertTrue(any("必须精确为 8192" in issue for issue in issues), issues)

    def test_detects_expanded_as_default_context_format(self) -> None:
        self._use_fixture_root()
        self._governance_contract()
        self._write("quwoquan_ops/cli/lib/feature_tree/commands.py", "# fixture\n")
        self._write(
            "quwoquan_ops/cli/lib/feature_tree/cli_entry.py",
            'parser.add_argument("--format", default="expanded")\n',
        )
        issues = self.module.check_manifest_budget()
        self.assertTrue(any("默认值必须是 manifest" in issue for issue in issues), issues)

    def test_manifest_budget_checks_every_feature_node(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t1
        nodes = [object(), object(), object(), object()]
        self.assertEqual(nodes, self.module._manifest_budget_nodes(nodes))

    def test_detects_reviewer_context_over_24_kib(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t1
        self._use_fixture_root()
        registry = self._valid_registry()
        self._write("AGENTS.md", "root")
        self._write(".agents/skills/review/references/reviewer-executor.md", "executor")
        self._write(".agents/skills/review/references/grading.md", "grading")
        self._write(".agents/skills/review/references/roles/probe/ROLE.md", "r" * 25000)
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, allow_unicode=True, sort_keys=False),
        )
        issues = self.module.check_reviewer_context_budget()
        self.assertTrue(any("超过 24576 bytes" in issue for issue in issues), issues)

    def test_workflow_requires_exact_five_sections(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        (self.root / ".agents/skills").mkdir(parents=True)
        self._workflow("dev", headings=("触发与输入", "执行", "HANDOFF"))
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("二级段落必须且只能" in issue for issue in issues), issues)

    def test_workflow_rejects_legacy_extra_sections(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        (self.root / ".agents/skills").mkdir(parents=True)
        headings = (*self.module.REQUIRED_SKILL_SECTIONS, "内置评审")
        self._workflow("dev", headings=headings)
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("二级段落必须且只能" in issue for issue in issues), issues)

    def test_workflow_rejects_shared_completion_jump(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        (self.root / ".agents/skills").mkdir(parents=True)
        self._workflow("dev")
        path = self.root / ".agents/skills/dev/SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + "completion-criteria.md\n", encoding="utf-8")
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("不得跳转共享文档" in issue for issue in issues), issues)

    def test_detects_cursor_rule_as_normative_carrier(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        self._write(".cursor/rules/pageflip.mdc", "---\nalwaysApply: false\n---\n规则\n")
        issues = self.module.check_required_sources_and_carriers()
        self.assertTrue(any("Cursor rule 不得承载规范" in issue for issue in issues), issues)

    def test_detects_role_reference_as_normative_carrier(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        self._write(
            ".agents/skills/review/references/roles/ux/references/geometry.md",
            "功能事实",
        )
        issues = self.module.check_required_sources_and_carriers()
        self.assertTrue(any("role references" in issue for issue in issues), issues)

    def test_detects_shared_completion_or_interaction_carrier(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        self._write(".agents/skills/review/references/completion-criteria.md", "第二真相源")
        issues = self.module.check_required_sources_and_carriers()
        self.assertTrue(any("退役载体" in issue for issue in issues), issues)

    def test_detects_claude_active_entry(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-005.t2
        self._use_fixture_root()
        self._write("CLAUDE.md", "@AGENTS.md")
        issues = self.module.check_required_sources_and_carriers()
        self.assertTrue(any("CLAUDE.md" in issue for issue in issues), issues)

    def test_detects_claude_directory_even_if_only_symlink(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-005.t2
        self._use_fixture_root()
        self._write(".agents/skills/dev/SKILL.md", "truth")
        (self.root / ".claude").symlink_to(self.root / ".agents")
        issues = self.module.check_required_sources_and_carriers()
        self.assertTrue(any(".claude" in issue for issue in issues), issues)

    def test_detects_old_codex_only_generator(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-005.t2
        self._use_fixture_root()
        self._write("quwoquan_ops/tools/generate_codex_agents.py", "old")
        issues = self.module.check_required_sources_and_carriers()
        self.assertTrue(any("generate_codex_agents.py" in issue for issue in issues), issues)

    def test_adapter_check_failure_is_visible(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-005.t1
        self._use_fixture_root()
        self._write(
            "quwoquan_ops/tools/generate_agent_adapters.py",
            "import sys\nprint('drift', file=sys.stderr)\nraise SystemExit(1)\n",
        )
        issues = self.module.check_adapter_generation()
        self.assertTrue(any("drift" in issue for issue in issues), issues)

    def test_adapter_silent_nonzero_exit_is_visible(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-005.t1
        self._use_fixture_root()
        self._write(
            "quwoquan_ops/tools/generate_agent_adapters.py",
            "raise SystemExit(7)\n",
        )
        issues = self.module.check_adapter_generation()
        self.assertTrue(any("静默退出 7" in issue for issue in issues), issues)

    def test_missing_adapter_generator_is_visible(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-005.t1
        self._use_fixture_root()
        issues = self.module.check_adapter_generation()
        self.assertTrue(any("缺中性 adapter 生成器" in issue for issue in issues), issues)

    def test_valid_registry_v2_passes(self) -> None:
        self._use_fixture_root()
        self._valid_registry()
        self.assertEqual([], self.module.check_checklists_and_registry())

    def test_registry_requires_v2_limits(self) -> None:
        self._use_fixture_root()
        registry = self._valid_registry()
        registry["limits"]["max_parallel"] = 4
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, sort_keys=False),
        )
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("max_parallel 必须为 2" in issue for issue in issues), issues)

    def test_registry_evidence_requires_covers(self) -> None:
        self._use_fixture_root()
        registry = self._valid_registry()
        del registry["evidence"]["proof"]["covers"]
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, sort_keys=False),
        )
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("evidence.proof 缺 covers" in issue for issue in issues), issues)

    def test_registry_rejects_v1_binding_keys(self) -> None:
        self._use_fixture_root()
        registry = self._valid_registry()
        registry["concurrency"] = {"max_parallel": 4}
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, sort_keys=False),
        )
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("v1 concurrency/bindings" in issue for issue in issues), issues)

    def test_explore_cannot_gain_automatic_primary(self) -> None:
        self._use_fixture_root()
        registry = self._valid_registry()
        registry["workflows"]["explore"]["primary"] = {
            "role": "probe",
            "required": True,
            "checklist": "roles/probe/checklists/dev/base.md",
        }
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, sort_keys=False),
        )
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("explore 必须默认零 Reviewer" in issue for issue in issues), issues)

    def test_delivery_workflow_cannot_disable_automatic_review(self) -> None:
        self._use_fixture_root()
        registry = self._valid_registry()
        registry["workflows"]["dev"] = {
            "segments": ["PRE", "POST"],
            "deliverable": "x",
            "automatic_review": False,
        }
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, sort_keys=False),
        )
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("dev 不是控制型 workflow" in issue for issue in issues), issues)

    def test_stale_profile_path_is_rejected(self) -> None:
        self._use_fixture_root()
        registry = self._valid_registry()
        registry["profiles"]["ghost"] = {
            "paths": ["does/not/exist/**"],
            "specialist": {
                "role": "probe",
                "priority": 1,
                "required": False,
                "checklists": {"dev": "roles/probe/checklists/dev/base.md"},
            },
        }
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, sort_keys=False),
        )
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("永不命中" in issue for issue in issues), issues)

    def test_checklist_rejects_gate_command(self) -> None:
        self._use_fixture_root()
        self._valid_registry()
        self._checklist("# probe\n\n- [MUST] 要求\n\ngate: make verify-x\n")
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("checklist 禁止 gate:" in issue for issue in issues), issues)

    def test_checklist_requires_binding_for_must(self) -> None:
        self._use_fixture_root()
        self._valid_registry()
        self._checklist("# probe\n\n- [MUST] 没有绑定\n")
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("未绑定本条 evidence 或客观 check" in issue for issue in issues), issues)

    def test_checklist_accepts_each_item_named_evidence_binding(self) -> None:
        self._use_fixture_root()
        self._valid_registry()
        self._checklist(
            "# probe\n\n"
            "- [MUST] 要求一\n  evidence: proof\n"
            "- [MUST NOT] 要求二\n  evidence: proof\n"
        )
        self.assertEqual([], self.module.check_checklists_and_registry())

    def test_checklist_rejects_mixed_bound_and_unbound_must_items(self) -> None:
        self._use_fixture_root()
        self._valid_registry()
        self._checklist(
            "# probe\n\n"
            "- [MUST] 已绑定\n  evidence: proof\n"
            "- [MUST NOT] 未绑定\n"
        )
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("MUST NOT" in issue and "未绑定本条" in issue for issue in issues), issues)

    def test_checklist_rejects_unknown_evidence(self) -> None:
        self._use_fixture_root()
        self._valid_registry()
        self._checklist("# probe\n\n- [MUST] 要求\n\nevidence: missing\n")
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("未注册 evidence" in issue for issue in issues), issues)

    def test_check_predicate_must_state_failure_condition(self) -> None:
        self._use_fixture_root()
        self._valid_registry()
        self._checklist("# probe\n\n- [MUST] 要求\n\ncheck: 看起来合理\n")
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("判失败" in issue for issue in issues), issues)

    def test_unregistered_checklist_is_not_an_inventory_error(self) -> None:
        self._use_fixture_root()
        self._valid_registry()
        self._checklist(
            "# spare\n\n- [MUST] 要求\n\nevidence: proof\n",
            role="spare",
            workflow="design",
        )
        issues = self.module.check_checklists_and_registry()
        self.assertFalse(any("未被 registry" in issue for issue in issues), issues)

    def test_command_shell_must_be_thin_and_point_to_skill(self) -> None:
        self._use_fixture_root()
        self._write(
            ".cursor/commands/dev.md",
            "---\nname: /dev\ndescription: d\n---\n\n" + "正文\n" * 15,
        )
        issues = self.module.check_commands_and_harness_stubs()
        self.assertTrue(any("命令薄壳预算" in issue for issue in issues), issues)
        self.assertTrue(any("未指向 .agents/skills/dev/SKILL.md" in issue for issue in issues), issues)

    def test_harness_skill_stub_must_point_to_neutral_skill(self) -> None:
        self._use_fixture_root()
        self._write(
            ".codex/skills/probe/SKILL.md",
            "---\nname: probe\ndescription: d\n---\n\n自带规范。\n",
        )
        issues = self.module.check_commands_and_harness_stubs()
        self.assertTrue(any("未指向 .agents/skills" in issue for issue in issues), issues)

    def test_broken_relative_link_is_rejected(self) -> None:
        self._use_fixture_root()
        self._write("AGENTS.md", "见 [gone](missing.md)\n")
        issues = self.module.check_references_and_duplicates()
        self.assertTrue(any("相对链接断链" in issue for issue in issues), issues)

    def test_long_duplicate_skill_paragraph_is_rejected(self) -> None:
        self._use_fixture_root()
        paragraph = "这是只允许一个 owner 的规范正文。" * 30
        self._write(".agents/skills/a/SKILL.md", paragraph)
        self._write(".agents/skills/b/SKILL.md", paragraph)
        issues = self.module.check_references_and_duplicates()
        self.assertTrue(any("长规范段落" in issue for issue in issues), issues)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
