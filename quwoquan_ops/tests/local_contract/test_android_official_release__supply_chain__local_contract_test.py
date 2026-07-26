# spec_ref: specs/feature-tree/product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md#gwt-002
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from quwoquan_ops.cli.lib.android_official_release import (
    AndroidOfficialReleaseError,
    _verify_remote_artifact,
    package_android_official_release,
)


class AndroidOfficialReleaseTest(unittest.TestCase):
    def test_packages_signed_apk_proof_and_product_ops_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            apk = tmp_path / "release.apk"
            apk.write_bytes(b"signed-apk-fixture")
            analyzer = _executable(
                tmp_path / "apkanalyzer",
                """#!/bin/sh
case "$2" in
  application-id) echo com.quwoquan.quwoquan_app ;;
  version-name) echo 1.8.2 ;;
  version-code) echo 18201 ;;
  *) exit 2 ;;
esac
""",
            )
            signer = _executable(
                tmp_path / "apksigner",
                """#!/bin/sh
echo 'Signer #1 certificate SHA-256 digest: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
""",
            )

            release = package_android_official_release(
                apk_path=apk,
                package_root=tmp_path / "package",
                public_origin="https://quwoquan.com",
                download_origin="https://cdn.quwoquan.com",
                expected_package="com.quwoquan.quwoquan_app",
                apkanalyzer=str(analyzer),
                apksigner=str(signer),
            )

            manifest = json.loads(Path(str(release["manifestPath"])).read_text())
            self.assertEqual(
                manifest["apkUrl"],
                "https://cdn.quwoquan.com/app/android/1.8.2/"
                "quwoquan-1.8.2-18201.apk",
            )
            self.assertFalse(manifest["remoteVerified"])
            self.assertEqual(len(manifest["apkSHA256"]), 64)
            environment = Path(str(release["environmentPath"])).read_text()
            self.assertIn("PRODUCT_OPS_ANDROID_LATEST_BUILD=18201", environment)
            self.assertIn(
                "PRODUCT_OPS_ANDROID_APK_SIGNING_CERTIFICATE_SHA256=",
                environment,
            )
            self.assertIn(
                "PRODUCT_OPS_ANDROID_APK_URL=https://cdn.quwoquan.com/",
                environment,
            )

    def test_rejects_untrusted_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            apk = tmp_path / "release.apk"
            apk.write_bytes(b"apk")
            analyzer = _executable(
                tmp_path / "apkanalyzer",
                """#!/bin/sh
case "$2" in
  application-id) echo com.quwoquan.quwoquan_app ;;
  version-name) echo 1.8.2 ;;
  version-code) echo 18201 ;;
esac
""",
            )
            signer = _executable(
                tmp_path / "apksigner",
                """#!/bin/sh
echo 'Signer #1 certificate SHA-256 digest: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
""",
            )
            with self.assertRaisesRegex(
                AndroidOfficialReleaseError,
                "HTTPS origin",
            ):
                package_android_official_release(
                    apk_path=apk,
                    package_root=tmp_path / "package",
                    public_origin="https://quwoquan.com",
                    download_origin="http://cdn.quwoquan.com",
                    expected_package="com.quwoquan.quwoquan_app",
                    apkanalyzer=str(analyzer),
                    apksigner=str(signer),
                )

    def test_remote_verification_requires_immutable_apk_response(self) -> None:
        payload = b"signed-production-apk"
        expected_sha256 = hashlib.sha256(payload).hexdigest()

        with _ArtifactServer(payload=payload, immutable=True) as apk_url:
            _verify_remote_artifact(
                apk_url=apk_url,
                expected_sha256=expected_sha256,
                expected_size=len(payload),
            )

        with _ArtifactServer(payload=payload, immutable=False) as apk_url:
            with self.assertRaisesRegex(
                AndroidOfficialReleaseError,
                "immutable cache semantics",
            ):
                _verify_remote_artifact(
                    apk_url=apk_url,
                    expected_sha256=expected_sha256,
                    expected_size=len(payload),
                )


def _executable(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)
    return path


class _ArtifactServer:
    def __init__(self, *, payload: bytes, immutable: bool) -> None:
        self._payload = payload
        self._immutable = immutable
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> str:
        payload = self._payload
        immutable = self._immutable

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/vnd.android.package-archive",
                )
                if immutable:
                    self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        host, port = self._server.server_address
        return f"http://{host}:{port}/quwoquan.apk"

    def __exit__(self, *args: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
