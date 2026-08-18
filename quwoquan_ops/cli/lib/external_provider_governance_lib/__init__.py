"""external_provider_governance 实现包。

公开入口由稳定 façade ``external_provider_governance.py`` re-export。这里仅保留
延迟包装，避免包初始化时反向加载 façade 形成循环依赖。
"""

from __future__ import annotations

from typing import Any


def compile_single_environment_bindings(**kwargs: Any) -> dict[str, Any]:
    from .single_environment import compile_single_environment_bindings as compile_bindings

    return compile_bindings(**kwargs)


__all__ = ["compile_single_environment_bindings"]
