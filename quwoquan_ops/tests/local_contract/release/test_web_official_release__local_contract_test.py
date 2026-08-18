# spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-005
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from quwoquan_ops.cli.lib import web_official_release
from quwoquan_ops.cli.lib.output_paths import PACKAGE_ROOT_OVERRIDE_ENV
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    _inject_noindex,
    _trusted_web_origin,
    _verify_font_manifest,
    _verify_web_build,
)


def _write_minimal_build(root: Path) -> None:
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
    _write_font_manifest(
        root,
        "assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf",
        create_file=True,
    )


def _write_font_manifest(root: Path, asset: str, *, create_file: bool) -> None:
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


class WebOfficialReleaseContractTest(unittest.TestCase):
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
            _write_minimal_build(root)
            _verify_web_build(root)
            _inject_noindex(root / "index.html")
            self.assertIn(
                'content="noindex,nofollow"',
                (root / "index.html").read_text(encoding="utf-8"),
            )

    def test_build_contract_requires_bootstrap_surface_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_minimal_build(root)
            (root / "qwq_bootstrap.js").unlink()
            with self.assertRaisesRegex(
                WebOfficialReleaseError, "bootstrap surface"
            ):
                _verify_web_build(root)

    def test_build_contract_requires_exactly_one_noto_sans_sc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_minimal_build(root)
            extra = root / "assets" / "fonts" / "noto_sans_sc" / "NotoSansSC-extra.ttf"
            extra.parent.mkdir(parents=True, exist_ok=True)
            extra.write_bytes(b"\x00\x01\x00\x00")
            with self.assertRaisesRegex(
                WebOfficialReleaseError, "exactly one bundled Noto Sans SC"
            ):
                _verify_web_build(root)

    # spec: REQ-007 / GWT-006 —— FontManifest 字体 URL 必须 URL-safe 且映射到唯一常规文件
    def test_font_manifest_accepts_url_safe_existing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_font_manifest(
                root,
                "assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf",
                create_file=True,
            )
            _verify_font_manifest(root)

    def test_font_manifest_rejects_url_unsafe_font_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_font_manifest(
                root,
                "assets/fonts/noto_sans_sc/NotoSansSC%5Bwght%5D.ttf",
                create_file=True,
            )
            with self.assertRaisesRegex(WebOfficialReleaseError, "needs URL encoding"):
                _verify_font_manifest(root)

    def test_font_manifest_rejects_missing_font_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_font_manifest(
                root,
                "assets/fonts/noto_sans_sc/NotoSansSC-wght.ttf",
                create_file=False,
            )
            with self.assertRaisesRegex(WebOfficialReleaseError, "missing"):
                _verify_font_manifest(root)

    def test_runtime_defines_reader_ignores_the_standalone_output_override(
        self,
    ) -> None:
        """输出隔离根不得遮蔽输入：app runtime 配置属于已激活的 runtime 候选包。"""
        captured: dict[str, object] = {}

        class _Completed:
            returncode = 0
            stdout = json.dumps({"APP_RUNTIME_ENV": "beta"})
            stderr = ""

        def fake_run(command, **kwargs):  # noqa: ANN001, ANN003
            captured["env"] = dict(kwargs["env"])
            return _Completed()

        with mock.patch.dict(
            os.environ,
            {PACKAGE_ROOT_OVERRIDE_ENV: "/tmp/standalone-packages/web/packages"},
            clear=False,
        ):
            with mock.patch.object(web_official_release.subprocess, "run", fake_run):
                defines = web_official_release._runtime_defines(Path("."), "beta")

        self.assertEqual(defines, {"APP_RUNTIME_ENV": "beta"})
        reader_env = captured["env"]
        assert isinstance(reader_env, dict)
        self.assertNotIn(PACKAGE_ROOT_OVERRIDE_ENV, reader_env)
        # 只剥这一个变量：其余环境（部署工作根、目标选择）仍必须传下去。
        self.assertEqual(reader_env.get("PATH"), os.environ.get("PATH"))


if __name__ == "__main__":
    unittest.main()
