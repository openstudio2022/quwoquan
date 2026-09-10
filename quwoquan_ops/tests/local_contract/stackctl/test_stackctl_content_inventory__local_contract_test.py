"""公开内容盘点只读入口、遍历与证据诚实性的本地契约。"""
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#req-002
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import content_inventory as subject
from quwoquan_ops.cli.lib import content_api_consumer as consumer

RELEASE = "release-inventory-test"
DIGEST = "sha256:" + "a" * 64
API = "https://api.alpha.quwoquan.com"


def _post(carrier: str, suffix: str = "1") -> dict[str, Any]:
    return {"postId": carrier + "-" + suffix, "contentType": carrier,
            "contentIdentity": "work", "mediaAssetId": "asset-shared"}


def _page(rows: list[dict[str, Any]], *, cursor: str | None = None,
          release: str = RELEASE, reason: str = "no_eligible_content") -> dict[str, Any]:
    return {"items": rows, "objectCards": [], "outcome": "content" if rows else "empty",
            "emptyReason": None if rows else reason, "nextCursor": cursor,
            "previousCursor": None, "paginationExpiresAt": None,
            "feedRequestId": "feed-observation", "releaseId": release, "manifestDigest": DIGEST}


def _observation(payload: dict[str, Any], kwargs: dict[str, Any], status: int = 200) -> consumer.HttpObservation:
    return consumer.HttpObservation(method=kwargs["method"], path="/" + kwargs["path"],
                                    status=status, payload=payload, request_id="request-observation",
                                    trace_id="trace-observation", started_at="now", completed_at="now",
                                    duration_ms=1)


def _healthy(**kwargs: Any) -> consumer.HttpObservation:
    query = kwargs.get("query") or {}
    if kwargs["path"].startswith("content/posts/"):
        post_id = kwargs["path"].rsplit("/", 1)[-1]
        carrier, suffix = post_id.split("-", 1)
        return _observation(_post(carrier, suffix), kwargs)
    if query.get("type"):
        return _observation(_page([_post(query["type"])]), kwargs)
    if query.get("channelId") == "premium_stream":
        return _observation(_page([]), kwargs)
    return _observation(_page([_post("video")]), kwargs)


