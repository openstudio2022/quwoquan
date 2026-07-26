#!/usr/bin/env python3
"""推荐面三场景黑盒探针（N2-2 stackctl verify 检查项）。

对 gamma-local（或 beta）网关执行只读 feed 探测，验证二期推荐能力的
端到端可用性（此前 stackctl verify 对 travel/premium/objectCards 零感知）：

  1. travel   —— GET /content/feed?channelId=travel_photography：
     travel 垂类路由可用，envelope 契约字段完整（items/feedRequestId）。
  2. premium  —— GET /content/feed?channelId=premium_stream：
     精品沉浸流 fail-closed 路由可用；池空时诚实空 items（不混入普通池）。
  3. objectCards —— GET /content/feed?channelId=recommend（seed viewer 身份）：
     gamma policy overlay 开启 objectCards 后，若对象卡种子已应用
     （apply_content_object_cards_seed.py），envelope.objectCards 必须出现
     entity_homepage 卡且 objectId 可路由；--require-object-cards 控制是否阻断。

契约对齐：响应字段以 quwoquan_service/services/content-service/contracts/content/post/operations.yaml 的
GetFeed response_fields 为真相源（items/nextCursor/cursor/feedRequestId/
rankingVersion/reasonVersion/objectCards）。

用法（gamma-local 完整验证）：
  python3 .../run_recommendation_feed_probe.py \
    --base-url http://127.0.0.1:18080 --viewer-id fixture_user_current \
    --require-object-cards --report .qwq_output/env/gamma/runs/rec-feed-probe/report.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "quwoquan_app").is_dir() and (candidate / "quwoquan_service").is_dir():
            return candidate
    raise RuntimeError("cannot locate quwoquan repo root")


REPO_ROOT = _find_repo_root()
SCENARIO = "content.recommendation.feed_surfaces_probe"
REPORT_SCHEMA = "recommendation-feed-probe-report"
# GetFeed 契约 envelope 必备字段（feedRequestId 服务端权威生成，必须非空）。
REQUIRED_ENVELOPE_FIELDS = ("items", "feedRequestId")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=os.environ.get("API_CONTRACT_ENV", "gamma"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("REC_FEED_GATEWAY_BASE_URL")
        or os.environ.get("GAMMA_BASE_URL")
        or "http://127.0.0.1:18080",
    )
    parser.add_argument(
        "--test-auth-token",
        default=os.environ.get("GAMMA_TEST_AUTH_TOKEN")
        or os.environ.get("TEST_AUTH_TOKEN")
        or "",
    )
    parser.add_argument(
        "--viewer-id",
        default="fixture_user_current",
        help="objectCards 场景的 seed viewer（与 content_recommendation_object_cards.gamma_seed.json 对齐）",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument(
        "--require-object-cards",
        action="store_true",
        help="要求 objectCards 场景必须返回 entity_homepage 卡（对象卡种子已应用后开启）",
    )
    parser.add_argument(
        "--report",
        default=".qwq_output/env/gamma/runs/rec-feed-probe/recommendation-feed-report.json",
    )
    return parser.parse_args()


def fetch_feed(
    base_url: str,
    channel_id: str,
    viewer_id: str,
    token: str,
    limit: int,
    timeout: int,
) -> tuple[int, dict[str, Any] | None, str]:
    query = urllib.parse.urlencode({"channelId": channel_id, "limit": str(limit)})
    url = f"{base_url.rstrip('/')}/content/feed?{query}"
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/json")
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
    feed_request_id = str(payload.get("feedRequestId") or "").strip()
    if not feed_request_id:
        errors.append("feedRequestId must be server-populated and non-empty")
    return errors


def check_object_cards(payload: dict[str, Any], required: bool) -> list[str]:
    cards = payload.get("objectCards")
    if cards is None:
        if required:
            return [
                "objectCards absent: gamma policy overlay may not be applied "
                "(QWQ_REC_POLICY_PATH) or object-card seed missing"
            ]
        return []
    if not isinstance(cards, list):
        return ["objectCards must be a list when present"]
    errors: list[str] = []
    if required and not cards:
        errors.append(
            "objectCards empty: apply seed via "
            "quwoquan_service/services/content-service/cmd/jobs/seed-object-cards/main.py"
        )
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            errors.append(f"objectCards[{index}] must be an object")
            continue
        kind = str(card.get("objectKind") or "").strip()
        object_id = str(card.get("objectId") or "").strip()
        if kind != "entity_homepage":
            errors.append(f"objectCards[{index}].objectKind unexpected: {kind!r}")
        if not object_id:
            errors.append(f"objectCards[{index}].objectId must be routable (non-empty)")
    return errors


def main() -> int:
    args = parse_args()
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "scenario": SCENARIO,
        "status": "running",
        "startedAt": utc_now(),
        "endedAt": "",
        "environment": {
            "env": args.env,
            "gatewayBaseUrl": args.base_url.rstrip("/"),
            "requireObjectCards": bool(args.require_object_cards),
            "viewerId": args.viewer_id,
        },
        "surfaces": {},
        "failures": [],
    }

    surfaces = (
        # (场景名, channelId, 是否带 viewer 身份, objectCards 断言)
        ("travel", "travel_photography", False, False),
        ("premium", "premium_stream", False, False),
        ("objectCards", "recommend", True, True),
    )

    failures: list[str] = []
    for name, channel_id, with_viewer, assert_cards in surfaces:
        status, payload, detail = fetch_feed(
            args.base_url,
            channel_id,
            args.viewer_id if with_viewer else "",
            args.test_auth_token,
            args.limit,
            args.timeout_seconds,
        )
        surface_report: dict[str, Any] = {
            "channelId": channel_id,
            "httpStatus": status,
            "errors": [],
        }
        if status != 200 or payload is None:
            surface_report["errors"] = [f"http {status}: {detail[:300]}"]
            failures.append(f"{name}: http {status}")
        else:
            errors = check_envelope(payload)
            if assert_cards:
                errors.extend(check_object_cards(payload, args.require_object_cards))
            surface_report["errors"] = errors
            surface_report["itemCount"] = len(payload.get("items") or [])
            surface_report["objectCardCount"] = len(payload.get("objectCards") or [])
            surface_report["rankingVersion"] = payload.get("rankingVersion", "")
            if errors:
                failures.extend(f"{name}: {e}" for e in errors)
        report["surfaces"][name] = surface_report

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
