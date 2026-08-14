#!/usr/bin/env python3
"""推荐面三场景黑盒探针（N2-2 stackctl verify 检查项）。

对 gamma-local（或 beta）网关执行只读 feed 探测，验证二期推荐能力的
端到端可用性（此前 stackctl verify 对 travel/premium/objectCards 零感知）：

  1. travel   —— GET /content/feed?channelId=travel_photography：
     travel 垂类路由可用，envelope 契约字段完整（items/feedRequestId）。
  2. premium  —— GET /content/feed?channelId=premium_stream：
     精品沉浸流 fail-closed 路由可用；release readiness 要求至少一条可交付内容。
  3. objectCards —— GET /content/feed?channelId=recommend（受管 Actor 身份）：
     canonical recommendation policy 开启 objectCards 后，若当前 immutable release
     已声明对象卡覆盖，envelope.objectCards 必须出现
     entity_homepage 卡且 objectId 可路由；--require-object-cards 控制是否阻断。

契约对齐：响应字段以 quwoquan_service/services/content-service/contracts/content/post/operations.yaml 的
GetFeed response_fields 为真相源（items/nextCursor/cursor/feedRequestId/
policyDigest/objectCards）。

用法（gamma-local 完整验证）：
  python3 .../run_recommendation_feed_probe.py \
    --env gamma --base-url https://api.gamma.quwoquan.com:19000 \
    --viewer-id "$QWQ_TEST_DATA_PRIMARY_ACTOR_ID" \
    --test-data-instance-id "$QWQ_TEST_DATA_INSTANCE_ID" \
    --actor-lease-digest "$QWQ_TEST_DATA_ACTOR_LEASE_DIGEST" \
    --candidate-binding-digest "$QWQ_TEST_DATA_CANDIDATE_BINDING_DIGEST" \
    --require-object-cards --report .qwq_output/env/gamma/runs/rec-feed-probe/report.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# 本地管理 TLS 环境（*-local）的网关根证书；由 --ca-file 注入，走正常验证。
_SSL_CONTEXT: ssl.SSLContext | None = None
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
    parser.add_argument(
        "--env",
        choices=("alpha", "beta", "gamma", "prod"),
        required=True,
    )
    parser.add_argument(
        "--base-url",
        required=True,
    )
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
    parser.add_argument(
        "--ca-file",
        default=os.environ.get("QWQ_PROBE_CA_FILE", ""),
        help="本地管理 TLS 环境（*-local）的根证书路径",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    parser.add_argument(
        "--require-object-cards",
        action="store_true",
        help="要求 objectCards 场景必须返回 entity_homepage 卡（对象卡种子已应用后开启）",
    )
    parser.add_argument(
        "--require-release-content",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "要求 travel 与 premium 两个内容面都返回至少一条内容（默认开启，"
            "防止空 feed 静默通过；仅在环境显式无内容 release 时用 "
            "--no-require-release-content 关闭并说明原因）。"
        ),
    )
    parser.add_argument(
        "--report",
        default=".qwq_output/env/gamma/runs/rec-feed-probe/recommendation-feed-report.json",
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
    return args


def fetch_feed(
    base_url: str,
    channel_id: str,
    viewer_id: str,
    token: str,
    limit: int,
    timeout: int,
    session_id: str,
) -> tuple[int, dict[str, Any] | None, str]:
    # 推荐路由契约要求 X-Client-Session-Id（GetFeed request_bindings），
    # 缺失时 fail-closed 400。
    query = urllib.parse.urlencode(
        {"channelId": channel_id, "limit": str(limit), "sessionId": session_id}
    )
    url = f"{base_url.rstrip('/')}/content/feed?{query}"
    request = urllib.request.Request(url, method="GET")
    request.add_header("Accept", "application/json")
    request.add_header("X-Client-Session-Id", session_id)
    if viewer_id:
        request.add_header("X-Client-User-Id", viewer_id)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(
            request, timeout=timeout, context=_SSL_CONTEXT
        ) as response:
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


def check_object_cards(payload: dict[str, Any], required: bool) -> list[str]:
    cards = payload.get("objectCards")
    if cards is None:
        if required:
            return [
                "objectCards absent: canonical recommendation policy may not be active "
                "(QWQ_REC_POLICY_PATH) or current immutable release lacks object-card coverage"
            ]
        return []
    if not isinstance(cards, list):
        return ["objectCards must be a list when present"]
    errors: list[str] = []
    if required and not cards:
        errors.append(
            "objectCards empty: current immutable release/readiness must provide "
            "entity_homepage coverage"
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


def check_non_empty_items(payload: dict[str, Any], *, required: bool) -> list[str]:
    if not required:
        return []
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return ["release content feed must contain at least one deliverable item"]
    return []


def main() -> int:
    args = parse_args()
    if args.ca_file:
        global _SSL_CONTEXT
        _SSL_CONTEXT = ssl.create_default_context(cafile=args.ca_file)
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
            "requireReleaseContent": bool(args.require_release_content),
            "testDataInstanceId": args.test_data_instance_id,
            "actorLeaseDigest": args.actor_lease_digest,
            "candidateBindingDigest": args.candidate_binding_digest,
            "viewerIdDigest": "sha256:"
            + hashlib.sha256(args.viewer_id.encode("utf-8")).hexdigest(),
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
        session_id = hashlib.sha256(
            f"{args.test_data_instance_id}\0{name}".encode("utf-8")
        ).hexdigest()[:32]
        status, payload, detail = fetch_feed(
            args.base_url,
            channel_id,
            args.viewer_id if with_viewer else "",
            args.test_auth_token,
            args.limit,
            args.timeout_seconds,
            session_id,
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
            if name in {"travel", "premium"}:
                errors.extend(
                    check_non_empty_items(
                        payload,
                        required=bool(args.require_release_content),
                    )
                )
            if assert_cards:
                errors.extend(check_object_cards(payload, args.require_object_cards))
            surface_report["errors"] = errors
            surface_report["itemCount"] = len(payload.get("items") or [])
            surface_report["objectCardCount"] = len(payload.get("objectCards") or [])
            surface_report["policyDigest"] = payload.get("policyDigest", "")
            surface_report["outcome"] = payload.get("outcome")
            surface_report["emptyReason"] = payload.get("emptyReason")
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
