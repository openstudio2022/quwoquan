# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-007
# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-004
#
# 官网网页版下载安装闭环 runner 的 download_verify 与 CaseResult 契约：
# URL 来源、SHA-256、签名证书摘要、包名比对必须与 latest.json 发布事实
# 同源；phases[] 记录 firstFailedPhaseId 且失败不得被后续成功覆盖。

import argparse
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

APP_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(APP_DIR / "scripts/device"))

import web_download_install_uat as runner


_APK_BYTES = b"official-web-apk-bytes"
_APK_SHA256 = hashlib.sha256(_APK_BYTES).hexdigest()
_CERTIFICATE = "c" * 64
_PROD_PACKAGE = runner.application_id_for("android", "prod", "release")


def _latest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "latestVersion": "1.8.2",
        "latestBuild": "18201",
        "apkUrl": "https://cdn.quwoquan.example/download/android/1.8.2/18201/quwoquan-18201.apk",
        "apkSHA256": _APK_SHA256,
        "apkSigningCertificateSHA256": _CERTIFICATE,
        "packageName": _PROD_PACKAGE,
        "minAndroidVersion": "26",
    }
    payload.update(overrides)
    return payload


def _write_apk(url: str, destination: Path) -> None:
    del url
    destination.write_bytes(_APK_BYTES)


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "download_base_url": "https://download.quwoquan.example",
        "device_id": "",
        "download_only": True,
        "upgrade": False,
        "skip_signature_verify": False,
        "output_dir": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class WebDownloadVerifyContractTest(unittest.TestCase):
    def test_download_verify_binds_sha256_signature_and_package_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.object(runner, "_fetch_json", return_value=_latest()), \
                    mock.patch.object(runner, "_download_file", _write_apk), \
                    mock.patch.object(
                        runner,
                        "_apksigner_certificate_sha256",
                        return_value=_CERTIFICATE,
                    ):
                evidence = runner.run_download_verify(
                    "https://download.quwoquan.example",
                    Path(temporary_dir),
                )

        self.assertEqual(evidence["apkSha256"], _APK_SHA256)
        self.assertEqual(evidence["packageName"], _PROD_PACKAGE)
        self.assertTrue(evidence["signature"]["verified"])
        self.assertEqual(evidence["signature"]["certificateSha256"], _CERTIFICATE)
        self.assertEqual(
            evidence["latestUrl"],
            "https://download.quwoquan.example/download/android/latest.json",
        )

    def test_non_https_download_base_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with self.assertRaises(runner.PhaseFailure) as caught:
                runner.run_download_verify(
                    "http://download.quwoquan.example",
                    Path(temporary_dir),
                )
        self.assertEqual(caught.exception.failure_code, "DOWNLOAD_URL_NOT_HTTPS")

    def test_sha256_mismatch_fails_instead_of_installing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.object(
                runner,
                "_fetch_json",
                return_value=_latest(apkSHA256="0" * 64),
            ), mock.patch.object(runner, "_download_file", _write_apk):
                with self.assertRaises(runner.PhaseFailure) as caught:
                    runner.run_download_verify(
                        "https://download.quwoquan.example",
                        Path(temporary_dir),
                    )
        self.assertEqual(caught.exception.failure_code, "APK_SHA256_MISMATCH")

    def test_package_name_must_match_canonical_prod_release_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.object(
                runner,
                "_fetch_json",
                return_value=_latest(packageName="com.example.other"),
            ):
                with self.assertRaises(runner.PhaseFailure) as caught:
                    runner.run_download_verify(
                        "https://download.quwoquan.example",
                        Path(temporary_dir),
                    )
        self.assertEqual(caught.exception.failure_code, "PACKAGE_NAME_MISMATCH")

    def test_signing_certificate_mismatch_is_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.object(runner, "_fetch_json", return_value=_latest()), \
                    mock.patch.object(runner, "_download_file", _write_apk), \
                    mock.patch.object(
                        runner,
                        "_apksigner_certificate_sha256",
                        return_value="d" * 64,
                    ):
                with self.assertRaises(runner.PhaseFailure) as caught:
                    runner.run_download_verify(
                        "https://download.quwoquan.example",
                        Path(temporary_dir),
                    )
        self.assertEqual(
            caught.exception.failure_code, "APK_SIGNING_CERTIFICATE_MISMATCH"
        )

    def test_incomplete_latest_manifest_is_blocked(self) -> None:
        incomplete = _latest()
        incomplete.pop("apkSigningCertificateSHA256")
        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.object(runner, "_fetch_json", return_value=incomplete):
                with self.assertRaises(runner.PhaseFailure) as caught:
                    runner.run_download_verify(
                        "https://download.quwoquan.example",
                        Path(temporary_dir),
                    )
        self.assertEqual(
            caught.exception.failure_code, "LATEST_MANIFEST_INCOMPLETE"
        )


