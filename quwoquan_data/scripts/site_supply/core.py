"""Core site-supply registry, frontier and stage artifacts."""
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
from _common.paths import _REPO_DATA_ROOT, RUNTIME_ROOT, now_iso
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

ADMISSION_LICENSED_ASSET_INGEST = "licensed_asset_ingest"

ADMISSION_ATTRIBUTION_PUBLISH_INGEST = "attribution_publish_ingest"

ADMISSION_MODES = (
    ADMISSION_BATCH_CRAWL,
    ADMISSION_CONTROLLED_TRIAL,
    ADMISSION_LICENSED_ASSET_INGEST,
    ADMISSION_ATTRIBUTION_PUBLISH_INGEST,
)

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
    return _REPO_DATA_ROOT / "verticals" / vertical / "sources" / "source_registry.yaml"

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
        "articleCommercialAdmission": str(profile.get("articleCommercialAdmission") or ""),
        "controlledTrial": dict(profile.get("controlledTrial") or {}),
        "attributionPublish": dict(profile.get("attributionPublish") or {}),
        "discoveryStrategy": dict(profile.get("discoveryStrategy") or {}),
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
    content_lanes = {str(x).strip() for x in (profile.get("contentLanes") or []) if str(x).strip()}
    article_admission = str(profile.get("articleCommercialAdmission") or "").strip()
    admission_mode = admission_mode if admission_mode in ADMISSION_MODES else ADMISSION_BATCH_CRAWL
    if not profile.get("rawProfilePresent"):
        blockers.append("siteCrawlProfile missing from source registry")
    if "article" in content_lanes:
        if not article_admission:
            blockers.append("articleCommercialAdmission is required for article-capable sites")
        elif admission_mode == ADMISSION_BATCH_CRAWL and article_admission != "commercial_release":
            blockers.append(
                f"articleCommercialAdmission={article_admission} cannot enter commercial article batch crawl"
            )
    if admission_mode == ADMISSION_CONTROLLED_TRIAL:
        if not (bool(controlled.get("allowed")) or (profile.get("fetchable") and profile.get("crawlAllowed"))):
            blockers.append("controlledTrial.allowed must be true or site must be fetchable+crawlAllowed")
        if controlled and not bool(controlled.get("validationOnly", True)):
            blockers.append("controlledTrial.validationOnly must remain true")
        if bool(controlled.get("rawFetchAllowed")):
            blockers.append("controlledTrial.rawFetchAllowed cannot be true")
        if bool(controlled.get("publishableAssetsAllowed")):
            blockers.append("controlledTrial.publishableAssetsAllowed cannot be true")
        if not str(profile.get("termsUrl") or "").strip():
            blockers.append("siteCrawlProfile.termsUrl is required for controlled trial")
        if not (profile.get("fetchable") and profile.get("crawlAllowed")):
            warnings.append("controlled trial does not grant raw batch crawl; generated candidates are validation-only")
    elif admission_mode == ADMISSION_LICENSED_ASSET_INGEST:
        rights_policy = str(profile.get("rightsPolicy") or "")
        if rights_policy not in {"licensed_asset_required", "commercial_license_required"}:
            blockers.append(
                "licensed_asset_ingest requires rightsPolicy=licensed_asset_required "
                "or commercial_license_required"
            )
        if str(profile.get("fetchMode") or "") not in {"licensed_api", "manual_authorization"}:
            blockers.append("licensed_asset_ingest requires fetchMode=licensed_api or manual_authorization")
        if str(profile.get("loginPolicy") or "") != "manual_authorization_required":
            blockers.append("licensed_asset_ingest requires loginPolicy=manual_authorization_required")
        if not str(profile.get("termsUrl") or "").strip():
            blockers.append("siteCrawlProfile.termsUrl is required for licensed asset ingest")
        warnings.append("licensed asset ingest must use an authorization manifest; raw site crawl is disabled")
    elif admission_mode == ADMISSION_ATTRIBUTION_PUBLISH_INGEST:
        rights_policy = str(profile.get("rightsPolicy") or "")
        attribution = (
            profile.get("attributionPublish")
            if isinstance(profile.get("attributionPublish"), Mapping)
            else {}
        )
        evidence_fields = [
            str(item).strip()
            for item in (attribution.get("evidenceFields") or [])
            if str(item).strip()
        ]
        if rights_policy != "attribution_no_watermark":
            blockers.append("attribution_publish_ingest requires rightsPolicy=attribution_no_watermark")
        if str(profile.get("fetchMode") or "") != "attribution_manifest":
            blockers.append("attribution_publish_ingest requires fetchMode=attribution_manifest")
        if str(profile.get("loginPolicy") or "") != "public_only":
            blockers.append("attribution_publish_ingest requires loginPolicy=public_only")
        if not str(profile.get("termsUrl") or "").strip():
            blockers.append("siteCrawlProfile.termsUrl is required for attribution publish ingest")
        if not bool(attribution.get("allowed")):
            blockers.append("siteCrawlProfile.attributionPublish.allowed must be true for attribution publish ingest")
        if not evidence_fields:
            blockers.append("siteCrawlProfile.attributionPublish.evidenceFields must not be empty")
        warnings.append(
            "attribution publish ingest must use a per-asset attribution manifest and original image bytes; "
            "raw site crawl is disabled"
        )
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
        elif admission_mode == ADMISSION_LICENSED_ASSET_INGEST:
            warnings.append("maxPagesPerDay=0; licensed asset ingest must not perform raw fetch")
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
        "sourceRegistryRef": str(_site_registry_path(vertical).relative_to(_REPO_DATA_ROOT)),
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


def _fetch_candidate_ref(url: str) -> str:
    return _stable_ref("candidate", url)

__all__ = [name for name in globals() if not name.startswith("__")]
