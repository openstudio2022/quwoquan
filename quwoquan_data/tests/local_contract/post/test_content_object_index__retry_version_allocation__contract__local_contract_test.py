"""Post retries freeze the next canonical version before authoring."""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data"
)
for path in (DATA_ROOT / "scripts", DATA_ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from content.post import object_index
from support.execution_manifest_fixture import build_execution_fixture


def test_post_retry_allocates_after_existing_canonical_version(
    monkeypatch,
    tmp_path: Path,
) -> None:
    execution_id = "20260809--travel-article-version--test-region-a--pilot-002"
    build_execution_fixture(
        execution_id,
        retry_of="20260809--travel-article-version--test-region-a--pilot-001",
    )
    publish_root = tmp_path / "publish"
    existing = publish_root / "posts/article/攻略/杭州西湖攻略/1"
    existing.mkdir(parents=True)
    (existing / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(object_index.core_paths, "PUBLISH_ROOT", publish_root)

    first = object_index.register_content_object(
        execution_id,
        "杭州西湖__source_a",
        content_type="article",
        angle="攻略",
        title="杭州西湖攻略",
    )
    second = object_index.register_content_object(
        execution_id,
        "杭州西湖__source_b",
        content_type="article",
        angle="攻略",
        title="杭州西湖攻略",
    )

    assert first["seq"] == 2
    assert second["seq"] == 3


def test_partial_canonical_directory_does_not_reserve_a_version(
    monkeypatch,
    tmp_path: Path,
) -> None:
    execution_id = "20260809--travel-image-version--test-region-a--pilot-001"
    build_execution_fixture(execution_id)
    publish_root = tmp_path / "publish"
    partial = publish_root / "posts/image/画报/西湖清晨/1"
    partial.mkdir(parents=True)
    (partial / "staging.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(object_index.core_paths, "PUBLISH_ROOT", publish_root)

    coords = object_index.register_content_object(
        execution_id,
        "杭州西湖_image",
        content_type="image",
        angle="画报",
        title="西湖清晨",
    )

    assert coords["seq"] == 1
