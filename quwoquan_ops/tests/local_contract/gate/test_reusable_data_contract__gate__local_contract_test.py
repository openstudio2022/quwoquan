"""local_contract: 可复用 Data 输入契约门禁的正负例。

门禁判定的是"可复用输入里不许沉淀一次性放量事实"，扫描面来自 module 级
`REPO_ROOT`，因此这里把它指向临时仓库树，用合成输入逐条驱动判据。

负例之外同样钉住豁免面：taxonomy 天然要写省份名、provider 计数规则只对
providers.yaml 生效、`1977` 与 `19770` 不是同一件事。豁免一旦被"顺手收紧"，
真实控制面就会开始长期假红，最终被绕过——那比没有这条门禁更糟。
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_ROOT = ROOT / "quwoquan_data" / "scripts"
MODULE_PATH = SCRIPTS_ROOT / "verify" / "verify_reusable_data_contract.py"

if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_reusable_data_contract_companion",
        MODULE_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReusableDataContractGateTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.gate = _load_module()
        self.gate.REPO_ROOT = self.repo
        self._seed_reusable_inputs()

    def _write(self, relative: str, text: str) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _seed_reusable_inputs(self) -> None:
        """垂类只拥有 provider / content / license 三份策略，且都不带放量事实。"""
        self._write(
            "quwoquan_data/verticals/travel/providers.yaml",
            "providers:\n  - id: wikipedia\n    role: encyclopedia_primary\n",
        )
        self._write(
            "quwoquan_data/verticals/travel/content_policy.yaml",
            "lanes:\n  homepage:\n    sourcePolicy: encyclopedia_primary\n",
        )
        self._write(
            "quwoquan_data/verticals/travel/rights/license_policy.yaml",
            "allowedLicenses:\n  - CC BY 4.0\n",
        )

    def _issues(self) -> list[str]:
        return self.gate.reusable_data_contract_issues()

    def _assert_rejected(self, needle: str) -> None:
        issues = self._issues()
        self.assertTrue(
            any(needle in item for item in issues),
            msg=f"expected an issue containing {needle!r}, got {issues}",
        )
        self.assertEqual(self.gate.main(), 1)

    def _assert_accepted(self) -> None:
        self.assertEqual(self._issues(), [])
        self.assertEqual(self.gate.main(), 0)

    def test_reusable_inputs_without_rollout_facts_are_accepted(self) -> None:
        self._assert_accepted()

    def test_missing_verticals_directory_is_rejected(self) -> None:
        # 垂类目录是可复用输入的骨架；它不在场时门禁必须报缺失，而不是把"没有
        # 文件可扫"读成"没有问题"。
        shutil.rmtree(self.repo / "quwoquan_data/verticals")
        self._assert_rejected("quwoquan_data/verticals: directory is missing")

    def test_vertical_only_owns_policy_and_license_files(self) -> None:
        self._write("quwoquan_data/verticals/travel/notes.md", "scratch\n")
        self._write("quwoquan_data/verticals/travel/rights/notes.yaml", "scratch: 1\n")
        self._write(
            "quwoquan_data/verticals/travel/lanes/providers.yaml",
            "providers: []\n",
        )
        issues = self._issues()
        self.assertEqual(
            sorted(
                item.split(":", 1)[0]
                for item in issues
                if "verticals only own" in item
            ),
            [
                "quwoquan_data/verticals/travel/lanes/providers.yaml",
                "quwoquan_data/verticals/travel/notes.md",
                "quwoquan_data/verticals/travel/rights/notes.yaml",
            ],
        )
        self.assertEqual(self.gate.main(), 1)

    def test_rollout_codename_in_reusable_contract_is_rejected(self) -> None:
        for text in ("stage: canary\n", "batch: two-province\n", "wave: h10k\n"):
            self._write("quwoquan_data/control_plane/campaigns/plan.yaml", text)
            self._assert_rejected("reusable contract contains task-specific value")

    def test_rollout_codename_match_ignores_case(self) -> None:
        self._write("quwoquan_data/control_plane/campaigns/plan.yaml", "stage: Canary\n")
        self._assert_rejected("reusable contract contains task-specific value")

    def test_domain_neutral_post_delete_probe_wording_is_accepted(self) -> None:
        self._write(
            "specs/feature-tree/runtime/runtime-data-engineering/spec.md",
            "post-delete minimal production probe validates the smallest new execution\n",
        )
        self._assert_accepted()

    def test_scale_catalog_is_held_to_the_same_rollout_ban(self) -> None:
        # scale catalog 自带一套 forbidden 元组，容易被当成"放量事实的合法落点"
        # 而单独放宽；它其实与其他可复用输入同口径。
        self._write(
            "quwoquan_data/control_plane/campaigns/scale_catalog.yaml",
            "stages:\n  - id: canary\n",
        )
        self._assert_rejected(
            "quwoquan_data/control_plane/campaigns/scale_catalog.yaml: "
            "reusable contract contains task-specific value"
        )

    def test_task_specific_place_and_count_values_are_rejected(self) -> None:
        for text in ("示例城市：浙江\n", "targetCount: 922\n"):
            self._write("quwoquan_data/prompts/homepage.md", text)
            self._assert_rejected(
                "quwoquan_data/prompts/homepage.md: "
                "reusable contract contains task-specific value"
            )

    def test_numbers_that_merely_contain_a_task_count_are_accepted(self) -> None:
        # 判据是词边界而不是子串；`19770` 之类的普通数值必须能自由出现，否则
        # 模板与 schema 会因为无关数字被长期误伤。
        self._write("quwoquan_data/prompts/homepage.md", "id: 19770 size: 28990\n")
        self._assert_accepted()

    def test_governance_taxonomy_is_out_of_scope(self) -> None:
        # taxonomy 就是地名的真相源；把它纳入扫描面等于禁止标签体系写省份。
        self._write(
            "quwoquan_data/control_plane/governance/taxonomy/地点/浙江/_definition.json",
            '{"tagRef": "地点/浙江"}\n',
        )
        self._assert_accepted()

    def test_provider_policy_rejects_known_task_exceptions(self) -> None:
        self._write(
            "quwoquan_data/verticals/travel/providers.yaml",
            "providers:\n  - id: wikipedia\nknownProvider: wikipedia\n",
        )
        self._assert_rejected("must not contain known* task exceptions")

    def test_known_exception_rule_is_scoped_to_provider_policy(self) -> None:
        self._write(
            "quwoquan_data/verticals/travel/content_policy.yaml",
            "knownProvider: wikipedia\nknownlist: []\n",
        )
        self._write(
            "quwoquan_data/verticals/travel/providers.yaml",
            "providers:\n  - id: wikipedia\nknownlist: []\n",
        )
        self._assert_accepted()

    def test_provider_policy_rejects_rollout_counts_and_maturity(self) -> None:
        for line in (
            "expectedCount: 12\n",
            "minimumLaneCounts:\n  homepage: 3\n",
            "maturity: pilot\n",
        ):
            self._write(
                "quwoquan_data/verticals/travel/providers.yaml",
                "providers:\n  - id: wikipedia\n" + line,
            )
            self._assert_rejected("must not contain rollout counts or maturity")

    def test_rollout_count_rule_is_line_anchored(self) -> None:
        self._write(
            "quwoquan_data/verticals/travel/providers.yaml",
            "providers:\n  - id: wikipedia\n# maturity: 由 campaign 决定，不写进策略\n",
        )
        self._assert_accepted()

    def test_reference_rejects_runtime_state(self) -> None:
        # reference 是可复用素材，不是执行台账；写进 executionId 就等于把一次
        # 运行的结论固化成下一次运行的输入。
        self._write("quwoquan_data/reference/travel.md", "executionId: 20260101--x\n")
        self._assert_rejected("reference contains runtime state or release conclusion")

    def test_reference_rejects_task_source_urls(self) -> None:
        self._write("quwoquan_data/reference/travel.md", "见 https://example.org/a\n")
        self._assert_rejected("reference must not contain task source URLs")

    def test_reference_without_runtime_state_is_accepted(self) -> None:
        self._write("quwoquan_data/reference/travel.md", "写作要点：先给结论\n")
        self._assert_accepted()

    def test_shared_fixture_rejects_rollout_values(self) -> None:
        self._write("quwoquan_data/tests/support/sample.py", 'WAVE = "h10k"\n')
        self._assert_rejected("shared fixture contains production rollout value")

    def test_undecodable_input_does_not_break_the_scan(self) -> None:
        path = self.repo / "quwoquan_data/reference/binary.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xff\xfeexecutionId:")
        self._assert_accepted()

    def test_real_repository_satisfies_the_reusable_contract(self) -> None:
        self.assertEqual(_load_module().reusable_data_contract_issues(), [])


if __name__ == "__main__":
    unittest.main()
