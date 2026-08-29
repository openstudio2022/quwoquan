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
    ACTIVE_POINTER_NAME,
    ACTIVE_POINTER_SCHEMA,
    WEB_RUNTIME_CONFIG_FILENAMES,
    WebOfficialReleaseError,
    _tree_sha256,
    _trusted_web_origin,
    _verify_font_manifest,
    _verify_web_build,
    _web_build_command,
    materialize_web_runtime_config,
    package_web_official_release,
    validate_web_official_artifact,
)


class WebOfficialReleaseContractTest(unittest.TestCase):
    def _write_package(
        self,
        package_root: Path,
        *,
        environment: str = "alpha",
        public_origin: str = "https://alpha.quwoquan.com:17000",
        with_active_pointer: bool = True,
    ) -> tuple[Path, Path]:
        release_id = f"web-release-{environment}"
        release_root = package_root / release_id
        public = release_root / "public"
        public.mkdir(parents=True)
        self._write_font_manifest(
            public,
            "assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf",
            create_file=True,
        )
        (public / "qwq_bootstrap.css").write_text(":root{}", encoding="utf-8")
        (public / "qwq_bootstrap.js").write_text("(function(){})();", encoding="utf-8")
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
        if with_active_pointer:
            (package_root / ACTIVE_POINTER_NAME).write_text(
                json.dumps(
                    {
                        "schema": ACTIVE_POINTER_SCHEMA,
                        "environment": environment,
                        "publicOrigin": public_origin,
                        "releaseId": release_id,
                        "contentSHA256": manifest["contentSHA256"],
                        "manifestSHA256": "sha256:"
                        + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
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

    def test_web_build_command_is_environment_agnostic(self) -> None:
        command = _web_build_command("/toolchain/flutter", Path("/output/public"))

        self.assertEqual(
            command,
            [
                "/toolchain/flutter",
                "build",
                "web",
                "--release",
                "--pwa-strategy=offline-first",
                "--output=/output/public",
            ],
        )
        self.assertFalse(any(value.startswith("--dart-define") for value in command))

    def _write_minimal_build(self, root: Path) -> None:
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
            json.dumps({"display": "standalone", "start_url": "/", "scope": "/"}),
            encoding="utf-8",
        )
        # 引擎前 bootstrap surface 产物（DEC-005）是构建完整性的一部分。
        (root / "qwq_bootstrap.css").write_text(":root{}", encoding="utf-8")
        (root / "qwq_bootstrap.js").write_text("(function(){})();", encoding="utf-8")
        # 夹具用 pubspec 声明的真实字体名。写成百分号编码的文件名会把「产物已 URL-safe」
        # 这件事伪装掉，REQ-007 要的恰好是解码后的名字本身不需要编码。
        self._write_font_manifest(
            root,
            "assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf",
            create_file=True,
        )

    def _write_font_manifest(self, root: Path, asset: str, *, create_file: bool) -> None:
        assets_root = root / "assets"
        assets_root.mkdir(parents=True, exist_ok=True)
        (assets_root / "FontManifest.json").write_text(
            json.dumps([{"family": "Noto Sans SC", "fonts": [{"asset": asset}]}]),
            encoding="utf-8",
        )
        if create_file:
            font_path = assets_root / asset
            font_path.parent.mkdir(parents=True, exist_ok=True)
            font_path.write_bytes(b"\x00\x01\x00\x00")

    def test_build_contract_requires_utf8_pwa_and_service_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_build(root)
            validate_web_official_artifact(root)
            self.assertNotIn(
                'content="noindex,nofollow"',
                (root / "index.html").read_text(encoding="utf-8"),
            )

    def test_all_environments_package_identical_public_bytes(self) -> None:
        origins = {
            "alpha": "https://alpha.quwoquan.com:17000",
            "beta": "https://beta.quwoquan.com:18000",
            "gamma": "https://gamma.quwoquan.com:19000",
            "prod": "https://quwoquan.com",
        }
        commands: list[list[str]] = []

        def compile_web(command: list[str], **_: object) -> Mock:
            commands.append(command)
            output = next(
                value.removeprefix("--output=")
                for value in command
                if value.startswith("--output=")
            )
            build_root = Path(output)
            build_root.mkdir(parents=True)
            self._write_minimal_build(build_root)
            return Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch("shutil.which", return_value="/toolchain/flutter"),
                patch("subprocess.run", side_effect=compile_web),
            ):
                releases = {
                    environment: package_web_official_release(
                        repo_root=Path("/repo"),
                        environment=environment,
                        target=f"{environment}-local"
                        if environment != "prod"
                        else "prod-hosted",
                        package_root=root / environment,
                        public_origin=origin,
                    )
                    for environment, origin in origins.items()
                }

            self.assertEqual(
                len({str(release["contentSHA256"]) for release in releases.values()}),
                1,
            )
            self.assertEqual(
                len({str(release["releaseId"]) for release in releases.values()}),
                1,
            )
            for environment, release in releases.items():
                index = (
                    Path(str(release["releasePath"])) / "public/index.html"
                ).read_text(encoding="utf-8")
                self.assertNotIn('content="noindex,nofollow"', index)
                self.assertEqual(release["noindex"], environment != "prod")

        normalized_commands = {
            tuple(value for value in command if not value.startswith("--output="))
            for command in commands
        }
        self.assertEqual(len(normalized_commands), 1)
        self.assertFalse(
            any(
                value.startswith("--dart-define")
                for command in commands
                for value in command
            )
        )

    def test_build_contract_requires_bootstrap_surface_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_build(root)
            (root / "qwq_bootstrap.js").unlink()
            with self.assertRaisesRegex(WebOfficialReleaseError, "bootstrap surface"):
                _verify_web_build(root)

    def test_shared_artifact_rejects_hosting_runtime_config_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_build(root)
            for filename in WEB_RUNTIME_CONFIG_FILENAMES:
                (root / filename).write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(
                WebOfficialReleaseError,
                "must not contain hosting runtime configuration",
            ):
                validate_web_official_artifact(root)

    def test_build_contract_requires_exactly_one_noto_sans_sc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_build(root)
            extra = root / "assets/fonts/noto_sans_sc/NotoSansSC-extra.ttf"
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_bytes(b"\x00\x01\x00\x00")
            with self.assertRaisesRegex(
                WebOfficialReleaseError, "exactly one bundled Noto Sans SC"
            ):
                _verify_web_build(root)

    # spec: REQ-007 —— FontManifest 字体 URL 必须 URL-safe 且映射到产物内唯一常规文件
    def test_font_manifest_accepts_url_safe_existing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_build(root)
            _verify_font_manifest(root)

    def test_font_manifest_rejects_url_unsafe_font_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_build(root)
            # 静态服务器先对 URL 解码再查磁盘：方括号解码后仍需编码，线上必然 404。
            self._write_font_manifest(
                root,
                "assets/fonts/noto_sans_sc/NotoSansSC[wght].ttf",
                create_file=True,
            )
            with self.assertRaisesRegex(
                WebOfficialReleaseError, "needs URL encoding"
            ):
                _verify_font_manifest(root)

    def test_font_manifest_rejects_missing_font_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_build(root)
            self._write_font_manifest(
                root,
                "assets/fonts/noto_sans_sc/NotoSansSC-absent.ttf",
                create_file=False,
            )
            with self.assertRaisesRegex(WebOfficialReleaseError, "is missing"):
                _verify_font_manifest(root)

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

    def test_dev_session_rejects_runtime_config_inside_immutable_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            _, public = self._write_package(package_root)
            (public / WEB_RUNTIME_CONFIG_FILENAMES[0]).write_text(
                "{}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ValueError,
                "must not contain hosting runtime configuration",
            ):
                _load_dev_session_public_web_package(
                    environment="alpha",
                    package_root=package_root,
                    public_origin="https://alpha.quwoquan.com:17000",
                )

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

    def test_dev_session_fails_closed_for_missing_pointer_or_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            with self.assertRaisesRegex(
                ValueError, "active release pointer is missing"
            ):
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

    def test_hosting_composition_materializes_config_and_binds_digests(self) -> None:
        from quwoquan_app.test.support.runtime.launcher.launcher_package_fixture import (
            temporary_launcher_package,
        )

        for environment, target in (
            ("alpha", "alpha-local"),
            ("beta", "beta-local"),
            ("gamma", "gamma-local"),
            ("prod", "prod-hosted"),
        ):
            with (
                self.subTest(environment=environment),
                temporary_launcher_package(environment, target) as fixture,
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                digests = materialize_web_runtime_config(
                    hosting_root=root,
                    trust_envelope=fixture.runtime_config_trust_envelope,
                    runtime_package=fixture.runtime_config_package,
                    expected_environment=environment,
                    expected_target=target,
                )
                self.assertEqual(
                    set(digests),
                    {
                        *WEB_RUNTIME_CONFIG_FILENAMES,
                        "runtimeConfigTrustEnvelopeDigest",
                        "runtimeConfigPackageDigest",
                    },
                )
                self.assertRegex(
                    digests["runtimeConfigTrustEnvelopeDigest"],
                    r"^sha256:[0-9a-f]{64}$",
                )
                self.assertRegex(
                    digests["runtimeConfigPackageDigest"],
                    r"^sha256:[0-9a-f]{64}$",
                )
                for filename in WEB_RUNTIME_CONFIG_FILENAMES:
                    payload = (root / filename).read_bytes()
                    self.assertEqual(
                        digests[filename],
                        "sha256:" + hashlib.sha256(payload).hexdigest(),
                    )

    def test_hosting_composition_requires_matching_environment(self) -> None:
        from quwoquan_app.test.support.runtime.launcher.launcher_package_fixture import (
            temporary_launcher_package,
        )

        with (
            temporary_launcher_package("alpha", "alpha-local") as fixture,
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(
                WebOfficialReleaseError,
                "does not match its composition",
            ),
        ):
            materialize_web_runtime_config(
                hosting_root=Path(directory),
                trust_envelope=fixture.runtime_config_trust_envelope,
                runtime_package=fixture.runtime_config_package,
                expected_environment="gamma",
                expected_target="gamma-local",
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
        self.assertIn(
            'X-Robots-Tag "noindex, nofollow"',
            app_route[html_matcher:file_server],
        )

    def test_web_compilation_entries_are_environment_agnostic(self) -> None:
        repo_root = Path(__file__).resolve().parents[4]
        runtime_writer = (
            repo_root / "quwoquan_ops/cli/lib/web_official_release.py"
        ).read_text(encoding="utf-8")
        product_writer = (
            repo_root / "quwoquan_ops/cli/commands/package_app_artifact.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(runtime_writer.count("def _web_build_command("), 1)
        self.assertNotIn("--dart-define", runtime_writer)
        web_product_start = product_writer.index(
            'web_output = app_dir / "build/web-shared"'
        )
        web_product_end = product_writer.index(
            "required_web_outputs = (", web_product_start
        )
        web_product_command = product_writer[web_product_start:web_product_end]
        self.assertIn("flutter_executable,", web_product_command)
        self.assertIn('"web",', web_product_command)
        self.assertNotIn("--dart-define", web_product_command)
        for forbidden in (
            "APP_RUNTIME_ENV",
            "CLOUD_GATEWAY_BASE_URL",
            "PUBLIC_WEB_BASE_URL",
            "public_origin",
        ):
            self.assertNotIn(forbidden, web_product_command)

    def test_prod_hosting_render_requires_external_runtime_inputs(self) -> None:
        package_inputs = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_ops/cli/prod/render_prod_plane_stack_lib/package_inputs.py"
        ).read_text(encoding="utf-8")
        writer = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_ops/cli/prod/render_prod_plane_stack_lib/render_entry.py"
        ).read_text(encoding="utf-8")
        deploy = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_ops/cli/prod/deploy_to_prod.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("--web-runtime-config-trust", package_inputs)
        self.assertIn("--web-runtime-config-package", package_inputs)
        self.assertIn('"gamma-proxy" in support', writer)
        self.assertIn("prod Web hosting runtime configuration is required", writer)
        self.assertIn("materialize_web_runtime_config(", writer)
        self.assertIn('expected_environment="prod"', writer)
        self.assertIn('expected_target="prod-hosted"', writer)
        self.assertIn("QWQ_WEB_RUNTIME_CONFIG_TRUST_PATH", deploy)
        self.assertIn("QWQ_WEB_RUNTIME_CONFIG_PACKAGE_PATH", deploy)
        self.assertIn('--web-runtime-config-trust "$QWQ_WEB_RUNTIME_CONFIG_TRUST_PATH"', deploy)
        self.assertIn('--web-runtime-config-package "$QWQ_WEB_RUNTIME_CONFIG_PACKAGE_PATH"', deploy)
        self.assertNotIn("request.headers", writer)
        self.assertNotIn("X-Environment", writer)

    def test_prod_web_host_never_applies_nonprod_noindex_policy(self) -> None:
        from quwoquan_ops.cli.prod import render_prod_plane_stack as render

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            render._write_caddyfile(output, "prod")
            caddy = (output / "runtime" / "Caddyfile").read_text(encoding="utf-8")

        web_start = caddy.index("\nquwoquan.com {")
        self.assertNotIn("X-Robots-Tag", caddy[web_start:])

    def test_writer_emits_exact_pointer_and_demotes_current(self) -> None:
        writer = (
            Path(__file__).resolve().parents[4]
            / "quwoquan_ops/cli/lib/web_official_release.py"
        ).read_text(encoding="utf-8")

        pointer = writer.index("ACTIVE_POINTER_NAME")
        current = writer.index('current = package_root / "current"')
        self.assertLess(pointer, current)
        self.assertIn('"manifestSHA256": manifest_sha256', writer)
        self.assertIn('"activePath": str(active_path)', writer)

    def test_dev_session_binds_the_exact_active_release_not_current(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            manifest_path, public = self._write_package(
                package_root,
                with_active_pointer=True,
            )
            receipt, resolved_public = _load_dev_session_public_web_package(
                environment="alpha",
                package_root=package_root,
                public_origin="https://alpha.quwoquan.com:17000",
            )
            self.assertEqual(resolved_public, public.resolve())
            self.assertEqual(receipt["packageVersion"], "web-release-alpha")
            self.assertEqual(
                receipt["manifestDigest"],
                "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            )

            # current 只是兼容投影：它指向别的 release 时必须失败，
            # 不允许静默按 current 提供服务。
            (package_root / "current").unlink()
            (package_root / "current").symlink_to(
                "web-release-other",
                target_is_directory=True,
            )
            with self.assertRaisesRegex(ValueError, "contradicts the active release"):
                _load_dev_session_public_web_package(
                    environment="alpha",
                    package_root=package_root,
                    public_origin="https://alpha.quwoquan.com:17000",
                )

    def test_dev_session_never_falls_back_to_current_for_identity(self) -> None:
        """指针缺席时即使 current 完好也必须失败：身份不得从 current 反推。"""

        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            self._write_package(package_root, with_active_pointer=False)
            self.assertTrue((package_root / "current").is_symlink())
            with self.assertRaisesRegex(
                ValueError, "active release pointer is missing"
            ):
                _load_dev_session_public_web_package(
                    environment="alpha",
                    package_root=package_root,
                    public_origin="https://alpha.quwoquan.com:17000",
                )

    def test_dev_session_fails_closed_on_pointer_and_manifest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            manifest_path, _ = self._write_package(
                package_root,
                with_active_pointer=True,
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assetCacheControl"] = "max-age=31536000"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "manifest digest drifted"):
                _load_dev_session_public_web_package(
                    environment="alpha",
                    package_root=package_root,
                    public_origin="https://alpha.quwoquan.com:17000",
                )

        with tempfile.TemporaryDirectory() as directory:
            package_root = Path(directory)
            self._write_package(package_root, with_active_pointer=True)
            (package_root / ACTIVE_POINTER_NAME).write_text(
                json.dumps({"schema": ACTIVE_POINTER_SCHEMA}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "pointer does not match"):
                _load_dev_session_public_web_package(
                    environment="alpha",
                    package_root=package_root,
                    public_origin="https://alpha.quwoquan.com:17000",
                )


if __name__ == "__main__":
    unittest.main()
