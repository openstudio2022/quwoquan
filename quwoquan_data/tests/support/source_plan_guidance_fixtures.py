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

from core.io import read_json, write_json

from content.post.article.evidence_text import clean_source_markdown, score_source_markdown

from core.paths import execution_root

from core.source_catalog import source_category_coverage

from content.source.source_unit import resolve_entity_object_dir

from content.source.prepare import prepare_source_plan

from content.execution import store

from content.source.research.auto_plan_public import write_auto_research_plans  # noqa: E402
from content.source.research.auto_plan_report import (  # noqa: E402
    _source_availability_summary,
)
from content.source.research.plan_state import (  # noqa: E402
    _image_window,
    _safe_collection_id,
    _source,
)
from content.source.research.reject_memory import (  # noqa: E402
    _download_reject_memory,
    _source_reject_should_enter_memory,
)
from content.source.research.plan_reuse import _verified_homepage_sources_from_source_units  # noqa: E402
from content.source.research.source_quality import (  # noqa: E402
    _article_base_candidate_limit,
    _candidate_gate,
    _collection_gate,
    _collection_publishable_image_urls,
    _license_allows_app_publish,
    _select_article_plan_sources,
)
from content.source.research.homepage_source_policy import _homepage_can_seed_base_draft  # noqa: E402
from content.source.research.source_registry import (  # noqa: E402
    _known_article_sources,
    _known_entity_aliases,
    _known_official_website,
    _travel_registry_url_fetchable,
)
from content.source.research.text_match import (  # noqa: E402
    _expanded_entity_aliases,
    _title_matches_entity,
    _wiki_title_matches_entity,
)
from content.source.research.wiki_core import (  # noqa: E402
    _external_article_category,
    _external_platform,
    _url_looks_like_article,
    _wiki_related_titles,
    _wiki_title,
    _wiki_title_for_entity,
)
from content.source.research.wiki_media import _openverse_images  # noqa: E402
from content.source.research.qunar_sources import (  # noqa: E402
    _qunar_travelogue_sources,
)

__all__ = sorted(name for name in globals() if name != "__all__" and not name.startswith("__"))
