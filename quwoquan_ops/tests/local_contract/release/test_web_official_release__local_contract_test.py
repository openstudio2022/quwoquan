# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-005
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from quwoquan_ops.cli.commands.dev_session_public_web import (
    _load_dev_session_public_web_package,
    _resolve_dev_session_public_web_package,
)
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    _inject_noindex,
    _runtime_defines,
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
        public_origin: str = "https://alpha.quwoquan.com:17000",
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
            "assetCacheControl": "no-cache, must-revalidate",
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
            _trusted_web_origin("alpha", "https://alpha.quwoquan.com:17000"),
            "https://alpha.quwoquan.com:17000",
        )
        self.assertEqual(
            _trusted_web_origin("prod", "https://quwoquan.com/"),
            "https://quwoquan.com",
        )
        self.assertEqual(
            _trusted_web_origin("beta", "https://beta.quwoquan.com:18000"),
            "https://beta.quwoquan.com:18000",
        )
        for rejected in (
            "https://alpha.quwoquan.com",
            "https://alpha.quwoquan.com:18000",
            "https://alpha.example.invalid",
            "https://attacker.example",
            "http://alpha.quwoquan.com",
            "https://user@alpha.quwoquan.com:17000",
            "https://alpha.quwoquan.com:17000/path",
            "https://alpha.quwoquan.com:17000?candidate=mutable",
        ):
            with self.assertRaises(WebOfficialReleaseError):
                _trusted_web_origin("alpha", rejected)

    def test_nonprod_runtime_defines_use_exact_test_live_target(self) -> None:
        completed = Mock(returncode=0, stdout='{"APP_RUNTIME_ENV":"beta"}')
        with patch("subprocess.run", return_value=completed) as run:
            values = _runtime_defines(
                Path("/repo"),
                "beta",
                target="beta-local",
                launch_policy="test_live",
            )
        self.assertEqual(values, {"APP_RUNTIME_ENV": "beta"})
        command = run.call_args.args[0]
        self.assertIn("--target", command)
        self.assertEqual(command[command.index("--target") + 1], "beta-local")
        self.assertEqual(
            command[command.index("--launch-policy") + 1],
            "test_live",
        )
        self.assertEqual(
            command[command.index("--launch-mode") + 1],
            "web_official_release",
        )

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
            self.assertEqual(
                receipt["publicOrigin"],
                "https://alpha.quwoquan.com:17000",
            )
            self.assertEqual(
                receipt["manifestDigest"],
                "sha256:"
                + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            )
            self.assertEqual(receipt["contentDigest"], "sha256:" + _tree_sha256(public))

    def test_dev_session_resolves_the_standalone_web_package_root(self) -> None:
        package_root = Path("/deploy/alpha-local/standalone-packages/web/packages/public-web")
        with (
            patch(
                "quwoquan_ops.cli.stackctl.deployment_target_path",
                return_value=package_root,
            ) as target_path,
            patch(
                "quwoquan_ops.cli.commands.dev_session_public_web._load_dev_session_public_web_package",
                return_value=({"environment": "alpha"}, Path("/public")),
            ) as load_package,
        ):
            receipt, public = _resolve_dev_session_public_web_package(
                environment="alpha",
                target="alpha-local",
                target_contract={
                    "publicBases": {
                        "publicWeb": "https://alpha.quwoquan.com:17000",
                    },
                },
            )
        target_path.assert_called_once_with(
            "alpha-local",
            "standalone-packages",
            "web",
            "packages",
            "public-web",
        )
        load_package.assert_called_once_with(
            environment="alpha",
            package_root=package_root,
            public_origin="https://alpha.quwoquan.com:17000",
        )
        self.assertEqual(receipt, {"environment": "alpha"})
        self.assertEqual(public, Path("/public"))

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

    def test_unversioned_web_assets_revalidate_across_package_activation(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        caddy = (
            repo_root / "quwoquan_ops/environments/gamma/local/Caddyfile"
        ).read_text(encoding="utf-8")
        start = caddy.index("@public_web_service_worker")
        end = caddy.index("\n\thandle {\n\t\timport business_api_edge", start)
        public_web = caddy[start:end]

        self.assertIn(
            "path /assets/* /canvaskit/* /icons/* /main.dart.js /flutter.js /flutter_bootstrap.js",
            public_web,
        )
        self.assertIn('Cache-Control "no-cache, must-revalidate"', public_web)
        self.assertIn(
            'Cache-Control "no-cache, no-store, must-revalidate"',
            public_web,
        )
        self.assertNotIn("max-age=31536000", public_web)
        self.assertNotIn("@public_web_immutable_asset", public_web)

    def test_spa_fallback_sets_utf8_and_revalidation_after_rewrite(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        caddy = (
            repo_root / "quwoquan_ops/environments/gamma/local/Caddyfile"
        ).read_text(encoding="utf-8")
        start = caddy.index("\thandle @public_web_app {")
        end = caddy.index("\n\thandle {\n\t\timport business_api_edge", start)
        app_route = caddy[start:end]

        self.assertIn("\n\t\troute {", app_route)
        rewrite = app_route.index("try_files {path} /index.html")
        html_matcher = app_route.index("@public_web_html path /index.html")
        html_headers = app_route.index(
            'Content-Type "text/html; charset=utf-8"'
        )
        file_server = app_route.index("file_server")
        self.assertLess(rewrite, html_matcher)
        self.assertLess(html_matcher, html_headers)
        self.assertLess(html_headers, file_server)
        self.assertIn(
            'Cache-Control "no-cache, must-revalidate"',
            app_route[html_matcher:file_server],
        )


if __name__ == "__main__":
    unittest.main()
