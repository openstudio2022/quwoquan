#!/usr/bin/env python3
"""从目录与 Markdown 直接读取、校验和展示特性树。

本工具刻意不支持 tree/index/registry/acceptance/changelog 兼容读取。

实现单轨落在 ``quwoquan_ops/cli/lib/feature_tree/`` 包内（context / patterns /
nodes / parsing / gitio / delta / ownership / evidence / commands / verify /
cli_entry）；本文件是稳定 CLI 入口并 re-export 包 API。fixture 树测试通过
monkeypatch ``quwoquan_ops.cli.lib.feature_tree.context`` 的 ``REPO_ROOT`` /
``TREE_ROOT`` 驱动。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.cli.lib.feature_tree import *  # noqa: E402,F401,F403
from quwoquan_ops.cli.lib.feature_tree import (  # noqa: E402,F401
    Node,
    build_parser,
    command_change_report,
    command_context,
    command_overview,
    command_verify,
    context,
    discover_nodes,
    main,
    node_for_spec,
    owners_for_path,
    parent_chain,
    resolve_target,
)

if __name__ == "__main__":
    raise SystemExit(main())
