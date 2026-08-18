"""store-channels 渠道矩阵与准入裁决的 local_contract。

绑定 deliver-deploy-prod-pipeline DEC-004 与 AppRoot 市场分发验收：
- 渠道矩阵只从 canonical `distribution_channels` metadata 生成。
- 凭据缺失或平台 Prod 正式 ID 未登记时渠道保持 GATE_BLOCK，
  不得伪造市场证据；一个渠道的裁决不得替代另一渠道。
"""

from __future__ import annotations

import argparse
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.commands.store_channels import command_store_channels

_EXPECTED_CHANNELS = {
    "apple_app_store",
    "apple_testflight",
    "huawei_appgallery",
    "xiaomi_getapps",
    "oppo_market",
    "vivo_market",
    "tencent_myapp",
    "official_web",
}

_CREDENTIAL_ENVS = (
    "QWQ_APPLE_ASC_API_KEY_PATH",
    "QWQ_HUAWEI_AGC_API_CLIENT_PATH",
    "QWQ_XIAOMI_DEV_CREDENTIAL_PATH",
    "QWQ_OPPO_DEV_CREDENTIAL_PATH",
    "QWQ_VIVO_DEV_CREDENTIAL_PATH",
    "QWQ_TENCENT_MYAPP_CREDENTIAL_PATH",
    "QWQ_OFFICIAL_WEB_DEPLOY_CREDENTIAL_PATH",
)


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {"app_platform": "all", "channel": ""}
    values.update(overrides)
    return argparse.Namespace(**values)


def _without_credentials() -> mock._patch_dict:
    cleaned = {name: "" for name in _CREDENTIAL_ENVS}
    return mock.patch.dict(os.environ, cleaned, clear=False)


class StoreChannelMatrixTest(unittest.TestCase):
    def test_matrix_lists_every_declared_channel_with_complete_row(self) -> None:
        with _without_credentials():
            result = command_store_channels(_args())

        self.assertEqual(result["exitCode"], 0)
        rows = {row["channelId"]: row for row in result["channels"]}
        self.assertEqual(set(rows), _EXPECTED_CHANNELS)
        for row in rows.values():
            for field in (
                "platform",
                "uploadFormat",
                "distributionClass",
                "storeSigningCustodian",
                "readback",
                "automationTier",
                "credentialOwner",
                "credentialEnv",
                "applicationId",
            ):
                self.assertTrue(str(row[field]).strip(), f"{row['channelId']}:{field}")
            self.assertIn(row["automationTier"], {"A1", "A2", "A3"})

    def test_platform_filter_returns_only_that_platform(self) -> None:
        with _without_credentials():
            result = command_store_channels(_args(app_platform="ios"))

        platforms = {row["platform"] for row in result["channels"]}
        self.assertEqual(platforms, {"ios"})
        self.assertEqual(
            {row["channelId"] for row in result["channels"]},
            {"apple_app_store", "apple_testflight"},
        )

    def test_missing_credential_blocks_the_channel_gate(self) -> None:
        with _without_credentials():
            result = command_store_channels(_args(channel="huawei_appgallery"))

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(result["channel"]["status"], "blocked")
        self.assertTrue(
            any(
                "QWQ_HUAWEI_AGC_API_CLIENT_PATH" in reason
                for reason in result["channel"]["blockedReasons"]
            )
        )

    def test_android_store_channel_is_ready_with_registered_id_and_credential(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            credential = Path(temporary_dir) / "agc.json"
            credential.write_text("{}", encoding="utf-8")
            with _without_credentials(), mock.patch.dict(
                os.environ,
                {"QWQ_HUAWEI_AGC_API_CLIENT_PATH": str(credential)},
                clear=False,
            ):
                result = command_store_channels(_args(channel="huawei_appgallery"))

        # Android Prod 正式 ID 是已登记外部事实；凭据就绪时渠道必须放行。
        self.assertTrue(result["channel"]["registeredProductionId"])
        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(result["channel"]["status"], "ready")
        self.assertEqual(
            result["channel"]["applicationId"], "com.quwoquan.quwoquan_app"
        )

    def test_unregistered_ios_production_id_blocks_store_even_with_credential(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            credential = Path(temporary_dir) / "asc.json"
            credential.write_text("{}", encoding="utf-8")
            with _without_credentials(), mock.patch.dict(
                os.environ,
                {"QWQ_APPLE_ASC_API_KEY_PATH": str(credential)},
                clear=False,
            ):
                result = command_store_channels(_args(channel="apple_app_store"))

        self.assertEqual(result["exitCode"], 2)
        self.assertTrue(
            any(
                "not a registered external fact" in reason
                for reason in result["channel"]["blockedReasons"]
            )
        )

    def test_one_channel_gate_never_substitutes_another(self) -> None:
        """华为凭据就绪不得让其他市场渠道的准入被替代。"""
        with tempfile.TemporaryDirectory() as temporary_dir:
            credential = Path(temporary_dir) / "agc.json"
            credential.write_text("{}", encoding="utf-8")
            with _without_credentials(), mock.patch.dict(
                os.environ,
                {"QWQ_HUAWEI_AGC_API_CLIENT_PATH": str(credential)},
                clear=False,
            ):
                huawei = command_store_channels(_args(channel="huawei_appgallery"))
                xiaomi = command_store_channels(_args(channel="xiaomi_getapps"))

        self.assertEqual(huawei["exitCode"], 0)
        self.assertEqual(xiaomi["exitCode"], 2)
        self.assertEqual(xiaomi["channel"]["status"], "blocked")

    def test_unknown_channel_is_rejected(self) -> None:
        result = command_store_channels(_args(channel="google_play"))

        self.assertEqual(result["exitCode"], 2)
        self.assertIn("unknown distribution channel", result["summary"])


if __name__ == "__main__":
    unittest.main()
