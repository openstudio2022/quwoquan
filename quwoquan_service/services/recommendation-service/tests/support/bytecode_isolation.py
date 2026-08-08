"""把本服务测试 session 的字节码出口移出源码树。

根 AGENTS.md：源码树不得保留 `__pycache__/`、`*.pyc`、`*.pyo`，缓存必须重定向到
`.qwq_output/env/repo/local/**`。

本服务的测试通过 `pyproject.toml` 的 `pythonpath` import 服务自己的
`generated/**`、`internal/**` 与 `cmd/api`。CPython 默认把 `.pyc` 写回这些源码目录，
Ops 服务架构治理随后会把 `generated/**` 下的每个 `.pyc` 判成「缺少 generated
output marker」——这就是「recommendation-service 单跑绿、与 Ops 架构治理测试
串跑必红」的顺序依赖来源。

服务架构契约只允许 `tests/` 下存在 `local_contract`、`api_integration`、`support`，
因此不能用 `tests/conftest.py`。这里改用 `addopts = "-p support.bytecode_isolation"`：
`-p` 插件在任何 conftest、测试模块与被测包被 import 之前加载，所以整个 session 的
字节码都会落到 canonical 输出根，隔离不依赖调用方是否传了 `-B` /
`PYTHONDONTWRITEBYTECODE`。

spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
BYTECODE_CACHE_ROOT = (
    REPO_ROOT
    / ".qwq_output"
    / "env"
    / "repo"
    / "local"
    / "tests"
    / "cache"
    / "bytecode"
    / "recommendation-service"
)

sys.pycache_prefix = str(BYTECODE_CACHE_ROOT)
