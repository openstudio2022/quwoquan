# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-036.t1
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-036.t2
# spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-036.t3
"""homepage 实体头在 publish 截面按 publish/entity schema fail closed。

此前 `entity.schema.json` 在生产链上零消费者：一个缺 `geoTagRef`、主来源不在百科闭集的实体
能一路走到 canonical，再在 Alpha ship 的 `homepage_import` 才被下游导入器拒绝，整级 release
连带 5 篇引用它的 posts 一起阻断。这些锚点直接判 `_homepage_surface`，因为它是唯一把冻结目标
与来源行投影成 `_entity.json` 字节的地方。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import content.release.canonical.final_surface_projection as subject
from content.release.canonical.object_transaction_contract import (
    ObjectTransactionError,
)
from core.schema import assert_valid

_WIKI_URL = "https://zh.wikipedia.org/api/rest_v1/page/summary/%E4%B9%9D%E5%AF%A8%E6%B2%9F"
_WEB_URL = "https://www.example-scenic.gov.cn/intro"


def _source_row(*, source_id: str, url: str) -> dict[str, Any]:
    unit = f"{source_id}__0123456789abcdef"
    return {
        "sourceId": source_id,
        "sourceRef": f"sources/{unit}/source.md",
        "sourceUrl": url,
        "sourceUseMode": "factual_reference_only",
        "fetchedAt": "2026-09-06T11:50:00+08:00",
        "digest": "sha256:" + "b" * 64,
        "meta": {"title": "九寨沟", "rawSha256": "sha256:" + "b" * 64},
    }


def _target(*, region: str) -> dict[str, Any]:
    return {
        "name": "九寨沟",
        "entityRef": "/entity/地点/景区/九寨沟",
        "entityId": "qwq_entity_jiuzhaigou",
        "entityType": "地点/景区",
        "region": region,
    }


def _project(
    tmp_path: Path,
    *,
    target: dict[str, Any],
    source_rows: list[dict[str, Any]],
) -> dict[Path, bytes | Path]:
    execution_root = tmp_path / "exec-001"
    object_dir = execution_root / "objects" / "entities" / "地点" / "景区" / "九寨沟"
    draft = object_dir / "4.draft"
    draft.mkdir(parents=True)
    (draft / "page.md").write_text("# 九寨沟\n\n正文。\n", encoding="utf-8")
    return subject._homepage_surface(
        execution_root=execution_root,
        object_dir=object_dir,
        target_ref="entities/地点/景区/九寨沟",
        target=target,
        compose={"creatorProfileRef": "qwq_creator_geo_editor_001"},
        source_rows=source_rows,
    )


@pytest.mark.parametrize("source_id,url,source_kind", [
    ("zh_wikipedia", _WIKI_URL, "wikipedia"),
    ("toutiao_baike", "https://www.baike.com/wiki/九寨沟", "toutiao_baike"),
])
@pytest.mark.parametrize("extractor", [None, "html_text"])
def test_compliant_homepage_entity_header_validates_against_publish_schema(
    tmp_path: Path, source_id: str, url: str, source_kind: str, extractor: str | None,
) -> None:
    source = _source_row(source_id=source_id, url=url)
    if extractor is not None:
        source["meta"]["extractor"] = extractor
    target = _target(region="中国/四川省/阿坝藏族羌族自治州/九寨沟县")
    files = _project(tmp_path, target=target, source_rows=[source])

    entity = json.loads(files[Path("_entity.json")])
    assert_valid(entity, "publish", "entity", label="projected homepage entity")
    assert entity["geoTagRef"] == "Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县"
    assert entity["geoTagRef"] in entity["tagRefs"]
    assert entity["entityRef"] == target["entityRef"]
    assert entity["entityId"] == target["entityId"]
    assert entity["primarySource"]["sourceKind"] == source_kind
    assert entity["primarySource"]["policyRevision"] == "encyclopedia-primary"
    expected_extractor = extractor or ("wikipedia_api" if source_kind == "wikipedia" else "toutiao_baike_html")
    assert entity["primarySource"]["extractor"] == expected_extractor


def test_target_without_region_fails_closed_before_writing_entity(
    tmp_path: Path,
) -> None:
    with pytest.raises(ObjectTransactionError, match="lacks region for geoTagRef"):
        _project(
            tmp_path,
            target=_target(region=""),
            source_rows=[_source_row(source_id="zh_wikipedia", url=_WIKI_URL)],
        )


@pytest.mark.parametrize("extractor", [None, "html_text", "wikipedia_api"])
def test_primary_source_outside_encyclopedia_closed_set_fails_closed(
    tmp_path: Path, extractor: str | None,
) -> None:
    source = _source_row(source_id="official_site", url=_WEB_URL)
    if extractor is not None:
        source["meta"]["extractor"] = extractor
    with pytest.raises(ValueError, match=r"homepage entity /entity/地点/景区/九寨沟") as info:
        _project(
            tmp_path,
            target=_target(region="中国/四川省/阿坝藏族羌族自治州/九寨沟县"),
            source_rows=[source],
        )

    message = str(info.value)
    assert "primarySource" in message
    assert "sourceKind" in message or "policyRevision" in message
