"""Keep Provider Patrol launcher handoff on the stackctl-selected runtime rail.

spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002.t2
spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-003.t1
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as subject

# 入口拆为薄壳 + environment_patrol_smoke 子包后，mock.patch.object 必须打在
# 被测函数实际读取全局名的实现模块（handoff）上，而不是入口 re-export 的绑定上。
from quwoquan_ops.cli.smoke.environment_patrol_smoke import (
    handoff as subject_handoff,
)
from quwoquan_ops.ci.provider_conformance import run_provider_patrol_uat as patrol_runner


_IDENTITY_ENV = "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
_PROVIDER_DIGEST = "sha256:" + "2" * 64
_IMMUTABLE_CANDIDATE = "sha256:" + "3" * 64
_MUTABLE_COMPOSE = "sha256:" + "4" * 64


def _args(
    *,
    candidate_digest: str,
    runtime_mode: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        env_name="local-alpha",
        runtime_env="alpha",
        candidate_digest=candidate_digest,
        runtime_mode=runtime_mode,
    )


def _immutable_identity() -> dict[str, object]:
    return {
        "schema": "stackctl.provider_conformance_runtime_identity.v1",
        "runtimeMode": "immutable_candidate",
        "environment": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "startupAttemptId": "attempt-alpha-immutable",
        "providerRuntimeDigest": _PROVIDER_DIGEST,
        "failureFree": True,
        "nonPromotable": False,
        "candidateDigest": _IMMUTABLE_CANDIDATE,
    }


def _mutable_identity() -> dict[str, object]:
    return {
        "schema": "stackctl.provider_conformance_runtime_identity.v1",
        "runtimeMode": "test_live",
        "environment": "alpha",
        "target": "alpha-local",
        "workload": "full",
        "startupAttemptId": "attempt-alpha-test-live",
        "providerRuntimeDigest": _PROVIDER_DIGEST,
        "failureFree": True,
        "nonPromotable": True,
        "mutableComposeDigest": _MUTABLE_COMPOSE,
        "mutableConfigurationDigest": "sha256:" + "5" * 64,
        "mutableStateDigest": "sha256:" + "6" * 64,
        "mutableWorkspaceStatusDigest": "sha256:" + "7" * 64,
        "mutableResolverHandoffDigest": "sha256:" + "8" * 64,
        "mutableSourceRevision": "a" * 40,
    }


class ProviderPatrolLauncherHandoffRuntimeModeContractTest(unittest.TestCase):
    def test_runtime_identity_is_frozen_before_consumer_lease_and_builder(
        self,
    ) -> None:
        main_source = inspect.getsource(subject.main)
        validation = main_source.index(
            "_validated_provider_patrol_runtime_identity("
        )
        lease = main_source.index("_acquire_patrol_consumer_lease(")
        builder = main_source.index("_provider_patrol_launcher_handoff(")
        self.assertLess(validation, lease)
        self.assertLess(lease, builder)

    def test_unbound_canonical_builder_keeps_test_live_policy_without_binding(
        self,
    ) -> None:
        completed = mock.Mock(
            returncode=0,
            stdout=json.dumps({"schema": "incomplete-handoff"}),
            stderr="",
        )
        with (
            mock.patch.object(
                subject_handoff,
                "load_test_live_content_binding",
                side_effect=AssertionError(
                    "unbound immutable handoff must not read test_live content"
                ),
            ) as load_binding,
            mock.patch.object(
                subject_handoff,
                "_effective_base_urls_for_device",
                return_value={
                    "gatewayBaseUrl": "https://api.alpha.example",
                    "legalBaseUrl": "https://legal.alpha.example",
                    "publicWebBaseUrl": "https://www.alpha.example",
                    "appDownloadBaseUrl": "https://download.alpha.example",
                    "mediaAvatarBaseUrl": "https://avatar.alpha.example",
                    "mediaImageBaseUrl": "https://image.alpha.example",
                    "mediaVideoBaseUrl": "https://video.alpha.example",
                    "mediaUploadBaseUrl": "https://upload.alpha.example",
                    "rtcMediaConnectionUrl": "wss://rtc.alpha.example",
                },
            ),
            mock.patch.object(subject.subprocess, "run", return_value=completed) as run,
            self.assertRaises(ValueError),
        ):
            subject._canonical_test_live_launcher_handoff(
                _args(
                    candidate_digest=_IMMUTABLE_CANDIDATE,
                    runtime_mode="immutable_candidate",
                ),
                {"id": "ios-simulator", "targetPlatform": "ios"},
                {},
                content_binding_mode="unbound",
            )

        load_binding.assert_not_called()
        command = run.call_args.args[0]
        self.assertEqual(
            command[command.index("--launch-policy") + 1],
            "test_live",
        )
        self.assertNotIn("--content-release-id", command)
        self.assertNotIn("--content-manifest-digest", command)
        self.assertNotIn("--content-readiness-receipt-digest", command)

    def test_immutable_identity_builds_unbound_handoff_without_test_live_binding(
        self,
    ) -> None:
        command_env = {
            _IDENTITY_ENV: json.dumps(_immutable_identity(), sort_keys=True)
        }
        expected = {"schema": "app-launcher-handoff", "contentBindingState": "unbound"}
        with (
            mock.patch.object(
                subject_handoff,
                "load_test_live_content_binding",
                side_effect=AssertionError(
                    "immutable Provider Patrol must not read test_live content"
                ),
            ) as load_binding,
            mock.patch.object(
                subject_handoff,
                "_canonical_test_live_launcher_handoff",
                return_value=expected,
            ) as build_unbound,
        ):
            runtime_identity = subject._validated_provider_patrol_runtime_identity(
                _args(
                    candidate_digest=_IMMUTABLE_CANDIDATE,
                    runtime_mode="immutable_candidate",
                ),
                command_env,
            )
            handoff = subject._provider_patrol_launcher_handoff(
                _args(
                    candidate_digest=_IMMUTABLE_CANDIDATE,
                    runtime_mode="immutable_candidate",
                ),
                {"id": "emulator-5556", "targetPlatform": "android-arm64"},
                command_env,
                runtime_identity=runtime_identity,
            )

        self.assertIs(handoff, expected)
        load_binding.assert_not_called()
        build_unbound.assert_called_once()
        self.assertEqual(
            build_unbound.call_args.kwargs,
            {"content_binding_mode": "unbound"},
        )

    def test_running_test_live_uses_exact_content_binding_without_fallback(
        self,
    ) -> None:
        command_env = {
            _IDENTITY_ENV: json.dumps(_mutable_identity(), sort_keys=True)
        }
        expected = {"schema": "app-launcher-handoff"}
        with mock.patch.object(
            subject_handoff,
            "_canonical_test_live_launcher_handoff",
            return_value=expected,
        ) as build_test_live:
            args = _args(
                candidate_digest=_MUTABLE_COMPOSE,
                runtime_mode="test_live",
            )
            runtime_identity = subject._validated_provider_patrol_runtime_identity(
                args,
                command_env,
            )
            handoff = subject._provider_patrol_launcher_handoff(
                args,
                {"id": "emulator-5556", "targetPlatform": "android-arm64"},
                command_env,
                runtime_identity=runtime_identity,
            )

        self.assertIs(handoff, expected)
        build_test_live.assert_called_once()

        with (
            mock.patch.object(
                subject_handoff,
                "_canonical_test_live_launcher_handoff",
                side_effect=ValueError(
                    "test-live content binding requires the exact running startup attempt"
                ),
            ),
            self.assertRaisesRegex(ValueError, "exact running startup attempt"),
        ):
            subject._provider_patrol_launcher_handoff(
                args,
                {"id": "emulator-5556", "targetPlatform": "android-arm64"},
                command_env,
                runtime_identity=runtime_identity,
            )

    def test_partial_foreign_or_candidate_drift_fails_before_either_rail(
        self,
    ) -> None:
        cases: dict[str, dict[str, object]] = {}
        partial = _immutable_identity()
        partial.pop("startupAttemptId")
        cases["partial"] = partial
        foreign = _immutable_identity()
        foreign["target"] = "beta-local"
        cases["foreign"] = foreign
        candidate_drift = _immutable_identity()
        candidate_drift["candidateDigest"] = "sha256:" + "9" * 64
        cases["candidate"] = candidate_drift

        for label, identity in cases.items():
            with (
                self.subTest(label=label),
                self.assertRaisesRegex(
                    ValueError,
                    "Provider Patrol runtime identity handoff",
                ),
            ):
                subject._validated_provider_patrol_runtime_identity(
                    _args(
                        candidate_digest=_IMMUTABLE_CANDIDATE,
                        runtime_mode="immutable_candidate",
                    ),
                    {_IDENTITY_ENV: json.dumps(identity, sort_keys=True)},
                )

    def test_explicit_identity_requires_matching_runtime_mode_before_launch(
        self,
    ) -> None:
        command_env = {
            _IDENTITY_ENV: json.dumps(_immutable_identity(), sort_keys=True)
        }
        for runtime_mode in ("", "test_live"):
            with (
                self.subTest(runtime_mode=runtime_mode),
                self.assertRaisesRegex(
                    ValueError,
                    "Provider Patrol runtime identity handoff",
                ),
            ):
                subject._validated_provider_patrol_runtime_identity(
                    _args(
                        candidate_digest=_IMMUTABLE_CANDIDATE,
                        runtime_mode=runtime_mode,
                    ),
                    command_env,
                )

    def test_non_provider_patrol_without_identity_preserves_test_live_behavior(
        self,
    ) -> None:
        expected = {"schema": "app-launcher-handoff"}
        with mock.patch.object(
            subject_handoff,
            "_canonical_test_live_launcher_handoff",
            return_value=expected,
        ) as build_test_live:
            args = _args(candidate_digest="", runtime_mode="")
            runtime_identity = subject._validated_provider_patrol_runtime_identity(
                args,
                {},
            )
            handoff = subject._provider_patrol_launcher_handoff(
                args,
                {"id": "emulator-5556", "targetPlatform": "android-arm64"},
                {},
                runtime_identity=runtime_identity,
            )

        self.assertIs(handoff, expected)
        build_test_live.assert_called_once()

    def test_provider_runner_passes_verified_runtime_mode_and_baseline(self) -> None:
        command = ["python3", "run_environment_patrol_smoke.py"]
        immutable = mock.Mock(
            launch_policy="prod_release",
            non_promotable=False,
            baseline_id=_IMMUTABLE_CANDIDATE,
        )
        patrol_runner._append_runtime_identity_arguments(command, immutable)
        self.assertEqual(
            command[-4:],
            [
                "--runtime-mode",
                "immutable_candidate",
                "--candidate-digest",
                _IMMUTABLE_CANDIDATE,
            ],
        )

        mutable = mock.Mock(
            launch_policy="test_live",
            non_promotable=True,
            baseline_id=_MUTABLE_COMPOSE,
        )
        patrol_runner._append_runtime_identity_arguments(command, mutable)
        self.assertEqual(
            command[-4:],
            [
                "--runtime-mode",
                "test_live",
                "--candidate-digest",
                _MUTABLE_COMPOSE,
            ],
        )


if __name__ == "__main__":
    unittest.main()
