from __future__ import annotations

import base64
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import socket
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import unittest
from unittest import mock

from quwoquan_ops.ci.provider_conformance import protected_otp_broker as subject
from quwoquan_ops.ci.provider_conformance.protected_otp_broker import (
    ProtectedOTPBroker,
)
from quwoquan_ops.ci.provider_conformance.run_sms_local_capture_api_integration import (
    _issue_ephemeral_tls,
)
from quwoquan_ops.cli.lib.local_provider_substitute_tls import (
    LocalProviderSubstituteTls,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import ProtectedDebugOTP


@contextmanager
def _started_https_broker(broker: ProtectedOTPBroker):
    with tempfile.TemporaryDirectory(prefix="qwq-otp-broker-test-") as temporary:
        ca_path, certificate_path, private_key_path = _issue_ephemeral_tls(
            Path(temporary)
        )
        tls = LocalProviderSubstituteTls(
            certificate_path=certificate_path,
            private_key_path=private_key_path,
            ca_path=ca_path,
        )
        with mock.patch.object(
            subject,
            "prepare_local_provider_substitute_tls",
            return_value=tls,
        ) as prepare:
            binding = broker.start()
        prepare.assert_called_once_with(
            broker._target_name,  # noqa: SLF001 - exact managed-CA scope contract
            role="protected-otp-broker",
        )
        try:
            yield binding, ssl.create_default_context(cafile=str(ca_path)), tls
        finally:
            broker.close()


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
        with _started_https_broker(broker) as (binding, context, tls):
            self.assertTrue(binding.url.startswith("https://127.0.0.1:"))
            self.assertEqual(binding.ca_digest, subject._sha256_file(tls.ca_path))
            self.assertEqual(
                binding.certificate_digest,
                subject._sha256_file(tls.certificate_path),
            )
            self.assertEqual(
                base64.b64decode(binding.ca_certificate_base64, validate=True),
                tls.ca_path.read_bytes(),
            )
            self.assertNotIn(binding.token, binding.url)
            self.assertNotIn(binding.token, repr(binding))
            self.assertNotIn(binding.ca_certificate_base64, repr(binding))

            parsed = urllib.parse.urlparse(binding.url)
            with socket.create_connection(
                (str(parsed.hostname), int(parsed.port or 0)),
                timeout=3,
            ) as raw_socket:
                with context.wrap_socket(
                    raw_socket,
                    server_hostname=parsed.hostname,
                ) as tls_socket:
                    self.assertEqual(tls_socket.version(), "TLSv1.3")

            request = urllib.request.Request(
                binding.url,
                data=b"",
                method="POST",
                headers={"Authorization": "Bearer " + binding.token},
            )
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                with urllib.request.urlopen(
                    request,
                    timeout=3,
                    context=context,
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload, {"code": "482731"})
            self.assertNotIn("482731", output.getvalue())
            self.assertNotIn(binding.token, output.getvalue())
            self.assertGreaterEqual(len(calls), 2)
            self.assertEqual(calls[-1]["environment"], "alpha")
            self.assertEqual(calls[-1]["target_name"], "alpha-local")
            self.assertEqual(calls[-1]["recipient"], "+8613800000000")

            with self.assertRaises(urllib.error.HTTPError) as second:
                urllib.request.urlopen(request, timeout=3, context=context)
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
        with _started_https_broker(broker) as (binding, context, _tls):
            request = urllib.request.Request(
                binding.url,
                data=b"",
                method="POST",
                headers={"Authorization": "Bearer wrong"},
            )
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(request, timeout=3, context=context)
            self.assertEqual(rejected.exception.code, 401)
            self.assertEqual(calls, 0)

    def test_dual_platform_broker_consumes_one_fresh_capture_per_device(self) -> None:
        codes = iter(("482731", "615204"))

        def reader(**_kwargs: object) -> ProtectedDebugOTP:
            code = next(codes)
            return ProtectedDebugOTP(
                request_id="request-" + code,
                expires_at="2026-08-03T10:05:00Z",
                code=code,
            )

        broker = ProtectedOTPBroker(
            environment="alpha",
            target_name="alpha-local",
            recipient="+8613800000000",
            reader=reader,
            max_consumptions=2,
        )
        with _started_https_broker(broker) as (binding, context, _tls):
            request = urllib.request.Request(
                binding.url,
                data=b"",
                method="POST",
                headers={"Authorization": "Bearer " + binding.token},
            )
            for expected in ("482731", "615204"):
                with urllib.request.urlopen(
                    request,
                    timeout=3,
                    context=context,
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(payload, {"code": expected})

            with self.assertRaises(urllib.error.HTTPError) as exhausted:
                urllib.request.urlopen(request, timeout=3, context=context)
            self.assertEqual(exhausted.exception.code, 404)

    def test_broker_rejects_unbounded_device_consumption(self) -> None:
        reader = lambda **_kwargs: ProtectedDebugOTP("", "", "123456")
        with self.assertRaisesRegex(ValueError, "one or two"):
            ProtectedOTPBroker(
                environment="alpha",
                target_name="alpha-local",
                recipient="+8613800000000",
                reader=reader,
                max_consumptions=3,
            )

    def test_broker_rejects_cleartext_and_untrusted_tls(self) -> None:
        calls = 0

        def reader(**_kwargs: object) -> ProtectedDebugOTP:
            nonlocal calls
            calls += 1
            return ProtectedDebugOTP("request", "expiry", "123456")

        broker = ProtectedOTPBroker(
            environment="gamma",
            target_name="gamma-local",
            recipient="+8613800000002",
            reader=reader,
        )
        with _started_https_broker(broker) as (binding, _context, _tls):
            cleartext = urllib.request.Request(
                binding.url.replace("https://", "http://", 1),
                data=b"",
                method="POST",
                headers={"Authorization": "Bearer " + binding.token},
            )
            with self.assertRaises((OSError, urllib.error.URLError)):
                urllib.request.urlopen(cleartext, timeout=3)

            protected = urllib.request.Request(
                binding.url,
                data=b"",
                method="POST",
                headers={"Authorization": "Bearer " + binding.token},
            )
            with self.assertRaises(urllib.error.URLError):
                urllib.request.urlopen(
                    protected,
                    timeout=3,
                    context=ssl.create_default_context(),
                )
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
