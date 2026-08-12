# spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.test_data.capabilities.user_service import (
    AUTHENTICATED_ACTORS,
)
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as patrol_smoke


class AppContentPreflightTest(unittest.TestCase):
    def test_feed_uat_evidence_requires_a_visible_card(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "patrol.log"
            log_path.write_text(
                "flutter: QWQ_FEED_CONTENT_EVIDENCE "
                '{"environment":"alpha","visibleCardCount":1,'
                '"visibleCardKeys":["home-feed-card-0"]}\n',
                encoding="utf-8",
            )
            evidence = patrol_smoke._read_feed_content_evidence(log_path)
            self.assertEqual(evidence["environment"], "alpha")
            self.assertEqual(evidence["visibleCardCount"], 1)

            log_path.write_text(
                "QWQ_FEED_CONTENT_EVIDENCE "
                '{"environment":"alpha","visibleCardCount":0,'
                '"visibleCardKeys":[]}\n',
                encoding="utf-8",
            )
            self.assertEqual(
                patrol_smoke._read_feed_content_evidence(log_path),
                {},
            )

    def test_app_uat_envelope_requires_release_bound_exact_queries(self) -> None:
        readiness = {
            "releaseId": "release-a",
            "releaseClass": "commercial",
            "productLifecycleState": "commercial",
            "readinessPhase": "commercial",
            "feedQueries": [
                {"name": "typed_article", "matchedPostIds": ["article-a"]},
                {"name": "typed_image", "matchedPostIds": ["image-a"]},
                {"name": "typed_video", "matchedPostIds": ["video-a"]},
                {"name": "homepage_recommend", "matchedPostIds": ["article-a"]},
                {"name": "premium_stream", "matchedPostIds": []},
            ],
            "appUatEnvelope": {
                "releaseId": "release-a",
                "releaseClass": "commercial",
                "productLifecycleState": "commercial",
                "homepageId": "homepage-a",
                "homepageTitle": "首页 A",
                "articleWorkId": "article-a",
                "articleTitle": "文章 A",
                "imageWorkId": "image-a",
                "imageTitle": "图片 A",
                "videoWorkId": "video-a",
                "creatorName": "创作者 A",
                "creatorUserHandle": "creator-a",
                "creatorPersonaId": "persona-a",
                "creatorAvatarAssetId": "avatar-a",
                "tagLabel": "标签 A",
                "videoAttribution": "来源 A",
            },
        }

        with self.assertRaisesRegex(ValueError, "Premium-query bound"):
            stackctl._app_content_uat_envelope(readiness)
        readiness["feedQueries"][-1]["matchedPostIds"] = ["video-a"]
        envelope = stackctl._app_content_uat_envelope(readiness)
        self.assertEqual(envelope["videoWorkId"], "video-a")
        self.assertEqual(envelope["creatorUserHandle"], "creator-a")
        self.assertEqual(envelope["creatorPersonaId"], "persona-a")
        self.assertEqual(envelope["creatorAvatarAssetId"], "avatar-a")

        consumer = json.loads(json.dumps(readiness))
        consumer["readinessPhase"] = "consumer"
        consumer["feedQueries"] = [
            item
            for item in consumer["feedQueries"]
            if item["name"] != "premium_stream"
        ]
        self.assertEqual(
            stackctl._app_content_uat_envelope(consumer)["videoWorkId"],
            "video-a",
        )
        next(
            item
            for item in consumer["feedQueries"]
            if item["name"] == "typed_video"
        )["matchedPostIds"] = []
        with self.assertRaisesRegex(ValueError, "typed_video is not exact-query bound"):
            stackctl._app_content_uat_envelope(consumer)

    def test_live_uat_holds_runtime_use_lock_while_preflighting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "uat"
            lock_handle = unittest.mock.MagicMock()
            observed_lock_state: list[bool] = []

            def preflight(_args: object) -> dict[str, object]:
                observed_lock_state.append(not lock_handle.close.called)
                return {
                    "exitCode": 2,
                    "details": ["typed blocker"],
                }

            with (
                patch.object(
                    stackctl,
                    "acquire_local_runtime_use_lock",
                    return_value=lock_handle,
                ) as acquire,
                patch.object(
                    stackctl,
                    "command_app_debug_preflight",
                    side_effect=preflight,
                ),
            ):
                result = stackctl.command_app_content_uat(
                    stackctl.argparse.Namespace(
                        targets="alpha-local,beta-local,gamma-local",
                        platform="ios-simulator",
                        device_id="SIMULATOR-UDID",
                        dry_run=False,
                        report_dir=str(report_dir),
                    )
                )

            self.assertEqual(result["exitCode"], 2)
            self.assertEqual(observed_lock_state, [True])
            acquire.assert_called_once_with(
                target="alpha-local,beta-local,gamma-local",
                purpose="app-content-uat:ios-simulator:SIMULATOR-UDID",
            )
            lock_handle.close.assert_called_once_with()

    def test_debug_preflight_requires_runtime_health_and_real_login_journey(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "debug-preflight"
            provider_health = json.dumps(
                {
                    "status": "ready",
                    "adapterId": "ext.sms.local_capture",
                    "environment": "alpha",
                    "configurationDigest": "sha256:" + "1" * 64,
                    "profile": "success",
                    "nonPromotable": True,
                }
            )
            provider_runtime_digest = "sha256:" + "5" * 64
            provider_runtime = {
                "composition": {
                    "runtimeCompositionDigest": provider_runtime_digest,
                    "workloads": [
                        {
                            "role": "sms-provider-substitute",
                            "adapterIds": ["ext.sms.local_capture"],
                        }
                    ],
                }
            }
            login_receipt = {
                "schema": "otp-local-capture-live-journey",
                "status": "passed",
                "target": "alpha-local",
                "launchPolicy": "test_live",
                "baselineId": "",
                "sourceRevision": "a" * 40,
                "configurationDigest": "sha256:" + "1" * 64,
                "providerRuntimeDigest": provider_runtime_digest,
                "startupAttemptId": "attempt-a",
                "challengePresent": True,
                "sessionPresent": True,
                "nonPromotable": True,
                "receiptRef": "receipt:otp-login:attempt-a",
                "receiptDigest": "sha256:" + "6" * 64,
            }

            def fetch(url: str, **_kwargs: object) -> tuple[bool, int, str, str]:
                return (
                    True,
                    200,
                    provider_health if "17330" in url else '{"status":"ok"}',
                    "application/json",
                )

            with (
                patch.object(
                    stackctl,
                    "load_test_live_startup_attempt",
                    return_value={
                        "status": "running",
                        "environment": "alpha",
                        "target": "alpha-local",
                        "workload": "full",
                        "configurationDigest": "sha256:" + "1" * 64,
                        "providerRuntimeDigest": provider_runtime_digest,
                    },
                ),
                patch.object(
                    stackctl,
                    "_active_provider_runtime",
                    return_value=provider_runtime,
                ),
                patch.object(
                    stackctl,
                    "compile_provider_runtime_composition",
                    return_value=provider_runtime["composition"],
                ),
                patch.object(
                    stackctl,
                    "load_test_live_content_binding",
                    return_value=None,
                ),
                patch.object(
                    stackctl,
                    "verify_certificate",
                    return_value={"profile": "local-managed", "status": "ready"},
                ),
                patch.object(stackctl, "fetch_url", side_effect=fetch),
                patch.object(
                    stackctl,
                    "_execute_otp_login_journey",
                    return_value=login_receipt,
                ),
                patch.object(
                    stackctl,
                    "command_app_content_preflight",
                    return_value={
                        "exitCode": 0,
                        "packageBaseline": "sha256:" + "2" * 64,
                        "sourceRevision": "a" * 40,
                        "releaseId": "release-a",
                        "manifestDigest": "sha256:" + "3" * 64,
                        "readinessReceiptRef": "receipt:readiness:release-a",
                        "readinessReceiptDigest": "sha256:" + "4" * 64,
                        "lifecycleExitRef": "receipt:lifecycle:release-a",
                        "appUatEnvelope": {
                            "schema": "quwoquan_data.app_uat_envelope",
                            "releaseId": "release-a",
                        },
                        "contentReadback": {
                            "homepagePostIds": ["post-a"],
                        },
                        "contentReadinessReportRef": (
                            "receipt:content-readiness:release-a"
                        ),
                    },
                ),
            ):
                passed = stackctl.command_app_debug_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir),
                        runtime_mode="test_live",
                    )
                )
                provider_health = provider_health.replace(
                    "sha256:" + "1" * 64,
                    "sha256:" + "9" * 64,
                )
                mismatched = stackctl.command_app_debug_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir / "configuration-mismatch"),
                        runtime_mode="test_live",
                    )
                )

            self.assertEqual(passed["exitCode"], 0)
            self.assertTrue(passed["provider"]["nonPromotable"])
            self.assertEqual(
                passed["provider"]["adapterId"],
                "ext.sms.local_capture",
            )
            self.assertEqual(passed["launchPolicy"], "test_live")
            self.assertEqual(passed["contentBindingState"], "unbound")
            self.assertEqual(passed["packageBaseline"], "")
            self.assertEqual(passed["releaseId"], "")
            self.assertTrue(passed["loginJourney"]["sessionPresent"])
            self.assertEqual(mismatched["exitCode"], 0)
            self.assertEqual(mismatched["status"], "warning")
            self.assertFalse(mismatched["details"])
            self.assertIn("mismatch", " ".join(mismatched["warnings"]))

            with patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value={
                    "status": "stopped",
                    "environment": "alpha",
                    "target": "alpha-local",
                    "workload": "full",
                    "configurationDigest": "sha256:" + "1" * 64,
                    "providerRuntimeDigest": provider_runtime_digest,
                },
            ), patch.object(
                stackctl,
                "_active_provider_runtime",
                return_value=provider_runtime,
            ), patch.object(
                stackctl,
                "compile_provider_runtime_composition",
                return_value=provider_runtime["composition"],
            ), patch.object(
                stackctl,
                "load_test_live_content_binding",
                return_value=None,
            ), patch.object(
                stackctl,
                "verify_certificate",
                return_value={"profile": "local-managed", "status": "ready"},
            ), patch.object(stackctl, "fetch_url", side_effect=fetch), patch.object(
                stackctl,
                "_execute_otp_login_journey",
                return_value=login_receipt,
            ), patch.object(
                stackctl,
                "command_app_content_preflight",
                return_value={"exitCode": 0},
            ):
                stopped = stackctl.command_app_debug_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir / "stopped"),
                        runtime_mode="test_live",
                    )
                )
            self.assertEqual(stopped["exitCode"], 0)
            self.assertEqual(stopped["status"], "warning")
            self.assertFalse(stopped["details"])
            self.assertIn("not running", " ".join(stopped["warnings"]))
            provider_health = provider_health.replace(
                "sha256:" + "9" * 64,
                "sha256:" + "1" * 64,
            )

            with patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value={
                    "status": "running",
                    "environment": "alpha",
                    "target": "alpha-local",
                    "workload": "full",
                    "configurationDigest": "sha256:" + "1" * 64,
                    "providerRuntimeDigest": provider_runtime_digest,
                },
            ), patch.object(
                stackctl,
                "_active_provider_runtime",
                side_effect=AssertionError(
                    "test_live preflight must not read an active candidate"
                ),
            ), patch.object(
                stackctl,
                "compile_provider_runtime_composition",
                return_value=provider_runtime["composition"],
            ), patch.object(
                stackctl,
                "load_test_live_content_binding",
                return_value=None,
            ), patch.object(
                stackctl,
                "verify_certificate",
                return_value={"profile": "local-managed", "status": "ready"},
            ), patch.object(stackctl, "fetch_url", side_effect=fetch), patch.object(
                stackctl,
                "_execute_otp_login_journey",
                return_value=login_receipt,
            ), patch.object(
                stackctl,
                "command_app_content_preflight",
                return_value={"exitCode": 0},
            ):
                candidate_independent = stackctl.command_app_debug_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir / "missing-candidate"),
                        runtime_mode="test_live",
                    )
                )
            self.assertEqual(candidate_independent["exitCode"], 0)
            self.assertEqual(candidate_independent["status"], "warning")
            self.assertNotIn(
                "candidate",
                " ".join(candidate_independent["warnings"]).lower(),
            )

    def test_debug_preflight_explicit_candidate_mode_binds_login_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "candidate-preflight"
            baseline_id = "sha256:" + "2" * 64
            configuration_digest = "sha256:" + "1" * 64
            provider_digest = "sha256:" + "5" * 64
            provider_runtime = {
                "baselineId": baseline_id,
                "composition": {
                    "runtimeCompositionDigest": provider_digest,
                    "workloads": [
                        {
                            "role": "sms-provider-substitute",
                            "adapterIds": ["ext.sms.local_capture"],
                        }
                    ],
                },
            }
            startup = {
                "status": "running",
                "env": "alpha",
                "target": "alpha-local",
                "workload": "full",
                "attemptId": "attempt-candidate-a",
                "candidateDigest": baseline_id,
                "configurationDigest": configuration_digest,
                "providerRuntimeDigest": provider_digest,
            }
            login_receipt = {
                "schema": "otp-local-capture-live-journey",
                "status": "passed",
                "target": "alpha-local",
                "launchPolicy": "immutable_candidate",
                "baselineId": baseline_id,
                "sourceRevision": "a" * 40,
                "configurationDigest": configuration_digest,
                "providerRuntimeDigest": provider_digest,
                "startupAttemptId": "attempt-candidate-a",
                "challengePresent": True,
                "sessionPresent": True,
                "nonPromotable": True,
                "receiptRef": "receipt:otp-login:attempt-candidate-a",
                "receiptDigest": "sha256:" + "6" * 64,
            }

            def fetch(url: str, **_kwargs: object) -> tuple[bool, int, str, str]:
                body = (
                    json.dumps(
                        {
                            "status": "ready",
                            "adapterId": "ext.sms.local_capture",
                            "environment": "alpha",
                            "configurationDigest": configuration_digest,
                            "profile": "success",
                            "nonPromotable": True,
                        }
                    )
                    if "17330" in url
                    else '{"status":"ok"}'
                )
                return True, 200, body, "application/json"

            with (
                patch.object(
                    stackctl,
                    "_active_provider_runtime",
                    return_value=provider_runtime,
                ),
                patch.object(
                    stackctl,
                    "load_startup_attempt",
                    return_value=startup,
                ),
                patch.object(
                    stackctl,
                    "load_test_live_content_binding",
                    return_value=None,
                ),
                patch.object(
                    stackctl,
                    "verify_certificate",
                    return_value={"profile": "local-managed", "status": "ready"},
                ),
                patch.object(stackctl, "fetch_url", side_effect=fetch),
                patch.object(
                    stackctl,
                    "_execute_otp_login_journey",
                    return_value=login_receipt,
                ) as execute_login,
            ):
                result = stackctl.command_app_debug_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir),
                        runtime_mode="immutable_candidate",
                    )
                )

            self.assertEqual(result["exitCode"], 0)
            self.assertEqual(result["launchPolicy"], "immutable_candidate")
            self.assertEqual(result["packageBaseline"], baseline_id)
            self.assertEqual(
                result["loginJourneyReceiptDigest"],
                login_receipt["receiptDigest"],
            )
            execute_login.assert_called_once()
            self.assertEqual(
                execute_login.call_args.kwargs["runtime_mode"],
                "immutable_candidate",
            )

    def test_active_candidate_resolves_only_commercial_release_and_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory, patch.dict(
            os.environ,
            {"QWQ_OUTPUT_ROOT": temporary_directory},
        ):
            root = Path(temporary_directory)
            candidate_dir = root / "candidate"
            candidate_dir.mkdir()
            attestation = root / "release.json"
            attestation.write_text(
                json.dumps(
                    {
                        "releaseClass": "commercial",
                        "productLifecycleState": "commercial",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            attestation_digest = "sha256:" + hashlib.sha256(
                attestation.read_bytes()
            ).hexdigest()
            manifest_digest = "sha256:" + "1" * 64
            manifest = {
                "baselineId": "sha256:" + "2" * 64,
                "sourceRevision": "revision-a",
                "release": {
                    "candidate": {
                        "releaseId": "release-a",
                        "releaseDigest": manifest_digest,
                        "attestationRef": str(attestation),
                        "attestationDigest": attestation_digest,
                    }
                },
            }
            (candidate_dir / "manifest.json").write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            readiness_path = (
                root
                / "env/alpha/runs/data-release/release-a/verify-a/release-readiness.json"
            )
            readiness_path.parent.mkdir(parents=True)
            readiness_path.write_text("{}\n", encoding="utf-8")
            lifecycle_path = (
                root
                / "env/alpha/runs/release-lifecycle-exit/release-a/exit-a/lifecycle-exit.json"
            )
            lifecycle_path.parent.mkdir(parents=True)
            lifecycle_path.write_text("{}\n", encoding="utf-8")
            readiness = {
                "releaseId": "release-a",
                "releaseClass": "commercial",
                "productLifecycleState": "commercial",
                "readinessPhase": "commercial",
                "verifyRunId": "verify-a",
                "manifestDigest": manifest_digest,
                "counts": {"posts": 3, "creators": 1},
                "postIds": ["article-a", "image-a", "video-a"],
                "creatorIds": ["creator-a"],
                "feedQueries": [
                    {"name": "typed_article", "matchedPostIds": ["article-a"]},
                    {"name": "typed_image", "matchedPostIds": ["image-a"]},
                    {"name": "typed_video", "matchedPostIds": ["video-a"]},
                    {
                        "name": "homepage_recommend",
                        "matchedPostIds": ["article-a", "image-a", "video-a"],
                    },
                    {"name": "premium_stream", "matchedPostIds": ["video-a"]},
                ],
                "appUatEnvelope": {
                    "releaseId": "release-a",
                    "releaseClass": "commercial",
                    "productLifecycleState": "commercial",
                    "homepageId": "homepage-a",
                    "homepageTitle": "首页 A",
                    "articleWorkId": "article-a",
                    "articleTitle": "文章 A",
                    "imageWorkId": "image-a",
                    "imageTitle": "图片 A",
                    "videoWorkId": "video-a",
                    "creatorName": "创作者 A",
                    "creatorUserHandle": "creator-a",
                    "creatorPersonaId": "persona-a",
                    "creatorAvatarAssetId": "avatar-a",
                    "tagLabel": "标签 A",
                    "videoAttribution": "来源 A",
                },
            }

            with (
                patch.object(
                    stackctl,
                    "active_deployment_candidate",
                    return_value={"candidateDir": str(candidate_dir)},
                ),
                patch.object(
                    stackctl,
                    "_load_data_release_readiness",
                    return_value=(readiness, readiness_path),
                ) as load_readiness,
                patch.object(
                    stackctl,
                    "_load_data_release_lifecycle_exit",
                    return_value=({}, lifecycle_path),
                ) as load_lifecycle,
            ):
                resolved = stackctl._resolve_active_app_content_evidence(
                    "alpha-local"
                )

            self.assertEqual(resolved[0]["baselineId"], manifest["baselineId"])
            self.assertEqual(resolved[1], readiness)
            self.assertEqual(resolved[2], readiness_path)
            self.assertEqual(
                resolved[3],
                "env/alpha/runs/release-lifecycle-exit/"
                "release-a/exit-a/lifecycle-exit.json",
            )
            self.assertEqual(
                load_readiness.call_args.kwargs["readiness_phase"],
                stackctl.ReadinessPhase.COMMERCIAL,
            )
            self.assertEqual(
                load_lifecycle.call_args.kwargs["lifecycle_exit_ref"],
                resolved[3],
            )

    def test_preflight_returns_release_bound_machine_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "report"
            manifest_digest = "sha256:" + "3" * 64
            readiness_path = Path(temporary_directory) / "release-readiness.json"
            readiness = {
                "releaseId": "release-a",
                "releaseClass": "commercial",
                "productLifecycleState": "commercial",
                "readinessPhase": "commercial",
                "verifyRunId": "verify-a",
                "manifestDigest": manifest_digest,
                "counts": {"posts": 3, "creators": 1},
                "postIds": ["article-a", "image-a", "video-a"],
                "creatorIds": ["creator-a"],
                "feedQueries": [
                    {"name": "typed_article", "matchedPostIds": ["article-a"]},
                    {"name": "typed_image", "matchedPostIds": ["image-a"]},
                    {"name": "typed_video", "matchedPostIds": ["video-a"]},
                    {
                        "name": "homepage_recommend",
                        "matchedPostIds": ["article-a", "image-a", "video-a"],
                    },
                    {"name": "premium_stream", "matchedPostIds": ["video-a"]},
                ],
                "appUatEnvelope": {
                    "releaseId": "release-a",
                    "releaseClass": "commercial",
                    "productLifecycleState": "commercial",
                    "homepageId": "homepage-a",
                    "homepageTitle": "首页 A",
                    "articleWorkId": "article-a",
                    "articleTitle": "文章 A",
                    "imageWorkId": "image-a",
                    "imageTitle": "图片 A",
                    "videoWorkId": "video-a",
                    "creatorName": "创作者 A",
                    "creatorUserHandle": "creator-a",
                    "creatorPersonaId": "persona-a",
                    "creatorAvatarAssetId": "avatar-a",
                    "tagLabel": "标签 A",
                    "videoAttribution": "来源 A",
                },
            }
            with (
                patch.object(
                    stackctl,
                    "_resolve_active_app_content_evidence",
                    return_value=(
                        {
                            "baselineId": "sha256:" + "4" * 64,
                            "sourceRevision": "revision-a",
                        },
                        readiness,
                        readiness_path,
                        "env/alpha/runs/release-lifecycle-exit/"
                        "release-a/exit-a/lifecycle-exit.json",
                    ),
                ),
                patch.object(
                    stackctl,
                    "command_content_readiness",
                    return_value={"exitCode": 0, "details": ["passed"]},
                ),
            ):
                result = stackctl.command_app_content_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir),
                    )
                )

            self.assertEqual(result["exitCode"], 0)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["releaseId"], "release-a")
            self.assertEqual(result["appUatEnvelope"]["videoWorkId"], "video-a")
            self.assertEqual(
                result["contentReadback"]["postIds"],
                ["article-a", "image-a", "video-a"],
            )
            self.assertRegex(
                result["readinessReceiptDigest"],
                r"^sha256:[0-9a-f]{64}$",
            )
            persisted = json.loads(
                (report_dir / "report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["manifestDigest"], manifest_digest)

    def test_test_live_preflight_resolves_binding_without_active_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "test-live-report"
            readiness_path = Path(temporary_directory) / "release-readiness.json"
            readiness = {
                "releaseId": "release-test-live-a",
                "releaseClass": "research",
                "productLifecycleState": "research",
                "readinessPhase": "consumer",
                "verifyRunId": "verify-test-live-a",
                "manifestDigest": "sha256:" + "3" * 64,
                "postIds": ["article-a", "image-a", "video-a"],
                "creatorIds": ["creator-a"],
                "feedQueries": [
                    {"name": "typed_article", "matchedPostIds": ["article-a"]},
                    {"name": "typed_image", "matchedPostIds": ["image-a"]},
                    {"name": "typed_video", "matchedPostIds": ["video-a"]},
                    {
                        "name": "homepage_recommend",
                        "matchedPostIds": ["article-a", "image-a", "video-a"],
                    },
                ],
                "appUatEnvelope": {
                    "releaseId": "release-test-live-a",
                    "releaseClass": "research",
                    "productLifecycleState": "research",
                    "homepageId": "homepage-a",
                    "homepageTitle": "首页 A",
                    "articleWorkId": "article-a",
                    "articleTitle": "文章 A",
                    "imageWorkId": "image-a",
                    "imageTitle": "图片 A",
                    "videoWorkId": "video-a",
                    "creatorName": "创作者 A",
                    "creatorUserHandle": "creator-a",
                    "creatorPersonaId": "persona-a",
                    "creatorAvatarAssetId": "avatar-a",
                    "tagLabel": "标签 A",
                    "videoAttribution": "来源 A",
                },
            }
            binding = {
                "readinessReceiptDigest": "sha256:" + "4" * 64,
            }
            mutable_resolver = unittest.mock.Mock(
                return_value=(
                    {"baselineId": "", "sourceRevision": "revision-a"},
                    readiness,
                    readiness_path,
                    "",
                )
            )
            with (
                patch.object(
                    stackctl,
                    "_resolve_test_live_app_content_evidence",
                    mutable_resolver,
                ),
                patch.object(
                    stackctl,
                    "_resolve_active_app_content_evidence",
                    side_effect=AssertionError("must not read active candidate"),
                ),
                patch.object(
                    stackctl,
                    "command_content_readiness",
                    return_value={"exitCode": 0, "details": ["passed"]},
                ),
            ):
                result = stackctl.command_app_content_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir),
                        runtime_mode="test_live",
                        content_binding=binding,
                    )
                )

            self.assertEqual(result["exitCode"], 0, result)
            self.assertEqual(result["packageBaseline"], "")
            self.assertEqual(
                result["readinessReceiptDigest"],
                binding["readinessReceiptDigest"],
            )
            mutable_resolver.assert_called_once_with("alpha-local", binding)

    def test_research_preflight_uses_research_readiness_without_lifecycle_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "research-report"
            readiness_path = Path(temporary_directory) / "release-readiness.json"
            readiness = {
                "releaseId": "release-research-a",
                "releaseClass": "research",
                "productLifecycleState": "research",
                "readinessPhase": "research",
                "verifyRunId": "verify-research-a",
                "manifestDigest": "sha256:" + "3" * 64,
                "postIds": ["article-a", "image-a", "video-a"],
                "creatorIds": ["creator-a"],
                "feedQueries": [
                    {"name": "typed_article", "matchedPostIds": ["article-a"]},
                    {"name": "typed_image", "matchedPostIds": ["image-a"]},
                    {"name": "typed_video", "matchedPostIds": ["video-a"]},
                    {
                        "name": "homepage_recommend",
                        "matchedPostIds": ["article-a", "image-a", "video-a"],
                    },
                    {"name": "premium_stream", "matchedPostIds": ["video-a"]},
                ],
                "appUatEnvelope": {
                    "releaseId": "release-research-a",
                    "releaseClass": "research",
                    "productLifecycleState": "research",
                    "homepageId": "homepage-a",
                    "homepageTitle": "海港灯塔",
                    "articleWorkId": "article-a",
                    "articleTitle": "灯塔维护手记",
                    "imageWorkId": "image-a",
                    "imageTitle": "潮汐时刻",
                    "videoWorkId": "video-a",
                    "creatorName": "灯塔观察员",
                    "creatorUserHandle": "creator-a",
                    "creatorPersonaId": "persona-a",
                    "creatorAvatarAssetId": "avatar-a",
                    "tagLabel": "海港",
                    "videoAttribution": "公开来源",
                },
            }
            captured: dict[str, object] = {}

            def content_readiness(args: object) -> dict[str, object]:
                captured["phase"] = getattr(args, "phase")
                captured["lifecycleExitRef"] = getattr(args, "lifecycle_exit_ref")
                return {"exitCode": 0, "details": ["passed"]}

            with (
                patch.object(
                    stackctl,
                    "_resolve_active_app_content_evidence",
                    return_value=(
                        {"baselineId": "", "sourceRevision": "revision-a"},
                        readiness,
                        readiness_path,
                        "",
                    ),
                ),
                patch.object(
                    stackctl,
                    "command_content_readiness",
                    side_effect=content_readiness,
                ),
            ):
                result = stackctl.command_app_content_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir),
                    )
                )

            self.assertEqual(result["exitCode"], 0)
            self.assertEqual(captured["phase"], "research")
            self.assertEqual(captured["lifecycleExitRef"], "")
            self.assertEqual(result["lifecycleExitRef"], "")
            self.assertEqual(
                result["appUatPlan"]["searchCanaries"][1]["expectedObjectId"],
                "homepage-a",
            )

    def test_three_environment_uat_binds_each_running_test_live_runtime_and_runs_suites(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "uat"
            manifest_digest = "sha256:" + "5" * 64
            video_ids = [f"video-{index:02d}" for index in range(1, 21)]
            uat_plan = {
                "releaseId": "release-a",
                "searchCanaries": [
                    {
                        "kind": "post",
                        "query": "灯塔维护手记",
                        "expectedObjectType": "content.post",
                        "expectedObjectId": "article-a",
                    },
                    {
                        "kind": "homepage",
                        "query": "海港灯塔",
                        "expectedObjectType": "entity.homepage",
                        "expectedObjectId": "homepage-a",
                    },
                    {
                        "kind": "persona",
                        "query": "灯塔观察员",
                        "expectedObjectType": "user.profile",
                        "expectedObjectId": "persona-a",
                    },
                ],
                "videoPagination": {
                    "pageSize": 20,
                    "expectedWorkIds": video_ids,
                },
                "videoPlaybackCanaries": [
                    {"position": "first", "index": 0, "workId": "video-01"},
                    {"position": "middle", "index": 10, "workId": "video-11"},
                    {"position": "last", "index": 19, "workId": "video-20"},
                ],
                "mediaChecks": {
                    "automatic": True,
                    "avatarAssetId": "avatar-a",
                    "imageWorkId": "image-a",
                    "videoWorkIds": video_ids,
                },
            }

            def preflight(args: object) -> dict[str, object]:
                target = str(getattr(args, "target"))
                environment = target.removesuffix("-local")
                ordinal = {"alpha": "a", "beta": "b", "gamma": "c"}[environment]
                return {
                    "exitCode": 0,
                    "target": target,
                    "environment": environment,
                    "launchPolicy": "test_live",
                    "contentBindingState": "bound",
                    "packageBaseline": "",
                    "sourceRevision": ordinal * 40,
                    "configurationDigest": "sha256:" + ordinal * 64,
                    "providerRuntimeDigest": "sha256:" + "d" * 64,
                    "releaseId": "release-a",
                    "manifestDigest": manifest_digest,
                    "readinessReceiptRef": (
                        f"env/{environment}/runs/data-release/"
                        "release-a/verify-a/release-readiness.json"
                    ),
                    "readinessReceiptDigest": "sha256:" + ordinal * 64,
                    "lifecycleExitRef": "",
                    "appUatEnvelope": {
                        "releaseId": "release-a",
                        "homepageId": "homepage-a",
                        "homepageTitle": "首页 A",
                        "articleWorkId": "article-a",
                        "articleTitle": "文章 A",
                        "imageWorkId": "image-a",
                        "imageTitle": "图片 A",
                        "videoWorkId": "video-01",
                        "creatorName": "灯塔观察员",
                        "creatorUserHandle": "creator-a",
                        "creatorPersonaId": "persona-a",
                        "creatorAvatarAssetId": "avatar-a",
                        "tagLabel": "标签 A",
                        "videoAttribution": "来源 A",
                    },
                    "appUatPlan": uat_plan,
                    "appUatPlanDigest": stackctl._canonical_document_checksum(
                        uat_plan
                    ),
                }

            def startup(target: str) -> dict[str, object]:
                environment = target.removesuffix("-local")
                ordinal = {"alpha": "a", "beta": "b", "gamma": "c"}[environment]
                return {
                    "status": "running",
                    "failure": None,
                    "attemptId": f"{environment}-test-live-attempt",
                    "environment": environment,
                    "target": target,
                    "composeProject": f"quwoquan_{environment}_test_live",
                    "runRoot": f"/tmp/{environment}-test-live-run",
                    "sourceRevision": ordinal * 40,
                    "workspaceStatusDigest": "sha256:" + "1" * 64,
                    "mutableStateDigest": "sha256:" + "2" * 64,
                    "composeDigest": "sha256:" + "3" * 64,
                    "configurationDigest": "sha256:" + ordinal * 64,
                    "providerRuntimeDigest": "sha256:" + "d" * 64,
                    "resolverHandoffDigest": "sha256:" + "4" * 64,
                }

            def content_binding(target: str) -> dict[str, object]:
                active = startup(target)
                environment = target.removesuffix("-local")
                ordinal = {"alpha": "a", "beta": "b", "gamma": "c"}[environment]
                return {
                    "launchPolicy": "test_live",
                    "nonPromotable": True,
                    "retentionClass": "run_bound",
                    "contentBindingState": "bound",
                    "environment": environment,
                    "target": target,
                    "startupAttemptId": active["attemptId"],
                    "startupIdentity": {
                        field: active[field]
                        for field in stackctl._APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS
                    },
                    "releaseId": "release-a",
                    "verifyRunId": "verify-a",
                    "manifestDigest": manifest_digest,
                    "readinessPhase": "research",
                    "readinessReceiptRef": (
                        f"env/{environment}/runs/data-release/"
                        "release-a/verify-a/release-readiness.json"
                    ),
                    "readinessReceiptDigest": "sha256:" + ordinal * 64,
                    "lifecycleExitRef": "",
                    "appUatEnvelope": preflight(
                        stackctl.argparse.Namespace(target=target)
                    )["appUatEnvelope"],
                    "appUatPlan": uat_plan,
                    "appUatPlanDigest": stackctl._canonical_document_checksum(
                        uat_plan
                    ),
                }

            def smoke_command(
                _environment: str,
                target: str,
                _report_dir: Path,
                **kwargs: object,
            ) -> dict[str, object]:
                return {
                    "argv": ["smoke", str(kwargs["suite_name"])],
                    "cwd": Path(temporary_directory),
                    "reportPath": f"reports/{target}-{kwargs['suite_name']}.json",
                }

            def execute(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                if "verify_ios_hot_restart.py" in " ".join(map(str, argv)):
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        json.dumps(
                            {
                                "status": "passed",
                                "launchMode": "direct_flutter_run",
                                "consumerLeaseId": "sha256:" + "7" * 64,
                                "reportPath": "reports/direct-flutter-run.json",
                            }
                        ),
                        "",
                    )
                return subprocess.CompletedProcess(argv, 0, "", "")

            with (
                patch.object(
                    stackctl,
                    "command_app_debug_preflight",
                    side_effect=preflight,
                ),
                patch.object(
                    stackctl,
                    "load_test_live_startup_attempt",
                    side_effect=startup,
                ),
                patch.object(
                    stackctl,
                    "load_test_live_content_binding",
                    side_effect=content_binding,
                ),
                patch.object(
                    stackctl,
                    "_environment_page_smoke_profile_command",
                    side_effect=smoke_command,
                ) as smoke_profile,
                patch.object(
                    stackctl,
                    "run",
                    side_effect=execute,
                ) as run,
            ):
                result = stackctl.command_app_content_uat(
                    stackctl.argparse.Namespace(
                        targets="alpha-local,beta-local,gamma-local",
                        platform="ios-simulator",
                        device_id="SIMULATOR-UDID",
                        dry_run=True,
                        report_dir=str(report_dir),
                    )
                )

            self.assertEqual(result["exitCode"], 0)
            self.assertEqual(result["status"], "planned")
            self.assertEqual(result["launchPolicy"], "test_live")
            self.assertEqual(result["packageBaseline"], "")
            self.assertEqual(
                set(result["runtimeBindings"]),
                {"alpha-local", "beta-local", "gamma-local"},
            )
            self.assertEqual(
                len(set(result["runtimeBindingDigests"].values())),
                3,
            )
            self.assertIn("no runtime evidence", result["details"][0])
            self.assertRegex(
                result["appUatEnvelopeDigest"],
                r"^sha256:[0-9a-f]{64}$",
            )
            self.assertEqual(len(result["runs"]), 27)
            self.assertEqual(run.call_count, 24)
            self.assertEqual(result["appUatPlan"], uat_plan)
            direct_calls = [
                call
                for call in run.call_args_list
                if "verify_ios_hot_restart.py" in " ".join(map(str, call.args[0]))
            ]
            self.assertEqual(len(direct_calls), 3)
            for call in direct_calls:
                self.assertIn("direct_flutter_run", call.args[0])
                self.assertIn("--preflight-only", call.args[0])
            patrol_calls = [
                call for call in run.call_args_list if call not in direct_calls
            ]
            for call in patrol_calls:
                self.assertIn("--platform", call.args[0])
                self.assertIn("ios", call.args[0])
                self.assertIn("--dry-run", call.args[0])
            core_calls = [
                call
                for call in patrol_calls
                if "app-content-app-core-readback" in " ".join(map(str, call.args[0]))
            ]
            self.assertEqual(len(core_calls), 3)
            for call in core_calls:
                self.assertIn("--data-release-id", call.args[0])
                self.assertIn("release-a", call.args[0])
                self.assertIn("--data-release-creator-user-handle", call.args[0])
                self.assertIn("creator-a", call.args[0])
                self.assertIn("--data-release-creator-persona-id", call.args[0])
                self.assertIn("persona-a", call.args[0])
                self.assertIn(
                    "--data-release-creator-avatar-asset-id",
                    call.args[0],
                )
                self.assertIn("avatar-a", call.args[0])
            home_video_calls = [
                call
                for call in smoke_profile.call_args_list
                if call.kwargs.get("suite_name")
                == "app-content-home-video-playback"
            ]
            self.assertEqual(len(home_video_calls), 3)
            for call in home_video_calls:
                self.assertEqual(
                    call.kwargs.get("patrol_target"),
                    stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
                )
                self.assertIsNotNone(call.kwargs.get("data_readiness_path"))
            video_canary_calls = [
                call
                for call in smoke_profile.call_args_list
                if str(call.kwargs.get("suite_name", "")).startswith(
                    "app-content-video-playback-"
                )
            ]
            self.assertEqual(len(video_canary_calls), 9)
            self.assertEqual(
                {
                    str(call.kwargs.get("release_video_work_id"))
                    for call in video_canary_calls
                },
                {"video-01", "video-11", "video-20"},
            )
            planned_search = [
                item
                for item in result["runs"]
                if item.get("suite") == "release-bound-search-and-video-page"
            ]
            self.assertEqual(len(planned_search), 3)
            self.assertTrue(
                all(item.get("searchCanaries") == uat_plan["searchCanaries"] for item in planned_search)
            )
            fault_calls = [
                call
                for call in patrol_calls
                if "app-content-controlled-edge-recovery"
                in " ".join(map(str, call.args[0]))
            ]
            self.assertEqual(len(fault_calls), 3)
            for call in fault_calls:
                self.assertIn("--stackctl-controlled-edge-fault", call.args[0])

    def test_app_content_uat_rejects_nonrunning_or_unbound_test_live(self) -> None:
        preflight = {
            "launchPolicy": "test_live",
            "target": "alpha-local",
            "environment": "alpha",
            "packageBaseline": "",
        }
        with patch.object(
            stackctl,
            "load_test_live_startup_attempt",
            return_value=None,
        ), self.assertRaisesRegex(ValueError, "current running test_live receipt"):
            stackctl._app_content_test_live_runtime_binding(preflight)

        running = {
            "status": "running",
            "failure": None,
        }
        with (
            patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value=running,
            ),
            patch.object(
                stackctl,
                "load_test_live_content_binding",
                return_value=None,
            ),
            self.assertRaisesRegex(ValueError, "run-bound content binding"),
        ):
            stackctl._app_content_test_live_runtime_binding(preflight)

    def test_app_content_uat_typed_actor_policy_matches_runner_contract(self) -> None:
        alpha_targets = {
            stackctl.DISCOVERY_FEED_UAT_TEST_TARGET,
            stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
            stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
            stackctl.VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
            stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
        }
        for target in alpha_targets:
            self.assertTrue(
                stackctl._app_content_uat_requires_typed_actor("alpha", target)
            )
        for environment in ("beta", "gamma"):
            self.assertTrue(
                stackctl._app_content_uat_requires_typed_actor(
                    environment,
                    stackctl.APP_CORE_READBACK_UAT_TEST_TARGET,
                )
            )
            self.assertTrue(
                stackctl._app_content_uat_requires_typed_actor(
                    environment,
                    stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
                )
            )
            for target in (
                stackctl.DISCOVERY_FEED_UAT_TEST_TARGET,
                stackctl.VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
                stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
            ):
                self.assertFalse(
                    stackctl._app_content_uat_requires_typed_actor(
                        environment,
                        target,
                    )
                )

    def test_app_content_uat_actor_context_binds_runtime_release_and_otp(self) -> None:
        manifest_digest = "sha256:" + "7" * 64
        startup_attempt_id = "alpha-test-live-current"
        runtime_binding = {
            "environment": "alpha",
            "target": "alpha-local",
            "startupAttemptId": startup_attempt_id,
            "releaseId": "release-a",
            "verifyRunId": "verify-a",
            "manifestDigest": manifest_digest,
            "readinessPhase": "research",
            "startupIdentity": {
                "mutableStateDigest": "sha256:" + "1" * 64,
                "composeDigest": "sha256:" + "2" * 64,
                "configurationDigest": "sha256:" + "3" * 64,
            },
        }
        preflight = {
            "provider": {
                "adapterId": "ext.sms.local_capture",
                "environment": "alpha",
                "configurationDigest": "sha256:" + "3" * 64,
                "nonPromotable": True,
                "ready": True,
            },
            "loginJourney": {
                "status": "passed",
                "challengePresent": True,
                "sessionPresent": True,
                "startupAttemptId": startup_attempt_id,
                "nonPromotable": True,
                "receiptRef": "env/alpha/runs/login/report.json",
                "receiptDigest": "sha256:" + "4" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            readiness_path = root / "release-readiness.json"
            readiness_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "environment": "alpha",
                        "releaseId": "release-a",
                        "verifyRunId": "verify-a",
                        "manifestDigest": manifest_digest,
                        "readinessPhase": "research",
                        "importRunId": "import-a",
                        "postIds": ["post-a"],
                    }
                ),
                encoding="utf-8",
            )
            context = stackctl._app_content_test_live_actor_context(
                preflight=preflight,
                runtime_binding=runtime_binding,
                readiness_path=readiness_path,
                report_dir=root / "uat",
            )

        self.assertEqual(context.candidate.baseline_id, "sha256:" + "1" * 64)
        self.assertEqual(context.candidate.package_digest, "sha256:" + "2" * 64)
        self.assertEqual(context.candidate.release_post_ids, ("post-a",))
        self.assertEqual(
            context.provider_evidence[
                AUTHENTICATED_ACTORS.required_provider_capabilities[0].value
            ][
                "candidateBindingDigest"
            ],
            context.candidate.digest,
        )

if __name__ == "__main__":
    unittest.main()
