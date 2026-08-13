"""棘轮基线的读写，保证治理块不被 ``--update-baseline`` 抹掉。

棘轮基线由「计数」和「治理块」两部分组成，两者必须住在同一个文件里：owner、度量
口径和退役条件一旦跟数字分家，换口径重建基线就不再留下任何痕迹，而那正是这类债务
唯一真正的逃逸方式（见 ``quwoquan_ops/gate/verify_ratchet_baseline_governance.py``）。

各脚本原先都是 ``path.write_text(json.dumps(counts))``，一次固化就把治理块连同它
记录的口径变更史一起删掉。读写收敛到这里，是为了让「保留治理块」成为默认行为，而
不是每个脚本各自记得。
"""

from __future__ import annotations

import json
from pathlib import Path

#: 治理块的键前缀。下划线开头的顶层键一律不是计数。
GOVERNANCE_PREFIX = "_"


def load_counts(path: Path) -> dict[str, int]:
    """读取计数部分，跳过治理块。"""
    document = json.loads(path.read_text(encoding="utf-8"))
    return {
        key: value
        for key, value in document.items()
        if not key.startswith(GOVERNANCE_PREFIX)
    }


def write_counts(path: Path, counts: dict[str, int]) -> None:
    """重写计数，逐字保留既有治理块。"""
    document = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    governance = {
        key: value
        for key, value in document.items()
        if key.startswith(GOVERNANCE_PREFIX)
    }
    path.write_text(
        json.dumps(
            {**governance, **counts}, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )


__all__ = ["GOVERNANCE_PREFIX", "load_counts", "write_counts"]
