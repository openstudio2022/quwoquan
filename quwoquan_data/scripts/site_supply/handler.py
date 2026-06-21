"""qwq-data site-supply — 网站维度内容供给线前半段契约与门禁。

本模块只做站点级 frontier/candidate/score/map/rollup 的 IO、契约和门禁。
真实语义抽取与正文创作仍由 Agent 与现有 content_plan/produce/review 主线承接。
"""
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


FRONTIER_SCHEMA = "quwoquan.site_supply.site_frontier_packet/1"
FRONTIER_CANDIDATES_SCHEMA = "quwoquan.site_supply.site_frontier_candidates/1"
FETCH_SCHEMA = "quwoquan.site_supply.site_fetch_packet/1"
CANDIDATE_SCHEMA = "quwoquan.site_supply.site_candidate_packet/1"
SCORE_SCHEMA = "quwoquan.site_supply.site_score_packet/1"
MAP_SCHEMA = "quwoquan.site_supply.site_map_packet/1"
ROLLUP_SCHEMA = "quwoquan.site_supply.site_rollup_report/1"
QUALITY_DISTRIBUTION_SCHEMA = "quwoquan.site_supply.quality_distribution_report/1"
DOWNSTREAM_E2E_SCHEMA = "quwoquan.site_supply.downstream_e2e_report/1"
DISCOVERY_PROGRESS_SCHEMA = "quwoquan.site_supply.frontier_discovery_progress/1"
GATE_SCHEMA = "quwoquan.site_supply.gate_report/1"
STAGE_SCHEMA = "quwoquan.site_supply.stage_result/1"
REPAIR_SCHEMA = "quwoquan.site_supply.repair_report/1"

DEFAULT_TIME_WINDOW_DAYS = 730
DEFAULT_DAILY_TARGET = 100_000
MIN_ARTICLE_TEXT_CHARS = 80
MIN_CONTENT_PLAN_ARTICLE_TEXT_CHARS = 600
MIN_PRODUCTION_SCORE = 0.45
DEFAULT_FETCH_MIN_TEXT_CHARS = 120
MAX_DEAD_LETTER_RATE = 0.02
MAX_EMPTY_EXTRACT_RATE = 0.05
MAX_THROTTLE_FORBIDDEN_RATE = 0.05
MAX_PROBE_PAGE_RATE = 0.02
MEDIAWIKI_MIN_WORDCOUNT = 80
MEDIAWIKI_MIN_SIZE_BYTES = 1600
MEDIAWIKI_DISALLOWED_TITLE_PREFIXES = ("昔日",)
ADMISSION_BATCH_CRAWL = "batch_crawl"
ADMISSION_CONTROLLED_TRIAL = "controlled_trial"
ADMISSION_MODES = (ADMISSION_BATCH_CRAWL, ADMISSION_CONTROLLED_TRIAL)
QUERY_STRATEGY_MANUAL = "manual"
QUERY_STRATEGY_TRAVEL_FRONTIER = "travel_frontier"
QUERY_STRATEGY_SITE_INDEX = "site_index"
QUERY_STRATEGIES = (QUERY_STRATEGY_MANUAL, QUERY_STRATEGY_TRAVEL_FRONTIER, QUERY_STRATEGY_SITE_INDEX)
REQUIRED_ASSET_RIGHTS_FIELDS = ("license", "credit", "sourceUrl", "termsUrl", "usageScope")
FRONTIER_META_QUERY_TERMS = {"中国", "全国", "网站供给线"}
TRAVEL_RELEVANCE_TITLE_TERMS = (
    "旅行", "旅游", "景区", "景点", "机场", "国道", "海岸线", "自行车道", "徒步", "自驾"
)
TRAVEL_RELEVANCE_BODY_TERMS = (
    "旅行", "旅游", "游客", "景区", "景点", "门票", "开放时间", "交通", "住宿", "餐馆",
    "观光", "抵达", "周游", "活动", "购物", "饮食", "夜生活", "入場", "入场", "安全",
    "下一站", "机场", "铁路", "汽车", "公路", "路线", "自驾", "徒步", "目的地"
)
TRAVEL_RELEVANCE_SECTION_MARKERS = (
    "== 抵达 ==", "== 抵達 ==", "== 周游 ==", "== 周遊 ==", "== 观光 ==",
    "== 觀光 ==", "== 活动 ==", "== 活動 ==", "== 购物 ==", "== 購物 ==",
    "== 饮食 ==", "== 飲食 ==", "== 住宿 ==", "== 安全 ==", "== 下一站 ==",
)
SITE_SUPPLY_STAGES = (
    "site_frontier",
    "site_fetch",
    "site_extract",
    "site_score",
    "site_map",
    "content_plan",
    "produce_review",
    "ship_import",
)
OBJECT_TRIPLET_FILES = ("stage_result.json", "gate_report.json", "repair_report.json")
TRAVEL_FRONTIER_SEED_QUERIES = (
    "北京", "上海", "成都", "重庆", "西安", "杭州", "南京", "苏州", "广州", "深圳",
    "厦门", "青岛", "大理", "丽江", "昆明", "三亚", "桂林", "张家界", "黄山", "九寨沟",
    "新疆", "西藏", "云南", "贵州", "四川", "福建", "浙江", "江苏", "广东", "广西",
    "湖南", "湖北", "河南", "河北", "山东", "山西", "陕西", "甘肃", "青海", "内蒙古",
    "东北", "川西", "江南", "海南", "周末游", "自驾游", "亲子游", "徒步", "古镇", "海岛",
    "雪山", "草原",
)


def site_supply_root(vertical: str, site_id: str, batch_id: str) -> Path:
    return RUNTIME_ROOT / "site_supply" / vertical / site_id / batch_id


def _site_registry_path(vertical: str) -> Path:
    return DATA_ROOT / "verticals" / vertical / "sources" / "source_registry.yaml"


def _load_vertical_source_registry(vertical: str) -> dict[str, Any]:
    path = _site_registry_path(vertical)
    if not path.is_file():
        raise FileNotFoundError(f"missing source registry: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: registry must be an object")
    return data


def _find_site(vertical: str, site_id: str) -> dict[str, Any]:
    data = _load_vertical_source_registry(vertical)
    for site in data.get("sites") or []:
        if isinstance(site, dict) and str(site.get("siteId") or "") == site_id:
            return site
    raise KeyError(f"{vertical}: unknown siteId {site_id}")


