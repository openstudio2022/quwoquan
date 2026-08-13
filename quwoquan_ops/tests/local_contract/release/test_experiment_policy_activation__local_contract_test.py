# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import experiment_policy_activation as activation


class ExperimentPolicyActivationLocalContractTest(unittest.TestCase):
    def test_test_live_is_runtime_bound_without_candidate_or_bearer_persistence(
        self,
    ) -> None:
        attempt_id = "alpha-test-live-" + "c" * 32
        configuration_digest = "sha256:" + "d" * 64
        search_create = {
            "id": "search_ranking",
            "key": "search_ranking",
            "status": "running",
            "experimentRevision": 1,
        }
        rec_create = {
            "id": "rec_model_vs_rule",
            "key": "rec_model_vs_rule",
            "status": "running",
            "experimentRevision": 1,
        }
        catalog = {
            "items": [
                {
                    **search_create,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    **rec_create,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 10000},
                        {"key": "model", "allocationBasisPoints": 0},
                    ],
                },
            ]
        }
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                side_effect=AssertionError("test_live must not read a candidate"),
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                side_effect=AssertionError("test_live must not read a manifest"),
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
                side_effect=AssertionError("loopback HTTP must not read release TLS"),
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-test-live-bearer",
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (201, search_create),
                    (200, catalog),
                    (201, rec_create),
                    (200, catalog),
                ],
            ) as request_json,
        ):
            receipt = activation.activate_test_live_experiment_policies(
                environment="alpha",
                target="alpha-local",
                product_ops_published_port=17250,
                attempt_id=attempt_id,
                configuration_digest=configuration_digest,
            )

        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["launchPolicy"], "test_live")
        self.assertIs(receipt["nonPromotable"], True)
        self.assertEqual(receipt["attemptId"], attempt_id)
        self.assertEqual(receipt["configurationDigest"], configuration_digest)
        self.assertRegex(receipt["runtimeIdentityDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            [item["id"] for item in receipt["policies"]],
            ["search_ranking", "rec_model_vs_rule"],
        )
        self.assertNotIn("sensitive-test-live-bearer", json.dumps(receipt))
        for call in request_json.call_args_list:
            self.assertEqual(call.kwargs["cafile"], None)
            self.assertEqual(
                call.kwargs["url"],
                "http://127.0.0.1:17250/control-plane/product/experiments",
            )
        create_call = request_json.call_args_list[0].kwargs
        self.assertTrue(
            create_call["headers"]["Idempotency-Key"].startswith(
                "test-live-runtime-policy/alpha-local/"
            )
        )
        self.assertNotIn("Authorization", create_call["headers"])

    def test_test_live_rolls_existing_model_policy_to_explicit_rule_only(self) -> None:
        attempt_id = "alpha-test-live-" + "e" * 32
        configuration_digest = "sha256:" + "f" * 64
        search = {
            "id": "search_ranking",
            "key": "search_ranking",
            "status": "running",
            "experimentRevision": 1,
            "variants": [
                {"key": "control", "allocationBasisPoints": 5000},
                {"key": "term_heat", "allocationBasisPoints": 5000},
            ],
        }
        recommendation_before = {
            "id": "rec_model_vs_rule",
            "key": "rec_model_vs_rule",
            "status": "running",
            "experimentRevision": 1,
            "variants": [
                {"key": "rule", "allocationBasisPoints": 5000},
                {"key": "model", "allocationBasisPoints": 5000},
            ],
        }
        recommendation_after = {
            **recommendation_before,
            "experimentRevision": 2,
            "variants": [
                {"key": "rule", "allocationBasisPoints": 10000},
                {"key": "model", "allocationBasisPoints": 0},
            ],
        }
        catalog_before = {"items": [search, recommendation_before]}
        catalog_after = {"items": [search, recommendation_after]}
        with (
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-test-live-bearer",
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (409, {"code": "OPS.USER.version_conflict"}),
                    (200, catalog_before),
                    (409, {"code": "OPS.USER.version_conflict"}),
                    (200, catalog_before),
                    (200, recommendation_after),
                    (200, catalog_after),
                ],
            ) as request_json,
        ):
            receipt = activation.activate_test_live_experiment_policies(
                environment="alpha",
                target="alpha-local",
                product_ops_published_port=17250,
                attempt_id=attempt_id,
                configuration_digest=configuration_digest,
            )

        self.assertEqual(receipt["operation"], "rolled_out")
        self.assertEqual(
            receipt["policyOperations"],
            {"search_ranking": "reused", "rec_model_vs_rule": "rolled_out"},
        )
        recommendation = next(
            item for item in receipt["policies"] if item["id"] == "rec_model_vs_rule"
        )
        self.assertEqual(recommendation["variants"], recommendation_after["variants"])
        rollout = request_json.call_args_list[4].kwargs
        self.assertEqual(
            rollout["url"],
            "http://127.0.0.1:17250/control-plane/product/experiments/rec_model_vs_rule:rollout",
        )
        self.assertEqual(rollout["headers"]["If-Match"], '"1"')
        self.assertIn("/rollout", rollout["headers"]["Idempotency-Key"])
        self.assertNotIn("sensitive-test-live-bearer", json.dumps(receipt))

    def test_test_live_rejects_wrong_identity_or_port_before_minting(self) -> None:
        valid = {
            "environment": "alpha",
            "target": "alpha-local",
            "product_ops_published_port": 17250,
            "attempt_id": "alpha-test-live-" + "a" * 32,
            "configuration_digest": "sha256:" + "b" * 64,
        }
        cases = (
            ({**valid, "target": "beta-local"}, "Alpha/Beta/Gamma"),
            ({**valid, "product_ops_published_port": 17251}, "does not match"),
            ({**valid, "attempt_id": "alpha-test-live-invalid"}, "attempt identity"),
            ({**valid, "configuration_digest": "sha256:invalid"}, "configuration digest"),
        )
        with mock.patch.object(
            activation,
            "mint_local_product_ops_operator_token",
        ) as mint:
            for arguments, message in cases:
                with self.subTest(arguments=arguments):
                    with self.assertRaisesRegex(
                        activation.ExperimentPolicyActivationError,
                        message,
                    ):
                        activation.activate_test_live_experiment_policies(**arguments)
        mint.assert_not_called()

    def test_create_is_package_bound_exact_and_never_persists_bearer(self) -> None:
        search_create = {
            "id": "search_ranking",
            "key": "search_ranking",
            "status": "running",
            "experimentRevision": 1,
        }
        rec_create = {
            "id": "rec_model_vs_rule",
            "key": "rec_model_vs_rule",
            "status": "running",
            "experimentRevision": 1,
        }
        catalog = {
            "items": [
                {
                    **search_create,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    **rec_create,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 5000},
                        {"key": "model", "allocationBasisPoints": 5000},
                    ],
                },
            ]
        }
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                return_value={
                    "packageDigest": "sha256:" + "b" * 64,
                    "sourceRevision": "revision-1",
                },
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-bearer",
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
                return_value=Path("/tmp/root.crt"),
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (201, search_create),
                    (200, catalog),
                    (201, rec_create),
                    (200, catalog),
                ],
            ) as request_json,
        ):
            receipt = activation.activate_search_experiment_policy(
                environment="alpha",
                target="alpha-local",
                product_ops_base_url="https://ops.alpha.quwoquan.local:17010",
            )

        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["operation"], "created")
        self.assertEqual(receipt["caseResult"]["executed"], 2)
        self.assertEqual(receipt["caseResult"]["skipped"], 0)
        self.assertEqual(
            [item["id"] for item in receipt["policies"]],
            ["search_ranking", "rec_model_vs_rule"],
        )
        self.assertNotIn("sensitive-bearer", json.dumps(receipt))
        create_call = request_json.call_args_list[0].kwargs
        self.assertEqual(create_call["method"], "POST")
        self.assertIn("Idempotency-Key", create_call["headers"])
        self.assertNotIn("Authorization", create_call["headers"])

    def test_existing_exact_policy_is_reused_without_second_source(self) -> None:
        catalog = {
            "items": [
                {
                    "id": "search_ranking",
                    "key": "search_ranking",
                    "status": "running",
                    "experimentRevision": 3,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    "id": "rec_model_vs_rule",
                    "key": "rec_model_vs_rule",
                    "status": "running",
                    "experimentRevision": 2,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 5000},
                        {"key": "model", "allocationBasisPoints": 5000},
                    ],
                },
            ]
        }
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                return_value={"packageDigest": "sha256:" + "b" * 64},
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="token",
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
                return_value=Path("/tmp/root.crt"),
            ),
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (409, {"code": "OPS.USER.version_conflict"}),
                    (200, catalog),
                    (409, {"code": "OPS.USER.version_conflict"}),
                    (200, catalog),
                ],
            ),
        ):
            receipt = activation.activate_search_experiment_policy(
                environment="gamma",
                target="gamma-local",
                product_ops_base_url="https://ops.gamma.quwoquan.local:19010",
            )
        self.assertEqual(receipt["operation"], "reused")
        self.assertEqual(receipt["policy"]["experimentRevision"], 3)
        self.assertEqual(
            receipt["policyOperations"],
            {"search_ranking": "reused", "rec_model_vs_rule": "reused"},
        )

    def test_published_port_bootstrap_uses_loopback_and_canonical_identity(
        self,
    ) -> None:
        """冷启动 policy owner bootstrap 走 loopback published port（此时
        gamma-proxy 尚不存在），且与 up 之后的 activation 共用同一 canonical
        recipes 与 idempotency 身份，暖启动是纯 reuse 而非第二真相源。"""

        catalog = {
            "items": [
                {
                    "id": "search_ranking",
                    "key": "search_ranking",
                    "status": "running",
                    "experimentRevision": 1,
                    "variants": [
                        {"key": "control", "allocationBasisPoints": 5000},
                        {"key": "term_heat", "allocationBasisPoints": 5000},
                    ],
                },
                {
                    "id": "rec_model_vs_rule",
                    "key": "rec_model_vs_rule",
                    "status": "running",
                    "experimentRevision": 1,
                    "variants": [
                        {"key": "rule", "allocationBasisPoints": 5000},
                        {"key": "model", "allocationBasisPoints": 5000},
                    ],
                },
            ]
        }
        search_create = dict(catalog["items"][0])
        rec_create = dict(catalog["items"][1])
        with (
            mock.patch.object(
                activation,
                "active_deployment_candidate",
                return_value={"baselineId": "sha256:" + "a" * 64},
            ),
            mock.patch.object(
                activation,
                "load_candidate_manifest",
                return_value={
                    "packageDigest": "sha256:" + "b" * 64,
                    "sourceRevision": "revision-1",
                },
            ),
            mock.patch.object(
                activation,
                "load_port_manifest",
                return_value={},
            ),
            mock.patch.object(
                activation,
                "profile_ports",
                return_value={"product-ops-service": 19250},
            ),
            mock.patch.object(
                activation,
                "mint_local_product_ops_operator_token",
                return_value="sensitive-bearer",
            ),
            mock.patch.object(
                activation,
                "root_certificate_path",
            ) as certificate_path,
            mock.patch.object(
                activation,
                "_request_json",
                side_effect=[
                    (201, search_create),
                    (200, catalog),
                    (201, rec_create),
                    (200, catalog),
                ],
            ) as request_json,
        ):
            receipt = activation.activate_search_experiment_policy_via_published_port(
                environment="gamma",
                target="gamma-local",
            )

        self.assertEqual(receipt["schema"], "qwq.experiment_policy_bootstrap_receipt")
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["launchPolicy"], "policy-owner-bootstrap")
        self.assertEqual(receipt["productOpsPublishedPort"], 19250)
        self.assertEqual(
            [item["id"] for item in receipt["policies"]],
            ["search_ranking", "rec_model_vs_rule"],
        )
        self.assertNotIn("sensitive-bearer", json.dumps(receipt))
        # bootstrap 阶段没有 gamma-proxy，不得依赖 public TLS 根证书。
        certificate_path.assert_not_called()
        for call in request_json.call_args_list:
            self.assertTrue(
                call.kwargs["url"].startswith("http://127.0.0.1:19250/"),
                call.kwargs["url"],
            )
            self.assertIsNone(call.kwargs["cafile"])
        create_call = request_json.call_args_list[0].kwargs
        # 与 up 之后 activate_search_experiment_policy 完全相同的幂等身份。
        self.assertTrue(
            create_call["headers"]["Idempotency-Key"].startswith(
                "runtime-policy/gamma-local/" + "a" * 16 + "/search_ranking/"
            ),
            create_call["headers"]["Idempotency-Key"],
        )

    def test_published_port_bootstrap_rejects_prod_before_credentials(self) -> None:
        with (
            mock.patch.object(
                activation, "mint_local_product_ops_operator_token"
            ) as mint,
            self.assertRaisesRegex(
                activation.ExperimentPolicyActivationError,
                "Alpha/Beta/Gamma",
            ),
        ):
            activation.activate_search_experiment_policy_via_published_port(
                environment="prod",
                target="prod-sim",
            )
        mint.assert_not_called()

    def test_prod_is_rejected_before_any_credential_is_minted(self) -> None:
        with (
            mock.patch.object(
                activation, "mint_local_product_ops_operator_token"
            ) as mint,
            self.assertRaisesRegex(
                activation.ExperimentPolicyActivationError,
                "Alpha/Beta/Gamma",
            ),
        ):
            activation.activate_search_experiment_policy(
                environment="prod",
                target="prod-sim",
                product_ops_base_url="https://ops.quwoquan.com",
            )
        mint.assert_not_called()


if __name__ == "__main__":
    unittest.main()
