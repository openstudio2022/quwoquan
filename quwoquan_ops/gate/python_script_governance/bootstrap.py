"""仓库根发现。依赖包 ``__init__`` 已完成的 sys.path bootstrap。"""
from __future__ import annotations

from repository_root import repository_root

DEFAULT_ROOT = repository_root()
