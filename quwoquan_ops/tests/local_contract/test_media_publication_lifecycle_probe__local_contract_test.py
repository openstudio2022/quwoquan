from __future__ import annotations

import http.server
import importlib.util
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
PROBE_PATH = (
    ROOT
    / "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "content-service/smoke/run_media_publication_lifecycle_probe.py"
)
SMOKE_DIR = PROBE_PATH.parent
if str(SMOKE_DIR) not in sys.path:
    sys.path.insert(0, str(SMOKE_DIR))

import report_feedback_probe_support as probe_support

SPEC = importlib.util.spec_from_file_location(
    "media_publication_lifecycle_probe_test",
    PROBE_PATH,
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load media publication lifecycle probe")
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


class _PublicationClient:
    def __init__(self) -> None:
        self.publication_bodies: list[dict[str, object]] = []

    def request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> tuple[int, dict[str, object]]:
        if method == "POST" and path == "/content/posts:publish":
            body = kwargs["body"]
            assert isinstance(body, dict)
            self.publication_bodies.append(body)
            visibility = str(body["visibility"])
            return 200, {
                "data": {
                    "postId": f"post-{visibility}",
                    "state": "pending_review",
                }
            }
        if method == "GET" and path.startswith("/content/posts/"):
            post_id = path.rsplit("/", 1)[-1]
            return 200, {
                "data": {
                    "id": post_id,
                    "status": "pending_review",
                    "moderationStatus": "pending",
                    "visibility": post_id.removeprefix("post-"),
                    "mediaItems": [{"kind": "image"}],
                    "mediaUrls": ["https://cdn.example/image"],
                    "coverUrl": "https://cdn.example/image",
                }
            }
        raise AssertionError(f"unexpected request: {method} {path}")


class _CoverClient:
    def __init__(self) -> None:
        self.calls = 0

    def request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> tuple[int, dict[str, object]]:
        self.calls += 1
        if self.calls == 1:
            return 400, {
                "error": {"code": "CONTENT.USER.media_not_ready"}
            }
        return 200, {
            "data": {
                "mediaId": "asset-video",
                "coverStrategy": "first_frame",
                "coverUrl": "https://cdn.example/video-cover",
            }
        }


class _PendingPostClient:
    def __init__(self) -> None:
        self.calls = 0

    def request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> tuple[int, dict[str, object]]:
        del kwargs
        if method != "GET" or path != "/content/posts/post-pending":
            raise AssertionError(f"unexpected request: {method} {path}")
        self.calls += 1
        published = self.calls > 1
        return 200, {
            "data": {
                "id": "post-pending",
                "status": "published" if published else "pending_review",
                "moderationStatus": "approved" if published else "pending",
                "visibility": "public",
            }
        }


class _ModerationClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []
        self.case_reads = 0

    def request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> tuple[int, dict[str, object]]:
        self.calls.append((method, path, kwargs.get("body")))
        if method == "GET":
            self.case_reads += 1
            if self.case_reads == 1:
                return 404, {
                    "error": {
                        "code": "CONTENT.USER.moderation_case_not_found",
                    }
                }
            return 200, {
                "data": {
                    "id": "case-pending",
                    "status": "pending",
                }
            }
        if path.endswith(":review-moderation"):
            return 200, {"CaseID": "case-pending", "Status": "reviewed"}
        if path.endswith(":moderate"):
            return 200, {"CaseID": "case-pending", "Status": "approved"}
        raise AssertionError(f"unexpected request: {method} {path}")


class _DiscardClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object, object]] = []
        self.discards = 0

    def request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> tuple[int, dict[str, object]]:
        self.calls.append(
            (
                method,
                path,
                kwargs.get("operation_id"),
                kwargs.get("idempotency_key"),
            )
        )
        if method == "DELETE":
            self.discards += 1
            return 200, {
                "data": {
                    "mediaId": "asset-discard",
                    "status": "deleted",
                    "replayed": self.discards > 1,
                }
            }
        if method == "GET":
            return 404, {
                "error": {"code": "CONTENT.USER.media_not_found"}
            }
        raise AssertionError(f"unexpected request: {method} {path}")


class _RetryTransportClient:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = list(statuses)
        self.calls: list[tuple[str, str, object, object, object]] = []

    def request(
        self,
        method: str,
        path: str,
        **kwargs: object,
    ) -> tuple[int, dict[str, object] | None]:
        self.calls.append(
            (
                method,
                path,
                kwargs.get("operation_id"),
                kwargs.get("idempotency_key"),
                kwargs.get("expected_statuses"),
            )
        )
        status = self.statuses.pop(0)
        if status == 200:
            return status, {"data": {"status": "completed"}}
        return status, None


