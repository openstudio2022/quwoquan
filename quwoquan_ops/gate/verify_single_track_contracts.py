#!/usr/bin/env python3
"""全仓单轨契约零兼容门禁：禁止版本信封、aliases、双读与 warn-only 逃逸。

实现单轨落在 ``single_track_contracts/`` 包内；本文件只是稳定 CLI 入口，
并为既有消费者 re-export 包 API（re-export 面即包 ``__all__``）。
"""

from __future__ import annotations

import re  # noqa: F401  # contract 测试经 module.re 消费本模块的 re。
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate.single_track_contracts import *  # noqa: E402,F401,F403
from quwoquan_ops.gate.single_track_contracts import main  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
