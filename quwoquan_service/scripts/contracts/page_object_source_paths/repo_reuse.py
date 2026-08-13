"""跨仓库只读复用：临时 import 门禁/App 模块，不复制其规则。

本模块只做 ``sys.path`` 受控挂载与只读加载，绝不在源码树留 ``__pycache__``，
也不把任何外部模块规则复制进本工具。
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .models import APP_DIR_NAME, REPORT_DIR_NAME


@contextmanager
def _importable(directory: Path):
    """临时把目录挂进 ``sys.path`` 做只读 import，且不在源码树留 ``__pycache__``。

    仓库禁止源码树出现 ``__pycache__``；本工具会被反复执行，绝不能顺手污染
    ``quwoquan_ops/gate`` 或 ``quwoquan_app/scripts/runtime``。
    """

    previous_bytecode_flag = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(directory))
    try:
        yield
    finally:
        if sys.path and sys.path[0] == str(directory):
            sys.path.pop(0)
        sys.dont_write_bytecode = previous_bytecode_flag


def _load_shape_resolver(repository_root: Path) -> Callable[[str], tuple[str, str, str, str] | None]:
    """只读复用 ``object_path_map`` 的对象身份派生，不复制别名规则。"""

    with _importable(repository_root / "quwoquan_ops" / "gate"):
        import object_path_map  # type: ignore

    graph_path = repository_root / object_path_map.CONTRACT_GRAPH_PATH
    roster = object_path_map.ObjectRoster(json.loads(graph_path.read_bytes()))

    def shape_of(source_path: str) -> tuple[str, str, str, str] | None:
        parts = Path(source_path).parts
        if not parts or parts[0] != "lib":
            return None
        return object_path_map.derive_app_target_shape_identity(parts[1:], roster)

    return shape_of


def _load_disk_scan_paths(repository_root: Path) -> frozenset[str]:
    with _importable(repository_root / APP_DIR_NAME / "scripts" / "runtime" / "page"):
        import page_disk_scan_paths  # type: ignore
    return page_disk_scan_paths.matrix_disk_scan_paths(repository_root)


def _default_report_dir(repository_root: Path) -> Path:
    """复用 Ops 的唯一输出根契约，不在本工具复制 ``.qwq_output`` 布局规则。"""

    with _importable(repository_root):
        from quwoquan_ops.cli.lib.output_paths import repo_runs_root  # type: ignore
    return repo_runs_root() / REPORT_DIR_NAME
