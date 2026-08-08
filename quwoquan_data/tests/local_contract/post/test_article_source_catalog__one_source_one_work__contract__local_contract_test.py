"""Article source catalogs stay bound to the frozen base source unit."""

from __future__ import annotations

import json
from pathlib import Path

from content.post.article import evidence_bundle


def _write_source_unit(root: Path, name: str, *, url: str) -> Path:
    unit = root / "sources" / name
    unit.mkdir(parents=True)
    (unit / "source.md").write_text(
        f"---\nurl: {url}\n---\n杭州西湖的湖面、柳岸与游船构成连续景观。\n",
        encoding="utf-8",
    )
    (unit / "source.quality.json").write_text(
        json.dumps(
            {
                "sourceId": name,
                "quality": "Strong",
                "score": 8,
                "reasons": [],
                "excerpt": "杭州西湖的湖面与柳岸",
                "url": url,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return unit


def test_declared_base_source_does_not_adopt_neighbouring_discovery_units(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base = _write_source_unit(
        tmp_path,
        "杭州西湖__travelogue__base",
        url="https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E",
    )
    _write_source_unit(
        tmp_path,
        "杭州西湖__travelogue__related",
        url="https://zh.wikivoyage.org/wiki/%E6%B5%99%E6%B1%9F",
    )
    monkeypatch.setattr(evidence_bundle, "execution_root", lambda _execution_id: tmp_path)
    monkeypatch.setattr(
        evidence_bundle,
        "_source_dirs_for_entity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("declared base source must disable discovery fallback")
        ),
    )

    rows = evidence_bundle.load_source_records(
        "20260808--travel-article-m1--test-region--scale-001",
        ["杭州西湖"],
        base_source_ref=base.joinpath("source.md").relative_to(tmp_path).as_posix(),
    )

    assert [row["sourceId"] for row in rows] == [base.name]
    assert [row["url"] for row in rows] == [
        "https://zh.wikivoyage.org/wiki/%E6%9D%AD%E5%B7%9E"
    ]
