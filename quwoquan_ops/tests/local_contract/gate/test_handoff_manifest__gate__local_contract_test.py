"""verify_handoff_manifest 的负例合约。

交接单是 HANDOFF 的物理形态；校验器一旦永远转绿，断链与悬空未决项就会
重新以聊天文本形态逃过下一轮 RESOLVE。每类缺陷都必须有能让它变红的负例。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[4]
_GATE = _REPO_ROOT / "quwoquan_ops/gate/verify_handoff_manifest.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_handoff_manifest", _GATE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALID = """# 轮次交接单

- intent 终版：示例轮次（范围变更：无）
- 新轮触发判定：不触发（依据：判据全绿）

## EvidenceFingerprint

- handoff_ref: `handoff-ref-v1:sha256:1111111111111111111111111111111111111111111111111111111111111111:sha256:2222222222222222222222222222222222222222222222222222222222222222`
- payload_ref: `.qwq_output/env/repo/runs/handoff/nonexistent/payload.json`
- ref: `evidence-fingerprint-v1:sha256:5842e2f11a8de997f4efc4f6e3e0e380a61bc29632f9f94c27170223134862a6`
- digest: `sha256:5842e2f11a8de997f4efc4f6e3e0e380a61bc29632f9f94c27170223134862a6`
- source_head: `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`
- source_fingerprint: `sha256:5842e2f11a8de997f4efc4f6e3e0e380a61bc29632f9f94c27170223134862a6`
- captured_metadata: `{"captured_at":"2026-08-29T12:00:00+08:00","captured_by":"handoff-fixture"}`
- freshness: `fresh`
- recovery_token: `rerun_evidence_for_new_fingerprint`
- digest_payload: `{"schema_version":2,"serialization_version":"evidence-fingerprint-v1","git":{"head_sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","merge_base_sha":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},"workspace":{"tracked_digest":"sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","untracked_digest":"sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","deleted_digest":"sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","renamed_digest":"sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","symlink_digest":"sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"},"assets":{"canonical_assets_digest":"sha256:fb6865ad9685c5e973a0b199adee4f76d6590dfa8d055b3ea7c9bc848774334b","review_assets_digest":"sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"},"execution":{"commands_digest":"sha256:4f7ee5959ab8df773923e454f942f1bdd8ed3793e5dc9c8ede9df27fb5f221a8","toolchain_digest":"sha256:110e293d95afee0bb3c43710acc565e856a0cd081009f8d549901a4c567b2fbe","provider_digest":"sha256:4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945","generator_digest":"sha256:b086de7b32510701e873f3d4ae742917ca1cc1141ffe4a8387d604ef474ef9e4"}}`

## 产出物

- 实现增量一份 + POST 评审结论

## 未决项去向

- 谓词单轨缺口（一类：已全仓 AST 扫描收敛并加防回潮锁）：转 `OPEN-007`
- 组网知识升格（孤例）：下一工作流 `prd` 承接

## 唯一合法下游

- plan-next；PRE 输入：本单证据链与 OPEN 变化

## 证据链

