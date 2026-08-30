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

    def test_preflight_drops_retired_readiness_fields_before_planner(
        self,
    ) -> None:
        readiness = {
            "releaseId": "release-a",
            "readinessPhase": "commercial",
            "appUatEnvelope": {
                "releaseId": "release-other",
                "videoWorkId": "legacy-video",
            },
            "appUatEnvelopeDigest": "sha256:" + "0" * 64,
        }
        release_contract = {
            "releaseHeader": {"releaseId": "release-a"},
            "releaseUatSamplePlan": {
                "releaseId": "release-a",
                "samples": [
                    {
                        "sampleId": "canary-video-001",
                        "carrier": "video",
                        "objectId": "release-video",
                        "objectRef": "objects/posts/video/release-video",
                        "objectDigest": "sha256:" + "7" * 64,
                    }
                ],
            },
            "releaseUatSamplePlanDigest": "sha256:" + "1" * 64,
        }
        projected_plan = {
            "releaseIdentity": {"releaseId": "release-a"},
            "carrierIdentities": {"video": "release-video"},
        }
        with patch.object(
            stackctl,
            "build_app_content_uat_plan",
            return_value=projected_plan,
        ) as build_plan:
            self.assertEqual(
                stackctl.app_preflight_commands._app_content_uat_sample_plan(
                    release_contract=release_contract,
                    readiness=readiness,
                ),
                projected_plan,
            )
        self.assertIsNot(build_plan.call_args.args[0], readiness)
        self.assertNotIn("appUatEnvelope", build_plan.call_args.args[0])
        self.assertNotIn("appUatEnvelopeDigest", build_plan.call_args.args[0])
        self.assertEqual(
            build_plan.call_args.kwargs["release_uat_sample_plan"],
            release_contract["releaseUatSamplePlan"],
        )

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

    def test_active_release_uat_contract_rejects_digest_drift_and_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            release_root = root / "release"
            header_path = release_root / "payload/release.json"
            sample_path = release_root / "payload/uat/sample_plan.json"
            attestation_path = release_root / "attestations/release.json"
            sample_path.parent.mkdir(parents=True)
            attestation_path.parent.mkdir(parents=True)
            sample_path.write_text(
                json.dumps({"schema": "quwoquan_data.release_uat_sample_plan"}),
                encoding="utf-8",
            )
            sample_digest = "sha256:" + hashlib.sha256(sample_path.read_bytes()).hexdigest()
            header_path.write_text(json.dumps({
                "releaseId": "release-a",
                "releaseClass": "research",
                "productLifecycleState": "research",
                "samplePlanRef": "uat/sample_plan.json",
                "samplePlanDigest": sample_digest,
            }), encoding="utf-8")
            attestation_path.write_text(json.dumps({
                "schema": "quwoquan_data.release_attestation",
                "releaseId": "release-a",
                "releaseClass": "research",
                "productLifecycleState": "research",
                "payloadSha256": "sha256:" + "3" * 64,
            }), encoding="utf-8")
            candidate = {
                "releaseId": "release-a",
                "releaseDigest": "sha256:" + "3" * 64,
                "attestationRef": str(attestation_path),
                "attestationDigest": "sha256:" + hashlib.sha256(attestation_path.read_bytes()).hexdigest(),
            }
            with self.assertRaisesRegex(ValueError, "payload digest drifted"):
                stackctl.app_preflight_commands._load_active_release_uat_contract(candidate)

            with patch(
                "quwoquan_ops.cli.commands.app_preflight_evidence._payload_tree_digest",
                return_value=candidate["releaseDigest"],
            ):
                loaded = stackctl.app_preflight_commands._load_active_release_uat_contract(candidate)
            self.assertEqual(loaded["releaseUatSamplePlanDigest"], sample_digest)

            sample_path.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.release_uat_sample_plan",
                        "releaseId": "release-drift",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch(
                    "quwoquan_ops.cli.commands.app_preflight_evidence._payload_tree_digest",
                    return_value=candidate["releaseDigest"],
                ),
                self.assertRaisesRegex(ValueError, "digest drifted"),
            ):
                stackctl.app_preflight_commands._load_active_release_uat_contract(candidate)

            sample_path.unlink()
            outside = root / "outside.json"
            outside.write_text(
                json.dumps({"schema": "quwoquan_data.release_uat_sample_plan"}),
                encoding="utf-8",
            )
            sample_path.symlink_to(outside)
            escaped_digest = "sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest()
            header_path.write_text(json.dumps({
                "releaseId": "release-a",
                "releaseClass": "research",
                "productLifecycleState": "research",
                "samplePlanRef": "uat/sample_plan.json",
                "samplePlanDigest": escaped_digest,
            }), encoding="utf-8")
            with (
                patch(
                    "quwoquan_ops.cli.commands.app_preflight_evidence._payload_tree_digest",
                    return_value=candidate["releaseDigest"],
                ),
                self.assertRaisesRegex(ValueError, "must not be a symlink"),
            ):
                stackctl.app_preflight_commands._load_active_release_uat_contract(candidate)

    def test_preflight_returns_release_bound_machine_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report_dir = root / "report"
            release_id = "release-a"
            release_root = root / "data/releases" / release_id
            readiness_path = root / "release-readiness.json"
            sample_plan = {
                "schema": "quwoquan_data.release_uat_sample_plan",
                "releaseId": release_id,
                "milestone": "M100",
                "sampleCases": [
                    {"sampleId": "homepage-1", "carrier": "homepage", "objectId": "entity-a"},
                    {"sampleId": "article-1", "carrier": "article", "objectId": "article-a"},
                    {"sampleId": "image-1", "carrier": "image", "objectId": "image-a"},
                    {"sampleId": "video-1", "carrier": "video", "objectId": "video-a"},
                ],
            }
            sample_path = release_root / "payload/uat/sample_plan.json"
            sample_path.parent.mkdir(parents=True)
            sample_path.write_text(json.dumps(sample_plan), encoding="utf-8")
            sample_digest = "sha256:" + hashlib.sha256(sample_path.read_bytes()).hexdigest()
            header = {
                "releaseId": release_id,
                "releaseClass": "commercial",
                "productLifecycleState": "commercial",
                "selectionScope": "milestone",
                "milestone": "M100",
                "poolDigest": "sha256:" + "2" * 64,
                "samplePlanRef": "uat/sample_plan.json",
                "samplePlanDigest": sample_digest,
                "contents": [
                    {"contentId": "article-a", "postRef": "article/a"},
                    {"contentId": "image-a", "postRef": "image/a"},
                    {"contentId": "video-a", "postRef": "video/a"},
                ],
                "authors": [],
            }
            header_path = release_root / "payload/release.json"
            header_path.write_text(json.dumps(header), encoding="utf-8")
            for ref, content_type, title, extra in (
                ("article/a", "article", "文章 A", {"creatorProfileId": "creator-a", "tagRefs": ["Topic/a"]}),
                ("image/a", "image", "图片 A", {}),
                ("video/a", "video", "视频 A", {"sourceAttribution": {"attributionText": "来源 A"}}),
            ):
                post_path = release_root / "payload/objects/posts" / ref / "manifest.json"
                post_path.parent.mkdir(parents=True)
                post_path.write_text(json.dumps({"contentType": content_type, "title": title, **extra}), encoding="utf-8")
            entity_path = release_root / "payload/objects/entities/entity-a/_entity.json"
            entity_path.parent.mkdir(parents=True)
            entity_path.write_text(json.dumps({"label": "首页 A"}), encoding="utf-8")
            creator_path = release_root / "payload/objects/creators/creator-a/profile.json"
            creator_path.parent.mkdir(parents=True)
            creator_path.write_text(json.dumps({
                "displayName": "创作者 A",
                "userHandle": "creator-a",
                "personaId": "persona-a",
                "avatarAsset": {"assetId": "avatar-a"},
            }), encoding="utf-8")
            tag_path = release_root / "payload/objects/tags/Topic/a/_definition.json"
            tag_path.parent.mkdir(parents=True)
            tag_path.write_text(json.dumps({"label": "标签 A"}), encoding="utf-8")
            manifest_digest = "sha256:" + "3" * 64
            attestation = {
                "schema": "quwoquan_data.release_attestation",
                "releaseId": release_id,
                "releaseClass": "commercial",
                "productLifecycleState": "commercial",
                "payloadSha256": manifest_digest,
            }
            attestation_path = release_root / "attestations/release.json"
            attestation_path.parent.mkdir(parents=True)
            attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
            candidate = {
                "releaseId": release_id,
                "releaseDigest": manifest_digest,
                "attestationRef": str(attestation_path),
                "attestationDigest": "sha256:" + hashlib.sha256(attestation_path.read_bytes()).hexdigest(),
            }
            homepage_report_path = root / "homepage.json"
            homepage_report_path.write_text(json.dumps({
                "entities": [{"entityRef": "entity-a", "homepageId": "homepage-a"}],
            }), encoding="utf-8")
            readiness = {
                "releaseId": release_id,
                "releaseClass": "commercial",
                "productLifecycleState": "commercial",
                "readinessPhase": "commercial",
                "verifyRunId": "verify-a",
                "manifestDigest": manifest_digest,
                "homepageApiVerificationRef": str(homepage_report_path),
                "postIds": ["article-a", "image-a", "video-a"],
                "feedQueries": [
                    {"name": "typed_article", "matchedPostIds": ["article-a"]},
                    {"name": "typed_image", "matchedPostIds": ["image-a"]},
                    {"name": "typed_video", "matchedPostIds": ["video-a"]},
                    {"name": "homepage_recommend", "matchedPostIds": ["article-a"]},
                    {"name": "premium_stream", "matchedPostIds": ["video-a"]},
                ],
            }
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            projected_plan = {
                "releaseId": release_id,
                "releaseUatSamplePlanRef": "uat/sample_plan.json",
                "releaseUatSamplePlanDigest": sample_digest,
                "videoPagination": {"pageSize": 20, "expectedWorkIds": ["video-a"]},
            }
            with (
                patch.object(
                    stackctl,
                    "_resolve_active_app_content_evidence",
                    return_value=(
                        {
                            "baselineId": "sha256:" + "4" * 64,
                            "sourceRevision": "revision-a",
                            "release": {"candidate": candidate},
                        },
                        readiness,
                        readiness_path,
                        "env/alpha/runs/release-lifecycle-exit/release-a/exit-a/lifecycle-exit.json",
                    ),
                ),
                patch.object(
                    stackctl,
                    "build_app_content_uat_plan",
                    return_value=projected_plan,
                ) as build_plan,
                patch(
                    "quwoquan_ops.cli.commands.app_preflight_evidence._payload_tree_digest",
                    return_value=manifest_digest,
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

            self.assertEqual(result["exitCode"], 0, result)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["releaseId"], release_id)
            self.assertNotIn("appUatEnvelope", result)
            self.assertNotIn("appUatEnvelopeDigest", result)
            self.assertEqual(result["releaseUatSamplePlan"], sample_plan)
            self.assertEqual(result["releaseUatSamplePlanDigest"], sample_digest)
            self.assertEqual(result["releaseHeader"], header)
            self.assertEqual(
                build_plan.call_args.kwargs["release_uat_sample_plan"],
                sample_plan,
            )
            self.assertEqual(
                build_plan.call_args.kwargs["release_payload_sha256"],
                manifest_digest,
            )

    def test_test_live_preflight_consumes_only_validated_plan_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "test-live-report"
            readiness_path = Path(temporary_directory) / "release-readiness.json"
            readiness = {
                "releaseId": "release-test-live-a",
                "readinessPhase": "consumer",
                "verifyRunId": "verify-test-live-a",
                "manifestDigest": "sha256:" + "3" * 64,
            }
            sample_plan_digest = "sha256:" + "8" * 64
            app_uat_plan = {
                "releaseIdentity": {"releaseId": "release-test-live-a"},
                "releaseUatSamplePlanRef": "uat/sample_plan.json",
                "releaseUatSamplePlanDigest": sample_plan_digest,
            }
            binding = {
                "releaseHeader": {},
                "releaseHeaderRef": "",
                "releaseHeaderDigest": "",
                "releaseUatSamplePlanRef": "uat/sample_plan.json",
                "releaseUatSamplePlanDigest": sample_plan_digest,
                "appUatPlan": app_uat_plan,
                "appUatPlanDigest": stackctl._canonical_document_checksum(app_uat_plan),
                "readinessReceiptDigest": "sha256:" + "4" * 64,
                "readinessReceiptRef": "env/alpha/release-readiness.json",
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
                ) as active_resolver,
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
            self.assertEqual(result["appUatPlan"], app_uat_plan)
            self.assertEqual(
                result["releaseUatSamplePlanDigest"], sample_plan_digest
            )
            self.assertNotIn("appUatEnvelope", result)
            self.assertNotIn("releaseHeader", result)
            self.assertNotIn("releaseUatSamplePlan", result)
            mutable_resolver.assert_called_once_with("alpha-local", binding)
            active_resolver.assert_not_called()
