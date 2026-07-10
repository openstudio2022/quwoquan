"""Deterministic public-source research plan bootstrap.

This fills the source/research lane with auditable public sources before a
semantic Agent is needed. It is intentionally conservative: it writes only
empty lane plans unless --force is passed, and it leaves explicit gaps when a
source cannot be discovered from registered public endpoints.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.parse
from typing import Any

from download.research import network_breaker
from download.research.auto_plan_public import write_auto_research_plans
from download.research.auto_plan_report import (
    _AUTO_DISCOVERY_REPORT,
    _merge_auto_reports,
    _source_availability_summary,
    _write_auto_report_artifacts,
)
from download.research.auto_plan_writer import _write_auto_research_plans_impl
from download.research.plan_state import (
    _DOWNLOAD_REJECT_MEMORY_BATCH_LIMIT,
    _VERIFIED_IMAGE_PLAN_SCAN_LIMIT,
    _accept_source,
    _accept_source_with_reject_memory,
    _add_url_memory,
    _collections_from_image_plan,
    _download_reject_memory,
    _entity_download_dirs_for_history,
    _filter_rejected_images,
    _homepage_urls_from_current_plan,
    _image_at,
    _image_window,
    _images_from_collections,
    _normalize_collection_for_reuse,
    _plan_has_payload,
    _record_unavailable,
    _reject_source_candidate,
    _safe_collection_id,
    _source,
    _source_reject_should_enter_memory,
    _source_unavailable_for_entity,
    _sources_from_article_plan,
    _task_batch_dirs_recency,
    _task_content_quotas,
    _task_spec,
    _url_in_memory,
    _url_memory_keys,
    _urls_from_issue_text,
    _verified_article_sources_from_prior_plans,
    _verified_homepage_sources_from_source_units,
    _verified_image_collections_from_prior_plans,
    _write_lane,
)
from download.research.progress import _now_iso, _write_auto_research_progress
from download.research.source_quality import (
    _ARTICLE_BASE_CATEGORIES,
    _HOMEPAGE_CORE_SOURCE_LIMIT,
    _HOMEPAGE_DISAMBIG_LINE_RE,
    _HOMEPAGE_DISAMBIG_MARKERS,
    _HOMEPAGE_FACT_MARKERS,
    _HOMEPAGE_FACT_UNIT_RE,
    _HOMEPAGE_INSECT_CONTEXT_RE,
    _HOMEPAGE_JSON_API_RE,
    _HOMEPAGE_NAVIGATION_MARKERS,
    _HOMEPAGE_PAREN_LOCATION_LINE_RE,
    _HOMEPAGE_REDIRECT_MARKERS,
    _HOMEPAGE_STATION_CONTEXT_RE,
    _HOMEPAGE_TEXT_EVIDENCE_REQUIRED_DOMAINS,
    _MAX_PUBLISHABLE_IMAGE_PIXELS,
    _SUPPORTING_ONLY_CATEGORIES,
    _TRAVEL_SOURCE_REGISTRY,
    _article_base_candidate_limit,
    _candidate_gate,
    _collection_gate,
    _collection_image_spec,
    _collection_publishable_image_urls,
    _evidence_reason,
    _homepage_can_seed_base_draft,
    _homepage_candidate_has_fetch_evidence,
    _homepage_core_sources,
    _homepage_entity_tokens,
    _homepage_fact_signal_count,
    _homepage_plan_sort_key,
    _homepage_requires_text_snapshot,
    _homepage_text_quality_issue,
    _image_conflicts_with_entity,
    _image_mentions_entity,
    _image_pixel_issue,
    _known_article_sources,
    _known_entity_aliases,
    _known_homepage_support_websites,
    _known_image_reject_terms,
    _known_image_search_hints,
    _known_official_website,
    _license_allows_app_publish,
    _select_article_plan_sources,
    _source_category,
    _source_has_text_snapshot,
    _travel_registry_url_fetchable,
)
from download.research.text_match import (
    _EN_ALIAS_SUFFIX_RE,
    _WIKI_TITLE_ALLOWED_ALIAS_EXACT_2CHAR,
    _WIKI_TITLE_ALLOWED_SUFFIXES,
    _WIKI_TITLE_BLOCKED_SUBSTITUTES,
    _dedupe_terms,
    _entity_name_variants,
    _expanded_entity_aliases,
    _normalized_title,
    _text_mentions_entity,
    _title_matches_entity,
    _wiki_resolved_title_matches_entity,
    _wiki_title_matches_entity,
)
from download.research.wiki_discovery import (
    _BASE_DRAFT_IMAGE_CANDIDATES,
    _OPENVERSE_API,
    _QUNAR_SEARCH_API,
    _RELATED_WIKI_SUFFIXES,
    _TRUSTED_EXTERNAL_DOMAINS,
    _claim_string_values,
    _commons_category_images,
    _commons_images,
    _commons_images_for_titles,
    _discover_open_license_image_pools,
    _external_article_category,
    _external_platform,
    _image_search_terms,
    _mediawiki_page_images,
    _official_website,
    _openverse_images,
    _qunar_review_support_source,
    _qunar_travelogue_sources,
    _strip_html,
    _trusted_external_links,
    _url_looks_like_article,
    _wikidata_claims,
    _wikidata_commons_images,
    _wikidata_entity_aliases,
    _wikidata_item_for_entity_search,
    _wikidata_item_for_zhwiki,
    _wiki_related_titles,
    _wiki_related_titles_for_entity,
    _wiki_title,
    _wiki_title_for_entity,
    _wiki_url,
)

_USER_AGENT = "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"
_AUTO_RESEARCH_CURL_TIMEOUT_SECONDS = max(
    3,
    int(os.environ.get("QWQ_AUTO_RESEARCH_CURL_TIMEOUT_SECONDS", "25")),
)
_AUTO_RESEARCH_CURL_RETRIES = max(
    1,
    int(os.environ.get("QWQ_AUTO_RESEARCH_CURL_RETRIES", "1")),
)


def _curl_raw(url: str, *, timeout: int) -> tuple[int, bytes]:
    """共享 curl 执行 + 网络断路器：出口故障时对已打开 host 秒级短路。

    网络级失败（DNS/连接/超时/SSL，见 NETWORK_CURL_EXIT_CODES）计入断路器；
    内容级失败（HTTP 错误体/解析失败）不计入。任一成功复位该 host。
    """
    if network_breaker.BREAKER.is_open(url) or network_breaker.wave_budget_exceeded():
        return -1, b""
    effective_timeout = max(3, int(timeout or _AUTO_RESEARCH_CURL_TIMEOUT_SECONDS))
    effective_retries = max(1, int(_AUTO_RESEARCH_CURL_RETRIES))
    proc = subprocess.run(
        [
            "curl", "-sS", "-L", "-A", _USER_AGENT,
            "--retry", str(effective_retries), "--retry-delay", "1", "--retry-all-errors",
            "--max-time", str(effective_timeout),
            url,
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        network_breaker.BREAKER.record_success(url)
    elif proc.returncode in network_breaker.NETWORK_CURL_EXIT_CODES:
        network_breaker.BREAKER.record_network_failure(url)
    stdout = proc.stdout if isinstance(proc.stdout, bytes) else bytes(str(proc.stdout or ""), "utf-8")
    return proc.returncode, stdout


def _curl_json(url: str, *, timeout: int = 25) -> dict[str, Any]:
    returncode, stdout = _curl_raw(url, timeout=timeout)
    if returncode != 0:
        return {}
    try:
        data = json.loads(stdout.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _curl_text(url: str, *, timeout: int = 25) -> str:
    returncode, stdout = _curl_raw(url, timeout=timeout)
    if returncode != 0:
        return ""
    return stdout.decode("utf-8", errors="replace")


def _wiki_api(host: str, params: dict[str, str | int]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    return _curl_json(f"https://{host}/w/api.php?{query}")


def handle_research_plan(args: argparse.Namespace) -> None:
    lane_arg = str(getattr(args, "lane", "all") or "all")
    lanes = None if lane_arg == "all" else {lane_arg}
    report = write_auto_research_plans(
        str(args.task),
        str(args.batch),
        [item.strip() for item in str(args.entity_ids or "").split(",") if item.strip()],
        entity_type=str(args.entity_type or ""),
        force=bool(getattr(args, "force", False)),
        lanes=lanes,
        max_workers=int(getattr(args, "max_workers", 1) or 1),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("issues") and getattr(args, "strict", False):
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    def _add_common(name: str, help_text: str) -> argparse.ArgumentParser:
        p = subparsers.add_parser(name, help=help_text)
        p.add_argument("--task", required=True)
        p.add_argument("--batch", required=True)
        p.add_argument("--entity-ids", required=True)
        p.add_argument("--entity-type", default="")
        p.add_argument("--lane", choices=("all", "homepage", "article", "image"), default="all")
        p.add_argument("--max-workers", type=int, default=1, help="Entity-level source discovery concurrency")
        p.add_argument("--force", action="store_true", help="Overwrite non-empty lane plans")
        p.add_argument("--strict", action="store_true", help="Exit non-zero when public-source discovery has gaps")
        p.set_defaults(handler=handle_research_plan)
        return p

    _add_common(
        "research-plan",
        "Bootstrap separated homepage/article/image source plans from registered public sources",
    )
    _add_common(
        "source-discover",
        "Discover and gate source candidates for one or more separated research lanes",
    )
