"""verify_agent_context_budget 的负例合约。

治理门禁最容易失效的方式不是报错，而是**永远转绿**——检查写歪了、正则不匹配、
或扫描范围漏掉目标目录，结果是通过但什么都没查。所以每条检查都必须有一个能让它变红的
负例，且真实仓库必须是绿的（否则说明检查过严，会被下一个人调松）。
"""

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
        """把门禁的 ROOT 指向临时树，使负例不污染真实仓库。

        第一方判定依赖 git 索引，所以默认把临时树初始化成仓库；
        需要验证「git 不可用时不得静默放过」的用例传 git=False。
        """
        self.module.ROOT = self.root
        if git:
            subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def _track(self, *rels: str) -> None:
        subprocess.run(["git", "add", "--", *rels], cwd=self.root, check=True)

    def _write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _skill(self, name: str, description: str = "d", body: str = "body") -> Path:
        return self._write(
            f".agents/skills/{name}/SKILL.md",
            f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        )

    # ── 真实仓库必须绿 ────────────────────────────────────────────────
    def test_real_repository_passes_every_check(self) -> None:
        for label, check in self.module.CHECKS:
            with self.subTest(check=label):
                self.assertEqual([], check(), f"{label} 在真实仓库上应为绿")

    # ── 预算类负例 ────────────────────────────────────────────────────
    def test_detects_agents_line_budget_overflow(self) -> None:
        self._use_fixture_root()
        budget = self.module.AGENTS_LINE_BUDGET
        self._write("AGENTS.md", "\n".join(f"line {i}" for i in range(budget + 5)))
        self._track("AGENTS.md")
        issues = self.module.check_agents_budget()
        self.assertTrue(
            any(f"超过 {budget} 行上限" in issue for issue in issues), issues
        )

    def test_detects_codex_merged_byte_budget_overflow(self) -> None:
        self._use_fixture_root()
        # 单文件各自不超行数上限，但合并后越过 Codex 32 KiB —— 这正是嵌套 AGENTS.md
        # 的真实失效形态：每个文件看起来都正常，只有合并总量会被静默截断。
        half = "x" * (self.module.CODEX_MERGED_BYTE_BUDGET // 2 + 100)
        self._write("AGENTS.md", half)
        self._write("nested/AGENTS.md", half)
        self._track("AGENTS.md", "nested/AGENTS.md")
        issues = self.module.check_agents_budget()
        self.assertTrue(any("超过 Codex" in issue for issue in issues), issues)

    def test_detects_third_party_agents_file(self) -> None:
        """依赖缓存自带的 AGENTS.md 会经嵌套拾取进入上下文。"""
        self._use_fixture_root()
        self._write("vendored/AGENTS.md", "third party instructions")
        issues = self.module.check_agents_budget()
        self.assertTrue(any("非第一方" in issue for issue in issues), issues)

    def test_refuses_to_pass_when_git_index_is_unavailable(self) -> None:
        """第一方判定依赖 git；查不到索引必须阻断，而不是当作没有违规。"""
        self._use_fixture_root(git=False)
        self._write("AGENTS.md", "root")
        issues = self.module.check_agents_budget()
        self.assertTrue(any("不可执行" in issue for issue in issues), issues)

    def test_prunes_dependency_caches_from_agents_scan(self) -> None:
        self._use_fixture_root()
        for pruned in sorted(self.module.PRUNED_DIR_NAMES):
            self._write(f"{pruned}/AGENTS.md", "cache-owned instructions")
        self.assertEqual([], self.module.check_agents_budget())

    def test_detects_skill_description_budget_overflow(self) -> None:
        self._use_fixture_root()
        each = self.module.SKILL_DESCRIPTION_EACH_BUDGET
        total = self.module.SKILL_DESCRIPTION_TOTAL_BUDGET
        for index in range(total // each + 2):
            self._skill(f"skill-{index}", description="d" * each)
        issues = self.module.check_skills()
        self.assertTrue(any("清单预算" in issue for issue in issues), issues)

    def test_detects_skill_line_budget_overflow(self) -> None:
        self._use_fixture_root()
        body = "\n".join(f"line {i}" for i in range(self.module.SKILL_LINE_BUDGET + 5))
        self._skill("fat-skill", body=body)
        issues = self.module.check_skills()
        self.assertTrue(any("行上限" in issue for issue in issues), issues)

    # ── frontmatter 与命名负例 ────────────────────────────────────────
    def test_detects_non_spec_frontmatter_field(self) -> None:
        """paths 是 Cursor 扩展字段，会在 Skills API 路径下硬报错。"""
        self._use_fixture_root()
        self._write(
            ".agents/skills/leaky/SKILL.md",
            "---\nname: leaky\ndescription: d\npaths: lib/**\n---\n\nbody\n",
        )
        issues = self.module.check_skills()
        self.assertTrue(any("非开放规范字段" in issue for issue in issues), issues)

    def test_detects_name_directory_mismatch(self) -> None:
        self._use_fixture_root()
        self._write(
            ".agents/skills/actual-dir/SKILL.md",
            "---\nname: other-name\ndescription: d\n---\n\nbody\n",
        )
        issues = self.module.check_skills()
        self.assertTrue(any("与目录名" in issue for issue in issues), issues)

    def test_detects_unquoted_colon_breaking_frontmatter_yaml(self) -> None:
        """`description: A: B` 会让整份 frontmatter 解析失败，技能静默不可见。

        手写的按行 partition 解析器会把这种值读成合法内容，从而漏报——
        本用例锁定门禁必须用真正的 YAML 解析器。
        """
        self._use_fixture_root()
        self._write(
            ".agents/skills/colon/SKILL.md",
            "---\nname: colon\ndescription: Do a thing: then another thing\n---\n\nbody\n",
        )
        issues = self.module.check_skills()
        self.assertTrue(any("不是合法 YAML" in issue for issue in issues), issues)

    def test_accepts_quoted_colon_in_description(self) -> None:
        self._use_fixture_root()
        self._write(
            ".agents/skills/quoted/SKILL.md",
            '---\nname: quoted\ndescription: "Do a thing: then another"\n---\n\nbody\n',
        )
        self.assertEqual([], self.module.check_skills())

    def test_detects_missing_description(self) -> None:
        """没有 description 的技能永远不会被自动触发。"""
        self._use_fixture_root()
        self._write(".agents/skills/mute/SKILL.md", "---\nname: mute\n---\n\nbody\n")
        issues = self.module.check_skills()
        self.assertTrue(any("缺 description" in issue for issue in issues), issues)

    # ── 工作流封闭集合与命令映射负例 ──────────────────────────────────
    def test_detects_non_workflow_top_level_skill(self) -> None:
        """原则/标准回流顶层是上一轮结构劣化的主形态，必须硬阻断。"""
        self._use_fixture_root()
        self._skill("some-principle")
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("不在工作流封闭集合内" in issue for issue in issues), issues)

    def test_detects_missing_workflow_skill(self) -> None:
        self._use_fixture_root()
        (self.root / ".agents/skills").mkdir(parents=True)
        issues = self.module.check_workflow_skills()
        self.assertTrue(
            any("缺工作流技能: .agents/skills/dev/SKILL.md" in issue for issue in issues),
            issues,
        )

    def test_detects_command_without_matching_workflow(self) -> None:
        self._use_fixture_root()
        (self.root / ".agents/skills").mkdir(parents=True)
        self._write(".cursor/commands/rogue.md", "---\nname: rogue\n---\n\n执行。\n")
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("双向一一映射" in issue for issue in issues), issues)

    def test_detects_fat_or_historical_command_shell(self) -> None:
        """命令薄壳一旦超预算或出现历史叙述，说明语义又回流到了命令层。"""
        self._use_fixture_root()
        (self.root / ".agents/skills").mkdir(parents=True)
        body = "\n".join(["本命令由旧命令迁移而来。"] * 20)
        self._write(".cursor/commands/dev.md", f"---\nname: dev\n---\n\n{body}\n")
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("行上限" in issue for issue in issues), issues)
        self.assertTrue(any("历史叙述措辞" in issue for issue in issues), issues)
        self.assertTrue(
            any("未指向 .agents/skills/dev/SKILL.md" in issue for issue in issues), issues
        )

    def test_detects_workflow_skill_without_template_sections(self) -> None:
        self._use_fixture_root()
        self._write(
            ".agents/skills/explore/SKILL.md",
            "---\nname: explore\ndescription: d\n---\n\n随便写的正文\n",
        )
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("metadata.kind 必须为 workflow" in issue for issue in issues), issues)
        self.assertTrue(any("缺统一模板段 ## HANDOFF" in issue for issue in issues), issues)

    def test_detects_handoff_without_downstream_declaration(self) -> None:
        self._use_fixture_root()
        sections = "\n\n".join(
            f"{s}\n\n内容" for s in self.module.REQUIRED_SKILL_SECTIONS
        )
        self._write(
            ".agents/skills/explore/SKILL.md",
            "---\nname: explore\ndescription: d\nmetadata:\n  kind: workflow\n"
            f"  command: /explore\n---\n\n{sections}\n",
        )
        issues = self.module.check_workflow_skills()
        self.assertTrue(any("缺「唯一合法下游」" in issue for issue in issues), issues)

    # ── 引用有效性负例 ────────────────────────────────────────────────
    def test_detects_nonexistent_make_target_in_gate_binding(self) -> None:
        """绑定到不存在的 target 的 MUST 等于没有门禁。"""
        self._use_fixture_root()
        self._write("Makefile", "verify-real-target:\n\t@true\n")
        self._write("AGENTS.md", "gate: make verify-does-not-exist\n")
        issues = self.module.check_references()
        self.assertTrue(
            any("不存在的 target" in issue for issue in issues), issues
        )

    def test_accepts_existing_make_target_in_gate_binding(self) -> None:
        self._use_fixture_root()
        self._write("Makefile", "verify-real-target:\n\t@true\n")
        self._write("AGENTS.md", "gate: make verify-real-target\n")
        self.assertEqual([], self.module.check_references())

    def test_detects_broken_relative_link_between_skills(self) -> None:
        self._use_fixture_root()
        self._write("Makefile", "noop:\n\t@true\n")
        self._write("AGENTS.md", "root\n")
        self._skill("linker", body="见 [gone](../gone/SKILL.md)")
        issues = self.module.check_references()
        self.assertTrue(any("断链" in issue for issue in issues), issues)

    def test_detects_truth_source_left_in_harness_private_directory(self) -> None:
        self._use_fixture_root()
        self._write("Makefile", "noop:\n\t@true\n")
        self._write("AGENTS.md", "详见 .cursor/skills/environment-ops/SKILL.md\n")
        issues = self.module.check_references()
        self.assertTrue(
            any("harness 专属路径" in issue for issue in issues), issues
        )

    def test_detects_reference_to_retired_skill_path(self) -> None:
        """旧技能路径的引用意味着某个文件还活在上一版结构里。"""
        self._use_fixture_root()
        self._write("Makefile", "noop:\n\t@true\n")
        self._write("AGENTS.md", "评审见 .agents/skills/review-board/SKILL.md\n")
        issues = self.module.check_references()
        self.assertTrue(any("已退役技能路径" in issue for issue in issues), issues)

    def test_detects_stale_glob_that_would_never_trigger(self) -> None:
        """globs 指向不存在的路径时规则静默失效，是改 globs 的最高危回归。"""
        self._use_fixture_root()
        self._write(
            ".cursor/rules/99-probe.mdc",
            "---\nglobs: quwoquan_app/lib/does_not_exist/**/*.dart\n---\n\n指针\n",
        )
        issues = self.module.check_rule_pointers()
        self.assertTrue(any("永不触发" in issue for issue in issues), issues)

    def test_accepts_glob_whose_static_prefix_exists(self) -> None:
        self._use_fixture_root()
        (self.root / "lib/design_system").mkdir(parents=True)
        self._write(
            ".cursor/rules/99-probe.mdc",
            "---\nglobs: lib/design_system/**/*.dart\n---\n\n指针\n",
        )
        self.assertEqual([], self.module.check_rule_pointers())

    def test_detects_fat_always_apply_rule(self) -> None:
        """常驻层只允许薄指针；正文回流会重新占满每个会话的上下文。"""
        self._use_fixture_root()
        self._write(
            ".cursor/rules/98-fat.mdc",
            "---\nalwaysApply: true\n---\n\n" + "正" * 3000,
        )
        issues = self.module.check_rule_pointers()
        self.assertTrue(any("常驻规则" in issue for issue in issues), issues)

    # ── checklist 分级负例 ────────────────────────────────────────────
    def _role_file(self, text: str) -> None:
        self._write(
            ".agents/skills/review/references/roles/probe/checklists/dev/base.md",
            text,
        )

    def test_detects_unbound_must_item(self) -> None:
        self._use_fixture_root()
        self._role_file("## DURING 执行中\n\n- [MUST] 某个无法判定的要求\n")
        issues = self.module.check_checklist_grading()
        self.assertTrue(any("未绑定 gate 或 check" in issue for issue in issues), issues)

    def test_accepts_must_item_bound_by_following_line(self) -> None:
        self._use_fixture_root()
        self._role_file(
            "## DURING 执行中\n\n- [MUST] 某个要求\n  gate: make verify-x\n"
        )
        self.assertEqual([], self.module.check_checklist_grading())

    def test_accepts_must_item_bound_by_check_predicate(self) -> None:
        self._use_fixture_root()
        self._role_file(
            "## POST 自检\n\n- [MUST] 某个要求\n  check: 读 X；出现 Y 判失败\n"
        )
        self.assertEqual([], self.module.check_checklist_grading())

    def test_detects_item_without_grade_tag(self) -> None:
        self._use_fixture_root()
        self._role_file("## PRE 准入\n\n- 一条没有分级的要求\n")
        issues = self.module.check_checklist_grading()
        self.assertTrue(any("缺分级标签" in issue for issue in issues), issues)

    def test_detects_unknown_grade_tag(self) -> None:
        self._use_fixture_root()
        self._role_file("## PRE 准入\n\n- [REQUIRED] 用了第二套裁决词\n")
        issues = self.module.check_checklist_grading()
        self.assertTrue(any("未知分级标签" in issue for issue in issues), issues)

    def test_handoff_section_is_exempt_from_grading(self) -> None:
        """HANDOFF 是交接契约（产出物/未决项/下一步/证据链），不是判定条目。"""
        self._use_fixture_root()
        self._role_file(
            "## POST 自检\n\n- [SHOULD] 某个建议\n\n"
            "## HANDOFF 交接\n\n- 产出：某个清单\n- 下一步：POST 评审汇总\n"
        )
        self.assertEqual([], self.module.check_checklist_grading())

    def test_should_items_need_no_binding(self) -> None:
        self._use_fixture_root()
        self._role_file(
            "## DURING 执行中\n\n- [SHOULD] 建议\n- [MAY] 可选\n- [ADVISORY] 背景\n"
        )
        self.assertEqual([], self.module.check_checklist_grading())

    # ── review 派发表负例 ─────────────────────────────────────────────
    _REGISTRY_HEAD = "concurrency:\n  max_parallel: 4\n  per_role_timeout_minutes: 10\n"

    def _registry(self, text: str) -> None:
        self._write(
            ".agents/skills/review/references/registry.yaml",
            self._REGISTRY_HEAD + text,
        )

    def _role(self, role: str, *checklists: str) -> None:
        """checklists 形如 'dev/base.md'，内容自带一条已绑定的 MUST。"""
        base = ".agents/skills/review/references/roles"
        self._write(f"{base}/{role}/ROLE.md", f"# {role}\n")
        for checklist in checklists:
            self._write(
                f"{base}/{role}/checklists/{checklist}",
                f"# {role}\n\n## POST 自检\n\n- [MUST] 要求\n  gate: make verify-x\n",
            )

    def _workflow_skill(self, name: str, *segments: str) -> None:
        calls = "\n".join(
            f"- {seg}：调 `review`（workflow=`{name}`，segment={seg}，deliverable=`x`）。"
            for seg in segments
        )
        self._write(
            f".agents/skills/{name}/SKILL.md",
            f"---\nname: {name}\ndescription: d\n---\n\n## 内置评审\n\n{calls}\n\n## HANDOFF\n\n内容\n",
        )

    def test_detects_binding_to_missing_checklist(self) -> None:
        """注册了却不存在的 checklist 会让该角色静默不产出结论。"""
        self._use_fixture_root()
        self._registry(
            "workflows:\n  dev:\n    segments: [POST]\n    deliverable: implementation\n"
            "    bindings:\n      - role: developer\n"
            "        checklist: roles/developer/checklists/dev/base.md\n"
        )
        self._write(
            ".agents/skills/review/references/roles/developer/ROLE.md", "# developer\n"
        )
        self._workflow_skill("dev", "POST")
        issues = self.module.check_review_registry()
        self.assertTrue(any("引用不存在的 checklist" in issue for issue in issues), issues)

    def test_detects_unreferenced_checklist_on_disk(self) -> None:
        self._use_fixture_root()
        self._registry(
            "workflows:\n  dev:\n    segments: [POST]\n    deliverable: implementation\n"
            "    bindings:\n      - role: developer\n"
            "        checklist: roles/developer/checklists/dev/base.md\n"
        )
        self._role("developer", "dev/base.md", "dev/orphan.md")
        self._workflow_skill("dev", "POST")
        issues = self.module.check_review_registry()
        self.assertTrue(any("永远不会被派发" in issue for issue in issues), issues)

    def test_detects_role_missing_role_definition(self) -> None:
        self._use_fixture_root()
        self._registry(
            "workflows:\n  dev:\n    segments: [POST]\n    deliverable: implementation\n"
            "    bindings:\n      - role: ghost\n"
            "        checklist: roles/ghost/checklists/dev/base.md\n"
        )
        self._write(
            ".agents/skills/review/references/roles/ghost/checklists/dev/base.md",
            "# ghost\n",
        )
        self._workflow_skill("dev", "POST")
        issues = self.module.check_review_registry()
        self.assertTrue(any("缺 roles/ghost/ROLE.md" in issue for issue in issues), issues)

    def test_detects_checklist_outside_checklists_directory(self) -> None:
        """角色根目录残留的 <stage>.md 是旧平铺结构的回流形态。"""
        self._use_fixture_root()
        self._registry(
            "workflows:\n  dev:\n    segments: [POST]\n    deliverable: implementation\n"
            "    bindings:\n      - role: developer\n"
            "        checklist: roles/developer/checklists/dev/base.md\n"
        )
        self._role("developer", "dev/base.md")
        self._write(
            ".agents/skills/review/references/roles/developer/dev.md", "# 旧平铺\n"
        )
        self._workflow_skill("dev", "POST")
        issues = self.module.check_review_registry()
        self.assertTrue(any("只允许 ROLE.md" in issue for issue in issues), issues)

    def test_detects_stale_profile_path(self) -> None:
        """profile 路径指向已消失的目录时该 profile 永不激活，相关 checklist 全部静默失效。"""
        self._use_fixture_root()
        self._registry(
            "profiles:\n  dart-app:\n    paths: [does/not/exist/**]\n"
            "workflows:\n  dev:\n    segments: [POST]\n    deliverable: implementation\n"
            "    bindings:\n      - role: developer\n"
            "        checklist: roles/developer/checklists/dev/base.md\n"
        )
        self._role("developer", "dev/base.md")
        self._workflow_skill("dev", "POST")
        issues = self.module.check_review_registry()
        self.assertTrue(any("永不命中" in issue for issue in issues), issues)

    def test_detects_binding_with_undeclared_profile(self) -> None:
        self._use_fixture_root()
        self._registry(
            "workflows:\n  dev:\n    segments: [POST]\n    deliverable: implementation\n"
            "    bindings:\n      - role: developer\n"
            "        checklist: roles/developer/checklists/dev/base.md\n"
            "        when: [no-such-profile]\n"
        )
        self._role("developer", "dev/base.md")
        self._workflow_skill("dev", "POST")
        issues = self.module.check_review_registry()
        self.assertTrue(any("未声明的 profile" in issue for issue in issues), issues)

    def test_detects_dead_registration_without_skill_declaration(self) -> None:
        """registry 有 binding 但没有任何 SKILL 声明该调用——评审永远不会被触发。"""
        self._use_fixture_root()
        self._registry(
            "workflows:\n  dev:\n    segments: [POST]\n    deliverable: implementation\n"
            "    bindings:\n      - role: developer\n"
            "        checklist: roles/developer/checklists/dev/base.md\n"
        )
        self._role("developer", "dev/base.md")
        issues = self.module.check_review_registry()
        self.assertTrue(any("死注册" in issue for issue in issues), issues)

    def test_detects_dead_call_without_registry_binding(self) -> None:
        """SKILL 声明了 review 调用但 registry 没有对应 workflow——调用时装配不出任何角色。"""
        self._use_fixture_root()
        self._registry(
            "workflows:\n  dev:\n    segments: [POST]\n    deliverable: implementation\n"
            "    bindings:\n      - role: developer\n"
            "        checklist: roles/developer/checklists/dev/base.md\n"
        )
        self._role("developer", "dev/base.md")
        self._workflow_skill("dev", "PRE", "POST")
        issues = self.module.check_review_registry()
        self.assertTrue(any("死调用" in issue for issue in issues), issues)

    def test_detects_duplicate_gate_ownership_in_unconditional_bundle(self) -> None:
        """无条件 bundle 内同一 gate 两个 owner 意味着重复执行与重复裁决。"""
        self._use_fixture_root()
        self._registry(
            "workflows:\n  dev:\n    segments: [POST]\n    deliverable: implementation\n"
            "    bindings:\n"
            "      - role: developer\n"
            "        checklist: roles/developer/checklists/dev/base.md\n"
            "      - role: architect\n"
            "        checklist: roles/architect/checklists/dev/base.md\n"
        )
        self._role("developer", "dev/base.md")
        self._role("architect", "dev/base.md")
        self._workflow_skill("dev", "POST")
        issues = self.module.check_review_registry()
        self.assertTrue(any("gate 重复归属" in issue for issue in issues), issues)

    # ── harness stub 体量负例 ─────────────────────────────────────────
    def test_detects_fat_harness_stub(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-005
        """宿主技能目录超出 stub 体量说明语义回流，形成第二真相源。"""
        self._use_fixture_root()
        body = "\n".join(["规范真相源：.agents/skills/x/SKILL.md"] * 15)
        self._write(
            ".cursor/skills/fat-stub/SKILL.md",
            f"---\nname: fat-stub\ndescription: d\n---\n\n{body}\n",
        )
        issues = self.module.check_harness_stubs()
        self.assertTrue(any("行上限" in issue for issue in issues), issues)

    def test_detects_harness_stub_without_truth_source_pointer(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-005
        self._use_fixture_root()
        self._write(
            ".codex/skills/blind-stub/SKILL.md",
            "---\nname: blind-stub\ndescription: d\n---\n\n自带一套说法。\n",
        )
        issues = self.module.check_harness_stubs()
        self.assertTrue(any("未指向 .agents/skills/" in issue for issue in issues), issues)

    # ── 完成判据单轨负例 ──────────────────────────────────────────────
    def test_detects_missing_completion_criteria_table(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        issues = self.module.check_completion_criteria()
        self.assertTrue(any("缺完成判据表" in issue for issue in issues), issues)

    def test_detects_workflow_missing_from_criteria_table(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        self._write(
            ".agents/skills/review/references/completion-criteria.md",
            "# 表\n\n## explore\n\n- verify: `make x` 退出 0\n",
        )
        issues = self.module.check_completion_criteria()
        self.assertTrue(any("缺 workflow `dev`" in issue for issue in issues), issues)

    def test_detects_criteria_section_without_verify_line(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        sections = "\n\n".join(
            f"## {wf}\n\n- verify: `make x` 退出 0"
            for wf in self.module.WORKFLOW_SKILLS
            if wf != "dev"
        )
        self._write(
            ".agents/skills/review/references/completion-criteria.md",
            f"# 表\n\n{sections}\n\n## dev\n\n- check: 只有 check 没有 verify\n",
        )
        issues = self.module.check_completion_criteria()
        self.assertTrue(any("缺 `- verify:` 判据行" in issue for issue in issues), issues)

    def test_detects_handoff_not_referencing_criteria_table(self) -> None:
        # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t2
        self._use_fixture_root()
        sections = "\n\n".join(
            f"## {wf}\n\n- verify: `make x` 退出 0"
            for wf in self.module.WORKFLOW_SKILLS
        )
        self._write(
            ".agents/skills/review/references/completion-criteria.md",
            f"# 表\n\n{sections}\n",
        )
        self._write(
            ".agents/skills/dev/SKILL.md",
            "---\nname: dev\ndescription: d\n---\n\n## HANDOFF\n\n- 产出物：x\n",
        )
        issues = self.module.check_completion_criteria()
        self.assertTrue(any("未引用完成判据表" in issue for issue in issues), issues)

    # ── 重复正文负例 ──────────────────────────────────────────────────
    def test_detects_duplicated_paragraph_across_skill_files(self) -> None:
        """同一段正文出现在两个文件就是第二真相源，改一处漏一处。"""
        self._use_fixture_root()
        paragraph = (
            "页面与 Provider 只依赖对象级 CommandWriter 与 Query typed port，"
            "禁止聚合 Repository、运行时数据源切换与任何形式的降级返回，"
            "失败必须保持失败语义并向上传播到统一恢复入口，"
            "任何 Remote adapter 在失败路径上都不得返回 fixture、空集合或本地合成成功，"
            "也不得吞掉 RuntimeFailure 后伪装为空态。"
        )
        self._skill("alpha-flow", body=paragraph)
        self._skill("beta-flow", body=paragraph)
        issues = self.module.check_duplicate_body()
        self.assertTrue(any("重复" in issue for issue in issues), issues)


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
