"""app content preflight: debug 预检、候选解析与 release 绑定回执合约。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""
from __future__ import annotations

from quwoquan_ops.tests.support.app_content_preflight_test_support import (
    Path,
    hashlib,
    json,
    os,
    patch,
    patrol_smoke,
    stackctl,
    tempfile,
    unittest,
)


class AppContentPreflightDebugRuntimeTest(unittest.TestCase):
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
                        "observabilityLogSinkDigest": "sha256:" + "7" * 64,
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
                patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value={
                        "issues": [],
                        "warnings": [],
                        "blocker": "",
                        "evidence": {"status": "ready"},
                    },
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
                    "observabilityLogSinkDigest": "sha256:" + "7" * 64,
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
            ), patch.object(
                stackctl,
                "local_runtime_capacity_evidence",
                return_value={
                    "issues": [],
                    "warnings": [],
                    "blocker": "",
                    "evidence": {"status": "ready"},
                },
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
                    "observabilityLogSinkDigest": "sha256:" + "7" * 64,
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
            ), patch.object(
                stackctl,
                "local_runtime_capacity_evidence",
                return_value={
                    "issues": [],
                    "warnings": [],
                    "blocker": "",
                    "evidence": {"status": "ready"},
                },
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
                "observabilityLogSinkDigest": "sha256:" + "7" * 64,
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
                patch.object(
                    stackctl,
                    "local_runtime_capacity_evidence",
                    return_value={
                        "issues": [],
                        "warnings": [],
                        "blocker": "",
                        "evidence": {"status": "ready"},
                    },
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
                        (
                            "env/alpha/runs/release-lifecycle-exit/"
                            "release-a/exit-a/lifecycle-exit.json"
                        ),
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
