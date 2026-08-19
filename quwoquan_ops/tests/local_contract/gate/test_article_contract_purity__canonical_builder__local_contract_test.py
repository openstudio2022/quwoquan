from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
GATE = ROOT / "quwoquan_app/scripts/content_service/content/post/verify_article_contract_purity.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "verify_article_contract_purity_companion",
        GATE,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_article_gate_locks_builder_times_and_retired_wire_absence(
    tmp_path: Path,
) -> None:
    gate = _load_gate()
    gate.ROOT = tmp_path
    gate.POST_DTO_FILES = [
        _write(tmp_path / "post_view.dart", "createdAt: canonicalCreatedAt\n"),
        _write(tmp_path / "contracts.dart", "createdAt: canonicalCreatedAt\n"),
    ]
    gate.READ_PATH_FILES = [
        _write(tmp_path / f"read-{index}.txt", "canonical markdown read\n")
        for index in range(3)
    ]
    gate.ARTICLE_DETAIL_VIEW = _write(
        tmp_path / "article_detail_view.dart",
        "enum ArticleDetailDocumentSource { markdown, empty }\n",
    )
    gate.POST_FIELDS = _write(tmp_path / "fields.yaml", "fields:\n- name: title\n")
    gate.ARTICLE_POST_PROJECTION = _write(
        tmp_path / "article_post.yaml",
        "fields:\n- name: body\n  aliases: []\n- name: summary\n  aliases: []\n",
    )
    gate.ARTICLE_SURFACE_VIEW_MAPPER = _write(
        tmp_path / "content_surface_view_mapper.dart",
        "canonical mapping\n",
    )
    gate.CONTENT_OBJECT_BUILDER = _write(
        tmp_path / "content_post_wire_test_builder.dart",
        "fixture_article_001 {'updatedAt': updatedAt, 'publishedAt': publishedAt}\n",
    )
    gate.DEAD_ARTIFACTS = [tmp_path / "retired_article_document.dart"]

    assert gate.main() == 0

    gate.CONTENT_OBJECT_BUILDER.write_text(
        "fixture_article_001 {'updatedAt': updatedAt}\n",
        encoding="utf-8",
    )
    assert gate.main() == 1

    gate.CONTENT_OBJECT_BUILDER.write_text(
        "fixture_article_001 {'updatedAt': updatedAt, 'publishedAt': publishedAt}\n",
        encoding="utf-8",
    )
    gate.DEAD_ARTIFACTS[0].write_text("articleDocument\n", encoding="utf-8")
    assert gate.main() == 1
