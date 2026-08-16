# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-005
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quwoquan_ops.cli.commands.dev_session_public_web import (
    _load_dev_session_public_web_package,
)
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    _inject_noindex,
    _tree_sha256,
    _trusted_web_origin,
    _verify_web_build,
)


class WebOfficialReleaseContractTest(unittest.TestCase):
    def _write_package(
        self,
        package_root: Path,
        *,
        environment: str = "alpha",
        public_origin: str = "https://alpha.quwoquan.com",
    ) -> tuple[Path, Path]:
        release_id = f"web-release-{environment}"
        release_root = package_root / release_id
        public = release_root / "public"
        font = public / "assets/assets/fonts/noto_sans_sc/NotoSansSC%5Bwght%5D.ttf"
        font.parent.mkdir(parents=True)
        font.write_bytes(b"noto-sans-sc")
        (public / "index.html").write_text(
            '<!doctype html><html lang="zh-CN"><head>'
            '<meta charset="utf-8">\n'
            '  <meta name="description" content="趣我圈"></head></html>',
            encoding="utf-8",
        )
        (public / "main.dart.js").write_text("main();", encoding="utf-8")
        (public / "flutter_service_worker.js").write_text(
            "self.addEventListener('fetch',()=>{});",
            encoding="utf-8",
        )
        (public / "manifest.json").write_text(
            json.dumps({"display": "standalone", "start_url": "/", "scope": "/"}),
            encoding="utf-8",
        )
        manifest = {
            "schema": "client-app.web.official-release",
            "environment": environment,
            "publicOrigin": public_origin,
            "releaseId": release_id,
            "contentSHA256": _tree_sha256(public),
            "noindex": environment != "prod",
            "spaFallback": "/index.html",
            "htmlContentType": "text/html; charset=utf-8",
            "assetCacheControl": "public, max-age=31536000, immutable",
            "serviceWorker": "flutter_service_worker.js",
        }
        manifest_path = release_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (package_root / "current").symlink_to(release_id, target_is_directory=True)
        return manifest_path, public

    def test_environment_origins_are_exact_official_hosts(self) -> None:
        self.assertEqual(
            _trusted_web_origin("alpha", "https://alpha.quwoquan.com"),
            "https://alpha.quwoquan.com",
        )
        self.assertEqual(
            _trusted_web_origin("prod", "https://quwoquan.com/"),
            "https://quwoquan.com",
        )
        self.assertEqual(
            _trusted_web_origin("beta", "https://beta.quwoquan.com:18000"),
            "https://beta.quwoquan.com",
        )
        for rejected in (
            "https://alpha.example.invalid",
            "https://attacker.example",
            "http://alpha.quwoquan.com",
            "https://user@alpha.quwoquan.com:17000",
            "https://alpha.quwoquan.com:17000/path",
            "https://alpha.quwoquan.com:17000?candidate=mutable",
        ):
            with self.assertRaises(WebOfficialReleaseError):
                _trusted_web_origin("alpha", rejected)

    def test_build_contract_requires_utf8_pwa_and_service_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                '<!doctype html><html lang="zh-CN"><head>'
                '<meta charset="utf-8">\n'
                '  <meta name="description" content="趣我圈"></head></html>',
                encoding="utf-8",
            )
            (root / "main.dart.js").write_text("main();", encoding="utf-8")
            (root / "flutter_service_worker.js").write_text(
                "self.addEventListener('fetch',()=>{});",
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "display": "standalone",
                        "start_url": "/",
                        "scope": "/",
                    }
                ),
                encoding="utf-8",
            )
            font = root / "assets/assets/fonts/noto_sans_sc/NotoSansSC%5Bwght%5D.ttf"
            font.parent.mkdir(parents=True)
            font.write_bytes(b"noto-sans-sc")
            _verify_web_build(root)
            _inject_noindex(root / "index.html")
            self.assertIn(
                'content="noindex,nofollow"',
                (root / "index.html").read_text(encoding="utf-8"),
            )

    def test_dev_session_reads_exact_current_package_and_digests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            manifest_path, public = self._write_package(package_root)
            receipt, resolved_public = _load_dev_session_public_web_package(
                environment="alpha",
                package_root=package_root,
                public_origin="https://alpha.quwoquan.com:17000",
            )
            self.assertEqual(resolved_public, public.resolve())
            self.assertEqual(receipt["environment"], "alpha")
            self.assertEqual(receipt["packageVersion"], "web-release-alpha")
            self.assertEqual(receipt["publicOrigin"], "https://alpha.quwoquan.com")
            self.assertEqual(
                receipt["manifestDigest"],
                "sha256:"
                + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(receipt["contentDigest"], "sha256:" + _tree_sha256(public))

    def test_dev_session_fails_closed_for_missing_current_or_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            with self.assertRaisesRegex(ValueError, "current symlink is missing"):
                _load_dev_session_public_web_package(
                    environment="alpha",
                    package_root=package_root,
                    public_origin="https://alpha.quwoquan.com:17000",
                )

            _, public = self._write_package(package_root)
            (public / "main.dart.js").write_text("drift();", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content digest drifted"):
                _load_dev_session_public_web_package(
                    environment="alpha",
                    package_root=package_root,
                    public_origin="https://alpha.quwoquan.com:17000",
                )

    def test_local_web_host_serves_package_instead_of_falling_through_to_api(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        caddy = (
            repo_root / "quwoquan_ops/environments/gamma/local/Caddyfile"
        ).read_text(encoding="utf-8")
        compose = (
            repo_root
            / "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn("handle @web_api", caddy)
        self.assertIn("root * /srv/web", caddy)
        self.assertIn("try_files {path} /index.html", caddy)
        self.assertIn('Content-Type "text/html; charset=utf-8"', caddy)
        self.assertIn('Content-Type "font/ttf"', caddy)
        self.assertIn("QWQ_PUBLIC_WEB_CONTENT_DIGEST", caddy)
        self.assertIn("LOCAL_GAMMA_PUBLIC_WEB_ROOT", compose)
        self.assertIn(":/srv/web:ro", compose)


if __name__ == "__main__":
    unittest.main()
