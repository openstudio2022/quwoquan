"""Crawler discovery and fetch helpers for site-supply."""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import functools
import hashlib
import json
import math
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.io import read_json, write_json
from _common.paths import DATA_ROOT, RUNTIME_ROOT, now_iso
from download.fetch import fetch_image_payload, fetch_source_payload

from site_supply.core import *  # noqa: F403
from site_supply.packets import *  # noqa: F403
from site_supply.targets import *  # noqa: F403
from site_supply.reports import *  # noqa: F403
from site_supply import bridge

def _read_seed_file(path: str | None) -> list[str]:
    if not path:
        return []
    seed_path = Path(path)
    if not seed_path.is_file():
        raise SystemExit(f"seed file not found: {seed_path}")
    urls: list[str] = []
    for line in seed_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            urls.append(stripped)
    return urls

def _dedupe_query_terms(values: list[str] | tuple[str, ...], *, limit: int = 0) -> list[str]:
    terms: list[str] = []
    for value in values:
        term = str(value or "").strip()
        if not term or term in terms:
            continue
        if term in FRONTIER_META_QUERY_TERMS:
            continue
        if term.startswith(("测试", "景区甲", "景区乙", "景区丙", "缺源", "快速失败", "可继续", "已修好", "空底稿")):
            continue
        terms.append(term)
        if limit and len(terms) >= int(limit):
            break
    return terms

