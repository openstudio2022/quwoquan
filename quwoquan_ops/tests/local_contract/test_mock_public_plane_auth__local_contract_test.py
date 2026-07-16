from __future__ import annotations

import json
import unittest

from quwoquan_ops.cli.lib.mock_public_plane import MockPublicPlaneHandler


class MockPublicPlaneAuthContractTest(unittest.TestCase):
    def setUp(self) -> None:
        MockPublicPlaneHandler.otp_challenges = {}
        MockPublicPlaneHandler.otp_send_history = {}
        self.handler = MockPublicPlaneHandler.__new__(MockPublicPlaneHandler)

    def _send(self, phone: str = "18013813909", *, now: float = 1000) -> dict[str, object]:
        status, payload, _headers = self.handler._create_otp_challenge(
            {"phone": phone, "deviceId": "device-alpha"},
            now=now,
        )
        self.assertEqual(status, 200)
        return payload

    def _login(
        self,
        code: str,
        *,
        phone: str = "18013813909",
        now: float = 1001,
    ) -> tuple[int, dict[str, object], dict[str, str]]:
        return self.handler._consume_otp_challenge(
            {
                "phone": phone,
                "otpCode": code,
                "agreementVersion": "2026-07-15",
                "privacyVersion": "2026-07-15",
            },
            now=now,
        )

    def test_fixed_code_creates_real_challenge_without_leaking_plaintext(self) -> None:
        payload = self._send()
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("123456", encoded)
        self.assertNotIn("otpCode", encoded)
        self.assertEqual(payload["deliveryStatus"], "delivered")

        status, result, _headers = self._login("123456")
        self.assertEqual(status, 200)
        self.assertTrue(str(result["accessToken"]).startswith("alpha_access_"))
        self.assertNotIn("123456", json.dumps(result, ensure_ascii=False))

        reuse_status, reuse_error, _headers = self._login("123456", now=1002)
        self.assertEqual(reuse_status, 400)
        self.assertEqual(reuse_error["code"], "USER.AUTH.otp_expired")

    def test_wrong_expired_rate_limited_and_locked_states_are_distinct(self) -> None:
        self._send()
        status, error, _headers = self._login("000000")
        self.assertEqual(status, 400)
        self.assertEqual(error["code"], "USER.AUTH.otp_mismatch")

        for attempt in range(MockPublicPlaneHandler.otp_max_failures - 1):
            status, error, _headers = self._login("000000", now=1002 + attempt)
        self.assertEqual(status, 423)
        self.assertEqual(error["code"], "USER.AUTH.login_locked")

        MockPublicPlaneHandler.otp_challenges = {}
        MockPublicPlaneHandler.otp_send_history = {}
        self._send(now=2000)
        expired_status, expired_error, _headers = self._login("123456", now=2301)
        self.assertEqual(expired_status, 400)
        self.assertEqual(expired_error["code"], "USER.AUTH.otp_expired")

        rate_status, rate_error, rate_headers = self.handler._create_otp_challenge(
            {"phone": "18013813909"},
            now=2001,
        )
        self.assertEqual(rate_status, 429)
        self.assertEqual(rate_error["code"], "USER.AUTH.otp_rate_limited")
        self.assertIn("Retry-After", rate_headers)


if __name__ == "__main__":
    unittest.main()
