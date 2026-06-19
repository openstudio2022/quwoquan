"""qwq-data site-supply — 网站维度内容供给线前半段契约与门禁。

本模块只做站点级 frontier/candidate/score/map/rollup 的 IO、契约和门禁。
真实语义抽取与正文创作仍由 Agent 与现有 content_plan/produce/review 主线承接。
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.io import read_json, write_json
from _common.paths import DATA_ROOT, RUNTIME_ROOT, now_iso
from download.fetch import fetch_source_payload


FRONTIER_SCHEMA = "quwoquan.site_supply.site_frontier_packet/1"
FETCH_SCHEMA = "quwoquan.site_supply.site_fetch_packet/1"
CANDIDATE_SCHEMA = "quwoquan.site_supply.site_candidate_packet/1"
SCORE_SCHEMA = "quwoquan.site_supply.site_score_packet/1"
MAP_SCHEMA = "quwoquan.site_supply.site_map_packet/1"
ROLLUP_SCHEMA = "quwoquan.site_supply.site_rollup_report/1"
GATE_SCHEMA = "quwoquan.site_supply.gate_report/1"
STAGE_SCHEMA = "quwoquan.site_supply.stage_result/1"
REPAIR_SCHEMA = "quwoquan.site_supply.repair_report/1"

DEFAULT_TIME_WINDOW_DAYS = 730
DEFAULT_DAILY_TARGET = 100_000
MIN_ARTICLE_TEXT_CHARS = 80
MIN_PRODUCTION_SCORE = 0.45
DEFAULT_FETCH_MIN_TEXT_CHARS = 120
ADMISSION_BATCH_CRAWL = "batch_crawl"
ADMISSION_CONTROLLED_TRIAL = "controlled_trial"
ADMISSION_MODES = (ADMISSION_BATCH_CRAWL, ADMISSION_CONTROLLED_TRIAL)
REQUIRED_ASSET_RIGHTS_FIELDS = ("license", "credit", "sourceUrl", "termsUrl", "usageScope")
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

    extracted_title = title.strip() or _first_text_line(text, fallback=url)
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
        },
        "semanticMentions": {
            "entities": entity_mentions or [],
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
        assets=[],
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
        "productionEligible": production_eligible,
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
            "entityHomepageCandidates": list(mentions.get("entities") or []),
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
            blockers.append(f"{ref}: site_score gate failed; repair at site_score")
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
    if dead_letter_count:
        blockers.append(f"deadLetterCount must be zero before scale; got {dead_letter_count}")
    stability_denominator = len(fetches) or total
    if stability_denominator:
        if (http_429_count + http_403_count) / stability_denominator > 0.05:
            blockers.append("site throttle/forbidden rate exceeds 5%")
        if probe_page_count / stability_denominator > 0.02:
            blockers.append("probe page rate exceeds 2%")
        if empty_extract_count / stability_denominator > 0.05:
            blockers.append("empty extract rate exceeds 5%")
        if duplicate_count / stability_denominator > 0.40:
            warnings.append("duplicate rate exceeds 40%; keep dedupe budget visible before expansion")
    if production_eligible and handoff_count < production_eligible:
        blockers.append("all productionEligible candidates must have site_map handoff packets")
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


def _qunar_search_candidates(
    *,
    queries: list[str],
    max_pages: int,
    limit: int,
    window: Mapping[str, Any],
    request_budget: int,
) -> list[dict[str, Any]]:
    if not queries or limit <= 0:
        return []
    from download.research_plan import _curl_json  # Reuse existing entity-line discovery IO.

    candidates: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    requests_used = 0
    start = _date(str(window.get("from")))
    end = _date(str(window.get("to")))
    for query in queries:
        encoded = urllib.parse.quote(query)
        for page in range(1, max(1, int(max_pages)) + 1):
            if requests_used >= int(request_budget):
                return candidates
            requests_used += 1
            data = _curl_json(f"https://touch.travel.qunar.com/search?_json&q={encoded}&page={page}", timeout=20)
            if data.get("ret") is not True:
                if requests_used >= int(request_budget):
                    return candidates
                requests_used += 1
                data = _curl_json(f"https://touch.travel.qunar.com/search?_json=&q={encoded}&page={page}", timeout=20)
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
                entity_mentions = [x for x in [city, *dests, *route[:8]] if x]
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
                    return candidates
    return candidates


def _crawl_input_candidates(args: argparse.Namespace, frontier: Mapping[str, Any]) -> list[dict[str, Any]]:
    target_count = max(0, int(args.target_count or 0))
    explicit_urls = _split_csv(args.seed_urls) + _read_seed_file(args.seed_file)
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
    if remaining > 0 and args.site_id == "qunar_guide":
        for row in _qunar_search_candidates(
            queries=_split_csv(args.queries),
            max_pages=args.max_search_pages,
            limit=remaining,
            window=frontier.get("timeWindow") or {},
            request_budget=args.max_discovery_requests,
        ):
            if row["url"] in seen:
                continue
            seen.add(row["url"])
            candidates.append(row)
            if target_count and len(candidates) >= target_count:
                break
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
    empty = 1 if "empty" in blockers or "too short" in blockers else 0
    return http_429, http_403, probe, empty


def _fetch_with_retry(url: str, *, retry_budget: int, retry_delay_seconds: float) -> tuple[Mapping[str, Any] | None, str, int]:
    attempts = 0
    last_error = ""
    for attempt in range(0, max(0, int(retry_budget)) + 1):
        attempts += 1
        try:
            return fetch_source_payload(url), "", attempts
        except Exception as exc:
            last_error = str(exc)
            if attempt >= int(retry_budget):
                break
            delay = max(float(retry_delay_seconds), float(attempt + 1))
            time.sleep(min(delay, 10.0))
    return None, last_error, attempts


def handle_crawl(args: argparse.Namespace) -> None:
    started = time.monotonic()
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
    frontier["frontier"] = {
        **dict(frontier.get("frontier") or {}),
        "targetCount": int(args.target_count),
        "discoveredCount": len(discovered),
        "maxDiscoveryRequests": int(args.max_discovery_requests),
    }
    if len(discovered) < int(args.target_count):
        frontier["gate"] = _gate_report(
            "site_frontier",
            [f"frontier discovery produced {len(discovered)} URLs < targetCount {int(args.target_count)}"],
            [],
        )
        write_site_frontier_packet(frontier)
        _print(frontier)
        raise SystemExit(1)
    write_site_frontier_packet(frontier)

    profile = frontier.get("profile") if isinstance(frontier.get("profile"), Mapping) else {}
    throttle_seconds = _rate_limit_seconds(profile)
    if args.throttle_seconds is not None:
        throttle_seconds = max(throttle_seconds, float(args.throttle_seconds))

    http_429 = http_403 = probe_pages = empty_extract = dead_letters = 0
    success_count = 0
    attempted = 0
    last_fetch_at = 0.0
    for row in discovered:
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        if attempted and throttle_seconds > 0:
            elapsed_since_fetch = time.monotonic() - last_fetch_at
            if elapsed_since_fetch < throttle_seconds:
                time.sleep(throttle_seconds - elapsed_since_fetch)
        attempted += 1
        payload, error, attempts_for_url = _fetch_with_retry(
            url,
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
    pcrawl.add_argument("--max-search-pages", type=int, default=3)
    pcrawl.add_argument("--max-discovery-requests", type=int, default=500)
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
    pcrawl.add_argument("--stop-on-first-failure", action="store_true")
    pcrawl.add_argument("--release-verified", action="store_true")
    pcrawl.add_argument("--import-verified", action="store_true")
    pcrawl.add_argument("--search-visible", action="store_true")
    pcrawl.add_argument("--recommendation-feedback-ready", action="store_true")
    pcrawl.set_defaults(handler=handle_crawl)
