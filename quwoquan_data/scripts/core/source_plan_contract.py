"""Source-plan contract signatures for scoped stale detection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

_DATA_ROOT = Path(__file__).resolve().parents[2]
_GLOBAL_RULE_RELATIVE_PATHS = (
    "scripts/core/source_plan_contract.py",
    "scripts/content/source/research/article_crawl_frontier.py",
    "scripts/content/source/research/article_frontier_contract.py",
    "scripts/content/source/research/article_frontier_profile.py",
    "scripts/content/source/research/article_frontier_robots.py",
    "scripts/content/source/research/article_site_crawl.py",
    "scripts/content/source/research/public_search.py",
    "scripts/content/source/research/qunar_sources.py",
    "scripts/content/source/research/source_registry.py",
    "scripts/content/source/research/network_io.py",
    "scripts/content/source/research/wiki_core.py",
    "scripts/content/source/research/wiki_media.py",
    "scripts/core/source_catalog.py",
    "control_plane/_shared/catalogs/source_catalog.yaml",
    "control_plane/_shared/catalogs/content_source_registry.yaml",
    "schema/execution/article_source_discovery_evidence.schema.json",
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _travel_registry_parts(vertical: str, entity_id: str) -> dict[str, Any]:
    if vertical != "travel":
        return {}
    del entity_id
    path = _DATA_ROOT / "verticals" / "travel" / "providers.yaml"
    data = _load_yaml(path)
    if not data:
        return {"path": str(path.relative_to(_DATA_ROOT)), "providers": {}}
    return {"path": str(path.relative_to(_DATA_ROOT)), "providers": data}


def source_plan_rule_signature(vertical: str, entity_id: str) -> dict[str, Any]:
    """Return a stable signature for mechanical source acquisition rules."""
    vertical = str(vertical or "travel").strip() or "travel"
    entity_id = str(entity_id or "").strip()
    global_files = {
        rel: _file_sha256(_DATA_ROOT / rel)
        for rel in _GLOBAL_RULE_RELATIVE_PATHS
    }
    rights_path = _DATA_ROOT / "verticals" / vertical / "rights" / "license_policy.yaml"
    if rights_path.is_file():
        global_files[str(rights_path.relative_to(_DATA_ROOT))] = _file_sha256(rights_path)
    parts = {
        "vertical": vertical,
        "entityId": entity_id,
        "globalFiles": global_files,
        "travelSourceRegistry": _travel_registry_parts(vertical, entity_id),
    }
    digest = hashlib.sha256(_stable_json(parts).encode("utf-8")).hexdigest()
    return {
        "vertical": vertical,
        "entityId": entity_id,
        "digest": f"sha256:{digest}",
    }
