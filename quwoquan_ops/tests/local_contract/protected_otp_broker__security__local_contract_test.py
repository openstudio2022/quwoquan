from __future__ import annotations

import json
import urllib.error
import urllib.request
import unittest

from quwoquan_ops.ci.provider_conformance.protected_otp_broker import (
    ProtectedOTPBroker,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import ProtectedDebugOTP


class ProtectedOTPBrokerSecurityTest(unittest.TestCase):
    def test_broker_polls_capture_and_returns_otp_exactly_once(self) -> None:
        calls: list[dict[str, object]] = []

        def reader(**kwargs: object) -> ProtectedDebugOTP:
            calls.append(kwargs)
            if len(calls) == 1:
                raise urllib.error.URLError("not captured")
            return ProtectedDebugOTP(
                request_id="request-1",
                expires_at="2026-08-03T10:05:00Z",
                code="482731",
            )

        broker = ProtectedOTPBroker(
            environment="alpha",
            target_name="alpha-local",
            recipient="+8613800000000",
            reader=reader,
            read_timeout_seconds=2,
        )
        binding = broker.start()
        self.addCleanup(broker.close)
        self.assertNotIn(binding.token, binding.url)
        self.assertNotIn(binding.token, repr(binding))

        request = urllib.request.Request(
            binding.url,
            data=b"",
            method="POST",
            headers={"Authorization": "Bearer " + binding.token},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload, {"code": "482731"})
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(calls[-1]["environment"], "alpha")
        self.assertEqual(calls[-1]["target_name"], "alpha-local")
        self.assertEqual(calls[-1]["recipient"], "+8613800000000")

        with self.assertRaises(urllib.error.HTTPError) as second:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(second.exception.code, 404)

    def test_broker_rejects_wrong_credential_without_reading_capture(self) -> None:
        calls = 0

        def reader(**_kwargs: object) -> ProtectedDebugOTP:
            nonlocal calls
            calls += 1
            raise AssertionError("unauthorized request reached capture")

        broker = ProtectedOTPBroker(
            environment="beta",
            target_name="beta-local",
            recipient="+8613800000001",
            reader=reader,
        )
        binding = broker.start()
        self.addCleanup(broker.close)
        request = urllib.request.Request(
            binding.url,
            data=b"",
            method="POST",
            headers={"Authorization": "Bearer wrong"},
        )
        with self.assertRaises(urllib.error.HTTPError) as rejected:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(rejected.exception.code, 401)
        self.assertEqual(calls, 0)

    def test_prod_and_cross_target_brokers_fail_closed(self) -> None:
        reader = lambda **_kwargs: ProtectedDebugOTP("", "", "123456")
        with self.assertRaisesRegex(ValueError, "Alpha/Beta/Gamma"):
            ProtectedOTPBroker(
                environment="prod",
                target_name="prod-hosted",
                recipient="+8613800000002",
                reader=reader,
            )
        with self.assertRaisesRegex(ValueError, "target/environment"):
            ProtectedOTPBroker(
                environment="alpha",
                target_name="beta-local",
                recipient="+8613800000002",
                reader=reader,
            )


if __name__ == "__main__":
    unittest.main()
