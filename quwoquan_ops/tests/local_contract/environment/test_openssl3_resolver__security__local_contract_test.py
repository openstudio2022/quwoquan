"""OpenSSL 3 Ed25519 raw-signing toolchain contracts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import base64
import hashlib
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import (
    app_launch_manifest_contract,
    app_runtime_config_signing,
    graphql_read_registry_signing,
    local_integration_service_mtls,
)
from quwoquan_ops.cli.lib.openssl3_resolver import (
    OPENSSL_BIN_ENV,
    OpenSSL3CapabilityError,
    OpenSSL3Executable,
    openssl3_identity_report,
    resolve_openssl3,
)


class OpenSSL3ResolverSecurityContractTest(unittest.TestCase):
    def _stub(self, root: Path, *, version: str, reject_rawin: bool = False) -> Path:
        stub = root / "openssl"
        stub.write_text(
            textwrap.dedent(
                f"""\
                #!/bin/sh
                if [ "$1" = "version" ]; then
                  echo "{version}"
                  exit 0
                fi
                if [ "$1" = "genpkey" ]; then
                  while [ "$#" -gt 0 ]; do
                    if [ "$1" = "-out" ]; then shift; printf private > "$1"; exit 0; fi
                    shift
                  done
                fi
                if [ "$1" = "pkey" ]; then
                  while [ "$#" -gt 0 ]; do
                    if [ "$1" = "-out" ]; then shift; printf public > "$1"; exit 0; fi
                    shift
                  done
                fi
                if [ "$1" = "pkeyutl" ] && [ "$2" = "-sign" ]; then
                  {"echo rawin-unsupported >&2; exit 1" if reject_rawin else ""}
                  while [ "$#" -gt 0 ]; do
                    if [ "$1" = "-out" ]; then shift; printf '0000000000000000000000000000000000000000000000000000000000000000' > "$1"; exit 0; fi
                    shift
                  done
                fi
                if [ "$1" = "pkeyutl" ] && [ "$2" = "-verify" ]; then exit 0; fi
                exit 1
                """
            ),
            encoding="utf-8",
        )
        stub.chmod(0o755)
        return stub

    def test_explicit_libressl_is_typed_capability_blocker_without_fallback(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-libressl-stub-") as temporary:
            stub = self._stub(Path(temporary), version="LibreSSL 3.3.6")
            with self.assertRaisesRegex(
                OpenSSL3CapabilityError,
                r"GATE_BLOCK\[OPENSSL_3_ED25519_RAWIN_CAPABILITY\].*LibreSSL 3[.]3[.]6",
            ):
                resolve_openssl3(
                    {OPENSSL_BIN_ENV: str(stub)}.get,
                    which=lambda _name: "/must/not/fallback/openssl",
                )

    def test_hostile_path_relative_candidate_fails_closed(self) -> None:
        with (
            mock.patch(
                "quwoquan_ops.cli.lib.openssl3_resolver._HOMEBREW_OPENSSL_CANDIDATES",
                (),
            ),
            self.assertRaisesRegex(
                OpenSSL3CapabilityError,
                r"PATH openssl must resolve to an absolute executable",
            ),
        ):
            resolve_openssl3({}.get, which=lambda _name: "hostile/openssl")

    def test_explicit_openssl3_wins_over_hostile_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-openssl3-explicit-") as temporary:
            stub = self._stub(Path(temporary), version="OpenSSL 3.6.3 9 Jun 2026")
            resolved = resolve_openssl3(
                {OPENSSL_BIN_ENV: str(stub)}.get,
                which=lambda _name: "/hostile/path/openssl",
            )
            self.assertEqual(resolved.executable, stub.resolve())

    def test_claimed_openssl3_must_pass_real_rawin_sign_and_verify_probe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-openssl3-stub-") as temporary:
            stub = self._stub(
                Path(temporary),
                version="OpenSSL 3.6.3 9 Jun 2026",
                reject_rawin=True,
            )
            with self.assertRaisesRegex(
                OpenSSL3CapabilityError,
                r"pkeyutl -rawin capability.*step=pkeyutl-sign-rawin",
            ):
                resolve_openssl3({OPENSSL_BIN_ENV: str(stub)}.get)

    def test_openssl3_returns_physical_identity_version_and_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-openssl3-stub-") as temporary:
            root = Path(temporary)
            physical = self._stub(root, version="OpenSSL 3.6.3 9 Jun 2026")
            link = root / "selected-openssl"
            link.symlink_to(physical)
            resolved = resolve_openssl3({OPENSSL_BIN_ENV: str(link)}.get)
            self.assertEqual(resolved.executable, physical.resolve())
            self.assertEqual(resolved.version, "OpenSSL 3.6.3 9 Jun 2026")
            self.assertEqual(
                resolved.digest,
                "sha256:" + hashlib.sha256(physical.read_bytes()).hexdigest(),
            )

    def test_report_identity_is_redacted_to_version_and_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-openssl3-report-") as temporary:
            stub = self._stub(Path(temporary), version="OpenSSL 3.6.3 9 Jun 2026")
            resolved = resolve_openssl3({OPENSSL_BIN_ENV: str(stub)}.get)
            report = dict(openssl3_identity_report(resolved))
            self.assertEqual(set(report), {"version", "digest"})
            self.assertNotIn(str(stub), repr(report))
            self.assertEqual(report["digest"], resolved.digest)

    def test_identity_revalidation_rejects_digest_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-openssl3-drift-") as temporary:
            stub = self._stub(Path(temporary), version="OpenSSL 3.6.3 9 Jun 2026")
            resolved = resolve_openssl3({OPENSSL_BIN_ENV: str(stub)}.get)
            stub.write_text(stub.read_text() + "\n# drift\n", encoding="utf-8")
            with self.assertRaisesRegex(
                OpenSSL3CapabilityError,
                r"OPENSSL_3_ED25519_RAWIN_CAPABILITY.*digest changed",
            ):
                resolved.argv("version")

    def test_verify_rejects_malformed_material_before_resolving(self) -> None:
        for module in (graphql_read_registry_signing, app_runtime_config_signing):
            with (
                self.subTest(module=module.__name__),
                mock.patch.object(
                    module,
                    "resolve_openssl3",
                    side_effect=AssertionError("must not resolve malformed material"),
                ),
                self.assertRaisesRegex(ValueError, "signature material is invalid"),
            ):
                module.verify_signature(b"short", b"payload", b"short")

    def test_one_identity_is_reused_by_sign_and_verify_argv(self) -> None:
        resolved = OpenSSL3Executable(
            executable=Path("/physical/openssl"),
            version="OpenSSL 3.6.3",
            digest="sha256:" + "0" * 64,
        )
        calls: list[list[str]] = []

        def run(argv: list[str], **_kwargs: object) -> mock.Mock:
            calls.append(argv)
            output = Path(argv[argv.index("-out") + 1]) if "-out" in argv else None
            if output is not None:
                output.write_bytes(b"0" * 64)
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")

        with (
            mock.patch.object(
                OpenSSL3Executable, "revalidate", return_value=resolved
            ),
            mock.patch.object(
                graphql_read_registry_signing.subprocess, "run", side_effect=run
            ),
        ):
            graphql_read_registry_signing.sign_payload(
                b"key", b"payload", openssl=resolved
            )
            graphql_read_registry_signing.verify_signature(
                b"p" * 32, b"payload", b"s" * 64, openssl=resolved
            )
        self.assertTrue(calls)
        self.assertEqual({argv[0] for argv in calls}, {"/physical/openssl"})

    def test_app_launch_manifest_propagates_typed_capability(self) -> None:
        capability = OpenSSL3CapabilityError(
            "GATE_BLOCK[OPENSSL_3_ED25519_RAWIN_CAPABILITY]: simulated"
        )
        with mock.patch.object(
            app_launch_manifest_contract,
            "verify_signature",
            side_effect=capability,
        ):
            package = {
                "environment": "alpha",
                "target": "alpha-local",
                "buildProfile": "nonprod",
                "launchPolicy": "test_live",
                "runtime": {"appRuntimeEnv": "alpha"},
                "issuedAt": "2026-08-30T00:00:00Z",
                "expiresAt": "2026-08-30T00:01:00Z",
                "payloadDigest": "sha256:" + "0" * 64,
                "signatureKeyId": "key-1",
                "signature": base64.b64encode(b"s" * 64).decode("ascii"),
                "trustedPublicKeys": {
                    "key-1": base64.b64encode(b"p" * 32).decode("ascii")
                },
            }
            envelope = {
                "buildProfile": "nonprod",
                "trustedPublicKeys": package["trustedPublicKeys"],
            }
            with self.assertRaises(OpenSSL3CapabilityError):
                app_launch_manifest_contract.validate_runtime_config_package(
                    package, envelope
                )

    def test_three_consumers_keep_capability_and_signature_failures_distinct(
        self,
    ) -> None:
        capability = OpenSSL3CapabilityError(
            "GATE_BLOCK[OPENSSL_3_ED25519_RAWIN_CAPABILITY]: simulated"
        )
        for module, call in (
            (
                graphql_read_registry_signing,
                lambda: graphql_read_registry_signing.sign_payload(b"key", b"payload"),
            ),
            (
                app_runtime_config_signing,
                lambda: app_runtime_config_signing.sign_payload(b"key", b"payload"),
            ),
            (
                local_integration_service_mtls,
                lambda: (
                    local_integration_service_mtls.prepare_local_integration_service_mtls(
                        "gamma", "gamma-local"
                    )
                ),
            ),
        ):
            with (
                self.subTest(module=module.__name__),
                mock.patch.object(module, "resolve_openssl3", side_effect=capability),
            ):
                with self.assertRaises(OpenSSL3CapabilityError):
                    call()

        resolved = OpenSSL3Executable(
            executable=Path("/physical/openssl"),
            version="OpenSSL 3.6.3",
            digest="sha256:" + "0" * 64,
        )
        failed = mock.Mock(returncode=1, stdout=b"", stderr=b"bad signature")
        for module, expected in (
            (graphql_read_registry_signing, "GraphQL registry signing failed"),
            (app_runtime_config_signing, "App runtime configuration signing failed"),
        ):
            with (
                self.subTest(module=module.__name__),
                mock.patch.object(module, "resolve_openssl3", return_value=resolved),
                mock.patch.object(
                    OpenSSL3Executable, "revalidate", return_value=resolved
                ),
                mock.patch.object(module.subprocess, "run", return_value=failed),
            ):
                with self.assertRaisesRegex(ValueError, expected):
                    module.sign_payload(b"invalid-key", b"payload")


if __name__ == "__main__":
    unittest.main()
