"""媒体处置的两条判据按可判定时点分家（DEC-029）。

历史失败形态：`verify homepage-media-completeness` 把「决策是否完整」与「manifest 是否
忠实兑现」合在一条命令里，而兑现证据只在物化期产生。`1.download` 的完成判据绑的正是
这条命令，于是该阶段结构上永远拿不到 pass，homepage lane 的 receipt 链在第三个阶段断裂
（`20260825--travel-homepage-m1-first--sichuan--pilot-003` 的 `004-1.download.json`）。

拆分后：决策闭合只读 `sources/**` 与冻结处置，`1.download` 截面即可判定，且不认发布
集合——下载期每个对象都必须有完整决策。兑现闭合只做对账，两个方向的差集都 fail closed，
它不重新决策，因此不可能与决策结论分歧。
"""
from pathlib import Path

import pytest

from core.io import write_json
from verify import verify_homepage_media_completeness as gate

_SOURCE = "测试实体甲__wikipedia__fixture"
_OBJECT = ("地点", "景区", "测试实体甲")
_EXECUTION_ID = "20260713--travel-homepage-coverage--test-region-a--pilot-001"


def _asset_ref(file_name: str) -> str:
    return f"sources/{_SOURCE}/assets/{file_name}"


def _write_source(root: Path) -> None:
    source = root / "sources" / _SOURCE
    write_json(
        source / "meta.json",
        {
            "entityName": _OBJECT[2],
            "imagePlacements": [
                {
                    "fileName": "hero.jpg",
                    "caption": "测试实体甲",
                    "sourceOrder": 0,
                    "placementType": "infoboxLead",
                },
                {
                    "fileName": "panorama.jpg",
                    "caption": "测试实体甲全景",
                    "sourceOrder": 1,
                    "placementType": "inline",
                },
            ],
            "assetFunnel": {
                "candidateCount": 2,
                "keptCount": 2,
                "droppedCount": 0,
                "quotaMode": "complete_source_page",
                "drops": [],
            },
        },
    )
    write_json(
        source / "assets" / "index.json",
        {
            "assets": [
                {"sourceAssetId": "001_001", "fileName": "hero.jpg"},
                {"sourceAssetId": "001_002", "fileName": "panorama.jpg"},
            ]
        },
    )


def _write_dispositions(root: Path, assets: list[dict[str, object]]) -> None:
    write_json(
        root / "entities" / Path(*_OBJECT) / "evidence" / "media_dispositions.json",
        {
            "schema": "quwoquan_data.homepage_media_dispositions",
            "executionId": _EXECUTION_ID,
            "objectRef": "/".join(_OBJECT),
            "assets": assets,
        },
    )


def _closed_dispositions() -> list[dict[str, object]]:
    return [
        {
            "sourceAssetRef": _asset_ref("hero.jpg"),
            "sourceAssetId": "001_001",
            "disposition": "cover",
            "assetId": "jia_cover",
            "reason": "published",
        },
        {
            "sourceAssetRef": _asset_ref("panorama.jpg"),
            "sourceAssetId": "001_002",
            "disposition": "policyExcluded",
            "assetId": "",
            "reason": "duplicate_visual_subject",
        },
    ]


def _write_manifest(root: Path) -> None:
    entity = root / "entities" / Path(*_OBJECT)
    write_json(
        entity / "manifest.json",
        {
            "assets": [
                {
                    "assetId": "jia_cover",
                    "fileName": "jia_cover.jpg",
                    "role": "cover",
                    "caption": "测试实体甲",
                    "placementType": "infoboxLead",
                    "sourceAssetRef": _asset_ref("hero.jpg"),
                }
            ]
        },
    )
    (entity / "page.md").write_text(
        "---\ncoverImage: asset://jia_cover\n---\n# 测试实体甲\n\n正文。\n",
        encoding="utf-8",
    )


@pytest.fixture
def execution_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "execution"
    _write_source(root)
    monkeypatch.setattr(gate.paths, "execution_root", lambda _execution: root)
    monkeypatch.setattr(gate, "load_terminal_execution_evidence", lambda _root: None)
    return root


