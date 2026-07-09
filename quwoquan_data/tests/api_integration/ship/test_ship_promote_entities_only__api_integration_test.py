"""homepage-only 批次 promote 契约：仅实体晋升时 ship 不得误判中止。"""
from __future__ import annotations

import sys
import types
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import pytest  # noqa: E402

import ship.handler as ship_handler  # noqa: E402


def _run_promote(monkeypatch: pytest.MonkeyPatch, *, posts: int, entities: int, copy_entities: bool) -> int:
    fake = types.SimpleNamespace(
        promote_release=lambda *a, **k: (0, 0, 0),
        promote_task_batch=lambda *a, **k: (posts, 0),
        promote_task_entities=lambda *a, **k: entities,
    )
    monkeypatch.setitem(sys.modules, "publish_ops.promote_to_publish", fake)
    args = ship_handler.argparse.Namespace(
        release_id=None,
        task="旅行/地域/中国/景区/示例任务",
        batch="b1",
        copy_entities=copy_entities,
    )
    return ship_handler._promote(args)


def _run_promote_release(monkeypatch: pytest.MonkeyPatch, *, posts: int, entities: int) -> int:
    fake = types.SimpleNamespace(
        promote_release=lambda *a, **k: (posts, 0, entities),
        promote_task_batch=lambda *a, **k: (0, 0),
        promote_task_entities=lambda *a, **k: 0,
    )
    monkeypatch.setitem(sys.modules, "publish_ops.promote_to_publish", fake)
    args = ship_handler.argparse.Namespace(
        release_id="rel_homepage_only",
        task=None,
        batch=None,
        copy_entities=False,
    )
    return ship_handler._promote(args)


class TestPromoteEntitiesOnly:
    def test_homepage_only_batch_counts_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _run_promote(monkeypatch, posts=0, entities=54, copy_entities=True) == 54

    def test_posts_and_entities_both_count(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _run_promote(monkeypatch, posts=10, entities=5, copy_entities=True) == 15

    def test_nothing_promoted_still_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _run_promote(monkeypatch, posts=0, entities=0, copy_entities=True) == 0

    def test_release_homepage_only_counts_entities(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # WP5 实测回归：homepage-only release 包 posts=0，实体晋升不得被判 nothing promoted。
        assert _run_promote_release(monkeypatch, posts=0, entities=1) == 1

    def test_release_nothing_promoted_still_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert _run_promote_release(monkeypatch, posts=0, entities=0) == 0
