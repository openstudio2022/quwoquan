"""Load versioned templates and control-plane inputs.

Runtime work packages never provide templates, catalogs, or creator profiles.
Tests may opt into explicit fixture roots, but production reads repository-owned
sources so every execution can attest the exact static inputs it consumed.
"""
from __future__ import annotations

import os
import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.paths import (
    _REPO_DATA_ROOT,
    CONTROL_PLANE_TAXONOMY_ROOT,
)


def _resolve_templates_root() -> Path:
    """Resolve the versioned template source, never a runtime output root."""
    override = os.environ.get("QWQ_TEMPLATES_ROOT")
    if override:
        return Path(override)
    return _REPO_DATA_ROOT / "templates"


TEMPLATES_ROOT = _resolve_templates_root()
CONTROL_PLANE_ROOT = Path(
    os.environ.get("QWQ_CONTROL_PLANE_ROOT", _REPO_DATA_ROOT / "control_plane")
)
CATALOGS_ROOT = CONTROL_PLANE_ROOT / "_shared" / "catalogs"
ROUTING_ROOT = CONTROL_PLANE_ROOT / "_shared" / "routing"
# Blueprint files are split by carrier under templates/{article,image,...}.
BLUEPRINTS_ROOT = TEMPLATES_ROOT
CREATORS_ROOT = CONTROL_PLANE_ROOT / "governance" / "creator_pool" / "profiles" / "system_builtin"
ARTICLE_TEMPLATE_RECOMMENDATIONS_PATH = (
    CATALOGS_ROOT / "article_template_recommendations.yaml"
)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def iter_yaml_files(root: Path, suffix: str) -> list[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob(f"*{suffix}") if p.is_file())


def active_tags_root() -> Path:
    """Return the versioned taxonomy contract, never a publish projection."""
    override = os.environ.get("QWQ_TAGS_ROOT")
    if override:
        return Path(override)
    return CONTROL_PLANE_TAXONOMY_ROOT


def tag_exists(tag_ref: str) -> bool:
    root = active_tags_root()
    tag_dir = root / tag_ref
    return tag_dir.is_dir() or (tag_dir / "_definition.json").is_file()


def load_template_recommendations() -> dict[str, list[str]]:
    data = load_yaml(ARTICLE_TEMPLATE_RECOMMENDATIONS_PATH)
    out: dict[str, list[str]] = {}
    for item in data.get("article_template_recommendations", []):
        category = item.get("category_id")
        templates = item.get("recommended_article_templates", [])
        if isinstance(category, str) and isinstance(templates, list):
            out[category] = [str(t) for t in templates]
    return out


@dataclass(frozen=True)
class TemplateRegistry:
    catalogs: dict[str, dict[str, Any]]
    routes: dict[str, dict[str, Any]]
    blueprints: dict[str, dict[str, Any]]
    blueprint_paths: dict[str, Path]
    creators: dict[str, dict[str, Any]]
    creator_paths: dict[str, Path]
    article_recommendations: dict[str, list[str]]

    @classmethod
    @functools.lru_cache(maxsize=1)
    def load(cls) -> "TemplateRegistry":
        catalogs = {
            path.stem: load_yaml(path)
            for path in iter_yaml_files(CATALOGS_ROOT, ".yaml")
        }
        routes = {
            path.stem.replace(".routing", ""): load_yaml(path)
            for path in iter_yaml_files(ROUTING_ROOT, ".routing.yaml")
        }
        blueprints: dict[str, dict[str, Any]] = {}
        blueprint_paths: dict[str, Path] = {}
        for path in iter_yaml_files(BLUEPRINTS_ROOT, ".tmpl.yaml"):
            data = load_yaml(path)
            _apply_style_defaults(data, catalogs)
            template_id = str(data.get("templateId", ""))
            if template_id:
                blueprints[template_id] = data
                blueprint_paths[template_id] = path

        creators: dict[str, dict[str, Any]] = {}
        creator_paths: dict[str, Path] = {}
        for path in iter_yaml_files(CREATORS_ROOT, ".creator.yaml"):
            data = load_yaml(path)
            creator_id = str(data.get("creatorProfileId", ""))
            if creator_id:
                creators[creator_id] = data
                creator_paths[creator_id] = path

        return cls(
            catalogs=catalogs,
            routes=routes,
            blueprints=blueprints,
            blueprint_paths=blueprint_paths,
            creators=creators,
            creator_paths=creator_paths,
            article_recommendations=load_template_recommendations(),
        )

    @classmethod
    def clear_cache(cls) -> None:
        cls.load.__func__.cache_clear()

    def creators_by_archetype(self, archetype: str) -> list[dict[str, Any]]:
        return [c for c in self.creators.values() if c.get("creatorArchetype") == archetype]


def _apply_style_defaults(blueprint: dict[str, Any], catalogs: dict[str, dict[str, Any]]) -> None:
    style_family = blueprint.get("styleFamily")
    families = catalogs.get("style_profile_catalog", {}).get("styleFamilies", {})
    if not style_family or style_family not in families:
        return
    family = families[style_family]
    if "styleProfile" not in blueprint and isinstance(family.get("styleProfile"), dict):
        blueprint["styleProfile"] = family["styleProfile"]
    if "render" not in blueprint and isinstance(family.get("render"), dict):
        blueprint["render"] = family["render"]
