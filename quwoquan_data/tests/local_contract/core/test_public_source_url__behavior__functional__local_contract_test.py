import pytest

from core.io import read_json, write_json
from core.public_source_url import normalize_public_https_url, normalize_public_source_url
from content.homepage import homepage_source_catalog


def test_public_source_url_canonicalizes_and_strips_tracking() -> None:
    assert normalize_public_source_url(
        "https://zh.wikipedia.org/wiki/九寨沟?utm_source=test#history",
        source_kind="wikipedia",
    ) == "https://zh.wikipedia.org/wiki/九寨沟"
    assert normalize_public_source_url(
        "https://baike.baidu.com/item/九寨沟?from=lemma",
        source_kind="baidu_baike",
    ) == "https://baike.baidu.com/item/九寨沟"
    assert normalize_public_https_url(
        "https://commons.wikimedia.org/wiki/File:Scenic.jpg?utm_source=test"
    ) == "https://commons.wikimedia.org/wiki/File:Scenic.jpg"


@pytest.mark.parametrize(
    ("url", "source_kind"),
    [
        ("http://zh.wikipedia.org/wiki/九寨沟", "wikipedia"),
        ("https://127.0.0.1/wiki/九寨沟", "wikipedia"),
        ("https://zh.wikipedia.org/wiki/九寨沟?access_token=secret", "wikipedia"),
        ("https://baike.baidu.com/item/九寨沟", "wikipedia"),
    ],
)
def test_public_source_url_blocks_unsafe_or_contract_drift(
    url: str,
    source_kind: str,
) -> None:
    with pytest.raises(ValueError):
        normalize_public_source_url(url, source_kind=source_kind)


def test_homepage_source_catalog_closes_primary_evidence(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_id = "20260714--travel-homepage-coverage--test-region-a--pilot-001"
    execution_root = tmp_path / "tasks" / execution_id
    unit = execution_root / "sources" / "unit-1"
    unit.mkdir(parents=True)
    (unit / "source.md").write_text("九寨沟来源正文", encoding="utf-8")
    (unit / "source.clean.md").write_text("九寨沟来源正文", encoding="utf-8")
    write_json(
        unit / "meta.json",
        {
            "sourceUnitId": "unit-1",
                "entityName": "九寨沟",
            "sourceKind": "wikipedia",
                "extractor": "wikipedia_api",
            "canonicalUrl": "https://zh.wikipedia.org/wiki/九寨沟",
            "title": "九寨沟",
            "fetchedAt": "2026-07-11T00:00:00Z",
            "snapshotHash": "sha256:" + ("a" * 64),
            "sourceUseMode": "licensed_adaptation",
                "policyRevision": "encyclopedia-primary",
            "license": "CC BY-SA 4.0",
        },
    )
    media = execution_root / "sources" / "unit-2"
    media.mkdir(parents=True)
    (media / "source.md").write_text("九寨沟图片来源", encoding="utf-8")
    write_json(
        media / "meta.json",
        {
            "sourceUnitId": "unit-2",
            "entityName": "九寨沟",
            "sourceKind": "image_collection",
            "extractor": "",
            "canonicalUrl": "https://commons.wikimedia.org/wiki/File:Scenic.jpg",
            "title": "九寨沟开放许可图片",
            "fetchedAt": "2026-07-11T00:00:00Z",
            "snapshotHash": "sha256:" + ("b" * 64),
            "sourceUseMode": "licensed_adaptation",
            "policyRevision": "",
            "license": "CC BY-SA 4.0",
        },
    )
    monkeypatch.setattr(homepage_source_catalog, "execution_root", lambda _execution_id: execution_root)
    obj = tmp_path / "object"
    obj.mkdir()
    primary, urls, evidence_ref, digest = homepage_source_catalog._materialize_homepage_source_catalog(
        execution_id,
        obj,
        {"primaryEvidenceRef": "sources/unit-1/source.md"},
        fallback_title="九寨沟",
        source_refs=(
            "sources/unit-1/source.md",
            "sources/unit-2/source.md",
        ),
    )
    assert primary["sourceKind"] == "wikipedia"
    assert urls == ["https://zh.wikipedia.org/wiki/九寨沟"]
    assert evidence_ref == "evidence/sources/unit-1/meta.json"
    assert digest.startswith("sha256:")
    assert (obj / "evidence/source_catalog.json").is_file()
    assert (obj / "evidence/sources/unit-1/source.clean.md").read_text(
        encoding="utf-8"
    ) == "九寨沟来源正文"
    catalog = read_json(obj / "evidence/source_catalog.json")
    assert [row["sourceUnitId"] for row in catalog["sources"]] == ["unit-1", "unit-2"]
    assert (obj / "evidence/sources/unit-2/source.clean.md").read_text(
        encoding="utf-8"
    ) == "九寨沟图片来源"
