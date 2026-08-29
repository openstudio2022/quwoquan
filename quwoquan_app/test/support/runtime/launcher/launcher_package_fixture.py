from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any, Iterator
from unittest import mock

APP_DIR = Path(__file__).resolve().parents[4]
if str(APP_DIR / "scripts/env") not in sys.path:
    sys.path.insert(0, str(APP_DIR / "scripts/env"))

from quwoquan_ops.cli.lib.app_launch_manifest_contract import (
    build_runtime_config_trust_envelope,
)
from quwoquan_ops.cli.lib.environment_topology import get_target, load_environment_topology
from quwoquan_ops.cli.lib.local_app_runtime_config_keys import (
    prepare_local_app_runtime_config_signing,
)


_SHARED_NONPROD_AUTHORITY_ROOT: ContextVar[Path | None] = ContextVar(
    "shared_nonprod_authority_root",
    default=None,
)


@contextmanager
def shared_nonprod_launcher_authority() -> Iterator[None]:
    with tempfile.TemporaryDirectory(prefix="qwq-launcher-nonprod-authority-") as temporary:
        token = _SHARED_NONPROD_AUTHORITY_ROOT.set(Path(temporary))
        try:
            yield
        finally:
            _SHARED_NONPROD_AUTHORITY_ROOT.reset(token)


