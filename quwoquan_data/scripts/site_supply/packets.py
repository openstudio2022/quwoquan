"""Site-supply fetch, candidate, score and map packets."""
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
from site_supply.targets import _site_map_knowledge_gap_candidates

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


def _packet_gate_passed(packet: Mapping[str, Any]) -> bool:
    gate = packet.get("gate") if isinstance(packet.get("gate"), Mapping) else {}
    return bool(gate.get("passed"))

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

__all__ = [name for name in globals() if not name.startswith("__")]
