"""灰度路由策略 → Caddy 分流编译的本地契约测试。

覆盖：
- 策略 enabled 且维度非空时，prod 实例 Caddyfile 注入 named matcher + gray upstream；
- gray 实例不注入（防转发环）；
- 策略 disabled 时不注入；
- verify_gray_routing_policy.py 拒绝非法枚举与全空维度启用。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
RENDER_PATH = ROOT / "quwoquan_ops/cli/prod/render_prod_plane_stack.py"
VERIFY_PATH = ROOT / "quwoquan_ops/environments/verify/verify_gray_routing_policy.py"


def _load_render_module():
    spec = importlib.util.spec_from_file_location("render_prod_plane_stack", RENDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GrayRoutingPolicyCompileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.render = _load_render_module()

    def _policy(self, **overrides):
        policy = {
            "enabled": True,
            "grayUpstream": "https://host.containers.internal:28443",
            "grayUpstreamTlsInsecureSkipVerify": True,
            "stageDimensions": {
                "gray-initial": {
                    "appVersions": ["1.2.1"],
                    "userIds": ["user-gray-1"],
                    "provinces": ["330000"],
                    "carriers": ["chinamobile"],
                },
                "carry-on": {
                    "appVersions": ["1.2.1"],
                    "userIds": ["user-gray-1"],
                    "provinces": ["330000"],
                    "carriers": ["chinamobile"],
                },
                "full": {
                    "appVersions": [],
                    "userIds": [],
                    "provinces": [],
                    "carriers": [],
                },
            },
        }
        policy.update(overrides)
        return {"policy": policy}

    def test_enabled_policy_compiles_matchers_for_all_dimensions(self) -> None:
        with patch.object(self.render, "_load_yaml", return_value=self._policy()):
            block = self.render._render_gray_routing_block("gray-initial")
        self.assertIn("@gray_appversions", block)
        self.assertIn("header X-Client-App-Version 1.2.1", block)
        self.assertIn("@gray_userids", block)
        self.assertIn("header X-Client-User-Id user-gray-1", block)
        self.assertIn("@gray_provinces", block)
        self.assertIn("header X-Client-Region-Code 330000", block)
        self.assertIn("@gray_carriers", block)
        self.assertIn("header X-Client-Carrier chinamobile", block)
        self.assertIn("reverse_proxy https://host.containers.internal:28443", block)
        self.assertIn("tls_insecure_skip_verify", block)
        self.assertIn("header_up Host {host}", block)

    def test_disabled_policy_compiles_nothing(self) -> None:
        with patch.object(
            self.render, "_load_yaml", return_value=self._policy(enabled=False)
        ):
            self.assertEqual(self.render._render_gray_routing_block("gray-initial"), "")

    def test_empty_dimension_is_skipped(self) -> None:
        policy = self._policy()
        stage = policy["policy"]["stageDimensions"]["gray-initial"]
        stage["provinces"] = []
        stage["carriers"] = []
        with patch.object(self.render, "_load_yaml", return_value=policy):
            block = self.render._render_gray_routing_block("gray-initial")
        self.assertIn("@gray_appversions", block)
        self.assertNotIn("@gray_provinces", block)
        self.assertNotIn("@gray_carriers", block)

    def test_full_stage_compiles_no_gray_routing(self) -> None:
        with patch.object(self.render, "_load_yaml", return_value=self._policy()):
            self.assertEqual(self.render._render_gray_routing_block("full"), "")

    def test_unknown_stage_fails_closed(self) -> None:
        with patch.object(self.render, "_load_yaml", return_value=self._policy()):
            with self.assertRaises(SystemExit):
                self.render._render_gray_routing_block("unrecognized")

    def test_repo_policy_passes_verify_gate(self) -> None:
        result = subprocess.run(
            [sys.executable, str(VERIFY_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
