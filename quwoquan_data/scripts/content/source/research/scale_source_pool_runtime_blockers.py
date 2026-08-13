"""scale source-pool runtime 的 typed 阻断错误（拆分自 scale_source_pool_runtime）。

各 runtime 兄弟模块共享同一个错误码与 fail-closed 语义。
"""
from __future__ import annotations

RUNTIME_INPUT_UNBOUND = "DATA.SOURCE.POOL.RUNTIME_INPUT_UNBOUND"


class ScaleSourcePoolRuntimeError(ValueError):
    """Typed missing, drifted, or cross-lane runtime source-pool input."""

    code = RUNTIME_INPUT_UNBOUND

    def __init__(self, issue: object) -> None:
        message = str(issue).strip()
        if not message:
            raise ValueError("source-pool runtime blocker requires an issue")
        self.issue = message
        super().__init__(f"{self.code}: {message}")


def _fail(issue: object) -> ScaleSourcePoolRuntimeError:
    return ScaleSourcePoolRuntimeError(issue)