class MediaPublicationLifecycleProbeContractTest(unittest.TestCase):
    def test_idempotent_media_command_retries_transient_gateway_status(self) -> None:
        client = _RetryTransportClient([503, 200])

        with mock.patch.object(probe.time, "sleep", return_value=None) as sleep:
            status, payload = probe._request_with_transport_retry(
                client,
                "POST",
                "/content/media/uploads/session-1:complete",
                operation_id="CompleteMediaUpload",
                body={"accessPolicy": "owner_only"},
                idempotency_key="complete-key",
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"data": {"status": "completed"}})
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(
            {call[3] for call in client.calls},
            {"complete-key"},
        )
        self.assertTrue(
            all(
                isinstance(call[4], frozenset) and 503 in call[4]
                for call in client.calls
            )
        )
        sleep.assert_called_once_with(1.0)

    def test_unreferenced_media_discard_replays_and_disappears_from_owner_read(
        self,
    ) -> None:
        client = _DiscardClient()

        probe._discard_unreferenced_asset(
            client,
            owner_query_client=client,
            asset_id="asset-discard",
            idempotency_key="discard-key",
        )

        self.assertEqual(
            client.calls,
            [
                (
                    "DELETE",
                    "/content/media/asset-discard",
                    "DiscardMediaAsset",
                    "discard-key",
                ),
                (
                    "DELETE",
                    "/content/media/asset-discard",
                    "DiscardMediaAsset",
                    "discard-key",
                ),
                (
                    "GET",
                    "/internal/content/media/asset-discard",
                    "GetOwnedMediaAsset",
                    None,
                ),
            ],
        )

    def test_media_viewer_uses_seeded_persona_without_unsupported_profile(self) -> None:
        self.assertEqual(probe.MEDIA_VIEWER_SUBJECT, "fixture_user_friend")
        expected = probe_support.LocalAcceptanceSession(
            owner_id="fixture_user_friend",
            persona_id="fixture_user_friend",
            access_token="token",
        )
        with mock.patch.object(
            probe_support,
            "open_local_acceptance_session",
            return_value=expected,
        ) as open_session:
            actual = probe_support.media_viewer_session(
                environment="beta",
                base_url="https://api.beta.example.invalid",
                target_name="beta-local",
                subject="fixture_user_friend",
            )

        self.assertIs(actual, expected)
        self.assertEqual(
            open_session.call_args.kwargs["subject"],
            "fixture_user_friend",
        )
        self.assertNotIn("profile", open_session.call_args.kwargs)

    def test_moderation_operator_uses_dedicated_least_privilege_profile(self) -> None:
        expected = probe_support.LocalAcceptanceSession(
            owner_id="fixture_content_moderation_operator",
            persona_id="fixture_content_moderation_operator",
            access_token="token",
        )
        with mock.patch.object(
            probe_support,
            "open_local_acceptance_session",
            return_value=expected,
        ) as open_session:
            actual = probe_support.moderation_operator_session(
                environment="beta",
                base_url="https://api.beta.example.invalid",
                target_name="beta-local",
            )

        self.assertIs(actual, expected)
        self.assertEqual(
            open_session.call_args.kwargs["profile"],
            "content-moderation-operator",
        )
        self.assertEqual(
            open_session.call_args.kwargs["subject"],
            "fixture_content_moderation_operator",
        )

    def test_probe_client_ignores_machine_proxy_for_system_resolved_target(self) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = b'{"status":"ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = probe_support.ProbeClient(
                f"http://127.0.0.1:{server.server_port}",
                probe_support.LocalAcceptanceSession(
                    owner_id="owner",
                    persona_id="persona",
                    access_token="token",
                ),
            )
            with mock.patch.dict(
                os.environ,
                {
                    "HTTP_PROXY": "http://127.0.0.1:1",
                    "HTTPS_PROXY": "http://127.0.0.1:1",
                    "ALL_PROXY": "http://127.0.0.1:1",
                    "NO_PROXY": "",
                },
            ):
                status, payload = client.request(
                    "GET",
                    "/healthz",
                    operation_id="GetHealth",
                )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "ok"})

    def test_probe_client_allows_explicit_gateway_transport_failure_body(self) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = b"upstream unavailable"
                self.send_response(503)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = probe_support.ProbeClient(
                f"http://127.0.0.1:{server.server_port}",
                probe_support.LocalAcceptanceSession(
                    owner_id="owner",
                    persona_id="persona",
                    access_token="token",
                ),
            )
            status, payload = client.request(
                "POST",
                "/content/posts:publish",
                operation_id="SubmitPostPublication",
                expected_statuses=frozenset({503}),
                allow_non_json_statuses=frozenset({503}),
                body={"publishIntentId": "intent"},
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(status, 503)
        self.assertIsNone(payload)

    def test_private_and_public_publications_use_distinct_draft_identity(self) -> None:
        client = _PublicationClient()
        created: list[str] = []

        private_post = probe._publish_and_readback(
            client,
            media_type="image",
            asset_id="asset-image",
            run_id="run-1",
            processing_timeout_seconds=1,
            visibility="private",
            on_post_created=created.append,
        )
        public_post = probe._publish_and_readback(
            client,
            media_type="image",
            asset_id="asset-image",
            run_id="run-1",
            processing_timeout_seconds=1,
            visibility="public",
            on_post_created=created.append,
        )

        self.assertEqual(private_post, "post-private")
        self.assertEqual(public_post, "post-public")
        self.assertEqual(created, ["post-private", "post-public"])
        private_drafts = {
            str(body["localDraftId"])
            for body in client.publication_bodies
            if body["visibility"] == "private"
        }
        public_drafts = {
            str(body["localDraftId"])
            for body in client.publication_bodies
            if body["visibility"] == "public"
        }
        self.assertEqual(
            private_drafts,
            {"media-publication-probe-draft-image-private-run-1"},
        )
        self.assertEqual(
            public_drafts,
            {"media-publication-probe-draft-image-public-run-1"},
        )
        self.assertTrue(private_drafts.isdisjoint(public_drafts))

    def test_pending_post_uses_real_moderation_case_before_publication(self) -> None:
        publisher = _PendingPostClient()
        operator = _ModerationClient()

        with mock.patch.object(probe.time, "sleep", return_value=None):
            used_case = probe._approve_post_for_publication(
                publisher,
                operator,
                post_id="post-pending",
                idempotency_prefix="moderation-run",
                timeout_seconds=1,
            )

        self.assertTrue(used_case)
        self.assertEqual(operator.case_reads, 2)
        self.assertEqual(
            [(method, path) for method, path, _body in operator.calls[-2:]],
            [
                (
                    "POST",
                    "/internal/content/posts/post-pending:review-moderation",
                ),
                ("POST", "/internal/content/posts/post-pending:moderate"),
            ],
        )
        self.assertEqual(
            operator.calls[-1][2],
            {
                "caseId": "case-pending",
                "decision": "approved",
                "decisionReason": "local_acceptance_safe_media_publication",
            },
        )

    def test_auto_cover_retries_only_canonical_media_not_ready(self) -> None:
        client = _CoverClient()

        with mock.patch.object(probe.time, "sleep", return_value=None):
            probe._select_auto_video_cover(
                client,
                asset_id="asset-video",
                idempotency_key="cover-key",
                processing_timeout_seconds=1,
            )

        self.assertEqual(client.calls, 2)

    def test_auto_cover_retries_worker_version_conflict(self) -> None:
        client = mock.Mock()
        client.request.side_effect = [
            (
                409,
                {"error": {"code": "CONTENT.USER.version_conflict"}},
            ),
            (
                200,
                {
                    "data": {
                        "mediaId": "asset-video",
                        "coverStrategy": "first_frame",
                        "coverUrl": "https://cdn.example/video-cover",
                    }
                },
            ),
        ]

        with mock.patch.object(probe.time, "sleep", return_value=None):
            probe._select_auto_video_cover(
                client,
                asset_id="asset-video",
                idempotency_key="cover-key",
                processing_timeout_seconds=1,
            )

        self.assertEqual(client.request.call_count, 2)

    def test_auto_cover_does_not_retry_another_400_failure(self) -> None:
        client = mock.Mock()
        client.request.return_value = (
            400,
            {"error": {"code": "CONTENT.USER.media_processing_rejected"}},
        )

        with self.assertRaises(probe.ProbeFailure) as raised:
            probe._select_auto_video_cover(
                client,
                asset_id="asset-video",
                idempotency_key="cover-key",
                processing_timeout_seconds=1,
            )

        self.assertEqual(raised.exception.category, "cover_selection_failed")
        client.request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