- `make verify-feature-tree` exit=0 2026-08-25T12:00:00+08:00 abc1234
"""

_CURRENT_HEAD = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, check=True, capture_output=True, text=True
).stdout.strip()
VALID = VALID.replace("`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`", f"`{_CURRENT_HEAD}`", 1)


class HandoffManifestGateTest(unittest.TestCase):
    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/spec.md#sit-002.t1

    def setUp(self) -> None:
        self.module = _load_gate()

    def test_valid_manifest_passes(self) -> None:
        with mock.patch.object(
            self.module.handoff_consumer,
            "_load_json_ref",
            side_effect=ValueError("fixture payload omitted"),
        ):
            issues = self.module.validate(VALID, "m.md")
        self.assertEqual(
            [issue for issue in issues if "canonical handoff payload stale" not in issue],
            [],
        )

    def test_detects_missing_constitution_section(self) -> None:
        text = VALID.replace("## 唯一合法下游", "## 别的段")
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("缺 required 段落「## 唯一合法下游」" in i for i in issues), issues)

    def test_detects_missing_head_field(self) -> None:
        text = VALID.replace("- 新轮触发判定：不触发（依据：判据全绿）", "")
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("缺头部字段「新轮触发判定」" in i for i in issues), issues)

    def test_detects_dangling_pending_item(self) -> None:
        """未决项没有三向裁决就是悬空——历史上缺口悬空到下轮才暴露的主形态。"""
        text = VALID.replace("转 `OPEN-007`", "还没想好怎么办")
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("未决项悬空" in i for i in issues), issues)

    def test_detects_pending_item_without_generalization(self) -> None:
        """有裁决但缺「孤例/一类」泛化判定——举一反三必须留痕，不许只靠自觉。"""
        text = VALID.replace(
            "- 组网知识升格（孤例）：下一工作流 `prd` 承接",
            "- 组网知识升格：下一工作流 `prd` 承接",
        )
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("缺泛化判定" in i for i in issues), issues)
        self.assertFalse(any("未决项悬空" in i for i in issues), issues)

    def test_generalization_marker_does_not_match_incidental_substring(self) -> None:
        """「统一类型」含「一类」子串，但不是结构化泛化判定，不得假通过。"""
        text = VALID.replace(
            "- 组网知识升格（孤例）：下一工作流 `prd` 承接",
            "- 组网知识升格按统一类型处理：下一工作流 `prd` 承接",
        )
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("缺泛化判定" in i for i in issues), issues)

    def test_detects_evidence_without_fields(self) -> None:
        """无退出码/时间戳/SHA 的证据无法复跑，只能被转抄——必须拦。"""
        text = VALID.replace(
            "- `make verify-feature-tree` exit=0 2026-08-25T12:00:00+08:00 abc1234",
            "- 测试都跑过了，全绿",
        )
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("证据条目缺字段" in i for i in issues), issues)

    def test_detects_empty_evidence_chain(self) -> None:
        text = VALID.replace(
            "- `make verify-feature-tree` exit=0 2026-08-25T12:00:00+08:00 abc1234",
            "",
        )
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("证据链为空" in i for i in issues), issues)

    def test_detects_missing_canonical_fingerprint(self) -> None:
        text = VALID.replace("- ref: `evidence-fingerprint-v1:", "- legacy_ref: `evidence-fingerprint-v1:")
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("EvidenceFingerprint 字段闭集漂移" in i for i in issues), issues)

    def test_detects_stale_source_head(self) -> None:
        issues = self.module.validate(
            VALID.replace(
                f"- source_head: `{_CURRENT_HEAD}`",
                f"- source_head: `{'0' * 40}`",
            ),
            "m.md",
        )
        self.assertTrue(any("source_head 已 stale" in i for i in issues), issues)

    def test_detects_stale_evidence(self) -> None:
        issues = self.module.validate(
            VALID.replace("- freshness: `fresh`", "- freshness: `stale`"),
            "m.md",
        )
        self.assertTrue(any("evidence freshness" in i for i in issues), issues)

    def test_detects_recovery_token_failure(self) -> None:
        issues = self.module.validate(
            VALID.replace(
                "- recovery_token: `rerun_evidence_for_new_fingerprint`",
                "- recovery_token: `continue_anyway`",
            ),
            "m.md",
        )
        self.assertTrue(any("recovery_token 非法" in i for i in issues), issues)

    def test_detects_digest_payload_byte_change(self) -> None:
        text = VALID.replace('"provider_digest":"sha256:', '"provider_digest":"sha256:0', 1)
        issues = self.module.validate(text, "m.md")
        self.assertTrue(any("digest_payload 与 canonical digest 不一致" in i for i in issues), issues)

    def test_accepts_explicit_no_pending_declaration(self) -> None:
        text = VALID.replace(
            "- 谓词单轨缺口（一类：已全仓 AST 扫描收敛并加防回潮锁）：转 `OPEN-007`\n"
            "- 组网知识升格（孤例）：下一工作流 `prd` 承接",
            "- 无未决项",
        )
        issues = self.module.validate(text, "m.md")
        self.assertEqual(
            [issue for issue in issues if "canonical handoff payload stale" not in issue],
            [],
        )


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
