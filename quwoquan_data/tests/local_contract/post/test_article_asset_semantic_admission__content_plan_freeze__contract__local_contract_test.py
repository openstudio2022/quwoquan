"""Article asset refs are semantically admitted before source-unit freeze."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

DATA_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.execution.controller import content_plan_assets
from content.execution.controller.content_plan_asset_semantics import (
    article_asset_semantic_issue,
)
from governance.entity_reference import entity_aliases


def _row(file_name: str, caption: str, relevance: str) -> dict[str, object]:
    return {
        "fileName": file_name,
        "sourceAssetId": file_name.removesuffix(".jpg"),
        "sha256": file_name.removesuffix(".jpg").ljust(64, "0"),
        "caption": caption,
        "relevance": relevance,
        "visualSubject": caption,
        "isRepresentativeVisual": True,
    }


def test_content_plan_excludes_off_entity_closing_before_freeze(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "sources/article_frontier"
    assets_dir = source_dir / "assets"
    assets_dir.mkdir(parents=True)
    rows = [
        _row(
            "001_lake.jpg",
            "西湖湖面与苏堤远景",
            "画面直接呈现杭州西湖水域与苏堤",
        ),
        _row(
            "002_bridge.jpg",
            "西湖断桥与湖岸",
            "画面直接呈现杭州西湖断桥景观",
        ),
        _row(
            "003_city.jpg",
            "塔楼与城市天际线",
            "杭州大厦及奢侈品街景",
        ),
    ]
    for row in rows:
        (assets_dir / str(row["fileName"])).write_bytes(b"image")
    monkeypatch.setattr(
        content_plan_assets,
        "relative_execution_ref",
        lambda path, _execution_id: Path(path).relative_to(tmp_path).as_posix(),
    )
    monkeypatch.setattr(
        content_plan_assets,
        "_assess_content_plan_publish_image",
        lambda *_args: SimpleNamespace(blocks_image_publish=False),
    )
    monkeypatch.setattr(
        content_plan_assets,
        "_canonical_article_asset_issue",
        lambda *_args: "",
    )

    refs, _shas, _collections, asset_refs = content_plan_assets.article_asset_claims(
        SimpleNamespace(execution_id="article-semantic-admission"),
        tmp_path,
        {
            "sourceDir": source_dir,
            "rows": rows,
            "targetEntity": "杭州西湖",
            "targetAliases": ["西湖", "西湖风景名胜区"],
        },
    )

    assert refs == [
        "sources/article_frontier/assets/001_lake.jpg",
        "sources/article_frontier/assets/002_bridge.jpg",
    ]
    assert asset_refs == refs
    assert not any("003_city" in ref for ref in refs)


def test_non_representative_source_asset_is_rejected_even_when_name_matches() -> None:
    issue = article_asset_semantic_issue(
        {
            "fileName": "map.jpg",
            "caption": "杭州西湖位置图",
            "relevance": "杭州西湖行政区定位",
            "isRepresentativeVisual": False,
        },
        entity_id="杭州西湖",
        entity_aliases=("西湖",),
    )

    assert "non-representative" in issue


def test_specific_landmark_in_frozen_source_body_is_admitted_but_city_asset_is_not() -> None:
    article_text = "沿西湖步行可见雷峰塔与西泠印社，二者都与湖岸叙事直接相关。"

    assert article_asset_semantic_issue(
        _row("leifeng.jpg", "Leifeng Pagoda 雷峰塔", "雷峰塔实景"),
        entity_id="杭州西湖",
        entity_aliases=("西湖",),
        article_text=article_text,
    ) == ""
    issue = article_asset_semantic_issue(
        _row("tower.jpg", "201607 Hangzhou Tower", "杭州大厦及奢侈品街景"),
        entity_id="杭州西湖",
        entity_aliases=("西湖",),
        article_text=article_text,
    )
    assert "frozen source body" in issue


def test_provider_subject_alias_and_decoded_commons_url_bind_west_lake_scenes() -> None:
    article_text = """# 杭州

