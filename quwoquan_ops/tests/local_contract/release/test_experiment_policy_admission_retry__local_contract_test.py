# spec_ref: specs/feature-tree/platform-ops-governance/spec.md
# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t6
# spec_ref: specs/feature-tree/product-ops-growth/experiment-bucketing-and-rollout/spec.md#sit-001.t7

from __future__ import annotations

import json
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

from quwoquan_ops.cli.lib import experiment_policy_activation as activation


class _PolicyServerState:
    def __init__(
        self,
        *,
        admission_failures: int = 0,
        ordinary_failure: bool = False,
        missing_admission_field: str = "",
        failure_status: int = 0,
        non_json_failure: bool = False,
    ):
        self.admission_failures = admission_failures
        self.ordinary_failure = ordinary_failure
        self.missing_admission_field = missing_admission_field
        self.failure_status = failure_status
        self.non_json_failure = non_json_failure
        self.posts: list[dict[str, Any]] = []
        self.policies: list[dict[str, Any]] = []


class _PolicyHandler(BaseHTTPRequestHandler):
    state: _PolicyServerState

    def log_message(self, _format: str, *args: object) -> None:
        del args

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _write_text(self, status: int, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        body = json.loads(raw)
        self.state.posts.append(
            {
                "body": body,
                "raw": raw,
                "idempotencyKey": self.headers.get("Idempotency-Key"),
            }
        )
        if self.state.failure_status:
            if self.state.non_json_failure:
                self._write_text(
                    self.state.failure_status,
                    b"upstream failure must not be parsed or retried",
                )
            else:
                self._write_json(
                    self.state.failure_status,
                    {
                        "code": "OPS.SYSTEM.command_failed",
                        "nature": "transient",
                        "kind": "internal",
                        "reason": "command_failed",
                    },
                )
            return
        if self.state.ordinary_failure:
            self._write_json(
                503,
                {
                    "code": "OPS.SYSTEM.internal_error",
                    "nature": "transient",
                    "kind": "internal",
                    "reason": "internal_error",
                    "recovery": {
                        "action": "retry",
                        "afterSeconds": 1,
                        "disruptionLevel": "snackbar",
                    },
                },
            )
            return
        if len(self.state.posts) <= self.state.admission_failures:
            admission_payload: dict[str, Any] = {
                "code": "GATEWAY.MIDDLEWARE.upstream_unavailable",
                "origin": "remoteDependency",
                "nature": "transient",
                "userMessage": "服务暂不可用，请稍后重试",
                "debugMessage": "debug_message_redacted",
                "module": "GATEWAY",
                "kind": "unavailable",
                "reason": "upstream_unavailable",
                "location": {
                    "businessObject": "cloud_request",
                    "functionModule": "runtime_errors",
                },
                "context": {
                    "attributes": [
                        {"key": "module", "value": "GATEWAY"},
                        {"key": "reason", "value": "upstream_unavailable"},
                    ]
                },
                "recovery": {
                    "action": "retry",
                    "afterSeconds": 1,
                    "disruptionLevel": "snackbar",
                },
                "requestId": "must-not-enter-receipt",
                "traceId": "must-not-enter-receipt",
            }
            admission_payload.pop(self.state.missing_admission_field, None)
            self._write_json(503, admission_payload)
            return
        created = {**body, "experimentRevision": 1}
        self.state.policies.append(created)
        self._write_json(201, created)

    def do_GET(self) -> None:  # noqa: N802
        self._write_json(200, {"items": self.state.policies})


@contextmanager
def _running_policy_server(
    state: _PolicyServerState,
) -> Iterator[str]:
    handler = type("BoundPolicyHandler", (_PolicyHandler,), {"state": state})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.01},
        daemon=True,
    )
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


