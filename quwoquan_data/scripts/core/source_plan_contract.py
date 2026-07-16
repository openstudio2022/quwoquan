"""Source-plan contract signatures for scoped stale detection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

SOURCE_PLAN_RULE_SIGNATURE_VERSION = "quwoquan.source_plan_rules.v4"

_DATA_ROOT = Path(__file__).resolve().parents[2]
_ENTITY_SCOPED_REGISTRY_KEYS = {
    "knownOfficialSites",
    "knownEntityAliases",
    "knownArticleSources",
}
_GLOBAL_RULE_RELATIVE_PATHS = (
    "scripts/content/source/prepare.py",
    "scripts/content/source/source_inputs.py",
    "scripts/content/source/research/auto_plan_writer.py",
    "scripts/content/source/research/source_quality.py",
    "scripts/content/source/research/network_io.py",
    "scripts/content/source/research/wiki_core.py",
    "scripts/content/source/research/wiki_media.py",
    "scripts/core/source_catalog.py",
    "control_plane/_shared/catalogs/source_catalog.yaml",
    "control_plane/_shared/catalogs/content_source_registry.yaml",
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_name(value: str) -> str:
    return "".join(str(value or "").strip().split()).casefold()


def _entity_row_matches(row: Mapping[str, Any], entity_id: str) -> bool:
    target = _normalized_name(entity_id)
    if not target:
        return False
    entity = _normalized_name(str(row.get("entity") or ""))
    aliases = {_normalized_name(str(item)) for item in (row.get("aliases") or [])}
    return target == entity or target in aliases


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _travel_registry_parts(vertical: str, entity_id: str) -> dict[str, Any]:
    if vertical != "travel":
        return {}
    path = _DATA_ROOT / "verticals" / "travel" / "sources" / "source_registry.yaml"
    data = _load_yaml(path)
    if not data:
        return {"path": str(path.relative_to(_DATA_ROOT)), "global": {}, "entityScoped": {}}
    global_part = {
        key: value
        for key, value in data.items()
        if key not in _ENTITY_SCOPED_REGISTRY_KEYS
    }
    entity_part: dict[str, list[Any]] = {}
    for key in sorted(_ENTITY_SCOPED_REGISTRY_KEYS):
        rows = data.get(key) or []
        if not isinstance(rows, list):
            continue
        matched = [
            row for row in rows
            if isinstance(row, Mapping) and _entity_row_matches(row, entity_id)
        ]
        if matched:
            entity_part[key] = matched
    return {
        "path": str(path.relative_to(_DATA_ROOT)),
        "global": global_part,
        "entityScoped": entity_part,
    }


def source_plan_rule_signature(vertical: str, entity_id: str) -> dict[str, Any]:
    """Return a stable signature for the rules that affect one entity content.execution.planning.

    Global executable/catalog changes intentionally affect every entity. The
    travel source registry is split: site/extractor policy is global, while
    known official/article rows are scoped by entity；homepage authority 只由
    content_source_registry 的四百科 policy 控制。
    """
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
        "version": SOURCE_PLAN_RULE_SIGNATURE_VERSION,
        "vertical": vertical,
        "entityId": entity_id,
        "globalFiles": global_files,
        "travelSourceRegistry": _travel_registry_parts(vertical, entity_id),
    }
    digest = hashlib.sha256(_stable_json(parts).encode("utf-8")).hexdigest()
    return {
        "version": SOURCE_PLAN_RULE_SIGNATURE_VERSION,
        "vertical": vertical,
        "entityId": entity_id,
        "hash": digest,
    }
