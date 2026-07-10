"""Load the quwoquan_data template library."""
from __future__ import annotations

import os
import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from _common.paths import _REPO_DATA_ROOT, DATA_ROOT, PUBLISH_ROOT, SERVICE_CONTRACTS_METADATA_ROOT


def _resolve_templates_root() -> Path:
    """系统内置模板库（creator_profiles/blueprints/routing/catalogs）是版本控制的契约
    真相源，应跟代码走，禁止随运行时 QWQ_DATA_ROOT 漂移到无模板的隔离/scratch 根。

    解析顺序：显式 QWQ_TEMPLATES_ROOT > 运行时数据根自带 templates（测试 fixture 场景）
    > 仓库内置 templates。回退保证 scratch 数据根下 creator 注册表不为空。
    """
    override = os.environ.get("QWQ_TEMPLATES_ROOT")
    if override:
        return Path(override)
    data_root_templates = DATA_ROOT / "templates"
    if (data_root_templates / "creator_profiles" / "system_builtin").is_dir():
        return data_root_templates
    return _REPO_DATA_ROOT / "templates"


TEMPLATES_ROOT = _resolve_templates_root()
CATALOGS_ROOT = TEMPLATES_ROOT / "_registry" / "catalogs"
ROUTING_ROOT = TEMPLATES_ROOT / "_registry" / "routing"
BLUEPRINTS_ROOT = TEMPLATES_ROOT / "blueprints"
CREATORS_ROOT = TEMPLATES_ROOT / "creator_profiles" / "system_builtin"
# ui_config 是服务侧受版本控制的契约真相源，跟代码走，禁止随 QWQ_DATA_ROOT 漂移。
UI_CONFIG_PATH = SERVICE_CONTRACTS_METADATA_ROOT / "content" / "post" / "ui_config.yaml"


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
    override = os.environ.get("QWQ_TAGS_ROOT")
    if override:
        return Path(override)
    publish_tags = PUBLISH_ROOT / "tags"
    if publish_tags.is_dir():
        return publish_tags
    return _REPO_DATA_ROOT / "publish" / "tags"


def tag_exists(tag_ref: str) -> bool:
    root = active_tags_root()
    tag_dir = root / tag_ref
    return tag_dir.is_dir() or (tag_dir / "_definition.json").is_file()


def load_template_recommendations() -> dict[str, list[str]]:
    data = load_yaml(UI_CONFIG_PATH)
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

        from _common.creator_pool.registry_bridge import load_travel_batch_creators

        batch_creators, batch_paths = load_travel_batch_creators()
        creators.update(batch_creators)
        creator_paths.update(batch_paths)

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
