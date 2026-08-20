"""environment patrol smoke：patrol 构建 workspace/wrapper 与设备恢复、播放证据契约。

由 1000 行硬顶拆分自 test_environment_patrol_smoke__local_contract_test.py；
测试逐字搬移，共享 helper 基类见
quwoquan_ops/tests/support/environment_patrol_smoke_test_support.py。
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke

# 入口拆为薄壳 + environment_patrol_smoke 子包后，mock.patch.object 必须打在
# 被测函数实际读取全局名的实现模块上，而不是入口 re-export 的绑定上。
from quwoquan_ops.cli.smoke.environment_patrol_smoke import (
    evidence as smoke_evidence,
    wrapper as smoke_wrapper,
)
from quwoquan_ops.cli import stackctl
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


class EnvironmentPatrolSmokeTest(EnvironmentPatrolSmokeCaseBase):
    def test_rollout_stage_parser_accepts_fixed_production_stages(self) -> None:
        for stage in ("canary", "5", "20", "50", "100"):
            with (
                self.subTest(stage=stage),
                mock.patch.object(
                    sys,
                    "argv",
                    ["run_environment_patrol_smoke.py", "--rollout-stage", stage],
                ),
            ):
                self.assertEqual(smoke.parse_args().rollout_stage, stage)

    def test_patrol_build_workspace_rejects_overlapping_runners(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            lock_path = Path(temporary_dir) / "patrol.lock"
            first = smoke._acquire_patrol_execution_lock(
                env_name="local-beta",
                target=smoke.DEFAULT_TARGET,
                lock_path=lock_path,
            )
            try:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Patrol build workspace is already in use",
                ):
                    smoke._acquire_patrol_execution_lock(
                        env_name="local-gamma",
                        target=smoke.DEFAULT_TARGET,
                        lock_path=lock_path,
                    )
            finally:
                first.close()
            replacement = smoke._acquire_patrol_execution_lock(
                env_name="local-gamma",
                target=smoke.DEFAULT_TARGET,
                lock_path=lock_path,
            )
            replacement.close()

    def test_patrol_bundler_target_has_valid_wrapper_alias_shape(
        self,
    ) -> None:
        wrapper_target = smoke._patrol_bundler_target(
            smoke.BASIC_VIABILITY_TARGET
        )
        self.assertRegex(
            wrapper_target,
            r"^test/patrol/"
            r"qwq_environment_smoke_[0-9a-f]{16}_test\.dart$",
        )
        self.assertNotIn("..", wrapper_target)

        args = self._args(target=smoke.BASIC_VIABILITY_TARGET)
        command = smoke.patrol_command(
            {
                "id": "android-gamma",
                "targetPlatform": "android-arm64",
                "emulator": True,
            },
            args,
            "patrol",
            dart_define_file=Path("/protected/session.json"),
        )

        self.assertEqual(
            command[command.index("-t") + 1],
            wrapper_target,
        )
        self.assertNotIn(str(smoke.APP_DIR), command[command.index("-t") + 1])

    def test_patrol_host_enumerates_every_canonical_uat_once(self) -> None:
        expected = tuple(
            path.relative_to(smoke.APP_DIR).as_posix()
            for path in sorted(
                (smoke.APP_DIR / "test/user_acceptance").rglob("*_test.dart")
            )
            if path.is_file()
        )

        enumerated = smoke._canonical_patrol_uat_targets()

        self.assertEqual(tuple(target for target, _ in enumerated), expected)
        wrapper_targets = tuple(wrapper for _, wrapper in enumerated)
        self.assertEqual(len(wrapper_targets), len(set(wrapper_targets)))
        self.assertTrue(
            all(
                wrapper.startswith("test/patrol/qwq_environment_smoke_")
                and wrapper.endswith("_test.dart")
                for wrapper in wrapper_targets
            )
        )

    def test_patrol_target_wrapper_forwards_main_and_is_removed_in_finally(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            app_dir = Path(temporary_dir) / "quwoquan_app"
            patrol_host_dir = app_dir / "test_host/patrol"
            wrapper_directory = patrol_host_dir / smoke.PATROL_TEST_DIRECTORY
            target_path = app_dir / smoke.BASIC_VIABILITY_TARGET
            wrapper_directory.mkdir(parents=True)
            target_path.parent.mkdir(parents=True)
            target_path.write_text("void main() {}\n", encoding="utf-8")
            bundle_path = wrapper_directory / "test_bundle.dart"
            bundle_preimage = b"// canonical tracked bundle\n"
            bundle_path.write_bytes(bundle_preimage)

            wrapper_path: Path | None = None
            cleanup = None
            with (
                mock.patch.object(smoke_wrapper, "APP_DIR", app_dir),
                mock.patch.object(
                    smoke_wrapper, "PATROL_HOST_DIR", patrol_host_dir
                ),
            ):
                try:
                    wrapper_path, wrapper_target, cleanup = (
                        smoke._create_patrol_target_wrapper(
                            smoke.BASIC_VIABILITY_TARGET
                        )
                    )
                    self.assertTrue(wrapper_path.is_file())
                    self.assertEqual(
                        wrapper_target,
                        wrapper_path.relative_to(patrol_host_dir).as_posix(),
                    )
                    self.assertRegex(
                        wrapper_path.stem,
                        r"^[A-Za-z_][A-Za-z0-9_]*$",
                    )
                    self.assertEqual(
                        wrapper_path.stat().st_mode & 0o777,
                        0o600,
                    )
                    self.assertEqual(
                        wrapper_path.read_text(encoding="utf-8"),
                        "// Ephemeral runner-owned Patrol wrapper; never commit this file.\n"
                        "import '../../../../test/user_acceptance/journeys/app_startup/"
                        "basic_viability__user_acceptance_test.dart' "
                        "as canonical_target;\n\n"
                        "void main() {\n"
                        "  canonical_target.main();\n"
                        "}\n",
                    )
                    bundle_path.write_bytes(b"// transient patrol bundle\n")
                    command = smoke.patrol_command(
                        {
                            "id": "android-gamma",
                            "targetPlatform": "android-arm64",
                            "emulator": True,
                        },
                        self._args(target=smoke.BASIC_VIABILITY_TARGET),
                        "patrol",
                        dart_define_file=Path("/protected/session.json"),
                        patrol_target=wrapper_target,
                    )
                    self.assertEqual(
                        command[command.index("-t") + 1], wrapper_target
                    )
                finally:
                    smoke._cleanup_patrol_target_wrapper(cleanup)

            assert wrapper_path is not None
            self.assertFalse(wrapper_path.exists())
            self.assertEqual(bundle_path.read_bytes(), bundle_preimage)

    def test_patrol_bundler_target_rejects_absolute_escape_or_noncanonical_test(
        self,
    ) -> None:
        invalid_targets = (
            str(smoke.APP_DIR / smoke.BASIC_VIABILITY_TARGET),
            "test/user_acceptance/patrol/../../local_contract/example_test.dart",
            "test/local_contract/example_test.dart",
            "test/user_acceptance/patrol/patrol_test_main.dart",
            "test/user_acceptance/journeys/missing_example_test.dart",
        )

        for target in invalid_targets:
            with self.subTest(target=target), self.assertRaises(ValueError):
                smoke._patrol_bundler_target(target)

    def test_default_target_is_the_video_playback_canary(self) -> None:
        self.assertEqual(
            smoke.DEFAULT_TARGET,
            (
                "test/user_acceptance/journeys/home_video_playback/"
                "video_playback_canary__user_acceptance_test.dart"
            ),
        )

    def test_runtime_recovery_evidence_is_exact_and_privacy_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            log_path = Path(temporary_dir) / "patrol.log"
            log_path.write_text(
                "QWQ_RUNTIME_RECOVERY_EVIDENCE "
                + json.dumps(
                    {
                        "authenticatedBefore": True,
                        "authenticatedAfter": True,
                        "sameOwner": True,
                        "samePersona": True,
                        "homeRestored": True,
                        "secondFaultNoReentry": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            evidence = smoke._read_runtime_recovery_evidence(log_path)
            self.assertTrue(all(evidence.values()))

            log_path.write_text(
                'QWQ_RUNTIME_RECOVERY_EVIDENCE {"sameOwner":true}\n',
                encoding="utf-8",
            )
            self.assertEqual(smoke._read_runtime_recovery_evidence(log_path), {})

    def test_controlled_edge_evidence_requires_copy_and_same_install_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            log_path = Path(temporary_dir) / "patrol.log"
            log_path.write_text(
                "QWQ_APP_CONTENT_FAULT_EVIDENCE "
                + json.dumps(
                    {
                        "environment": "gamma",
                        "copyKey": "connectionUnavailable",
                        "singlePrimaryAction": True,
                        "forbiddenBrandAbsent": True,
                        "technicalDetailsAbsent": True,
                        "blockedRetryCount": 5,
                        "blockingErrorRetained": True,
                        "sameInstallRecovery": True,
                        "recoveredVisibleCardCount": 2,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            evidence = smoke._read_controlled_edge_fault_evidence(log_path)
            self.assertEqual(evidence["copyKey"], "connectionUnavailable")
            self.assertEqual(evidence["recoveredVisibleCardCount"], 2)

            log_path.write_text(
                'QWQ_APP_CONTENT_FAULT_EVIDENCE '
                '{"environment":"gamma","copyKey":"reloadLater",'
                '"singlePrimaryAction":true,"forbiddenBrandAbsent":true,'
                '"technicalDetailsAbsent":true,"blockedRetryCount":5,'
                '"blockingErrorRetained":true,"sameInstallRecovery":true,'
                '"recoveredVisibleCardCount":2}\n',
                encoding="utf-8",
            )
            self.assertEqual(
                smoke._read_controlled_edge_fault_evidence(log_path),
                {},
            )

    def test_ios_device_evidence_command_is_exact_device_and_marker_scoped(
        self,
    ) -> None:
        command = smoke._ios_device_evidence_command(
            "SIMULATOR-EXACT-UDID",
            xcrun_path="/usr/bin/xcrun",
        )

        self.assertEqual(
            command[:5],
            [
                "/usr/bin/xcrun",
                "simctl",
                "spawn",
                "SIMULATOR-EXACT-UDID",
                "log",
            ],
        )
        predicate = command[command.index("--predicate") + 1]
        self.assertIn('process == "Runner"', predicate)
        for token in smoke.IOS_DEVICE_EVIDENCE_TOKENS:
            self.assertIn(f'eventMessage CONTAINS "{token}"', predicate)
        self.assertNotIn("--last", command)
        self.assertNotIn("log show", " ".join(command))

    def test_ios_device_evidence_stream_keeps_only_current_whitelisted_markers(
        self,
    ) -> None:
        observed: list[str] = []
        with tempfile.TemporaryDirectory() as temporary_dir:
            log_path = Path(temporary_dir) / "device-evidence.log"
            marker_line = smoke.FEED_CONTENT_EVIDENCE_PREFIX + json.dumps(
                {
                    "environment": "alpha",
                    "visibleCardCount": 1,
                    "visibleCardKeys": ["home-feed-card-0"],
                },
            )
            stream = smoke._IosDeviceEvidenceStream(
                device_id="SIMULATOR-EXACT-UDID",
                log_path=log_path,
                output_line_handler=observed.append,
                command=[
                    sys.executable,
                    "-u",
                    "-c",
                    (
                        "import time; "
                        "print('historical or unrelated line', flush=True); "
                        f"print({marker_line!r}, flush=True); time.sleep(5)"
                    ),
                ],
            )

            stream.start()
            for _ in range(20):
                if observed:
                    break
                time.sleep(0.05)
            receipt = stream.stop(grace_seconds=0)
            captured = log_path.read_text(encoding="utf-8")
            evidence = smoke._read_feed_content_evidence(log_path)

        self.assertEqual(receipt["status"], "captured")
        self.assertEqual(receipt["deviceId"], "SIMULATOR-EXACT-UDID")
        self.assertNotIn("historical or unrelated line", captured)
        self.assertIn(smoke.FEED_CONTENT_EVIDENCE_PREFIX, captured)
        self.assertEqual(len(observed), 1)
        self.assertEqual(evidence["visibleCardCount"], 1)

    def test_ios_device_evidence_stream_ignores_predicate_banner_before_page_marker(
        self,
    ) -> None:
        screenshot = mock.Mock(
            return_value={"status": "captured", "path": "after.png"}
        )
        capture = smoke_evidence._AppContentPageScreenshotCapture(
            args=self._args(target=smoke.FEED_LOAD_TARGET),
            runtime_env="alpha",
            capture=screenshot,
        )
        marker_line = (
            smoke_evidence.APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX
            + json.dumps(
                {
                    "environment": "alpha",
                    "suite": "homepage-feed",
                    "route": "/",
                    "terminalKey": "home-feed-card-0",
                }
            )
        )
        predicate_banner = (
            'Filtering the log data using "process == \\"Runner\\" AND '
            '(eventMessage CONTAINS \\"'
            + smoke_evidence.APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX
            + '\\")"'
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            log_path = Path(temporary_dir) / "device-evidence.log"
            stream = smoke._IosDeviceEvidenceStream(
                device_id="SIMULATOR-EXACT-UDID",
                log_path=log_path,
                output_line_handler=capture.handle_line,
                command=[
                    sys.executable,
                    "-u",
                    "-c",
                    (
                        "import time; "
                        f"print({predicate_banner!r}, flush=True); "
                        f"print({marker_line!r}, flush=True); time.sleep(5)"
                    ),
                ],
            )

            stream.start()
            for _ in range(20):
                if screenshot.called:
                    break
                time.sleep(0.05)
            receipt = stream.stop(grace_seconds=0)
            captured = log_path.read_text(encoding="utf-8")

        self.assertEqual(receipt["status"], "captured")
        screenshot.assert_called_once_with()
        self.assertEqual(capture.marker_count, 1)
        self.assertNotIn("Filtering the log data using", captured)
        self.assertIn(marker_line, captured)

    def test_ios_device_evidence_stream_keeps_real_invalid_page_marker_fail_closed(
        self,
    ) -> None:
        screenshot = mock.Mock(
            return_value={"status": "captured", "path": "after.png"}
        )
        capture = smoke_evidence._AppContentPageScreenshotCapture(
            args=self._args(target=smoke.FEED_LOAD_TARGET),
            runtime_env="alpha",
            capture=screenshot,
        )
        invalid_marker = (
            smoke_evidence.APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX
            + "not-json"
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            log_path = Path(temporary_dir) / "device-evidence.log"
            stream = smoke._IosDeviceEvidenceStream(
                device_id="SIMULATOR-EXACT-UDID",
                log_path=log_path,
                output_line_handler=capture.handle_line,
                command=[
                    sys.executable,
                    "-u",
                    "-c",
                    (
                        "import time; "
                        f"print({invalid_marker!r}, flush=True); time.sleep(5)"
                    ),
                ],
            )

            stream.start()
            for _ in range(20):
                if stream._handler_error is not None:
                    break
                time.sleep(0.05)
            with self.assertRaisesRegex(RuntimeError, "not valid JSON"):
                stream.stop(grace_seconds=0)

        screenshot.assert_not_called()

    def test_android_device_evidence_is_exact_device_and_current_run_scoped(
        self,
    ) -> None:
        stream_command, boundary_command = smoke._android_device_evidence_commands(
            "emulator-5556",
            "current-run-boundary",
            adb_path="/sdk/platform-tools/adb",
        )

        self.assertEqual(
            stream_command[:4],
            ["/sdk/platform-tools/adb", "-s", "emulator-5556", "logcat"],
        )
        self.assertEqual(
            stream_command[stream_command.index("-T") + 1],
            "1",
        )
        self.assertIn("flutter:I", stream_command)
        self.assertIn(
            f"{smoke.ANDROID_DEVICE_EVIDENCE_LOG_TAG}:I",
            stream_command,
        )
        self.assertEqual(boundary_command[2], "emulator-5556")
        self.assertEqual(boundary_command[-1], "current-run-boundary")

    def test_android_device_evidence_reemits_boundary_until_stream_observes_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            stream = smoke._AndroidDeviceEvidenceStream(
                device_id="emulator-5556",
                log_path=Path(temporary_dir) / "device-evidence.log",
                command=[
                    sys.executable,
                    "-u",
                    "-c",
                    "import time; time.sleep(5)",
                ],
                run_boundary="current-run-boundary",
                run_boundary_command=["emit-boundary"],
            )
            wait_count = 0

            def observe_on_second_emission(*, timeout: float) -> bool:
                nonlocal wait_count
                wait_count += 1
                if wait_count == 2:
                    stream._run_boundary_observed.set()
                    return True
                return False

            stream._run_boundary_observed.wait = mock.Mock(
                side_effect=observe_on_second_emission
            )
            with mock.patch.object(
                smoke_evidence.subprocess,
                "run",
                return_value=mock.Mock(returncode=0, stdout="", stderr=""),
            ) as boundary_run:
                stream.start()
                receipt = stream.stop(grace_seconds=0)

        self.assertEqual(boundary_run.call_count, 2)
        self.assertTrue(receipt["runBoundaryObserved"])

    def test_app_content_page_screenshot_marker_captures_once_during_patrol(
        self,
    ) -> None:
        cases = (
            (smoke.FEED_LOAD_TARGET, "homepage-feed", "/", "home-feed-card-0"),
            (
                smoke.CORE_READBACK_TARGET,
                "app-core-readback",
                "/",
                "works_immersive_pager",
            ),
            (
                smoke.MESSAGE_HOME_TARGET,
                "message-home",
                "/chat/conversation-a",
                "chat_input_text_field",
            ),
            (
                smoke.PROFILE_JOURNEY_TARGET,
                "profile-journey",
                "/user/creator-a",
                "profile-header-avatar",
            ),
        )
        for target, suite, route, terminal_key in cases:
            with self.subTest(suite=suite):
                screenshot = mock.Mock(
                    return_value={"status": "captured", "path": "after.png"}
                )
                capture = smoke_evidence._AppContentPageScreenshotCapture(
                    args=self._args(target=target),
                    runtime_env="alpha",
                    capture=screenshot,
                )
                marker = (
                    smoke_evidence.APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX
                    + json.dumps(
                        {
                            "environment": "alpha",
                            "suite": suite,
                            "route": route,
                            "terminalKey": terminal_key,
                        }
                    )
                )

                capture.handle_line(marker)

                screenshot.assert_called_once_with()
                self.assertTrue(capture.evidence["capturedDuringPatrol"])
                self.assertEqual(capture.evidence["marker"]["route"], route)
                with self.assertRaisesRegex(RuntimeError, "exactly once"):
                    capture.handle_line(marker)

    def test_app_content_page_screenshot_marker_identity_and_presence_fail_closed(
        self,
    ) -> None:
        args = self._args(target=smoke.FEED_LOAD_TARGET)
        screenshot = mock.Mock(
            return_value={"status": "captured", "path": "after.png"}
        )
        capture = smoke_evidence._AppContentPageScreenshotCapture(
            args=args,
            runtime_env="alpha",
            capture=screenshot,
        )
        result = {"exitCode": 0, "outputSummary": "passed"}
        capture.apply_success_gate(result, dry_run=False)
        self.assertEqual(result["exitCode"], 1)
        self.assertIn("in-run route/key screenshot", result["outputSummary"])

        canonical = {
            "environment": "alpha",
            "suite": "homepage-feed",
            "route": "/",
            "terminalKey": "home-feed-card-0",
        }
        invalid = (
            ("environment", "beta", "environment"),
            ("suite", "profile-journey", "suite"),
            ("route", "/chat/conversation-a", "route"),
            ("terminalKey", "profile-header-avatar", "terminalKey"),
        )
        for field, value, reason in invalid:
            with self.subTest(field=field):
                payload = {**canonical, field: value}
                isolated = smoke_evidence._AppContentPageScreenshotCapture(
                    args=args,
                    runtime_env="alpha",
                    capture=screenshot,
                )
                with self.assertRaisesRegex(RuntimeError, reason):
                    isolated.handle_line(
                        smoke_evidence.APP_CONTENT_PAGE_SCREENSHOT_READY_PREFIX
                        + json.dumps(payload)
                    )

    def test_android_device_log_marker_passes_and_missing_marker_fails_closed(
        self,
    ) -> None:
        old_marker = smoke.FEED_CONTENT_EVIDENCE_PREFIX + json.dumps(
            {
                "environment": "beta",
                "visibleCardCount": 1,
                "visibleCardKeys": ["home-feed-card-9"],
            }
        )
        current_marker = smoke.FEED_CONTENT_EVIDENCE_PREFIX + json.dumps(
            {
                "environment": "alpha",
                "visibleCardCount": 2,
                "visibleCardKeys": ["home-feed-card-0", "home-feed-card-1"],
            }
        )
        boundary = "current-android-patrol-run"
        with tempfile.TemporaryDirectory() as temporary_dir:
            run_dir = Path(temporary_dir)
            patrol_log = run_dir / "patrol.log"
            patrol_log.write_text(
                "instrumentation passed; historical stdout has no marker\n",
                encoding="utf-8",
            )
            device_log = run_dir / "device-evidence.log"
            stream = smoke._AndroidDeviceEvidenceStream(
                device_id="emulator-5556",
                log_path=device_log,
                command=[
                    sys.executable,
                    "-u",
                    "-c",
                    (
                        f"import time; print({old_marker!r}, flush=True); "
                        f"print({boundary!r}, flush=True); "
                        f"print({current_marker!r}, flush=True); time.sleep(5)"
                    ),
                ],
                run_boundary=boundary,
            )
            stream.start()
            for _ in range(20):
                if current_marker in device_log.read_text(encoding="utf-8"):
                    break
                time.sleep(0.05)
            receipt = stream.stop(grace_seconds=0)
            evidence_path = smoke._structured_evidence_log_path(
                {"id": "emulator-5556", "targetPlatform": "android-arm64"},
                run_dir,
            )
            evidence = smoke._read_feed_content_evidence(evidence_path)
            passed_result = {
                "exitCode": 0,
                "outputSummary": "instrumentation passed",
            }
            args = self._args(target=smoke.FEED_LOAD_TARGET)
            smoke._apply_feed_content_evidence_gate(
                passed_result,
                args,
                evidence,
            )

            device_log.write_text("current run has no marker\n", encoding="utf-8")
            failed_result = {
                "exitCode": 0,
                "outputSummary": "instrumentation passed",
            }
            smoke._apply_feed_content_evidence_gate(
                failed_result,
                args,
                smoke._read_feed_content_evidence(device_log),
            )

        self.assertTrue(receipt["runBoundaryObserved"])
        self.assertEqual(evidence["environment"], "alpha")
        self.assertEqual(evidence["visibleCardCount"], 2)
        self.assertEqual(passed_result["exitCode"], 0)
        self.assertEqual(failed_result["exitCode"], 1)
        self.assertIn("did not emit", failed_result["outputSummary"])

    def test_run_command_streams_restore_marker_before_process_exit(self) -> None:
        observed: list[str] = []
        with tempfile.TemporaryDirectory() as temporary_dir:
            result = smoke.run_command(
                [
                    sys.executable,
                    "-c",
                    "print('QWQ_APP_CONTENT_EDGE_RESTORE_REQUEST {}', flush=True)",
                ],
                cwd=Path(temporary_dir),
                timeout_seconds=5,
                output_line_handler=observed.append,
            )
        self.assertEqual(result["exitCode"], 0)
        self.assertEqual(len(observed), 1)
        self.assertIn("QWQ_APP_CONTENT_EDGE_RESTORE_REQUEST", observed[0])

    def test_runtime_recovery_requires_persisted_session_without_injected_identity(self) -> None:
        target = smoke.RUNTIME_RECOVERY_TARGET
        with self.assertRaisesRegex(
            ValueError,
            "requires --persisted-device-session",
        ):
            smoke._prepare_execution_session(
                self._args(
                    target=target,
                    test_auth_token="",
                    test_refresh_token="",
                    current_owner_id="",
                    current_persona_id="",
                )
            )

        args = self._args(
            target=target,
            persisted_device_session=True,
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_persona_id="",
        )
        self.assertEqual(
            smoke._prepare_execution_session(args),
            "persisted_device_session",
        )
        with self.assertRaisesRegex(ValueError, "forbids injected auth"):
            smoke._prepare_execution_session(
                self._args(
                    target=target,
                    persisted_device_session=True,
                )
            )

    def test_runtime_recovery_requires_dual_physical_device_matrix(self) -> None:
        args = self._args(
            target=smoke.RUNTIME_RECOVERY_TARGET,
            persisted_device_session=True,
        )
        with self.assertRaisesRegex(RuntimeError, "physical Android"):
            smoke._validate_runtime_recovery_device_matrix(
                args,
                [
                    {"targetPlatform": "android-arm64", "emulator": False},
                    {"targetPlatform": "ios", "emulator": True},
                ],
            )
        smoke._validate_runtime_recovery_device_matrix(
            args,
            [
                {"targetPlatform": "android-arm64", "emulator": False},
                {"targetPlatform": "ios", "emulator": False},
            ],
        )
        smoke._validate_runtime_recovery_device_matrix(
            self._args(
                target=smoke.RUNTIME_RECOVERY_TARGET,
                persisted_device_session=True,
                platform="android",
            ),
            [{"targetPlatform": "android-arm64", "emulator": False}],
        )
        smoke._validate_runtime_recovery_device_matrix(
            self._args(
                target=smoke.RUNTIME_RECOVERY_TARGET,
                persisted_device_session=True,
                platform="ios",
            ),
            [{"targetPlatform": "ios", "emulator": False}],
        )

    def test_native_video_evidence_only_accepts_patrol_log_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            patrol_log = Path(temporary_dir) / "patrol.log"
            patrol_log.write_text(
                "\n".join(
                    [
                        "controller ready",
                        (
                            "QWQ_VIDEO_PLAYBACK_EVIDENCE "
                            '{"nativeFirstFrame":true,"nativeSeekSettled":true}'
                        ),
                    ],
                ),
                encoding="utf-8",
            )

            evidence = smoke._read_video_playback_evidence(patrol_log)

        self.assertEqual(
            evidence,
            {"nativeFirstFrame": True, "nativeSeekSettled": True},
        )

    def test_alpha_playback_canary_uses_the_current_published_release(self) -> None:
        topology = stackctl.load_environment_topology()
        target = stackctl.get_target(topology, "alpha-local")
        canary = target["playbackCanary"]

        self.assertEqual(canary["source"], "published-release")
        self.assertEqual(canary["workIdEnv"], "VIDEO_PLAYBACK_CANARY_WORK_ID")
        self.assertEqual(
            canary["publicSliceKeyEnv"],
            "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY",
        )
        self.assertEqual(
            smoke._evidence_class_for_runtime("alpha"),
            "user_acceptance_remote",
        )
        self.assertEqual(
            smoke._evidence_class_for_runtime("beta"),
            "user_acceptance_remote",
        )

    def test_beta_playback_canary_uses_the_current_published_release(self) -> None:
        topology = stackctl.load_environment_topology()
        target = stackctl.get_target(topology, "beta-local")
        canary = target["playbackCanary"]

        self.assertEqual(canary["source"], "published-release")
        self.assertEqual(
            canary["workIdEnv"],
            "VIDEO_PLAYBACK_CANARY_WORK_ID",
        )
        self.assertEqual(
            canary["publicSliceKeyEnv"],
            "VIDEO_PLAYBACK_CANARY_PUBLIC_SLICE_KEY",
        )

    def test_remote_patrol_keeps_125s_video_contract_without_app_bundle(self) -> None:
        profile = ROOT / "quwoquan_data/reference/media_canary/video_playback.yaml"
        self.assertTrue(profile.is_file(), "mediaCanary.profileRef must resolve")
        profile_text = profile.read_text(encoding="utf-8")
        self.assertIn("media-canary-seek-125s", profile_text)
        self.assertIn("durationMs: 125000", profile_text)
        self.assertIn("publicSlicePrefix: media/video/s/media-canary-seek-125s/v1", profile_text)
        self.assertIn("media-canary-hour-boundary-3595s", profile_text)

        self.assertFalse(
            (
                ROOT
                / "quwoquan_app/test/user_acceptance/patrol/patrol_test_main.dart"
            ).exists()
        )
        harness = (
            ROOT
            / "quwoquan_app/test/support/runtime/patrol/"
            "patrol_environment_harness.dart"
        ).read_text(encoding="utf-8")
        self.assertNotIn("buildAlphaCloudOverrides", harness)
        self.assertNotIn("providerScopeOverrides", harness)
        self.assertIn("launchPatrolAppOnce($)", harness)


if __name__ == "__main__":
    unittest.main()
