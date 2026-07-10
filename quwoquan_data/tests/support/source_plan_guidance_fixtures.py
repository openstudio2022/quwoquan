"""Shared imports and fixtures for source-plan guidance tests."""



from __future__ import annotations

import sys

import tempfile

import urllib.parse

import shutil

from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")

TESTS_ROOT = DATA_ROOT / "tests"

SCRIPTS_ROOT = DATA_ROOT / "scripts"

for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os

_TMP = tempfile.mkdtemp(prefix="source_plan_guidance_")

os.environ["QWQ_RUNTIME_ROOT"] = _TMP

# committed 根与 runtime snapshot 根（RUNTIME_ROOT/tasks）必须物理隔离，
# 与生产契约同构（COMMITTED_TASKS_ROOT != TASKS_ROOT）。
os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(Path(_TMP) / "committed_tasks")

from _common.io import read_json, write_json

from _common.content_evidence import clean_source_markdown, score_source_markdown

from _common.paths import batch_root

from _common.source_catalog import source_category_coverage

from _common.source_unit import resolve_entity_object_dir

from download.prepare import prepare_source_plan

from task import store

# 抗导入顺序泄漏：本套件在导入期设了进程级临时 QWQ_RUNTIME_ROOT/QWQ_COMMITTED_TASKS_ROOT，
# 但 `_common.paths` 的根是导入期冻结的模块常量；若同一 pytest 进程里其它测试文件先导入了
# `_common.paths`（env 尚未指向临时目录），COMMITTED_TASKS_ROOT 会冻结成真实仓库 tasks/，
# 导致本套件 `store.save_spec` 把夹具规格写进真实 `quwoquan_data/control_plane/tasks/`（随后 task lint 失败、
# 工作树被污染）。这里在导入后把已冻结的常量重钉到本套件临时根，强制隔离，不受导入顺序影响。
import _common.paths as _paths_mod  # noqa: E402

_RUNTIME_TMP = Path(_TMP)
_COMMITTED_TMP = Path(_TMP) / "committed_tasks"
_paths_mod.RUNTIME_ROOT = _RUNTIME_TMP
_paths_mod.TASKS_ROOT = _RUNTIME_TMP / "tasks"
_paths_mod.COMMITTED_TASKS_ROOT = _COMMITTED_TMP
_paths_mod.PUBLISH_ROOT = _RUNTIME_TMP / "publish"
_paths_mod.RELEASE_ROOT = _RUNTIME_TMP / "release"
# task.store 通过 `from _common.paths import COMMITTED_TASKS_ROOT` 绑定了自身副本（defaults_chain 用），
# 同步重钉，确保读默认链也指向临时根。
store.COMMITTED_TASKS_ROOT = _COMMITTED_TMP

from download.research_plan import (  # noqa: E402
    _article_base_candidate_limit,
    _candidate_gate,
    _collection_gate,
    _collection_publishable_image_urls,
    _download_reject_memory,
    _expanded_entity_aliases,
    _external_article_category,
    _external_platform,
    _homepage_can_seed_base_draft,
    _image_window,
    _known_article_sources,
    _known_entity_aliases,
    _known_homepage_support_websites,
    _known_official_website,
    _license_allows_app_publish,
    _openverse_images,
    _qunar_travelogue_sources,
    _safe_collection_id,
    _select_article_plan_sources,
    _source,
    _source_availability_summary,
    _source_reject_should_enter_memory,
    _title_matches_entity,
    _url_looks_like_article,
    _travel_registry_url_fetchable,
    _verified_homepage_sources_from_source_units,
    _wiki_related_titles,
    _wiki_title,
    _wiki_title_for_entity,
    _wiki_title_matches_entity,
    write_auto_research_plans,
)

import download.research_plan as research_plan_mod



__all__ = sorted(name for name in globals() if name != "__all__" and not name.startswith("__"))