@dataclass(frozen=True)
class LauncherPackageFixture:
    environment: str
    target: str
    candidate_root: Path
    package_dir: Path
    runtime_config_path: Path
    runtime_config_package: dict[str, Any]
    runtime_config_trust_envelope: dict[str, Any]

    def load_runtime_config_package(self, args: Any) -> dict[str, Any]:
        if args.env != self.environment or args.target != self.target:
            raise ValueError("test launcher package target identity mismatch")
        return json.loads(json.dumps(self.runtime_config_package))

    def validate_runtime_config_package(
        self,
        validator: Any,
        package: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[str]:
        return validator(
            package or self.runtime_config_package,
            self.runtime_config_trust_envelope,
            **kwargs,
        )

    def validate_handoff(
        self,
        validator: Any,
        handoff: dict[str, Any],
        contract: dict[str, Any] | None = None,
    ) -> list[str]:
        return validator(
            handoff,
            self.runtime_config_trust_envelope,
            contract,
        )

    def runtime_config_package_digest(
        self,
        contract: dict[str, Any],
    ) -> str:
        settings = contract["digest_contract"]["canonical_json"]
        encoded = json.dumps(
            self.runtime_config_package,
            ensure_ascii=settings["ensure_ascii"],
            separators=tuple(settings["separators"]),
            sort_keys=settings["sort_keys"],
        ).encode(contract["digest_contract"]["input_encoding"])
        algorithm = str(contract["digest_contract"]["algorithm"])
        digest = hashlib.new(algorithm, encoded)
        return f"{algorithm}:{digest.hexdigest()}"


@contextmanager
def temporary_launcher_package(
    environment: str,
    target: str,
) -> Iterator[LauncherPackageFixture]:
    topology = load_environment_topology()
    target_config = get_target(topology, target)
    if target_config.get("env") != environment:
        raise ValueError("test launcher package target/environment mismatch")
    public_bases = dict(target_config.get("publicBases") or {})
    baseline_id = "sha256:" + hashlib.sha256(
        f"launcher-local-contract\0{environment}\0{target}".encode("utf-8")
    ).hexdigest()
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        candidate_root = (
            temporary_root
            / "deploy"
            / target
            / "candidates"
            / "runtime-full"
            / baseline_id.replace(":", "-")
        )
        package_dir = candidate_root / "packages" / "app"
        package_dir.mkdir(parents=True)
        runtime_config_path = package_dir / "app_runtime.yaml"
        runtime_values = {
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
        }
        runtime_config_path.write_text(
            json.dumps(
                {"schema": "app-runtime-config", "runtime": runtime_values},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        source_git_sha = hashlib.sha1(
            f"git\0{environment}\0{target}".encode("utf-8")
        ).hexdigest()
        source_tree_digest = "sha256:" + hashlib.sha256(
            f"tree\0{environment}\0{target}".encode("utf-8")
        ).hexdigest()
        report = {
            "status": "packaged",
            "env": environment,
            "target": target,
            "provenance": {
                "gitRevision": source_git_sha,
                "sourceTreeDigest": source_tree_digest,
            },
        }
        (package_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        fixture_key_root = temporary_root / "keys"
        shared_authority_root = _SHARED_NONPROD_AUTHORITY_ROOT.get()
        key_root = shared_authority_root or fixture_key_root
        with mock.patch(
            "quwoquan_ops.cli.lib.local_app_runtime_config_keys.deployment_target_path",
            side_effect=lambda selected_target, *parts: key_root.joinpath(
                selected_target,
                *parts,
            ),
        ):
            if environment in {"alpha", "beta", "gamma"}:
                signing = prepare_local_app_runtime_config_signing(APP_DIR.parent)
            else:
                signing = _issue_test_signing_material(fixture_key_root / "prod")
        from print_app_env_dart_defines import build_runtime_config_package

        issued_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        launch_policy = (
            "prod" + "_release" if environment == "prod" else "test_live"
        )
        runtime_config_package = build_runtime_config_package(
            environment=environment,
            target=target,
            launch_policy=launch_policy,
            values=runtime_values,
            source_git_sha=source_git_sha,
            source_tree_digest=source_tree_digest,
            signing=signing,
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=1),
        )
        trusted_public_keys = json.loads(
            signing.trusted_public_keys_path.read_text(encoding="utf-8")
        )
        build_profile = "prod" if environment == "prod" else "nonprod"
        runtime_config_trust_envelope = build_runtime_config_trust_envelope(
            build_profile,
            trusted_public_keys,
        )
        yield LauncherPackageFixture(
            environment=environment,
            target=target,
            candidate_root=candidate_root,
            package_dir=package_dir,
            runtime_config_path=runtime_config_path,
            runtime_config_package=runtime_config_package,
            runtime_config_trust_envelope=runtime_config_trust_envelope,
        )


def _issue_test_signing_material(key_root: Path) -> Any:
    from quwoquan_ops.cli.lib.app_runtime_config_signing import SigningMaterial
    from quwoquan_ops.cli.lib.local_app_runtime_config_keys import _issue_keypair

    key_dir = key_root / "secrets/app-runtime-config"
    key_dir.mkdir(parents=True)
    os.chmod(key_dir, 0o700)
    private_path = key_dir / "signing.pem"
    keyring_path = key_dir / "trusted_public_keys.json"
    _issue_keypair(key_dir, private_path, keyring_path)
    keyring = json.loads(keyring_path.read_text(encoding="utf-8"))
    return SigningMaterial(next(iter(keyring)), private_path, keyring_path)


def build_test_handoff_fixture(
    launcher_module: Any,
    environment: str,
    target: str,
    *,
    launch_provenance: str,
    extra_arguments: tuple[str, ...] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = launcher_module.load_launch_manifest_contract()
    arguments = launcher_module._parser(contract).parse_args(
        [
            "--env",
            environment,
            "--target",
            target,
            "--launch-provenance",
            launch_provenance,
            *extra_arguments,
        ]
    )
    with temporary_launcher_package(environment, target) as package:
        with mock.patch.object(
            launcher_module,
            "_runtime_config_trust_envelope",
            return_value=package.runtime_config_trust_envelope,
        ):
            handoff = launcher_module.build_handoff(
                arguments,
                runtime_config_package_loader=package.load_runtime_config_package,
            )
        plain_handoff = {
            **handoff,
            "runtimeConfigPackage": dict(handoff["runtimeConfigPackage"]),
        }
        return plain_handoff, dict(package.runtime_config_trust_envelope)


def build_test_handoff(
    launcher_module: Any,
    environment: str,
    target: str,
    *,
    launch_provenance: str,
    extra_arguments: tuple[str, ...] = (),
) -> dict[str, Any]:
    handoff, _ = build_test_handoff_fixture(
        launcher_module,
        environment,
        target,
        launch_provenance=launch_provenance,
        extra_arguments=extra_arguments,
    )
    return handoff
