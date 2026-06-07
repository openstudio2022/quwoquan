"""HITL 最小化回归（目标① 人只看真正模糊的项）：

策略 autoDiscardScoreAtMost 让"明确违规"(水印/平台标记，image_safety unsafe→1分)
自动 discard、不占用人工；"明确合格"(safe→4分)自动 publishable；只有真正模糊的
needs_review(人脸边界→2分)才转人工 fix。

可直接运行 python3 quwoquan_data/tests/integration/test_hitl_autopass.py
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
os.environ["QWQ_DATA_ROOT"] = str(_TMP)

sys.path.insert(0, str(SCRIPTS_ROOT))

from _common.review_ledger import (  # noqa: E402
    DEFAULT_POLICY,
    STATE_DISCARD,
    STATE_FIX,
    STATE_PUBLISHABLE,
    agent_image_item,
    needs_human,
    resolve_publish_state,
)


def test_unsafe_auto_discard_no_human():
    """水印/平台标记 unsafe → 1 分 → 自动 discard，不进人工队列。"""
    item = agent_image_item("a1", {"status": "unsafe", "reasons": ["watermark"]})
    assert resolve_publish_state(item, DEFAULT_POLICY) == STATE_DISCARD
    assert needs_human(item, DEFAULT_POLICY) is False


def test_needs_review_still_human():
    """人脸边界 needs_review → 2 分 → 仍需人工裁决（不自动丢弃）。"""
    item = agent_image_item("a2", {"status": "needs_review", "reasons": ["face_boundary"]})
    assert resolve_publish_state(item, DEFAULT_POLICY) == STATE_FIX
    assert needs_human(item, DEFAULT_POLICY) is True


def test_safe_auto_publishable():
    """safe → 4 分 → 自动可发布，无需人工。"""
    item = agent_image_item("a3", {"status": "safe", "reasons": []})
    assert resolve_publish_state(item, DEFAULT_POLICY) == STATE_PUBLISHABLE
    assert needs_human(item, DEFAULT_POLICY) is False


def test_disable_auto_discard_reverts_to_human():
    """关闭 autoDiscardScoreAtMost → 退回旧行为（unsafe 也转人工）。"""
    pol = {"autoApprove": {"agentMinScore": 3, "requireHumanWhenDoubtful": True},
           "reprocess": {"maxAttempts": 3}}
    item = agent_image_item("a4", {"status": "unsafe", "reasons": ["platform_mark"]})
    assert resolve_publish_state(item, pol) == STATE_FIX
    assert needs_human(item, pol) is True


def _run_all() -> None:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"hitl autopass tests passed ({len(fns)})")


if __name__ == "__main__":
    _run_all()
