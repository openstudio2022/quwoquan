#!/usr/bin/env python3
# spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/spec.md#sit-001
# readiness_case: ranked_window_feed_journey_probe_ops_env
"""排序窗口 content feed 旅程黑盒探针（RankedRecommendationWindow UAT 锚点）。

CreateRankedRecommendationWindow / GetRankedRecommendationPage 的可见性为
internal 且 principal 为 service，端侧没有直接页面；其用户验收锚点按
recommendation-platform OPEN-002 的裁决挂在 content feed 旅程上。本探针经
网关 `GET /content/feed?channelId=recommend`（sort=recommend 主链路）验证
排序窗口生命周期在真实环境中的用户可观察语义：

  1. first_page —— 首刷返回契约 envelope（items/feedRequestId/policyDigest/
     outcome）；非空首刷证明窗口创建成功且已固化。
  2. pagination —— 用 nextCursor + 回显 feedRequestId 连续续页：每页 envelope
     合法、feedRequestId 归因连续、跨页 contentId 无重复（不可变
     RankedFeedWindow 按 (ordinal, contentId) 稳定续接）。
  3. back_replay —— 用 previousCursor 回翻上一已交付页：契约要求只按
     FeedDeliveryPage 已交付 Post 身份原序 hydrate，删除或不可见项只缩短
     页面，因此回翻序列必须是原页 contentId 序列的保序子序列。

契约真相源：quwoquan_service/services/content-service/contracts/content/post/operations.yaml
的 GetFeed（request_bindings/response_fields，推荐路由要求 X-Client-Session-Id）。

用法（gamma-local）：
  python3 .../run_ranked_window_feed_journey_probe.py \
    --env gamma --base-url https://api.gamma.quwoquan.com:19000 \
    --viewer-id "$QWQ_TEST_DATA_PRIMARY_ACTOR_ID" \
    --test-data-instance-id "$QWQ_TEST_DATA_INSTANCE_ID" \
    --actor-lease-digest "$QWQ_TEST_DATA_ACTOR_LEASE_DIGEST" \
    --candidate-binding-digest "$QWQ_TEST_DATA_CANDIDATE_BINDING_DIGEST" \
    --report .qwq_output/env/gamma/runs/ranked-window-probe/report.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")


REPO_ROOT = _find_repo_root()
SCENARIO = "recommendation.ranked_window.feed_journey_probe"
REPORT_SCHEMA = "ranked-window-feed-journey-probe-report"
REQUIRED_ENVELOPE_FIELDS = ("items", "feedRequestId", "policyDigest", "outcome")
CANONICAL_EMPTY_REASONS = {
    "no_active_release",
    "no_eligible_content",
    "following_empty",
    "continuation_end",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("alpha", "beta", "gamma", "prod"), required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument(
        "--test-auth-token",
        default=os.environ.get("GAMMA_TEST_AUTH_TOKEN")
        or os.environ.get("TEST_AUTH_TOKEN")
        or "",
    )
    parser.add_argument(
        "--viewer-id",
        default=os.environ.get("QWQ_TEST_DATA_PRIMARY_ACTOR_ID", ""),
        help="由当前 CaseResult/ActorLease 投影的 primary Actor ID",
    )
    parser.add_argument(
        "--test-data-instance-id",
        default=os.environ.get("QWQ_TEST_DATA_INSTANCE_ID", ""),
    )
    parser.add_argument(
        "--actor-lease-digest",
        default=os.environ.get("QWQ_TEST_DATA_ACTOR_LEASE_DIGEST", ""),
    )
    parser.add_argument(
        "--candidate-binding-digest",
        default=os.environ.get("QWQ_TEST_DATA_CANDIDATE_BINDING_DIGEST", ""),
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--min-pages",
        type=int,
        default=2,
        help="必须完成的连续页数（含首刷）；不足即失败，release readiness 应保证足量内容",
    )
    parser.add_argument("--max-pages", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument(
        "--report",
        default=".qwq_output/env/gamma/runs/ranked-window-probe/ranked-window-feed-journey-report.json",
    )
    args = parser.parse_args()
    for label, value in (
        ("--viewer-id", args.viewer_id),
        ("--test-data-instance-id", args.test_data_instance_id),
    ):
        if not str(value).strip():
            parser.error(f"{label} must come from the active test-data ActorLease")
    for label, value in (
        ("--actor-lease-digest", args.actor_lease_digest),
        ("--candidate-binding-digest", args.candidate_binding_digest),
    ):
        if re.fullmatch(r"sha256:[0-9a-f]{64}", str(value).strip()) is None:
            parser.error(f"{label} must be a canonical test-data receipt digest")
    if args.min_pages < 1 or args.max_pages < args.min_pages:
        parser.error("--min-pages must be >= 1 and <= --max-pages")
    return args


def fetch_feed(
    *,
    base_url: str,
    session_id: str,
    viewer_id: str,
    token: str,
    limit: int,
    timeout: int,
    cursor: str = "",
    feed_request_id: str = "",
) -> tuple[int, dict[str, Any] | None, str]:
    params: dict[str, str] = {
        "channelId": "recommend",
        "sort": "recommend",
        "limit": str(limit),
        "sessionId": session_id,
    }
    if cursor:
        params["cursor"] = cursor
    if feed_request_id:
        params["feedRequestId"] = feed_request_id
    url = f"{base_url.rstrip('/')}/content/feed?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/json")
    request.add_header("X-Client-Session-Id", session_id)
    if viewer_id:
        request.add_header("X-Client-User-Id", viewer_id)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(body), ""
            except json.JSONDecodeError as exc:
                return response.status, None, f"invalid json: {exc}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return exc.code, None, detail
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, None, str(exc)


def check_envelope(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_ENVELOPE_FIELDS:
        if field not in payload:
            errors.append(f"missing envelope field: {field}")
    items = payload.get("items")
    if not isinstance(items, list):
        errors.append("items must be a list")
    if not str(payload.get("feedRequestId") or "").strip():
        errors.append("feedRequestId must be server-populated and non-empty")
    policy_digest = str(payload.get("policyDigest") or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", policy_digest) is None:
        errors.append("policyDigest must be a canonical sha256 digest")
    if isinstance(items, list):
        outcome = payload.get("outcome")
        empty_reason = payload.get("emptyReason")
        if items:
            if outcome != "content":
                errors.append("non-empty items require outcome=content")
            if empty_reason not in (None, ""):
                errors.append("content outcome cannot carry emptyReason")
        else:
            if outcome != "empty":
                errors.append("empty items require outcome=empty")
            if empty_reason not in CANONICAL_EMPTY_REASONS:
                errors.append("empty outcome requires a canonical emptyReason")
    return errors


def item_content_ids(payload: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for item in payload.get("items") or []:
        if isinstance(item, dict):
            content_id = str(
                item.get("postId") or item.get("id") or item.get("contentId") or ""
            ).strip()
            if content_id:
                ids.append(content_id)
    return ids


def is_ordered_subsequence(candidate: list[str], reference: list[str]) -> bool:
    it = iter(reference)
    return all(any(entry == ref for ref in it) for entry in candidate)


def main() -> int:
    args = parse_args()
    session_id = f"ranked-window-probe-{uuid.uuid4().hex}"
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "scenario": SCENARIO,
        "status": "running",
        "startedAt": utc_now(),
        "endedAt": "",
        "environment": {
            "env": args.env,
            "gatewayBaseUrl": args.base_url.rstrip("/"),
            "sessionIdDigest": "sha256:"
            + hashlib.sha256(session_id.encode("utf-8")).hexdigest(),
            "testDataInstanceId": args.test_data_instance_id,
            "actorLeaseDigest": args.actor_lease_digest,
            "candidateBindingDigest": args.candidate_binding_digest,
            "viewerIdDigest": "sha256:"
            + hashlib.sha256(args.viewer_id.encode("utf-8")).hexdigest(),
            "minPages": args.min_pages,
            "maxPages": args.max_pages,
        },
        "pages": [],
        "backReplay": {},
        "failures": [],
    }
    failures: list[str] = []

    pages: list[dict[str, Any]] = []
    seen_content_ids: set[str] = set()
    cursor = ""
    feed_request_id = ""
    for ordinal in range(args.max_pages):
        status, payload, detail = fetch_feed(
            base_url=args.base_url,
            session_id=session_id,
            viewer_id=args.viewer_id,
            token=args.test_auth_token,
            limit=args.limit,
            timeout=args.timeout_seconds,
            cursor=cursor,
            feed_request_id=feed_request_id,
        )
        page_report: dict[str, Any] = {"ordinal": ordinal, "httpStatus": status, "errors": []}
        if status != 200 or payload is None:
            page_report["errors"] = [f"http {status}: {detail[:300]}"]
            failures.append(f"page[{ordinal}]: http {status}")
            report["pages"].append(page_report)
            break
        errors = check_envelope(payload)
        content_ids = item_content_ids(payload)
        page_report["itemCount"] = len(content_ids)
        page_report["feedRequestId"] = payload.get("feedRequestId")
        page_report["outcome"] = payload.get("outcome")
        page_report["emptyReason"] = payload.get("emptyReason")
        if ordinal == 0:
            if not content_ids:
                errors.append(
                    "first page must deliver ranked content "
                    "(empty pool means the window journey cannot be accepted)"
                )
            feed_request_id = str(payload.get("feedRequestId") or "").strip()
        else:
            response_request_id = str(payload.get("feedRequestId") or "").strip()
            if response_request_id != feed_request_id:
                errors.append(
                    "pagination must keep the same feedRequestId attribution "
                    f"(expected {feed_request_id!r}, got {response_request_id!r})"
                )
        duplicated = [cid for cid in content_ids if cid in seen_content_ids]
        if duplicated:
            errors.append(
                "ranked window pagination must not repeat content across pages: "
                + ",".join(duplicated[:5])
            )
        seen_content_ids.update(content_ids)
        page_report["errors"] = errors
        if errors:
            failures.extend(f"page[{ordinal}]: {e}" for e in errors)
        pages.append({"payload": payload, "contentIds": content_ids})
        report["pages"].append(page_report)
        cursor = str(payload.get("nextCursor") or "").strip()
        if not cursor:
            break

    if len(pages) < args.min_pages:
        failures.append(
            f"journey completed only {len(pages)} page(s); "
            f"--min-pages={args.min_pages} requires a real continuation "
            "(release readiness must provide enough deliverable content)"
        )

    # previousCursor 回翻：契约要求只按已交付页原序 hydrate，删除只缩短页面。
    if len(pages) >= 2:
        previous_cursor = str(pages[1]["payload"].get("previousCursor") or "").strip()
        replay_report: dict[str, Any] = {"attempted": bool(previous_cursor), "errors": []}
        if not previous_cursor:
            replay_report["errors"] = [
                "second page must carry previousCursor pointing at the delivered first page"
            ]
            failures.append("backReplay: missing previousCursor on page[1]")
        else:
            status, payload, detail = fetch_feed(
                base_url=args.base_url,
                session_id=session_id,
                viewer_id=args.viewer_id,
                token=args.test_auth_token,
                limit=args.limit,
                timeout=args.timeout_seconds,
                cursor=previous_cursor,
                feed_request_id=feed_request_id,
            )
            replay_report["httpStatus"] = status
            if status != 200 or payload is None:
                replay_report["errors"] = [f"http {status}: {detail[:300]}"]
                failures.append(f"backReplay: http {status}")
            else:
                errors = check_envelope(payload)
                replay_ids = item_content_ids(payload)
                replay_report["itemCount"] = len(replay_ids)
                if not is_ordered_subsequence(replay_ids, pages[0]["contentIds"]):
                    errors.append(
                        "back replay must hydrate the delivered page in original order "
                        "(ordered subsequence of the first page)"
                    )
                replay_report["errors"] = errors
                if errors:
                    failures.extend(f"backReplay: {e}" for e in errors)
        report["backReplay"] = replay_report

    report["failures"] = failures
    report["status"] = "failed" if failures else "passed"
    report["endedAt"] = utc_now()

    report_path = REPO_ROOT / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    print(json.dumps({k: report[k] for k in ("status", "failures")}, ensure_ascii=False))
    print(f"report: {args.report}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
