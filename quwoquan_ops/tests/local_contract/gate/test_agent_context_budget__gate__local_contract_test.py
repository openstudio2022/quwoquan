"""渐进 Agent 上下文门禁的负例合约。"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

_REPO_ROOT = Path(__file__).resolve().parents[4]
_GATE = _REPO_ROOT / "quwoquan_ops/gate/verify_agent_context_budget.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_agent_context_budget", _GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentContextBudgetPlacementTest(unittest.TestCase):
    def test_slow_verifier_is_governance_manual_only(self) -> None:
        commit_gate = (_REPO_ROOT / "quwoquan_ops/gate/commit_gate.sh").read_text(encoding="utf-8")
        repo_gate = (_REPO_ROOT / "quwoquan_ops/gate/gate_repo.sh").read_text(encoding="utf-8")
        makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        registry = (_REPO_ROOT / ".agents/skills/review/references/registry.yaml").read_text(encoding="utf-8")
        governance = (_REPO_ROOT / ".github/workflows/domain-governance.yml").read_text(encoding="utf-8")
        for ordinary in (commit_gate, repo_gate, registry):
            self.assertNotIn("verify-agent-context-budget", ordinary)
            self.assertNotIn("verify_agent_context_budget.py", ordinary)
        self.assertNotIn("$(MAKE) verify-agent-context-budget", makefile[makefile.index("gate:"):makefile.index("verify:")])
        self.assertIn("make verify-agent-context-budget", governance)

    def test_data_shard_selector_never_selects_ops_context_budget_test(self) -> None:
        selector = (_REPO_ROOT / "quwoquan_ops/gate/delivery_gate_data_shard.py").read_text(encoding="utf-8")
        self.assertIn('TEST_ROOT_PARTS = ("quwoquan_data", "tests", "local_contract")', selector)
        self.assertNotIn("verify_agent_context_budget", selector)


class AgentContextBudgetGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_gate()
        self.workflow_names = self.module._workflow_skills()
        self.command_names = self.module._command_bound_workflows()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _use_fixture_root(self, *, git: bool = True) -> None:
        self.module.ROOT = self.root
        for workflow in self.workflow_names:
            if not (self.root / f".agents/skills/{workflow}/SKILL.md").is_file():
                self._workflow(workflow)
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
                        "schema_version": 3,
                        "max_bytes": manifest_max_bytes,
                        "required_fields": [
                            "schema_version",
                            "target",
                            "resolved_owner",
                            "owner_chain",
                            "canonical_contexts",
                            "applicable_agents",
                            "open_items",
                            "evidence_fingerprint",
                        ],
                        "owner_chain_fields": ["level", "node_id", "path"],
                        "context_fields": ["path", "anchor", "kind"],
                        "open_item_fields": [
                            "path",
                            "id",
                            "title",
                            "release_impact",
                        ],
                        "fingerprint_field": "evidence_fingerprint",
                        "fingerprint_binding_fields": [
                            "mode",
                            "ref",
                            "digest",
                            "receipt",
                            "receipt_ref",
                        ],
                        "fingerprint_binding_modes": ["embedded", "referenced"],
                    },
                },
                sort_keys=False,
            ),
        )

    def _workflow_text(
        self,
        name: str,
        *,
        headings: tuple[str, ...] | None = None,
        frontmatter: str | None = None,
    ) -> str:
        headings = headings or self.module.REQUIRED_SKILL_SECTIONS
        command = f"  command: /{name}\n" if name in self.command_names else ""
        sections = "\n\n".join(f"## {heading}\n\n内容" for heading in headings)
        frontmatter = frontmatter or (
            f"name: {name}\n"
            "description: d\n"
            "metadata:\n"
            "  kind: workflow\n"
            f"{command}"
        )
        return "---\n" + frontmatter + "---\n\n" + f"# {name}\n\n{sections}\n"

    def _workflow(self, name: str, *, headings: tuple[str, ...] | None = None) -> None:
        self._write(
            f".agents/skills/{name}/SKILL.md",
            self._workflow_text(name, headings=headings),
        )

    def _checklist(self, text: str, *, role: str = "probe", workflow: str = "dev") -> str:
        rel = f"roles/{role}/checklists/{workflow}/base.md"
        self._write(f".agents/skills/review/references/{rel}", text)
        self._write(f".agents/skills/review/references/roles/{role}/ROLE.md", f"# {role}\n")
        return rel

    def _valid_registry(self) -> dict:
        for workflow in self.workflow_names:
            if not (self.root / f".agents/skills/{workflow}/SKILL.md").is_file():
                self._workflow(workflow)
        self._write("Makefile", "verify-x:\n\t@true\n")
        checklist = self._checklist("# probe\n\n- [MUST] 要求\n\nevidence: proof\n")
        workflows: dict[str, dict] = {}
        for workflow in self.workflow_names:
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
                    "baseline_evidence": "proof",
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
                "max_evidence_timeout_seconds": 3600,
                "reviewer_context_bytes": 24 * 1024,
            },
            "evidence": {
                "proof": {
                    "command": "make verify-x",
                    "segment": "POST",
                    "required": True,
                    "timeout_seconds": 300,
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

    def test_real_repository_scope_checks_pass(self) -> None:
        scoped = {
            "默认 manifest 预算", "Workflow Skill 五段", "命令与 harness 薄壳",
            "Review registry/checklist", "Reviewer 上下文预算",
            "引用与重复规范", "两宿主 adapter",
        }
        for label, check in self.module.CHECKS:
            if label not in scoped:
                continue
            with self.subTest(check=label):
                self.assertEqual([], check(), f"{label} 在真实仓库上应为绿")

    def test_hotl_runtime_matrix_covers_all_scenarios_within_budget(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-001.t2
        self.assertEqual([], self.module.check_hotl_runtime_matrix())

    def test_hotl_runtime_matrix_rejects_missing_scenario_and_oversize(self) -> None:
        self.module.ROOT = self.root
        path = self._write(
            self.module.HOTL_RUNTIME_MATRIX_PATH,
            self.module.HOTL_RUNTIME_MATRIX_START
            + "\n| SKILL:commit |\n"
            + ("x" * (self.module.HOTL_RUNTIME_MATRIX_MAX_BYTES + 1))
            + "\n"
            + self.module.HOTL_RUNTIME_MATRIX_END,
        )
        self.assertTrue(path.is_file())
        issues = self.module.check_hotl_runtime_matrix()
        self.assertTrue(any("超过" in issue for issue in issues), issues)
        self.assertTrue(any("SKILL:review" in issue for issue in issues), issues)
        self.assertTrue(any("BOUNDARY:release" in issue for issue in issues), issues)
        self.assertTrue(any("完整固定列头" in issue for issue in issues), issues)

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

    def test_delivery_skills_bind_exact_owner_manifest_and_read_only_terminal(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
        expected = {
            "content-production": "content-release",
            "environment-ops": "release-evidence",
            "incident-inspection": "inspection-report",
        }
        for workflow, deliverable in expected.items():
            with self.subTest(workflow=workflow):
                text = (
                    _REPO_ROOT / f".agents/skills/{workflow}/SKILL.md"
                ).read_text(encoding="utf-8")
                self.assertIn(f"`{deliverable}`", text)
                self.assertIn("make feature-context TARGET=<exact-path>", text)
                self.assertIn("content-addressed immutable owner manifest exact ref", text)
                self.assertIn("PRE owner identity ref", text)
                self.assertIn("`--owner-identity`", text)
                self.assertIn("`--candidate-evidence`", text)
                self.assertIn("no-review-deliverable", text)
                self.assertNotIn("纯环境操作不要求 Feature owner manifest", text)

    def test_mutation_skills_require_unique_owner_before_writing(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t3
        expectations = {
            "prd": ("target、owner", "`GATE_BLOCK`"),
            "design": ("target/owner", "`GATE_BLOCK`"),
            "dev": ("owner 未冻结", "typed blocker"),
        }
        for workflow, required in expectations.items():
            with self.subTest(workflow=workflow):
                text = (
                    _REPO_ROOT / f".agents/skills/{workflow}/SKILL.md"
                ).read_text(encoding="utf-8")
                self.assertIn("make feature-context TARGET=<exact-path>", text)
                self.assertIn("immutable exact ref", text)
                for phrase in required:
                    self.assertIn(phrase, text)

    def test_hosted_smoke_reuses_current_exact_owner_manifest_consumer(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t1
        source = (
            _REPO_ROOT / "quwoquan_ops/cli/hosted_authority_smoke.py"
        ).read_text(encoding="utf-8")
        start = source.index("def _verify_owner_manifest(")
        end = source.index("\ndef _verify_readiness_descriptor", start)
        owner_source = source[start:end]
        symbols = (
            "exact_digest = _sha256(owner_manifest_bytes)",
            "expected_ref = (OWNER_MANIFEST_ROOT / expected_name).as_posix()",
            "if owner_manifest_ref != expected_ref:",
            "validated_ref = validate_content_addressed_ref(",
            "if validated_ref != owner_manifest_ref:",
            "_verify_owner_manifest_descriptor(",
            'manifest = _json_bytes(owner_manifest_bytes, label="owner manifest")',
            "validate_feature_context_manifest(manifest)",
            "fingerprint = validate_current_feature_context_fingerprint(",
            "return manifest, fingerprint, exact_digest",
        )
        positions = [owner_source.index(symbol) for symbol in symbols]
        self.assertEqual(positions, sorted(positions))
        run_start = source.index("def run_observe_only_smoke(")
        run_source = source[run_start:]
        verify_call = run_source.index(
            "manifest, manifest_fingerprint, manifest_digest = _verify_owner_manifest("
        )
        authority_binding = run_source.index(
            'expected_fingerprint=str(manifest_fingerprint["digest"])'
        )
        identity_use = run_source.index(
            '"evidence_fingerprint": manifest_fingerprint["digest"]'
        )
        self.assertLess(verify_call, authority_binding)
        self.assertLess(authority_binding, identity_use)

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

    def test_dynamic_valid_workflow_skill_is_discovered(self) -> None:
        self._use_fixture_root()
        self._workflow("probe")
        self.assertIn("probe", self.module._workflow_skills())
        issues = self.module.check_workflow_skills()
        self.assertFalse(any("probe/SKILL.md" in issue for issue in issues), issues)

    def test_workflow_malformed_yaml_is_reported_and_not_discovered(self) -> None:
        self._use_fixture_root()
        self._write(
            ".agents/skills/probe/SKILL.md",
            self._workflow_text("probe", frontmatter="name: [probe\nmetadata:\n  kind: workflow\n"),
        )
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("probe/SKILL.md" in issue and "合法 YAML" in issue for issue in issues), issues)
        self.assertNotIn("probe", self.module._workflow_skills())

    def test_workflow_missing_metadata_is_reported_and_not_discovered(self) -> None:
        self._use_fixture_root()
        self._write(
            ".agents/skills/probe/SKILL.md",
            self._workflow_text("probe", frontmatter="name: probe\ndescription: d\n"),
        )
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("probe/SKILL.md" in issue and "metadata 必须是映射" in issue for issue in issues), issues)
        self.assertNotIn("probe", self.module._workflow_skills())

    def test_workflow_wrong_kind_is_reported_and_not_discovered(self) -> None:
        self._use_fixture_root()
        self._write(
            ".agents/skills/probe/SKILL.md",
            self._workflow_text(
                "probe",
                frontmatter="name: probe\ndescription: d\nmetadata:\n  kind: reference\n",
            ),
        )
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("probe/SKILL.md" in issue and "metadata.kind 必须为 workflow" in issue for issue in issues), issues)
        self.assertNotIn("probe", self.module._workflow_skills())

    def test_workflow_directory_missing_skill_is_reported(self) -> None:
        self._use_fixture_root()
        (self.root / ".agents/skills/probe").mkdir(parents=True)
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("probe/SKILL.md" in issue and "regular non-symlink" in issue for issue in issues), issues)

    def test_workflow_directory_symlink_is_rejected_without_loading_target(self) -> None:
        self._use_fixture_root()
        outside_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_tmp.cleanup)
        outside = Path(outside_tmp.name)
        outside_skill = outside / "SKILL.md"
        outside_skill.write_text(self._workflow_text("escape"), encoding="utf-8")
        escape = self.root / ".agents/skills/escape"
        escape.symlink_to(outside, target_is_directory=True)
        escaped_skill_path = escape / "SKILL.md"
        original_read_text = Path.read_text

        def guarded_read_text(candidate: Path, *args: object, **kwargs: object) -> str:
            if candidate == escaped_skill_path:
                raise AssertionError("不得读取仓外 Skill")
            return original_read_text(candidate, *args, **kwargs)

        with patch.object(Path, "read_text", guarded_read_text):
            workflows, issues = self.module._discover_workflow_skill_metadata()
            self.assertNotIn("escape", workflows)
            self.assertNotIn("escape", self.module._workflow_skills())
        self.assertTrue(any("skills/escape" in issue and "不得是 symlink" in issue for issue in issues), issues)

    def test_workflow_broken_direct_child_symlink_is_rejected(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        broken = self.root / ".agents/skills/broken"
        broken.symlink_to(self.root / "missing-skill", target_is_directory=True)
        workflows, issues = self.module._discover_workflow_skill_metadata()
        self.assertNotIn("broken", workflows)
        self.assertTrue(
            any("skills/broken" in issue and "不得是 symlink" in issue for issue in issues),
            issues,
        )

    def test_workflow_file_direct_child_symlink_is_rejected(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        target = self._write("skill-link-target.md", "not a workflow directory\n")
        linked_file = self.root / ".agents/skills/file-link"
        linked_file.symlink_to(target)
        workflows, issues = self.module._discover_workflow_skill_metadata()
        self.assertNotIn("file-link", workflows)
        self.assertTrue(
            any("skills/file-link" in issue and "不得是 symlink" in issue for issue in issues),
            issues,
        )

    def test_workflow_skill_root_symlink_is_rejected_without_traversal(self) -> None:
        self.module.ROOT = self.root
        outside_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_tmp.cleanup)
        outside = Path(outside_tmp.name)
        outside_probe = outside / "probe/SKILL.md"
        outside_probe.parent.mkdir(parents=True)
        outside_probe.write_text(self._workflow_text("probe"), encoding="utf-8")
        agents = self.root / ".agents"
        agents.mkdir(parents=True)
        skill_root = agents / "skills"
        skill_root.symlink_to(outside, target_is_directory=True)
        escaped_skill_path = skill_root / "probe/SKILL.md"
        original_read_text = Path.read_text

        def guarded_read_text(candidate: Path, *args: object, **kwargs: object) -> str:
            if candidate == escaped_skill_path:
                raise AssertionError("不得遍历仓外 Skill root")
            return original_read_text(candidate, *args, **kwargs)

        with patch.object(Path, "read_text", guarded_read_text):
            workflows, issues = self.module._discover_workflow_skill_metadata()
            self.assertEqual({}, workflows)
            self.assertEqual((), self.module._workflow_skills())
        self.assertTrue(any(".agents/skills" in issue and "non-symlink" in issue for issue in issues), issues)

    def test_agents_root_symlink_is_rejected_without_traversal(self) -> None:
        self.module.ROOT = self.root
        outside_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_tmp.cleanup)
        outside = Path(outside_tmp.name)
        outside_probe = outside / "skills/probe/SKILL.md"
        outside_probe.parent.mkdir(parents=True)
        outside_probe.write_text(self._workflow_text("probe"), encoding="utf-8")
        agents_root = self.root / ".agents"
        agents_root.symlink_to(outside, target_is_directory=True)
        escaped_skill_path = agents_root / "skills/probe/SKILL.md"
        original_read_text = Path.read_text

        def guarded_read_text(candidate: Path, *args: object, **kwargs: object) -> str:
            if candidate == escaped_skill_path:
                raise AssertionError("不得遍历仓外 .agents")
            return original_read_text(candidate, *args, **kwargs)

        with patch.object(Path, "read_text", guarded_read_text):
            workflows, issues = self.module._discover_workflow_skill_metadata()
            self.assertEqual({}, workflows)
            self.assertNotIn("probe", workflows)
            self.assertNotIn("probe", self.module._workflow_skills())
        self.assertTrue(any(".agents 必须是 real non-symlink directory" in issue for issue in issues), issues)

    def test_workflow_requires_exact_five_sections(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        (self.root / ".agents/skills").mkdir(parents=True, exist_ok=True)
        self._workflow("dev", headings=("触发与输入", "执行", "HANDOFF"))
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("二级段落必须且只能" in issue for issue in issues), issues)

    def test_workflow_rejects_legacy_extra_sections(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        (self.root / ".agents/skills").mkdir(parents=True, exist_ok=True)
        headings = (*self.module.REQUIRED_SKILL_SECTIONS, "内置评审")
        self._workflow("dev", headings=headings)
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("二级段落必须且只能" in issue for issue in issues), issues)

    def test_workflow_rejects_shared_completion_jump(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        (self.root / ".agents/skills").mkdir(parents=True, exist_ok=True)
        self._workflow("dev")
        path = self.root / ".agents/skills/dev/SKILL.md"
        path.write_text(path.read_text(encoding="utf-8") + "completion-criteria.md\n", encoding="utf-8")
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("不得跳转共享文档" in issue for issue in issues), issues)

    def test_retired_wfr_exact_path_reappearance_is_rejected(self) -> None:
        self._use_fixture_root()
        retired = "quwoquan_ops/cli/workflow_resolver.py"
        self._write(retired, "# retired\n")
        issues = self.module.check_retired_workflow_resolution()
        self.assertTrue(any(retired in issue and "路径回潮" in issue for issue in issues), issues)

    def test_retired_wfr_admission_field_reappearance_is_rejected(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        carrier = "quwoquan_ops/policies/governance_pipeline_admission_contract.yaml"
        self._write(carrier, "workflow_resolve_source: legacy\n")
        self._track(carrier)
        issues = self.module.check_retired_workflow_resolution()
        self.assertTrue(any(carrier in issue and "workflow_resolve_source" in issue for issue in issues), issues)

    def test_tracked_renamed_python_wfr_source_is_rejected_without_registration(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        carrier = "quwoquan_ops/cli/renamed_workflow_probe.py"
        self._write(carrier, "workflow_resolution = 'retired'\n")
        self._track(carrier)
        issues = self.module.check_retired_workflow_resolution()
        self.assertTrue(any(carrier in issue and "workflow_resolution" in issue for issue in issues), issues)

    def test_tracked_renamed_yaml_wfr_source_is_rejected_without_registration(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        carrier = "quwoquan_ops/policies/renamed-workflow-probe.yaml"
        self._write(carrier, "route_receipt: retired\n")
        self._track(carrier)
        issues = self.module.check_retired_workflow_resolution()
        self.assertTrue(any(carrier in issue and "route_receipt" in issue for issue in issues), issues)

    def test_tracked_renamed_markdown_wfr_source_is_rejected_without_registration(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        carrier = (
            "specs/feature-tree/runtime/development-workflow-governance/"
            "renamed-routing-probe.md"
        )
        self._write(carrier, "workflow-resolution 是退役结构。\n")
        self._track(carrier)
        issues = self.module.check_retired_workflow_resolution()
        self.assertTrue(any(carrier in issue and "workflow-resolution" in issue for issue in issues), issues)

    def test_wfr_scan_ignores_untracked_temporary_source(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        self._write("quwoquan_ops/cli/temporary_probe.py", "workflow_resolution = 'temp'\n")
        self.assertEqual([], self.module.check_retired_workflow_resolution())

    def test_wfr_scan_ignores_tracked_test_fixture_and_generated_output(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        fixture = "quwoquan_ops/tests/fixtures/workflow_resolution_fixture.py"
        generated = "quwoquan_ops/cli/lib/generated/workflow_resolution.py"
        self._write(fixture, "workflow_resolution = 'fixture'\n")
        self._write(generated, "workflow_resolution = 'generated'\n")
        self._track(fixture, generated)
        self.assertEqual([], self.module.check_retired_workflow_resolution())

    def test_wfr_scan_ignores_tracked_historical_deleted_source(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        carrier = "quwoquan_ops/gate/deleted_workflow_probe.py"
        path = self._write(carrier, "workflow_resolution = 'deleted'\n")
        self._track(carrier)
        path.unlink()
        self.assertEqual([], self.module.check_retired_workflow_resolution())

    def test_legitimate_device_and_local_resolver_words_are_not_rejected(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-001.t2
        self._use_fixture_root()
        carrier = "quwoquan_ops/cli/lib/local_device_resolver.py"
        self._write(
            carrier,
            "def resolve_device():\n"
            "    return 'device resolver and local resolver are business terms'\n",
        )
        self._track(carrier)
        self.assertEqual([], self.module.check_retired_workflow_resolution())

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

    def test_registry_orphan_workflow_is_rejected(self) -> None:
        self._use_fixture_root()
        registry = self._valid_registry()
        registry["workflows"]["ghost"] = {
            "segments": ["PRE", "POST"],
            "deliverable": "x",
            "automatic_review": False,
        }
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, sort_keys=False),
        )
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("workflows.ghost" in issue and "成功发现" in issue for issue in issues), issues)

    def test_profile_unknown_workflow_is_rejected(self) -> None:
        self._use_fixture_root()
        registry = self._valid_registry()
        registry["profiles"]["ghost"] = {
            "paths": ["Makefile"],
            "specialist": {
                "role": "probe",
                "priority": 1,
                "required": False,
                "checklists": {"ghost": "roles/probe/checklists/dev/base.md"},
            },
        }
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self.module.yaml.safe_dump(registry, sort_keys=False),
        )
        issues = self.module.check_checklists_and_registry()
        self.assertTrue(any("profiles.ghost 引用未知 workflow ghost" in issue for issue in issues), issues)

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

    def test_registry_evidence_requires_bounded_timeout_seconds(self) -> None:
        self._use_fixture_root()
        for invalid in (None, 0, -1, 3601, True):
            with self.subTest(invalid=invalid):
                registry = self._valid_registry()
                if invalid is None:
                    del registry["evidence"]["proof"]["timeout_seconds"]
                else:
                    registry["evidence"]["proof"]["timeout_seconds"] = invalid
                self._write(
                    ".agents/skills/review/references/registry.yaml",
                    self.module.yaml.safe_dump(registry, sort_keys=False),
                )
                issues = self.module.check_checklists_and_registry()
                self.assertTrue(
                    any("timeout_seconds" in issue for issue in issues), issues
                )

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

    def test_command_shell_must_be_exact_single_line_projection(self) -> None:
        self._use_fixture_root()
        self._workflow("dev")
        self._write(
            ".cursor/commands/dev.md",
            "---\nname: /dev\ndescription: d\n---\n\n" + "正文\n" * 2,
        )
        issues = self.module.check_commands_and_harness_stubs()
        self.assertTrue(any("canonical 单行 Skill 投影" in issue for issue in issues), issues)

    def test_command_projection_is_derived_from_skill_metadata(self) -> None:
        self._use_fixture_root()
        self._workflow("dev")
        self._workflow("environment-ops")
        for name in self.command_names:
            self._write(
                f".cursor/commands/{name}.md",
                "---\n" f"name: /{name}\n" "description: d\n---\n\n"
                f"加载并按 `.agents/skills/{name}/SKILL.md` 执行。\n",
            )
        for name in self.command_names:
            self._write(
                f".cursor/commands/{name}.md",
                f"---\nname: /{name}\ndescription: d\n---\n\n"
                f"加载并按 `.agents/skills/{name}/SKILL.md` 执行。\n",
            )
        self.assertEqual([], self.module.check_commands_and_harness_stubs())

    def test_harness_workflow_stub_is_forbidden(self) -> None:
        self._use_fixture_root()
        self._write(
            ".codex/skills/probe/SKILL.md",
            "---\nname: probe\ndescription: d\n---\n\n指向 .agents/skills/probe/SKILL.md。\n",
        )
        issues = self.module.check_commands_and_harness_stubs()
        self.assertTrue(any("禁止宿主专属 Workflow stub" in issue for issue in issues), issues)

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
