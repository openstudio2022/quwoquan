"""无人值守 fleet 驱动的落点合同测试。

Given `.qwq_output/data/local` 只允许 `cache/` 与 `workspace/`，
When `fleet_dispatcher.sh` 用默认 `--log-dir` 起一次 lane，
Then 该默认落点必须在 `DATA_WORKSPACE_ROOT` 之内，否则任何正式 fleet 运行都会让
`verify output-root-isolation` 变红——驱动是 shell、不能 import paths，所以这条
一致性只能由测试锁住。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

DATA_ROOT = next(
    parent for parent in Path(__file__).resolve().parents
    if parent.name == "quwoquan_data"
)
SCRIPTS_ROOT = DATA_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from core.paths import (  # noqa: E402
    DATA_LOCAL_ROOT,
    DATA_WORKSPACE_ROOT,
    OUTPUT_ROOT,
)

DISPATCHER = (
    SCRIPTS_ROOT / "content/execution/runner/fleet_dispatcher.sh"
)
_LOG_DIR_DEFAULT_RE = re.compile(
    r'^LOG_DIR="\$\{LOG_DIR:-\$REPO_ROOT/(?P<relative>[^}"]*?)/\$\(date',
    re.MULTILINE,
)


def _dispatcher_default_log_dir_relative() -> str:
    match = _LOG_DIR_DEFAULT_RE.search(DISPATCHER.read_text(encoding="utf-8"))
    assert match is not None, (
        "fleet_dispatcher.sh must keep one parameterized default --log-dir "
        "so its layout stays assertable"
    )
    return match.group("relative")


def _dispatcher_suffix_under_output_root() -> Path:
    """驱动默认落点相对输出根的后缀。

    测试隔离会把 `QWQ_OUTPUT_ROOT` 指到临时目录，而 shell 默认值是仓库相对路径，
    所以两者只能在「相对输出根」这一层比较。
    """
    relative = Path(_dispatcher_default_log_dir_relative())
    return relative.relative_to(".qwq_output")


def test_dispatcher_default_log_dir_lives_under_the_workspace_root() -> None:
    """shell 默认落点必须落在 paths.py 声明的可弃 workspace 子树内。"""
    suffix = _dispatcher_suffix_under_output_root()
    workspace_suffix = DATA_WORKSPACE_ROOT.relative_to(OUTPUT_ROOT)

    assert suffix.is_relative_to(workspace_suffix), (
        f"dispatcher default log dir {suffix} must sit under {workspace_suffix}"
    )


def test_dispatcher_default_log_dir_is_not_directly_under_data_local() -> None:
    """回潮锁：直接落 data/local/<name> 会被布局门拒绝。"""
    suffix = _dispatcher_suffix_under_output_root()
    local_suffix = DATA_LOCAL_ROOT.relative_to(OUTPUT_ROOT)

    assert suffix.parent != local_suffix, (
        "fleet logs must not sit directly under data/local; "
        "only cache/ and workspace/ are allowed there"
    )
