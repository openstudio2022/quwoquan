#!/usr/bin/env python3
"""派生全 Python 治理边界及 Python/Shell 脚本 owner、角色与结构违规。

本门只读取物理树、既有入口和 canonical owner 目录，不维护脚本 registry、
债务 baseline 或 orphan allowlist。每个 Python 文件必须唯一落入派生治理边界；
``report`` 总是输出实时派生结果，``check`` 只阻断可确定的目录、命名、角色、
临时文件和无 owner tool 违规。外部入口路径闭包由
``verify_entrypoint_script_paths.py`` 单独负责。

实现单轨落在 ``python_script_governance/`` 包内；本文件只是稳定 CLI 入口，
并为既有消费者 re-export 包 API。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    path
    for path in Path(__file__).resolve().parents
    if (path / "repository_root.py").is_file()
)
if str(_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP))

from repository_root import repository_root  # noqa: E402

DEFAULT_ROOT = repository_root()
if str(DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT))

from quwoquan_ops.gate.python_script_governance import (  # noqa: E402
    derive_report,
    main,
    parse_args,
)

__all__ = ["DEFAULT_ROOT", "derive_report", "main", "parse_args"]


if __name__ == "__main__":
    raise SystemExit(main())