### 杭州西湖文化景观
西湖十景包括三潭印月、三潭映月和断桥残雪。

### 购物
杭州大厦位于武林广场。
"""
    three_pools = _row(
        "three-pools.jpg",
        "File:Three Pools Mirroring the Moon-pool.JPG",
        "File:Three Pools Mirroring the Moon-pool.JPG",
    )
    three_pools["visualSubjectEvidence"] = [
        {
            "value": "三潭映月",
            "language": "zh",
            "commonsCategory": "Three Pools Mirroring the Moon",
            "wikidataItem": "Q10866444",
        }
    ]
    broken_bridge = _row(
        "broken-bridge.jpg",
        "Duanqiao Can Xue",
        "Duanqiao Can Xue",
    )
    broken_bridge["sourceUrl"] = (
        "https://commons.wikimedia.org/wiki/"
        "File:%E6%96%AD%E6%A1%A5%E6%AE%8B%E9%9B%AA%E5%9B%BD%E4%BF%9D%E7%A2%91.JPG"
    )

    assert article_asset_semantic_issue(
        three_pools,
        entity_id="杭州西湖",
        entity_aliases=("西湖",),
        article_text=article_text,
    ) == ""
    assert article_asset_semantic_issue(
        broken_bridge,
        entity_id="杭州西湖",
        entity_aliases=("西湖",),
        article_text=article_text,
    ) == ""


def test_target_section_does_not_admit_subject_mentioned_only_in_other_section() -> None:
    row = _row("tower.jpg", "Hangzhou Tower", "Hangzhou Tower")
    row["visualSubjectEvidence"] = [
        {
            "value": "杭州大厦",
            "language": "zh",
            "commonsCategory": "Hangzhou Tower",
            "wikidataItem": "Q11102459",
        }
    ]

    issue = article_asset_semantic_issue(
        row,
        entity_id="杭州西湖",
        entity_aliases=("西湖",),
        article_text=(
            "### 杭州西湖文化景观\n断桥残雪与三潭印月。\n\n"
            "### 购物\n杭州大厦位于武林广场。"
        ),
    )

    assert "frozen source body" in issue


def test_canonical_duplicates_are_removed_before_article_refs_freeze(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "sources/article_frontier"
    assets_dir = source_dir / "assets"
    assets_dir.mkdir(parents=True)
    rows = [
        _row("001_old.jpg", "杭州西湖旧图", "杭州西湖"),
        _row("002_new.jpg", "杭州西湖新图一", "杭州西湖"),
        _row("003_new.jpg", "杭州西湖新图二", "杭州西湖"),
    ]
    for row in rows:
        (assets_dir / str(row["fileName"])).write_bytes(b"image")
    monkeypatch.setattr(
        content_plan_assets,
        "relative_execution_ref",
        lambda path, _execution_id: Path(path).relative_to(tmp_path).as_posix(),
    )
    monkeypatch.setattr(
        content_plan_assets,
        "_assess_content_plan_publish_image",
        lambda *_args: SimpleNamespace(blocks_image_publish=False),
    )
    monkeypatch.setattr(
        content_plan_assets,
        "_canonical_article_asset_issue",
        lambda _source_dir, row: (
            "canonical image identity duplicated" if row["fileName"] == "001_old.jpg" else ""
        ),
    )

    refs, _shas, _collections, asset_refs = content_plan_assets.article_asset_claims(
        SimpleNamespace(execution_id="article-canonical-admission"),
        tmp_path,
        {
            "sourceDir": source_dir,
            "rows": rows,
            "targetEntity": "杭州西湖",
            "targetAliases": ["西湖"],
        },
    )

    assert refs == [
        "sources/article_frontier/assets/002_new.jpg",
        "sources/article_frontier/assets/003_new.jpg",
    ]
    assert asset_refs == refs


def test_canonical_entity_name_resolves_local_name_and_stable_aliases() -> None:
    aliases = entity_aliases("杭州西湖")

    assert "西湖" in aliases
    assert "西湖风景名胜区" in aliases
    assert "West Lake Hangzhou" in aliases
