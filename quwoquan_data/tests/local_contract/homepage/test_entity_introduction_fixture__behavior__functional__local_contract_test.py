"""fixture entity-introduction 合约测试：publish 实体 → App introduction fixture。

与 entity-service homepage_introduction.go 的三段结构投影同构：
overview（导语）/ body（## 章节，含 :::figure asset:// 行）/
relatedImages（## 相关图片 :::gallery ids= 属性）。
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import json

import pytest

from core.io import write_json  # noqa: E402
from tests.support.entity_introduction_fixture import (  # noqa: E402
    canonical_slug,
    merge_into_scenarios,
    project_entity_introduction,
)

PAGE_MD = """---
title: 测试山
coverImage: asset://测试山_cover_雪峰全景_1_aabbccdd
---

# 测试山

测试山位于测试省，是三段结构投影的合约样本，导语必须成为概况章节与摘要来源。

## 历史沿革

早期开凿，持续演进。

:::figure id="fig_01" layout="fullWidth" caption="山门旧照"
asset://测试山_detail_山门_2_11223344
:::

## 相关图片

:::gallery ids="测试山_detail_远眺_3_55667788,测试山_detail_山门_2_11223344" layout="grid"
:::
"""


def seed_entity(root: Path, *, materialized: bool = True) -> Path:
    entity_dir = root / "地点" / "景区" / "测试山"
    entity_dir.mkdir(parents=True, exist_ok=True)
    write_json(entity_dir / "_entity.json", {
        "label": "测试山",
        "domain": "地点",
        "type": "景区",
        "summary": "测试山 header 摘要",
        "originTaskId": "旅行/测试/任务",
    })
    (entity_dir / "page.md").write_text(PAGE_MD, encoding="utf-8")
    assets = [
        {"assetId": "测试山_cover_雪峰全景_1_aabbccdd", "role": "cover", "caption": "雪峰全景",
         "sourceRef": "sources/测试山/source.md"},
        {"assetId": "测试山_detail_山门_2_11223344", "role": "detail", "caption": "山门旧照",
         "sourceRef": "sources/测试山/source.md"},
        {"assetId": "测试山_detail_远眺_3_55667788", "role": "related", "caption": "",
         "sourceRef": "sources/测试山/source.md"},
    ]
    if materialized:
        for i, asset in enumerate(assets):
            asset["objectKey"] = f"library/sha256/{i:02d}/obj_{i}.jpg"
            asset["cdnUrl"] = f"https://cdn.example.com/{asset['objectKey']}"
    write_json(entity_dir / "manifest.json", {"assets": assets})
    return entity_dir


def minimal_scenarios() -> dict:
    return {
        "schema": "contract-fixture",
        "seedSets": {
            "entity_homepage_core": {
                "description": "",
                "homepages": [
                    {
                        "homepageId": "homepage_sight_west_lake",
                        "type": "sight",
                        "title": "西湖景区",
                        "followerCount": 1286,
                        "introduction": {"coverUrl": "https://images.unsplash.com/photo-x"},
                    }
                ],
            }
        },
    }


def test_projection_three_segments_and_asset_binding(tmp_path: Path) -> None:
    seed_entity(tmp_path)
    entry, issues = project_entity_introduction(tmp_path / "地点/景区/测试山", "地点/景区/测试山")
    assert entry is not None and issues == []

    assert entry["homepageId"] == "homepage_sight_" + canonical_slug("测试山")
    assert entry["canonicalEntityId"] == "entity:sight:" + canonical_slug("测试山")
    assert entry["status"] == "published"
    # 封面来自 frontmatter coverImage 资产 URL，不允许 unsplash 占位。
    assert entry["coverUrl"].startswith("https://cdn.example.com/")
    assert "unsplash" not in json.dumps(entry, ensure_ascii=False)
    assert "三段结构投影的合约样本" in entry["summary"]

    intro = entry["introduction"]
    kinds = [s["kind"] for s in intro["sections"]]
    assert kinds == ["overview", "body", "relatedImages"]

    body = intro["sections"][1]
    assert body["title"] == "历史沿革"
    assert ':::figure id="fig_01"' in body["bodyMarkdown"]
    assert [a["assetId"] for a in body["assets"]] == ["测试山_detail_山门_2_11223344"]
    assert body["assets"][0]["role"] == "inline"

    related = intro["sections"][2]
    assert [a["assetId"] for a in related["assets"]] == [
        "测试山_detail_远眺_3_55667788",
        "测试山_detail_山门_2_11223344",
    ]
    assert all(a["role"] == "related" for a in related["assets"])
    assert "bodyMarkdown" not in related


def test_media_base_url_overrides_cdn(tmp_path: Path) -> None:
    seed_entity(tmp_path)
    entry, _ = project_entity_introduction(
        tmp_path / "地点/景区/测试山", "地点/景区/测试山",
        media_base_url="https://media.local/",
    )
    assert entry is not None
    assert entry["coverUrl"].startswith("https://media.local/library/")


def test_unmaterialized_assets_reported_as_issue(tmp_path: Path) -> None:
    seed_entity(tmp_path, materialized=False)
    entry, issues = project_entity_introduction(tmp_path / "地点/景区/测试山", "地点/景区/测试山")
    assert entry is not None
    assert len(issues) == 3 and all("materialize" in issue for issue in issues)
    # 无 URL 资产不得进入 sections，relatedImages 空则整节裁剪。
    assert [s["kind"] for s in entry["introduction"]["sections"]] == ["overview", "body"]
    assert entry["introduction"]["sections"][1]["assets"] == []


def test_unknown_entity_type_skipped(tmp_path: Path) -> None:
    entity_dir = tmp_path / "地点" / "未知类型" / "神秘对象"
    entity_dir.mkdir(parents=True)
    write_json(entity_dir / "_entity.json", {"label": "神秘对象", "domain": "地点", "type": "未知类型"})
    (entity_dir / "page.md").write_text("# 神秘对象\n\n正文。\n", encoding="utf-8")
    entry, issues = project_entity_introduction(entity_dir, "地点/未知类型/神秘对象")
    assert entry is None
    assert issues and "未登记主页类型映射" in issues[0]


def test_merge_upsert_is_idempotent_and_preserves_manual_fields(tmp_path: Path) -> None:
    seed_entity(tmp_path)
    entry, _ = project_entity_introduction(tmp_path / "地点/景区/测试山", "地点/景区/测试山")
    assert entry is not None

    scenarios = minimal_scenarios()
    merge_into_scenarios(scenarios, [entry])
    homepages = scenarios["seedSets"]["entity_homepage_core"]["homepages"]
    assert len(homepages) == 2  # 西湖 + 测试山

    # 幂等重跑不重复新增。
    merge_into_scenarios(scenarios, [entry])
    assert len(scenarios["seedSets"]["entity_homepage_core"]["homepages"]) == 2

    # 已有条目（西湖）被同 id 生成条目更新时保留手工运营字段。
    west_lake_regen = dict(entry)
    west_lake_regen = json.loads(json.dumps(west_lake_regen))
    west_lake_regen["homepageId"] = "homepage_sight_west_lake"
    merge_into_scenarios(scenarios, [west_lake_regen])
    updated = next(
        h for h in scenarios["seedSets"]["entity_homepage_core"]["homepages"]
        if h["homepageId"] == "homepage_sight_west_lake"
    )
    assert updated["followerCount"] == 1286
    assert "unsplash" not in json.dumps(updated["introduction"], ensure_ascii=False)


def test_canonical_slug_matches_service_side_semantics() -> None:
    # 与 homepage_lookup.go canonicalSlug 同构：中文保留、空白/横线转下划线、去首尾。
    assert canonical_slug("测试山") == "测试山"
    assert canonical_slug("West Lake") == "west_lake"
    assert canonical_slug("  A-B/C  ") == "a_b_c"
    assert canonical_slug("！！") == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