def _task_coverage_query_terms(*, limit: int = 500) -> list[str]:
    terms: list[str] = []
    tasks_root = DATA_ROOT / "tasks"
    if not tasks_root.is_dir():
        return []
    for path in sorted(tasks_root.glob("**/task.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(data, Mapping):
            continue
        scope = data.get("scope") if isinstance(data.get("scope"), Mapping) else {}
        for item in scope.get("coverageTargets") or []:
            if isinstance(item, Mapping):
                name = str(item.get("name") or "").strip()
                aliases = sorted(_entity_name_aliases(name), key=lambda term: (term == name, len(term), term))
                terms.extend(_dedupe_query_terms([*aliases, name]))
        terms = _dedupe_query_terms(terms, limit=limit)
        if limit and len(terms) >= int(limit):
            break
    return terms

def _travel_frontier_query_terms(*, manual_queries: list[str] | None = None, limit: int = 500) -> list[str]:
    reserve_count = len(manual_queries or []) + len(TRAVEL_FRONTIER_SEED_QUERIES)
    coverage_limit = max(0, int(limit) - reserve_count) if limit else 0
    coverage_terms = _task_coverage_query_terms(limit=coverage_limit)
    return _dedupe_query_terms(
        [
            *(manual_queries or []),
            *coverage_terms,
            *TRAVEL_FRONTIER_SEED_QUERIES,
        ],
        limit=limit,
    )

def _mediawiki_title_allowed(title: str) -> bool:
    normalized = str(title or "").strip()
    if not normalized or ":" in normalized:
        return False
    if normalized.startswith(MEDIAWIKI_DISALLOWED_TITLE_PREFIXES):
        return False
    if normalized in {"首页", "主頁", "主页", "Main Page"}:
        return False
    # Wikivoyage district subpages are often shells or sparse stubs; keep them
    # out of frontier so fetch does not spend budget on predictable rejects.
    if "/" in normalized:
        return False
    if "消歧义" in normalized or "disambiguation" in normalized.lower():
        return False
    return True

def _mediawiki_url_allowed(url: str) -> bool:
    parsed = urllib.parse.urlparse(str(url or ""))
    if not (parsed.hostname or "").endswith("wikivoyage.org"):
        return True
    if "/wiki/" not in parsed.path:
        return False
    title = urllib.parse.unquote(parsed.path.split("/wiki/", 1)[1].split("#")[0]).replace("_", " ")
    return _mediawiki_title_allowed(title)

def _mediawiki_search_row_allowed(row: Mapping[str, Any], *, min_size_bytes: int = MEDIAWIKI_MIN_SIZE_BYTES) -> bool:
    if int(row.get("ns") or 0) != 0:
        return False
    if not _mediawiki_title_allowed(str(row.get("title") or "")):
        return False
    if int(row.get("wordcount") or 0) < MEDIAWIKI_MIN_WORDCOUNT:
        return False
    if int(row.get("size") or 0) < max(MEDIAWIKI_MIN_SIZE_BYTES, int(min_size_bytes)):
        return False
    return True

def _mediawiki_title_matches_query_terms(title: str, terms: list[str] | tuple[str, ...]) -> bool:
    normalized_title = re.sub(r"\s+", "", str(title or "").strip()).lower()
    if not normalized_title:
        return False
    normalized_terms = [
        re.sub(r"\s+", "", str(term or "").strip()).lower()
        for term in terms
        if str(term or "").strip()
    ]
    if not normalized_terms:
        return True
    if normalized_title in normalized_terms:
        return True
    return any(len(term) >= 3 and term in normalized_title for term in normalized_terms)

def _mediawiki_current_query_title_terms(query: str) -> list[str]:
    terms = [str(query or "").strip()]
    query_target = bridge.call(
        "_resolve_known_entity_target",
        _resolve_known_entity_target,
        query,
        expected_entity_type="地点/景区",
    )
    if query_target:
        terms.extend(_entity_name_aliases(str(query_target.get("name") or "")))
    return _dedupe_query_terms(terms)

def _qunar_search_candidates(
    *,
    queries: list[str],
    max_pages: int,
    limit: int,
    window: Mapping[str, Any],
    request_budget: int,
    request_timeout: int = 20,
    discovery_timeout_seconds: float = 0.0,
    progress_callback: Any | None = None,
) -> list[dict[str, Any]]:
    if not queries or limit <= 0:
        return []
    from download.research_plan import _curl_json  # Reuse existing entity-line discovery IO.

    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    requests_used = 0
    start = _date(str(window.get("from")))
    end = _date(str(window.get("to")))

    started = time.monotonic()

    def report(status: str, *, query: str = "", page: int = 0, message: str = "") -> None:
        if progress_callback is None:
            return
        progress_callback(
            status=status,
            requests_used=requests_used,
            discovered_count=len(candidates),
            query=query,
            page=page,
            message=message,
        )

    report("running", message="qunar discovery started")
    for query in queries:
        encoded = urllib.parse.quote(query)
        for page in range(1, max(1, int(max_pages)) + 1):
            if requests_used >= int(request_budget):
                report("budget_exhausted", query=query, page=page, message="frontier discovery request budget exhausted")
                return candidates
            if (
                float(discovery_timeout_seconds or 0.0) > 0
                and (time.monotonic() - started) >= float(discovery_timeout_seconds)
            ):
                report("timeout", query=query, page=page, message="frontier discovery elapsed budget exhausted")
                return candidates
            requests_used += 1
            data = _curl_json(
                f"https://touch.travel.qunar.com/search?_json&q={encoded}&page={page}",
                timeout=int(request_timeout),
            )
            report("running", query=query, page=page)
            if data.get("ret") is not True:
                if requests_used >= int(request_budget):
                    report(
                        "budget_exhausted",
                        query=query,
                        page=page,
                        message="frontier discovery request budget exhausted before fallback search",
                    )
                    return candidates
                if (
                    float(discovery_timeout_seconds or 0.0) > 0
                    and (time.monotonic() - started) >= float(discovery_timeout_seconds)
                ):
                    report("timeout", query=query, page=page, message="frontier discovery elapsed budget exhausted")
                    return candidates
                requests_used += 1
                data = _curl_json(
                    f"https://touch.travel.qunar.com/search?_json=&q={encoded}&page={page}",
                    timeout=int(request_timeout),
                )
                report("running", query=query, page=page)
            payload = data.get("data") if isinstance(data.get("data"), Mapping) else {}
            rows = payload.get("bookList") if isinstance(payload.get("bookList"), list) else []
            if not rows:
                break
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                raw_id = str(row.get("id") or "").strip()
                if not raw_id:
                    continue
                published_at = _timestamp_ms_to_date(row.get("startTime") or row.get("cTime") or row.get("uTime"))
                if published_at:
                    published = _date(published_at)
                    if published < start or published > end:
                        continue
                url = f"https://touch.travel.qunar.com/youji/{raw_id}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                route = [str(item).strip() for item in (row.get("travelRoute") or []) if str(item).strip()]
                dests = [str(item).strip() for item in (row.get("destCities") or []) if str(item).strip()]
                city = str(row.get("cityName") or "").strip()
                query_target = bridge.call(
                    "_resolve_known_entity_target",
                    _resolve_known_entity_target,
                    query,
                    expected_entity_type="地点/景区",
                )
                query_mentions = [
                    f"{query_target['entityType']}/{query_target['name']}"
                ] if query_target else []
                entity_mentions = [x for x in [*query_mentions, city, *dests, *route[:8]] if x]
                candidates.append(
                    {
                        "url": url,
                        "lane": "article",
                        "title": re.sub(r"<[^>]+>", "", str(row.get("title") or "")).strip(),
                        "author": re.sub(r"<[^>]+>", "", str(row.get("userName") or "")).strip(),
                        "publishedAt": published_at,
                        "entityMentions": entity_mentions[:12],
                        "tagMentions": ["Topic/旅行/玩法/自然风光", "Source/去哪儿攻略/游记"],
                        "discovery": {
                            "provider": "qunar_touch_search_json",
                            "query": query,
                            "page": page,
                            "sourceId": raw_id,
                            "viewCount": row.get("viewCount") or 0,
                        },
                    }
                )
                if len(candidates) >= limit:
                    report("completed", query=query, page=page, message="frontier discovery reached target")
                    return candidates
    report("completed", message="frontier discovery exhausted query set")
    return candidates

def _mediawiki_search_candidates(
    *,
    host: str,
    provider: str,
    queries: list[str],
    max_pages: int,
    limit: int,
    request_budget: int,
    min_size_bytes: int = MEDIAWIKI_MIN_SIZE_BYTES,
    title_terms: list[str] | None = None,
    request_timeout: int = 20,
    discovery_timeout_seconds: float = 0.0,
    progress_callback: Any | None = None,
) -> list[dict[str, Any]]:
    if not queries or limit <= 0:
        return []
    from download.research_plan import _curl_json

    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    requests_used = 0
    started = time.monotonic()

    def report(status: str, *, query: str = "", page: int = 0, message: str = "") -> None:
        if progress_callback is None:
            return
        progress_callback(
            status=status,
            requests_used=requests_used,
            discovered_count=len(candidates),
            query=query,
            page=page,
            message=message,
        )

    report("running", message="mediawiki discovery started")
    for query in queries:
        for page in range(1, max(1, int(max_pages)) + 1):
            if requests_used >= int(request_budget):
                report("budget_exhausted", query=query, page=page, message="frontier discovery request budget exhausted")
                return candidates
            if (
                float(discovery_timeout_seconds or 0.0) > 0
                and (time.monotonic() - started) >= float(discovery_timeout_seconds)
            ):
                report("timeout", query=query, page=page, message="frontier discovery elapsed budget exhausted")
                return candidates
            requests_used += 1
            params = urllib.parse.urlencode(
                {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": "20",
                    "sroffset": str((page - 1) * 20),
                    "srprop": "size|wordcount|timestamp",
                    "format": "json",
                }
            )
            data = _curl_json(f"https://{host}/w/api.php?{params}", timeout=int(request_timeout))
            report("running", query=query, page=page)
            rows = (((data.get("query") or {}).get("search")) if isinstance(data.get("query"), Mapping) else [])
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                if not _mediawiki_search_row_allowed(row, min_size_bytes=min_size_bytes):
                    continue
                title = str(row.get("title") or "").strip()
                current_title_terms = _mediawiki_current_query_title_terms(query)
                title_matches_current_query = _mediawiki_title_matches_query_terms(title, current_title_terms)
                if title_terms and not title_matches_current_query:
                    continue
                url_title = urllib.parse.quote(title.replace(" ", "_"), safe="")
                url = f"https://{host}/wiki/{url_title}"
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                query_target = bridge.call(
                    "_resolve_known_entity_target",
                    _resolve_known_entity_target,
                    query,
                    expected_entity_type="地点/景区",
                )
                query_mentions = (
                    [f"{query_target['entityType']}/{query_target['name']}"]
                    if query_target and title_matches_current_query else []
                )
                entity_mentions = [*query_mentions, title]
                candidates.append(
                    {
                        "url": url,
                        "lane": "article",
                        "title": title,
                        "author": "",
                        "publishedAt": "",
                        "entityMentions": entity_mentions,
                        "tagMentions": ["Topic/旅行/目的地指南", f"Source/{provider}/MediaWiki"],
                        "discovery": {
                            "provider": "mediawiki_search_api",
                        "site": provider,
                        "query": query,
                        "page": page,
                        "pageId": row.get("pageid") or "",
                        "size": row.get("size") or 0,
                        "wordcount": row.get("wordcount") or 0,
                    },
                }
            )
                if len(candidates) >= limit:
                    report("completed", query=query, page=page, message="frontier discovery reached target")
                    return candidates
    report("completed", message="frontier discovery exhausted query set")
    return candidates

def _mediawiki_site_index_candidates(
    *,
    host: str,
    provider: str,
    limit: int,
    request_budget: int,
    request_timeout: int = 20,
    discovery_timeout_seconds: float = 0.0,
    progress_callback: Any | None = None,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    from download.research_plan import _curl_json

    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    requests_used = 0
    continuation: dict[str, str] = {}
    page_limit = min(500, max(50, min(int(limit), 500)))
    started = time.monotonic()

    def report(status: str, *, message: str = "") -> None:
        if progress_callback is None:
            return
        progress_callback(
            status=status,
            requests_used=requests_used,
            discovered_count=len(candidates),
            message=message,
        )

    report("running", message="mediawiki allpages discovery started")
    while len(candidates) < int(limit):
        if requests_used >= int(request_budget):
            report("budget_exhausted", message="frontier discovery request budget exhausted")
            return candidates
        if (
            float(discovery_timeout_seconds or 0.0) > 0
            and (time.monotonic() - started) >= float(discovery_timeout_seconds)
        ):
            report("timeout", message="frontier discovery elapsed budget exhausted")
            return candidates
        params = {
            "action": "query",
            "generator": "allpages",
            "gapnamespace": "0",
            "gapfilterredir": "nonredirects",
            "gaplimit": str(page_limit),
            "prop": "info",
            "inprop": "url",
            "format": "json",
            **continuation,
        }
        url = f"https://{host}/w/api.php?{urllib.parse.urlencode(params)}"
        requests_used += 1
        data = _curl_json(url, timeout=int(request_timeout))
        report("running")
        pages = (((data.get("query") or {}).get("pages")) if isinstance(data.get("query"), Mapping) else {})
        if not isinstance(pages, Mapping):
            report("completed", message="mediawiki allpages response had no page map")
            return candidates
        for page in sorted(pages.values(), key=lambda item: str((item or {}).get("title") or "")):
            if not isinstance(page, Mapping):
                continue
            title = str(page.get("title") or "").strip()
            if not _mediawiki_title_allowed(title):
                continue
            if _safe_len := int(page.get("length") or 0):
                if _safe_len < MEDIAWIKI_MIN_SIZE_BYTES:
                    continue
            url = str(page.get("fullurl") or "").strip()
            if not url:
                url_title = urllib.parse.quote(title.replace(" ", "_"), safe="")
                url = f"https://{host}/wiki/{url_title}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(
                {
                    "url": url,
                    "lane": "article",
                    "title": title,
                    "author": "",
                    "publishedAt": "",
                    "entityMentions": [title],
                    "tagMentions": ["Topic/旅行/目的地指南", f"Source/{provider}/MediaWiki"],
                    "discovery": {
                        "provider": "mediawiki_allpages_api",
                        "site": provider,
                        "pageId": page.get("pageid") or "",
                        "length": page.get("length") or 0,
                    },
                }
            )
            if len(candidates) >= int(limit):
                report("completed", message="frontier discovery reached target")
                return candidates
        raw_continue = data.get("continue") if isinstance(data.get("continue"), Mapping) else {}
        gap_continue = str(raw_continue.get("gapcontinue") or "").strip()
        if not gap_continue:
            report("completed", message="frontier discovery exhausted allpages index")
            return candidates
        continuation = {
            key: str(raw_continue[key])
            for key in ("continue", "gapcontinue")
            if key in raw_continue and str(raw_continue.get(key) or "").strip()
        }
    report("completed", message="frontier discovery reached target")
    return candidates

def _crawl_input_candidates(args: argparse.Namespace, frontier: Mapping[str, Any]) -> list[dict[str, Any]]:
    target_count = max(0, int(getattr(args, "discovery_target_count", args.target_count) or 0))
    root = site_supply_root(args.vertical, args.site_id, args.batch)
    discovery_started = time.monotonic()
    discovery_request_timeout = int(getattr(args, "discovery_request_timeout", 20) or 20)
    discovery_timeout_seconds = float(getattr(args, "discovery_timeout_seconds", 0.0) or 0.0)
    latest_requests_used = 0

    def progress_callback(
        *,
        status: str,
        requests_used: int,
        discovered_count: int,
        query: str = "",
        page: int = 0,
        message: str = "",
    ) -> None:
        nonlocal latest_requests_used
        latest_requests_used = max(latest_requests_used, int(requests_used))
        _write_frontier_discovery_progress(
            root,
            status=status,
            target_count=int(getattr(args, "target_count", target_count) or target_count),
            discovery_target_count=target_count,
            discovered_count=discovered_count,
            request_budget=int(args.max_discovery_requests),
            requests_used=requests_used,
            query=query,
            page=page,
            started_monotonic=discovery_started,
            message=message,
        )

    progress_callback(
        status="running",
        requests_used=0,
        discovered_count=0,
        message="frontier discovery started",
    )
    explicit_urls = _split_csv(args.seed_urls) + _read_seed_file(args.seed_file)
    if args.site_id == "wikivoyage_zh":
        explicit_urls = [url for url in explicit_urls if _mediawiki_url_allowed(url)]
    candidates: list[dict[str, Any]] = [
        {
            "url": url,
            "lane": args.lane,
            "title": "",
            "author": "",
            "publishedAt": args.end_date,
            "entityMentions": _split_csv(args.entity_mentions),
            "tagMentions": _split_csv(args.tag_mentions),
            "discovery": {"provider": "explicit_seed"},
        }
        for url in explicit_urls
    ]
    seen = {row["url"] for row in candidates}
    remaining = target_count - len(candidates) if target_count else 0
    manual_queries = _split_csv(args.queries)
    query_strategy = str(getattr(args, "query_strategy", QUERY_STRATEGY_MANUAL) or QUERY_STRATEGY_MANUAL)
    queries = (
        _travel_frontier_query_terms(manual_queries=manual_queries)
        if query_strategy == QUERY_STRATEGY_TRAVEL_FRONTIER else manual_queries
    )
    if remaining > 0 and args.site_id == "qunar_guide":
        for row in bridge.call(
            "_qunar_search_candidates",
            _qunar_search_candidates,
            queries=queries,
            max_pages=args.max_search_pages,
            limit=remaining,
            window=frontier.get("timeWindow") or {},
            request_budget=args.max_discovery_requests,
            request_timeout=discovery_request_timeout,
            discovery_timeout_seconds=discovery_timeout_seconds,
            progress_callback=progress_callback,
        ):
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            candidates.append(row)
            if target_count and len(candidates) >= target_count:
                break
    elif remaining > 0 and args.site_id == "wikivoyage_zh":
        if query_strategy == QUERY_STRATEGY_SITE_INDEX:
            mediawiki_rows = _mediawiki_site_index_candidates(
                host="zh.wikivoyage.org",
                provider="维基导游",
                limit=remaining,
                request_budget=args.max_discovery_requests,
                request_timeout=discovery_request_timeout,
                discovery_timeout_seconds=discovery_timeout_seconds,
                progress_callback=progress_callback,
            )
        else:
            mediawiki_rows = _mediawiki_search_candidates(
                host="zh.wikivoyage.org",
                provider="维基导游",
                queries=queries,
                max_pages=args.max_search_pages,
                limit=remaining,
                request_budget=args.max_discovery_requests,
                min_size_bytes=max(MEDIAWIKI_MIN_SIZE_BYTES, int(args.min_text_chars) * 6),
                title_terms=queries,
                request_timeout=discovery_request_timeout,
                discovery_timeout_seconds=discovery_timeout_seconds,
                progress_callback=progress_callback,
            )
        for row in mediawiki_rows:
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            candidates.append(row)
            if target_count and len(candidates) >= target_count:
                break
    progress_callback(
        status="completed" if len(candidates) >= target_count else "underfilled",
        requests_used=latest_requests_used,
        discovered_count=len(candidates),
        message="frontier discovery candidate selection completed",
    )
    if target_count:
        return candidates[:target_count]
    return candidates

def _rate_limit_seconds(profile: Mapping[str, Any]) -> float:
    rate = profile.get("rateLimit") if isinstance(profile.get("rateLimit"), Mapping) else {}
    rps = rate.get("maxRequestsPerSecond")
    try:
        value = float(rps)
    except (TypeError, ValueError):
        return 0.0
    if value <= 0:
        return 0.0
    return 1.0 / value

def _classify_fetch_packet(packet: Mapping[str, Any]) -> tuple[int, int, int, int]:
    fetch = packet.get("fetch") if isinstance(packet.get("fetch"), Mapping) else {}
    status = int(fetch.get("statusCode") or 0)
    blockers = "\n".join(str(x) for x in ((packet.get("gate") or {}).get("blockers") or []))
    http_429 = 1 if status == 429 or "status=429" in blockers else 0
    http_403 = 1 if status == 403 or "status=403" in blockers else 0
    probe = 1 if "probe/error page detected" in blockers else 0
    empty = 1 if "fetch body is empty" in blockers or "empty response" in blockers else 0
    return http_429, http_403, probe, empty

def _rollup_observed_counts(root: Path) -> dict[str, int | float]:
    fetch_paths = sorted((root / "fetches").glob("*/site_fetch_packet.json"))
    map_paths = sorted((root / "map").glob("*/site_map_packet.json"))
    http_429 = http_403 = probe_pages = empty_extract = dead_letters = 0
    for path in fetch_paths:
        packet = read_json(path)
        c429, c403, cprobe, cempty = _classify_fetch_packet(packet)
        http_429 += c429
        http_403 += c403
        probe_pages += cprobe
        empty_extract += cempty
        fetch = packet.get("fetch") if isinstance(packet.get("fetch"), Mapping) else {}
        if not _packet_gate_passed(packet) and str(fetch.get("error") or "").strip():
            dead_letters += 1
    handoff_count = 0
    for path in map_paths:
        packet = read_json(path)
        if ((packet.get("contentPlanHandoff") or {}).get("eligible")):
            handoff_count += 1
    return {
        "http429Count": http_429,
        "http403Count": http_403,
        "probePageCount": probe_pages,
        "emptyExtractCount": empty_extract,
        "deadLetterCount": dead_letters,
        "handoffCount": handoff_count,
        "fetchCount": len(fetch_paths),
        "firstPassRate": (handoff_count / len(fetch_paths)) if fetch_paths else 0.0,
    }

def _observed_objects_per_hour_from_stage_results(root: Path) -> float:
    timestamps: list[dt.datetime] = []
    for path in sorted((root / "fetches").glob("*/stage_result.json")):
        try:
            result = read_json(path)
        except Exception:
            continue
        raw = str(result.get("createdAt") or "").strip()
        if not raw:
            continue
        try:
            timestamps.append(dt.datetime.fromisoformat(raw.replace("Z", "+00:00")))
        except ValueError:
            continue
    if len(timestamps) < 2:
        return 0.0
    elapsed_hours = (max(timestamps) - min(timestamps)).total_seconds() / 3600
    if elapsed_hours <= 0:
        return 0.0
    return len(timestamps) / elapsed_hours

def _recomputed_site_rollup_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    objects_per_hour: float | None = None,
) -> dict[str, Any]:
    root = site_supply_root(vertical, site_id, batch_id)
    previous_path = root / "_shared" / "site_rollup_report.json"
    previous = read_json(previous_path) if previous_path.is_file() else {}
    execution = previous.get("executionReadiness") if isinstance(previous.get("executionReadiness"), Mapping) else {}
    measured = execution.get("measuredThroughput") if isinstance(execution.get("measuredThroughput"), Mapping) else {}
    observed = _rollup_observed_counts(root)
    downstream = _downstream_readiness_from_reports(vertical, site_id, batch_id)
    measured_objects_per_hour = float(measured.get("objectsPerHour") or 0.0)
    effective_objects_per_hour = float(objects_per_hour) if objects_per_hour is not None else measured_objects_per_hour
    if effective_objects_per_hour <= 0:
        effective_objects_per_hour = _observed_objects_per_hour_from_stage_results(root)
    return build_site_rollup_report(
        vertical=vertical,
        site_id=site_id,
        batch_id=batch_id,
        objects_per_hour=effective_objects_per_hour,
        first_pass_rate=float(observed["firstPassRate"]),
        token_ledger_count=int(execution.get("tokenLedgerCount") or observed["handoffCount"]),
        release_verified=bool(execution.get("releaseVerified")) or downstream["releaseVerified"],
        import_verified=bool(execution.get("importVerified")) or downstream["importVerified"],
        search_visible=bool(execution.get("searchVisible")) or downstream["searchVisible"],
        recommendation_feedback_ready=(
            bool(execution.get("recommendationFeedbackReady")) or downstream["recommendationFeedbackReady"]
        ),
        http_429_count=int(observed["http429Count"]),
        http_403_count=int(observed["http403Count"]),
        probe_page_count=int(observed["probePageCount"]),
        empty_extract_count=int(observed["emptyExtractCount"]),
        dead_letter_count=int(observed["deadLetterCount"]),
    )

def _fetch_with_retry(
    url: str,
    *,
    source: Mapping[str, Any] | None = None,
    retry_budget: int,
    retry_delay_seconds: float,
) -> tuple[Mapping[str, Any] | None, str, int]:
    attempts = 0
    last_error = ""
    for attempt in range(0, max(0, int(retry_budget)) + 1):
        attempts += 1
        try:
            return bridge.call("fetch_source_payload", fetch_source_payload, url, source=source), "", attempts
        except Exception as exc:
            last_error = str(exc)
            if attempt >= int(retry_budget):
                break
            delay = max(float(retry_delay_seconds), float(attempt + 1))
            time.sleep(min(delay, 10.0))
    return None, last_error, attempts

__all__ = [name for name in globals() if not name.startswith("__")]
