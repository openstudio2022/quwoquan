from __future__ import annotations

import ssl
import unittest
from unittest import mock
from urllib import error

from quwoquan_ops.cli import stackctl


class _Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"status":"ok"}'


class StackctlFetchUrlConnectionRefusedReliabilityLocalContractTest(unittest.TestCase):
    def test_fetch_url__connection_refused__reliability__local_contract(self) -> None:
        with (
            mock.patch.object(
                stackctl.urllib.request,
                "urlopen",
                side_effect=[
                    error.URLError(ConnectionRefusedError("not ready")),
                    _Response(),
                ],
            ) as urlopen,
            mock.patch.object(stackctl.time, "sleep") as sleep,
        ):
            passed, status, body, content_type = stackctl.fetch_url(
                "https://example.test/healthz",
                retry_attempts=2,
            )

        self.assertTrue(passed)
        self.assertEqual(status, 200)
        self.assertEqual(body, '{"status":"ok"}')
        self.assertEqual(content_type, "application/json")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2.0)

    def test_fetch_url_retries_transient_tls_startup_eof(self) -> None:
        with (
            mock.patch.object(
                stackctl.urllib.request,
                "urlopen",
                side_effect=[
                    error.URLError(
                        ssl.SSLError(
                            1,
                            "[SSL: UNEXPECTED_EOF_WHILE_READING] "
                            "EOF occurred in violation of protocol",
                        )
                    ),
                    _Response(),
                ],
            ) as urlopen,
            mock.patch.object(stackctl.time, "sleep") as sleep,
        ):
            passed, status, body, content_type = stackctl.fetch_url(
                "https://example.test/healthz",
                retry_attempts=2,
            )

        self.assertTrue(passed)
        self.assertEqual(status, 200)
        self.assertEqual(body, '{"status":"ok"}')
        self.assertEqual(content_type, "application/json")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2.0)
