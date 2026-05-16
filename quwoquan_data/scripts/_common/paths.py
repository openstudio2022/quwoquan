"""路径真相源 — 统一目录结构

核心原则：
- entities/tags/posts 在 runtime/tasks 和 publish/v{N} 下同构
- 所有 ID 从目录路径推导，JSON 中不重复存储
- entities 三层目录：entities/{领域}/{类型}/{名称}/（如 entities/地点/景区/峨眉山/）
- tags 全目录化，每个标签 = 目录 + _definition.json
- posts 按内容角度标签分类，标题命名目录，编号子目录
- sop 目录与实体类型对齐：sop/主页/{领域}/{类型}/
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DATA_ROOT = Path(os.environ.get("QWQ_DATA_ROOT", Path(__file__).resolve().parents[2]))
RUNTIME_ROOT = Path(os.environ.get("QWQ_RUNTIME_ROOT", DATA_ROOT / "runtime"))
PUBLISH_ROOT = Path(os.environ.get("QWQ_PUBLISH_ROOT", DATA_ROOT / "publish"))
RELEASE_ROOT = Path(os.environ.get("QWQ_RELEASE_ROOT", DATA_ROOT / "release"))
SCHEMA_ROOT = DATA_ROOT / "schema"
SOP_ROOT = DATA_ROOT / "sop"

TASKS_ROOT = RUNTIME_ROOT / "tasks"
COMMANDS = ("explore", "build", "download", "produce", "reconcile", "publish")
NOW_ISO = "2026-05-15T00:00:00+08:00"


# ─── publish 版本化 ───────────────────────────────────────────────
def publish_meta_path() -> Path:
    return PUBLISH_ROOT / "publish_meta.json"


def publish_active_version() -> int:
    meta = publish_meta_path()
    if meta.exists():
        return json.loads(meta.read_text(encoding="utf-8")).get("activeVersion", 0)
    return 0


def publish_version_root(version: int) -> Path:
    return PUBLISH_ROOT / f"v{version}"


# ─── 同构路径（runtime task 与 publish 共用）─────────────────────
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

    # sop: sop/主页/{domain}/{type}/ -> guide.md, template.md, example.md
    def sop_dir(self, domain: str, etype: str) -> Path:
        return SOP_ROOT / "主页" / domain / etype

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


# ─── task 级路径 ──────────────────────────────────────────────────
def task_root(task_id: str) -> Path:
    return TASKS_ROOT / task_id


def task_data(task_id: str) -> DataRoot:
    return DataRoot(task_root(task_id))


def task_manifest(task_id: str) -> Path:
    return task_root(task_id) / "task_manifest.json"


def task_catalog(task_id: str) -> Path:
    return task_root(task_id) / "catalog.ndjson"


def task_changeset_dir(task_id: str) -> Path:
    return task_root(task_id) / "changeset"


# ─── publish 同构 ─────────────────────────────────────────────────
def publish_data(version: int) -> DataRoot:
    return DataRoot(publish_version_root(version))


# ─── release 输出（供服务端 bulk import 消费）─────────────────────
def release_root(release_id: str) -> Path:
    return RELEASE_ROOT / release_id


def release_manifest(release_id: str) -> Path:
    return release_root(release_id) / "release_manifest.json"


# ─── task 产物快捷路径（assemble 消费）────────────────────────────
def task_entities(task_id: str) -> Path:
    return task_root(task_id) / "entities.ndjson"


def task_tags(task_id: str) -> Path:
    return task_root(task_id) / "tags.ndjson"


def task_entity_pages(task_id: str) -> Path:
    return task_root(task_id) / "entity_pages"


def task_graph(task_id: str) -> Path:
    return task_root(task_id) / "graph"


def task_posts(task_id: str) -> Path:
    return task_root(task_id) / "posts"


# ─── batch 级路径 ─────────────────────────────────────────────────
def batch_root(task_id: str, batch_id: str) -> Path:
    return task_root(task_id) / "batches" / batch_id


def batch_command_root(task_id: str, batch_id: str, command: str) -> Path:
    return batch_root(task_id, batch_id) / command


def batch_inputs_dir(task_id: str, batch_id: str, command: str, step: str) -> Path:
    return batch_command_root(task_id, batch_id, command) / "inputs" / step


def batch_results_dir(task_id: str, batch_id: str, command: str, step: str) -> Path:
    return batch_command_root(task_id, batch_id, command) / "results" / step


def batch_assistant_task(task_id: str, batch_id: str, command: str, step: str) -> Path:
    return batch_command_root(task_id, batch_id, command) / "assistant_tasks" / f"{step}.json"


def batch_sources_dir(task_id: str, batch_id: str, entity_name: str) -> Path:
    return batch_command_root(task_id, batch_id, "download") / "sources" / entity_name


# ─── layout helpers ───────────────────────────────────────────────
def ensure_task_layout(task_id: str) -> Path:
    root = task_root(task_id)
    root.mkdir(parents=True, exist_ok=True)
    d = task_data(task_id)
    d.entities_dir().mkdir(exist_ok=True)
    d.tags_dir().mkdir(exist_ok=True)
    d.posts_dir().mkdir(exist_ok=True)
    task_changeset_dir(task_id).mkdir(exist_ok=True)
    return root


def ensure_batch_layout(task_id: str, batch_id: str, command: str) -> Path:
    cmd_root = batch_command_root(task_id, batch_id, command)
    (cmd_root / "inputs").mkdir(parents=True, exist_ok=True)
    (cmd_root / "results").mkdir(parents=True, exist_ok=True)
    (cmd_root / "assistant_tasks").mkdir(parents=True, exist_ok=True)
    return cmd_root
