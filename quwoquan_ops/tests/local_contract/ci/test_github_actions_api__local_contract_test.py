from __future__ import annotations

import io
import json
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest import mock

from quwoquan_ops.ci.lib.github_actions_api import (
    GithubActionsApiError,
    load_paginated_items,
    request_json,
)


class _Response(io.BytesIO):
    status = 200
    headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class GithubActionsApiTest(unittest.TestCase):
    def test_terminal_401_fails_without_retry(self) -> None:
        error = urllib.error.HTTPError("url", 401, "no", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error) as urlopen:
            with self.assertRaisesRegex(GithubActionsApiError, "AUTHORITY_HTTP_REJECTED"):
                request_json("https://example.invalid", "token")
        self.assertEqual(urlopen.call_count, 1)

    def test_rate_limit_and_server_failure_retry_then_succeed(self) -> None:
        rate_limit = urllib.error.HTTPError(
            "url",
            429,
            "slow",
            {"Retry-After": "0"},
            None,
        )
        server = urllib.error.HTTPError("url", 503, "down", {}, None)
        response = _Response(json.dumps({"ok": True}).encode("utf-8"))
        with mock.patch(
            "urllib.request.urlopen",
            side_effect=(rate_limit, server, response),
        ):
            payload, stats = request_json(
                "https://example.invalid",
                "token",
                sleep=lambda _seconds: None,
            )
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(stats["requestCount"], 3)
        self.assertEqual(stats["retryCount"], 2)

    def test_retry_budget_exhaustion_fails_closed(self) -> None:
        server = urllib.error.HTTPError("url", 503, "down", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=server) as urlopen:
            with self.assertRaisesRegex(
                GithubActionsApiError, "AUTHORITY_RETRY_EXHAUSTED"
            ):
                request_json(
                    "https://example.invalid",
                    "token",
                    max_attempts=2,
                    sleep=lambda _seconds: None,
                )
        self.assertEqual(urlopen.call_count, 2)

    def test_invalid_json_response_fails_without_retry(self) -> None:
        with mock.patch(
            "urllib.request.urlopen",
            return_value=_Response(b"not-json"),
        ) as urlopen:
            with self.assertRaisesRegex(
                GithubActionsApiError, "AUTHORITY_RESPONSE_INVALID"
            ):
                request_json("https://example.invalid", "token")
        self.assertEqual(urlopen.call_count, 1)

    def test_absolute_deadline_blocks_before_request(self) -> None:
        now = datetime(2026, 8, 26, tzinfo=timezone.utc)
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(
                GithubActionsApiError, "AUTHORITY_DEADLINE_EXCEEDED"
            ):
                request_json(
                    "https://example.invalid",
                    "token",
                    deadline=now - timedelta(seconds=1),
                    now=lambda: now,
                )
        urlopen.assert_not_called()

    def test_pagination_reads_every_page(self) -> None:
        first = {"jobs": [{"id": index} for index in range(100)]}
        second = {"jobs": [{"id": 100}]}
        with mock.patch(
            "quwoquan_ops.ci.lib.github_actions_api.request_json",
            side_effect=((first, {"requestCount": 1, "retryCount": 0, "lastHttpStatus": 200}), (second, {"requestCount": 1, "retryCount": 0, "lastHttpStatus": 200})),
        ) as request:
            items, stats = load_paginated_items(
                "https://example.invalid/jobs",
                "token",
                key="jobs",
            )
        self.assertEqual(len(items), 101)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(stats["requestCount"], 2)


if __name__ == "__main__":
    unittest.main()
