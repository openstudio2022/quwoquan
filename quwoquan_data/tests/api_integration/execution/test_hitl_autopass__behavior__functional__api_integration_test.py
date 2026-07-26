"""HITL 最小化回归（目标① 人只看真正模糊的项）：

策略 autoDiscardScoreAtMost 让"明确违规"(水印/平台标记，image_safety unsafe→1分)
自动 discard、不占用人工；"明确合格"(safe→4分)自动 publishable；只有真正模糊的
needs_review(人脸边界→2分)才转人工 fix。

可直接运行 python3 quwoquan_data/tests/api_integration/execution/test_hitl_autopass__behavior__functional__api_integration_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

DATA_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "quwoquan_data")
TESTS_ROOT = DATA_ROOT / "tests"
SCRIPTS_ROOT = DATA_ROOT / "scripts"
for _path in (DATA_ROOT, TESTS_ROOT, SCRIPTS_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="hitl_"))

sys.path.insert(0, str(SCRIPTS_ROOT))

from core.control_types import ReviewPublishState  # noqa: E402
from content.review.ledger import (  # noqa: E402
    agent_image_verdict,
    needs_human,
    resolve_publish_state,
)
from content.review.policy import review_policy  # noqa: E402


def test_unsafe_auto_discard_no_human():
    """水印/平台标记 unsafe → 1 分 → 自动 discard，不进人工队列。"""
    item = agent_image_verdict("a1", {"status": "unsafe", "reasons": ["watermark"]})
    assert resolve_publish_state(item) is ReviewPublishState.DISCARD
    assert needs_human(item) is False


def test_needs_review_still_human():
    """人脸边界 needs_review → 2 分 → 仍需人工裁决（不自动丢弃）。"""
    item = agent_image_verdict("a2", {"status": "needs_review", "reasons": ["face_boundary"]})
    assert resolve_publish_state(item) is ReviewPublishState.FIX
    assert needs_human(item) is True


def test_safe_auto_publishable():
    """safe → 4 分 → 自动可发布，无需人工。"""
    item = agent_image_verdict("a3", {"status": "safe", "reasons": []})
    assert resolve_publish_state(item) is ReviewPublishState.PUBLISHABLE
    assert needs_human(item) is False


def test_policy_owns_auto_discard_threshold():
    """Unsafe disposition follows the repository-owned review policy."""
    policy = review_policy()
    item = agent_image_verdict("a4", {"status": "unsafe", "reasons": ["platform_mark"]})
    assert item.agent_score == policy.auto_discard_at_most


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"hitl autopass tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
