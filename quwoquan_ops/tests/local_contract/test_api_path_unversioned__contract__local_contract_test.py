"""local_contract: API path 去版本门禁正负例。"""

from __future__ import annotations

import importlib.util
import tempfile
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
        authorities = mod.load_external_provider_path_authorities()
        contract_paths = frozenset(authorities)
        self.assertIn("/v1/chat/completions", contract_paths)
        self.assertIn("/v1/provider/sms/send", contract_paths)
        self.assertIn("/v1/debug/sms/otp/latest", contract_paths)
        self.assertTrue(
            mod.line_is_excluded(
                'CompletionURL: server.URL + "/v1/chat/completions",',
                relative_path=(
                    "quwoquan_service/services/assistant-service/tests/"
                    "local_contract/assistant/assistant_session/"
                    "infrastructure_modelprovider_client__local_contract_test.go"
                ),
                external_provider_authorities=authorities,
            )
        )
        self.assertTrue(
            mod.line_is_excluded(
                'endpoint := apiBaseURL + "/v1/projects/" + projectID',
                relative_path=(
                    "quwoquan_service/services/integration-service/internal/"
                    "external_integration/push_delivery/infrastructure/provider/"
                    "fcm_provider.go"
                ),
            )
        )
        self.assertTrue(
            mod.line_is_excluded(
                'POST /v1/debug/sms/otp/latest 只存在于替代 Provider 内部控制面',
                relative_path=(
                    "specs/feature-tree/user-identity-profile-relationship/"
                    "onboarding-and-identity-entry/"
                    "four-environment-commercial-login-maturity/spec.md"
                ),
                external_provider_authorities=authorities,
            )
        )
        self.assertFalse(
            mod.line_is_excluded(
                'path: "/v1/content/feed"',
                relative_path=(
                    "quwoquan_service/services/content-service/contracts/"
                    "content/post/operations.yaml"
                ),
                external_provider_authorities=authorities,
            )
        )
        self.assertFalse(
            mod.line_is_excluded(
                'path: "/v1/debug/sms/otp/latest/compat"',
                relative_path="quwoquan_ops/cli/lib/local_sms_provider_debug.py",
                external_provider_authorities=authorities,
            )
        )

    def test_first_party_operation_cannot_reuse_registered_provider_path(self) -> None:
        mod = _load_module()
        authorities = mod.load_external_provider_path_authorities()
        line = 'path: "/v1/provider/sms/send"'
        self.assertFalse(
            mod.line_is_excluded(
                line,
                relative_path=(
                    "quwoquan_service/services/user-service/contracts/"
                    "account/user_account/operations.yaml"
                ),
                external_provider_authorities=authorities,
            )
        )
        self.assertIsNotNone(mod.VERSIONED_API.search(line))

        fcm_line = 'path: "/v1/projects/{projectId}/messages:send"'
        self.assertFalse(
            mod.line_is_excluded(
                fcm_line,
                relative_path=(
                    "quwoquan_service/services/integration-service/contracts/"
                    "external_integration/push_delivery/operations.yaml"
                ),
                external_provider_authorities=authorities,
            )
        )
        self.assertIsNotNone(mod.VERSIONED_API.search(fcm_line))

    def test_provider_path_exception_requires_valid_endpoint_contract(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            contract = Path(tmp) / "sms/contract/endpoints.yaml"
            contract.parent.mkdir(parents=True)
            contract.write_text(
                "schema: unsupported\n"
                "role: sms-provider-substitute\n"
                "endpoints:\n"
                "  INTEGRATION_SMS_ENDPOINT:\n"
                "    path: /v1/provider/sms/send\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "unsupported endpoint"):
                mod.load_external_provider_versioned_paths(Path(tmp))

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
