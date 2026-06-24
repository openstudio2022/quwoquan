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

os.environ["QWQ_COMMITTED_TASKS_ROOT"] = str(Path(_TMP) / "tasks")

from _common.io import read_json, write_json

from _common.content_evidence import clean_source_markdown, score_source_markdown

from _common.paths import batch_root

from _common.source_catalog import source_category_coverage

from _common.source_unit import resolve_entity_object_dir

from download.prepare import prepare_source_plan

from task import store

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
