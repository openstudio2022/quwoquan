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

    def test_debug_preflight_warns_for_runtime_content_and_provider_unavailability(
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
                    "load_startup_attempt",
                    return_value={
                        "status": "running",
                        "env": "alpha",
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
                    "verify_certificate",
                    return_value={"profile": "local-managed", "status": "ready"},
                ),
                patch.object(stackctl, "fetch_url", side_effect=fetch),
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
            self.assertEqual(mismatched["exitCode"], 0)
            self.assertEqual(mismatched["status"], "warning")
            self.assertIn("mismatch", " ".join(mismatched["warnings"]))

            with patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    "status": "stopped",
                    "env": "alpha",
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
                "verify_certificate",
                return_value={"profile": "local-managed", "status": "ready"},
            ), patch.object(stackctl, "fetch_url", side_effect=fetch), patch.object(
                stackctl,
                "command_app_content_preflight",
                return_value={"exitCode": 0},
            ):
                stopped = stackctl.command_app_debug_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir / "stopped"),
                    )
                )
            self.assertEqual(stopped["exitCode"], 0)
            self.assertEqual(stopped["status"], "warning")
            self.assertIn("not running", " ".join(stopped["warnings"]))

            with patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    "status": "running",
                    "env": "alpha",
                    "target": "alpha-local",
                    "workload": "full",
                    "configurationDigest": "sha256:" + "1" * 64,
                    "providerRuntimeDigest": provider_runtime_digest,
                },
            ), patch.object(
                stackctl,
                "_active_provider_runtime",
                side_effect=ValueError(
                    "alpha-local has no active immutable candidate"
                ),
            ), patch.object(
                stackctl,
                "verify_certificate",
                return_value={"profile": "local-managed", "status": "ready"},
            ), patch.object(stackctl, "fetch_url", side_effect=fetch), patch.object(
                stackctl,
                "command_app_content_preflight",
                return_value={"exitCode": 0},
            ):
                missing_candidate = stackctl.command_app_debug_preflight(
                    stackctl.argparse.Namespace(
                        target="alpha-local",
                        report_dir=str(report_dir / "missing-candidate"),
                    )
                )
            self.assertEqual(missing_candidate["exitCode"], 0)
            self.assertEqual(missing_candidate["status"], "warning")
            self.assertIn(
                "no active immutable candidate",
                " ".join(missing_candidate["warnings"]),
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
            attestation.write_text("{}\n", encoding="utf-8")
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

    def test_three_environment_uat_requires_one_baseline_and_runs_positive_and_fault_suites(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "uat"
            manifest_digest = "sha256:" + "5" * 64

            def preflight(args: object) -> dict[str, object]:
                target = str(getattr(args, "target"))
                environment = target.removesuffix("-local")
                return {
                    "exitCode": 0,
                    "target": target,
                    "environment": environment,
                    "packageBaseline": "sha256:" + "6" * 64,
                    "releaseId": "release-a",
                    "manifestDigest": manifest_digest,
                    "readinessReceiptRef": (
                        f".qwq_output/env/{environment}/runs/data-release/"
                        "release-a/verify-a/release-readiness.json"
                    ),
                    "appUatEnvelope": {
                        "releaseId": "release-a",
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
                    "_environment_page_smoke_profile_command",
                    side_effect=smoke_command,
                ),
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
            self.assertIn("no runtime evidence", result["details"][0])
            self.assertRegex(
                result["appUatEnvelopeDigest"],
                r"^sha256:[0-9a-f]{64}$",
            )
            self.assertEqual(len(result["runs"]), 15)
            self.assertEqual(run.call_count, 15)
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
            fault_calls = [
                call
                for call in patrol_calls
                if "app-content-controlled-edge-recovery"
                in " ".join(map(str, call.args[0]))
            ]
            self.assertEqual(len(fault_calls), 3)
            for call in fault_calls:
                self.assertIn("--stackctl-controlled-edge-fault", call.args[0])


if __name__ == "__main__":
    unittest.main()
