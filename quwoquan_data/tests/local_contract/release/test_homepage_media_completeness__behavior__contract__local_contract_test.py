from pathlib import Path

from core.io import write_json
from verify import verify_homepage_media_completeness as gate


def _write_execution(root: Path, *, capped: bool) -> None:
    source = root / "sources" / "测试实体乙__wikipedia__fixture"
    placements = [
        {
            "fileName": "20240730_Dongqian_Hu.jpg",
            "caption": "测试实体乙",
            "sourceOrder": 0,
            "placementType": "infoboxLead",
        },
        *[
            {
                "fileName": f"gallery_{index}.jpg",
                "caption": f"测试实体乙图{index}",
                "sourceOrder": index,
                "placementType": "groupMember",
                "groupId": "gal-001",
            }
            for index in range(1, 5)
        ],
    ]
    kept = 4 if capped else 5
    drops = [{"slug": "home_wikipedia#5", "reason": "capReached: old limit"}] if capped else []
    write_json(
        source / "meta.json",
        {
            "imagePlacements": placements,
            "assetFunnel": {
                "candidateCount": 5,
                "keptCount": kept,
                "droppedCount": len(drops),
                "quotaMode": "group_aware" if capped else "complete_source_page",
                "drops": drops,
            },
        },
    )
    write_json(
        source / "assets" / "index.json",
        {
            "assets": [
                {
                    "sourceAssetId": f"001_{index:03d}",
                    "fileName": placements[index - 1]["fileName"],
                }
                for index in range(1, kept + 1)
            ]
        },
    )
    entity = root / "entities" / "地点" / "景区" / "测试实体乙"
    write_json(
        entity / "manifest.json",
        {
            "assets": [
                {
                    "assetId": "dongqian_cover",
                    "fileName": "dongqian_cover.jpg",
                    "role": "cover",
                    "caption": "测试实体乙",
                    "placementType": "infoboxLead",
                    "sourceAssetRef": f"sources/{source.name}/assets/{placements[0]['fileName']}",
                },
                *[
                    {
                        "assetId": f"dongqian_related_{index}",
                        "fileName": f"dongqian_related_{index}.jpg",
                        "role": "related",
                        "caption": f"测试实体乙图{index}",
                        "placementType": "groupMember",
                        "sourceAssetRef": f"sources/{source.name}/assets/{placements[index]['fileName']}",
                    }
                    for index in range(1, kept)
                ],
            ]
        },
    )
    related_ids = ",".join(f"dongqian_related_{index}" for index in range(1, kept))
    (entity / "page.md").write_text(
        "---\ncoverImage: asset://dongqian_cover\n---\n# 测试实体乙\n\n正文。\n\n"
        f'## 相关图片\n\n:::gallery ids="{related_ids}" layout="grid"\n:::\n',
        encoding="utf-8",
    )
    write_json(
        entity / "evidence" / "media_dispositions.json",
        {
            "schema": "quwoquan_data.homepage_media_dispositions",
            "executionId": "20260713--travel-homepage-coverage--test-region-a--pilot-001",
            "objectRef": "地点/景区/测试实体乙",
            "assets": [
                {
                    "sourceAssetRef": f"sources/{source.name}/assets/{placements[0]['fileName']}",
                    "sourceAssetId": "001_001",
                    "disposition": "cover",
                    "assetId": "dongqian_cover",
                    "reason": "published",
                },
                *[
                    {
                        "sourceAssetRef": f"sources/{source.name}/assets/{placements[index]['fileName']}",
                        "sourceAssetId": f"001_{index + 1:03d}",
                        "disposition": "related",
                        "assetId": f"dongqian_related_{index}",
                        "reason": "published",
                    }
                    for index in range(1, kept)
                ],
            ],
        },
    )


def test_homepage_media_completeness_accepts_closed_execution(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "execution"
    _write_execution(root, capped=False)
    monkeypatch.setattr(gate.paths, "execution_root", lambda _execution: root)
    report = gate.homepage_media_completeness_report("execution")
    assert report["passed"] is True
    assert report["checkedSourceCount"] == 1
    assert report["checkedHomepageCount"] == 1


def test_homepage_media_completeness_rejects_historical_cap(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "execution"
    _write_execution(root, capped=True)
    monkeypatch.setattr(gate.paths, "execution_root", lambda _execution: root)
    report = gate.homepage_media_completeness_report("execution")
    assert report["passed"] is False
    assert "DATA.MEDIA.ENUMERATION_INCOMPLETE" in {row["code"] for row in report["issues"]}
    assert all("retryable" not in row for row in report["issues"])


def test_homepage_media_completeness_rejects_typed_fetch_failure(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "execution"
    _write_execution(root, capped=False)
    source = next((root / "sources").iterdir())
    meta_path = source / "meta.json"
    meta = gate.read_json(meta_path)
    meta["assetFunnel"] = {
        "candidateCount": 5,
        "keptCount": 4,
        "droppedCount": 1,
        "dedupeRemoved": 0,
        "quotaMode": "complete_source_page",
        "drops": [
            {
                "slug": "测试实体乙/home_wikipedia#5",
                "reason": "fetch:rate_limited",
                "statusCode": 429,
            }
        ],
        "fetchFailures": [
            {
                "sourceOrder": 4,
                "requestedUrl": "https://upload.wikimedia.org/example.jpg",
                "resolvedUrl": "https://upload.wikimedia.org/example.jpg",
                "failure": "rate_limited",
                "statusCode": 429,
                "attemptCount": 5,
            }
        ],
    }
    gate.write_json(meta_path, meta)
    monkeypatch.setattr(gate.paths, "execution_root", lambda _execution: root)

    report = gate.homepage_media_completeness_report("execution")

    assert report["passed"] is False
    assert "DATA.MEDIA.DOWNLOAD_INCOMPLETE" in {row["code"] for row in report["issues"]}


def test_homepage_media_completeness_requires_an_outcome_for_every_downloaded_image(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "execution"
    _write_execution(root, capped=False)
    evidence = root / "entities" / "地点" / "景区" / "测试实体乙" / "evidence" / "media_dispositions.json"
    payload = gate.read_json(evidence)
    payload["assets"].pop()
    write_json(evidence, payload)
    monkeypatch.setattr(gate.paths, "execution_root", lambda _execution: root)

    report = gate.homepage_media_completeness_report("execution")

    assert report["passed"] is False
    assert "DATA.MEDIA.ENUMERATION_INCOMPLETE" in {row["code"] for row in report["issues"]}