def test_decision_closes_without_any_materialization(execution_root: Path) -> None:
    """1.download 截面没有 manifest 也没有 page.md，决策仍必须可判定为闭合。"""

    _write_dispositions(execution_root, _closed_dispositions())

    report = gate.homepage_media_decision_report("execution")

    assert report["passed"] is True, report["issues"]
    assert not (execution_root / "entities" / Path(*_OBJECT) / "manifest.json").exists()


def test_decision_rejects_a_downloaded_image_without_outcome(execution_root: Path) -> None:
    """「每张下载图恰有一个发布处置」不因判据前移而放宽。"""

    _write_dispositions(execution_root, _closed_dispositions()[:1])

    report = gate.homepage_media_decision_report("execution")

    assert report["passed"] is False
    assert "DATA.MEDIA.ENUMERATION_INCOMPLETE" in {row["code"] for row in report["issues"]}


def test_decision_rejects_non_published_outcome_pointing_at_an_asset(
    execution_root: Path,
) -> None:
    assets = _closed_dispositions()
    assets[1]["assetId"] = "jia_leaked"
    _write_dispositions(execution_root, assets)

    report = gate.homepage_media_decision_report("execution")

    assert report["passed"] is False
    assert "DATA.CONTRACT.INVALID" in {row["code"] for row in report["issues"]}


def test_decision_does_not_read_the_publishable_scope(execution_root: Path) -> None:
    """下载期还没有发布集合；每个下载对象都必须有完整决策，不存在豁免。"""

    _write_dispositions(execution_root, _closed_dispositions()[:1])

    assert gate.homepage_media_decision_report("execution")["passed"] is False


def test_fulfillment_accepts_a_manifest_that_matches_frozen_dispositions(
    execution_root: Path,
) -> None:
    _write_dispositions(execution_root, _closed_dispositions())
    _write_manifest(execution_root)

    report = gate.homepage_media_fulfillment_report(
        "execution", publishable_names={_OBJECT[2]}
    )

    assert report["passed"] is True, report["issues"]


def test_fulfillment_rejects_a_published_outcome_missing_from_the_manifest(
    execution_root: Path,
) -> None:
    _write_dispositions(execution_root, _closed_dispositions())
    write_json(
        execution_root / "entities" / Path(*_OBJECT) / "manifest.json", {"assets": []}
    )
    (execution_root / "entities" / Path(*_OBJECT) / "page.md").write_text(
        "# 测试实体甲\n\n正文。\n", encoding="utf-8"
    )

    report = gate.homepage_media_fulfillment_report(
        "execution", publishable_names={_OBJECT[2]}
    )

    assert report["passed"] is False
    assert "DATA.MEDIA.ENUMERATION_INCOMPLETE" in {row["code"] for row in report["issues"]}


def test_fulfillment_rejects_a_manifest_asset_with_no_frozen_disposition(
    execution_root: Path,
) -> None:
    """反向差集同样 fail closed，否则物化可以静默发布一张没被决策过的图。"""

    _write_dispositions(execution_root, _closed_dispositions())
    entity = execution_root / "entities" / Path(*_OBJECT)
    write_json(
        entity / "manifest.json",
        {
            "assets": [
                {
                    "assetId": "jia_cover",
                    "fileName": "jia_cover.jpg",
                    "role": "cover",
                    "caption": "测试实体甲",
                    "placementType": "infoboxLead",
                    "sourceAssetRef": _asset_ref("hero.jpg"),
                },
                {
                    "assetId": "jia_smuggled",
                    "fileName": "jia_smuggled.jpg",
                    "role": "related",
                    "caption": "未经决策的图",
                    "placementType": "inline",
                    "sourceAssetRef": _asset_ref("never_decided.jpg"),
                },
            ]
        },
    )
    (entity / "page.md").write_text(
        "---\ncoverImage: asset://jia_cover\n---\n# 测试实体甲\n\n正文。\n",
        encoding="utf-8",
    )

    report = gate.homepage_media_fulfillment_report(
        "execution", publishable_names={_OBJECT[2]}
    )

    assert report["passed"] is False
    assert any(
        "never_decided.jpg" in str(row.get("attrs", {})) for row in report["issues"]
    ), report["issues"]
