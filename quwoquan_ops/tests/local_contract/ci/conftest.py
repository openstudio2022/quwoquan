"""ci concern 共享 fixture。

local readiness 在隔离 capsule 内以 `GIT_DIR` / `GIT_WORK_TREE` 运行 focused 测试；
本目录多数用例会在 tmp_path 里 `git init` 自建仓库，若继承这两个变量，所有 git 命令都会
落到 capsule 的 git dir（`dev1.0` 已存在、index 被污染）。这里按用例粒度剥离，
让测试仓库只由 cwd 决定。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

_CAPSULE_GIT_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OPTIONAL_LOCKS")


@pytest.fixture(autouse=True)
def _isolated_git_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in _CAPSULE_GIT_ENV:
        monkeypatch.delenv(name, raising=False)
    yield
