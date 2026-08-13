"""app content preflight: 三环境 UAT 绑定、actor 策略与 research 预检合约。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""
from __future__ import annotations

from quwoquan_ops.tests.support.app_content_preflight_test_support import (
    AUTHENTICATED_ACTORS,
    Path,
    canonical_digest,
    json,
    patch,
    stackctl,
    subprocess,
    tempfile,
    unittest,
)


class AppContentPreflightUatActorsTest(unittest.TestCase):
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
                "sourceRevision": "a" * 40,
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
            readiness = {
                "passed": True,
                "environment": "alpha",
                "releaseId": "release-a",
                "verifyRunId": "verify-a",
                "manifestDigest": manifest_digest,
                "readinessPhase": "research",
                "releaseClass": "research",
                "productLifecycleState": "research",
                "importRunId": "import-a",
                "sourceRevision": "a" * 40,
                "postIds": ["post-a"],
                "creatorIds": ["creator-a"],
                "entityRefs": ["entity-a"],
                "tagRefs": ["tag-a"],
                "mediaAssetIds": ["media-a"],
            }
            readiness["verificationChecksum"] = canonical_digest(readiness)
            readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
            context = stackctl._app_content_test_live_actor_context(
                preflight=preflight,
                runtime_binding=runtime_binding,
                readiness_path=readiness_path,
                report_dir=root / "uat",
            )

        self.assertEqual(context.candidate.baseline_id, "sha256:" + "1" * 64)
        self.assertEqual(context.candidate.package_digest, "sha256:" + "2" * 64)
        self.assertEqual(
            tuple(item.object_id for item in context.candidate.release_posts),
            ("post-a",),
        )
        self.assertEqual(
            context.provider_evidence[
                AUTHENTICATED_ACTORS.required_provider_capabilities[0].value
            ][
                "candidateBindingDigest"
            ],
            context.candidate.digest,
        )

