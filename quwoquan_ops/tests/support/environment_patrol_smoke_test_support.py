"""environment patrol smoke 契约套件的共享 helper 基类。

由 1000 行硬顶拆分自
quwoquan_ops/tests/local_contract/environment/test_environment_patrol_smoke__local_contract_test.py，
供 environment concern 下六个拆分套件共用；方法体逐字保留原实现。
"""

from __future__ import annotations

import argparse
import unittest
from unittest import mock

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib.provider_runtime_composition import (
    compile_provider_runtime_composition,
)
from quwoquan_ops.cli.smoke import run_environment_patrol_smoke as smoke


class EnvironmentPatrolSmokeCaseBase(unittest.TestCase):
    """共享构造 helper；不含 test_ 方法，不会被 pytest 收集为用例。"""

    def _args(self, **overrides: object) -> argparse.Namespace:
        values = {
            "env_name": "local-gamma",
            "runtime_env": "gamma",
            "api_contract_env": "gamma",
            "gateway_base_url": "https://api.gamma.quwoquan.com:19000",
            "product_ops_base_url": "https://ops.gamma.quwoquan.com:19010",
            "media_avatar_base_url": "https://cdn.gamma.quwoquan.com:19100",
            "media_image_base_url": "https://cdn.gamma.quwoquan.com:19100",
            "media_video_base_url": "https://cdn.gamma.quwoquan.com:19100",
            "media_upload_base_url": "https://upload.gamma.quwoquan.com:19130",
            "rtc_media_connection_url": "wss://rtc.gamma.quwoquan.com:19000",
            "video_playback_canary_work_id": "fixture_video_001",
            "patrol_install_id": "",
            "account_closure_disposable_ack": False,
            "persisted_device_session": False,
            "test_auth_token": "local-gamma-token",
            "test_refresh_token": "local-gamma-refresh",
            "release_uat_cases": "",
            "release_uat_cases_b64": "",
            "current_owner_id": "fixture_owner_current",
            "current_persona_id": "fixture_user_current",
            "target": (
                "test/user_acceptance/journeys/home_video_playback/"
                "video_playback_canary__user_acceptance_test.dart"
            ),
            "platform": "all",
            "device_id": [],
            "dry_run": False,
            "stackctl_controlled_edge_fault": False,
            "timeout_seconds": 1200,
            "report": ".qwq_output/env/repo/runs/device-matrix/environment-smoke/report.json",
        }
        values.update(overrides)
        target_name = smoke._local_target_for_environment_alias(
            str(values["env_name"])
        )
        public_bases = smoke.get_target(
            smoke.load_environment_topology(),
            target_name,
        )["publicBases"]
        for argument, role in (
            ("gateway_base_url", "api"),
            ("product_ops_base_url", "productOps"),
            ("media_avatar_base_url", "mediaAvatar"),
            ("media_image_base_url", "mediaImage"),
            ("media_video_base_url", "mediaVideo"),
            ("media_upload_base_url", "mediaUpload"),
            ("rtc_media_connection_url", "rtc"),
        ):
            if argument not in overrides:
                values[argument] = public_bases[role]
        return argparse.Namespace(**values)

    def _test_live_receipt(
        self,
        *,
        environment: str = "gamma",
        status: str = "running",
        failure: str | None = None,
    ) -> dict[str, object]:
        return {
            "environment": environment,
            "target": f"{environment}-local",
            "sourceRevision": "a" * 40,
            "workspaceStatusDigest": "sha256:" + "1" * 64,
            "mutableStateDigest": "sha256:" + "2" * 64,
            "configurationDigest": "sha256:" + "3" * 64,
            "attemptId": f"{environment}-test-live-attempt",
            "status": status,
            "failure": failure,
        }

    def _launcher_handoff(
        self,
        args: argparse.Namespace,
        *,
        android_transport: bool = True,
    ) -> dict[str, object]:
        environment = args.runtime_env
        target = smoke._local_target_for_environment_alias(args.env_name)
        public_bases = smoke.get_target(
            smoke.load_environment_topology(),
            target,
        )["publicBases"]
        # endpoint 取值只由 handoff 携带的签名 runtime package 表达；编译期
        # define 已随 executor cutover 退役，替身不得再自持一份 define 投影。
        runtime_values = {
            "appRuntimeEnv": environment,
            "gatewayBaseUrl": args.gateway_base_url,
            "legalBaseUrl": public_bases["legal"],
            "publicWebBaseUrl": public_bases["publicWeb"],
            "appDownloadBaseUrl": public_bases["appDownload"],
            "realtimeBaseUrl": public_bases["realtime"],
            "mediaAvatarCdnBaseUrl": args.media_avatar_base_url,
            "mediaImageCdnBaseUrl": args.media_image_base_url,
            "mediaVideoCdnBaseUrl": args.media_video_base_url,
            "mediaUploadBaseUrl": args.media_upload_base_url,
            "rtcMediaConnectionUrl": args.rtc_media_connection_url,
        }
        transport = {
            "required": android_transport,
            "reverseExpectedPorts": "19000,19010,19100,19130"
            if android_transport
            else "",
            "reverseActualPorts": "19000,19010,19100,19130"
            if android_transport
            else "",
            "reverseReceiptDigest": "sha256:" + "6" * 64
            if android_transport
            else "",
            "consumerLeaseId": "sha256:" + "7" * 64
            if android_transport
            else "",
        }
        effective = {
            "schema": "app-effective-launch-manifest",
            "environment": environment,
            "buildProfile": "nonprod",
            "target": target,
            "entrypoint": "lib/main_prod.dart",
            "launchProvenance": "canonical_launcher",
            "runtimeConfigSupplyMode": "external_runtime_package",
            "launchPolicy": "test_live",
            "runtimeConfigPackageDigest": "sha256:" + "1" * 64,
            "runtimeConfigTrustEnvelopeDigest": "sha256:" + "3" * 64,
            "requiresLocalTransport": True,
            "transport": transport,
        }
        return {
            **effective,
            "schema": "app-launcher-handoff",
            "compileDiagnostics": {
                "launchProvenance": "canonical_launcher",
                "runtimeConfigSupplyMode": "external_runtime_package",
            },
            "runtimeConfigPackage": {
                "schema": "app-runtime-config-package",
                "environment": environment,
                "target": target,
                "runtime": runtime_values,
            },
            "effectiveLaunchManifest": effective,
            "effectiveLaunchManifestDigest": "sha256:" + "2" * 64,
        }

    def _expected_roles_from_current_provider_source(
        self,
        target_name: str,
    ) -> list[str]:
        environment_name = target_name.removesuffix("-local")
        composition = compile_provider_runtime_composition(
            environment=environment_name,
            target=target_name,
        )
        provider_runtime_digest = composition["runtimeCompositionDigest"]
        with (
            mock.patch.object(
                stackctl,
                "_active_provider_runtime",
                return_value={"composition": composition},
            ),
            mock.patch.object(
                stackctl,
                "load_startup_attempt",
                return_value={
                    "schema": "stackctl-local-startup-attempt",
                    "attemptId": f"attempt-{target_name}",
                    "env": environment_name,
                    "target": target_name,
                    "status": "running",
                    "workload": "full",
                    "providerRuntimeDigest": provider_runtime_digest,
                },
            ),
            # 角色闭包现在会同时读 test-live 回执来裁决两栈互斥，这里显式声明「没有
            # test-live 栈」，否则断言会随开发机上残留的回执飘。
            mock.patch.object(
                stackctl,
                "load_test_live_startup_attempt",
                return_value=None,
            ),
        ):
            return stackctl._expected_local_roles(target_name)
