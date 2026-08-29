"""Final AppArtifact runtime-config trust readback local contracts."""

from __future__ import annotations

import json
import os
import stat
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile
import zlib
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


def _trust_envelope(build_profile: str = "nonprod") -> dict[str, object]:
    return {
        "schema": "app-runtime-config-trust",
        "buildProfile": build_profile,
        "signatureAlgorithm": "ed25519",
        "trustedPublicKeys": {
            f"{build_profile}-key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        },
    }


def _trust_bytes(build_profile: str = "nonprod") -> bytes:
    return json.dumps(_trust_envelope(build_profile), sort_keys=True).encode("utf-8")


def _write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "w") as archive:
            for name, payload in entries:
                archive.writestr(name, payload)


def _mark_zip_entries_encrypted(
    path: Path,
    *,
    local_header: bool,
    central_header: bool,
) -> None:
    payload = bytearray(path.read_bytes())
    found = False
    selected_headers = []
    if local_header:
        selected_headers.append((b"PK\x03\x04", 6))
    if central_header:
        selected_headers.append((b"PK\x01\x02", 8))
    for signature, flag_offset in selected_headers:
        cursor = 0
        while True:
            cursor = payload.find(signature, cursor)
            if cursor < 0:
                break
            flags = struct.unpack_from("<H", payload, cursor + flag_offset)[0]
            struct.pack_into("<H", payload, cursor + flag_offset, flags | 0x1)
            cursor += len(signature)
            found = True
    if not found:
        raise AssertionError("zip fixture contains no file header")
    path.write_bytes(payload)


_FAKE_SIGNING_DIGEST = "sha256:" + "2" * 64


def _readback_record(
    *,
    artifact_root: Path,
    artifact: Path,
    platform: str,
    artifact_format: str,
    build_profile: str,
    expected_build_input_digest: str,
    expected_artifact_digest: str | None = None,
    expected_artifact_filesystem_identity: tuple[int, ...] | None = None,
    expected_signing_identity_digest: str = _FAKE_SIGNING_DIGEST,
) -> identity_module.AppArtifactTrustReadback:
    if expected_artifact_digest is None:
        try:
            expected_artifact_digest = package_module._artifact_digest(artifact)
        except AppArtifactBuildError:
            expected_artifact_digest = "sha256:" + "0" * 64
    if expected_artifact_filesystem_identity is None:
        expected_artifact_filesystem_identity = (
            identity_module.artifact_filesystem_identity(artifact)
        )
    with mock.patch.object(
        identity_module,
        "signing_digest",
        return_value=expected_signing_identity_digest,
    ):
        return identity_module.read_runtime_config_trust_envelope(
            artifact_root=artifact_root,
            artifact=artifact,
            platform=platform,
            artifact_format=artifact_format,
            build_profile=build_profile,
            expected_build_input_digest=expected_build_input_digest,
            expected_artifact_digest=expected_artifact_digest,
            expected_artifact_filesystem_identity=(
                expected_artifact_filesystem_identity
            ),
            expected_signing_identity_digest=expected_signing_identity_digest,
        )


def _readback(**values: object) -> str:
    return _readback_record(
        **values,
    ).runtime_config_trust_envelope_digest


