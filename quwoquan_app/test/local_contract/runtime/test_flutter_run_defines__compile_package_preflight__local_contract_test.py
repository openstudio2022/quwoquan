#!/usr/bin/env python3
"""flutter run 编译期 define 预检门禁的 local_contract。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = (
    REPO_ROOT
    / "quwoquan_app"
    / "scripts"
    / "device" / "verify_flutter_run_defines.py"
)


def load_verifier():
    spec = importlib.util.spec_from_file_location(
        "verify_flutter_run_defines", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FlutterRunDefinesPreflightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verifier = load_verifier()

    def defines(self, **overrides: str) -> dict[str, str]:
        base = {
            "APP_RUNTIME_ENV": "gamma",
            "CLOUD_GATEWAY_BASE_URL": "https://gateway.example.com",
            "APP_LEGAL_BASE_URL": "https://legal.example.com",
            "PUBLIC_WEB_BASE_URL": "https://web.example.com",
            "MEDIA_AVATAR_CDN_BASE_URL": "https://avatar.example.com",
            "MEDIA_IMAGE_CDN_BASE_URL": "https://image.example.com",
            "MEDIA_VIDEO_CDN_BASE_URL": "https://video.example.com",
            "MEDIA_UPLOAD_BASE_URL": "https://upload.example.com",
            "RTC_MEDIA_CONNECTION_URL": "wss://rtc.example.com",
        }
        base.update(overrides)
        return base

    def test_complete_package_has_no_issues(self) -> None:
        issues = self.verifier.validate_flutter_run_defines(
            self.defines(),
            expected_env="gamma",
            platform="android",
            target="gamma-local",
            entrypoint="lib/main_prod.dart",
        )
        self.assertEqual(issues, [])

    def test_missing_runtime_env_is_reported(self) -> None:
        defines = self.defines()
        del defines["APP_RUNTIME_ENV"]
        issues = self.verifier.validate_flutter_run_defines(defines)
        self.assertIn("missing APP_RUNTIME_ENV", issues)

    def test_unknown_runtime_env_is_rejected(self) -> None:
        issues = self.verifier.validate_flutter_run_defines(
            self.defines(APP_RUNTIME_ENV="staging")
        )
        self.assertIn(
            "APP_RUNTIME_ENV must be one of alpha|beta|gamma|prod", issues
        )

    def test_every_required_define_key_is_enforced(self) -> None:
        for key in sorted(self.verifier.REQUIRED_DEFINE_KEYS - {"APP_RUNTIME_ENV"}):
            with self.subTest(key=key):
                defines = self.defines()
                del defines[key]
                issues = self.verifier.validate_flutter_run_defines(defines)
                self.assertIn(f"missing {key}", issues)

    def test_endpoint_must_be_https_origin(self) -> None:
        issues = self.verifier.validate_flutter_run_defines(
            self.defines(CLOUD_GATEWAY_BASE_URL="http://gateway.example.com")
        )
        self.assertIn(
            "CLOUD_GATEWAY_BASE_URL must be an HTTPS origin without query/fragment",
            issues,
        )

    def test_rtc_endpoint_must_be_wss_origin(self) -> None:
        issues = self.verifier.validate_flutter_run_defines(
            self.defines(RTC_MEDIA_CONNECTION_URL="https://rtc.example.com")
        )
        self.assertIn(
            "RTC_MEDIA_CONNECTION_URL must be a WSS origin without query/fragment",
            issues,
        )

    def test_target_must_agree_with_runtime_env(self) -> None:
        issues = self.verifier.validate_flutter_run_defines(
            self.defines(APP_RUNTIME_ENV="gamma"), target="alpha-local"
        )
        self.assertIn("target alpha-local requires APP_RUNTIME_ENV=alpha", issues)

    def test_entrypoint_is_the_single_prod_runner(self) -> None:
        issues = self.verifier.validate_flutter_run_defines(
            self.defines(), entrypoint="lib/main_gamma.dart"
        )
        self.assertTrue(
            any(issue.startswith("entrypoint lib/main_gamma.dart") for issue in issues)
        )

    def test_defines_digest_binds_the_selected_package(self) -> None:
        defines = self.defines()
        canonical = hashlib.sha256(
            json.dumps(
                defines, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            self.verifier.validate_flutter_run_defines(
                defines, defines_digest=f"sha256:{canonical}"
            ),
            [],
        )
        self.assertIn(
            "dart define digest does not match the selected package",
            self.verifier.validate_flutter_run_defines(
                defines, defines_digest="sha256:" + "0" * 64
            ),
        )

    def test_prod_hosted_rejects_local_transport_evidence(self) -> None:
        issues = self.verifier.validate_flutter_run_defines(
            self.defines(APP_RUNTIME_ENV="prod"),
            target="prod-hosted",
            consumer_lease_id="sha256:" + "a" * 64,
        )
        self.assertIn(
            "prod-hosted package must not contain local transport evidence", issues
        )

    def test_reverse_ports_must_match_when_transport_is_required(self) -> None:
        issues = self.verifier.validate_flutter_run_defines(
            self.defines(),
            target="gamma-local",
            transport_required=True,
            reverse_expected_ports="8080,9090",
            reverse_actual_ports="8080",
            reverse_receipt_digest="sha256:" + "b" * 64,
            consumer_lease_id="sha256:" + "c" * 64,
        )
        self.assertIn(
            "Android reverse expected/actual ports do not match", issues
        )

    def test_parses_flutter_style_define_arguments(self) -> None:
        self.assertEqual(
            self.verifier.parse_dart_define_args(
                ["--dart-define=APP_RUNTIME_ENV=gamma", "--dart-define=EMPTY="]
            ),
            {"APP_RUNTIME_ENV": "gamma", "EMPTY": ""},
        )


if __name__ == "__main__":
    unittest.main()
