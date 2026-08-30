"""environment patrol smoke：typed actor 会话、凭据红线与 release-bound UAT 状态契约。

由 1000 行硬顶拆分自 test_environment_patrol_smoke__local_contract_test.py；
测试逐字搬移，共享 helper 基类见
quwoquan_ops/tests/support/environment_patrol_smoke_test_support.py。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke

# 入口拆为薄壳 + environment_patrol_smoke 子包后，mock.patch.object 必须打在
# 被测函数实际读取全局名的实现模块上，而不是入口 re-export 的绑定上。
from quwoquan_ops.cli.smoke.environment_patrol_smoke import (
    entry as smoke_entry,
    handoff as smoke_handoff,
    wrapper as smoke_wrapper,
)
from quwoquan_ops.tests.support.environment_patrol_smoke_test_support import (
    EnvironmentPatrolSmokeCaseBase,
)


class EnvironmentPatrolSmokeTest(EnvironmentPatrolSmokeCaseBase):
    def test_typed_core_uat_requires_control_plane_actor_and_forbids_anonymous(
        self,
    ) -> None:
        args = self._args(
            target=smoke.BASIC_VIABILITY_TARGET,
            video_playback_canary_work_id="",
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_persona_id="",
        )
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_TEST_DATA_ACCESS_TOKEN": "typed-access",
                "QWQ_TEST_DATA_REFRESH_TOKEN": "typed-refresh",
                "QWQ_TEST_DATA_OWNER_ID": "typed-owner",
                "QWQ_TEST_DATA_PERSONA_ID": "typed-persona",
            },
            clear=False,
        ):
            source = smoke._prepare_execution_session(args)

        self.assertEqual(source, "test_data_protected_authenticated_session")
        self.assertEqual(smoke._missing_required_args(args), [])
        self.assertFalse(smoke._requires_video_playback_canary(args))
        self.assertFalse(smoke._uses_runtime_anonymous_session(args))
        command = smoke.patrol_command(
            {
                "id": "sim-1",
                "targetPlatform": "ios",
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "emulator": True,
            },
            args,
            "patrol",
            dart_define_file=None,
            typed_test_data_session_handoff=True,
        )
        self.assertNotIn("--dart-define-from-file=", "\n".join(command))
        self.assertNotIn("runtime_anonymous_session", "\n".join(command))

    def test_alpha_app_content_targets_use_typed_session_handoff(self) -> None:
        targets = (
            *smoke.TYPED_AUTHENTICATED_SESSION_TARGETS,
            *smoke.ALPHA_APP_CONTENT_TYPED_SESSION_TARGETS,
        )
        for target in targets:
            with self.subTest(target=target):
                args = self._args(
                    env_name="alpha-local",
                    runtime_env="alpha",
                    api_contract_env="alpha",
                    target=target,
                    test_auth_token="",
                    test_refresh_token="",
                    current_owner_id="",
                    current_persona_id="",
                )
                with mock.patch.dict(
                    os.environ,
                    {
                        "QWQ_TEST_DATA_ACCESS_TOKEN": "typed-access",
                        "QWQ_TEST_DATA_REFRESH_TOKEN": "typed-refresh",
                        "QWQ_TEST_DATA_OWNER_ID": "typed-owner",
                        "QWQ_TEST_DATA_PERSONA_ID": "typed-persona",
                    },
                    clear=False,
                ):
                    source = smoke._prepare_execution_session(args)

                self.assertEqual(
                    source,
                    "test_data_protected_authenticated_session",
                )
                self.assertEqual(smoke._missing_required_args(args), [])
                self.assertFalse(smoke._uses_runtime_anonymous_session(args))
                self.assertFalse(
                    smoke._uses_public_video_canary_anonymous_session(args)
                )
                if target == smoke.CORE_READBACK_TARGET:
                    for destination, _ in smoke.RELEASE_APP_UAT_DEFINES:
                        setattr(args, destination, "canonical-release-value")
                elif target == smoke.HOME_VIDEO_PLAYBACK_TARGET:
                    args.data_release_id = "canonical-release-value"
                with mock.patch.dict(
                    os.environ,
                    {smoke.APP_CONTENT_VIDEO_PAGE_COUNT_ENV: "1"},
                    clear=False,
                ):
                    command = smoke.patrol_command(
                        {
                            "id": "sim-1",
                            "targetPlatform": "ios",
                            "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                            "emulator": True,
                        },
                        args,
                        "patrol",
                        dart_define_file=None,
                        typed_test_data_session_handoff=True,
                    )
                joined = "\n".join(command)
                self.assertNotIn("--dart-define-from-file=", joined)
                self.assertNotIn("runtime_anonymous_session", joined)

    def test_beta_gamma_app_content_guest_targets_remain_anonymous(self) -> None:
        guest_targets = (
            (smoke.FEED_LOAD_TARGET, "runtime_anonymous_session"),
            (smoke.DEFAULT_TARGET, "anonymous_public_video_session"),
            (smoke.CONTROLLED_EDGE_FAULT_TARGET, "runtime_anonymous_session"),
        )
        for environment in ("beta", "gamma"):
            for target, expected_source in guest_targets:
                with self.subTest(environment=environment, target=target):
                    args = self._args(
                        env_name=f"{environment}-local",
                        runtime_env=environment,
                        api_contract_env=environment,
                        target=target,
                        test_auth_token="",
                        test_refresh_token="",
                        current_owner_id="",
                        current_persona_id="",
                    )
                    with mock.patch.object(
                        smoke_handoff,
                        "load_test_live_startup_attempt",
                    ) as load_receipt:
                        source = smoke._prepare_execution_session(args)

                    load_receipt.assert_not_called()
                    self.assertEqual(source, expected_source)
                    self.assertEqual(smoke._missing_required_args(args), [])

    def test_beta_gamma_core_readback_remains_protected(self) -> None:
        for environment in ("beta", "gamma"):
            for target in (
                smoke.CORE_READBACK_TARGET,
                smoke.PROFILE_JOURNEY_TARGET,
            ):
                with self.subTest(environment=environment, target=target):
                    args = self._args(
                        env_name=f"{environment}-local",
                        runtime_env=environment,
                        api_contract_env=environment,
                        target=target,
                        test_auth_token="",
                        test_refresh_token="",
                        current_owner_id="",
                        current_persona_id="",
                    )
                    with mock.patch.dict(
                        os.environ,
                        {
                            "QWQ_TEST_DATA_ACCESS_TOKEN": "typed-access",
                            "QWQ_TEST_DATA_REFRESH_TOKEN": "typed-refresh",
                            "QWQ_TEST_DATA_OWNER_ID": "typed-owner",
                            "QWQ_TEST_DATA_PERSONA_ID": "typed-persona",
                        },
                        clear=False,
                    ):
                        source = smoke._prepare_execution_session(args)

                    self.assertEqual(
                        source,
                        "test_data_protected_authenticated_session",
                    )
                    self.assertEqual(smoke._missing_required_args(args), [])

    def test_profile_uat_actor_handoff_stays_out_of_command_and_report(
        self,
    ) -> None:
        actor_environment = {
            "QWQ_TEST_DATA_ACCESS_TOKEN": "profile-access-secret",
            "QWQ_TEST_DATA_REFRESH_TOKEN": "profile-refresh-secret",
            "QWQ_TEST_DATA_OWNER_ID": "profile-owner-secret",
            "QWQ_TEST_DATA_PERSONA_ID": "profile-persona-secret",
        }
        args = self._args(
            env_name="alpha-local",
            runtime_env="alpha",
            api_contract_env="alpha",
            target=smoke.PROFILE_JOURNEY_TARGET,
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_persona_id="",
        )
        with mock.patch.dict(os.environ, actor_environment, clear=False):
            source = smoke._prepare_execution_session(args)

        self.assertEqual(source, "test_data_protected_authenticated_session")
        self.assertEqual(smoke._missing_required_args(args), [])
        actor = args._typed_test_data_actor
        command = smoke.patrol_command(
            {
                "id": "sim-1",
                "targetPlatform": "ios",
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "emulator": True,
            },
            args,
            "patrol",
            dart_define_file=None,
            typed_test_data_session_handoff=True,
        )
        command_report = json.dumps(smoke._redact_command(command))
        output_report = smoke._redact_text(
            " ".join(actor.secret_values()),
            actor.secret_values(),
        )

        self.assertNotIn("--test-auth-token", command_report)
        self.assertNotIn("--dart-define-from-file=", command_report)
        self.assertNotIn("APP_CONTENT_PROFILE_P0_ONLY", command_report)
        for secret in actor.secret_values():
            self.assertNotIn(secret, command_report)
            self.assertNotIn(secret, output_report)
        self.assertEqual(output_report, "<redacted> <redacted> <redacted> <redacted>")

    def test_app_content_profile_p0_define_is_exact_target_only(self) -> None:
        device = {
            "id": "sim-1",
            "targetPlatform": "ios",
            "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
            "emulator": True,
        }
        args = self._args(
            env_name="gamma-local",
            runtime_env="gamma",
            api_contract_env="gamma",
            target=smoke.PROFILE_JOURNEY_TARGET,
        )
        with mock.patch.dict(os.environ, {}, clear=True):
            gamma_p1_command = smoke.patrol_command(
                device,
                args,
                "patrol",
                dart_define_file=None,
                typed_test_data_session_handoff=True,
            )
        self.assertNotIn(
            "--dart-define=APP_CONTENT_PROFILE_P0_ONLY=true",
            gamma_p1_command,
        )

        with mock.patch.dict(
            os.environ,
            {"QWQ_APP_CONTENT_PROFILE_P0_ONLY": "true"},
            clear=False,
        ):
            command = smoke.patrol_command(
                device,
                args,
                "patrol",
                dart_define_file=None,
                typed_test_data_session_handoff=True,
            )
        self.assertIn("--dart-define=APP_CONTENT_PROFILE_P0_ONLY=true", command)

        args.target = smoke.CORE_READBACK_TARGET
        with mock.patch.dict(
            os.environ,
            {"QWQ_APP_CONTENT_PROFILE_P0_ONLY": "true"},
            clear=False,
        ), self.assertRaisesRegex(
            ValueError,
            "only valid for the profile journey",
        ):
            smoke.patrol_command(
                device,
                args,
                "patrol",
                dart_define_file=None,
                typed_test_data_session_handoff=True,
            )

        args.target = smoke.PROFILE_JOURNEY_TARGET
        with mock.patch.dict(
            os.environ,
            {"QWQ_APP_CONTENT_PROFILE_P0_ONLY": "false"},
            clear=False,
        ), self.assertRaisesRegex(ValueError, "must equal true"):
            smoke.patrol_command(
                device,
                args,
                "patrol",
                dart_define_file=None,
                typed_test_data_session_handoff=True,
            )

    def test_typed_core_uat_rejects_missing_or_incomplete_actor_handoff(self) -> None:
        def args() -> argparse.Namespace:
            return self._args(
                target=smoke.CORE_READBACK_TARGET,
                test_auth_token="",
                test_refresh_token="",
                current_owner_id="",
                current_persona_id="",
            )

        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
            ValueError,
            "TestDataSession actor handoff",
        ):
            smoke._prepare_execution_session(args())
        with mock.patch.dict(
            os.environ,
            {"QWQ_TEST_DATA_ACCESS_TOKEN": "typed-access"},
            clear=True,
        ), self.assertRaisesRegex(ValueError, "actor handoff is incomplete"):
            smoke._prepare_execution_session(args())

    def test_typed_core_uat_rejects_caller_injected_credentials(self) -> None:
        args = self._args(target=smoke.CORE_READBACK_TARGET)
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_TEST_DATA_ACCESS_TOKEN": "typed-access",
                "QWQ_TEST_DATA_REFRESH_TOKEN": "typed-refresh",
                "QWQ_TEST_DATA_OWNER_ID": "typed-owner",
                "QWQ_TEST_DATA_PERSONA_ID": "typed-persona",
            },
            clear=False,
        ), self.assertRaisesRegex(ValueError, "forbids caller-injected"):
            smoke._prepare_execution_session(args)

    def test_typed_runtime_wrapper_keeps_actor_session_out_of_argv(
        self,
    ) -> None:
        args = self._args(
            target=smoke.MESSAGE_HOME_TARGET,
            test_auth_token="",
            test_refresh_token="",
            current_owner_id="",
            current_persona_id="",
        )
        actor = smoke.TypedTestDataActor(
            access_token="typed-access",
            refresh_token="typed-refresh",
            owner_id="typed-owner",
            persona_id="typed-persona",
        )
        conversation = smoke.TypedTestDataConversation(
            conversation_id="typed-conversation",
            message_ids=("typed-message-a", "typed-message-b"),
        )

        with tempfile.TemporaryDirectory() as temporary_dir:
            app_dir = Path(temporary_dir) / "quwoquan_app"
            patrol_host_dir = app_dir / "test_host/patrol"
            wrapper_directory = patrol_host_dir / smoke.PATROL_TEST_DIRECTORY
            target_path = app_dir / smoke.MESSAGE_HOME_TARGET
            wrapper_directory.mkdir(parents=True)
            target_path.parent.mkdir(parents=True)
            target_path.write_text("void main() {}\n", encoding="utf-8")
            (wrapper_directory / "test_bundle.dart").write_text(
                "// canonical tracked bundle\n",
                encoding="utf-8",
            )
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
                            smoke.MESSAGE_HOME_TARGET,
                            typed_actor=actor,
                            typed_conversation=conversation,
                        )
                    )
                    source = wrapper_path.read_text(encoding="utf-8")
                    command = smoke.patrol_command(
                        {
                            "id": "sim-1",
                            "targetPlatform": "ios",
                            "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                            "emulator": True,
                        },
                        args,
                        "patrol",
                        dart_define_file=None,
                        patrol_target=wrapper_target,
                        typed_test_data_session_handoff=True,
                    )
                    joined = "\n".join(command)
                    for secret in (
                        "typed-access",
                        "typed-refresh",
                        "typed-owner",
                        "typed-persona",
                        "typed-conversation",
                        "typed-message-a",
                        "typed-message-b",
                    ):
                        self.assertNotIn(secret, joined)
                        self.assertNotIn(secret, source)
                        self.assertNotIn(
                            base64.b64encode(secret.encode("utf-8")).decode(
                                "ascii"
                            ),
                            joined,
                        )
                    self.assertNotIn("--dart-define-from-file=", joined)
                    self.assertIn(
                        "installPatrolAcceptanceSessionForRunner",
                        source,
                    )
                    self.assertIn(
                        "installPatrolTestDataConversationForRunner",
                        source,
                    )
                    self.assertTrue(
                        tuple(
                            wrapper_directory.glob(
                                "qwq_typed_test_data_conversation_*.dart"
                            )
                        )
                    )
                finally:
                    smoke._cleanup_patrol_target_wrapper(cleanup)
            self.assertFalse(wrapper_path.exists())
            self.assertFalse(
                tuple(
                    wrapper_directory.glob(
                        "qwq_typed_test_data_conversation_*.dart"
                    )
                )
            )

    def test_message_target_requires_complete_typed_conversation_handoff(self) -> None:
        args = self._args(target=smoke.MESSAGE_HOME_TARGET)
        self.assertTrue(smoke._requires_typed_test_data_conversation(args))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(
                smoke._typed_test_data_conversation_from_environment()
            )
        with mock.patch.dict(
            os.environ,
            {"QWQ_TEST_DATA_CONVERSATION_ID": "conversation-a"},
            clear=True,
        ), self.assertRaisesRegex(ValueError, "handoff is incomplete"):
            smoke._typed_test_data_conversation_from_environment()
        with mock.patch.dict(
            os.environ,
            {
                "QWQ_TEST_DATA_CONVERSATION_ID": "conversation-a",
                "QWQ_TEST_DATA_MESSAGE_IDS_JSON": '["message-a","message-b"]',
            },
            clear=True,
        ):
            handoff = smoke._typed_test_data_conversation_from_environment()
        self.assertEqual(handoff.conversation_id, "conversation-a")
        self.assertEqual(handoff.message_ids, ("message-a", "message-b"))

    def test_typed_conversation_wrapper_and_dart_consumer_are_isomorphic(self) -> None:
        wrapper_source = Path(smoke_wrapper.__file__).read_text(encoding="utf-8")
        support_source = (
            ROOT
            / "quwoquan_app/test/support/runtime/patrol_acceptance_session.dart"
        ).read_text(encoding="utf-8")
        target_source = (
            ROOT / "quwoquan_app" / smoke.MESSAGE_HOME_TARGET
        ).read_text(
            encoding="utf-8"
        )

        method = "installPatrolTestDataConversationForRunner"
        self.assertIn(method, wrapper_source)
        self.assertIn(method, support_source)
        for field, dart_type in (
            ("conversationId", "String"),
            ("initialMessageIds", "List<String>"),
        ):
            self.assertIn(f"{field}:", wrapper_source)
            self.assertIn(f"required {dart_type} {field}", support_source)
        self.assertLess(
            wrapper_source.index("installPatrolAcceptanceSessionForRunner"),
            wrapper_source.index(method),
        )
        self.assertIn("requirePatrolTestDataConversationForRunner", target_source)
        self.assertIn("initialMessageIds", target_source)

    def test_typed_actor_generated_artifact_cleanup_is_exact_and_converges(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            app_dir = Path(temporary_dir) / "quwoquan_app"
            build_dir = app_dir / "build"
            dart_tool_dir = app_dir / ".dart_tool"
            build_dir.mkdir(parents=True)
            dart_tool_dir.mkdir(parents=True)
            plain = build_dir / "kernel_blob.bin"
            plain.write_bytes(b"prefix runtime-owner suffix")
            archive = build_dir / "app-debug.apk"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("assets/test.txt", "encoded-runtime-owner")
            ignored_cache = (
                build_dir
                / "app/intermediates/incremental/packageDebugAndroidTest/tmp/zip-cache/androidResources"
            )
            ignored_cache.parent.mkdir(parents=True)
            ignored_cache.write_bytes(b"not-a-zip runtime-owner")
            unrelated = dart_tool_dir / "package_config.json"
            unrelated.write_text("unrelated\n", encoding="utf-8")

            removed = smoke._purge_typed_actor_credential_artifacts(
                ("runtime-owner", "encoded-runtime-owner"),
                app_dir=app_dir,
            )

            self.assertEqual(removed, 2)
            self.assertFalse(plain.exists())
            self.assertFalse(archive.exists())
            self.assertTrue(ignored_cache.exists())
            self.assertEqual(
                unrelated.read_text(encoding="utf-8"),
                "unrelated\n",
            )

    def test_provider_uat_defines_are_explicit_private_inputs(self) -> None:
        args = self._args(
            env_name="gamma-local",
            runtime_env="gamma",
            test_auth_token="remote-access",
            test_refresh_token="remote-refresh",
        )
        environment = {
            "QWQ_PROVIDER_UAT_DART_DEFINE_KEYS": (
                "QWQ_PROVIDER_UAT_LOCATION_QUERY,"
                "QWQ_PROVIDER_UAT_LOCATION_EXPECTED_TEXT"
            ),
            "QWQ_PROVIDER_UAT_LOCATION_QUERY": "天安门",
            "QWQ_PROVIDER_UAT_LOCATION_EXPECTED_TEXT": "天安门",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            path = smoke._create_patrol_secret_define_file(args)
            provider_secrets = smoke._provider_uat_secret_values()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["QWQ_PROVIDER_UAT_LOCATION_QUERY"],
                "天安门",
            )
            self.assertEqual(
                payload["QWQ_PROVIDER_UAT_LOCATION_EXPECTED_TEXT"],
                "天安门",
            )
            self.assertEqual(
                provider_secrets,
                (
                    "天安门",
                    "QWQ_PROVIDER_UAT_LOCATION_QUERY=天安门",
                    "天安门",
                    "QWQ_PROVIDER_UAT_LOCATION_EXPECTED_TEXT=天安门",
                ),
            )
        finally:
            path.unlink(missing_ok=True)

    def test_unauthenticated_auth_entry_rejects_preloaded_session(self) -> None:
        args = self._args(
            target=(
                "test/user_acceptance/service/user_service/account/authentication_challenge/"
                "sms_otp_provider__user_acceptance_test.dart"
            ),
            unauthenticated_auth_entry=True,
        )
        with self.assertRaisesRegex(
            ValueError,
            "cannot preload a session",
        ):
            smoke._prepare_execution_session(args)

        args.test_auth_token = ""
        args.test_refresh_token = ""
        args.current_owner_id = ""
        args.current_persona_id = ""
        self.assertEqual(
            smoke._prepare_execution_session(args),
            "unauthenticated_auth_entry",
        )
        self.assertFalse(smoke._uses_runtime_anonymous_session(args))
        command = smoke.patrol_command(
            {
                "id": "android-alpha",
                "targetPlatform": "android-arm64",
                "emulator": True,
            },
            args,
            "patrol",
            dart_define_file=Path("/tmp/provider-uat-defines.json"),
        )
        self.assertIn(
            "--dart-define=QWQ_PATROL_SESSION_MODE=unauthenticated_auth_entry",
            command,
        )
        self.assertIn(
            "--dart-define-from-file=/tmp/provider-uat-defines.json",
            command,
        )
        self.assertEqual(smoke._missing_required_args(args), [])

    def test_patrol_output_redacts_access_and_refresh_secrets(self) -> None:
        output = "argv access-secret refresh-secret\nrequest failed"

        self.assertEqual(
            smoke._redact_text(output, ("access-secret", "refresh-secret")),
            "argv <redacted> <redacted>\nrequest failed",
        )

    def test_patrol_output_redacts_base64_encoded_provider_define(self) -> None:
        define = "QWQ_PROVIDER_UAT_SMS_PHONE=19912345678"
        encoded = base64.b64encode(define.encode("utf-8")).decode("ascii")

        self.assertEqual(
            smoke._redact_text(f"-Pdart-defines={encoded}", (define,)),
            "-Pdart-defines=<redacted>",
        )

    def test_remote_session_missing_actor_is_gate_blocked(self) -> None:
        args = self._args(
            env_name="prod-hosted",
            runtime_env="prod",
            test_auth_token="remote-access",
            test_refresh_token="remote-refresh",
            current_owner_id="",
            current_persona_id="",
        )

        self.assertEqual(
            smoke._missing_required_args(args),
            ["current_owner_id", "current_persona_id"],
        )

    def test_release_bound_homepage_uat_does_not_require_video_canary(self) -> None:
        args = self._args(
            target=(
                "test/user_acceptance/service/entity_service/entity_homepage/homepage/"
                "release_homepage__consumer_render__functional__user_acceptance_test.dart"
            ),
            release_uat_cases="/tmp/homepage_verification_cases.json",
            video_playback_canary_work_id="",
        )

        self.assertNotIn(
            "video_playback_canary_work_id",
            smoke._missing_required_args(args),
        )

    def test_release_bound_core_readback_still_requires_video_canary(self) -> None:
        args = self._args(
            target=smoke.CORE_READBACK_TARGET,
            video_playback_canary_work_id="",
        )

        self.assertTrue(smoke._requires_video_playback_canary(args))
        self.assertIn(
            "video_playback_canary_work_id",
            smoke._missing_required_args(args),
        )

    def test_release_bound_core_readback_requires_explicit_positive_video_page_count(
        self,
    ) -> None:
        args = self._args(
            target=smoke.CORE_READBACK_TARGET,
            video_playback_canary_work_id="video-a",
        )
        for destination, _ in smoke.RELEASE_APP_UAT_DEFINES:
            setattr(args, destination, "canonical-release-value")
        device = {
            "id": "sim-1",
            "targetPlatform": "ios",
            "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
            "emulator": True,
        }
        for value in ("", "0", "many"):
            with self.subTest(value=value), mock.patch.dict(
                os.environ,
                {smoke.APP_CONTENT_VIDEO_PAGE_COUNT_ENV: value},
                clear=False,
            ), self.assertRaisesRegex(ValueError, "positive release video page count"):
                smoke.patrol_command(
                    device,
                    args,
                    "patrol",
                    dart_define_file=None,
                    typed_test_data_session_handoff=True,
                )
        with mock.patch.dict(
            os.environ,
            {smoke.APP_CONTENT_VIDEO_PAGE_COUNT_ENV: "1"},
            clear=False,
        ):
            command = smoke.patrol_command(
                device,
                args,
                "patrol",
                dart_define_file=None,
                typed_test_data_session_handoff=True,
            )
        self.assertIn("--dart-define=DATA_RELEASE_VIDEO_PAGE_COUNT=1", command)

    def test_release_bound_home_video_still_requires_video_canary(self) -> None:
        args = self._args(
            env_name="alpha-local",
            runtime_env="alpha",
            api_contract_env="alpha",
            target=smoke.HOME_VIDEO_PLAYBACK_TARGET,
            video_playback_canary_work_id="",
        )

        self.assertTrue(smoke._requires_video_playback_canary(args))
        self.assertIn(
            "video_playback_canary_work_id",
            smoke._missing_required_args(args),
        )
        self.assertTrue(smoke._requires_typed_authenticated_session(args))

    def test_release_bound_home_video_binds_exact_release_identity(self) -> None:
        args = self._args(
            env_name="alpha-local",
            runtime_env="alpha",
            api_contract_env="alpha",
            target=smoke.HOME_VIDEO_PLAYBACK_TARGET,
            data_release_id="release-a",
        )
        command = smoke.patrol_command(
            {
                "id": "sim-1",
                "targetPlatform": "ios",
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "emulator": True,
            },
            args,
            "patrol",
            dart_define_file=None,
            typed_test_data_session_handoff=True,
        )

        self.assertIn("--dart-define=DATA_RELEASE_ID=release-a", command)

        args.data_release_id = ""
        with self.assertRaisesRegex(
            ValueError,
            "home video playback requires one immutable release identity",
        ):
            smoke.patrol_command(
                {
                    "id": "sim-1",
                    "targetPlatform": "ios",
                    "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                    "emulator": True,
                },
                args,
                "patrol",
                dart_define_file=None,
                typed_test_data_session_handoff=True,
            )

    def test_release_bound_dry_run_does_not_touch_ios_device_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            cases = root / "homepage_verification_cases.json"
            cases.write_text(
                json.dumps(
                    {
                        "schema": "quwoquan_data.homepage_verification_case_manifest",
                        "environment": "gamma",
                        "releaseId": "release-a",
                        "runId": "apply-a",
                        "importerReportRef": "env/gamma/runs/data-release/release-a/apply-a/homepage-import.json",
                        "generatedAt": "2026-07-24T00:00:00Z",
                        "cases": [
                            {
                                "entityRef": "地点/景区/test-entity-a",
                                "homepageId": "homepage-a",
                                "title": "test-entity-a",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = self._args(
                dry_run=True,
                platform="ios",
                release_uat_cases=str(cases),
                report=str(root / "report.json"),
            )
            device = {
                "id": "dry-run-ios",
                "name": "Dry Run iPhone",
                "targetPlatform": "ios",
                "emulator": True,
                "sdk": "com.apple.CoreSimulator.SimRuntime.iOS-17-2",
                "screenClass": "phone",
            }
            with (
                mock.patch.object(smoke_entry, "parse_args", return_value=args),
                mock.patch.object(smoke_entry, "dry_run_devices", return_value=[device]),
                mock.patch.object(smoke_entry, "ensure_patrol_ios_products_bridge") as bridge,
                mock.patch.object(smoke_entry, "capture_device_screenshot") as screenshot,
            ):
                self.assertEqual(smoke.main(), 0)

            bridge.assert_not_called()
            screenshot.assert_not_called()
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "dry_run")
            self.assertEqual(report["caseResults"][0]["status"], "not_executed")
            self.assertNotIn("currentOwnerId", report)
            self.assertNotIn("currentPersonaId", report)
            self.assertTrue(report["hasCurrentOwnerIdentity"])
            self.assertTrue(report["hasCurrentPersonaIdentity"])
            self.assertEqual(report["runs"][0]["evidence"]["localTlsTrust"]["reason"], "not-required")
            self.assertEqual(report["runs"][0]["evidence"]["beforeScreenshot"]["reason"], "dry-run")

    def test_local_gamma_rejects_host_injected_session(self) -> None:
        args = self._args(test_auth_token="host-token")

        with self.assertRaisesRegex(ValueError, "device-runtime anonymous login"):
            smoke._prepare_execution_session(args)

    def test_output_evidence_ref_removes_repo_output_prefix(self) -> None:
        path = ROOT / ".qwq_output/env/gamma/runs/data-release/release/apply/homepage_verification_cases.json"

        self.assertEqual(
            smoke._output_evidence_ref(path),
            "env/gamma/runs/data-release/release/apply/homepage_verification_cases.json",
        )


if __name__ == "__main__":
    unittest.main()
