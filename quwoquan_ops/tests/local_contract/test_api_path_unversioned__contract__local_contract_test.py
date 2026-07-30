"""local_contract: API path 去版本门禁正负例。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "quwoquan_ops/gate/verify_api_path_unversioned.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_api_path_unversioned", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ApiPathUnversionedContractTest(unittest.TestCase):
    def test_versioned_api_line_is_detected(self) -> None:
        mod = _load_module()
        self.assertIsNotNone(mod.VERSIONED_API.search('path: "/v1/content/feed"'))
        self.assertIsNotNone(mod.VERSIONED_API.search('handle /internal/v1/recommendation/x'))
        self.assertIsNotNone(mod.VERSIONED_API.search('"/callbacks/v1/payments/x"'))
        self.assertIsNone(mod.VERSIONED_API.search('path: "/content/feed"'))
        self.assertIsNone(mod.VERSIONED_API.search('handle /internal/recommendation/x'))

    def test_media_object_key_is_excluded(self) -> None:
        mod = _load_module()
        line = 'url: "media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png"'
        self.assertTrue(mod.line_is_excluded(line))

    def test_immutable_public_media_slice_assertion_is_excluded(self) -> None:
        mod = _load_module()
        self.assertTrue(
            mod.line_is_excluded(
                'issues.append("public fixture 当前唯一 canonical 版本必须是 /v1/")'
            )
        )

    def test_injected_versioned_path_is_rejected(self) -> None:
        mod = _load_module()
        line = 'route := "/v1/content/feed"\n'
        self.assertFalse(mod.line_is_excluded(line))
        self.assertIsNotNone(mod.VERSIONED_API.search(line))

    def test_external_provider_versioned_paths_are_excluded(self) -> None:
        mod = _load_module()
        self.assertTrue(
            mod.line_is_excluded('CompletionURL: server.URL + "/v1/chat/completions",')
        )
        self.assertTrue(
            mod.line_is_excluded('endpoint := apiBaseURL + "/v1/projects/" + projectID')
        )

    def test_negative_route_guard_is_excluded(self) -> None:
        mod = _load_module()
        self.assertTrue(
            mod.line_is_excluded(
                '{method: http.MethodPost, path: "/v1/search", '
                "wantStatus: http.StatusNotFound},"
            )
        )

    def test_generated_routes_have_no_version_segment(self) -> None:
        routes_root = ROOT / "quwoquan_service/services"
        hits: list[str] = []
        for path in routes_root.glob("*/internal/adapters/http/generated_routes.go"):
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if "/v1/" in line or "/internal/v1/" in line or "/callbacks/v1/" in line:
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}:{line.strip()}")
        self.assertEqual(hits, [], msg="generated routes must not retain API version segments")

    def test_content_feed_unversioned_route_exists(self) -> None:
        path = (
            ROOT
            / "quwoquan_service/services/content-service/generated/content/post/transport/routes.g.go"
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn('pathTemplate: "/content/feed"', text)
        self.assertNotIn('pathTemplate: "/v1/content/feed"', text)

    def test_global_contracts_and_observability_are_scanned(self) -> None:
        mod = _load_module()
        self.assertIn("quwoquan_service/contracts", mod.SCAN_ROOTS)
        self.assertIn("quwoquan_ops/observability", mod.SCAN_ROOTS)


if __name__ == "__main__":
    unittest.main()
