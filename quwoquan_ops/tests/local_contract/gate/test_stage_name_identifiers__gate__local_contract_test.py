# spec_ref: specs/feature-tree/runtime/runtime-control-plane-foundation/domain-onboarding-acceptance-governance/spec.md#gwt-004
"""`verify_stage_name_identifiers.py`（阶段名标识零容忍门禁）的本地契约。

本测试锁定五件事：

1. 拦截能力：历史违规形态（`m2_*` / `m8_*` / `m9_p0_*` fixture 名、
   `assistant_m2_contract` / `m11_local_scenario` 测试文件名、
   `TestAssistantM2ContractSchemasGovernance` 等测试标识、`user_m9` 等
   fixture 标识值）新增即被拦下，覆盖路径、测试标识、JSON、schema key 四个面。
2. 合法形态不误报：hex digest、ULID 假 id、量级值 `M10000`、连续缩写
   `M3U8` / `B2B` / `HTTP2`、tier 契约 key `T1..T4`、`utf8` / `h264` / `v2`。
3. fail-closed：扫描根缺失或任一扫描面命中 0 个对象即阻断，空扫描不得通过。
4. 当前树 strict-zero：真实 `quwoquan_service` 树零违规，且门禁源码没有
   allowlist / baseline 逃逸入口。
5. gate 接线：`gate_repo.sh` 的 `run_service` 段执行本门禁。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GATE_PATH = (
    ROOT
    / "quwoquan_service/scripts/verify/structure/verify_stage_name_identifiers.py"
)
GATE_REPO_PATH = ROOT / "quwoquan_ops/gate/gate_repo.sh"
GATE_COMMAND = (
    "python3 quwoquan_service/scripts/verify/structure/"
    "verify_stage_name_identifiers.py"
)


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_stage_name_identifiers", GATE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("verify_stage_name_identifiers", module)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


class StageTokenJudgementTest(unittest.TestCase):
    """判定规则本身：历史违规命中，合法形态不误报。"""

    def test_historical_violations_are_detected(self) -> None:
        for identifier in (
            "m2_app_message_min.json",
            "m2_assistant_stream_sequence_min.json",
            "m8_skill_subscription_active.json",
            "m9_p0_replay_cases.json",
            "assistant_m2_contract__local_contract_test.go",
            "m11_local_scenario__local_contract_test.go",
            "TestAssistantM2ContractSchemasGovernance",
            "assertM2FieldsGovernance",
            "TestAssistantSessionM11LocalScenarioApplicationPort",
            "user_m9",
            "evt_m2_001",
            "trace_m2_turn_min",
            "m9_daily_assistant_morning",
            "b10_backfill",
            "phase0_bootstrap.py",
            "pre_acquisition_handoff_phase1.py",
            "part3_worker",
        ):
            with self.subTest(identifier=identifier):
                self.assertTrue(
                    gate.stage_tokens(identifier),
                    f"{identifier!r} 是阶段名标识，必须被判定命中",
                )

    def test_legitimate_identifiers_are_not_flagged(self) -> None:
        for identifier in (
            # 量级/容量语义：序号 ≥3 位不是阶段名。
            "M10000",
            "M10000_PLUS",
            "20260720--travel-video-m10000--china--scale-903",
            # 连续大写缩写整体成段。
            "M3U8",
            "B2B",
            "HTTP2Client",
            # hex digest / asset id 片段。
            "a106fb9e0332be5cc0cb6142faba42df08e0a3d274085684ee87ca590e5b1cc6",
            "photo-1500530855697-b586d89ba3ee",
            "峨眉山_detail_2_6b16553b",
            "u_1469033011854-3a045667b738",
            # ULID / base32 假 id：无分隔符不成 token。
            "msg_01J8DAILY00000000000001",
            # tier 契约 key 与特性树子句锚点：t 前缀不在闭集。
            "valueTierWeights",
            "T1",
            "gwt-004.t2",
            # 版本号与外部格式。
            "v2",
            "utf8",
            "h264",
            # 行为命名后的现名。
            "wire_min_app_message.json",
            "official_skill_proactive_replay_cases.json",
            "local_scenario_application_port__local_contract_test.go",
            "TestAssistantContractSchemaFieldGovernance",
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(
                    gate.stage_tokens(identifier),
                    [],
                    f"{identifier!r} 是合法标识，不得误报",
                )


class ScanSurfacesTest(unittest.TestCase):
    """四个扫描面各自都能拦下新增阶段名。"""

    def _minimal_clean_tree(self, root: Path) -> None:
        """每个扫描面至少一个受检对象，满足 fail-closed 的非空要求。"""
        tests_dir = root / "services/foo-service/tests/local_contract/foo/bar"
        tests_dir.mkdir(parents=True)
        (tests_dir / "behavior__local_contract_test.go").write_text(
            "package local_contract\n\nfunc TestFooBehavior(t *testing.T) {}\n",
            encoding="utf-8",
        )
        fixtures = root / "services/foo-service/tests/support/contract_fixtures"
        fixtures.mkdir(parents=True)
        (fixtures / "wire_min_foo.json").write_text(
            '{"fooId": "foo_001"}\n', encoding="utf-8"
        )
        contracts = root / "services/foo-service/contracts/foo/bar"
        contracts.mkdir(parents=True)
        (contracts / "schema.yaml").write_text(
            "fields:\n  - name: fooId\n    type: string\n", encoding="utf-8"
        )

    def test_clean_tree_passes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._minimal_clean_tree(root)
            self.assertEqual(gate.scan(root), [])

    def test_each_surface_blocks_new_stage_names(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._minimal_clean_tree(root)
            fixtures = root / "services/foo-service/tests/support/contract_fixtures"
            # 路径面：阶段名文件名。
            (fixtures / "m9_p0_replay_cases.json").write_text(
                "{}\n", encoding="utf-8"
            )
            # 测试标识面：阶段名测试函数。
            tests_dir = root / "services/foo-service/tests/local_contract/foo/bar"
            (tests_dir / "governance__local_contract_test.go").write_text(
                "package local_contract\n\n"
                "func TestFooM2ContractGovernance(t *testing.T) {}\n",
                encoding="utf-8",
            )
            # JSON 面：阶段名 key 与标识值。
            (fixtures / "wire_min_bar.json").write_text(
                '{"m8_case": "user_m9"}\n', encoding="utf-8"
            )
            # schema key 面：契约字段名。
            contracts = root / "services/foo-service/contracts/foo/bar"
            (contracts / "extra.yaml").write_text(
                "phase1_field: value\n", encoding="utf-8"
            )

            violations = gate.scan(root)

            self.assertTrue(
                any(v.startswith("path: ") and "m9_p0_replay_cases" in v for v in violations),
                violations,
            )
            self.assertTrue(
                any(
                    v.startswith("test-identifier: ")
                    and "TestFooM2ContractGovernance" in v
                    for v in violations
                ),
                violations,
            )
            self.assertTrue(
                any(v.startswith("json-key: ") and "m8_case" in v for v in violations),
                violations,
            )
            self.assertTrue(
                any(v.startswith("json-value: ") and "user_m9" in v for v in violations),
                violations,
            )
            self.assertTrue(
                any(
                    v.startswith("schema-key: ") and "phase1_field" in v
                    for v in violations
                ),
                violations,
            )

    def test_missing_or_empty_scan_root_fails_closed(self) -> None:
        import tempfile

        with self.assertRaises(gate.ScanRootUnusable):
            gate.scan(Path("/nonexistent/stage-name-scan-root"))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(gate.ScanRootUnusable):
                gate.scan(Path(temporary))

    def test_missing_surface_fails_closed(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # 只有普通文件，没有测试/JSON/契约面。
            (root / "readme.txt").write_text("hello\n", encoding="utf-8")
            with self.assertRaises(gate.ScanRootUnusable):
                gate.scan(root)


class RepositoryStrictZeroTest(unittest.TestCase):
    """当前树零违规、无 allowlist、gate 链接线存在。"""

    def test_repository_service_tree_is_strict_zero(self) -> None:
        self.assertEqual(gate.main([]), 0)

    def test_gate_source_has_no_allowlist_or_baseline_escape(self) -> None:
        """零容忍：门禁不得携带豁免数据结构或基线读写入口。"""
        source = GATE_PATH.read_text(encoding="utf-8")
        for token in (
            "ALLOWLIST",
            "--allowlist",
            "--write-baseline",
            "def load_baseline",
            "def write_baseline",
            "BASELINE_PATH",
        ):
            self.assertNotIn(token, source)

    def test_gate_repo_wires_scanner_in_run_service(self) -> None:
        source = GATE_REPO_PATH.read_text(encoding="utf-8")
        self.assertEqual(source.count(GATE_COMMAND), 1)
        service_segment = source[
            source.index("\nrun_service() {") : source.index("\nrun_app() {")
        ]
        self.assertIn(GATE_COMMAND, service_segment)


if __name__ == "__main__":
    unittest.main()
