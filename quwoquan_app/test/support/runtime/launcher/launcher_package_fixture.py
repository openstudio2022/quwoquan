from __future__ import annotations

import hashlib
import json
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)


@dataclass(frozen=True)
class LauncherPackageFixture:
    environment: str
    target: str
    candidate_root: Path
    package_dir: Path
    runtime_config_path: Path
    defines: dict[str, str]

    def load_defines(self, args: Any) -> dict[str, str]:
        if args.env != self.environment or args.target != self.target:
            raise ValueError("test launcher package target identity mismatch")
        values = dict(self.defines)
        optional = {
            "APP_CURRENT_USER_ID": args.current_user_id,
            "APP_INSTANCE_ID": args.app_instance_id,
            "APP_INSTANCE_NAMESPACE": args.app_instance_namespace,
            "QWQ_APP_LAUNCH_MODE": args.launch_mode,
            "APP_ROLLOUT_MODE": args.rollout_mode,
        }
        values.update(
            (key, str(value).strip())
            for key, value in optional.items()
            if str(value).strip()
        )
        return values

    def runtime_config_digest(
        self,
        environment: str,
        contract: dict[str, Any],
        *,
        target: str,
    ) -> str:
        if environment != self.environment or target != self.target:
            raise ValueError("test runtime config target identity mismatch")
        algorithm = str(contract["digest_contract"]["algorithm"])
        digest = hashlib.new(algorithm)
        digest.update(self.runtime_config_path.read_bytes())
        return f"{algorithm}:{digest.hexdigest()}"


@contextmanager
def temporary_launcher_package(
    environment: str,
    target: str,
) -> Iterator[LauncherPackageFixture]:
    topology = load_environment_topology()
    target_config = get_target(topology, target)
    public_bases = dict(target_config.get("publicBases") or {})
    baseline_id = "sha256:" + hashlib.sha256(
        f"launcher-local-contract\0{environment}\0{target}".encode("utf-8")
    ).hexdigest()
    with tempfile.TemporaryDirectory() as temporary_directory:
        candidate_root = (
            Path(temporary_directory)
            / "deploy"
            / target
            / "candidates"
            / "runtime-full"
            / baseline_id.replace(":", "-")
        )
        package_dir = candidate_root / "packages" / "app"
        package_dir.mkdir(parents=True)
        runtime_config_path = package_dir / "app_runtime.yaml"
        runtime_config = {
            "schema": "app-runtime-config",
            "runtime": {
                "appRuntimeEnv": environment,
                "gatewayBaseUrl": str(public_bases["api"]),
                "legalBaseUrl": str(public_bases["legal"]),
                "publicWebBaseUrl": str(public_bases["publicWeb"]),
                "appDownloadBaseUrl": str(public_bases["appDownload"]),
                "realtimeBaseUrl": str(public_bases["realtime"]),
                "mediaAvatarCdnBaseUrl": str(public_bases["mediaAvatar"]),
                "mediaImageCdnBaseUrl": str(public_bases["mediaImage"]),
                "mediaVideoCdnBaseUrl": str(public_bases["mediaVideo"]),
                "mediaUploadBaseUrl": str(public_bases["mediaUpload"]),
                "rtcMediaConnectionUrl": str(public_bases["rtc"]),
                "currentUserId": "",
            },
        }
        runtime_config_path.write_text(
            json.dumps(runtime_config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (package_dir / "report.json").write_text(
            json.dumps(
                {
                    "status": "packaged",
                    "env": environment,
                    "target": target,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        yield LauncherPackageFixture(
            environment=environment,
            target=target,
            candidate_root=candidate_root,
            package_dir=package_dir,
            runtime_config_path=runtime_config_path,
            defines={
                "APP_RUNTIME_ENV": environment,
                "CLOUD_GATEWAY_BASE_URL": str(public_bases["api"]),
                "APP_LEGAL_BASE_URL": str(public_bases["legal"]),
                "PUBLIC_WEB_BASE_URL": str(public_bases["publicWeb"]),
                "APP_DOWNLOAD_BASE_URL": str(public_bases["appDownload"]),
                "REALTIME_CONNECTION_URL": str(public_bases["realtime"]),
                "MEDIA_AVATAR_CDN_BASE_URL": str(public_bases["mediaAvatar"]),
                "MEDIA_IMAGE_CDN_BASE_URL": str(public_bases["mediaImage"]),
                "MEDIA_VIDEO_CDN_BASE_URL": str(public_bases["mediaVideo"]),
                "MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
                "RTC_MEDIA_CONNECTION_URL": str(public_bases["rtc"]),
            },
        )


def build_test_handoff(
    launcher_module: Any,
    environment: str,
    target: str,
    *,
    launch_mode: str,
    extra_arguments: tuple[str, ...] = (),
) -> dict[str, Any]:
    contract = launcher_module.load_launch_manifest_contract()
    arguments = launcher_module._parser(contract).parse_args(
        [
            "--env",
            environment,
            "--target",
            target,
            "--launch-mode",
            launch_mode,
            *extra_arguments,
        ]
    )
    with temporary_launcher_package(environment, target) as package:
        return launcher_module.build_handoff(
            arguments,
            define_loader=package.load_defines,
            runtime_config_digest_loader=package.runtime_config_digest,
        )


def fixture_runtime_config_digest(environment: str, target: str) -> str:
    from launch_manifest_metadata import load_launch_manifest_contract

    contract = load_launch_manifest_contract()
    with temporary_launcher_package(environment, target) as package:
        return package.runtime_config_digest(
            environment,
            contract,
            target=target,
        )
