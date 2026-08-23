"""Web bootstrap surface 的 local_contract 测试（DEC-005）。

绑定 public-content-web-entry REQ-007/GWT-006：引擎前只允许一个平台实现的
bootstrap surface；loading 为 role=status + aria-live=polite 且无动作；
字体 404/首次离线进入 startupDependencyUnavailable 全屏恢复态，唯一动作是
重新加载；文案与视觉 token 来自设计系统/l10n 生成产物，HTML 不复制品牌字面值。
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = APP_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from web import bootstrap_assets  # noqa: E402

INDEX_HTML = APP_ROOT / "web/index.html"
CSS_ASSET = APP_ROOT / "web/qwq_bootstrap.css"
JS_ASSET = APP_ROOT / "web/qwq_bootstrap.js"
ARB_ZH = APP_ROOT / "lib/l10n/app_zh.arb"


class WebBootstrapSurfaceContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = INDEX_HTML.read_text(encoding="utf-8")
        cls.css = CSS_ASSET.read_text(encoding="utf-8")
        cls.js = JS_ASSET.read_text(encoding="utf-8")

    def test_generated_assets_are_in_sync_with_sources(self) -> None:
        # generator 是唯一实现：安全逻辑与设计系统/ARB 产物必须逐字节同步。
        bootstrap_assets.check()

    def test_index_html_mounts_single_bootstrap_surface(self) -> None:
        self.assertIn('<link rel="stylesheet" href="qwq_bootstrap.css">', self.index)
        self.assertIn('<script src="qwq_bootstrap.js"></script>', self.index)
        self.assertEqual(self.index.count("qwq-bootstrap-surface"), 1)
        self.assertIn('role="status" aria-live="polite"', self.index)
        self.assertIn('role="alert" hidden', self.index)
        self.assertIn('id="qwq-bootstrap-reload"', self.index)
        self.assertIn('type="button"', self.index)

    def test_index_html_does_not_copy_brand_literals(self) -> None:
        # 品牌颜色与恢复文案只存在于生成产物；HTML 不保留第二份。
        body = self.index.split("</head>", 1)[1]
        self.assertNotRegex(body, re.compile(r"#[0-9a-fA-F]{6}"))
        self.assertNotIn("<style>", self.index)
        arb = json.loads(ARB_ZH.read_text(encoding="utf-8"))
        for key in (
            "webBootstrapLoading",
            "webBootstrapUnavailableTitle",
            "webBootstrapReload",
        ):
            self.assertNotIn(arb[key], self.index)

    def test_css_variables_come_from_design_tokens(self) -> None:
        # AppColors.iosGroupedBackgroundLight / brandBlue600 的 canonical 值。
        self.assertIn("--qwq-background: #f2f2f7;", self.css)
        self.assertIn("--qwq-accent: #0a84ff;", self.css)
        self.assertIn("prefers-color-scheme: dark", self.css)
        self.assertIn("GENERATED", self.css)
        # 恢复动作触达面积与焦点可见性。
        self.assertIn("min-height: 44px", self.css)
        self.assertIn("focus-visible", self.css)

    def test_js_carries_l10n_and_recovery_semantics(self) -> None:
        arb = json.loads(ARB_ZH.read_text(encoding="utf-8"))
        for key in (
            "webBootstrapLoading",
            "webBootstrapUnavailableTitle",
            "webBootstrapUnavailableBody",
            "webBootstrapReload",
        ):
            self.assertIn(arb[key], self.js)
        self.assertIn("flutter-first-frame", self.js)
        self.assertIn("location.reload()", self.js)
        # 字体与引擎关键资源失败必须进入恢复态，不允许静默 tofu。
        self.assertIn("FontManifest", self.js)
        self.assertIn(r"\.ttf", self.js)
        self.assertIn("GENERATED", self.js)

    def test_loading_state_has_no_actions(self) -> None:
        loading = self.index.split('id="qwq-bootstrap-loading"', 1)[1].split(
            'id="qwq-bootstrap-recovery"', 1
        )[0]
        self.assertNotIn("<button", loading)
        self.assertNotIn("<a ", loading)

    def test_runtime_config_is_verified_before_flutter_engine_load(self) -> None:
        bootstrap = (APP_ROOT / "web/flutter_bootstrap.js").read_text(encoding="utf-8")
        self.assertIn('RUNTIME_CONFIG_TRUST_PATH = "/runtime-config-trust.json"', self.js)
        self.assertIn('RUNTIME_CONFIG_PACKAGE_PATH = "/runtime-config-package.json"', self.js)
        self.assertIn('cache: "no-store"', self.js)
        self.assertIn('credentials: "same-origin"', self.js)
        self.assertIn("fetchJson(RUNTIME_CONFIG_TRUST_PATH", self.js)
        self.assertIn("RUNTIME_CONFIG_PACKAGE_PATH,\n      \"package\"", self.js)
        self.assertIn('TRUST_SCHEMA = "app-runtime-config-trust"', self.js)
        self.assertIn('PACKAGE_SCHEMA = "app-runtime-config-package"', self.js)
        self.assertIn('EXPECTED_SCHEMA_VERSION = "1"', self.js)
        self.assertIn('signatureAlgorithm !== "ed25519"', self.js)
        self.assertIn('new URL(path, window.location.href)', self.js)
        self.assertIn('url.origin !== window.location.origin', self.js)
        self.assertNotIn('RUNTIME_CONFIG_TRUST_PATH = "runtime-config-trust.json"', self.js)
        self.assertNotIn('RUNTIME_CONFIG_PACKAGE_PATH = "runtime-config-package.json"', self.js)
        self.assertIn('crypto.subtle.verify(', self.js)
        self.assertIn('{ name: "Ed25519" }', self.js)
        self.assertIn("runtime-payload-digest-invalid", self.js)
        self.assertIn("runtime-freshness-invalid", self.js)
        self.assertIn("runtime-signature-key-untrusted", self.js)
        self.assertIn("runtime-trust-profile-mismatch", self.js)
        self.assertIn("window.__qwqRuntimeConfigReady.then(startFlutter)", bootstrap)
        self.assertIn("payload.payloadDigest = \"\"", self.js)
        self.assertIn("trustEnvelope.trustedPublicKeys", self.js)
        self.assertIn("packageValue.trustedPublicKeys", self.js)
        self.assertIn("runtime-trust-keyring-invalid", self.js)
        for rejected_url_component in (
            "url.username",
            "url.password",
            "url.search",
            "url.hash",
        ):
            self.assertIn(rejected_url_component, self.js)
        self.assertIn("canonicalTimestamp.test(packageValue.issuedAt)", self.js)
        self.assertIn("canonicalTimestamp.test(packageValue.expiresAt)", self.js)
        self.assertIn("packageValue.buildProfile !== trustEnvelope.buildProfile", self.js)
        self.assertIn("window.__qwqReadRuntimeConfigPackage", self.js)
        self.assertIn("JSON.stringify(packageValue)", self.js)
        self.assertNotIn("JSON.stringify(envelope)", self.js)
        for retired in (
            '"package",\n    "trustedBuildProfile"',
            '"trustedTarget"',
            "trustEnvelope.package",
            "trustEnvelope.trustedBuildProfile",
            "trustEnvelope.trustedTarget",
        ):
            self.assertNotIn(retired, self.js)
        self.assertLess(
            bootstrap.index("window.__qwqRuntimeConfigReady.then(startFlutter)"),
            bootstrap.index(".catch(function (error)"),
        )
        self.assertNotIn("String.fromEnvironment", bootstrap)
        self.assertNotIn("APP_RUNTIME_ENV", bootstrap)

    def test_config_failure_has_distinct_surface_and_copy(self) -> None:
        self.assertIn('id="qwq-bootstrap-config-error"', self.index)
        self.assertIn('id="qwq-bootstrap-config-code"', self.index)
        self.assertIn("应用配置不可用", self.js)
        self.assertIn("当前站点的启动配置缺失、已过期或未通过安全校验", self.js)
        self.assertIn("window.__qwqShowRuntimeConfigError", self.js)
        self.assertNotIn(
            'window.__qwqShowRuntimeConfigError = showRecovery',
            self.js,
        )

    def test_web_bundle_has_no_environment_or_endpoint_defaults(self) -> None:
        joined = self.index + self.js + (APP_ROOT / "web/flutter_bootstrap.js").read_text(
            encoding="utf-8"
        )
        self.assertNotRegex(joined, re.compile(r"https://(?:api|cdn|rtc)\\."))
        self.assertNotIn("APP_RUNTIME_ENV", joined)
        self.assertNotIn('environment = "alpha"', joined)
        self.assertNotIn('environment = "prod"', joined)
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage.setItem(\"qwq-runtime", self.js)


if __name__ == "__main__":
    unittest.main()