@pytest.fixture(autouse=True)
def _canonical_authority(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ca = tmp_path / "root.crt"
    ca.write_text("mock CA")
    monkeypatch.setattr(subject, "_authority", lambda target: (API, ca))


def _run(http: Any = _healthy, **kwargs: Any) -> dict[str, Any]:
    return subject.collect_content_inventory(target="alpha-local", http_request=http, **kwargs)


def test_cursor_pages_unique_counts_and_read_only_public_requests() -> None:
    calls = []
    def request(**kwargs: Any) -> consumer.HttpObservation:
        calls.append(kwargs)
        query = kwargs.get("query") or {}
        if query.get("type") == "article" and not kwargs["path"].startswith("content/posts/"):
            payload = (_page([_post("article", "2")]) if query.get("cursor")
                       else _page([_post("article")], cursor="next-article"))
            return _observation(payload, kwargs)
        return _healthy(**kwargs)
    report = _run(request)
    assert report["status"] == "complete"
    assert report["typedContent"]["article"]["count"] == 2
    assert report["typedContent"]["article"]["pagesRead"] == 2
    assert report["uniquePostCount"] == 4
    assert report["traversalComplete"] is True
    assert report["activeIdentity"] == {"releaseId": RELEASE, "manifestDigest": DIGEST,
                                        "source": "first_valid_feed_response"}
    assert report["media"]["uniqueAssetCount"] == 1
    assert report["media"]["byteVerification"] == "notObserved"
    assert report["media"]["accessibleAssetCount"] is None
    assert report["postDetails"]["fullVerification"] is False
    assert all(call["method"] == "GET" and call["api_base"] == API for call in calls)
    assert all("body" not in call and "bearer_token" not in call for call in calls)
    assert all(call["follow_redirects"] is False for call in calls)
    assert len({call["client_session_id"] for call in calls}) == 1
    assert all(int(call["query"]["limit"]) <= 20 for call in calls if call.get("query"))
    continuation = next(call for call in calls if (call.get("query") or {}).get("cursor"))
    assert continuation["query"]["feedRequestId"] == "feed-observation"


def test_premium_empty_does_not_claim_video_library_empty() -> None:
    report = _run()
    assert report["typedContent"]["video"]["count"] == 1
    premium = report["windows"]["premium"]
    assert premium["observedCount"] == 0
    assert premium["outcome"] == "empty"
    assert premium["emptyReason"] == "no_eligible_content"
    assert premium["traversalComplete"] is False
    assert "count" not in premium
    assert report["windows"]["recommend"]["observedCount"] == 1


def test_healthy_empty_has_reason_and_zero() -> None:
    report = _run(lambda **kwargs: _observation(_page([]), kwargs))
    assert report["status"] == "complete"
    assert report["uniquePostCount"] == 0
    for cell in report["typedContent"].values():
        assert cell["count"] == 0 and cell["traversalComplete"] is True
        assert cell["outcome"] == "empty" and cell["emptyReason"] == "no_eligible_content"


@pytest.mark.parametrize("flip_field,flip_value", [("releaseId", "release-new"), ("manifestDigest", "sha256:" + "b" * 64)])
def test_version_flip_stops_without_stitching_counts(flip_field: str, flip_value: str) -> None:
    calls = []
    def request(**kwargs: Any) -> consumer.HttpObservation:
        calls.append(kwargs)
        row = _healthy(**kwargs)
        if len(calls) == 2:
            row.payload[flip_field] = flip_value
        return row
    report = _run(request)
    assert len(calls) == 2
    assert report["firstBlocker"]["type"] == "active_changed"
    assert report["uniquePostCount"] is None
    assert report["traversalComplete"] is False
    assert all(cell["count"] is None for cell in report["typedContent"].values())


@pytest.mark.parametrize("duplicate", [False, True])
def test_loop_cursor_and_duplicate_post_stop(duplicate: bool) -> None:
    calls = []
    def request(**kwargs: Any) -> consumer.HttpObservation:
        calls.append(kwargs)
        suffix = "1" if duplicate else str(len(calls))
        return _observation(_page([_post("article", suffix)], cursor="same-cursor"), kwargs)
    report = _run(request)
    assert len(calls) == 2
    assert report["firstBlocker"]["type"] == ("duplicate_post_id" if duplicate else "cursor_loop")
    assert report["typedContent"]["article"]["count"] is None
    assert report["typedContent"]["article"]["traversalComplete"] is False


def test_same_post_id_across_types_is_invalid() -> None:
    def request(**kwargs: Any) -> consumer.HttpObservation:
        observation = _healthy(**kwargs)
        observation.payload["items"][0]["postId"] = "shared-post-id"
        return observation
    report = _run(request)
    assert report["firstBlocker"]["type"] == "post_type_conflict"
    assert all(cell["count"] is None for cell in report["typedContent"].values())


@pytest.mark.parametrize("error,code", [
    (TimeoutError("private exception details"), "transport_timeout"),
    (consumer.ContentApiConsumerTransportError("secret bearer phone"), "transport_failed"),
    (consumer.ContentApiConsumerError("HTTP response exceeded byte budget"), "body_limit"),
])
def test_transport_failures_are_unknown_not_empty(error: Exception, code: str) -> None:
    request = mock.Mock(side_effect=error)
    report = _run(request)
    assert request.call_count == 1
    assert report["firstBlocker"]["type"] == code
    assert report["uniquePostCount"] is None
    assert report["typedContent"]["article"]["count"] is None
    assert report["typedContent"]["article"]["observedCount"] is None
    assert report["media"]["uniqueAssetCount"] is None
    assert "secret bearer phone" not in json.dumps(report)


@pytest.mark.parametrize("payload,status,code", [
    ({}, 200, "noncanonical_response"),
    ({}, 503, "http_status"),
    (_page([]) | {"emptyReason": None}, 200, "noncanonical_response"),
    (_page([]) | {"emptyReason": "no_active_release", "releaseId": None, "manifestDigest": None}, 200, "no_active_release"),
])
def test_noncanonical_or_no_active_responses_are_unknown(payload: dict[str, Any], status: int, code: str) -> None:
    report = _run(lambda **kwargs: _observation(payload, kwargs, status))
    assert report["firstBlocker"]["type"] == code
    assert report["uniquePostCount"] is None
    assert report["typedContent"]["article"]["count"] is None


@pytest.mark.parametrize("limits,code", [
    (subject.InventoryLimits(max_pages=1), "max_pages"),
    (subject.InventoryLimits(max_bytes=1), "body_limit"),
    (subject.InventoryLimits(max_bytes=subject.PAGE_BYTES), "max_bytes"),
    (subject.InventoryLimits(page_size=21), "invalid_limits"),
])
def test_limits_preserve_incomplete_and_unknown(limits: subject.InventoryLimits, code: str) -> None:
    report = _run(limits=limits)
    assert report["firstBlocker"]["type"] == code
    assert report["traversalComplete"] is False
    assert report["uniquePostCount"] is None


def test_time_budget_and_explicit_identity_fail_closed() -> None:
    ticks = iter([0.0, 2.0])
    request = mock.Mock()
    report = _run(request, limits=subject.InventoryLimits(total_seconds=1), clock=lambda: next(ticks))
    assert report["firstBlocker"]["type"] == "total_timeout"
    request.assert_not_called()
    mismatch = _run(release_id="other-release")
    assert mismatch["firstBlocker"]["type"] == "release_mismatch"
    assert mismatch["activeIdentity"] is None


def test_real_cli_parse_and_main_never_enter_mutation_or_availability(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = mock.Mock(side_effect=_healthy)
    monkeypatch.setattr(subject, "_default_request", request)
    monkeypatch.setattr(stackctl, "resolve_report_dir", lambda *args: tmp_path)
    traps = ["_read_only_user_availability_report", "_candidate_workspace_report",
             "command_content_readiness", "command_content_api_consumer", "command_up", "command_deploy"]
    for symbol in traps:
        monkeypatch.setattr(stackctl, symbol, mock.Mock(side_effect=AssertionError(symbol)))
    argv = ["stackctl", "inspect", "--target", "alpha-local", "--scope", "content", "--detail-samples", "0"]
    parsed = stackctl.build_parser().parse_args(argv[1:])
    assert parsed.scope == "content" and parsed.detail_samples == 0
    monkeypatch.setattr(sys, "argv", argv)
    assert stackctl.main() == 0
    report = json.loads((tmp_path / "report.json").read_text())["inspection"]["content"]
    assert report["readOnly"]["accountCreated"] is False
    assert report["readOnly"]["releaseMutation"] is False
    assert len(request.call_args_list) == 5
    assert all(call.kwargs["method"] == "GET" for call in request.call_args_list)
    for symbol in traps:
        getattr(stackctl, symbol).assert_not_called()


def test_canonical_resolver_and_target_ca_are_used(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 绕过本模块 fixture 替换，校验实际 resolver，而非在 CLI 接受调用者 URL。
    from importlib import reload
    reload(subject)
    topology = {"targets": {"alpha-local": {"env": "alpha", "publicBases": {"api": API}}}}
    ca = tmp_path / "canonical-ca.crt"
    ca.write_text("mock canonical CA")
    monkeypatch.setattr(subject, "load_environment_topology", lambda: topology)
    ca_resolver = mock.Mock(return_value=ca)
    monkeypatch.setattr(subject, "root_certificate_path", ca_resolver)
    assert subject._authority("alpha-local") == (API, ca)
    ca_resolver.assert_called_once_with("alpha-local")
    topology["targets"]["alpha-local"]["publicBases"]["api"] = "http://localhost"
    report = _run()
    assert report["firstBlocker"]["type"] == "canonical_authority_unavailable"


def test_read_only_bootstrap_dispatches_content_without_loading_mutation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from quwoquan_ops.cli import read_only_entry
    import quwoquan_ops.cli as cli_package

    module_before = sys.modules["quwoquan_ops.cli.stackctl"]
    package_before = cli_package.stackctl
    request = mock.Mock(side_effect=_healthy)
    monkeypatch.setattr(subject, "_default_request", request)
    monkeypatch.setattr(read_only_entry, "resolve_report_dir", lambda *args: tmp_path)
    try:
        parser = read_only_entry.build_parser()
        facade = sys.modules["quwoquan_ops.cli.stackctl"]
        for symbol in ("_read_only_user_availability_report", "_candidate_workspace_report", "open_test_data_acceptance_session"):
            setattr(facade, symbol, mock.Mock(side_effect=AssertionError(symbol)))
        args = parser.parse_args(["inspect", "--target", "alpha-local", "--scope", "content", "--detail-samples", "0"])
        result = facade.command_inspect(args)
        assert result["exitCode"] == 0
        assert request.call_count == 5
        facade._read_only_user_availability_report.assert_not_called()
        facade.open_test_data_acceptance_session.assert_not_called()
    finally:
        sys.modules["quwoquan_ops.cli.stackctl"] = module_before
        cli_package.stackctl = package_before


def test_conflicting_post_types_across_ranked_windows_invalidates_inventory() -> None:
    def request(**kwargs: Any) -> consumer.HttpObservation:
        query = kwargs.get("query") or {}
        if query.get("channelId"):
            kind = "image" if query["channelId"] == "recommend" else "video"
            return _observation(_page([_post(kind) | {"postId": "window-only-post"}]), kwargs)
        return _healthy(**kwargs)
    report = _run(request)
    assert report["firstBlocker"]["type"] == "post_type_conflict"
    assert report["uniquePostCount"] is None


def test_detail_sample_limits_do_not_claim_full_media_verification() -> None:
    calls = []
    def request(**kwargs: Any) -> consumer.HttpObservation:
        calls.append(kwargs)
        return _healthy(**kwargs)
    report = _run(request, limits=subject.InventoryLimits(detail_samples=1))
    assert report["postDetails"]["sampleSize"] == 1
    assert report["postDetails"]["observedCount"] == 1
    assert report["postDetails"]["fullVerification"] is False
    assert report["media"]["byteVerification"] == "notObserved"
    assert sum(call["path"].startswith("content/posts/") for call in calls) == 1


def test_transport_missing_safety_contract_blocks_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    invoked = []
    def unsafe_transport(*, client_session_id: str) -> Any:
        invoked.append(client_session_id)
    monkeypatch.setattr(consumer, "_default_http_request", unsafe_transport)
    report = subject.collect_content_inventory(target="alpha-local")
    assert report["firstBlocker"]["type"] == "transport_safety_unavailable"
    assert invoked == []
