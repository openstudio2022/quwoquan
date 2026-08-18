"""Shared imports and fixtures for source-plan guidance tests."""



from __future__ import annotations

import sys

import urllib.parse

from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")

TESTS_ROOT = DATA_ROOT / "tests"

SCRIPTS_ROOT = DATA_ROOT / "scripts"

for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from _common.io import read_json, write_json

from _common.content_evidence import clean_source_markdown, score_source_markdown

from _common.paths import batch_root

from _common.source_catalog import source_category_coverage

from _common.source_unit import resolve_entity_object_dir

from download.prepare import prepare_source_plan

from content import store

from download.research.auto_plan_public import write_auto_research_plans  # noqa: E402
from download.research.auto_plan_report import (  # noqa: E402
    _source_availability_summary,
)
from download.research.plan_state import (  # noqa: E402
    _download_reject_memory,
    _image_window,
    _safe_collection_id,
    _source,
    _source_reject_should_enter_memory,
    _verified_homepage_sources_from_source_units,
)
from download.research.source_quality import (  # noqa: E402
    _article_base_candidate_limit,
    _candidate_gate,
    _collection_gate,
    _collection_publishable_image_urls,
    _homepage_can_seed_base_draft,
    _known_article_sources,
    _known_entity_aliases,
    _known_official_website,
    _license_allows_app_publish,
    _select_article_plan_sources,
    _travel_registry_url_fetchable,
)
from download.research.text_match import (  # noqa: E402
    _expanded_entity_aliases,
    _title_matches_entity,
    _wiki_title_matches_entity,
)
from download.research.wiki_core import (  # noqa: E402
    _external_article_category,
    _external_platform,
    _url_looks_like_article,
    _wiki_related_titles,
    _wiki_title,
    _wiki_title_for_entity,
)
from download.research.wiki_media import (  # noqa: E402
    _openverse_images,
    _qunar_travelogue_sources,
)

__all__ = sorted(name for name in globals() if name != "__all__" and not name.startswith("__"))