def _split_csv(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(str(value)[:10])


def _time_window(days: int, *, end_date: str | None = None, start_date: str | None = None) -> dict[str, str | int]:
    end = _date(end_date) if end_date else dt.date.today()
    start = _date(start_date) if start_date else end - dt.timedelta(days=int(days))
    return {"from": start.isoformat(), "to": end.isoformat(), "days": (end - start).days}


def _stable_ref(prefix: str, *parts: object) -> str:
    raw = "|".join(str(x) for x in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha1(raw).hexdigest()[:16]}"


def _int_with_default(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _profile_from_site(site: Mapping[str, Any], *, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    profile = dict(site.get("siteCrawlProfile") or {})
    profile.update({k: v for k, v in dict(overrides or {}).items() if v not in (None, "", [])})
    content_lanes = profile.get("contentLanes") or profile.get("lanes") or ["article"]
    allowed_paths = profile.get("allowedPaths") or site.get("urlPatterns") or []
    return {
        "siteId": str(site.get("siteId") or ""),
        "platform": str(site.get("platform") or ""),
        "domains": [str(x) for x in (profile.get("domains") or site.get("domains") or []) if str(x)],
        "allowedPaths": [str(x) for x in allowed_paths if str(x)],
        "contentLanes": [str(x) for x in content_lanes if str(x)],
        "fetchMode": str(profile.get("fetchMode") or site.get("fetchMode") or "html"),
        "extractor": str(profile.get("extractor") or site.get("extractor") or "generic_html"),
        "rightsPolicy": str(profile.get("rightsPolicy") or site.get("licensePolicy") or ""),
        "rateLimit": profile.get("rateLimit") or {"mode": str(site.get("rateLimit") or "conservative")},
        "robotsPolicy": str(profile.get("robotsPolicy") or "respect_robots_txt"),
        "loginPolicy": str(profile.get("loginPolicy") or "public_only"),
        "watermarkPolicy": str(profile.get("watermarkPolicy") or "reject_watermarked_publish_assets"),
        "termsUrl": str(profile.get("termsUrl") or site.get("termsUrl") or ""),
        "maxDepth": _int_with_default(profile.get("maxDepth"), 2),
        "maxPagesPerDay": _int_with_default(profile.get("maxPagesPerDay"), 0),
        "crawlAllowed": bool(profile.get("crawlAllowed", False)),
        "fetchable": bool(site.get("fetchable")),
        "sourceCategory": str(site.get("category") or ""),
        "qualityTier": str(site.get("qualityTier") or ""),
        "controlledTrial": dict(profile.get("controlledTrial") or {}),
        "rawProfilePresent": bool(site.get("siteCrawlProfile")),
    }


def _profile_gate(
    profile: Mapping[str, Any],
    *,
    daily_target: int,
    queue_backend: str,
    time_window: Mapping[str, Any],
    admission_mode: str = ADMISSION_BATCH_CRAWL,
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    controlled = profile.get("controlledTrial") if isinstance(profile.get("controlledTrial"), Mapping) else {}
    admission_mode = admission_mode if admission_mode in ADMISSION_MODES else ADMISSION_BATCH_CRAWL
    if not profile.get("rawProfilePresent"):
        blockers.append("siteCrawlProfile missing from source registry")
    if admission_mode == ADMISSION_CONTROLLED_TRIAL:
        if not (bool(controlled.get("allowed")) or (profile.get("fetchable") and profile.get("crawlAllowed"))):
            blockers.append("controlledTrial.allowed must be true or site must be fetchable+crawlAllowed")
        if controlled and not bool(controlled.get("validationOnly", True)):
            blockers.append("controlledTrial.validationOnly must remain true")
        if bool(controlled.get("rawFetchAllowed")):
            blockers.append("controlledTrial.rawFetchAllowed cannot be true")
        if not str(profile.get("termsUrl") or "").strip():
            blockers.append("siteCrawlProfile.termsUrl is required for controlled trial")
        if not (profile.get("fetchable") and profile.get("crawlAllowed")):
            warnings.append("controlled trial does not grant raw batch crawl; generated candidates are validation-only")
    else:
        if not profile.get("fetchable"):
            blockers.append("fetchable=false sites cannot enter batch site crawl")
        if not profile.get("crawlAllowed"):
            blockers.append("siteCrawlProfile.crawlAllowed must be true for batch crawl")
    if not profile.get("domains"):
        blockers.append("siteCrawlProfile.domains must not be empty")
    if not profile.get("allowedPaths"):
        blockers.append("siteCrawlProfile.allowedPaths must not be empty")
    if not profile.get("contentLanes"):
        blockers.append("siteCrawlProfile.contentLanes must not be empty")
    if not profile.get("rightsPolicy"):
        blockers.append("siteCrawlProfile.rightsPolicy must be explicit")
    if str(profile.get("robotsPolicy") or "") in {"ignore", "bypass"}:
        blockers.append("robotsPolicy cannot bypass robots/terms")
    if str(profile.get("loginPolicy") or "") not in {"public_only", "manual_authorization_required"}:
        blockers.append("loginPolicy must be public_only or manual_authorization_required")
    if int(time_window.get("days") or 0) > DEFAULT_TIME_WINDOW_DAYS + 1:
        blockers.append("site crawl time window must be within the latest two years")
    if int(daily_target) >= DEFAULT_DAILY_TARGET and queue_backend != "reliabletask":
        blockers.append("daily target >=100000 requires queueBackend=reliabletask")
    if int(profile.get("maxPagesPerDay") or 0) <= 0:
        if admission_mode == ADMISSION_CONTROLLED_TRIAL:
            warnings.append("maxPagesPerDay=0; controlled trial must not perform raw fetch")
        else:
            warnings.append("maxPagesPerDay=0; crawler must run in discovery-only dry mode")
    return blockers, warnings


def _gate_report(stage: str, blockers: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "schemaVersion": GATE_SCHEMA,
        "stage": stage,
        "passed": not blockers,
        "decision": "pass" if not blockers else "fail",
        "blockers": blockers,
        "warnings": warnings,
        "createdAt": now_iso(),
    }


def _stage_result(stage: str, outputs: list[str], gate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": STAGE_SCHEMA,
        "stage": stage,
        "status": "succeeded" if gate.get("passed") else "blocked",
        "outputs": outputs,
        "gateReport": f"{stage}/gate_report.json",
        "repairReport": f"{stage}/repair_report.json",
        "createdAt": now_iso(),
    }


def _repair_report(stage: str, blockers: list[str]) -> dict[str, Any]:
    return {
        "schemaVersion": REPAIR_SCHEMA,
        "stage": stage,
        "required": bool(blockers),
        "fallbackStage": stage if blockers else "",
        "reasons": blockers,
        "createdAt": now_iso(),
    }


def _write_stage_triplet(root: Path, stage: str, outputs: list[str], gate: Mapping[str, Any]) -> None:
    stage_dir = root / stage
    write_json(stage_dir / "gate_report.json", dict(gate))
    write_json(stage_dir / "stage_result.json", _stage_result(stage, outputs, gate))
    write_json(stage_dir / "repair_report.json", _repair_report(stage, list(gate.get("blockers") or [])))


def _write_stage_triplet_append_outputs(
    root: Path,
    stage: str,
    outputs: list[str],
    gate: Mapping[str, Any],
) -> None:
    stage_dir = root / stage
    previous_outputs: list[str] = []
    previous_path = stage_dir / "stage_result.json"
    if previous_path.is_file():
        try:
            previous = read_json(previous_path)
        except Exception:
            previous = {}
        if isinstance(previous, Mapping):
            previous_outputs = [str(item) for item in (previous.get("outputs") or [])]
    merged_outputs = list(dict.fromkeys(previous_outputs + [str(item) for item in outputs]))
    _write_stage_triplet(root, stage, merged_outputs, gate)


def _write_object_triplet(object_dir: Path, stage: str, outputs: list[str], gate: Mapping[str, Any]) -> None:
    write_json(object_dir / "gate_report.json", dict(gate))
    write_json(object_dir / "stage_result.json", _stage_result(stage, outputs, gate))
    write_json(object_dir / "repair_report.json", _repair_report(stage, list(gate.get("blockers") or [])))


def _object_triplet_missing(object_dir: Path) -> list[str]:
    return [name for name in OBJECT_TRIPLET_FILES if not (object_dir / name).is_file()]


def build_site_frontier_packet(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    daily_target: int = DEFAULT_DAILY_TARGET,
    queue_backend: str = "reliabletask",
    lanes: list[str] | None = None,
    time_window_days: int = DEFAULT_TIME_WINDOW_DAYS,
    start_date: str | None = None,
    end_date: str | None = None,
    entry_urls: list[str] | None = None,
    allowed_paths: list[str] | None = None,
    admission_mode: str = ADMISSION_BATCH_CRAWL,
) -> dict[str, Any]:
    site = _find_site(vertical, site_id)
    overrides = {
        "contentLanes": lanes,
        "allowedPaths": allowed_paths,
    }
    profile = _profile_from_site(site, overrides=overrides)
    window = _time_window(time_window_days, end_date=end_date, start_date=start_date)
    blockers, warnings = _profile_gate(
        profile,
        daily_target=daily_target,
        queue_backend=queue_backend,
        time_window=window,
        admission_mode=admission_mode,
    )
    frontier_urls = entry_urls or list(profile["allowedPaths"])
    next_stage = "site_fetch" if admission_mode == ADMISSION_BATCH_CRAWL else "site_extract"
    packet = {
        "schemaVersion": FRONTIER_SCHEMA,
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "workspaceRoot": str(site_supply_root(vertical, site_id, batch_id)),
        "sourceRegistryRef": str(_site_registry_path(vertical).relative_to(DATA_ROOT)),
        "admissionMode": admission_mode,
        "profile": profile,
        "timeWindow": window,
        "dailyTarget": int(daily_target),
        "queuePolicy": {
            "backend": queue_backend,
            "requiredForScale": "reliabletask",
            "partitionKeyPattern": "vertical|siteId|dateBucket|lane|candidateRef|stage",
        },
        "frontier": {
            "entryUrls": frontier_urls,
            "dedupeKey": "canonicalUrl",
            "stages": list(SITE_SUPPLY_STAGES),
        },
        "handoff": {
            "next": next_stage if not blockers else "",
            "contentPlanOnlyAfter": "site_map",
            "mustReuse": ["source_unit", "assets/index.json", "content_plan_packet", "review_ledger"],
        },
        "gate": _gate_report("site_frontier", blockers, warnings),
        "createdAt": now_iso(),
    }
    return packet


def write_site_frontier_packet(packet: Mapping[str, Any]) -> Path:
    root = site_supply_root(str(packet["vertical"]), str(packet["siteId"]), str(packet["batchId"]))
    path = root / "site_frontier" / "site_frontier_packet.json"
    write_json(path, dict(packet))
    write_json(root / "_shared" / "site_supply_manifest.json", {
        "schemaVersion": "quwoquan.site_supply.manifest/1",
        "vertical": packet["vertical"],
        "siteId": packet["siteId"],
        "batchId": packet["batchId"],
        "workspaceRoot": str(root),
        "frontierPacket": str(path),
        "createdAt": now_iso(),
    })
    _write_stage_triplet(root, "site_frontier", [str(path)], packet["gate"])
    return path


def _frontier_packet(vertical: str, site_id: str, batch_id: str) -> dict[str, Any]:
    return read_json(site_supply_root(vertical, site_id, batch_id) / "site_frontier" / "site_frontier_packet.json")


def _write_frontier_candidates(root: Path, rows: list[Mapping[str, Any]]) -> Path:
    path = root / "site_frontier" / "site_frontier_candidates.json"
    payload = {
        "schemaVersion": FRONTIER_CANDIDATES_SCHEMA,
        "candidateCount": len(rows),
        "candidates": [
            {
                "candidateRef": _fetch_candidate_ref(str(row.get("url") or "")),
                "url": str(row.get("url") or ""),
                "lane": str(row.get("lane") or "article"),
                "title": str(row.get("title") or ""),
                "publishedAt": str(row.get("publishedAt") or ""),
                "author": str(row.get("author") or ""),
                "entityMentions": [str(x) for x in (row.get("entityMentions") or [])],
                "tagMentions": [str(x) for x in (row.get("tagMentions") or [])],
                "discovery": dict(row.get("discovery") or {}) if isinstance(row.get("discovery"), Mapping) else {},
            }
            for row in rows
        ],
        "createdAt": now_iso(),
    }
    write_json(path, payload)
    return path


def _write_frontier_discovery_progress(
    root: Path,
    *,
    status: str,
    target_count: int,
    discovery_target_count: int,
    discovered_count: int,
    request_budget: int,
    requests_used: int,
    query: str = "",
    page: int = 0,
    started_monotonic: float | None = None,
    message: str = "",
) -> Path:
    elapsed_seconds = 0.0
    if started_monotonic is not None:
        elapsed_seconds = max(time.monotonic() - started_monotonic, 0.0)
    path = root / "site_frontier" / "discovery_progress.json"
    write_json(
        path,
        {
            "schemaVersion": DISCOVERY_PROGRESS_SCHEMA,
            "stage": "site_frontier",
            "status": status,
            "targetCount": int(target_count),
            "discoveryTargetCount": int(discovery_target_count),
            "discoveredCount": int(discovered_count),
            "remainingCount": max(int(discovery_target_count) - int(discovered_count), 0),
            "requestBudget": int(request_budget),
            "requestsUsed": int(requests_used),
            "query": str(query or ""),
            "page": int(page or 0),
            "elapsedSeconds": round(elapsed_seconds, 3),
            "message": str(message or ""),
            "updatedAt": now_iso(),
        },
    )
    return path


def _host_allowed(domains: list[str], host: str) -> bool:
    normalized = host.lower()
    return any(normalized == d.lower() or normalized.endswith(f".{d.lower()}") for d in domains)


def _url_allowed(frontier: Mapping[str, Any], url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    profile = frontier.get("profile") or {}
    if not _host_allowed([str(x) for x in (profile.get("domains") or [])], host):
        return False
    allowed_paths = [str(x) for x in (profile.get("allowedPaths") or []) if str(x)]
    if not allowed_paths:
        return False
    normalized = urllib.parse.urlunparse(parsed)
    for pattern in allowed_paths:
        if pattern.startswith("http://") or pattern.startswith("https://"):
            if fnmatch.fnmatch(normalized, pattern):
                return True
        elif pattern.startswith("/") and parsed.path.startswith(pattern):
            return True
        elif fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def _probe_text_reason(text: str, title: str = "") -> str:
    haystack = f"{title}\n{text}".strip()
    if not haystack:
        return "empty fetch text"
    probe_tokens = (
        "非常抱歉，您访问的页面不存在",
        "访问的页面不存在",
        "访问异常",
        "安全验证",
        "请完成验证",
        "登录后查看",
        "captcha",
        "robot check",
    )
    for token in probe_tokens:
        if token.lower() in haystack.lower():
            return f"probe/error page detected: {token}"
    return ""


def _first_text_line(text: str, fallback: str = "") -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if len(stripped) >= 4:
            return stripped[:120]
    return str(fallback or "").strip()[:120]


def _wiki_title_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "/wiki/" not in parsed.path:
        return ""
    raw = parsed.path.split("/wiki/", 1)[1].split("#", 1)[0].split("?", 1)[0]
    return urllib.parse.unquote(raw).replace("_", " ").strip()


def _timestamp_ms_to_date(value: Any) -> str:
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return ""
    if raw <= 0:
        return ""
    return dt.datetime.fromtimestamp(raw / 1000, tz=dt.timezone.utc).date().isoformat()


def _fetch_candidate_ref(url: str) -> str:
    return _stable_ref("candidate", url)


def build_site_fetch_packet(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    url: str,
    lane: str = "article",
    title: str = "",
    author: str = "",
    published_at: str | None = None,
    entity_mentions: list[str] | None = None,
    tag_mentions: list[str] | None = None,
    min_text_chars: int = DEFAULT_FETCH_MIN_TEXT_CHARS,
    payload: Mapping[str, Any] | None = None,
    error: str = "",
    attempts: int = 0,
) -> dict[str, Any]:
    frontier = _frontier_packet(vertical, site_id, batch_id)
    profile = frontier.get("profile") if isinstance(frontier.get("profile"), Mapping) else {}
    blockers: list[str] = []
    warnings: list[str] = []
    if str(frontier.get("admissionMode") or ADMISSION_BATCH_CRAWL) != ADMISSION_BATCH_CRAWL:
        blockers.append("site_fetch is only allowed for batch_crawl admission")
    if not ((frontier.get("gate") or {}).get("passed")):
        blockers.append("site_frontier gate did not pass; repair at site_frontier")
    if lane not in set(profile.get("contentLanes") or []):
        blockers.append(f"lane {lane!r} is not allowed by site frontier")
    if not _url_allowed(frontier, url):
        blockers.append("fetch url is outside site frontier domains/allowedPaths")

    status_code = int((payload or {}).get("statusCode") or 0)
    text = str((payload or {}).get("text") or "")
    assets = [a for a in ((payload or {}).get("assets") or []) if isinstance(a, Mapping)]
    sha256 = str((payload or {}).get("sha256") or "")
    html_bytes = (payload or {}).get("htmlBytes")
    content_length = len(html_bytes) if isinstance(html_bytes, (bytes, bytearray)) else 0
    runtime = (payload or {}).get("runtime") if isinstance((payload or {}).get("runtime"), Mapping) else {}
    if error:
        blockers.append(f"fetch failed: {error}")
    if payload is not None:
        if status_code != 200:
            blockers.append(f"fetch statusCode must be 200; got {status_code}")
        if content_length <= 0:
            blockers.append("fetch body is empty")
        if len(text.strip()) < int(min_text_chars):
            blockers.append(f"fetch extracted text is too short (<{int(min_text_chars)} chars)")
        probe_reason = _probe_text_reason(text, title)
        if probe_reason:
            blockers.append(probe_reason)
    elif not error and not blockers:
        warnings.append("fetch payload missing; packet is preflight-only")

    url_title = _wiki_title_from_url(url)
    extracted_title = title.strip() or url_title or _first_text_line(text, fallback=url)
    entities = [str(value).strip() for value in (entity_mentions or []) if str(value).strip()]
    if not entities and url_title:
        entities = [url_title]
    packet = {
        "schemaVersion": FETCH_SCHEMA,
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "candidateRef": _fetch_candidate_ref(url),
        "lane": lane,
        "canonicalUrl": url,
        "source": {
            "platform": profile.get("platform") or site_id,
            "extractor": profile.get("extractor") or "",
            "rightsPolicy": profile.get("rightsPolicy") or "",
            "termsUrl": profile.get("termsUrl") or "",
            "admissionMode": frontier.get("admissionMode") or ADMISSION_BATCH_CRAWL,
            "validationOnly": False,
        },
        "fetch": {
            "attempted": payload is not None or bool(error),
            "attempts": int(attempts or (1 if (payload is not None or error) else 0)),
            "statusCode": status_code,
            "contentLength": content_length,
            "sha256": sha256,
            "error": error,
            "runtime": dict(runtime),
        },
        "extraction": {
            "title": extracted_title,
            "author": author.strip(),
            "publishedAt": published_at or "",
            "textChars": len(text.strip()),
            "text": text.strip(),
            "assets": assets,
        },
        "semanticMentions": {
            "entities": entities,
            "tags": tag_mentions or [],
            "state": "mention_only",
        },
        "gate": _gate_report("site_fetch", blockers, warnings),
        "createdAt": now_iso(),
    }
    return packet


def write_site_fetch_packet(
    packet: Mapping[str, Any],
    *,
    html_bytes: bytes | None = None,
) -> Path:
    root = site_supply_root(str(packet["vertical"]), str(packet["siteId"]), str(packet["batchId"]))
    ref = str(packet["candidateRef"])
    object_dir = root / "fetches" / ref
    path = object_dir / "site_fetch_packet.json"
    payload = dict(packet)
    if html_bytes:
        raw_dir = object_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "page.html").write_bytes(html_bytes)
        text = str(((payload.get("extraction") or {}).get("text")) or "")
        (raw_dir / "source.md").write_text(text, encoding="utf-8")
        payload["fetch"] = {
            **dict(payload.get("fetch") or {}),
            "htmlPath": str(raw_dir / "page.html"),
            "sourceMdPath": str(raw_dir / "source.md"),
        }
    write_json(path, payload)
    _write_object_triplet(object_dir, "site_fetch", [str(path)], payload["gate"])
    _write_stage_triplet(root, "site_fetch", [str(path)], payload["gate"])
    return path


def build_site_candidate_from_fetch(fetch_packet: Mapping[str, Any]) -> dict[str, Any]:
    extraction = fetch_packet.get("extraction") if isinstance(fetch_packet.get("extraction"), Mapping) else {}
    mentions = fetch_packet.get("semanticMentions") if isinstance(fetch_packet.get("semanticMentions"), Mapping) else {}
    return build_site_candidate_packet(
        vertical=str(fetch_packet["vertical"]),
        site_id=str(fetch_packet["siteId"]),
        batch_id=str(fetch_packet["batchId"]),
        url=str(fetch_packet["canonicalUrl"]),
        lane=str(fetch_packet.get("lane") or "article"),
        title=str(extraction.get("title") or ""),
        text=str(extraction.get("text") or ""),
        published_at=str(extraction.get("publishedAt") or "") or None,
        author=str(extraction.get("author") or ""),
        assets=[dict(a) for a in (extraction.get("assets") or []) if isinstance(a, Mapping)],
        entity_mentions=[str(x) for x in (mentions.get("entities") or [])],
        tag_mentions=[str(x) for x in (mentions.get("tags") or [])],
    )


def _parse_assets(raw: str | None, *, source_url: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    assets = []
    for idx, item in enumerate(_split_csv(raw), start=1):
        parts = item.split("|")
        asset = {
            "assetId": _stable_ref("asset", source_url, item, idx),
            "url": parts[0].strip(),
            "sourceUrl": source_url,
        }
        for key, value in zip(("license", "credit", "termsUrl", "usageScope", "modelReleaseStatus"), parts[1:]):
            asset[key] = value.strip()
        assets.append(asset)
    return assets


def build_site_candidate_packet(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    url: str,
    lane: str,
    title: str,
    text: str = "",
    published_at: str | None = None,
    author: str = "",
    assets: list[dict[str, Any]] | None = None,
    entity_mentions: list[str] | None = None,
    tag_mentions: list[str] | None = None,
) -> dict[str, Any]:
    frontier = _frontier_packet(vertical, site_id, batch_id)
    candidate_ref = _stable_ref("candidate", url)
    profile = frontier.get("profile") or {}
    admission_mode = str(frontier.get("admissionMode") or ADMISSION_BATCH_CRAWL)
    blockers: list[str] = []
    warnings: list[str] = []
    if not ((frontier.get("gate") or {}).get("passed")):
        blockers.append("site_frontier gate did not pass; repair at site_frontier")
    if lane not in set(profile.get("contentLanes") or []):
        blockers.append(f"lane {lane!r} is not allowed by site frontier")
    if not _url_allowed(frontier, url):
        blockers.append("candidate url is outside site frontier domains/allowedPaths")
    if not title.strip():
        blockers.append("candidate title is required")
    if lane in {"article", "homepage", "knowledgeCard"} and len(text.strip()) < MIN_ARTICLE_TEXT_CHARS:
        blockers.append(f"{lane} candidate text is too short (<{MIN_ARTICLE_TEXT_CHARS} chars)")
    if lane in {"image", "video"} and not assets:
        blockers.append(f"{lane} candidate requires at least one asset")
    if published_at:
        try:
            published = _date(published_at)
            start = _date(str((frontier.get("timeWindow") or {}).get("from")))
            end = _date(str((frontier.get("timeWindow") or {}).get("to")))
            if published < start or published > end:
                blockers.append("candidate publishedAt is outside the latest two-year window")
        except ValueError:
            blockers.append("candidate publishedAt must be ISO date")
    else:
        warnings.append("candidate publishedAt missing; freshness scoring will be conservative")

    source_ref = f"{vertical}:{site_id}:{candidate_ref}"
    packet = {
        "schemaVersion": CANDIDATE_SCHEMA,
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "candidateRef": candidate_ref,
        "lane": lane,
        "canonicalUrl": url,
        "source": {
            "sourceRef": source_ref,
            "platform": profile.get("platform") or site_id,
            "sourceKind": f"site_{lane}",
            "rightsPolicy": profile.get("rightsPolicy") or "",
            "extractor": profile.get("extractor") or "",
            "admissionMode": admission_mode,
            "validationOnly": admission_mode == ADMISSION_CONTROLLED_TRIAL,
            "termsUrl": profile.get("termsUrl") or "",
        },
        "title": title.strip(),
        "author": author.strip(),
        "publishedAt": published_at or "",
        "text": text.strip(),
        "assets": assets or [],
        "semanticMentions": {
            "entities": entity_mentions or [],
            "tags": tag_mentions or [],
            "state": "mention_only",
        },
        "dedupe": {
            "canonicalUrlHash": _stable_ref("url", url),
            "sourceCollectionId": _stable_ref("collection", site_id, url),
        },
        "gate": _gate_report("site_extract", blockers, warnings),
        "createdAt": now_iso(),
    }
    return packet


def write_site_candidate_packet(packet: Mapping[str, Any]) -> Path:
    root = site_supply_root(str(packet["vertical"]), str(packet["siteId"]), str(packet["batchId"]))
    ref = str(packet["candidateRef"])
    object_dir = root / "candidates" / ref
    path = object_dir / "site_candidate_packet.json"
    write_json(path, dict(packet))
    _write_object_triplet(object_dir, "site_extract", [str(path)], packet["gate"])
    _write_stage_triplet(root, "site_extract", [str(path)], packet["gate"])
    return path


def _candidate_path(root: Path, candidate_ref: str) -> Path:
    return root / "candidates" / candidate_ref / "site_candidate_packet.json"


def _score_path(root: Path, candidate_ref: str) -> Path:
    return root / "scores" / candidate_ref / "site_score_packet.json"


def _asset_rights_issues(assets: list[Mapping[str, Any]]) -> list[str]:
    issues: list[str] = []
    for asset in assets:
        asset_id = str(asset.get("assetId") or asset.get("url") or "asset")
        for field in REQUIRED_ASSET_RIGHTS_FIELDS:
            if not str(asset.get(field) or "").strip():
                issues.append(f"{asset_id}: missing asset rights field {field}")
        if asset.get("faceDetected") is True and str(asset.get("modelReleaseStatus") or "") not in {
            "not_required",
            "obtained",
            "editorial_only",
        }:
            issues.append(f"{asset_id}: face detected requires modelReleaseStatus")
    return issues


def _travel_relevance_signals(candidate: Mapping[str, Any]) -> dict[str, Any]:
    title = str(candidate.get("title") or "")
    text = str(candidate.get("text") or "")
    title_hits = [term for term in TRAVEL_RELEVANCE_TITLE_TERMS if term in title]
    body_hits = [term for term in TRAVEL_RELEVANCE_BODY_TERMS if term in text]
    section_hits = [marker for marker in TRAVEL_RELEVANCE_SECTION_MARKERS if marker in text]
    passed = bool(title_hits) or len(section_hits) >= 2 or len(set(body_hits)) >= 4
    return {
        "passed": passed,
        "titleHits": title_hits[:8],
        "bodyHits": sorted(set(body_hits))[:12],
        "sectionHits": section_hits[:8],
    }


def _vertical_relevance_issues(candidate: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    vertical = str(candidate.get("vertical") or "").strip()
    if vertical != "travel":
        return [], {"vertical": vertical, "passed": True, "policy": "not_applicable"}
    lane = str(candidate.get("lane") or "").strip()
    if lane in {"image", "video"}:
        return [], {"vertical": vertical, "passed": True, "policy": "media_lane_asset_context"}
    signals = _travel_relevance_signals(candidate)
    if signals.get("passed"):
        return [], {"vertical": vertical, **signals}
    return [
        "travel relevance gate: candidate lacks destination/logistics/scenic travel signals"
    ], {"vertical": vertical, **signals}


def build_site_score_packet(candidate: Mapping[str, Any], *, duplicate: bool = False) -> dict[str, Any]:
    text = str(candidate.get("text") or "")
    lane = str(candidate.get("lane") or "")
    assets = candidate.get("assets") if isinstance(candidate.get("assets"), list) else []
    blockers: list[str] = []
    warnings: list[str] = []
    quality = min(1.0, max(0.0, len(text) / 1200.0))
    visual = 1.0 if assets else (0.2 if lane in {"article", "homepage", "knowledgeCard"} else 0.0)
    rights_issues = _asset_rights_issues([a for a in assets if isinstance(a, Mapping)])
    rights_policy = str(((candidate.get("source") or {}).get("rightsPolicy")) or "")
    validation_only = bool(((candidate.get("source") or {}).get("validationOnly")))
    candidate_gate = candidate.get("gate") if isinstance(candidate.get("gate"), Mapping) else {}
    if candidate_gate and not candidate_gate.get("passed"):
        blockers.append("candidate gate did not pass; cannot score for production")
    if duplicate:
        blockers.append("duplicate semantic/canonical fingerprint")
    if lane in {"image", "video"} and rights_issues:
        blockers.extend(rights_issues)
    if rights_policy in {"reference_only", "blocked"}:
        blockers.append(f"rightsPolicy={rights_policy} cannot enter production")
    if not text.strip() and lane not in {"image", "video"}:
        blockers.append("empty extract cannot enter production")
    if quality < 0.10 and lane not in {"image", "video"}:
        warnings.append("text quality score is low; candidate may remain discovery-only")
    relevance_issues, relevance_signals = _vertical_relevance_issues(candidate)
    if not validation_only:
        blockers.extend(relevance_issues)
    # 作品 vs 随记判定：站点全站分类入库（真实抓取候选 moment/abandoned 不进 content_plan）。
    # validationOnly(受控试跑) 候选只落审计 verdict、不阻断，因其为结构试跑合成候选。
    from _common.content_source_registry import resolve_source_class
    from _common.works_classifier import classify_works

    platform = str(((candidate.get("source") or {}).get("platform")) or "")
    works_source_class = resolve_source_class(platform=platform)
    works_rights_blocked = rights_policy in {"reference_only", "blocked"} or (
        lane in {"image", "video"} and bool(rights_issues)
    )
    works_verdict = classify_works(
        str(candidate.get("candidateRef") or ""),
        source_class=works_source_class,
        source_text=text,
        narrative_volume=0,
        image_count=len([a for a in assets if isinstance(a, Mapping)]),
        declared_carrier=lane if lane in {"article", "image", "homepage", "knowledgeCard"} else "article",
        rights_blocked=works_rights_blocked,
    )
    works_decision = str(works_verdict.get("decision") or "")
    if not validation_only and works_decision != "work":
        blockers.append(
            f"works classifier: {works_decision} "
            f"(abandonReason={works_verdict.get('abandonReason')}, tier={works_verdict.get('sourceTier')}) "
            "随记/低专业度站点候选不进入全站分类入库"
        )
    score = round((quality * 0.42) + (visual * 0.18) + 0.20 + 0.20, 4)
    production_eligible = not blockers and score >= MIN_PRODUCTION_SCORE
    if not production_eligible and not blockers:
        blockers.append("candidate score below production threshold")
    return {
        "schemaVersion": SCORE_SCHEMA,
        "vertical": candidate.get("vertical"),
        "siteId": candidate.get("siteId"),
        "batchId": candidate.get("batchId"),
        "candidateRef": candidate.get("candidateRef"),
        "canonicalUrl": candidate.get("canonicalUrl"),
        "lane": lane,
        "scores": {
            "overall": score,
            "contentQuality": round(quality, 4),
            "visualQuality": round(visual, 4),
            "freshness": 0.2 if not candidate.get("publishedAt") else 0.8,
            "rightsSafety": 0.0 if rights_issues else 1.0,
            "dedupeValue": 0.0 if duplicate else 1.0,
        },
        "verticalRelevance": relevance_signals,
        "productionEligible": production_eligible,
        "worksDecision": works_decision,
        "worksCarrier": works_verdict.get("carrier"),
        "worksSourceTier": works_verdict.get("sourceTier"),
        "publishRecommendation": (
            "validation_only_handoff" if production_eligible and validation_only else (
                "publish_candidate" if production_eligible else "blocked"
            )
        ),
        "issues": blockers + warnings,
        "gate": _gate_report("site_score", blockers, warnings),
        "createdAt": now_iso(),
    }


def write_site_score_packet(packet: Mapping[str, Any]) -> Path:
    root = site_supply_root(str(packet["vertical"]), str(packet["siteId"]), str(packet["batchId"]))
    ref = str(packet["candidateRef"])
    path = _score_path(root, ref)
    write_json(path, dict(packet))
    _write_object_triplet(path.parent, "site_score", [str(path)], packet["gate"])
    _write_stage_triplet(root, "site_score", [str(path)], packet["gate"])
    return path


def build_site_map_packet(candidate: Mapping[str, Any], score: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not score.get("productionEligible"):
        blockers.append("site_score is not productionEligible")
    source_ref = str(((candidate.get("source") or {}).get("sourceRef")) or "")
    if not source_ref:
        blockers.append("candidate sourceRef missing")
    lane = str(candidate.get("lane") or "")
    content_type = {
        "article": "article",
        "image": "imagePost",
        "video": "videoPost",
        "homepage": "homepage",
        "knowledgeCard": "knowledgeCard",
    }.get(lane, lane)
    mentions = candidate.get("semanticMentions") if isinstance(candidate.get("semanticMentions"), Mapping) else {}
    if mentions.get("state") != "mention_only":
        blockers.append("site_map may only emit mention_only refs before entity/homepage review")
    entity_gap_candidates, unresolved_entity_mentions, topic_candidates = _site_map_knowledge_gap_candidates(
        [str(x).strip() for x in (mentions.get("entities") or []) if str(x).strip()]
    )
    if unresolved_entity_mentions:
        warnings.append("unverified entity mentions remain mention_only; no entity homepage candidate emitted")
    packet = {
        "schemaVersion": MAP_SCHEMA,
        "vertical": candidate.get("vertical"),
        "siteId": candidate.get("siteId"),
        "batchId": candidate.get("batchId"),
        "candidateRef": candidate.get("candidateRef"),
        "canonicalUrl": candidate.get("canonicalUrl"),
        "targetContentType": content_type,
        "contentPlanHandoff": {
            "eligible": not blockers,
            "evidenceRefs": [source_ref] if source_ref else [],
            "baseSourceRef": source_ref,
            "oneSourceOneWork": True,
            "assetReusePolicy": "one_work_only",
        },
        "semanticMentions": {
            "entities": list(mentions.get("entities") or []),
            "tags": list(mentions.get("tags") or []),
            "state": "mention_only",
        },
        "knowledgeGaps": {
            "entityHomepageCandidates": entity_gap_candidates,
            "unresolvedEntityMentions": unresolved_entity_mentions,
            "topicCandidates": topic_candidates,
            "tagCandidates": list(mentions.get("tags") or []),
        },
        "gate": _gate_report("site_map", blockers, warnings),
        "createdAt": now_iso(),
    }
    return packet


def write_site_map_packet(packet: Mapping[str, Any]) -> Path:
    root = site_supply_root(str(packet["vertical"]), str(packet["siteId"]), str(packet["batchId"]))
    ref = str(packet["candidateRef"])
    object_dir = root / "map" / ref
    path = object_dir / "site_map_packet.json"
    write_json(path, dict(packet))
    _write_object_triplet(object_dir, "site_map", [str(path)], packet["gate"])
    _write_stage_triplet(root, "site_map", [str(path)], packet["gate"])
    return path


def _map_path(root: Path, candidate_ref: str) -> Path:
    return root / "map" / candidate_ref / "site_map_packet.json"


def _existing_crawl_handoff_ready(root: Path, candidate_ref: str) -> bool:
    try:
        candidate = read_json(_candidate_path(root, candidate_ref))
        score = read_json(_score_path(root, candidate_ref))
        mapped = read_json(_map_path(root, candidate_ref))
    except (OSError, ValueError, TypeError):
        return False
    return (
        _packet_gate_passed(candidate)
        and _packet_gate_passed(score)
        and bool(score.get("productionEligible"))
        and _packet_gate_passed(mapped)
        and bool((mapped.get("contentPlanHandoff") or {}).get("eligible"))
    )


def _eligible_site_map_refs(root: Path) -> list[str]:
    refs: list[str] = []
    for path in sorted((root / "map").glob("*/site_map_packet.json")):
        try:
            packet = read_json(path)
        except Exception:
            continue
        if not _packet_gate_passed(packet):
            continue
        if not ((packet.get("contentPlanHandoff") or {}).get("eligible")):
            continue
        ref = str(packet.get("candidateRef") or path.parent.name).strip()
        if ref:
            refs.append(ref)
    return refs


def _source_category_for_site(site_id: str) -> str:
    if "wikivoyage" in site_id:
        return "wikivoyage"
    if "qunar" in site_id:
        return "travel_guide"
    return "platform_article"


def _site_candidate_ref_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff-]+", "_", value).strip("_") or "site_candidate"


def _entity_name_from_mention(value: str) -> str:
    parts = [part for part in str(value or "").strip().strip("/").split("/") if part]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    return parts[-1] if parts else str(value or "").strip()


def _typed_entity_mention(value: str) -> tuple[str, str]:
    parts = [part for part in str(value or "").strip().strip("/").split("/") if part]
    if parts and parts[0] == "entity":
        parts = parts[1:]
    if len(parts) >= 3:
        return "/".join(parts[:2]), "/".join(parts[2:])
    return "", ""


_ENTITY_ALIAS_SUFFIXES = (
    "风景名胜旅游区",
    "风景名胜区",
    "文化旅游区",
    "旅游度假区",
    "风景旅游区",
    "旅游景区",
    "风景区",
    "旅游区",
    "景区",
)
_ENTITY_ALIAS_SEPARATORS_RE = re.compile(r"[·•—－/、]+")


def _entity_name_aliases(name: str) -> set[str]:
    raw = str(name or "").strip()
    if not raw:
        return set()
    aliases = {raw}
    for suffix in _ENTITY_ALIAS_SUFFIXES:
        if raw.endswith(suffix) and len(raw) > len(suffix):
            aliases.add(raw[: -len(suffix)])
            break
    paren_prefix = re.split(r"[（(]", raw, maxsplit=1)[0].strip()
    if len(paren_prefix) >= 4:
        aliases.add(paren_prefix)
    for part in _ENTITY_ALIAS_SEPARATORS_RE.split(raw):
        part = part.strip()
        if len(part) < 2:
            continue
        if "（" in part or "(" in part or "）" in part or ")" in part:
            continue
        aliases.add(part)
        for suffix in _ENTITY_ALIAS_SUFFIXES:
            if part.endswith(suffix) and len(part) > len(suffix):
                aliases.add(part[: -len(suffix)])
                break
    return aliases


@functools.lru_cache(maxsize=1)
def _known_coverage_entity_targets() -> dict[str, tuple[dict[str, str], ...]]:
    targets: dict[str, list[dict[str, str]]] = {}
    tasks_root = DATA_ROOT / "tasks"
    if not tasks_root.is_dir():
        return {}
    for path in sorted(tasks_root.glob("**/task.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(data, Mapping):
            continue
        workflow_policy = data.get("workflowPolicy") if isinstance(data.get("workflowPolicy"), Mapping) else {}
        if workflow_policy.get("siteSupplyDynamicContentPlan"):
            continue
        scope = data.get("scope") if isinstance(data.get("scope"), Mapping) else {}
        for row in scope.get("coverageTargets") or []:
            if not isinstance(row, Mapping):
                continue
            name = str(row.get("name") or "").strip()
            entity_type = str(row.get("entityType") or "").strip().strip("/")
            if not name or not entity_type:
                continue
            target = {
                "name": name,
                "entityType": entity_type,
                "source": path.relative_to(DATA_ROOT).as_posix(),
            }
            for alias in _entity_name_aliases(name):
                targets.setdefault(alias, []).append(target)
    return {key: tuple(value) for key, value in targets.items()}


def _resolve_known_entity_target(name: str, *, expected_entity_type: str) -> dict[str, str] | None:
    raw_name = str(name or "").strip()
    known_targets = _known_coverage_entity_targets()
    options = [
        target
        for target in known_targets.get(raw_name, ())
        if not expected_entity_type or target.get("entityType") == expected_entity_type
    ]
    exact: dict[tuple[str, str], dict[str, str]] = {
        (str(target.get("entityType") or ""), str(target.get("name") or "")): target
        for target in options
        if str(target.get("name") or "") == raw_name
    }
    if len(exact) == 1:
        return next(iter(exact.values()))
    unique: dict[tuple[str, str], dict[str, str]] = {
        (str(target.get("entityType") or ""), str(target.get("name") or "")): target
        for target in options
    }
    if len(unique) == 1:
        return next(iter(unique.values()))
    return None


def _site_map_knowledge_gap_candidates(entity_mentions: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Split raw site mentions from verified entity-homepage gap candidates.

    Website-line extraction often starts from page titles. A title is useful
    evidence, but it is not enough to manufacture an entity/homepage gap. Only
    explicitly typed mentions or names already known in committed coverage
    targets can enter entityHomepageCandidates; everything else stays auditable
    as mention/topic material for later mapping.
    """
    entity_candidates: list[str] = []
    unresolved_mentions: list[str] = []
    topic_candidates: list[str] = []
    seen_entities: set[str] = set()
    seen_unresolved: set[str] = set()
    seen_topics: set[str] = set()
    for raw in entity_mentions:
        value = str(raw or "").strip()
        if not value:
            continue
        typed_entity_type, typed_entity_name = _typed_entity_mention(value)
        if typed_entity_type and typed_entity_name:
            candidate = f"{typed_entity_type}/{typed_entity_name}"
            if candidate not in seen_entities:
                entity_candidates.append(candidate)
                seen_entities.add(candidate)
            continue
        name = _entity_name_from_mention(value)
        if not name:
            continue
        known_target = _resolve_known_entity_target(name, expected_entity_type="")
        if known_target:
            candidate = f"{known_target.get('entityType')}/{known_target.get('name')}"
            if candidate not in seen_entities:
                entity_candidates.append(candidate)
                seen_entities.add(candidate)
            continue
        if name not in seen_unresolved:
            unresolved_mentions.append(name)
            seen_unresolved.add(name)
        if name not in seen_topics:
            topic_candidates.append(name)
            seen_topics.add(name)
    return entity_candidates, unresolved_mentions, topic_candidates


def _download_candidate_images(candidate: Mapping[str, Any], *, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    images: list[dict[str, Any]] = []
    issues: list[str] = []
    for asset in [a for a in (candidate.get("assets") or []) if isinstance(a, Mapping)][: max(1, int(limit))]:
        url = str(asset.get("url") or asset.get("sourceUrl") or "").strip()
        if not url:
            issues.append(f"{asset.get('assetId') or 'asset'}: missing image url")
            continue
        payload = fetch_image_payload(url)
        if payload is None:
            issues.append(f"{asset.get('assetId') or url}: image download failed or not an image")
            continue
        image = {
            **dict(asset),
            **payload,
            "url": str(payload.get("url") or url),
            "sourceUrl": str(asset.get("sourceUrl") or asset.get("collectionPageUrl") or url),
            "termsUrl": str(asset.get("termsUrl") or ""),
            "license": str(asset.get("license") or ""),
            "credit": str(asset.get("credit") or ""),
            "usageScope": str(asset.get("usageScope") or ""),
            "sourceCollectionId": str(asset.get("sourceCollectionId") or _stable_ref("collection", url)),
            "caption": str(asset.get("caption") or asset.get("fileTitle") or candidate.get("title") or ""),
            "relevance": str(candidate.get("title") or ""),
        }
        missing = [field for field in REQUIRED_ASSET_RIGHTS_FIELDS if not str(image.get(field) or "").strip()]
        if missing:
            issues.append(f"{asset.get('assetId') or url}: missing rights fields {missing}")
            continue
        images.append(image)
    return images, issues


def _content_plan_title(candidate: Mapping[str, Any], entity_name: str, intent_label: str) -> str:
    raw_title = str(candidate.get("title") or entity_name).strip()
    if raw_title and raw_title != entity_name:
        return f"{entity_name}·{intent_label}：{raw_title[:40]}"
    return f"{entity_name}·{intent_label}"


def _site_candidate_condition_context(text: str, *, source_ref: str) -> dict[str, Any]:
    """Derive a minimal auditable region context from site-candidate evidence.

    Entity-line content normally inherits conditionContext from the entity
    profile.  Website-line candidates can arrive before the entity homepage is
    fully built, so region-locked evidence terms must be carried forward from
    the candidate itself instead of being discovered only at release time.
    """
    from template.condition import REGION_LOCKED_TERMS

    hits = sorted({term for term in REGION_LOCKED_TERMS if term in str(text or "")})
    if not hits:
        return {}
    if any(term in hits for term in ("高原", "高反", "海拔")):
        label = "高原/高海拔"
    elif any(term in hits for term in ("雪山", "戈壁", "沙漠")):
        label = "山地/荒漠"
    elif any(term in hits for term in ("沿海", "海岛", "台风", "潮汐")):
        label = "沿海/海岛"
    elif any(term in hits for term in ("热带", "雨林")):
        label = "热带/雨林"
    else:
        label = "地域条件"
    return {
        "region": {
            "name": label,
            "label": label,
            "source": "site_candidate_evidence",
            "evidenceTerms": hits,
            "evidenceRef": source_ref,
        }
    }


def build_site_content_plan(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    task_id: str,
    target_batch: str,
    limit: int = 10,
    refs: list[str] | None = None,
    entity_type: str = "地点/景区",
    intent: str = "行前指南",
    audience: str = "leisureTraveler",
    max_images_per_candidate: int = 3,
    allow_partial: bool = False,
) -> dict[str, Any]:
    from _common.base_draft import extract_base_draft_body
    from _common.content_source_registry import resolve_source_class
    from _common.content_plan import CONTENT_PLAN_SCHEMA, validate_content_plan
    from _common.content_object import write_brief_object
    from _common.paths import (
        batch_content_plan_packet_path,
        batch_root,
        committed_task_spec,
        ensure_batch_layout,
        relative_batch_ref,
    )
    from _common.release_integrity import MIN_ARTICLE_BASE_DRAFT_CHARS
    from _common.source_unit import resolve_entity_object_dir, write_source_unit
    from _common.works_classifier import classify_works
    from _common.batch_manifest import write_batch_manifest
    from plan.brief import hydrate_entity_condition_context, resolve_compose_brief
    from template.registry import TemplateRegistry
    from template.router import RouteRequest

    source_root = site_supply_root(vertical, site_id, batch_id)
    explicit_refs = [str(ref).strip() for ref in (refs or []) if str(ref).strip()]
    all_refs = explicit_refs or _eligible_site_map_refs(source_root)
    scan_refs = all_refs[: int(limit)] if explicit_refs and limit > 0 else all_refs
    blockers: list[str] = []
    warnings: list[str] = []
    items: list[dict[str, Any]] = []
    validation_targets: list[dict[str, str]] = []
    validation_target_keys: set[tuple[str, str]] = set()
    skipped: dict[str, list[str]] = {}
    scanned_refs: list[str] = []
    outputs: list[str] = []
    target_root = batch_root(task_id, target_batch)
    target_task_spec = committed_task_spec(task_id)
    if not target_task_spec.is_file():
        blockers.append(f"committed task spec missing for taskId {task_id!r}; repair at task/site-plan")
        skipped = {
            ref: ["committed task spec missing; repair at task/site-plan"]
            for ref in scan_refs
        }
        report = {
            "schemaVersion": "quwoquan.site_supply.content_plan_report/1",
            "vertical": vertical,
            "siteId": site_id,
            "batchId": batch_id,
            "taskId": task_id,
            "targetBatch": target_batch,
            "eligibleAvailableCount": len(all_refs),
            "selectedCount": len(scan_refs),
            "requestedCount": int(limit),
            "itemCount": 0,
            "skipped": skipped,
            "outputs": outputs,
            "createdAt": now_iso(),
        }
        gate = _gate_report("content_plan", blockers, warnings)
        report["gate"] = gate
        report_path = target_root / "_shared" / "site_supply_content_plan_report.json"
        write_json(report_path, report)
        outputs.append(str(report_path))
        _write_stage_triplet(source_root, "content_plan", outputs, gate)
        return report
    ensure_batch_layout(task_id, target_batch, "download")
    ensure_batch_layout(task_id, target_batch, "produce")
    write_batch_manifest(task_id, target_batch, command="site-supply:content-plan")
    registry = TemplateRegistry.load()
    etype_parts = [p for p in str(entity_type).strip("/").split("/") if p]
    entity_domain = etype_parts[0] if len(etype_parts) >= 2 else "地点"
    entity_leaf_type = etype_parts[-1] if etype_parts else "景区"
    source_category = _source_category_for_site(site_id)

    for ref in scan_refs:
        if limit > 0 and len(items) >= int(limit):
            break
        scanned_refs.append(ref)
        ref_issues: list[str] = []
        candidate_path = _candidate_path(source_root, ref)
        score_path = _score_path(source_root, ref)
        map_path = _map_path(source_root, ref)
        if not candidate_path.is_file():
            ref_issues.append("site_candidate_packet missing; repair at site_extract")
        if not score_path.is_file():
            ref_issues.append("site_score_packet missing; repair at site_score")
        if not map_path.is_file():
            ref_issues.append("site_map_packet missing; repair at site_map")
        if ref_issues:
            skipped[ref] = ref_issues
            continue
        candidate = read_json(candidate_path)
        score = read_json(score_path)
        mapped = read_json(map_path)
        if not _packet_gate_passed(candidate):
            ref_issues.append("site_extract gate failed; repair at site_extract")
        if not bool(score.get("productionEligible")) or not _packet_gate_passed(score):
            ref_issues.append("site_score not productionEligible; repair at site_score")
        if not _packet_gate_passed(mapped) or not ((mapped.get("contentPlanHandoff") or {}).get("eligible")):
            ref_issues.append("site_map handoff not eligible; repair at site_map")
        if str(candidate.get("lane") or "") != "article":
            ref_issues.append("content-plan v1 only supports article lane")
        mentions = candidate.get("semanticMentions") if isinstance(candidate.get("semanticMentions"), Mapping) else {}
        expected_entity_type = f"{entity_domain}/{entity_leaf_type}"
        raw_entity_values = [str(x).strip() for x in (mentions.get("entities") or []) if str(x).strip()]
        entity_name = ""
        raw_entity_name = ""
        mismatched_typed: list[str] = []
        unresolved_raw: list[str] = []
        for raw_entity_value in raw_entity_values:
            typed_entity_type, typed_entity_name = _typed_entity_mention(raw_entity_value)
            if typed_entity_type:
                if typed_entity_type == expected_entity_type:
                    entity_name = typed_entity_name
                    break
                mismatched_typed.append(raw_entity_value)
                continue
            candidate_entity_name = _entity_name_from_mention(raw_entity_value)
            known_target = _resolve_known_entity_target(candidate_entity_name, expected_entity_type=expected_entity_type)
            if known_target:
                entity_name = str(known_target.get("name") or candidate_entity_name).strip()
                raw_entity_name = candidate_entity_name
                break
            if candidate_entity_name:
                unresolved_raw.append(candidate_entity_name)
        if not entity_name:
            raw_entity_name = unresolved_raw[0] if unresolved_raw else str(candidate.get("title") or "").strip()
            if mismatched_typed:
                ref_issues.append(
                    f"candidate lacks {expected_entity_type} mention; mismatched typed mentions={mismatched_typed[:3]}"
                )
            elif raw_entity_name:
                ref_issues.append(
                    f"candidate lacks verified {expected_entity_type} mapping for {raw_entity_name!r}; repair at site_map"
                )
        if not entity_name and not raw_entity_name:
            ref_issues.append("candidate has no entity mention/title; repair at site_map")
        text = str(candidate.get("text") or "").strip()
        source_id = f"{site_id}_{_site_candidate_ref_slug(ref)}"
        base_draft_text = extract_base_draft_body(text)
        effective_text_len = len(re.sub(r"\s+", "", base_draft_text))
        if effective_text_len < MIN_ARTICLE_BASE_DRAFT_CHARS:
            ref_issues.append(
                f"candidate baseDraftText too short for content_plan "
                f"({effective_text_len} < {MIN_ARTICLE_BASE_DRAFT_CHARS}); repair at site_extract"
            )
        platform = str((candidate.get("source") or {}).get("platform") or site_id)
        source_class = resolve_source_class(source_id=source_id, platform=platform)
        works_verdict = classify_works(
            ref,
            source_class=source_class,
            source_text=base_draft_text,
            entity_name=entity_name or raw_entity_name or str(candidate.get("title") or ""),
            narrative_volume=0,
            image_count=0,
            declared_carrier="article",
            rights_blocked=False,
        )
        if str(works_verdict.get("decision") or "") != "work":
            ref_issues.append(
                "works classifier rejected content_plan candidate as "
                f"{works_verdict.get('decision')!r} "
                f"(abandonReason={works_verdict.get('abandonReason')}, "
                f"sourceTier={works_verdict.get('sourceTier')}, score={works_verdict.get('score')}); "
                "repair at site_score"
            )
        text_only_article = int(max_images_per_candidate) <= 0
        images, image_issues = ([], []) if text_only_article else _download_candidate_images(candidate, limit=max_images_per_candidate)
        if not images and not text_only_article:
            ref_issues.append("no downloadable/right-cleared source images; repair at site_extract or source rights")
        if text_only_article:
            warnings.append(f"{ref}: text-only article plan; source images are not requested or published")
        if image_issues:
            warnings.extend(f"{ref}: {issue}" for issue in image_issues[:5])
        if ref_issues:
            skipped[ref] = ref_issues
            continue

        entity_ref = f"/entity/{entity_domain}/{entity_leaf_type}/{entity_name}"
        object_dir = resolve_entity_object_dir(task_id, target_batch, entity_ref)
        source_ordinal = len(items) + 1
        unit_dir = object_dir / "1.download" / "sources" / f"{source_ordinal:02d}.{source_id}"
        write_source_unit(
            object_dir,
            ordinal=source_ordinal,
            source_id=source_id,
            source_md=text,
            clean_md=text,
            html_bytes=None,
            quality={
                "sourceId": source_id,
                "quality": "A-story" if float((score.get("scores") or {}).get("overall") or 0) >= 0.7 else "B-fact",
                "score": max(4, min(10, int(float((score.get("scores") or {}).get("overall") or 0.5) * 10))),
                "reasons": ["site_supply_handoff", site_id, "rights_checked"],
                "excerpt": text[:180],
                "url": str(candidate.get("canonicalUrl") or ""),
            },
            platform=str((candidate.get("source") or {}).get("platform") or site_id),
            source_category=source_category,
            source_use_mode="factual_reference_only",
            source_role="base",
            image_evidence_mode="source_unit_assets",
            research_lane="article",
            license_value=str((candidate.get("source") or {}).get("rightsPolicy") or "factual_citation_only"),
            url=str(candidate.get("canonicalUrl") or ""),
            title=str(candidate.get("title") or entity_name),
            target_ref=entity_ref,
            relevance=f"{entity_name} 网站供给线候选；仅作事实参考，正文需独立表达",
            images=images,
            task_id=task_id,
            batch_id=target_batch,
            build_variants=False,
        )
        source_ref = relative_batch_ref(unit_dir / "source.md", task_id, target_batch)
        title = _content_plan_title(candidate, entity_name, intent)
        brief = resolve_compose_brief(
            registry,
            RouteRequest(
                vertical="travel",
                subject_kind="entity",
                subject_type=f"{entity_domain}/{entity_leaf_type}",
                intent=intent,
                audience=audience,
            ),
            title=title,
            entity_refs=[entity_ref],
        )
        update_fields = {
            "baseSourceRef": source_ref,
            "sourceUseMode": "factual_reference_only",
            "writingIntent": "planning_consultation",
            "routeCoverageExpectations": {"minCoveredEntityRefs": 1, "requireAllPrimaryNodes": False},
            "evidenceRequirements": {
                "fact": {"required": True},
                "emotion": {"required": False},
                "mainline": {"required": True, "minSignals": 1},
            },
            "explicitFeelings": {"requireLike": False, "requireDislike": False},
            "mustIncludeFacts": [entity_name],
            "bannedRegisterTerms": sorted(set(list(brief.get("bannedRegisterTerms") or []) + ["携程", "马蜂窝", "去哪儿", "维基导游", "Wikivoyage"])),
        }
        if images:
            update_fields["imagePlan"] = [{"slot": "来源封面", "imageLayout": "fullWidth"}]
        else:
            update_fields["imagePlan"] = []
            update_fields["publishMediaMode"] = "text_only"
        brief.update(update_fields)
        brief = hydrate_entity_condition_context(brief, task_id=task_id, batch_id=target_batch)
        context = brief.get("conditionContext") if isinstance(brief.get("conditionContext"), dict) else {}
        if not (isinstance(context, dict) and context.get("region")):
            candidate_context = _site_candidate_condition_context(text, source_ref=source_ref)
            if candidate_context:
                merged_context = dict(context) if isinstance(context, dict) else {}
                merged_context.update(candidate_context)
                brief["conditionContext"] = merged_context
        write_brief_object(task_id, target_batch, ref, brief, content_type="article")
        items.append(
            {
                "ref": ref,
                "kind": "entity",
                "carrier": "article",
                "researchLane": "article",
                "title": title,
                "entityRefs": [entity_ref],
                "evidenceRefs": [source_ref],
                "rationale": "site_map eligible candidate converted to one-source-one-work factual article plan",
                "mustIncludeFacts": brief["mustIncludeFacts"],
                "writingIntent": "planning_consultation",
                "baseSourceRef": source_ref,
                "sourceUseMode": "factual_reference_only",
                "sourceCandidateRef": ref,
                "sourceUrl": str(candidate.get("canonicalUrl") or ""),
            }
        )
        validation_target_key = (f"{entity_domain}/{entity_leaf_type}", entity_name)
        if validation_target_key not in validation_target_keys:
            validation_target_keys.add(validation_target_key)
            validation_targets.append({"entityType": validation_target_key[0], "name": validation_target_key[1]})
        outputs.append(str(unit_dir / "source.md"))
        outputs.append(str(unit_dir / "meta.json"))

    if not items:
        blockers.append("content_plan produced no eligible items")
    if skipped and not allow_partial:
        for ref, issues in skipped.items():
            blockers.append(f"{ref}: " + "; ".join(issues))
    report = {
        "schemaVersion": "quwoquan.site_supply.content_plan_report/1",
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "taskId": task_id,
        "targetBatch": target_batch,
        "eligibleAvailableCount": len(all_refs),
        "selectedCount": len(scanned_refs),
        "requestedCount": int(limit),
        "itemCount": len(items),
        "skipped": skipped,
        "outputs": outputs,
        "createdAt": now_iso(),
    }
    if items:
        write_batch_manifest(
            task_id,
            target_batch,
            coverage_targets=validation_targets,
            command="site-supply:content-plan",
        )
        write_json(
            batch_content_plan_packet_path(task_id, target_batch),
            {
                "schemaVersion": CONTENT_PLAN_SCHEMA,
                "taskId": task_id,
                "batchId": target_batch,
                "generatedBy": "site_supply_content_plan_bridge",
                "sourceSite": {"vertical": vertical, "siteId": site_id, "batchId": batch_id},
                "items": items,
            },
        )
        outputs.append(str(batch_content_plan_packet_path(task_id, target_batch)))
        validation_issues = validate_content_plan(
            task_id,
            target_batch,
            {"scope": {"coverageTargets": validation_targets}, "content": {"quotas": {}}},
        )
        if validation_issues:
            blockers.extend(f"content_plan validator: {issue}" for issue in validation_issues)
    write_json(target_root / "_shared" / "site_supply_content_plan_report.json", report)
    outputs.append(str(target_root / "_shared" / "site_supply_content_plan_report.json"))
    gate = _gate_report("content_plan", blockers, warnings)
    report["gate"] = gate
    write_json(target_root / "_shared" / "site_supply_content_plan_report.json", report)
    _write_stage_triplet(source_root, "content_plan", outputs, gate)
    return report


def handle_content_plan(args: argparse.Namespace) -> None:
    report = build_site_content_plan(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        task_id=args.task,
        target_batch=args.target_batch,
        limit=args.limit,
        refs=_split_csv(args.refs),
        entity_type=args.entity_type,
        intent=args.intent,
        audience=args.audience,
        max_images_per_candidate=args.max_images_per_candidate,
        allow_partial=args.allow_partial,
    )
    _print(report)
    if not (report.get("gate") or {}).get("passed"):
        raise SystemExit(1)


def _by_ref(rows: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        ref = str(row.get("candidateRef") or "").strip()
        if ref:
            indexed[ref] = row
    return indexed


def _bump(counter: dict[str, int], key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


def _packet_gate_passed(packet: Mapping[str, Any]) -> bool:
    gate = packet.get("gate") if isinstance(packet.get("gate"), Mapping) else {}
    return bool(gate.get("passed"))


def _packet_gate_reasons(packet: Mapping[str, Any], field: str) -> list[str]:
    gate = packet.get("gate") if isinstance(packet.get("gate"), Mapping) else {}
    return [str(item) for item in (gate.get(field) or []) if str(item).strip()]


def _read_packet_rows(root: Path, stage_dir: str, packet_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / stage_dir).glob(f"*/{packet_name}")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _quality_bucket(overall: float, *, production_eligible: bool, gate_passed: bool) -> str:
    if not gate_passed or not production_eligible:
        return "disqualified"
    if overall >= 0.70:
        return "highQuality"
    if overall >= 0.55:
        return "acceptable"
    if overall >= MIN_PRODUCTION_SCORE:
        return "marginal"
    return "disqualified"


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def build_site_quality_distribution_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
) -> dict[str, Any]:
    root = site_supply_root(vertical, site_id, batch_id)
    blockers: list[str] = []
    warnings: list[str] = []
    try:
        frontier = _frontier_packet(vertical, site_id, batch_id)
    except Exception as exc:
        frontier = {}
        blockers.append(f"site_frontier_packet missing or unreadable: {exc}")
    profile = frontier.get("profile") if isinstance(frontier.get("profile"), Mapping) else {}
    controlled = profile.get("controlledTrial") if isinstance(profile.get("controlledTrial"), Mapping) else {}
    admission_mode = str(frontier.get("admissionMode") or ADMISSION_BATCH_CRAWL)
    validation_only = bool(controlled.get("validationOnly")) or admission_mode == ADMISSION_CONTROLLED_TRIAL
    publishable_assets_allowed = bool(controlled.get("publishableAssetsAllowed", True))
    commercial_blockers: list[str] = []
    if validation_only:
        commercial_blockers.append("controlledTrial.validationOnly=true")
    if not bool(profile.get("fetchable")):
        commercial_blockers.append("fetchable=false")
    if not bool(profile.get("crawlAllowed")):
        commercial_blockers.append("crawlAllowed=false")
    if not publishable_assets_allowed:
        commercial_blockers.append("publishableAssetsAllowed=false")

    candidates = _read_packet_rows(root, "candidates", "site_candidate_packet.json")
    scores = _read_packet_rows(root, "scores", "site_score_packet.json")
    maps = _read_packet_rows(root, "map", "site_map_packet.json")
    scores_by_ref = _by_ref(scores)
    maps_by_ref = _by_ref(maps)
    candidate_refs = {str(candidate.get("candidateRef") or "") for candidate in candidates if str(candidate.get("candidateRef") or "")}
    lane_counts: dict[str, int] = {}
    production_lane_counts: dict[str, int] = {}
    handoff_lane_counts: dict[str, int] = {}
    bucket_counts = {
        "highQuality": 0,
        "acceptable": 0,
        "marginal": 0,
        "disqualified": 0,
    }
    blocker_reasons: dict[str, int] = {}
    warning_reasons: dict[str, int] = {}
    score_values: list[float] = []
    production_eligible = 0
    handoff_eligible = 0

    if not candidates:
        blockers.append("quality report requires at least one site_candidate_packet")
    for reason in commercial_blockers:
        _bump(warning_reasons, reason)
    for candidate in candidates:
        ref = str(candidate.get("candidateRef") or "")
        lane = str(candidate.get("lane") or "unknown")
        _bump(lane_counts, lane)
        for reason in _packet_gate_reasons(candidate, "blockers"):
            _bump(blocker_reasons, reason)
        for reason in _packet_gate_reasons(candidate, "warnings"):
            _bump(warning_reasons, reason)
        score = scores_by_ref.get(ref)
        if score is None:
            bucket_counts["disqualified"] += 1
            _bump(blocker_reasons, "missing site_score_packet")
            continue
        for reason in _packet_gate_reasons(score, "blockers"):
            _bump(blocker_reasons, reason)
        for reason in _packet_gate_reasons(score, "warnings"):
            _bump(warning_reasons, reason)
        scores_payload = score.get("scores") if isinstance(score.get("scores"), Mapping) else {}
        overall = float(scores_payload.get("overall") or 0.0)
        score_values.append(overall)
        score_gate_passed = _packet_gate_passed(score)
        score_production_eligible = bool(score.get("productionEligible"))
        if score_production_eligible:
            production_eligible += 1
            _bump(production_lane_counts, lane)
        bucket_counts[_quality_bucket(overall, production_eligible=score_production_eligible, gate_passed=score_gate_passed)] += 1
        mapped = maps_by_ref.get(ref)
        if mapped is None:
            if score_production_eligible:
                _bump(blocker_reasons, "missing site_map_packet")
            continue
        for reason in _packet_gate_reasons(mapped, "blockers"):
            _bump(blocker_reasons, reason)
        for reason in _packet_gate_reasons(mapped, "warnings"):
            _bump(warning_reasons, reason)
        if bool((mapped.get("contentPlanHandoff") or {}).get("eligible")) and _packet_gate_passed(mapped):
            handoff_eligible += 1
            _bump(handoff_lane_counts, lane)

    for score_ref in sorted(set(scores_by_ref) - candidate_refs):
        _bump(blocker_reasons, f"{score_ref}: orphan site_score_packet")
    for map_ref in sorted(set(maps_by_ref) - set(scores_by_ref)):
        _bump(blocker_reasons, f"{map_ref}: orphan site_map_packet")

    total = len(candidates)
    commercial_ready = bool(total) and not commercial_blockers and not blockers
    if commercial_blockers:
        warnings.append("batch is quality-measurable but not commercial-publishable under current site profile")
    score_summary = {
        "min": round(min(score_values), 4) if score_values else 0.0,
        "avg": round(sum(score_values) / len(score_values), 4) if score_values else 0.0,
        "max": round(max(score_values), 4) if score_values else 0.0,
    }
    report = {
        "schemaVersion": QUALITY_DISTRIBUTION_SCHEMA,
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "workspaceRoot": str(root),
        "frontier": {
            "admissionMode": admission_mode,
            "validationOnly": validation_only,
            "publishableAssetsAllowed": publishable_assets_allowed,
            "fetchable": bool(profile.get("fetchable")),
            "crawlAllowed": bool(profile.get("crawlAllowed")),
            "rightsPolicy": str(profile.get("rightsPolicy") or ""),
        },
        "qualityFunnel": {
            "candidateCount": total,
            "laneCounts": lane_counts,
            "scoreCount": len(scores),
            "mapCount": len(maps),
            "productionEligibleCount": production_eligible,
            "productionEligibleLaneCounts": production_lane_counts,
            "contentPlanHandoffCount": handoff_eligible,
            "contentPlanHandoffLaneCounts": handoff_lane_counts,
            "successRate": _ratio(production_eligible, total),
            "handoffRate": _ratio(handoff_eligible, total),
        },
        "qualityDistribution": {
            "buckets": bucket_counts,
            "rates": {key: _ratio(value, total) for key, value in bucket_counts.items()},
            "score": score_summary,
        },
        "commercialReadiness": {
            "ready": commercial_ready,
            "decision": "go" if commercial_ready else "trial_only_or_blocked",
            "blockers": commercial_blockers,
        },
        "riskDistribution": {
            "blockerReasons": dict(sorted(blocker_reasons.items())),
            "warningReasons": dict(sorted(warning_reasons.items())),
        },
        "gate": _gate_report("quality_distribution", blockers, warnings),
        "createdAt": now_iso(),
    }
    return report


def write_site_quality_distribution_report(report: Mapping[str, Any]) -> Path:
    root = site_supply_root(str(report["vertical"]), str(report["siteId"]), str(report["batchId"]))
    path = root / "_shared" / "site_quality_distribution_report.json"
    write_json(path, dict(report))
    _write_stage_triplet(root, "quality_distribution", [str(path)], report["gate"])
    return path


def _runtime_batch_root(task_id: str, batch_id: str) -> Path:
    return RUNTIME_ROOT / "tasks" / Path(*str(task_id).split("/")) / "batches" / batch_id


def _publish_root() -> Path:
    from _common.paths import PUBLISH_ROOT

    return PUBLISH_ROOT


def _content_plan_packet_path(task_id: str, batch_id: str) -> Path:
    return _runtime_batch_root(task_id, batch_id) / "_shared" / "content_plan_packet.json"


def _content_object_index_path(task_id: str, batch_id: str) -> Path:
    return _runtime_batch_root(task_id, batch_id) / "_shared" / "content_object_index.json"


def _content_plan_matches_site(
    packet: Mapping[str, Any],
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
) -> bool:
    source = packet.get("sourceSite") if isinstance(packet.get("sourceSite"), Mapping) else {}
    return (
        str(source.get("vertical") or "") == vertical
        and str(source.get("siteId") or "") == site_id
        and str(source.get("batchId") or "") == batch_id
    )


def _site_content_plan_report_source_site(
    shared: Path,
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    task_id: str,
    target_batch: str,
) -> dict[str, str] | None:
    report_path = shared / "site_supply_content_plan_report.json"
    if not report_path.is_file():
        return None
    try:
        report = read_json(report_path)
    except (OSError, ValueError, TypeError):
        return None
    gate = report.get("gate") if isinstance(report.get("gate"), Mapping) else {}
    if not gate.get("passed"):
        return None
    if (
        str(report.get("vertical") or "") != vertical
        or str(report.get("siteId") or "") != site_id
        or str(report.get("batchId") or "") != batch_id
        or str(report.get("taskId") or "") != task_id
        or str(report.get("targetBatch") or "") != target_batch
    ):
        return None
    return {"vertical": vertical, "siteId": site_id, "batchId": batch_id}


def repair_content_plan_source_site_provenance(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    task_id: str,
    target_batch: str,
) -> bool:
    packet_path = _content_plan_packet_path(task_id, target_batch)
    if not packet_path.is_file():
        return False
    packet = read_json(packet_path)
    if not isinstance(packet, dict):
        return False
    if isinstance(packet.get("sourceSite"), Mapping):
        return False
    shared = _runtime_batch_root(task_id, target_batch) / "_shared"
    source_site = _site_content_plan_report_source_site(
        shared,
        vertical=vertical,
        site_id=site_id,
        batch_id=batch_id,
        task_id=task_id,
        target_batch=target_batch,
    )
    if not source_site:
        return False
    packet["sourceSite"] = source_site
    write_json(packet_path, packet)
    return True


def _post_refs_for_content_plan_batch(task_id: str, batch_id: str, packet: Mapping[str, Any]) -> list[str]:
    refs = [
        str(item.get("ref") or "").strip()
        for item in (packet.get("items") or [])
        if isinstance(item, Mapping) and str(item.get("ref") or "").strip()
    ]
    index = read_json(_content_object_index_path(task_id, batch_id)) if _content_object_index_path(task_id, batch_id).is_file() else {}
    coords_by_ref = index.get("refs") if isinstance(index.get("refs"), Mapping) else {}
    out: list[str] = []
    for ref in refs:
        coords = coords_by_ref.get(ref) if isinstance(coords_by_ref, Mapping) else None
        if not isinstance(coords, Mapping):
            continue
        content_type = str(coords.get("contentType") or "").strip()
        angle = str(coords.get("angle") or "").strip()
        title = str(coords.get("title") or "").strip()
        seq = int(coords.get("seq") or 1)
        if content_type and angle and title:
            out.append(f"posts/{content_type}/{angle}/{title}/{seq}")
    return sorted(dict.fromkeys(out))


def _publish_index_post_refs() -> set[str]:
    refs: set[str] = set()
    index_root = _publish_root() / "index" / "posts"
    if not index_root.is_dir():
        return refs
    for path in sorted(index_root.glob("*.ndjson")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ref = str(row.get("postRef") or "").strip()
            if ref:
                refs.add(ref)
    return refs


def _release_contract_post_refs(path: str | Path) -> tuple[bool, set[str]]:
    p = Path(path)
    if not p.is_file():
        return False, set()
    data = read_json(p)
    desired = data.get("desiredRefs") if isinstance(data.get("desiredRefs"), Mapping) else None
    if desired is None or not isinstance(desired.get("posts"), list):
        return False, set()
    return True, {str(ref).strip() for ref in desired.get("posts") or [] if str(ref).strip()}


def _sample_bundle_post_refs(env: str) -> set[str]:
    path = _publish_root() / "sample_bundles" / f"{env}.json"
    if not path.is_file():
        return set()
    data = read_json(path)
    return {str(ref) for ref in (data.get("posts") or []) if str(ref).strip()}


def _report_status_passed(path: str | Path, *, allow_dry_run: bool = False) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    data = read_json(p)
    status = str(data.get("status") or "").strip()
    if status in {"passed", "active"}:
        return True
    return allow_dry_run and status == "dry-run"


def build_downstream_e2e_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    task_id: str,
    target_batch: str,
    env: str = "gamma",
    allow_dry_run_import: bool = False,
) -> dict[str, Any]:
    root = _runtime_batch_root(task_id, target_batch)
    shared = root / "_shared"
    packet_path = _content_plan_packet_path(task_id, target_batch)
    blockers: list[str] = []
    warnings: list[str] = []
    evidence_paths: list[str] = []
    packet: dict[str, Any] = {}
    if packet_path.is_file():
        packet = read_json(packet_path)
        evidence_paths.append(str(packet_path))
        if not _content_plan_matches_site(packet, vertical=vertical, site_id=site_id, batch_id=batch_id):
            blockers.append("content_plan sourceSite does not match requested site batch")
    else:
        blockers.append("content_plan_packet missing for downstream batch")

    planned_post_refs = _post_refs_for_content_plan_batch(task_id, target_batch, packet) if packet else []
    if not planned_post_refs:
        blockers.append("no content object post refs found for downstream batch")

    ship_path = shared / "ship_report.json"
    ship = read_json(ship_path) if ship_path.is_file() else {}
    if ship:
        evidence_paths.append(str(ship_path))
    else:
        blockers.append("ship_report.json missing")

    summaries = [row for row in (ship.get("summary") or []) if isinstance(row, Mapping)]
    env_summaries = [row for row in summaries if str(row.get("env") or "") == env]
    if not env_summaries:
        blockers.append(f"ship_report has no summary for env={env}")
    release_verified = False
    release_ref_contract_seen = False
    released_post_refs: set[str] = set()
    for row in env_summaries:
        contract_path = Path(str(row.get("releaseContract") or ""))
        consistency_path = Path(str(row.get("consistencyReport") or ""))
        if contract_path.is_file():
            evidence_paths.append(str(contract_path))
            ref_contract_seen, contract_refs = _release_contract_post_refs(contract_path)
            if ref_contract_seen:
                release_ref_contract_seen = True
                released_post_refs.update(contract_refs)
        if consistency_path.is_file():
            evidence_paths.append(str(consistency_path))
        if contract_path.is_file() and _report_status_passed(consistency_path):
            release_verified = True
    if not release_verified:
        blockers.append(f"release consistency evidence missing or failed for env={env}")
    post_refs = sorted(released_post_refs) if release_ref_contract_seen else planned_post_refs
    if not post_refs:
        blockers.append("no published post refs found after release gate")
    dropped_before_release = max(0, len(set(planned_post_refs)) - len(set(post_refs)))
    if release_ref_contract_seen and dropped_before_release:
        warnings.append(
            f"{dropped_before_release} content_plan object(s) did not pass publish gate; excluded from downstream visibility checks"
        )

    import_path = shared / f"{env}_import_report.json"
    import_report = read_json(import_path) if import_path.is_file() else {}
    import_verified = _report_status_passed(import_path, allow_dry_run=allow_dry_run_import)
    if import_path.is_file():
        evidence_paths.append(str(import_path))
    else:
        blockers.append(f"{env}_import_report.json missing")
    if not import_verified:
        blockers.append(f"import evidence missing or not active for env={env}")
    if allow_dry_run_import and str(import_report.get("status") or "") == "dry-run":
        warnings.append("import evidence is dry-run; acceptable only for controlled local rehearsal")

    indexed_refs = _publish_index_post_refs()
    bundle_refs = _sample_bundle_post_refs(env)
    missing_index = sorted(set(post_refs) - indexed_refs)
    missing_bundle = sorted(set(post_refs) - bundle_refs)
    if missing_index:
        blockers.append(f"publish index missing post ref(s): {missing_index[:5]}")
    current_bundle_visible = bool(post_refs) and not missing_bundle
    if missing_bundle:
        message = f"sample bundle {env} missing post ref(s): {missing_bundle[:5]}"
        if release_ref_contract_seen and release_verified:
            warnings.append(
                message
                + "; current mutable sample bundle may point at another isolated release, "
                + "archived release contract is used for historical visibility evidence"
            )
        else:
            blockers.append(message)
    search_visible = bool(post_refs) and not missing_index and (
        current_bundle_visible or (release_ref_contract_seen and release_verified)
    )

    counts = import_report.get("counts") if isinstance(import_report.get("counts"), Mapping) else {}
    feed_upserted = int(counts.get("feedUpserted") or 0)
    recommendation_ready = bool(import_verified and (feed_upserted >= len(post_refs) or allow_dry_run_import))
    if not recommendation_ready:
        blockers.append("recommendation cold-start/feed import evidence missing")

    report = {
        "schemaVersion": DOWNSTREAM_E2E_SCHEMA,
        "vertical": vertical,
        "siteId": site_id,
        "sourceBatchId": batch_id,
        "taskId": task_id,
        "targetBatch": target_batch,
        "env": env,
        "postRefs": post_refs,
        "plannedPostRefs": planned_post_refs,
        "releasedPostRefs": post_refs,
        "plannedPostRefCount": len(planned_post_refs),
        "releasedPostRefCount": len(post_refs),
        "droppedBeforeReleaseCount": dropped_before_release,
        "checks": {
            "releaseVerified": release_verified,
            "importVerified": import_verified,
            "searchVisible": search_visible,
            "currentSampleBundleVisible": current_bundle_visible,
            "recommendationFeedbackReady": recommendation_ready,
        },
        "importStatus": str(import_report.get("status") or ""),
        "importCounts": dict(counts),
        "evidencePaths": sorted(dict.fromkeys(evidence_paths)),
        "gate": _gate_report("ship_import", blockers, warnings),
        "createdAt": now_iso(),
    }
    return report


def write_downstream_e2e_report(report: Mapping[str, Any]) -> Path:
    task_id = str(report["taskId"])
    target_batch = str(report["targetBatch"])
    path = _runtime_batch_root(task_id, target_batch) / "_shared" / "site_supply_downstream_e2e_report.json"
    payload = dict(report)
    payload["reportPath"] = str(path)
    gate = payload.get("gate") if isinstance(payload.get("gate"), Mapping) else {}
    if path.is_file() and not bool(gate.get("passed")):
        try:
            previous = read_json(path)
        except Exception:
            previous = {}
        previous_gate = previous.get("gate") if isinstance(previous.get("gate"), Mapping) else {}
        if bool(previous_gate.get("passed")):
            failed_path = path.with_name("site_supply_downstream_e2e_report_last_failed.json")
            payload["reportPath"] = str(failed_path)
            write_json(failed_path, payload)
            return failed_path
    write_json(path, payload)
    root = site_supply_root(str(report["vertical"]), str(report["siteId"]), str(report["sourceBatchId"]))
    outputs = [str(path)] + [str(p) for p in (payload.get("evidencePaths") or [])]
    _write_stage_triplet_append_outputs(root, "ship_import", outputs, payload["gate"])
    return path


def _iter_downstream_e2e_reports(vertical: str, site_id: str, batch_id: str) -> list[dict[str, Any]]:
    tasks_root = RUNTIME_ROOT / "tasks"
    if not tasks_root.is_dir():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(tasks_root.glob("**/batches/*/_shared/site_supply_downstream_e2e_report.json")):
        try:
            report = read_json(path)
        except Exception:
            continue
        if (
            str(report.get("vertical") or "") == vertical
            and str(report.get("siteId") or "") == site_id
            and str(report.get("sourceBatchId") or "") == batch_id
        ):
            reports.append(report)
    return reports


def _downstream_readiness_from_reports(vertical: str, site_id: str, batch_id: str) -> dict[str, bool]:
    reports = [
        report
        for report in _iter_downstream_e2e_reports(vertical, site_id, batch_id)
        if bool((report.get("gate") or {}).get("passed"))
    ]
    if not reports:
        return {
            "releaseVerified": False,
            "importVerified": False,
            "searchVisible": False,
            "recommendationFeedbackReady": False,
        }
    checks = [report.get("checks") if isinstance(report.get("checks"), Mapping) else {} for report in reports]
    return {
        "releaseVerified": any(bool(row.get("releaseVerified")) for row in checks),
        "importVerified": any(bool(row.get("importVerified")) for row in checks),
        "searchVisible": any(bool(row.get("searchVisible")) for row in checks),
        "recommendationFeedbackReady": any(bool(row.get("recommendationFeedbackReady")) for row in checks),
    }


def build_site_rollup_report(
    *,
    vertical: str,
    site_id: str,
    batch_id: str,
    objects_per_hour: float = 0.0,
    first_pass_rate: float | None = None,
    token_ledger_count: int = 0,
    release_verified: bool = False,
    import_verified: bool = False,
    search_visible: bool = False,
    recommendation_feedback_ready: bool = False,
    http_429_count: int = 0,
    http_403_count: int = 0,
    probe_page_count: int = 0,
    empty_extract_count: int = 0,
    duplicate_count: int = 0,
    dead_letter_count: int = 0,
) -> dict[str, Any]:
    root = site_supply_root(vertical, site_id, batch_id)
    frontier = _frontier_packet(vertical, site_id, batch_id)
    fetch_paths = sorted((root / "fetches").glob("*/site_fetch_packet.json"))
    candidate_paths = sorted((root / "candidates").glob("*/site_candidate_packet.json"))
    score_paths = sorted((root / "scores").glob("*/site_score_packet.json"))
    map_paths = sorted((root / "map").glob("*/site_map_packet.json"))
    fetches = [read_json(path) for path in fetch_paths]
    candidates = [read_json(path) for path in candidate_paths]
    scores = [read_json(path) for path in score_paths]
    maps = [read_json(path) for path in map_paths]
    scores_by_ref = _by_ref(scores)
    maps_by_ref = _by_ref(maps)
    candidates_by_ref = _by_ref(candidates)
    lane_counts: dict[str, int] = {}
    production_lane_counts: dict[str, int] = {}
    handoff_lane_counts: dict[str, int] = {}
    for candidate in candidates:
        lane = str(candidate.get("lane") or "unknown")
        _bump(lane_counts, lane)
    for score in scores:
        if score.get("productionEligible"):
            _bump(production_lane_counts, str(score.get("lane") or "unknown"))
    for mapped in maps:
        if not ((mapped.get("contentPlanHandoff") or {}).get("eligible")):
            continue
        ref = str(mapped.get("candidateRef") or "")
        candidate = candidates_by_ref.get(ref, {})
        lane = str(candidate.get("lane") or mapped.get("targetContentType") or "unknown")
        _bump(handoff_lane_counts, lane)
    production_eligible = sum(1 for s in scores if s.get("productionEligible"))
    handoff_count = sum(1 for m in maps if ((m.get("contentPlanHandoff") or {}).get("eligible")))
    entity_handoff_count = 0
    unresolved_entity_mention_count = 0
    topic_candidate_count = 0
    for mapped in maps:
        if not ((mapped.get("contentPlanHandoff") or {}).get("eligible")):
            continue
        gaps = mapped.get("knowledgeGaps") if isinstance(mapped.get("knowledgeGaps"), Mapping) else {}
        if gaps.get("entityHomepageCandidates"):
            entity_handoff_count += 1
        unresolved_entity_mention_count += len(gaps.get("unresolvedEntityMentions") or [])
        topic_candidate_count += len(gaps.get("topicCandidates") or [])
    blockers: list[str] = []
    warnings: list[str] = []
    total = len(candidates)
    if not frontier.get("gate", {}).get("passed"):
        blockers.append("site_frontier gate failed")
    if total <= 0:
        blockers.append("site rollup requires at least one candidate")
    stage_failures = {
        "site_fetch": 0,
        "site_extract": 0,
        "site_score": 0,
        "site_map": 0,
        "missing_candidate_after_fetch": 0,
        "missing_score": 0,
        "missing_map": 0,
        "orphan_score": 0,
        "orphan_map": 0,
        "missing_object_evidence": 0,
    }
    candidate_refs = {str(c.get("candidateRef") or "") for c in candidates if str(c.get("candidateRef") or "")}
    fetch_pass_refs: set[str] = set()
    for fetched in fetches:
        ref = str(fetched.get("candidateRef") or "<missing>")
        missing_fetch = _object_triplet_missing(root / "fetches" / ref)
        if missing_fetch:
            stage_failures["missing_object_evidence"] += 1
            blockers.append(f"{ref}: missing site_fetch object evidence {missing_fetch}")
        if _packet_gate_passed(fetched):
            fetch_pass_refs.add(ref)
        else:
            stage_failures["site_fetch"] += 1
    for ref in sorted(fetch_pass_refs - candidate_refs):
        stage_failures["missing_candidate_after_fetch"] += 1
        blockers.append(f"{ref}: site_fetch passed but site_candidate_packet is missing")
    for candidate in candidates:
        ref = str(candidate.get("candidateRef") or "<missing>")
        missing = _object_triplet_missing(root / "candidates" / ref)
        if missing:
            stage_failures["missing_object_evidence"] += 1
            blockers.append(f"{ref}: missing site_extract object evidence {missing}")
        if not _packet_gate_passed(candidate):
            stage_failures["site_extract"] += 1
            blockers.append(f"{ref}: site_extract gate failed; repair at site_extract")
            continue
        score = scores_by_ref.get(ref)
        if score is None:
            stage_failures["missing_score"] += 1
            blockers.append(f"{ref}: missing site_score_packet; re-inject at site_score")
            continue
        missing_score = _object_triplet_missing(root / "scores" / ref)
        if missing_score:
            stage_failures["missing_object_evidence"] += 1
            blockers.append(f"{ref}: missing site_score object evidence {missing_score}")
        if not _packet_gate_passed(score):
            stage_failures["site_score"] += 1
            continue
        if score.get("productionEligible"):
            mapped = maps_by_ref.get(ref)
            if mapped is None:
                stage_failures["missing_map"] += 1
                blockers.append(f"{ref}: missing site_map_packet; re-inject at site_map")
                continue
            missing_map = _object_triplet_missing(root / "map" / ref)
            if missing_map:
                stage_failures["missing_object_evidence"] += 1
                blockers.append(f"{ref}: missing site_map object evidence {missing_map}")
            if not _packet_gate_passed(mapped):
                stage_failures["site_map"] += 1
                blockers.append(f"{ref}: site_map gate failed; repair at site_map")
            elif not ((mapped.get("contentPlanHandoff") or {}).get("eligible")):
                stage_failures["site_map"] += 1
                blockers.append(f"{ref}: site_map did not produce eligible content_plan handoff")
    for ref in sorted(set(scores_by_ref) - candidate_refs):
        stage_failures["orphan_score"] += 1
        blockers.append(f"{ref}: orphan site_score_packet without candidate")
    for ref in sorted(set(maps_by_ref) - set(scores_by_ref)):
        stage_failures["orphan_map"] += 1
        blockers.append(f"{ref}: orphan site_map_packet without score")
    for mapped in maps:
        ref = str(mapped.get("candidateRef") or "<missing>")
        if ((mapped.get("contentPlanHandoff") or {}).get("eligible")) and not scores_by_ref.get(ref, {}).get("productionEligible"):
            stage_failures["site_map"] += 1
            blockers.append(f"{ref}: site_map handoff is eligible without productionEligible score")
    stability_denominator = len(fetches) or total
    if stability_denominator:
        if dead_letter_count / stability_denominator > MAX_DEAD_LETTER_RATE:
            blockers.append(f"deadLetter rate exceeds {MAX_DEAD_LETTER_RATE:.0%}")
        if (http_429_count + http_403_count) / stability_denominator > MAX_THROTTLE_FORBIDDEN_RATE:
            blockers.append(f"site throttle/forbidden rate exceeds {MAX_THROTTLE_FORBIDDEN_RATE:.0%}")
        if probe_page_count / stability_denominator > MAX_PROBE_PAGE_RATE:
            blockers.append(f"probe page rate exceeds {MAX_PROBE_PAGE_RATE:.0%}")
        if empty_extract_count / stability_denominator > MAX_EMPTY_EXTRACT_RATE:
            blockers.append(f"empty extract rate exceeds {MAX_EMPTY_EXTRACT_RATE:.0%}")
        if duplicate_count / stability_denominator > 0.40:
            warnings.append("duplicate rate exceeds 40%; keep dedupe budget visible before expansion")
    elif dead_letter_count:
        blockers.append(f"deadLetterCount present without fetch/candidate denominator; got {dead_letter_count}")
    if production_eligible and handoff_count < production_eligible:
        blockers.append("all productionEligible candidates must have site_map handoff packets")
    target_count = int(((frontier.get("frontier") or {}).get("targetCount")) or 0)
    if target_count and handoff_count < target_count:
        blockers.append(f"contentPlanHandoffCount {handoff_count} < targetCount {target_count}")
    report = {
        "schemaVersion": ROLLUP_SCHEMA,
        "vertical": vertical,
        "siteId": site_id,
        "batchId": batch_id,
        "passed": not blockers,
        "decision": "go" if not blockers else "no_go",
        "workspaceRoot": str(root),
        "frontier": {
            "admissionMode": frontier.get("admissionMode") or ADMISSION_BATCH_CRAWL,
            "profile": frontier.get("profile") or {},
            "queuePolicy": frontier.get("queuePolicy") or {},
            "timeWindow": frontier.get("timeWindow") or {},
        },
        "siteFunnel": {
            "frontierReady": bool(frontier.get("gate", {}).get("passed")),
            "fetchCount": len(fetches),
            "fetchGatePassedCount": len(fetch_pass_refs),
            "candidateCount": total,
            "laneCounts": lane_counts,
            "scoreCount": len(scores),
            "productionEligibleCount": production_eligible,
            "productionEligibleLaneCounts": production_lane_counts,
            "contentPlanHandoffCount": handoff_count,
            "entityMappedContentPlanHandoffCount": entity_handoff_count,
            "unresolvedEntityMentionCount": unresolved_entity_mention_count,
            "topicCandidateCount": topic_candidate_count,
            "contentPlanHandoffLaneCounts": handoff_lane_counts,
            "blockedCount": max(0, len(scores) - production_eligible),
            "http429Count": int(http_429_count),
            "http403Count": int(http_403_count),
            "probePageCount": int(probe_page_count),
            "emptyExtractCount": int(empty_extract_count),
            "duplicateCount": int(duplicate_count),
            "deadLetterCount": int(dead_letter_count),
            "stageFailures": stage_failures,
        },
        "executionReadiness": {
            "queueBackend": ((frontier.get("queuePolicy") or {}).get("backend")) or "",
            "measuredThroughput": {"objectsPerHour": float(objects_per_hour)},
            "firstPassRate": first_pass_rate,
            "tokenLedgerCount": int(token_ledger_count),
            "releaseVerified": bool(release_verified),
            "importVerified": bool(import_verified),
            "searchVisible": bool(search_visible),
            "recommendationFeedbackReady": bool(recommendation_feedback_ready),
        },
        "blockers": blockers,
        "warnings": warnings,
        "createdAt": now_iso(),
    }
    return report


def write_site_rollup_report(report: Mapping[str, Any]) -> Path:
    root = site_supply_root(str(report["vertical"]), str(report["siteId"]), str(report["batchId"]))
    path = root / "_shared" / "site_rollup_report.json"
    write_json(path, dict(report))
    _write_stage_triplet(root, "site_rollup", [str(path)], _gate_report("site_rollup", list(report.get("blockers") or []), list(report.get("warnings") or [])))
    return path


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(dict(payload), ensure_ascii=False, indent=2))


def handle_plan(args: argparse.Namespace) -> None:
    packet = build_site_frontier_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        daily_target=args.daily_target,
        queue_backend=args.queue_backend,
        lanes=_split_csv(args.lanes) or None,
        time_window_days=args.time_window_days,
        start_date=args.start_date,
        end_date=args.end_date,
        entry_urls=_split_csv(args.entry_urls) or None,
        allowed_paths=_split_csv(args.allowed_paths) or None,
        admission_mode=args.admission_mode,
    )
    if args.write:
        write_site_frontier_packet(packet)
    _print(packet)
    if not packet["gate"]["passed"]:
        raise SystemExit(1)


def handle_candidate(args: argparse.Namespace) -> None:
    packet = build_site_candidate_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        url=args.url,
        lane=args.lane,
        title=args.title,
        text=args.text or "",
        published_at=args.published_at,
        author=args.author or "",
        assets=_parse_assets(args.assets, source_url=args.url),
        entity_mentions=_split_csv(args.entity_mentions),
        tag_mentions=_split_csv(args.tag_mentions),
    )
    if args.write:
        write_site_candidate_packet(packet)
    _print(packet)
    if not packet["gate"]["passed"]:
        raise SystemExit(1)


def handle_score(args: argparse.Namespace) -> None:
    root = site_supply_root(args.vertical, args.site_id, args.batch)
    ref = args.candidate_ref or _stable_ref("candidate", args.url)
    candidate = read_json(_candidate_path(root, ref))
    packet = build_site_score_packet(candidate, duplicate=args.duplicate)
    if args.write:
        write_site_score_packet(packet)
    _print(packet)
    if not packet["gate"]["passed"]:
        raise SystemExit(1)


def handle_map(args: argparse.Namespace) -> None:
    root = site_supply_root(args.vertical, args.site_id, args.batch)
    ref = args.candidate_ref or _stable_ref("candidate", args.url)
    candidate = read_json(_candidate_path(root, ref))
    score = read_json(_score_path(root, ref))
    packet = build_site_map_packet(candidate, score)
    if args.write:
        write_site_map_packet(packet)
    _print(packet)
    if not packet["gate"]["passed"]:
        raise SystemExit(1)


def handle_rollup(args: argparse.Namespace) -> None:
    report = build_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=args.objects_per_hour,
        first_pass_rate=args.first_pass_rate,
        token_ledger_count=args.token_ledger_count,
        release_verified=args.release_verified,
        import_verified=args.import_verified,
        search_visible=args.search_visible,
        recommendation_feedback_ready=args.recommendation_feedback_ready,
        http_429_count=args.http_429_count,
        http_403_count=args.http_403_count,
        probe_page_count=args.probe_page_count,
        empty_extract_count=args.empty_extract_count,
        duplicate_count=args.duplicate_count,
        dead_letter_count=args.dead_letter_count,
    )
    if args.write:
        write_site_rollup_report(report)
    _print(report)
    if not report["passed"]:
        raise SystemExit(1)


def handle_quality_report(args: argparse.Namespace) -> None:
    report = build_site_quality_distribution_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
    )
    if args.write:
        write_site_quality_distribution_report(report)
    _print(report)
    if not (report.get("gate") or {}).get("passed"):
        raise SystemExit(1)


def handle_rerollup(args: argparse.Namespace) -> None:
    report = _recomputed_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=args.objects_per_hour,
    )
    if args.write:
        write_site_rollup_report(report)
    _print(report)
    if not report["passed"]:
        raise SystemExit(1)


def handle_downstream_evidence(args: argparse.Namespace) -> None:
    if args.write:
        repair_content_plan_source_site_provenance(
            vertical=args.vertical,
            site_id=args.site_id,
            batch_id=args.batch,
            task_id=args.task,
            target_batch=args.target_batch,
        )
    report = build_downstream_e2e_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        task_id=args.task,
        target_batch=args.target_batch,
        env=args.env,
        allow_dry_run_import=args.allow_dry_run_import,
    )
    if args.write:
        write_downstream_e2e_report(report)
    _print(report)
    if not (report.get("gate") or {}).get("passed"):
        raise SystemExit(1)


def handle_repair_fetch(args: argparse.Namespace) -> None:
    root = site_supply_root(args.vertical, args.site_id, args.batch)
    ref = args.candidate_ref or _stable_ref("candidate", args.url)
    previous = read_json(root / "fetches" / ref / "site_fetch_packet.json")
    frontier = _frontier_packet(args.vertical, args.site_id, args.batch)
    profile = frontier.get("profile") if isinstance(frontier.get("profile"), Mapping) else {}
    url = str(previous.get("canonicalUrl") or args.url or "").strip()
    if not url:
        raise SystemExit("repair-fetch requires --url or an existing fetch packet canonicalUrl")
    payload, error, attempts = _fetch_with_retry(
        url,
        source=profile,
        retry_budget=args.fetch_retry_budget,
        retry_delay_seconds=args.fetch_retry_delay,
    )
    extraction = previous.get("extraction") if isinstance(previous.get("extraction"), Mapping) else {}
    mentions = previous.get("semanticMentions") if isinstance(previous.get("semanticMentions"), Mapping) else {}
    fetch_packet = build_site_fetch_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        url=url,
        lane=str(previous.get("lane") or args.lane),
        title=str(extraction.get("title") or previous.get("title") or ""),
        author=str(extraction.get("author") or ""),
        published_at=str(extraction.get("publishedAt") or "") or args.published_at,
        entity_mentions=[str(x) for x in (mentions.get("entities") or [])],
        tag_mentions=[str(x) for x in (mentions.get("tags") or [])],
        min_text_chars=args.min_text_chars,
        payload=payload,
        error=error,
        attempts=attempts,
    )
    write_site_fetch_packet(
        fetch_packet,
        html_bytes=(payload or {}).get("htmlBytes") if isinstance((payload or {}).get("htmlBytes"), bytes) else None,
    )
    if fetch_packet["gate"]["passed"]:
        candidate = build_site_candidate_from_fetch(fetch_packet)
        write_site_candidate_packet(candidate)
        if candidate["gate"]["passed"]:
            score = build_site_score_packet(candidate)
            write_site_score_packet(score)
            if score["gate"]["passed"]:
                mapped = build_site_map_packet(candidate, score)
                write_site_map_packet(mapped)
    report = _recomputed_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=args.objects_per_hour,
    )
    write_site_rollup_report(report)
    _print({"fetch": fetch_packet, "rollup": report})
    if not fetch_packet["gate"]["passed"] or not report["passed"]:
        raise SystemExit(1)


def _trial_text(index: int) -> str:
    return (
        f"这是第 {index} 个网站维度结构试跑候选，包含路线、地点、时间、交通、体验判断、"
        "证据映射、实体 mention 和后续 content_plan handoff 所需的事实边界。"
        "该文本用于验证 stage gate、repair、score、map 和 rollup 的结构稳定性，不代表真实发布正文。"
    )


def _trial_lane_counts(args: argparse.Namespace) -> dict[str, int]:
    explicit = {
        "article": args.article_count,
        "image": args.image_count,
        "video": args.video_count,
    }
    if any(value is not None for value in explicit.values()):
        counts = {lane: int(value or 0) for lane, value in explicit.items()}
        total = sum(counts.values())
        if args.target_count is not None and int(args.target_count) != total:
            raise SystemExit("--target-count must equal article/image/video count sum when lane counts are explicit")
        if total <= 0:
            raise SystemExit("at least one lane count must be >0")
        return {lane: count for lane, count in counts.items() if count > 0}
    if args.target_count is None:
        raise SystemExit("--target-count is required unless explicit lane counts are provided")
    return {"article": int(args.target_count)}


def _trial_url(profile: Mapping[str, Any], *, batch_id: str, lane: str, index: int) -> str:
    allowed_paths = [str(x) for x in (profile.get("allowedPaths") or []) if str(x)]
    pattern = allowed_paths[0] if allowed_paths else "https://example.com/*"
    token = f"site-trial/{lane}/{batch_id}-{index:06d}.html"
    if "*" in pattern:
        return pattern.replace("*", token, 1)
    return f"{pattern.rstrip('/')}/{token}"


def _trial_assets(profile: Mapping[str, Any], *, url: str, lane: str, index: int) -> list[dict[str, Any]]:
    if lane not in {"image", "video"}:
        return []
    platform = str(profile.get("platform") or profile.get("siteId") or "site")
    ext = "jpg" if lane == "image" else "mp4"
    terms_url = str(profile.get("termsUrl") or url)
    return [{
        "assetId": _stable_ref("asset", url, lane, index),
        "url": f"{url}#controlled-{lane}-{index:06d}.{ext}",
        "sourceUrl": url,
        "license": "validation_only_not_for_publish",
        "credit": f"{platform} controlled trial",
        "termsUrl": terms_url,
        "usageScope": "site_supply_controlled_trial_only",
        "modelReleaseStatus": "not_required",
        "publishable": False,
    }]


def handle_trial(args: argparse.Namespace) -> None:
    packet = build_site_frontier_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        daily_target=args.daily_target,
        queue_backend=args.queue_backend,
        end_date=args.end_date,
        admission_mode=args.admission_mode,
    )
    write_site_frontier_packet(packet)
    if not packet["gate"]["passed"]:
        _print(packet)
        raise SystemExit(1)
    lane_counts = _trial_lane_counts(args)
    profile = packet.get("profile") or {}
    global_idx = 0
    for lane, count in lane_counts.items():
        for lane_idx in range(1, count + 1):
            global_idx += 1
            url = _trial_url(profile, batch_id=args.batch, lane=lane, index=global_idx)
            candidate = build_site_candidate_packet(
                vertical=args.vertical,
                site_id=args.site_id,
                batch_id=args.batch,
                url=url,
                lane=lane,
                title=f"{args.batch} {lane} 受控试跑候选 {lane_idx:06d}",
                text=_trial_text(global_idx) if lane == "article" else "",
                published_at=args.end_date,
                assets=_trial_assets(profile, url=url, lane=lane, index=global_idx),
                entity_mentions=[f"地点/景区/结构试跑景区{global_idx:06d}"],
                tag_mentions=["Topic/旅行/玩法/自然风光", f"Format/内容载体/{lane}"],
            )
            write_site_candidate_packet(candidate)
            if not candidate["gate"]["passed"]:
                _print(candidate)
                raise SystemExit(1)
            score = build_site_score_packet(candidate)
            write_site_score_packet(score)
            if not score["gate"]["passed"]:
                _print(score)
                raise SystemExit(1)
            mapped = build_site_map_packet(candidate, score)
            write_site_map_packet(mapped)
            if not mapped["gate"]["passed"]:
                _print(mapped)
                raise SystemExit(1)
    rollup = build_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=args.objects_per_hour,
        first_pass_rate=args.first_pass_rate,
        token_ledger_count=args.token_ledger_count if args.token_ledger_count is not None else global_idx,
        release_verified=args.release_verified,
        import_verified=args.import_verified,
        search_visible=args.search_visible,
        recommendation_feedback_ready=args.recommendation_feedback_ready,
    )
    write_site_rollup_report(rollup)
    _print(rollup)
    if not rollup["passed"]:
        raise SystemExit(1)


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
    query_target = _resolve_known_entity_target(query, expected_entity_type="地点/景区")
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
                query_target = _resolve_known_entity_target(query, expected_entity_type="地点/景区")
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
                query_target = _resolve_known_entity_target(query, expected_entity_type="地点/景区")
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
        for row in _qunar_search_candidates(
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
            return fetch_source_payload(url, source=source), "", attempts
        except Exception as exc:
            last_error = str(exc)
            if attempt >= int(retry_budget):
                break
            delay = max(float(retry_delay_seconds), float(attempt + 1))
            time.sleep(min(delay, 10.0))
    return None, last_error, attempts


def handle_crawl(args: argparse.Namespace) -> None:
    started = time.monotonic()
    target_count = int(args.target_count)
    overfetch_ratio = max(1.0, float(getattr(args, "frontier_overfetch_ratio", 1.0)))
    args.discovery_target_count = max(target_count, int(math.ceil(target_count * overfetch_ratio)))
    frontier = build_site_frontier_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        daily_target=args.daily_target,
        queue_backend=args.queue_backend,
        lanes=[args.lane],
        end_date=args.end_date,
        admission_mode=ADMISSION_BATCH_CRAWL,
    )
    write_site_frontier_packet(frontier)
    if not frontier["gate"]["passed"]:
        _print(frontier)
        raise SystemExit(1)

    discovered = _crawl_input_candidates(args, frontier)
    if not discovered:
        raise SystemExit("no real crawl input URLs discovered; repair at site_frontier discovery")
    root = site_supply_root(args.vertical, args.site_id, args.batch)
    frontier_candidates_path = _write_frontier_candidates(root, discovered)
    frontier["frontier"] = {
        **dict(frontier.get("frontier") or {}),
        "targetCount": target_count,
        "discoveryTargetCount": int(args.discovery_target_count),
        "frontierOverfetchRatio": overfetch_ratio,
        "discoveredCount": len(discovered),
        "maxDiscoveryRequests": int(args.max_discovery_requests),
        "queryStrategy": str(getattr(args, "query_strategy", QUERY_STRATEGY_MANUAL) or QUERY_STRATEGY_MANUAL),
        "frontierCandidates": str(frontier_candidates_path),
    }
    if len(discovered) < target_count:
        frontier["gate"] = _gate_report(
            "site_frontier",
            [f"frontier discovery produced {len(discovered)} URLs < targetCount {target_count}"],
            [],
        )
        write_site_frontier_packet(frontier)
        _print(frontier)
        raise SystemExit(1)
    write_site_frontier_packet(frontier)
    if bool(getattr(args, "frontier_only", False)):
        _print(frontier)
        return

    profile = frontier.get("profile") if isinstance(frontier.get("profile"), Mapping) else {}
    throttle_seconds = _rate_limit_seconds(profile)
    if args.throttle_seconds is not None:
        throttle_seconds = max(throttle_seconds, float(args.throttle_seconds))

    http_429 = http_403 = probe_pages = empty_extract = dead_letters = 0
    success_count = 0
    attempted = 0
    last_fetch_at = 0.0
    for row in discovered:
        if success_count >= target_count:
            break
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        candidate_ref = _fetch_candidate_ref(url)
        if _existing_crawl_handoff_ready(root, candidate_ref):
            success_count += 1
            continue
        if attempted and throttle_seconds > 0:
            elapsed_since_fetch = time.monotonic() - last_fetch_at
            if elapsed_since_fetch < throttle_seconds:
                time.sleep(throttle_seconds - elapsed_since_fetch)
        attempted += 1
        payload, error, attempts_for_url = _fetch_with_retry(
            url,
            source=profile,
            retry_budget=args.fetch_retry_budget,
            retry_delay_seconds=args.fetch_retry_delay,
        )
        last_fetch_at = time.monotonic()
        fetch_packet = build_site_fetch_packet(
            vertical=args.vertical,
            site_id=args.site_id,
            batch_id=args.batch,
            url=url,
            lane=str(row.get("lane") or args.lane),
            title=str(row.get("title") or ""),
            author=str(row.get("author") or ""),
            published_at=str(row.get("publishedAt") or "") or args.end_date,
            entity_mentions=[str(x) for x in (row.get("entityMentions") or [])],
            tag_mentions=[str(x) for x in (row.get("tagMentions") or [])],
            min_text_chars=args.min_text_chars,
            payload=payload,
            error=error,
            attempts=attempts_for_url,
        )
        write_site_fetch_packet(
            fetch_packet,
            html_bytes=(payload or {}).get("htmlBytes") if isinstance((payload or {}).get("htmlBytes"), bytes) else None,
        )
        c429, c403, cprobe, cempty = _classify_fetch_packet(fetch_packet)
        http_429 += c429
        http_403 += c403
        probe_pages += cprobe
        empty_extract += cempty
        if not fetch_packet["gate"]["passed"]:
            if error:
                dead_letters += 1
            if args.stop_on_first_failure:
                break
            continue

        candidate = build_site_candidate_from_fetch(fetch_packet)
        write_site_candidate_packet(candidate)
        if not candidate["gate"]["passed"]:
            continue
        score = build_site_score_packet(candidate)
        write_site_score_packet(score)
        if not score["gate"]["passed"]:
            continue
        mapped = build_site_map_packet(candidate, score)
        write_site_map_packet(mapped)
        if mapped["gate"]["passed"]:
            success_count += 1

    elapsed_hours = max((time.monotonic() - started) / 3600.0, 0.000001)
    objects_per_hour = success_count / elapsed_hours if args.objects_per_hour is None else args.objects_per_hour
    first_pass_rate = (success_count / attempted) if attempted else 0.0
    rollup = build_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=objects_per_hour,
        first_pass_rate=first_pass_rate,
        token_ledger_count=args.token_ledger_count if args.token_ledger_count is not None else success_count,
        release_verified=args.release_verified,
        import_verified=args.import_verified,
        search_visible=args.search_visible,
        recommendation_feedback_ready=args.recommendation_feedback_ready,
        http_429_count=http_429,
        http_403_count=http_403,
        probe_page_count=probe_pages,
        empty_extract_count=empty_extract,
        dead_letter_count=dead_letters,
    )
    write_site_rollup_report(rollup)
    _print(rollup)
    if not rollup["passed"]:
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("site-supply", help="网站维度内容供给线 packet/gate/rollup")
    sub = p.add_subparsers(dest="site_supply_command", required=True)

    pp = sub.add_parser("plan", help="生成 site_frontier_packet 并校验站点准入")
    pp.add_argument("--vertical", default="travel")
    pp.add_argument("--site-id", required=True)
    pp.add_argument("--batch", required=True)
    pp.add_argument("--daily-target", type=int, default=DEFAULT_DAILY_TARGET)
    pp.add_argument("--queue-backend", choices=["local_file", "reliabletask"], default="reliabletask")
    pp.add_argument("--lanes", help="逗号分隔 lane 覆盖，默认读 registry")
    pp.add_argument("--entry-urls", help="逗号分隔入口 URL/Pattern，默认读 registry")
    pp.add_argument("--allowed-paths", help="逗号分隔允许 URL pattern/path，默认读 registry")
    pp.add_argument("--admission-mode", choices=ADMISSION_MODES, default=ADMISSION_BATCH_CRAWL)
    pp.add_argument("--time-window-days", type=int, default=DEFAULT_TIME_WINDOW_DAYS)
    pp.add_argument("--start-date")
    pp.add_argument("--end-date")
    pp.add_argument("--write", action="store_true")
    pp.set_defaults(handler=handle_plan)

    pc = sub.add_parser("candidate", help="写入/校验单个 site_candidate_packet")
    pc.add_argument("--vertical", default="travel")
    pc.add_argument("--site-id", required=True)
    pc.add_argument("--batch", required=True)
    pc.add_argument("--url", required=True)
    pc.add_argument("--lane", required=True, choices=["homepage", "article", "image", "video", "knowledgeCard"])
    pc.add_argument("--title", required=True)
    pc.add_argument("--text", default="")
    pc.add_argument("--published-at")
    pc.add_argument("--author", default="")
    pc.add_argument("--assets", help="逗号分隔 assetUrl|license|credit|termsUrl|usageScope|modelReleaseStatus")
    pc.add_argument("--entity-mentions", default="")
    pc.add_argument("--tag-mentions", default="")
    pc.add_argument("--write", action="store_true")
    pc.set_defaults(handler=handle_candidate)

    ps = sub.add_parser("score", help="根据 candidate 写 site_score_packet")
    ps.add_argument("--vertical", default="travel")
    ps.add_argument("--site-id", required=True)
    ps.add_argument("--batch", required=True)
    group = ps.add_mutually_exclusive_group(required=True)
    group.add_argument("--candidate-ref")
    group.add_argument("--url")
    ps.add_argument("--duplicate", action="store_true")
    ps.add_argument("--write", action="store_true")
    ps.set_defaults(handler=handle_score)

    pm = sub.add_parser("map", help="把合格候选映射为 content_plan handoff")
    pm.add_argument("--vertical", default="travel")
    pm.add_argument("--site-id", required=True)
    pm.add_argument("--batch", required=True)
    group_m = pm.add_mutually_exclusive_group(required=True)
    group_m.add_argument("--candidate-ref")
    group_m.add_argument("--url")
    pm.add_argument("--write", action="store_true")
    pm.set_defaults(handler=handle_map)

    pcp = sub.add_parser("content-plan", help="把 site_map 合格候选物化为标准 content_plan batch")
    pcp.add_argument("--vertical", default="travel")
    pcp.add_argument("--site-id", required=True)
    pcp.add_argument("--batch", required=True, help="site_supply batch")
    pcp.add_argument("--task", required=True, help="目标 runtime taskId")
    pcp.add_argument("--target-batch", required=True, help="目标 runtime batchId")
    pcp.add_argument("--limit", type=int, default=10)
    pcp.add_argument("--refs", default="", help="逗号分隔 candidateRef；默认取所有 site_map eligible")
    pcp.add_argument("--entity-type", default="地点/景区")
    pcp.add_argument("--intent", default="行前指南")
    pcp.add_argument("--audience", default="leisureTraveler")
    pcp.add_argument("--max-images-per-candidate", type=int, default=3)
    pcp.add_argument("--allow-partial", action="store_true")
    pcp.set_defaults(handler=handle_content_plan)

    pr = sub.add_parser("rollup", help="聚合站点漏斗与规模化准出证据")
    pr.add_argument("--vertical", default="travel")
    pr.add_argument("--site-id", required=True)
    pr.add_argument("--batch", required=True)
    pr.add_argument("--objects-per-hour", type=float, default=0.0)
    pr.add_argument("--first-pass-rate", type=float)
    pr.add_argument("--token-ledger-count", type=int, default=0)
    pr.add_argument("--release-verified", action="store_true")
    pr.add_argument("--import-verified", action="store_true")
    pr.add_argument("--search-visible", action="store_true")
    pr.add_argument("--recommendation-feedback-ready", action="store_true")
    pr.add_argument("--http-429-count", type=int, default=0)
    pr.add_argument("--http-403-count", type=int, default=0)
    pr.add_argument("--probe-page-count", type=int, default=0)
    pr.add_argument("--empty-extract-count", type=int, default=0)
    pr.add_argument("--duplicate-count", type=int, default=0)
    pr.add_argument("--dead-letter-count", type=int, default=0)
    pr.add_argument("--write", action="store_true")
    pr.set_defaults(handler=handle_rollup)

    pqr = sub.add_parser("quality-report", help="聚合站点候选质量分布与商用准入证据")
    pqr.add_argument("--vertical", default="travel")
    pqr.add_argument("--site-id", required=True)
    pqr.add_argument("--batch", required=True)
    pqr.add_argument("--write", action="store_true")
    pqr.set_defaults(handler=handle_quality_report)

    prr = sub.add_parser("rerollup", help="按现有对象证据重算站点漏斗与准出")
    prr.add_argument("--vertical", default="travel")
    prr.add_argument("--site-id", required=True)
    prr.add_argument("--batch", required=True)
    prr.add_argument("--objects-per-hour", type=float)
    prr.add_argument("--write", action="store_true")
    prr.set_defaults(handler=handle_rerollup)

    pde = sub.add_parser("downstream-evidence", help="汇总 content_plan→ship/import→search/reco 证据并回写站点准出")
    pde.add_argument("--vertical", default="travel")
    pde.add_argument("--site-id", required=True)
    pde.add_argument("--batch", required=True, help="source site_supply batch")
    pde.add_argument("--task", required=True)
    pde.add_argument("--target-batch", required=True)
    pde.add_argument("--env", default="gamma")
    pde.add_argument(
        "--allow-dry-run-import",
        action="store_true",
        help="仅本地受控 rehearsal 允许 dry-run importer 作为导入命令链证据",
    )
    pde.add_argument("--write", action="store_true")
    pde.set_defaults(handler=handle_downstream_evidence)

    prf = sub.add_parser("repair-fetch", help="重新抓取单个失败候选并回灌 extract→score→map")
    prf.add_argument("--vertical", default="travel")
    prf.add_argument("--site-id", required=True)
    prf.add_argument("--batch", required=True)
    group_rf = prf.add_mutually_exclusive_group(required=True)
    group_rf.add_argument("--candidate-ref")
    group_rf.add_argument("--url")
    prf.add_argument("--lane", choices=["article"], default="article")
    prf.add_argument("--published-at")
    prf.add_argument("--min-text-chars", type=int, default=DEFAULT_FETCH_MIN_TEXT_CHARS)
    prf.add_argument("--fetch-retry-budget", type=int, default=2)
    prf.add_argument("--fetch-retry-delay", type=float, default=1.0)
    prf.add_argument("--objects-per-hour", type=float)
    prf.set_defaults(handler=handle_repair_fetch)

    pt = sub.add_parser("trial", help="结构试跑：生成受控候选并执行 frontier→candidate→score→map→rollup")
    pt.add_argument("--vertical", default="travel")
    pt.add_argument("--site-id", required=True)
    pt.add_argument("--batch", required=True)
    pt.add_argument("--target-count", type=int)
    pt.add_argument("--article-count", type=int)
    pt.add_argument("--image-count", type=int)
    pt.add_argument("--video-count", type=int)
    pt.add_argument("--daily-target", type=int, default=10_000)
    pt.add_argument("--queue-backend", choices=["local_file", "reliabletask"], default="reliabletask")
    pt.add_argument("--admission-mode", choices=ADMISSION_MODES, default=ADMISSION_CONTROLLED_TRIAL)
    pt.add_argument("--end-date", default=dt.date.today().isoformat())
    pt.add_argument("--objects-per-hour", type=float, default=500.0)
    pt.add_argument("--first-pass-rate", type=float, default=0.82)
    pt.add_argument("--token-ledger-count", type=int)
    pt.add_argument("--release-verified", action="store_true")
    pt.add_argument("--import-verified", action="store_true")
    pt.add_argument("--search-visible", action="store_true")
    pt.add_argument("--recommendation-feedback-ready", action="store_true")
    pt.set_defaults(handler=handle_trial)

    pcrawl = sub.add_parser("crawl", help="真实抓取：frontier→fetch→candidate→score→map→rollup")
    pcrawl.add_argument("--vertical", default="travel")
    pcrawl.add_argument("--site-id", required=True)
    pcrawl.add_argument("--batch", required=True)
    pcrawl.add_argument("--target-count", type=int, required=True)
    pcrawl.add_argument("--lane", choices=["article"], default="article")
    pcrawl.add_argument("--queries", default="", help="逗号分隔站内发现 query；qunar_guide 复用去哪儿搜索发现")
    pcrawl.add_argument("--query-strategy", choices=QUERY_STRATEGIES, default=QUERY_STRATEGY_MANUAL)
    pcrawl.add_argument("--max-search-pages", type=int, default=3)
    pcrawl.add_argument("--max-discovery-requests", type=int, default=500)
    pcrawl.add_argument("--discovery-request-timeout", type=int, default=20)
    pcrawl.add_argument("--discovery-timeout-seconds", type=float, default=0.0)
    pcrawl.add_argument("--frontier-overfetch-ratio", type=float, default=1.05)
    pcrawl.add_argument("--seed-urls", default="", help="逗号分隔显式 URL，仍需通过 registry/frontier/fetch 门")
    pcrawl.add_argument("--seed-file", help="每行一个显式 URL，仍需通过 registry/frontier/fetch 门")
    pcrawl.add_argument("--entity-mentions", default="")
    pcrawl.add_argument("--tag-mentions", default="")
    pcrawl.add_argument("--daily-target", type=int, default=10_000)
    pcrawl.add_argument("--queue-backend", choices=["local_file", "reliabletask"], default="reliabletask")
    pcrawl.add_argument("--end-date", default=dt.date.today().isoformat())
    pcrawl.add_argument("--min-text-chars", type=int, default=DEFAULT_FETCH_MIN_TEXT_CHARS)
    pcrawl.add_argument("--objects-per-hour", type=float)
    pcrawl.add_argument("--token-ledger-count", type=int)
    pcrawl.add_argument("--fetch-retry-budget", type=int, default=2)
    pcrawl.add_argument("--fetch-retry-delay", type=float, default=1.0)
    pcrawl.add_argument("--throttle-seconds", type=float)
    pcrawl.add_argument("--frontier-only", action="store_true")
    pcrawl.add_argument("--stop-on-first-failure", action="store_true")
    pcrawl.add_argument("--release-verified", action="store_true")
    pcrawl.add_argument("--import-verified", action="store_true")
    pcrawl.add_argument("--search-visible", action="store_true")
    pcrawl.add_argument("--recommendation-feedback-ready", action="store_true")
    pcrawl.set_defaults(handler=handle_crawl)
