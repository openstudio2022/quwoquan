from __future__ import annotations

import unittest

from quwoquan_ops.cli.lib.local_provider_credentials import (
    _required_material_for_environment,
    load_nonprod_provider_environment,
    provider_environment_reference_names,
)


def _material(environment: str) -> dict[str, str]:
    _, secret_keys = _required_material_for_environment(environment)
    values = {key: f"target-scoped-{key.lower()}" for key in secret_keys}
    values["SMS_SUBSTITUTE_OPERATOR_TOKEN"] = (
        "target-scoped-sms-substitute-operator-token"
    )
    values["PROVIDER_SUBSTITUTE_OPERATOR_TOKEN"] = (
        "target-scoped-provider-protocol-operator-token"
    )
    return values


class LocalProviderCredentialsSecurityLocalContractTest(unittest.TestCase):
    def test_reference_inventory_does_not_read_protected_values(self) -> None:
        endpoint_keys, secret_keys = provider_environment_reference_names("alpha")
        self.assertEqual(endpoint_keys, frozenset({"RTC_MEDIA_CONNECTION_URL"}))
        self.assertEqual(
            secret_keys,
            frozenset(
                {
                    "INTEGRATION_SMS_TOKEN",
                    "RTC_MEDIA_API_KEY",
                    "RTC_MEDIA_API_SECRET",
                }
            ),
        )

    def test_nonprod_provider_input_is_only_target_scoped_livekit_material(self) -> None:
        endpoint_keys, secret_keys = _required_material_for_environment("beta")

        self.assertEqual(endpoint_keys, {"RTC_MEDIA_CONNECTION_URL"})
        self.assertEqual(
            secret_keys,
            {
                "INTEGRATION_SMS_TOKEN",
                "RTC_MEDIA_API_KEY",
                "RTC_MEDIA_API_SECRET",
            },
        )

    def test_loader_projects_only_canonical_internal_endpoints(self) -> None:
        values = load_nonprod_provider_environment(
            environment="alpha",
            target_name="alpha-local",
            source=_material("alpha"),
        )
        self.assertEqual(
            values["CONTENT_EMBEDDING_ENDPOINT"],
            "https://provider-protocol-substitute:18089/v1/embeddings",
        )
        self.assertEqual(
            values["ASSISTANT_MODEL_COMPLETION_URL"],
            "https://provider-protocol-substitute:18089/v1/chat/completions",
        )
        self.assertEqual(
            values["RTC_MEDIA_CONNECTION_URL"],
            "http://livekit-sfu:7880",
        )
        self.assertNotEqual(
            values["PROVIDER_SUBSTITUTE_OPERATOR_TOKEN"],
            values["SMS_SUBSTITUTE_OPERATOR_TOKEN"],
        )

    def test_missing_material_fails_closed_without_exposing_values(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "GATE_BLOCK: target-scoped nonprod Provider material is missing",
        ) as failure:
            load_nonprod_provider_environment(
                environment="beta",
                target_name="beta-local",
                source={},
            )
        self.assertIn("RTC_MEDIA_API_KEY", str(failure.exception))

    def test_placeholder_secret_material_fails_closed(self) -> None:
        material = _material("gamma")
        material["RTC_MEDIA_API_KEY"] = "placeholder"
        with self.assertRaisesRegex(RuntimeError, "placeholder values"):
            load_nonprod_provider_environment(
                environment="gamma",
                target_name="gamma-local",
                source=material,
            )

    def test_target_and_environment_are_bound(self) -> None:
        with self.assertRaisesRegex(ValueError, "target/environment mismatch"):
            load_nonprod_provider_environment(
                environment="alpha",
                target_name="beta-local",
                source=_material("alpha"),
            )

    def test_prod_material_is_never_loaded_by_nonprod_facade(self) -> None:
        with self.assertRaisesRegex(ValueError, "only valid for Alpha/Beta/Gamma"):
            load_nonprod_provider_environment(
                environment="prod",
                target_name="prod-local",
                source={},
            )


if __name__ == "__main__":
    unittest.main()
