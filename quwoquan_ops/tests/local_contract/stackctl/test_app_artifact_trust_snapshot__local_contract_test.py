"""Filesystem snapshot races for final AppArtifact trust readback."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from collections.abc import Callable
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import quwoquan_ops.cli.commands.package_app_artifact as package_module
import quwoquan_ops.cli.commands.package_app_artifact_identity as identity_module
from quwoquan_ops.cli.commands.package_app_artifact_identity import (
    AppArtifactBuildError,
)

_TRUST_ENTRY = "assets/qwq_runtime/runtime-config-trust.json"
_SIGNING_DIGEST = "sha256:" + "2" * 64


def _trust_envelope() -> dict[str, object]:
    return {
        "schema": "app-runtime-config-trust",
        "buildProfile": "nonprod",
        "signatureAlgorithm": "ed25519",
        "trustedPublicKeys": {
            "nonprod-key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        },
    }


def _trust_bytes() -> bytes:
    return json.dumps(_trust_envelope(), sort_keys=True).encode("utf-8")


def _write_apk(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(_TRUST_ENTRY, _trust_bytes())


def _readback(root: Path, artifact: Path) -> identity_module.AppArtifactTrustReadback:
    expected_digest = package_module._artifact_digest(artifact)
    expected_identity = identity_module.artifact_filesystem_identity(artifact)
    expected_trust = identity_module.runtime_config_trust_envelope_digest(
        _trust_envelope()
    )
    with mock.patch.object(
        identity_module,
        "signing_digest",
        return_value=_SIGNING_DIGEST,
    ):
        return identity_module.read_runtime_config_trust_envelope(
            artifact_root=root,
            artifact=artifact,
            platform="android" if artifact.suffix == ".apk" else "ios",
            artifact_format="apk" if artifact.suffix == ".apk" else "app",
            build_profile="nonprod",
            expected_build_input_digest=expected_trust,
            expected_artifact_digest=expected_digest,
            expected_artifact_filesystem_identity=expected_identity,
            expected_signing_identity_digest=_SIGNING_DIGEST,
        )


class AppArtifactTrustSnapshotTest(unittest.TestCase):
    def test_attempt_root_replacement_is_typed_snapshot_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "attempt"
            root.mkdir()
            artifact = root / "app.apk"
            _write_apk(artifact)
            original_read = zipfile.ZipFile.read
            replaced = False

            def replace_root(
                archive: zipfile.ZipFile,
                member: object,
                pwd: bytes | None = None,
            ) -> bytes:
                nonlocal replaced
                payload = original_read(archive, member, pwd=pwd)
                if not replaced:
                    opened_root = parent / "opened-attempt"
                    root.rename(opened_root)
                    root.mkdir()
                    shutil.copy2(opened_root / "app.apk", artifact)
                    replaced = True
                return payload

            with (
                mock.patch.object(
                    identity_module.zipfile.ZipFile,
                    "read",
                    autospec=True,
                    side_effect=replace_root,
                ),
                self.assertRaisesRegex(
                    AppArtifactBuildError,
                    "artifact_snapshot_drift",
                ),
            ):
                _readback(root, artifact)

    def test_app_runtime_and_trust_path_replacement_are_rejected(self) -> None:
        for replaced_component in ("runtime", "trust"):
            with self.subTest(component=replaced_component):  # noqa: SIM117
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    app = root / "Runner.app"
                    runtime = app / "qwq_runtime"
                    runtime.mkdir(parents=True)
                    trust = runtime / "runtime-config-trust.json"
                    trust.write_bytes(_trust_bytes())
                    original_read = os.read
                    replaced = False

                    def replace_path(
                        descriptor: int,
                        amount: int,
                        *,
                        _original_read: Callable[[int, int], bytes] = original_read,
                        _component: str = replaced_component,
                        _runtime: Path = runtime,
                        _app: Path = app,
                        _trust: Path = trust,
                    ) -> bytes:
                        nonlocal replaced
                        payload = _original_read(descriptor, amount)
                        if payload and not replaced:
                            if _component == "runtime":
                                _runtime.rename(_app / "opened-runtime")
                                _runtime.mkdir()
                                (_runtime / "runtime-config-trust.json").write_bytes(
                                    _trust_bytes()
                                )
                            else:
                                _trust.rename(_runtime / "opened-trust.json")
                                _trust.write_bytes(_trust_bytes())
                            replaced = True
                        return payload

                    with (
                        mock.patch.object(
                            identity_module.os,
                            "read",
                            side_effect=replace_path,
                        ),
                        self.assertRaisesRegex(
                            AppArtifactBuildError,
                            "trust_readback_drift",
                        ),
                    ):
                        _readback(root, app)

    def test_app_trust_ctime_only_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = root / "Runner.app"
            runtime = app / "qwq_runtime"
            runtime.mkdir(parents=True)
            trust = runtime / "runtime-config-trust.json"
            trust.write_bytes(_trust_bytes())
            original_read = os.read
            mutated = False

            def mutate_ctime(descriptor: int, amount: int) -> bytes:
                nonlocal mutated
                payload = original_read(descriptor, amount)
                if payload and not mutated:
                    before = trust.stat()
                    trust.write_bytes(_trust_bytes())
                    os.utime(trust, ns=(before.st_atime_ns, before.st_mtime_ns))
                    mutated = True
                return payload

            with (
                mock.patch.object(
                    identity_module.os,
                    "read",
                    side_effect=mutate_ctime,
                ),
                self.assertRaisesRegex(
                    AppArtifactBuildError,
                    "trust_readback_drift",
                ),
            ):
                _readback(root, app)


if __name__ == "__main__":
    unittest.main()
