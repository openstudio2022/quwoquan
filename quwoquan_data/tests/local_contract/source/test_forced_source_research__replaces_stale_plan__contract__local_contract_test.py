from __future__ import annotations

import sys
from pathlib import Path


DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from content.source.research import auto_plan_public  # noqa: E402


def test_forced_source_research_invalidates_only_selected_lane(monkeypatch, tmp_path):
    object_dir = tmp_path / "entities" / "地点" / "景区" / "测试景区"
    download_dir = object_dir / "1.download"
    download_dir.mkdir(parents=True)
    homepage_plan = download_dir / "homepage_source_plan.json"
    article_plan = download_dir / "article_source_plan.json"
    homepage_plan.write_text('{"payload":{"sources":[{"stale":true}]}}', encoding="utf-8")
    article_plan.write_text('{"payload":{"sources":[{"keep":true}]}}', encoding="utf-8")
    monkeypatch.setattr(
        auto_plan_public,
        "resolve_research_entity_types",
        lambda *_args, **_kwargs: {"测试景区": "地点/景区"},
    )
    monkeypatch.setattr(
        auto_plan_public,
        "resolve_entity_object_dir",
        lambda *_args, **_kwargs: object_dir,
    )
    monkeypatch.setattr(
        auto_plan_public,
        "research_plan_files",
        lambda: {
            "homepage": "homepage_source_plan.json",
            "article": "article_source_plan.json",
            "image": "image_source_plan.json",
        },
    )

    auto_plan_public._invalidate_forced_lane_plans(
        "execution",
        ["测试景区"],
        entity_type="地点/景区",
        lanes={"homepage"},
    )

    assert not homepage_plan.exists()
    assert article_plan.is_file()
