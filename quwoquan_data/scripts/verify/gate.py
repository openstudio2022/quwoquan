"""Exit gate for verify command（纯决策，逻辑在 _common.post_verify）。"""
from __future__ import annotations

from _common.post_verify import verify_scope


def gate_verify(*, task: str | None = None, batch: str | None = None, release: str | None = None, scope: str = "current"):
    """返回 (roots, issues)。issues 非空即门禁失败。"""
    return verify_scope(task=task, batch=batch, release=release, scope=scope)
