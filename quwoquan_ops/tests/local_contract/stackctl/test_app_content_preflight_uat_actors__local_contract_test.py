"""app content preflight: 三环境 UAT 绑定、actor 策略与 research 预检合约。

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

from quwoquan_ops.cli.commands import app_preflight_uat as uat
from quwoquan_ops.tests.support.app_content_preflight_test_support import (
    Path,
    json,
    patch,
    stackctl,
    subprocess,
    tempfile,
    unittest,
)


class AppContentPreflightUatActorsTest(unittest.TestCase):
    def test_patrol_screenshot_evidence_requires_an_in_run_page_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            screenshot = root / "after.png"
            screenshot.write_bytes(b"real-page-frame")
            report = root / "report.json"
            payload = {
                "status": "passed",
                "testedAppArtifactBinding": {
                    "status": "passed",
                    "bindings": [],
                    "comparisonProjections": [],
                },
                "externalProductionAutDriverArtifact": {
                    "status": "passed",
                    "marker": "native-driver-artifact",
                },
                "runs": [
                    {
                        "exitCode": 0,
                        "evidence": {
                            "afterScreenshot": {
                                "status": "captured",
                                "path": str(screenshot),
                            }
                        },
                    }
                ],
            }
            report.write_text(json.dumps(payload), encoding="utf-8")

            old_host_capture = stackctl._app_content_patrol_evidence(str(report))
            self.assertEqual(old_host_capture["screenshotDigest"], "")
            self.assertEqual(old_host_capture["screenshotMarker"], {})

            payload["runs"][0]["evidence"]["afterScreenshot"].update(
                {
                    "capturedDuringPatrol": True,
                    "marker": {
                        "environment": "alpha",
                        "suite": "homepage-feed",
                        "route": "/",
                        "terminalKey": "home-feed-card-0",
                    },
                }
            )
            report.write_text(json.dumps(payload), encoding="utf-8")
            live_capture = stackctl._app_content_patrol_evidence(str(report))

        self.assertRegex(live_capture["screenshotDigest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(live_capture["screenshotMarker"]["suite"], "homepage-feed")
        self.assertEqual(
            live_capture["testedAppArtifactBinding"]["status"],
            "passed",
        )
        self.assertEqual(
            live_capture["externalProductionAutDriverArtifact"]["marker"],
            "native-driver-artifact",
        )

    def test_patrol_evidence_preserves_first_failed_run_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = Path(temporary_directory) / "report.json"
            artifact_blocker = {
                "errorCode": "APP.UAT.page_artifact_binding_missing",
                "sourceOperationId": (
                    "environment_page_smoke.tested_app_artifact_binding"
                ),
                "httpStatus": None,
            }
            first_blocker = {
                "errorCode": "CONTENT.SYSTEM.required_dependency_unavailable",
                "sourceOperationId": "content.feed.read",
                "httpStatus": 503,
            }
            report.write_text(
                json.dumps(
                    {
                        "status": "gate_block",
                        "target": "test/example.dart",
                        "environmentAlias": "beta-local",
                        "platform": "android",
                        "testedAppArtifactBinding": {
                            "status": "gate_block",
                            "errorCode": artifact_blocker["errorCode"],
                            "bindings": [],
                            "comparisonProjections": [],
                        },
                        "runs": [
                            {
                                "exitCode": 2,
                                "device": {"id": "emulator-5556"},
                                "typedBlocker": {
                                    "errorCode": "APP.LAUNCH.compile_failed"
                                },
                                "artifactBindingBlocker": {},
                                "evidence": {
                                    "typedBlocker": first_blocker,
                                    "artifactBindingBlocker": artifact_blocker,
                                },
                            },
                            {
                                "exitCode": 0,
                                "device": {"id": "emulator-5558"},
                                "evidence": {
                                    "typedBlocker": {},
                                    "artifactBindingBlocker": {},
                                },
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            evidence = stackctl._app_content_patrol_evidence(str(report))

        self.assertEqual(evidence["typedBlocker"], first_blocker)
        self.assertEqual(evidence["artifactBindingBlocker"], artifact_blocker)
        self.assertEqual(evidence["deviceId"], "emulator-5556")
        self.assertEqual(evidence["patrolTarget"], "test/example.dart")
        self.assertEqual(evidence["environmentAlias"], "beta-local")
        self.assertEqual(evidence["platform"], "android")

    def test_patrol_evidence_projects_only_closed_child_receipt_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report = Path(temporary_directory) / "report.json"
            payload = {
                "status": "passed",
                "target": "test/example.dart",
                "environmentAlias": "alpha-local",
                "platform": "android",
                "runs": [
                    {
                        "exitCode": 0,
                        "firstBlocker": "APP.LAUNCH.runtime_config_activation_failed",
                        "device": {"id": "emulator-5554"},
                        "evidence": {},
                    }
                ],
            }
            report.write_text(json.dumps(payload), encoding="utf-8")
            evidence = stackctl._app_content_patrol_evidence(str(report))

            payload["runs"][0].pop("firstBlocker")
            payload["runs"][0]["errorCode"] = (
                "APP.LAUNCH.runtime_config_activation_failed"
            )
            report.write_text(json.dumps(payload), encoding="utf-8")
            error_evidence = stackctl._app_content_patrol_evidence(str(report))

            payload["runs"][0]["errorCode"] = "token=/private/secret-not-a-typed-code"
            report.write_text(json.dumps(payload), encoding="utf-8")
            invalid = stackctl._app_content_patrol_evidence(str(report))

        self.assertEqual(
            evidence["typedBlocker"],
            {
                "errorCode": "APP.LAUNCH.runtime_config_activation_failed",
                "sourceOperationId": "environment_page_smoke.child_receipt",
                "httpStatus": None,
            },
        )
        self.assertEqual(error_evidence["typedBlocker"], evidence["typedBlocker"])
        self.assertEqual(
            invalid["typedBlocker"]["errorCode"],
            "APP.LAUNCH.receipt_invalid",
        )
        self.assertNotIn("secret-not-a-typed-code", str(invalid))

    def test_research_preflight_uses_research_readiness_without_lifecycle_exit(
        self,
    ) -> None:
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
                captured["phase"] = vars(args)["phase"]
                captured["lifecycleExitRef"] = vars(args)["lifecycle_exit_ref"]
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

    def test_three_environment_uat_allows_target_baselines_on_one_release_train(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_dir = Path(temporary_directory) / "uat"
            manifest_digest = "sha256:" + "5" * 64
            release_train_id = "sha256:" + "e" * 64
            preflight_modes: list[tuple[str, str]] = []
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
                target = str(vars(args)["target"])
                environment = target.removesuffix("-local")
                ordinal = {"alpha": "a", "beta": "b", "gamma": "c"}[environment]
                preflight_modes.append(
                    (
                        str(vars(args)["purpose"]),
                        str(vars(args)["runtime_mode"]),
                    )
                )
                return {
                    "exitCode": 0,
                    "target": target,
                    "environment": environment,
                    "purpose": "content_live",
                    "launchPolicy": "immutable_candidate",
                    "nonPromotable": False,
                    "status": "passed",
                    "contentLive": "passed",
                    "contentBindingState": "bound",
                    "packageBaseline": "sha256:" + ordinal * 64,
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
                    "appUatPlanDigest": stackctl._canonical_document_checksum(uat_plan),
                }

            def runtime_binding(result: object) -> dict[str, object]:
                self.assertIsInstance(result, dict)
                result = result if isinstance(result, dict) else {}
                target = str(result["target"])
                environment = target.removesuffix("-local")
                baseline = str(result["packageBaseline"])
                return {
                    "launchPolicy": "immutable_candidate",
                    "nonPromotable": False,
                    "retentionClass": "immutable_candidate",
                    "contentBindingState": "bound",
                    "environment": environment,
                    "target": target,
                    "packageBaseline": baseline,
                    "candidateDigest": baseline,
                    "releaseTrainId": release_train_id,
                    "startupAttemptId": f"{environment}-candidate-attempt",
                    "composeProject": f"quwoquan_{environment}_release",
                    "startupIdentity": {
                        "candidateDigest": baseline,
                        "configurationDigest": result["configurationDigest"],
                    },
                    "releaseId": "release-a",
                    "verifyRunId": "verify-a",
                    "manifestDigest": manifest_digest,
                    "readinessPhase": "research",
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

            def execute(
                argv: list[str], **_kwargs: object
            ) -> subprocess.CompletedProcess[str]:
                if "verify_ios_hot_restart.py" in " ".join(map(str, argv)):
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        json.dumps(
                            {
                                "status": "passed",
                                "launchProvenance": "workspace_flutter_run",
                                "runtimeConfigSupplyMode": ("external_runtime_package"),
                                "consumerLeaseId": "sha256:" + "7" * 64,
                                "reportPath": "reports/workspace-flutter-run.json",
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
                    "_app_content_test_live_runtime_binding",
                    side_effect=runtime_binding,
                ),
                patch.object(
                    uat,
                    "_app_content_readiness_path",
                    side_effect=lambda item: Path(str(item["readinessReceiptRef"])),
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
            self.assertEqual(result["launchPolicy"], "immutable_candidate")
            self.assertTrue(result["nonPromotable"])
            self.assertNotIn("packageBaseline", result)
            self.assertEqual(
                result["packageBaselines"],
                {
                    "alpha-local": "sha256:" + "a" * 64,
                    "beta-local": "sha256:" + "b" * 64,
                    "gamma-local": "sha256:" + "c" * 64,
                },
            )
            self.assertEqual(result["releaseTrainId"], release_train_id)
            self.assertEqual(
                preflight_modes,
                [("content_live", "immutable_candidate")] * 3,
            )
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
            # 三个 target 均执行 6 个页面 P0 suite；每环境另有 release
            # probe + workspace Flutter run。
            self.assertEqual(len(result["runs"]), 24)
            self.assertEqual(run.call_count, 21)
            self.assertEqual(result["appUatPlan"], uat_plan)
            direct_calls = [
                call
                for call in run.call_args_list
                if "verify_ios_hot_restart.py" in " ".join(map(str, call.args[0]))
            ]
            self.assertEqual(len(direct_calls), 3)
            for call in direct_calls:
                direct_argv = call.args[0]
                self.assertEqual(
                    (call.kwargs.get("env") or {}).get("QWQ_OUTPUT_ROOT"),
                    str(stackctl.output_root().expanduser().resolve()),
                )
                self.assertIn("workspace_flutter_run", direct_argv)
                self.assertIn("--preflight-only", direct_argv)
                timeout_argument = direct_argv.index("--ready-timeout-seconds")
                self.assertEqual(
                    direct_argv[timeout_argument + 1],
                    "900",
                )
                cold_native_argument = direct_argv.index(
                    "--max-cold-native-safe-terminal-ms"
                )
                self.assertEqual(
                    direct_argv[cold_native_argument + 1],
                    "12000",
                )
            workspace_runs = [
                item
                for item in result["runs"]
                if item["suite"] == "workspace-flutter-run"
            ]
            self.assertEqual(len(workspace_runs), 3)
            for item in workspace_runs:
                self.assertEqual(
                    item["launchProvenance"],
                    "workspace_flutter_run",
                )
                self.assertEqual(
                    item["runtimeConfigSupplyMode"],
                    "external_runtime_package",
                )
            patrol_calls = [
                call for call in run.call_args_list if call not in direct_calls
            ]
            for call in patrol_calls:
                self.assertIn("--platform", call.args[0])
                self.assertIn("ios", call.args[0])
                self.assertIn("--dry-run", call.args[0])
                environment = call.kwargs.get("env") or {}
                is_profile = "app-content-profile-journey" in " ".join(
                    map(str, call.args[0])
                )
                self.assertEqual(
                    environment.get("QWQ_APP_CONTENT_PROFILE_P0_ONLY"),
                    "true" if is_profile else None,
                )
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
                self.assertEqual(
                    (call.kwargs.get("env") or {}).get(
                        "QWQ_APP_CONTENT_VIDEO_PAGE_COUNT"
                    ),
                    "20",
                )
            profile_journey_calls = [
                call
                for call in smoke_profile.call_args_list
                if call.kwargs.get("suite_name") == "app-content-profile-journey"
            ]
            self.assertEqual(len(profile_journey_calls), 3)
            for call in profile_journey_calls:
                self.assertEqual(
                    call.kwargs.get("patrol_target"),
                    stackctl.PROFILE_JOURNEY_UAT_TEST_TARGET,
                )
            message_calls = [
                call
                for call in smoke_profile.call_args_list
                if call.kwargs.get("suite_name") == "app-content-message-home"
            ]
            self.assertEqual(len(message_calls), 3)
            for call in message_calls:
                self.assertEqual(
                    call.kwargs.get("patrol_target"),
                    stackctl.MESSAGE_HOME_UAT_TEST_TARGET,
                )
            planned_messages = [
                item for item in result["runs"] if item.get("suite") == "message-home"
            ]
            self.assertEqual(len(planned_messages), 3)
            self.assertTrue(
                all(item.get("typedTestDataConversation") for item in planned_messages)
            )
            self.assertTrue(
                all(
                    (item.get("testDataScope") or {}).get("status") == "planned"
                    for item in planned_messages
                )
            )
            home_video_calls = [
                call
                for call in smoke_profile.call_args_list
                if call.kwargs.get("suite_name") == "app-content-home-video-playback"
            ]
            self.assertEqual(len(home_video_calls), 3)
            for call in home_video_calls:
                self.assertEqual(
                    call.kwargs.get("patrol_target"),
                    stackctl.HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
                )
                self.assertIsNotNone(call.kwargs.get("data_readiness_path"))
            executed_home_video_calls = [
                call
                for call in patrol_calls
                if "app-content-home-video-playback" in " ".join(map(str, call.args[0]))
            ]
            self.assertEqual(len(executed_home_video_calls), 3)
            for call in executed_home_video_calls:
                self.assertIn("--data-release-id", call.args[0])
                self.assertIn("release-a", call.args[0])
            planned_suite_names = [
                str(call.kwargs.get("suite_name") or "")
                for call in smoke_profile.call_args_list
            ]
            home_video_positions = [
                index
                for index, suite_name in enumerate(planned_suite_names)
                if suite_name == "app-content-home-video-playback"
            ]
            app_core_positions = [
                index
                for index, suite_name in enumerate(planned_suite_names)
                if suite_name == "app-content-app-core-readback"
            ]
            self.assertEqual(len(home_video_positions), len(app_core_positions))
            self.assertTrue(
                all(
                    home_video < app_core
                    for home_video, app_core in zip(
                        home_video_positions,
                        app_core_positions,
                        strict=True,
                    )
                ),
                "video progress evidence must run before a video-book content gap",
            )
            video_canary_calls = [
                call
                for call in smoke_profile.call_args_list
                if str(call.kwargs.get("suite_name", "")).startswith(
                    "app-content-video-playback-"
                )
            ]
            self.assertEqual(video_canary_calls, [])
            planned_search = [
                item
                for item in result["runs"]
                if item.get("suite") == "release-bound-search-and-video-page"
            ]
            self.assertEqual(len(planned_search), 3)
            self.assertTrue(
                all(
                    item.get("searchCanaries") == uat_plan["searchCanaries"]
                    for item in planned_search
                )
            )
            fault_calls = [
                call
                for call in patrol_calls
                if "app-content-controlled-edge-recovery"
                in " ".join(map(str, call.args[0]))
            ]
            self.assertEqual(len(fault_calls), 3)
            for fault_call in fault_calls:
                self.assertIn(
                    "--stackctl-controlled-edge-fault",
                    fault_call.args[0],
                )
            fault_profile_calls = [
                call
                for call in smoke_profile.call_args_list
                if call.kwargs.get("suite_name")
                == "app-content-controlled-edge-recovery"
            ]
            self.assertEqual(len(fault_profile_calls), 3)
            self.assertEqual(
                {(call.args[0], call.args[1]) for call in fault_profile_calls},
                {
                    ("alpha", "alpha-local"),
                    ("beta", "beta-local"),
                    ("gamma", "gamma-local"),
                },
            )
            self.assertTrue(
                all(
                    call.kwargs.get("patrol_target")
                    == stackctl.CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET
                    for call in fault_profile_calls
                )
            )
            self.assertEqual(
                {
                    str(call.kwargs.get("suite_name") or "")
                    for call in smoke_profile.call_args_list
                },
                {
                    "app-content-homepage-feed",
                    "app-content-profile-journey",
                    "app-content-message-home",
                    "app-content-home-video-playback",
                    "app-content-app-core-readback",
                    "app-content-controlled-edge-recovery",
                },
            )
