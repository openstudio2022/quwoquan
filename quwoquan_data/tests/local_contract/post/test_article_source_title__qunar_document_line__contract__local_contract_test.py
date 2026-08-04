# spec_ref: specs/feature-tree/runtime/runtime-data-engineering/article-commercial-scale-closure/spec.md
from __future__ import annotations

from content.post.article.base_draft_source import extract_source_title
from core.io import write_json
from core.paths import execution_root


def test_extract_source_title_uses_document_line_when_heading_too_short(
    monkeypatch,
    tmp_path,
) -> None:
    execution_id = "20260731--travel-article-title--hangzhou-west-lake--pilot-001"
    root = tmp_path / "tasks" / execution_id
    source_dir = root / "sources" / "杭州西湖__travelogue__demo"
    source_dir.mkdir(parents=True)
    (source_dir / "source.clean.md").write_text(
        "1日游,2026杭州游记,杭州旅游/自助游/自由行/游玩攻略-【去哪儿攻略】\n\n"
        "# 1日游\n\n西湖边走走停停。\n",
        encoding="utf-8",
    )
    write_json(source_dir / "meta.json", {"sourceId": "qunar_demo", "title": ""})
    monkeypatch.setattr(
        "content.post.article.base_draft_source.execution_root",
        lambda _execution_id: root,
    )
    monkeypatch.setattr(
        "content.post.article.base_draft.execution_root",
        lambda _execution_id: root,
    )

    title = extract_source_title(execution_id, "sources/杭州西湖__travelogue__demo")

    assert title
    assert "1日游" in title or "杭州" in title
    assert title != "1日游"


def test_extract_source_title_accepts_short_cjk_metadata_before_inline_image(
    monkeypatch,
    tmp_path,
) -> None:
    execution_id = "20260803--travel-article-title--short-cjk--pilot-001"
    root = tmp_path / "tasks" / execution_id
    monkeypatch.setattr(
        "content.post.article.base_draft_source.execution_root",
        lambda _execution_id: root,
    )
    monkeypatch.setattr(
        "content.post.article.base_draft.execution_root",
        lambda _execution_id: root,
    )

    for ordinal, expected_title in enumerate(("西湖", "九寨沟"), start=1):
        source_dir = root / "sources" / f"short-cjk-{ordinal}"
        source_dir.mkdir(parents=True)
        (source_dir / "source.clean.md").write_text(
            f"![{expected_title}](asset://source-inline-001)\n\n"
            "## 了解\n\n这里是来源正文。\n",
            encoding="utf-8",
        )
        write_json(
            source_dir / "meta.json",
            {
                "sourceId": f"wikivoyage-short-{ordinal}",
                "title": expected_title,
            },
        )

        assert extract_source_title(execution_id, str(source_dir.relative_to(root))) == expected_title
