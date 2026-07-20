from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from quwoquan_ops.cli.lib.mock_public_plane import MockPublicPlaneHandler


class AlphaAuthPublicPlaneApiIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        MockPublicPlaneHandler.mode = "api"
        MockPublicPlaneHandler.runtime_env = "alpha"
        MockPublicPlaneHandler.otp_challenges = {}
        MockPublicPlaneHandler.otp_send_history = {}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MockPublicPlaneHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def _post(self, path: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def _get(self, path: str) -> tuple[int, dict[str, object]]:
        with urllib.request.urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_homepage_search_has_alpha_mock_contract_projection(self) -> None:
        status, payload = self._get("/homepages/search?query=%E8%A5%BF%E6%B9%96&limit=1")

        self.assertEqual(status, 200)
        self.assertEqual(payload["items"], [])
        self.assertTrue(payload["mockBoundary"])

    def test_global_search_has_canonical_alpha_mock_projection(self) -> None:
        status, payload = self._post(
            "/search",
            {"query": "西湖", "mode": "result", "limit": 1},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["hits"], [])
        self.assertTrue(payload["requestId"])
        self.assertTrue(payload["rankingVersion"])
        self.assertTrue(payload["mockBoundary"])

    def test_bare_alpha_send_and_login_routes_are_json_and_metadata_aligned(self) -> None:
        send_status, send_payload = self._post(
            "/auth/otp/send",
            {"phone": "18013813909", "deviceId": "alpha-device", "platform": "ios"},
        )
        self.assertEqual(send_status, 200)
        self.assertIn("challengeId", send_payload)
        self.assertNotIn("123456", json.dumps(send_payload))

        login_status, login_payload = self._post(
            "/auth/login/phone",
            {
                "phone": "18013813909",
                "otpCode": "123456",
                "agreementVersion": "2026-07-15",
                "privacyVersion": "2026-07-15",
                "deviceId": "alpha-device",
                "platform": "ios",
            },
        )
        self.assertEqual(login_status, 200)
        self.assertIn("accessToken", login_payload)
        self.assertEqual(login_payload["identityOrigin"], "phone")

    def test_wrong_code_returns_json_error_instead_of_html_404(self) -> None:
        self._post("/auth/otp/send", {"phone": "13900000000"})
        status, payload = self._post(
            "/auth/login/phone",
            {
                "phone": "13900000000",
                "otpCode": "000000",
                "agreementVersion": "v1",
                "privacyVersion": "v1",
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["code"], "USER.AUTH.otp_mismatch")
        self.assertNotIn("mock route is not ready", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
