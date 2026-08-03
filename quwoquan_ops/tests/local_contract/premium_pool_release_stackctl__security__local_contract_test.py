# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-004

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import local_environment_auth, premium_pool_release


def _jwt(claims: dict[str, object], *, alg: str = "HS256") -> str:
    def encode(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return encode({"alg": alg, "typ": "JWT"}) + "." + encode(claims) + ".signature"


class PremiumPoolReleaseStackctlSecurityLocalContractTest(unittest.TestCase):
    def test_alpha_operator_is_short_lived_typed_and_never_returned_in_receipt(self) -> None:
        token = _jwt(
            {
                "sub": "operator:content-commercial:alpha",
                "roles": ["operator"],
                "scope": (
                    "ops.experiment.read ops.experiment.write "
                    "ops.reco.read ops.reco.write ops.telemetry.read"
                ),
                "iss": "quwoquan.alpha.local",
                "aud": "quwoquan-app",
                "iat": 100,
                "exp": 1000,
            }
        )
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=token + "\n", stderr=""
        )
        with (
            mock.patch.object(
                local_environment_auth,
                "prepare_local_environment_auth",
                return_value=local_environment_auth.LocalEnvironmentAuth(
                    environment={
                        "AUTH_JWT_SECRET": "s" * 48,
                        "AUTH_JWT_ISSUER": "quwoquan.alpha.local",
                        "AUTH_JWT_AUDIENCE": "quwoquan-app",
                        "AUTH_JWT_TOKEN_VERSION": "1",
                    },
                    secret_path=Path("/tmp/auth.env"),
                ),
            ),
            mock.patch.object(
                local_environment_auth.subprocess,
                "run",
                return_value=completed,
            ) as run,
        ):
            actual = local_environment_auth.mint_local_product_ops_operator_token(
                "alpha", "alpha-local"
            )

        self.assertEqual(actual, token)
        self.assertEqual(
            run.call_args.args[0],
            ["go", "run", "./cmd/local-product-ops-operator-credential"],
        )
        self.assertEqual(run.call_args.kwargs["env"]["APP_ENV"], "alpha")

    def test_prod_cannot_use_nonprod_operator_port(self) -> None:
        with (
            mock.patch.object(local_environment_auth.subprocess, "run") as run,
            self.assertRaisesRegex(ValueError, "Alpha/Beta/Gamma"),
        ):
            local_environment_auth.mint_local_product_ops_operator_token(
                "prod", "prod-sim"
            )
        run.assert_not_called()

    def test_gamma_uses_same_target_scoped_nonprod_operator_port(self) -> None:
        expected = local_environment_auth.LocalAcceptanceSession(
            owner_id="operator:content-commercial:gamma",
            persona_id="",
            access_token="gamma-token",
        )
        with mock.patch.object(
            premium_pool_release,
            "mint_local_product_ops_operator_token",
            return_value=expected.access_token,
        ) as mint:
            session, kind = premium_pool_release.open_premium_pool_operator_session(
                environment="gamma", target="gamma-local"
            )
        self.assertEqual(session, expected)
        self.assertEqual(kind, "managed_local_hs256_operator")
        mint.assert_called_once_with("gamma", "gamma-local")

    def test_candidate_binding_rejects_video_outside_active_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = root / "data-release/release/verify/release-readiness.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.environment_release_readiness",
                        "environment": "alpha",
                        "readinessPhase": "consumer",
                        "passed": True,
                        "releaseId": "release-1",
                        "manifestDigest": "sha256:" + "a" * 64,
                        "importRunId": "apply-1",
                        "verifyRunId": "verify-1",
                        "feedQueries": [
                            {"name": "typed_video", "matchedPostIds": ["video-1"]}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.object(
                    premium_pool_release,
                    "active_deployment_candidate",
                    return_value={"baselineId": "sha256:" + "b" * 64},
                ),
                mock.patch.object(
                    premium_pool_release,
                    "load_candidate_manifest",
                    return_value={
                        "baselineId": "sha256:" + "b" * 64,
                        "packageDigest": "sha256:" + "c" * 64,
                        "sourceRevision": "revision-1",
                        "release": {
                            "candidate": {
                                "releaseId": "release-1",
                                "releaseDigest": "sha256:" + "a" * 64,
                            }
                        },
                    },
                ),
                mock.patch.object(
                    premium_pool_release,
                    "env_runs_root",
                    return_value=root,
                ),
                self.assertRaisesRegex(
                    premium_pool_release.PremiumPoolReleaseError,
                    "release-bound video",
                ),
            ):
                premium_pool_release.load_premium_pool_candidate_binding(
                    environment="alpha",
                    target="alpha-local",
                    readiness_receipt=receipt,
                    content_id="video-other",
                )

    def test_stackctl_gamma_gate_block_report_never_contains_bearer(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(
                stackctl,
                "resolve_report_dir",
                return_value=Path(temporary),
            ),
            mock.patch.object(
                stackctl,
                "load_premium_pool_candidate_binding",
                return_value=mock.sentinel.binding,
            ),
            mock.patch.object(
                stackctl,
                "open_premium_pool_operator_session",
                side_effect=premium_pool_release.PremiumPoolReleaseError(
                    "GATE_BLOCK: target-scoped operator material is unavailable"
                ),
            ),
        ):
            result = stackctl.command_premium_pool(
                argparse.Namespace(
                    target="gamma-local",
                    action="upsert-and-verify",
                    readiness_receipt="receipt.json",
                    content_id="video-1",
                    quality_score=0.88,
                    expires_at="2099-01-01T00:00:00Z",
                    projection_deadline_seconds=1.0,
                )
            )
            report = json.loads(
                (Path(temporary) / "report.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["exitCode"], 2)
        self.assertEqual(report["status"], "gate_block")
        self.assertNotIn("Bearer", json.dumps(report))

    def test_content_release_readback_needs_no_operator_credential(self) -> None:
        binding = premium_pool_release.PremiumPoolCandidateBinding(
            environment="alpha",
            target="alpha-local",
            baseline_id="sha256:" + "a" * 64,
            package_digest="sha256:" + "b" * 64,
            source_revision="revision-1",
            release_id="release-1",
            manifest_digest="sha256:" + "c" * 64,
            import_run_id="apply-1",
            verify_run_id="verify-1",
            content_id="video-1",
            readiness_receipt_ref="run/release-readiness.json",
        )
        with mock.patch.object(
            premium_pool_release,
            "_wait_for_premium_projection",
            return_value=["video-1"],
        ) as wait:
            receipt = premium_pool_release.execute_premium_pool_readback(
                binding=binding,
                api_base_url="https://api.alpha.quwoquan.local",
                ssl_cafile="/tmp/root.pem",
                projection_deadline_seconds=1.0,
            )

        self.assertEqual(receipt["schema"], "qwq.premium_pool_readback_receipt")
        self.assertEqual(receipt["recommendationReadback"]["contentId"], "video-1")
        self.assertNotIn("operator", receipt)
        wait.assert_called_once()

    def test_premium_feed_readback_uses_canonical_client_session_header(self) -> None:
        with mock.patch.object(
            premium_pool_release,
            "_request_json",
            return_value={"items": [{"id": "video-1"}]},
        ) as request_json:
            matched = premium_pool_release._wait_for_premium_projection(
                api_base_url="https://api.alpha.quwoquan.local",
                content_id="video-1",
                client_session_id="premium-readback-session",
                ssl_cafile="/tmp/root.pem",
                deadline_seconds=1.0,
            )

        self.assertEqual(matched, ["video-1"])
        self.assertEqual(
            request_json.call_args.kwargs["headers"],
            {"X-Client-Session-Id": "premium-readback-session"},
        )

    def test_parser_exposes_only_candidate_bound_nonprod_operation(self) -> None:
        args = stackctl.build_parser().parse_args(
            [
                "premium-pool",
                "--target",
                "alpha-local",
                "--action",
                "upsert-and-verify",
                "--readiness-receipt",
                "receipt.json",
                "--content-id",
                "video-1",
                "--quality-score",
                "0.88",
                "--expires-at",
                "2099-01-01T00:00:00Z",
            ]
        )
        self.assertEqual(args.command, "premium-pool")
        self.assertEqual(args.target, "alpha-local")

        readback_args = stackctl.build_parser().parse_args(
            [
                "premium-pool",
                "--target",
                "alpha-local",
                "--action",
                "verify-readback",
                "--readiness-receipt",
                "receipt.json",
                "--content-id",
                "video-1",
            ]
        )
        self.assertEqual(readback_args.action, "verify-readback")
        self.assertIsNone(readback_args.quality_score)


if __name__ == "__main__":
    unittest.main()
