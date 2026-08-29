"""App runtime configuration Ed25519 authority contracts.

spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.app_runtime_config_signing import (
    _derive_public_key,
    SIGNING_KEY_ID_ENV,
    SIGNING_PRIVATE_KEY_FILE_ENV,
    TRUSTED_PUBLIC_KEYS_FILE_ENV,
    canonical_signed_payload,
    decode_keyring,
    resolve_signing_material,
    sign_payload,
    verify_signature,
)


class AppRuntimeConfigSigningSecurityContractTest(unittest.TestCase):
    def _issue_external_material(self, root: Path) -> tuple[Path, Path]:
        private_path = root / "runtime-config-signing.pem"
        public_path = root / "runtime-config-public.der"
        keyring_path = root / "runtime-config-trusted-public-keys.json"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_path)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                str(private_path),
                "-pubout",
                "-outform",
                "DER",
                "-out",
                str(public_path),
            ],
            check=True,
            capture_output=True,
        )
        keyring_path.write_text(
            json.dumps(
                {
                    "runtime-test-ed25519": base64.b64encode(
                        public_path.read_bytes()[-32:]
                    ).decode("ascii")
                },
                ensure_ascii=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        os.chmod(private_path, 0o600)
        os.chmod(keyring_path, 0o600)
        return private_path, keyring_path

    def test_external_ed25519_material_signs_and_verifies_canonical_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-runtime-signing-") as temporary:
            private_path, keyring_path = self._issue_external_material(Path(temporary))
            signing = resolve_signing_material(
                ROOT,
                {
                    SIGNING_KEY_ID_ENV: "runtime-test-ed25519",
                    SIGNING_PRIVATE_KEY_FILE_ENV: str(private_path),
                    TRUSTED_PUBLIC_KEYS_FILE_ENV: str(keyring_path),
                }.get,
            )
            package = {
                "schema": "app-runtime-config-package",
                "environment": "alpha",
                "signature": "must-be-excluded",
                "runtime": {"gatewayBaseUrl": "https://api.alpha.quwoquan.com"},
            }
            payload = canonical_signed_payload(package)
            self.assertNotIn(b'"signature"', payload)
            signature = sign_payload(private_path.read_bytes(), payload)
            public = base64.b64decode(
                decode_keyring(keyring_path.read_bytes())[signing.key_id],
                validate=True,
            )
            verify_signature(public, payload, signature)
            with self.assertRaisesRegex(ValueError, "verification failed"):
                verify_signature(public, payload + b"tampered", signature)

    def test_private_key_must_be_absolute_external_regular_0600_and_match_keyring(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qwq-runtime-signing-") as temporary:
            root = Path(temporary)
            private_path, keyring_path = self._issue_external_material(root)
            environment = {
                SIGNING_KEY_ID_ENV: "runtime-test-ed25519",
                SIGNING_PRIVATE_KEY_FILE_ENV: str(private_path),
                TRUSTED_PUBLIC_KEYS_FILE_ENV: str(keyring_path),
            }
            os.chmod(private_path, 0o644)
            with self.assertRaisesRegex(ValueError, "permissions must be 0600"):
                resolve_signing_material(ROOT, environment.get)
            os.chmod(private_path, 0o600)
            environment[SIGNING_PRIVATE_KEY_FILE_ENV] = private_path.name
            with self.assertRaisesRegex(ValueError, "absolute external path"):
                resolve_signing_material(ROOT, environment.get)
            environment[SIGNING_PRIVATE_KEY_FILE_ENV] = str(private_path)
            wrong_keyring = root / "wrong-keyring.json"
            wrong_keyring.write_text(
                json.dumps({"runtime-test-ed25519": base64.b64encode(b"x" * 32).decode("ascii")}, separators=(",", ":")),
                encoding="utf-8",
            )
            os.chmod(wrong_keyring, 0o600)
            environment[TRUSTED_PUBLIC_KEYS_FILE_ENV] = str(wrong_keyring)
            with self.assertRaisesRegex(ValueError, "does not match keyring"):
                resolve_signing_material(ROOT, environment.get)

    def test_openssl_without_ed25519_is_reported_as_toolchain_not_bad_key(self) -> None:
        """PATH 上解析到不支持 Ed25519 的 openssl 时，诊断必须指向工具链。

        macOS 自带 `/usr/bin/openssl` 是 LibreSSL，对一把完全合法的 Ed25519
        密钥同样退非零。若把它报成「密钥非法」，排查会被引向密钥材料与签名
        权威，而真正要换的只是 PATH——这类误导代价高且会重复发生。
        """

        stub_root = Path(tempfile.mkdtemp())
        stub = stub_root / "openssl"
        stub.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "version" ]; then echo "LibreSSL 3.3.6"; exit 0; fi\n'
            'echo "unsupported private key algorithm:TYPE=Ed25519" >&2\n'
            "exit 1\n",
            encoding="utf-8",
        )
        os.chmod(stub, 0o755)
        original_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = f"{stub_root}:{original_path}"
            with self.assertRaisesRegex(ValueError, "不支持 Ed25519"):
                _derive_public_key(b"-----BEGIN PRIVATE KEY-----\n")
        finally:
            os.environ["PATH"] = original_path

    def test_invalid_key_material_is_still_reported_as_bad_key(self) -> None:
        """工具链判别不得吃掉真实的密钥非法：非 unsupported 的失败仍归密钥。"""

        stub_root = Path(tempfile.mkdtemp())
        stub = stub_root / "openssl"
        stub.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "version" ]; then echo "OpenSSL 3.6.3"; exit 0; fi\n'
            'echo "could not read key" >&2\n'
            "exit 1\n",
            encoding="utf-8",
        )
        os.chmod(stub, 0o755)
        original_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = f"{stub_root}:{original_path}"
            with self.assertRaisesRegex(ValueError, "not a valid Ed25519 PEM"):
                _derive_public_key(b"-----BEGIN PRIVATE KEY-----\n")
        finally:
            os.environ["PATH"] = original_path

    def test_keyring_rejects_noncanonical_or_non_ed25519_values(self) -> None:
        with self.assertRaises(ValueError):
            decode_keyring(b"{}")
        with self.assertRaisesRegex(ValueError, "strict base64"):
            decode_keyring(b'{"runtime-test-ed25519":"not base64"}')
        with self.assertRaisesRegex(ValueError, "must be Ed25519"):
            decode_keyring(
                json.dumps(
                    {"runtime-test-ed25519": base64.b64encode(b"short").decode("ascii")}
                ).encode("utf-8")
            )


if __name__ == "__main__":
    unittest.main()
