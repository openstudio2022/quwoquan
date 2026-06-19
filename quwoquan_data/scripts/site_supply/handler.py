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
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.io import read_json, write_json
from _common.paths import DATA_ROOT, RUNTIME_ROOT, now_iso


FRONTIER_SCHEMA = "quwoquan.site_supply.site_frontier_packet/1"
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
    candidate_paths = sorted((root / "candidates").glob("*/site_candidate_packet.json"))
    score_paths = sorted((root / "scores").glob("*/site_score_packet.json"))
    map_paths = sorted((root / "map").glob("*/site_map_packet.json"))
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
        "site_extract": 0,
        "site_score": 0,
        "site_map": 0,
        "missing_score": 0,
        "missing_map": 0,
        "orphan_score": 0,
        "orphan_map": 0,
        "missing_object_evidence": 0,
    }
    candidate_refs = {str(c.get("candidateRef") or "") for c in candidates if str(c.get("candidateRef") or "")}
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
    if total:
        if (http_429_count + http_403_count) / total > 0.05:
            blockers.append("site throttle/forbidden rate exceeds 5%")
        if probe_page_count / total > 0.02:
            blockers.append("probe page rate exceeds 2%")
        if empty_extract_count / total > 0.05:
            blockers.append("empty extract rate exceeds 5%")
        if duplicate_count / total > 0.40:
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
