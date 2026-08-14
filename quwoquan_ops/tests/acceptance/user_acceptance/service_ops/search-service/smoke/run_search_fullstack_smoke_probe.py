#!/usr/bin/env python3
# readiness_case: search_fullstack_smoke_probe_ops_env
# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003
# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t4
# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t5
# spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-002
"""搜索全栈冒烟：经网关 persisted GraphQL SearchPage 验证生产装配链。

App wire → Caddy 网关 → api-edge persisted query → search-service → CJK ES：
- 与 App 结果 Tab 同构的 all/article/image/video 矩阵返回 200、过滤生效且非空
- circle/user 仅作 objectTypes 过滤附属断言（泄漏即败；circle 非 release 数据，
  空结果登记 skipped_empty 不判失败）
- searchRequestId/rankPosition/matchedTerms/degradeSignals 投影在 wire 上
- 翻页 cursor 连续且无重复
- 非法词汇按 GraphQL enum 校验结构化拒绝
- 同 query 重复 20 次 TopN objectRef 序列一致
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[7]

SCHEMA = "search-fullstack-smoke-probe-report"
SCENARIO = "search.search_index_view.fullstack_smoke"
SEARCH_PAGE_SHA256 = "111b715594655786eba342c5cbebe7ea1338a9cf016ed0f35f54096802583478"

# 与 App SearchNetworkResultsPage 一级结果 Tab 同构（不含小趣 assistant、不含交集分组）。
TAB_MATRIX: list[dict[str, Any]] = [
    {
        "tab": "all",
        "objectTypes": ["CONTENT_POST", "USER_PROFILE", "ENTITY_HOMEPAGE", "LOCATION_PLACE"],
        "contentTypes": None,
        "requireHits": True,
    },
    {
        "tab": "article",
        "objectTypes": ["CONTENT_POST"],
        "contentTypes": ["ARTICLE"],
        "requireHits": True,
    },
    {
        "tab": "image",
        "objectTypes": ["CONTENT_POST"],
        "contentTypes": ["IMAGE"],
        "requireHits": True,
    },
    {
        "tab": "video",
        "objectTypes": ["CONTENT_POST"],
        "contentTypes": ["VIDEO"],
        "requireHits": True,
    },
]

# 过滤生效附属断言：不是 App 一级 Tab，只证明 objectTypes 收窄无泄漏。
# circle 不是 Data release 对象（只能经 Circle 域公开 command 创建），空结果
# 登记 skipped_empty 而非失败；user/entity 由 release + backfill 保证非空。
FILTER_ASSERTIONS: list[dict[str, Any]] = [
    {"tab": "circle_filter", "objectTypes": ["CIRCLE"], "contentTypes": None, "requireHits": False},
    {
        "tab": "user_filter",
        "objectTypes": ["USER_PROFILE", "ENTITY_HOMEPAGE"],
        "contentTypes": None,
        "requireHits": True,
    },
]


class ProbeFailure(Exception):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("beta", "gamma"), default="gamma")
    parser.add_argument("--base-url", required=True, help="网关 public base，例如 https://api.gamma.quwoquan.com:PORT")
    parser.add_argument("--query", default="西湖", help="预期在环境激活数据中可命中的中文关键词")
    parser.add_argument("--repeat", type=int, default=20, help="重复一致性执行次数")
    parser.add_argument("--insecure", action="store_true", help="local-managed TLS 下跳过证书校验")
    parser.add_argument(
        "--report",
        default=".qwq_output/env/repo/runs/search-fullstack-smoke/report.json",
    )
    return parser.parse_args()


class GraphQLClient:
    def __init__(self, base_url: str, *, insecure: bool) -> None:
        self._endpoint = base_url.rstrip("/") + "/graphql"
        self._context = ssl.create_default_context()
        if insecure:
            self._context.check_hostname = False
            self._context.verify_mode = ssl.CERT_NONE

    def search_page(self, variables: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        body = {
            "operationName": "SearchPage",
            "variables": variables,
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": SEARCH_PAGE_SHA256}},
        }
        request = urllib.request.Request(
            self._endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15, context=self._context) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
            except ValueError as parse_error:
                raise ProbeFailure(
                    "gateway_unavailable",
                    f"/graphql returned HTTP {exc.code} without JSON body: {raw[:200]}",
                ) from parse_error
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProbeFailure("gateway_unavailable", f"/graphql transport failed: {exc}") from exc
        errors = payload.get("errors") or []
        data = payload.get("data") or {}
        slice_payload = data.get("searchPage") if isinstance(data, dict) else None
        return slice_payload, errors


def _search_input(query: str, *, tab: dict[str, Any], first: int = 10, after: str = "") -> dict[str, Any]:
    entry: dict[str, Any] = {"query": query, "first": first}
    if tab.get("objectTypes"):
        entry["objectTypes"] = tab["objectTypes"]
    if tab.get("contentTypes"):
        entry["contentTypes"] = tab["contentTypes"]
    if after:
        entry["after"] = after
    return {"input": entry}


def _require_slice(slice_payload: dict[str, Any] | None, errors: list[dict[str, Any]], *, context: str) -> dict[str, Any]:
    if errors:
        raise ProbeFailure(
            "contract_mismatch",
            f"{context}: unexpected GraphQL errors: {json.dumps(errors, ensure_ascii=False)[:300]}",
        )
    if not isinstance(slice_payload, dict):
        raise ProbeFailure("contract_mismatch", f"{context}: searchPage slice is missing")
    return slice_payload


def _item_refs(slice_payload: dict[str, Any]) -> list[str]:
    return [str(item.get("objectRef") or "") for item in slice_payload.get("items") or []]


def _check_slice_filter(client: GraphQLClient, query: str, tab: dict[str, Any], report: dict[str, Any]) -> None:
    context = f"tab={tab['tab']}"
    slice_payload, errors = client.search_page(_search_input(query, tab=tab))
    slice_payload = _require_slice(slice_payload, errors, context=context)
    items = slice_payload.get("items") or []
    if not str(slice_payload.get("searchRequestId") or "").strip():
        raise ProbeFailure("contract_mismatch", f"{context}: searchRequestId missing on wire")
    if not isinstance(slice_payload.get("matchedTerms"), list):
        raise ProbeFailure("contract_mismatch", f"{context}: matchedTerms missing on wire")
    if not isinstance(slice_payload.get("degradeSignals"), list):
        raise ProbeFailure("contract_mismatch", f"{context}: degradeSignals missing on wire")
    if not items:
        if tab.get("requireHits"):
            raise ProbeFailure("empty_index", f"{context}: empty result is not commercial evidence")
        report["steps"].append(
            {
                "name": f"tab_matrix_{tab['tab']}",
                "status": "skipped_empty",
                "reason": "no corpus for this optional filter; leak assertion vacuously holds",
            }
        )
        return
    allowed_result_types = set(tab["objectTypes"] or [])
    for position, item in enumerate(items):
        result_type = str(item.get("resultType") or "")
        if allowed_result_types and result_type not in allowed_result_types:
            raise ProbeFailure(
                "filter_leak",
                f"{context}: item resultType {result_type} escaped the objectTypes filter",
            )
        if tab.get("contentTypes"):
            content_type = str(item.get("contentType") or "").upper()
            if content_type not in set(tab["contentTypes"]):
                raise ProbeFailure(
                    "filter_leak",
                    f"{context}: item contentType {content_type} escaped the contentTypes filter",
                )
        rank_position = item.get("rankPosition")
        if not isinstance(rank_position, int) or rank_position < 0:
            raise ProbeFailure(
                "contract_mismatch",
                f"{context}: rankPosition missing or invalid at index {position}",
            )
    report["steps"].append(
        {
            "name": f"tab_matrix_{tab['tab']}",
            "status": "passed",
            "itemCount": len(items),
        }
    )


def _check_tab_matrix(client: GraphQLClient, query: str, report: dict[str, Any]) -> None:
    for tab in TAB_MATRIX:
        _check_slice_filter(client, query, tab, report)
    for tab in FILTER_ASSERTIONS:
        _check_slice_filter(client, query, tab, report)


def _check_pagination(client: GraphQLClient, query: str, report: dict[str, Any]) -> None:
    tab = TAB_MATRIX[0]
    first_slice, errors = client.search_page(_search_input(query, tab=tab, first=3))
    first_slice = _require_slice(first_slice, errors, context="pagination first page")
    first_refs = _item_refs(first_slice)
    cursor = str(first_slice.get("nextCursor") or "")
    if len(first_refs) < 3 or not cursor:
        report["steps"].append(
            {
                "name": "pagination_continuity",
                "status": "skipped",
                "reason": "corpus too small for a continuation page",
            }
        )
        return
    seen = set(first_refs)
    pages = 1
    while cursor and pages < 5:
        next_slice, errors = client.search_page(_search_input(query, tab=tab, first=3, after=cursor))
        next_slice = _require_slice(next_slice, errors, context=f"pagination page {pages + 1}")
        refs = _item_refs(next_slice)
        for ref in refs:
            if ref in seen:
                raise ProbeFailure("pagination_drift", f"cursor pagination duplicated {ref}")
            seen.add(ref)
        cursor = str(next_slice.get("nextCursor") or "")
        pages += 1
    report["steps"].append(
        {"name": "pagination_continuity", "status": "passed", "pages": pages, "distinctItems": len(seen)}
    )


def _check_invalid_vocabulary(client: GraphQLClient, query: str, report: dict[str, Any]) -> None:
    variables = {"input": {"query": query, "first": 5, "objectTypes": ["content.post"]}}
    slice_payload, errors = client.search_page(variables)
    if slice_payload is not None or not errors:
        raise ProbeFailure(
            "vocabulary_leak",
            "internal object type 'content.post' must be rejected by GraphQL enum validation",
        )
    report["steps"].append({"name": "invalid_vocabulary_rejected", "status": "passed"})


def _check_repeat_consistency(client: GraphQLClient, query: str, repeat: int, report: dict[str, Any]) -> None:
    baseline: list[str] | None = None
    for attempt in range(repeat):
        slice_payload, errors = client.search_page(_search_input(query, tab=TAB_MATRIX[0], first=10))
        slice_payload = _require_slice(slice_payload, errors, context=f"repeat #{attempt + 1}")
        refs = _item_refs(slice_payload)
        if baseline is None:
            baseline = refs
            if not baseline:
                raise ProbeFailure("empty_index", "repeat consistency has no hits to compare")
        elif refs != baseline:
            raise ProbeFailure(
                "repeatability_drift",
                f"repeat #{attempt + 1} TopN drifted: baseline={baseline} got={refs}",
            )
    report["steps"].append(
        {"name": "repeat_consistency", "status": "passed", "repeat": repeat, "topN": len(baseline or [])}
    )


def _write_report(path: Path, report: dict[str, Any]) -> Path:
    target = path if path.is_absolute() else REPO_ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    args = _parse_args()
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "scenario": SCENARIO,
        "status": "running",
        "failureCategory": "",
        "blockingReason": "",
        "startedAt": _utc_now(),
        "endedAt": "",
        "environment": {"env": args.env, "gatewayBaseUrl": args.base_url.rstrip("/")},
        "query": args.query,
        "steps": [],
    }
    return_code = 1
    try:
        client = GraphQLClient(args.base_url, insecure=args.insecure)
        _check_tab_matrix(client, args.query, report)
        _check_pagination(client, args.query, report)
        _check_invalid_vocabulary(client, args.query, report)
        _check_repeat_consistency(client, args.query, args.repeat, report)
        report["status"] = "passed"
        return_code = 0
    except ProbeFailure as exc:
        report["status"] = "failed"
        report["failureCategory"] = exc.category
        report["blockingReason"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "failed"
        report["failureCategory"] = "unexpected_error"
        report["blockingReason"] = f"{type(exc).__name__}: {exc}"
    finally:
        report["endedAt"] = _utc_now()
        target = _write_report(Path(args.report), report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "scenario": SCENARIO,
                    "report": str(target),
                    "failureCategory": report["failureCategory"],
                },
                ensure_ascii=False,
            )
        )
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
