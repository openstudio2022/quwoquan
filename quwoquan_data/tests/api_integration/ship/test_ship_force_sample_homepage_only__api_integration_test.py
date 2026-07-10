"""homepage-only 批次 force-current-batch-sample 契约。

homepage-only 批次（如 H100）只有 entities/ 产物，没有 posts 与
content_object_index.json；--force-current-batch-sample 必须允许
posts 为空、强制实体 refs 全量进样，而不是 SystemExit。
纯 posts 批次缺 content_object_index.json 时仍必须阻断。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import pytest  # noqa: E402

import ship.handler as ship_handler  # noqa: E402

TASK_ID = "旅行/地域/中国/景区/示例任务"
BATCH_ID = "b1"


def _fake_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, with_entities: bool) -> Path:
    root = tmp_path / "batch"
    shared = root / "_shared"
    shared.mkdir(parents=True)
    if with_entities:
        entity_dir = root / "entities" / "地点" / "景区" / "武侯祠"
        entity_dir.mkdir(parents=True)
        (entity_dir / "_entity.json").write_text(json.dumps({"name": "武侯祠"}), encoding="utf-8")
    monkeypatch.setattr(ship_handler, "batch_root", lambda t, b: root)
    monkeypatch.setattr(ship_handler, "batch_shared_dir", lambda t, b: shared)
    return root


class TestForceSampleHomepageOnly:
    def test_homepage_only_batch_posts_refs_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fake_batch(tmp_path, monkeypatch, with_entities=True)
        assert ship_handler._current_batch_post_refs(TASK_ID, BATCH_ID) == []
        assert ship_handler._current_batch_entity_refs(TASK_ID, BATCH_ID) == ["地点/景区/武侯祠"]

    def test_posts_batch_missing_index_still_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _fake_batch(tmp_path, monkeypatch, with_entities=False)
        with pytest.raises(SystemExit, match="content_object_index"):
            ship_handler._current_batch_post_refs(TASK_ID, BATCH_ID)
