"""Canonical object-path helper for Data work packages and publish roots."""
from __future__ import annotations

from pathlib import Path

class DataRoot:
    """runtime task 或 publish version 下的统一数据根。"""

    def __init__(self, root: Path):
        self.root = root

    # entities: entities/{domain}/{type}/{name}/
    def entities_dir(self) -> Path:
        return self.root / "entities"

    def entity_dir(self, domain: str, etype: str, name: str) -> Path:
        return self.entities_dir() / domain / etype / name

    def entity_json(self, domain: str, etype: str, name: str) -> Path:
        return self.entity_dir(domain, etype, name) / "_entity.json"

    def entity_page(self, domain: str, etype: str, name: str) -> Path:
        return self.entity_dir(domain, etype, name) / "page.md"

    def entity_manifest(self, domain: str, etype: str, name: str) -> Path:
        return self.entity_dir(domain, etype, name) / "manifest.json"

    # tags: tags/{dim}/{...path}/_definition.json
    def tags_dir(self) -> Path:
        return self.root / "tags"

    def taxonomy(self) -> Path:
        return self.tags_dir() / "_taxonomy.json"

    def tag_dir(self, tag_path: str) -> Path:
        return self.tags_dir() / tag_path

    def tag_file(self, tag_path: str) -> Path:
        return self.tag_dir(tag_path) / "_definition.json"

    def tag_dimension_dir(self, dim: str) -> Path:
        return self.tags_dir() / dim

    # posts: posts/{content_type}/{angle_tag}/{title}/{seq}/
    def posts_dir(self) -> Path:
        return self.root / "posts"

    def post_type_dir(self, content_type: str) -> Path:
        return self.posts_dir() / content_type

    def post_dir(self, content_type: str, angle_tag: str, title: str, seq: int = 1) -> Path:
        return self.post_type_dir(content_type) / angle_tag / title / str(seq)

    def post_article(self, content_type: str, angle_tag: str, title: str, seq: int = 1) -> Path:
        return self.post_dir(content_type, angle_tag, title, seq) / "article.md"

    def post_manifest(self, content_type: str, angle_tag: str, title: str, seq: int = 1) -> Path:
        return self.post_dir(content_type, angle_tag, title, seq) / "manifest.json"
