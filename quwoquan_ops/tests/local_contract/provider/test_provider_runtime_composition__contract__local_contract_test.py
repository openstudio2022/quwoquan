from __future__ import annotations

import re
import unittest
from copy import deepcopy
from unittest import mock

from quwoquan_ops.cli.lib import provider_runtime_composition as subject
from quwoquan_ops.cli.lib.external_provider_governance import load_and_compile
from quwoquan_ops.cli.lib.provider_runtime_composition import (
    compile_provider_runtime_composition,
    validate_provider_runtime_composition,
)


class ProviderRuntimeCompositionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compiled, issues = load_and_compile()
        if issues:
            raise AssertionError([issue.render() for issue in issues])

    def test_nonprod_workloads_are_derived_from_selected_bindings(self) -> None:
        expected_roles = {
            "provider-protocol-substitute",
            "sms-provider-substitute",
        }
        for environment in ("alpha", "beta", "gamma"):
            with self.subTest(environment=environment):
                result = compile_provider_runtime_composition(
                    environment=environment,
                    target=f"{environment}-local",
                    compiled=self.compiled,
                )
                self.assertEqual(
                    {workload["role"] for workload in result["workloads"]},
                    expected_roles,
                )
                self.assertRegex(
                    result["bindingDigest"],
                    r"^sha256:[0-9a-f]{64}$",
                )
                self.assertRegex(
                    result["runtimeCompositionDigest"],
                    r"^sha256:[0-9a-f]{64}$",
                )
                by_role = {
                    workload["role"]: workload for workload in result["workloads"]
                }
                self.assertEqual(
                    by_role["sms-provider-substitute"]["adapterIds"],
                    ["ext.sms.local_capture"],
                )
                self.assertEqual(
                    len(by_role["provider-protocol-substitute"]["capabilityIds"]),
                    10 if environment == "alpha" else 9,
                )
                if environment == "alpha":
                    binding_by_capability = {
                        binding["capabilityId"]: binding
                        for binding in result["bindings"]
                    }
                    self.assertEqual(
                        binding_by_capability["location.poi.search"]["adapterId"],
                        "ext.map.nominatim.protocol_substitute",
                    )
                    # route.read 保持未启用（App 无路线消费页面），不进入
                    # alpha substitute workload。
                    self.assertEqual(
                        binding_by_capability["location.route.read"]["state"],
                        "not_required",
                    )
                    self.assertEqual(
                        binding_by_capability["location.route.read"]["adapterId"],
                        "",
                    )
                self.assertIn(
                    "INTEGRATION_SMS_ENDPOINT",
                    result["materialKeys"]["endpoint"],
                )
                self.assertIn(
                    "INTEGRATION_SMS_TOKEN",
                    result["materialKeys"]["secret"],
                )

    def test_prod_contains_no_nonprod_substitute_workload(self) -> None:
        result = compile_provider_runtime_composition(
            environment="prod",
            target="prod-hosted",
            compiled=self.compiled,
        )
        self.assertEqual(result["workloads"], [])
        self.assertNotIn(
            "protocol_substitute",
            " ".join(binding["adapterId"] for binding in result["bindings"]),
        )
        self.assertNotIn(
            "local_capture",
            " ".join(binding["adapterId"] for binding in result["bindings"]),
        )

    def test_prod_fails_closed_when_binding_selects_local_capture(self) -> None:
        compiled = deepcopy(self.compiled)
        compiled["selectedBindings"]["prod"]["identity.sms.otp"] = deepcopy(
            compiled["selectedBindings"]["alpha"]["identity.sms.otp"]
        )
        with self.assertRaisesRegex(
            ValueError,
            "Prod Provider runtime forbids non-production adapter",
        ):
            compile_provider_runtime_composition(
                environment="prod",
                target="prod-hosted",
                compiled=compiled,
            )

    def test_binding_digest_covers_selector_and_material_identity(self) -> None:
        baseline = self._minimal_sms_compiled()
        baseline_result = compile_provider_runtime_composition(
            environment="alpha",
            target="alpha-local",
            compiled=baseline,
        )
        baseline_digest = baseline_result["bindingDigest"]
        mutations = []

        capability = deepcopy(baseline)
        binding = capability["selectedBindings"]["alpha"].pop("identity.sms.otp")
        capability["selectedBindings"]["alpha"]["identity.sms.delivery"] = binding
        mutations.append(capability)

        state = deepcopy(baseline)
        state["selectedBindings"]["alpha"]["identity.sms.otp"]["state"] = "blocked"
        mutations.append(state)

        adapter = deepcopy(baseline)
        adapter["selectedBindings"]["alpha"]["identity.sms.otp"]["adapter_id"] = (
            "ext.sms.alternate_local_capture"
        )
        mutations.append(adapter)

        endpoint_key = deepcopy(baseline)
        endpoint_key["selectedBindings"]["alpha"]["identity.sms.otp"][
            "endpoint_envs"
        ] = {"delivery": "INTEGRATION_SMS_ENDPOINT"}
        mutations.append(endpoint_key)

        secret_key = deepcopy(baseline)
        secret_key["selectedBindings"]["alpha"]["identity.sms.otp"]["secret_refs"] = [
            "INTEGRATION_SMS_TOKEN",
            "INTEGRATION_SMS_SECONDARY_TOKEN",
        ]
        mutations.append(secret_key)

        for index, mutated in enumerate(mutations):
            with self.subTest(index=index):
                result = compile_provider_runtime_composition(
                    environment="alpha",
                    target="alpha-local",
                    compiled=mutated,
                )
                self.assertNotEqual(result["bindingDigest"], baseline_digest)
                self.assertTrue(
                    re.fullmatch(
                        r"sha256:[0-9a-f]{64}",
                        result["bindingDigest"],
                    )
                )

    def test_nonprod_production_vendor_selector_fails_closed(self) -> None:
        compiled = self._minimal_sms_compiled()
        binding = compiled["selectedBindings"]["alpha"]["identity.sms.otp"]
        binding["adapter_id"] = "ext.sms.aliyun"
        binding["endpoint_ref"] = "environment_binding:integration.sms"

        with self.assertRaisesRegex(
            ValueError,
            "third-party Provider must select a local substitute",
        ):
            compile_provider_runtime_composition(
                environment="alpha",
                target="alpha-local",
                compiled=compiled,
            )

    def test_nonprod_vendor_cannot_hide_behind_local_topology(self) -> None:
        compiled = self._minimal_sms_compiled()
        binding = compiled["selectedBindings"]["alpha"]["identity.sms.otp"]
        binding["adapter_id"] = "ext.sms.aliyun"

        with self.assertRaisesRegex(
            ValueError,
            "third-party Provider must select a local substitute",
        ):
            compile_provider_runtime_composition(
                environment="alpha",
                target="alpha-local",
                compiled=compiled,
            )

    def test_nonprod_substitute_cannot_use_external_environment_binding(self) -> None:
        compiled = self._minimal_sms_compiled()
        binding = compiled["selectedBindings"]["alpha"]["identity.sms.otp"]
        binding["endpoint_ref"] = "environment_binding:integration.sms"

        with self.assertRaisesRegex(
            ValueError,
            "third-party Provider must select a local substitute",
        ):
            compile_provider_runtime_composition(
                environment="alpha",
                target="alpha-local",
                compiled=compiled,
            )

    def test_nonprod_elasticsearch_cannot_cross_environment(self) -> None:
        compiled = deepcopy(self.compiled)
        compiled["selectedBindings"]["beta"]["runtime.log.sink"][
            "endpoint_ref"
        ] = "local_topology:alpha.elasticsearch"

        with self.assertRaisesRegex(
            ValueError,
            "Elasticsearch endpoint crosses target isolation",
        ):
            compile_provider_runtime_composition(
                environment="beta",
                target="beta-local",
                compiled=compiled,
            )

    def test_substitute_without_endpoint_workload_contract_fails_closed(self) -> None:
        compiled = self._minimal_sms_compiled()
        compiled["selectedBindings"]["alpha"]["identity.sms.otp"]["endpoint_ref"] = (
            "local_topology:missing-sms-substitute"
        )
        with self.assertRaisesRegex(
            ValueError,
            "has no canonical endpoint workload contract",
        ):
            compile_provider_runtime_composition(
                environment="alpha",
                target="alpha-local",
                compiled=compiled,
            )

    def test_packaged_validator_owns_material_and_workload_closure(self) -> None:
        composition = compile_provider_runtime_composition(
            environment="alpha",
            target="alpha-local",
            compiled=self.compiled,
        )
        missing_material = deepcopy(composition)
        missing_material["materialKeys"]["endpoint"].remove(
            "INTEGRATION_SMS_ENDPOINT"
        )
        with self.assertRaisesRegex(ValueError, "materialKeys closure mismatch"):
            validate_provider_runtime_composition(
                missing_material,
                expected_environment="alpha",
                expected_target="alpha-local",
            )

    def test_package_self_verify_does_not_read_current_endpoint_contracts(self) -> None:
        composition = compile_provider_runtime_composition(
            environment="alpha",
            target="alpha-local",
            compiled=self.compiled,
        )

        with mock.patch.object(
            subject,
            "_load_endpoint_contracts",
            side_effect=AssertionError("self_verify must not read current contracts"),
        ):
            validated = validate_provider_runtime_composition(
                composition,
                expected_environment="alpha",
                expected_target="alpha-local",
                require_current_contracts=False,
            )

        self.assertEqual(validated, composition)

        missing_workload = deepcopy(composition)
        missing_workload["workloads"] = [
            workload
            for workload in missing_workload["workloads"]
            if workload["role"] != "sms-provider-substitute"
        ]
        with self.assertRaisesRegex(ValueError, "substitute workload is missing"):
            validate_provider_runtime_composition(
                missing_workload,
                expected_environment="alpha",
                expected_target="alpha-local",
            )

    def test_rehashed_nonprod_production_vendor_selector_is_rejected(self) -> None:
        composition = compile_provider_runtime_composition(
            environment="alpha",
            target="alpha-local",
            compiled=self.compiled,
        )
        forged = deepcopy(composition)
        for binding in forged["bindings"]:
            if binding["capabilityId"] == "identity.sms.otp":
                binding["adapterId"] = "ext.sms.aliyun"
                binding["endpointRef"] = "environment_binding:integration.sms"
                break
        forged["workloads"] = [
            workload
            for workload in forged["workloads"]
            if workload["role"] != "sms-provider-substitute"
        ]
        self._reseal(forged)

        with self.assertRaisesRegex(
            ValueError,
            "third-party Provider must select a local substitute",
        ):
            validate_provider_runtime_composition(
                forged,
                expected_environment="alpha",
                expected_target="alpha-local",
            )

    def test_rehashed_canonical_workload_refs_and_digests_are_rejected(self) -> None:
        composition = compile_provider_runtime_composition(
            environment="alpha",
            target="alpha-local",
            compiled=self.compiled,
        )
        mutations = (
            ("contractRef", "/tmp/forged/endpoints.yaml"),
            ("contractRef", "../forged/endpoints.yaml"),
            ("contractDigest", "sha256:" + "1" * 64),
            ("composeRef", "/tmp/forged/compose.yaml"),
            ("composeRef", "../forged/compose.yaml"),
            ("composeDigest", "sha256:" + "2" * 64),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                forged = deepcopy(composition)
                forged["workloads"][0][field] = value
                self._reseal(forged)
                with self.assertRaisesRegex(
                    ValueError,
                    "canonical workload drift",
                ):
                    validate_provider_runtime_composition(
                        forged,
                        expected_environment="alpha",
                        expected_target="alpha-local",
                    )

    @staticmethod
    def _reseal(composition: dict[str, object]) -> None:
        composition["bindingDigest"] = subject._digest(composition["bindings"])
        composition["runtimeCompositionDigest"] = subject._digest(
            {
                "environment": composition["environment"],
                "target": composition["target"],
                "bindingDigest": composition["bindingDigest"],
                "materialKeys": composition["materialKeys"],
                "workloads": composition["workloads"],
            }
        )

    @staticmethod
    def _minimal_sms_compiled() -> dict[str, object]:
        return {
            "schema": "compiled-external-provider-bindings",
            "issues": [],
            "selectedBindings": {
                "alpha": {
                    "identity.sms.otp": {
                        "state": "enabled",
                        "adapter_id": "ext.sms.local_capture",
                        "endpoint_ref": "local_topology:sms-provider-substitute",
                        "endpoint_envs": {
                            "endpoint": "INTEGRATION_SMS_ENDPOINT",
                        },
                        "secret_refs": ["INTEGRATION_SMS_TOKEN"],
                    },
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