class WebDownloadCaseResultContractTest(unittest.TestCase):
    def test_download_only_case_result_keeps_device_phases_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.object(runner, "_fetch_json", return_value=_latest()), \
                    mock.patch.object(runner, "_download_file", _write_apk), \
                    mock.patch.object(
                        runner,
                        "_apksigner_certificate_sha256",
                        return_value=_CERTIFICATE,
                    ):
                case_result = runner.execute_case(
                    _args(output_dir=temporary_dir)
                )

            report = json.loads(
                (Path(temporary_dir) / "case_result.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(case_result["status"], "download_verified_only")
        self.assertEqual(case_result["automationTier"], "A2")
        self.assertEqual(case_result["channelId"], "official_web")
        self.assertEqual(case_result["firstFailedPhaseId"], "")
        phase_status = {
            row["phaseId"]: row["status"] for row in case_result["phases"]
        }
        self.assertEqual(phase_status["download_verify"], "passed")
        for phase_id in ("install", "launch", "first_frame"):
            self.assertEqual(phase_status[phase_id], "skipped")
        self.assertEqual(report["specRefs"], list(runner.SPEC_REFS))

    def test_download_verify_failure_is_first_failed_and_not_overwritten(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.object(
                runner,
                "_fetch_json",
                return_value=_latest(apkSHA256="0" * 64),
            ), mock.patch.object(runner, "_download_file", _write_apk):
                case_result = runner.execute_case(
                    _args(output_dir=temporary_dir, device_id="emulator-5554")
                )

        self.assertEqual(case_result["status"], "failed")
        self.assertEqual(case_result["firstFailedPhaseId"], "download_verify")
        download_row = next(
            row
            for row in case_result["phases"]
            if row["phaseId"] == "download_verify"
        )
        self.assertEqual(download_row["status"], "failed")
        self.assertEqual(download_row["failureCode"], "APK_SHA256_MISMATCH")
        for row in case_result["phases"]:
            if row["phaseId"] != "download_verify":
                self.assertEqual(row["status"], "skipped")

    def test_upgrade_case_uses_in_place_install_and_distinct_case_id(self) -> None:
        adb_calls: list[list[str]] = []

        def fake_run_adb(device_id: str, *arguments: str):
            adb_calls.append([device_id, *arguments])
            command = " ".join(arguments)
            if command.startswith("shell pm path"):
                return mock.Mock(returncode=0, stdout="package:/data/app/base.apk\n", stderr="")
            if command.startswith("install"):
                return mock.Mock(returncode=0, stdout="Success\n", stderr="")
            if command.startswith("shell am start"):
                return mock.Mock(returncode=0, stdout="Status: ok\n", stderr="")
            if command.startswith("logcat -d"):
                return mock.Mock(
                    returncode=0,
                    stdout=f"I/ActivityTaskManager: Displayed {_PROD_PACKAGE}/.MainActivity\n",
                    stderr="",
                )
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as temporary_dir:
            with mock.patch.object(runner, "_fetch_json", return_value=_latest()), \
                    mock.patch.object(runner, "_download_file", _write_apk), \
                    mock.patch.object(
                        runner,
                        "_apksigner_certificate_sha256",
                        return_value=_CERTIFICATE,
                    ), mock.patch.object(runner, "_run_adb", fake_run_adb):
                case_result = runner.execute_case(
                    _args(
                        output_dir=temporary_dir,
                        device_id="emulator-5554",
                        download_only=False,
                        upgrade=True,
                    )
                )

        self.assertEqual(case_result["status"], "passed")
        self.assertEqual(case_result["caseId"], "web_download_install_upgrade")
        install_row = next(
            row for row in case_result["phases"] if row["phaseId"] == "install"
        )
        self.assertEqual(
            install_row["evidence"]["installMode"], "upgrade_in_place"
        )
        # 覆盖升级不得先卸载旧版本。
        self.assertFalse(
            any(call[1] == "uninstall" for call in adb_calls),
            adb_calls,
        )


if __name__ == "__main__":
    unittest.main()
