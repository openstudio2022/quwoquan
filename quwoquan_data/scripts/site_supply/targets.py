"""Target resolution and entity mention mapping for site-supply."""
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
from site_supply import bridge

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
    known_targets = bridge.call(
        "_known_coverage_entity_targets",
        _known_coverage_entity_targets,
    )
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
        known_target = bridge.call(
            "_resolve_known_entity_target",
            _resolve_known_entity_target,
            name,
            expected_entity_type="",
        )
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

__all__ = [name for name in globals() if not name.startswith("__")]
