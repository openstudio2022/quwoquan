from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.local_provider_credentials import (
    _required_material_for_environment,
    load_protected_provider_environment,
    provider_environment_reference_names,
)


def _material(environment: str, *, secret_root: Path | None = None) -> dict[str, str]:
    endpoint_keys, secret_keys = _required_material_for_environment(environment)
    material = {
        key: (
            f"https://provider.nonprod.test/{key.lower()}"
            if key in endpoint_keys
            else f"protected-{key.lower()}"
        )
        for key in endpoint_keys | secret_keys
    }
    if secret_root is not None:
        for key in secret_keys:
            if not key.endswith("_FILE"):
                continue
            path = secret_root / key.lower()
            path.write_text("protected\n", encoding="utf-8")
            path.chmod(0o600)
            material[key] = str(path)
    return material


class LocalProviderCredentialsSecurityLocalContractTest(unittest.TestCase):
    def test_reference_inventory_does_not_read_protected_values(self) -> None:
        endpoint_keys, secret_keys = provider_environment_reference_names("alpha")
        self.assertIn("ASSISTANT_MODEL_COMPLETION_URL", endpoint_keys)
        self.assertIn("ASSISTANT_MODEL_API_KEY", secret_keys)

    def test_nonprod_login_requires_sms_material_but_not_optional_identity_material(self) -> None:
        endpoint_keys, secret_keys = _required_material_for_environment("beta")

        self.assertIn("INTEGRATION_SMS_ENDPOINT", endpoint_keys)
        self.assertTrue(
            {
                "INTEGRATION_SMS_TOKEN",
                "OTP_CODE_REF_KEYS_JSON",
                "INTEGRATION_SERVICE_MTLS_CA_FILE",
                "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE",
                "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE",
            }.issubset(secret_keys)
        )
        self.assertTrue(
            {
                "ALIYUN_DYPNS_ACCESS_KEY_ID",
                "ALIYUN_DYPNS_ACCESS_KEY_SECRET",
                "WECHAT_OAUTH_APP_SECRET",
                "ALIPAY_OAUTH_APP_PRIVATE_KEY_PEM",
            }.isdisjoint(secret_keys)
        )

    def test_loader_returns_only_preinjected_material_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            material = _material("alpha", secret_root=root)
            before = sorted(path.name for path in root.iterdir())
            values = load_protected_provider_environment(
                environment="alpha",
                target_name="alpha-local",
                source=material,
            )
            self.assertIn("CONTENT_EMBEDDING_API_KEY", values)
            self.assertIn("RTC_MEDIA_CONNECTION_URL", values)
            self.assertEqual(sorted(path.name for path in root.iterdir()), before)

    def test_missing_material_fails_closed_without_exposing_values(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "GATE_BLOCK: protected Provider material is missing",
        ) as failure:
            load_protected_provider_environment(
                environment="beta",
                target_name="beta-local",
                source={},
            )
        self.assertIn("ASSISTANT_MODEL_API_KEY", str(failure.exception))

    def test_placeholder_material_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            material = _material("gamma", secret_root=Path(temporary_dir))
            material["ASSISTANT_MODEL_COMPLETION_URL"] = "https://fixture.local/model"
            with self.assertRaisesRegex(RuntimeError, "placeholder values"):
                load_protected_provider_environment(
                    environment="gamma",
                    target_name="gamma-local",
                    source=material,
                )

    def test_target_and_environment_are_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            with self.assertRaisesRegex(ValueError, "target/environment mismatch"):
                load_protected_provider_environment(
                    environment="alpha",
                    target_name="beta-local",
                    source=_material("alpha", secret_root=Path(temporary_dir)),
                )

    def test_file_material_must_exist_and_private_keys_are_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            material = _material("beta", secret_root=root)
            material["INTEGRATION_PUSH_APNS_KEY_FILE"] = str(root / "missing.p8")
            with self.assertRaisesRegex(RuntimeError, "absolute regular file"):
                load_protected_provider_environment(
                    environment="beta",
                    target_name="beta-local",
                    source=material,
                )

            material = _material("beta", secret_root=root)
            apns_key = Path(material["INTEGRATION_PUSH_APNS_KEY_FILE"])
            apns_key.chmod(0o644)
            with self.assertRaisesRegex(RuntimeError, "owner-only"):
                load_protected_provider_environment(
                    environment="beta",
                    target_name="beta-local",
                    source=material,
                )

    def test_prod_material_is_never_loaded_by_nonprod_facade(self) -> None:
        with self.assertRaisesRegex(ValueError, "only valid for Alpha/Beta/Gamma"):
            load_protected_provider_environment(
                environment="prod",
                target_name="prod-local",
                source={},
            )


if __name__ == "__main__":
    unittest.main()