class ExperimentPolicyAdmissionRetryLocalContractTest(unittest.TestCase):
    @staticmethod
    def _recipe() -> dict[str, Any]:
        return {
            "id": "search_ranking",
            "key": "search_ranking",
            "status": "running",
            "variants": [
                {"key": "control", "allocationBasisPoints": 5000},
                {"key": "term_heat", "allocationBasisPoints": 5000},
            ],
        }

    def _activate(
        self,
        base_url: str,
        *,
        deadline_seconds: float = 5,
    ) -> dict[str, Any]:
        return activation._activate_one_policy(
            recipe=self._recipe(),
            allow_rollout=False,
            target="alpha-local",
            binding_id="sha256:" + "b" * 64,
            idempotency_prefix="stackctl-test-live",
            product_ops_base_url=base_url,
            token="local-contract-token",
            cafile=None,
            deadline=time.monotonic() + deadline_seconds,
        )

    def test_cold_empty_admission_503_retries_same_create_until_readback(self) -> None:
        state = _PolicyServerState(admission_failures=2)
        with _running_policy_server(state) as base_url:
            result = self._activate(base_url)

        self.assertEqual(result["operation"], "created")
        self.assertEqual(len(state.posts), 3)
        self.assertEqual(len({post["raw"] for post in state.posts}), 1)
        self.assertEqual(
            len({post["idempotencyKey"] for post in state.posts}),
            1,
        )
        self.assertEqual(state.posts[0]["body"], self._recipe())

    def test_ordinary_503_fails_fast_without_retry(self) -> None:
        state = _PolicyServerState(ordinary_failure=True)
        with _running_policy_server(state) as base_url:
            with self.assertRaisesRegex(
                activation.ExperimentPolicyActivationError,
                "HTTP 503",
            ):
                self._activate(base_url)

        self.assertEqual(len(state.posts), 1)

    def test_other_4xx_and_5xx_fail_fast_without_retry(self) -> None:
        for status in (400, 401, 403, 404, 422, 429, 500, 502, 504):
            with self.subTest(status=status):
                state = _PolicyServerState(failure_status=status)
                with _running_policy_server(state) as base_url:
                    with self.assertRaisesRegex(
                        activation.ExperimentPolicyActivationError,
                        f"HTTP {status}",
                    ):
                        self._activate(base_url)
                self.assertEqual(len(state.posts), 1)

    def test_non_json_responses_fail_fast_without_retry(self) -> None:
        for status in (201, 503):
            with self.subTest(status=status):
                state = _PolicyServerState(
                    failure_status=status,
                    non_json_failure=True,
                )
                with _running_policy_server(state) as base_url:
                    with self.assertRaisesRegex(
                        activation.ExperimentPolicyActivationError,
                        f"non-JSON HTTP {status}",
                    ):
                        self._activate(base_url)
                self.assertEqual(len(state.posts), 1)

    def test_admission_503_missing_any_required_field_fails_fast(self) -> None:
        required_fields = (
            "code",
            "origin",
            "nature",
            "userMessage",
            "debugMessage",
            "module",
            "kind",
            "reason",
            "location",
            "context",
            "recovery",
        )
        for field in required_fields:
            with self.subTest(field=field):
                state = _PolicyServerState(
                    admission_failures=100,
                    missing_admission_field=field,
                )
                with _running_policy_server(state) as base_url:
                    with self.assertRaisesRegex(
                        activation.ExperimentPolicyActivationError,
                        "HTTP 503",
                    ):
                        self._activate(base_url, deadline_seconds=0.05)
                self.assertEqual(len(state.posts), 1)

    def test_admission_deadline_preserves_only_safe_typed_fingerprint(self) -> None:
        state = _PolicyServerState(admission_failures=100)
        with _running_policy_server(state) as base_url:
            with self.assertRaises(
                activation.ExperimentPolicyActivationError
            ) as raised:
                self._activate(base_url, deadline_seconds=0.05)

        message = str(raised.exception)
        self.assertIn("HTTP 503", message)
        self.assertIn("GATEWAY.MIDDLEWARE.upstream_unavailable", message)
        self.assertIn('"reason":"upstream_unavailable"', message)
        self.assertIn('"action":"retry"', message)
        self.assertNotIn("must-not-enter-receipt", message)
        self.assertNotIn("requestId", message)
        self.assertNotIn("traceId", message)


if __name__ == "__main__":
    unittest.main()