class AppArtifactTrustReadbackTest(unittest.TestCase):
    def test_final_mobile_artifact_trust_readback_supports_all_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = identity_module.runtime_config_trust_envelope_digest(
                _trust_envelope()
            )
            fixtures = (
                (
                    "android",
                    "apk",
                    root / "app.apk",
                    "assets/qwq_runtime/runtime-config-trust.json",
                ),
                (
                    "android",
                    "aab",
                    root / "app.aab",
                    "base/assets/qwq_runtime/runtime-config-trust.json",
                ),
                (
                    "ios",
                    "ipa",
                    root / "app.ipa",
                    "Payload/Runner.app/qwq_runtime/runtime-config-trust.json",
                ),
            )
            for platform, artifact_format, artifact, entry in fixtures:
                with self.subTest(artifact_format=artifact_format):
                    decoy = (
                        "base/assets/qwq_runtime/runtime-config-trust.json"
                        if artifact_format == "apk"
                        else "assets/qwq_runtime/runtime-config-trust.json"
                    )
                    entries = [(entry, _trust_bytes())]
                    if artifact_format in {"apk", "aab"}:
                        entries.append((decoy, _trust_bytes("prod")))
                        entries.append((decoy, _trust_bytes("prod")))
                        decoy_package = (
                            "base/assets/qwq_runtime/runtime-config-package.json"
                            if artifact_format == "apk"
                            else "assets/qwq_runtime/runtime-config-package.json"
                        )
                        entries.append((decoy_package, b"{}"))
                    _write_zip(artifact, entries)
                    self.assertEqual(
                        _readback(
                            artifact_root=root,
                            artifact=artifact,
                            platform=platform,
                            artifact_format=artifact_format,
                            build_profile="nonprod",
                            expected_build_input_digest=expected,
                        ),
                        expected,
                    )
            app = root / "Runner.app"
            trust_path = app / "qwq_runtime/runtime-config-trust.json"
            trust_path.parent.mkdir(parents=True)
            trust_path.write_bytes(_trust_bytes())
            self.assertEqual(
                _readback(
                    artifact_root=root,
                    artifact=app,
                    platform="ios",
                    artifact_format="app",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                ),
                expected,
            )

    def test_final_artifact_trust_readback_failures_are_typed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = identity_module.runtime_config_trust_envelope_digest(
                _trust_envelope()
            )
            cases: list[tuple[str, list[tuple[str, bytes]], str]] = [
                ("missing", [("assets/other.json", b"{}")], "trust_missing"),
                (
                    "ambiguous",
                    [
                        (
                            "assets/qwq_runtime/runtime-config-trust.json",
                            _trust_bytes(),
                        ),
                        (
                            "assets/qwq_runtime/runtime-config-trust.json",
                            _trust_bytes(),
                        ),
                    ],
                    "trust_ambiguous",
                ),
                (
                    "unsafe",
                    [
                        (
                            "assets/qwq_runtime/runtime-config-trust.json",
                            _trust_bytes(),
                        ),
                        ("../escape.txt", b"escape"),
                    ],
                    "trust_unsafe_entry",
                ),
                (
                    "backslash",
                    [
                        (
                            "assets/qwq_runtime/runtime-config-trust.json",
                            _trust_bytes(),
                        ),
                        ("assets\\escape.txt", b"escape"),
                    ],
                    "trust_unsafe_entry",
                ),
                (
                    "malformed",
                    [("assets/qwq_runtime/runtime-config-trust.json", b"{")],
                    "trust_malformed",
                ),
                (
                    "duplicate-json-key",
                    [
                        (
                            "assets/qwq_runtime/runtime-config-trust.json",
                            (
                                b'{"schema":"app-runtime-config-trust",'
                                b'"schema":"app-runtime-config-trust"}'
                            ),
                        )
                    ],
                    "trust_malformed",
                ),
                (
                    "schema",
                    [
                        (
                            "assets/qwq_runtime/runtime-config-trust.json",
                            json.dumps(
                                {**_trust_envelope(), "schema": "wrong-schema"}
                            ).encode("utf-8"),
                        )
                    ],
                    "trust_invalid",
                ),
                (
                    "profile",
                    [
                        (
                            "assets/qwq_runtime/runtime-config-trust.json",
                            _trust_bytes("prod"),
                        )
                    ],
                    "trust_profile_mismatch",
                ),
            ]
            for name, entries, blocker in cases:
                with self.subTest(name=name):
                    artifact = root / f"{name}.apk"
                    _write_zip(artifact, entries)
                    with self.assertRaisesRegex(AppArtifactBuildError, blocker):
                        _readback(
                            artifact_root=root,
                            artifact=artifact,
                            platform="android",
                            artifact_format="apk",
                            build_profile="nonprod",
                            expected_build_input_digest=expected,
                        )

            drift = root / "drift.apk"
            _write_zip(
                drift,
                [("assets/qwq_runtime/runtime-config-trust.json", _trust_bytes())],
            )
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_digest_mismatch"):
                _readback(
                    artifact_root=root,
                    artifact=drift,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest="sha256:" + "f" * 64,
                )

    def test_final_artifact_trust_readback_rejects_archive_hazards(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = identity_module.runtime_config_trust_envelope_digest(
                _trust_envelope()
            )
            exact = "assets/qwq_runtime/runtime-config-trust.json"

            for create_system in (3, 0):
                with self.subTest(special_create_system=create_system):
                    special = root / f"special-{create_system}.apk"
                    special_info = zipfile.ZipInfo(exact)
                    special_info.create_system = create_system
                    special_info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    with zipfile.ZipFile(special, "w") as archive:
                        archive.writestr(
                            special_info,
                            b"runtime-config-trust.json",
                        )
                    with self.assertRaisesRegex(
                        AppArtifactBuildError,
                        "trust_unsafe_entry",
                    ):
                        _readback(
                            artifact_root=root,
                            artifact=special,
                            platform="android",
                            artifact_format="apk",
                            build_profile="nonprod",
                            expected_build_input_digest=expected,
                        )

            for header in ("local", "central"):
                with self.subTest(encrypted_header=header):
                    encrypted = root / f"encrypted-{header}.apk"
                    _write_zip(encrypted, [(exact, _trust_bytes())])
                    _mark_zip_entries_encrypted(
                        encrypted,
                        local_header=header == "local",
                        central_header=header == "central",
                    )
                    with self.assertRaisesRegex(
                        AppArtifactBuildError,
                        "trust_unsafe_entry",
                    ):
                        _readback(
                            artifact_root=root,
                            artifact=encrypted,
                            platform="android",
                            artifact_format="apk",
                            build_profile="nonprod",
                            expected_build_input_digest=expected,
                        )

            nul_name = exact + "X"
            nul = root / "nul.apk"
            _write_zip(nul, [(nul_name, _trust_bytes())])
            raw_nul = nul.read_bytes()
            encoded_name = nul_name.encode("utf-8")
            self.assertEqual(raw_nul.count(encoded_name), 2)
            nul.write_bytes(raw_nul.replace(encoded_name, exact.encode() + b"\x00"))
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_unsafe_entry"):
                _readback(
                    artifact_root=root,
                    artifact=nul,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            oversized = root / "oversized.apk"
            _write_zip(oversized, [(exact, _trust_bytes())])
            with (
                mock.patch.object(
                    identity_module,
                    "_MAX_ARTIFACT_ARCHIVE_ENTRY_BYTES",
                    1,
                ),
                self.assertRaisesRegex(
                    AppArtifactBuildError,
                    "trust_unsafe_entry",
                ),
            ):
                _readback(
                    artifact_root=root,
                    artifact=oversized,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            bounded = root / "bounded.apk"
            _write_zip(bounded, [(exact, _trust_bytes())])
            for bound_name in (
                "_MAX_ARTIFACT_ARCHIVE_ENTRIES",
                "_MAX_ARTIFACT_ARCHIVE_TOTAL_BYTES",
            ):
                with (
                    self.subTest(bound=bound_name),
                    mock.patch.object(identity_module, bound_name, 0),
                    self.assertRaisesRegex(
                        AppArtifactBuildError,
                        "trust_unsafe_entry",
                    ),
                ):
                    _readback(
                        artifact_root=root,
                        artifact=bounded,
                        platform="android",
                        artifact_format="apk",
                        build_profile="nonprod",
                        expected_build_input_digest=expected,
                    )

            corrupt = root / "corrupt.apk"
            trust_payload = _trust_bytes()
            _write_zip(corrupt, [(exact, trust_payload)])
            raw = bytearray(corrupt.read_bytes())
            trust_offset = raw.find(trust_payload)
            self.assertGreaterEqual(trust_offset, 0)
            raw[trust_offset] ^= 0x1
            corrupt.write_bytes(raw)
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_malformed"):
                _readback(
                    artifact_root=root,
                    artifact=corrupt,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            deflated = root / "deflated-corrupt.apk"
            with zipfile.ZipFile(
                deflated,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                archive.writestr(exact, trust_payload)
            deflated_raw = bytearray(deflated.read_bytes())
            name_size, extra_size = struct.unpack_from("<HH", deflated_raw, 26)
            compressed_size = struct.unpack_from("<I", deflated_raw, 18)[0]
            compressed_offset = 30 + name_size + extra_size
            self.assertGreater(compressed_size, 0)
            deflated_raw[compressed_offset] ^= 0xFF
            deflated.write_bytes(deflated_raw)
            with self.assertRaisesRegex(
                AppArtifactBuildError,
                "trust_malformed",
            ) as raised:
                _readback(
                    artifact_root=root,
                    artifact=deflated,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )
            self.assertIsInstance(raised.exception.__cause__, zlib.error)

            two_apps = root / "two-apps.ipa"
            _write_zip(
                two_apps,
                [
                    (
                        "Payload/Runner.app/qwq_runtime/runtime-config-trust.json",
                        _trust_bytes(),
                    ),
                    (
                        "Payload/Other.app/qwq_runtime/runtime-config-trust.json",
                        _trust_bytes(),
                    ),
                ],
            )
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_ambiguous"):
                _readback(
                    artifact_root=root,
                    artifact=two_apps,
                    platform="ios",
                    artifact_format="ipa",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            no_apps = root / "no-apps.ipa"
            _write_zip(no_apps, [("Payload/readme.txt", b"not an app")])
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_ambiguous"):
                _readback(
                    artifact_root=root,
                    artifact=no_apps,
                    platform="ios",
                    artifact_format="ipa",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            original = root / "original.apk"
            linked = root / "linked.apk"
            _write_zip(original, [(exact, _trust_bytes())])
            os.link(original, linked)
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_unsafe_entry"):
                _readback(
                    artifact_root=root,
                    artifact=linked,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            symlinked = root / "symlinked.apk"
            symlinked.symlink_to(original)
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_unsafe_entry"):
                _readback(
                    artifact_root=root,
                    artifact=symlinked,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            fifo = root / "fifo.apk"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_unsafe_entry"):
                _readback(
                    artifact_root=root,
                    artifact=fifo,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

    def test_runtime_config_package_sibling_is_rejected_in_all_formats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = identity_module.runtime_config_trust_envelope_digest(
                _trust_envelope()
            )
            fixtures = (
                (
                    "android",
                    "apk",
                    root / "app.apk",
                    "assets/qwq_runtime/runtime-config-trust.json",
                    "assets/qwq_runtime/runtime-config-package.json",
                ),
                (
                    "android",
                    "aab",
                    root / "app.aab",
                    "base/assets/qwq_runtime/runtime-config-trust.json",
                    "base/assets/qwq_runtime/runtime-config-package.json",
                ),
                (
                    "ios",
                    "ipa",
                    root / "app.ipa",
                    "Payload/Runner.app/qwq_runtime/runtime-config-trust.json",
                    "Payload/Runner.app/qwq_runtime/runtime-config-package.json",
                ),
            )
            for (
                platform,
                artifact_format,
                artifact,
                trust_entry,
                package_entry,
            ) in fixtures:
                with self.subTest(artifact_format=artifact_format):
                    _write_zip(
                        artifact,
                        [(trust_entry, _trust_bytes()), (package_entry, b"{}")],
                    )
                    with self.assertRaisesRegex(
                        AppArtifactBuildError,
                        "runtime_config_package_forbidden",
                    ):
                        _readback(
                            artifact_root=root,
                            artifact=artifact,
                            platform=platform,
                            artifact_format=artifact_format,
                            build_profile="nonprod",
                            expected_build_input_digest=expected,
                        )

            app = root / "Runner.app"
            runtime = app / "qwq_runtime"
            runtime.mkdir(parents=True)
            (runtime / "runtime-config-trust.json").write_bytes(_trust_bytes())
            (runtime / "runtime-config-package.json").write_text(
                "{}",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                AppArtifactBuildError,
                "runtime_config_package_forbidden",
            ):
                _readback(
                    artifact_root=root,
                    artifact=app,
                    platform="ios",
                    artifact_format="app",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

    def test_app_trust_readback_rejects_symlink_and_hardlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = identity_module.runtime_config_trust_envelope_digest(
                _trust_envelope()
            )

            symlink_app = root / "Symlink.app"
            symlink_runtime = symlink_app / "qwq_runtime"
            symlink_runtime.mkdir(parents=True)
            external = root / "external-trust.json"
            external.write_bytes(_trust_bytes())
            (symlink_runtime / "runtime-config-trust.json").symlink_to(external)
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_unsafe_entry"):
                _readback(
                    artifact_root=root,
                    artifact=symlink_app,
                    platform="ios",
                    artifact_format="app",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            runtime_link_app = root / "RuntimeLink.app"
            runtime_link_app.mkdir()
            external_runtime = root / "external-runtime"
            external_runtime.mkdir()
            (external_runtime / "runtime-config-trust.json").write_bytes(_trust_bytes())
            (runtime_link_app / "qwq_runtime").symlink_to(
                external_runtime,
                target_is_directory=True,
            )
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_unsafe_entry"):
                _readback(
                    artifact_root=root,
                    artifact=runtime_link_app,
                    platform="ios",
                    artifact_format="app",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            real_app = root / "Real.app"
            real_runtime = real_app / "qwq_runtime"
            real_runtime.mkdir(parents=True)
            (real_runtime / "runtime-config-trust.json").write_bytes(_trust_bytes())
            app_link = root / "AppLink.app"
            app_link.symlink_to(real_app, target_is_directory=True)
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_unsafe_entry"):
                _readback(
                    artifact_root=root,
                    artifact=app_link,
                    platform="ios",
                    artifact_format="app",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            fifo_app = root / "Fifo.app"
            fifo_runtime = fifo_app / "qwq_runtime"
            fifo_runtime.mkdir(parents=True)
            os.mkfifo(fifo_runtime / "runtime-config-trust.json")
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_unsafe_entry"):
                _readback(
                    artifact_root=root,
                    artifact=fifo_app,
                    platform="ios",
                    artifact_format="app",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            hardlink_app = root / "Hardlink.app"
            hardlink_runtime = hardlink_app / "qwq_runtime"
            hardlink_runtime.mkdir(parents=True)
            hardlink_trust = hardlink_runtime / "runtime-config-trust.json"
            hardlink_trust.write_bytes(_trust_bytes())
            os.link(hardlink_trust, root / "hardlink-copy.json")
            with self.assertRaisesRegex(AppArtifactBuildError, "trust_unsafe_entry"):
                _readback(
                    artifact_root=root,
                    artifact=hardlink_app,
                    platform="ios",
                    artifact_format="app",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

    def test_archive_trust_readback_detects_ctime_and_path_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = identity_module.runtime_config_trust_envelope_digest(
                _trust_envelope()
            )
            exact = "assets/qwq_runtime/runtime-config-trust.json"
            original_zip_read = zipfile.ZipFile.read

            ctime_artifact = root / "ctime.apk"
            _write_zip(ctime_artifact, [(exact, _trust_bytes())])
            ctime_mutated = False

            def mutate_ctime(
                archive: zipfile.ZipFile,
                member: object,
                pwd: bytes | None = None,
            ) -> bytes:
                nonlocal ctime_mutated
                payload = original_zip_read(archive, member, pwd=pwd)
                if not ctime_mutated:
                    before = ctime_artifact.stat()
                    raw = bytearray(ctime_artifact.read_bytes())
                    raw[0] ^= 0x1
                    ctime_artifact.write_bytes(raw)
                    os.utime(
                        ctime_artifact,
                        ns=(before.st_atime_ns, before.st_mtime_ns),
                    )
                    ctime_mutated = True
                return payload

            with (
                mock.patch.object(
                    identity_module.zipfile.ZipFile,
                    "read",
                    autospec=True,
                    side_effect=mutate_ctime,
                ),
                self.assertRaisesRegex(
                    AppArtifactBuildError,
                    "trust_readback_drift",
                ),
            ):
                _readback(
                    artifact_root=root,
                    artifact=ctime_artifact,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            replaced_artifact = root / "replaced.apk"
            _write_zip(replaced_artifact, [(exact, _trust_bytes())])
            replacement_done = False

            def replace_path(
                archive: zipfile.ZipFile,
                member: object,
                pwd: bytes | None = None,
            ) -> bytes:
                nonlocal replacement_done
                payload = original_zip_read(archive, member, pwd=pwd)
                if not replacement_done:
                    replaced_artifact.rename(root / "opened.apk")
                    _write_zip(replaced_artifact, [(exact, _trust_bytes())])
                    replacement_done = True
                return payload

            with (
                mock.patch.object(
                    identity_module.zipfile.ZipFile,
                    "read",
                    autospec=True,
                    side_effect=replace_path,
                ),
                self.assertRaisesRegex(
                    AppArtifactBuildError,
                    "trust_readback_drift",
                ),
            ):
                _readback(
                    artifact_root=root,
                    artifact=replaced_artifact,
                    platform="android",
                    artifact_format="apk",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

    def test_app_trust_readback_detects_package_and_path_toctou(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = identity_module.runtime_config_trust_envelope_digest(
                _trust_envelope()
            )
            original_os_read = os.read

            package_app = root / "PackageRace.app"
            package_runtime = package_app / "qwq_runtime"
            package_runtime.mkdir(parents=True)
            (package_runtime / "runtime-config-trust.json").write_bytes(_trust_bytes())
            package_created = False

            def create_package(descriptor: int, amount: int) -> bytes:
                nonlocal package_created
                payload = original_os_read(descriptor, amount)
                if payload and not package_created:
                    (package_runtime / "runtime-config-package.json").write_text(
                        "{}",
                        encoding="utf-8",
                    )
                    package_created = True
                return payload

            with (
                mock.patch.object(
                    identity_module.os,
                    "read",
                    side_effect=create_package,
                ),
                self.assertRaisesRegex(
                    AppArtifactBuildError,
                    "runtime_config_package_forbidden",
                ),
            ):
                _readback(
                    artifact_root=root,
                    artifact=package_app,
                    platform="ios",
                    artifact_format="app",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )

            replace_app = root / "Replace.app"
            replace_runtime = replace_app / "qwq_runtime"
            replace_runtime.mkdir(parents=True)
            (replace_runtime / "runtime-config-trust.json").write_bytes(_trust_bytes())
            app_replaced = False

            def replace_app_path(descriptor: int, amount: int) -> bytes:
                nonlocal app_replaced
                payload = original_os_read(descriptor, amount)
                if payload and not app_replaced:
                    replace_app.rename(root / "Opened.app")
                    new_runtime = replace_app / "qwq_runtime"
                    new_runtime.mkdir(parents=True)
                    (new_runtime / "runtime-config-trust.json").write_bytes(
                        _trust_bytes()
                    )
                    app_replaced = True
                return payload

            with (
                mock.patch.object(
                    identity_module.os,
                    "read",
                    side_effect=replace_app_path,
                ),
                self.assertRaisesRegex(
                    AppArtifactBuildError,
                    "trust_readback_drift",
                ),
            ):
                _readback(
                    artifact_root=root,
                    artifact=replace_app,
                    platform="ios",
                    artifact_format="app",
                    build_profile="nonprod",
                    expected_build_input_digest=expected,
                )
