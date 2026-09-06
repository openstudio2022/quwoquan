"""stackctl `store-distribution` 渠道分发回执的 local_contract 测试。

绑定 deliver-deploy-prod-pipeline DEC-007：分发回执由 CI/CD 分发控制面
唯一拥有、append-only、逐渠道独立；同一 candidate 的全部 android 渠道
必须引用同一 reviewed release APK source digest（fan-out 不复制不重编），
blocked 渠道与缺失 readback 证据不得伪造分发事实。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.commands.store_distribution import (
    command_store_distribution,
)

_CANDIDATE = "sha256:" + "a" * 64
_APK_DIGEST = "sha256:" + "b" * 64
_OTHER_DIGEST = "sha256:" + "c" * 64


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "channel": "vivo_market",
        "candidate_id": _CANDIDATE,
        "artifact_digest": _APK_DIGEST,
        "display_version": "1.4.0",
        "build_number": "58",
        "phase": "uploaded",
        "platform_record_id": "vivo-app-10001",
        "readback_evidence": "",
        "list_receipts": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class StackctlStoreDistributionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        root = Path(self._directory.name)
        self.receipt_root = root / "receipts" / "store-distribution"
        evidence = root / "readback.json"
        evidence.write_text('{"status":"ok"}', encoding="utf-8")
        self.evidence_path = str(evidence)
        patcher_root = mock.patch(
            "quwoquan_ops.cli.commands.store_distribution._receipt_root",
            return_value=self.receipt_root,
        )
        patcher_root.start()
        self.addCleanup(patcher_root.stop)
        # 凭据在位的渠道准入门：指向真实存在的凭据文件。
        credential = root / "credential.json"
        credential.write_text("{}", encoding="utf-8")
        env = {
            "QWQ_VIVO_DEV_CREDENTIAL_PATH": str(credential),
            "QWQ_OPPO_DEV_CREDENTIAL_PATH": str(credential),
            "QWQ_OFFICIAL_WEB_DEPLOY_CREDENTIAL_PATH": str(credential),
        }
        patcher_env = mock.patch.dict("os.environ", env)
        patcher_env.start()
        self.addCleanup(patcher_env.stop)

    def _record(self, **overrides: object) -> dict[str, object]:
        overrides.setdefault("readback_evidence", self.evidence_path)
        return command_store_distribution(_args(**overrides))

    def test_ready_channel_records_append_only_receipt(self) -> None:
        result = self._record()
        self.assertEqual(result["exitCode"], 0, result)
        receipt = result["receipt"]
        self.assertEqual(receipt["schema"], "app-distribution-receipt")
        self.assertEqual(receipt["channelId"], "vivo_market")
        self.assertEqual(receipt["applicationId"], "com.leadwise.quwoquan")
        self.assertEqual(receipt["readbackMethod"], "manual_with_machine_receipt")
        path = Path(str(result["receiptPath"]))
        self.assertTrue(path.is_file())
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored, receipt)
        # 同一回执重放幂等：不产生第二个文件，不改写既有回执。
        replay = self._record()
        self.assertEqual(replay["exitCode"], 0, replay)
        files = list(self.receipt_root.rglob("*.json"))
        self.assertEqual(len(files), 1, files)

    def test_blocked_channel_must_not_fabricate_distribution_facts(self) -> None:
        # xiaomi 凭据未设置 → store-channels 准入门 GATE_BLOCK。
        result = self._record(channel="xiaomi_getapps")
        self.assertEqual(result["exitCode"], 2, result)
        self.assertIn("GATE_BLOCK", str(result["summary"]))
        self.assertFalse(self.receipt_root.exists())

    def test_missing_readback_evidence_is_blocked(self) -> None:
        result = command_store_distribution(
            _args(readback_evidence="/nonexistent/readback.json")
        )
        self.assertEqual(result["exitCode"], 2)
        self.assertTrue(
            any("readback-evidence" in item for item in result["details"]),
            result["details"],
        )

    def test_android_fanout_requires_one_apk_digest_per_candidate(self) -> None:
        first = self._record(channel="vivo_market")
        self.assertEqual(first["exitCode"], 0, first)
        # 另一 android 渠道复用同一 candidate + 同一 APK digest：允许。
        same = self._record(
            channel="oppo_market", platform_record_id="oppo-app-2"
        )
        self.assertEqual(same["exitCode"], 0, same)
        # 同一 candidate 换 digest：fan-out violation，阻断。
        conflict = self._record(
            channel="oppo_market",
            artifact_digest=_OTHER_DIGEST,
            platform_record_id="oppo-app-2",
        )
        self.assertEqual(conflict["exitCode"], 2, conflict)
        self.assertIn("fan-out violation", str(conflict["summary"]))

    def test_non_upload_phase_requires_prior_uploaded_receipt(self) -> None:
        premature = self._record(phase="published")
        self.assertEqual(premature["exitCode"], 2, premature)
        self.assertIn("uploaded", str(premature["summary"]))
        uploaded = self._record(phase="uploaded")
        self.assertEqual(uploaded["exitCode"], 0, uploaded)
        published = self._record(phase="published")
        self.assertEqual(published["exitCode"], 0, published)
        # 逐渠道独立：vivo 的 uploaded 不能替 oppo 解锁 published。
        other = self._record(
            channel="oppo_market",
            phase="published",
            platform_record_id="oppo-app-2",
        )
        self.assertEqual(other["exitCode"], 2, other)

    def test_invalid_inputs_are_typed_blockers(self) -> None:
        result = command_store_distribution(
            _args(
                channel="unknown_market",
                candidate_id="not-a-digest",
                artifact_digest="",
                display_version="",
                build_number="",
                phase="shipped",
                platform_record_id="",
                readback_evidence=self.evidence_path,
            )
        )
        self.assertEqual(result["exitCode"], 2)
        details = " ".join(str(item) for item in result["details"])
        for marker in (
            "--channel",
            "--candidate-id",
            "--artifact-digest",
            "--display-version",
            "--phase",
            "--platform-record-id",
        ):
            self.assertIn(marker, details, marker)

    def test_list_receipts_filters_by_channel(self) -> None:
        self._record(channel="vivo_market")
        self._record(channel="oppo_market", platform_record_id="oppo-app-2")
        all_rows = command_store_distribution(
            _args(list_receipts=True, channel="")
        )
        self.assertEqual(all_rows["exitCode"], 0)
        self.assertEqual(len(all_rows["receipts"]), 2)
        vivo_rows = command_store_distribution(
            _args(list_receipts=True, channel="vivo_market")
        )
        self.assertEqual(len(vivo_rows["receipts"]), 1)
        self.assertEqual(
            vivo_rows["receipts"][0]["channelId"], "vivo_market"
        )


if __name__ == "__main__":
    unittest.main()
