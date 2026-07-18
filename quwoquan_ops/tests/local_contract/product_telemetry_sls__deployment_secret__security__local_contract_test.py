from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.lib.product_telemetry_sls import load_product_telemetry_sls


REQUIRED_VALUES = {
    "PRODUCT_OPS_SLS_REGION": "cn-test",
    "PRODUCT_OPS_SLS_ENDPOINT": "cn-test.log.example",
    "PRODUCT_OPS_SLS_PROJECT": "product-telemetry-test",
    "ALIBABA_CLOUD_ACCESS_KEY_ID": "test-key-id",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "test-key-secret",
}


class ProductTelemetrySLSDeploymentSecretSecurityLocalContractTest(unittest.TestCase):
    def test_complete_process_environment_does_not_require_a_file(self) -> None:
        bundle = load_product_telemetry_sls(
            "gamma", "gamma-local", process_environment=REQUIRED_VALUES
        )

        self.assertEqual(bundle.environment, REQUIRED_VALUES)
        self.assertIsNone(bundle.secret_path)

    def test_environment_specific_file_must_be_outside_runtime_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            path = home / ".config/quwoquan/product_telemetry_sls/beta.env"
            path.parent.mkdir(parents=True)
            path.write_text(
                "".join(f"{key}={value}\n" for key, value in REQUIRED_VALUES.items()),
                encoding="utf-8",
            )
            os.chmod(path, 0o600)

            bundle = load_product_telemetry_sls(
                "beta", "beta-local", process_environment={}, home=home
            )

        self.assertEqual(bundle.environment, REQUIRED_VALUES)
        self.assertEqual(bundle.secret_path, path)
        self.assertNotIn(".qwq_output", str(path))

    def test_missing_file_is_a_gate_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            with self.assertRaisesRegex(RuntimeError, "deployment secret is missing"):
                load_product_telemetry_sls(
                    "gamma",
                    "gamma-local",
                    process_environment={},
                    home=Path(temporary_home),
                )

    def test_insecure_file_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            path = home / ".config/quwoquan/product_telemetry_sls/gamma.env"
            path.parent.mkdir(parents=True)
            path.write_text(
                "".join(f"{key}={value}\n" for key, value in REQUIRED_VALUES.items()),
                encoding="utf-8",
            )
            os.chmod(path, 0o644)

            with self.assertRaisesRegex(RuntimeError, "must use mode 0600"):
                load_product_telemetry_sls(
                    "gamma", "gamma-local", process_environment={}, home=home
                )

    def test_unknown_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_home:
            home = Path(temporary_home)
            path = home / ".config/quwoquan/product_telemetry_sls/gamma.env"
            path.parent.mkdir(parents=True)
            path.write_text("UNDECLARED=value\n", encoding="utf-8")
            os.chmod(path, 0o600)

            with self.assertRaisesRegex(RuntimeError, "invalid product telemetry"):
                load_product_telemetry_sls(
                    "gamma", "gamma-local", process_environment={}, home=home
                )

    def test_cross_environment_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported product telemetry target"):
            load_product_telemetry_sls(
                "beta", "gamma-local", process_environment=REQUIRED_VALUES
            )


if __name__ == "__main__":
    unittest.main()
