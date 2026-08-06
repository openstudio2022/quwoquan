#!/usr/bin/env python3
"""
verify_behavior_error_stack_convergence.py

阻断 behavior 上报重新引入自建异常/自建 post retry 栈。behavior 可以保留离线队列和
压缩传输，但 HTTP 失败必须统一经 CloudErrorMapper -> CloudException/runtimeFailure。
"""

from __future__ import annotations


import sys
from pathlib import Path

_SCRIPTS_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "scripts" and (parent / "_common" / "paths.py").is_file()
)
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from _common.paths import APP_ROOT, REPO_ROOT, SCRIPTS_ROOT

from pathlib import Path

import os
import sys

REPO_ROOT = str(REPO_ROOT)
TARGET = (
    "quwoquan_app/lib/service/content_service/content/content_behavior_fact/"
    "application/content_behavior_repository.dart"
)
FORBIDDEN = [
    "BehaviorReportException",
    "_postWithRetry",
]


def main() -> int:
    path = os.path.join(REPO_ROOT, TARGET)
    with open(path, encoding="utf-8") as handle:
        content = handle.read()
    failed = False
    for token in FORBIDDEN:
        if token in content:
            print(f"{TARGET}: forbidden behavior error stack token: {token}")
            failed = True
    if failed:
        print(
            "\nverify_behavior_error_stack_convergence: behavior 错误栈未统一到 CloudException/runtimeFailure",
            file=sys.stderr,
        )
        return 1
    print("verify_behavior_error_stack_convergence: behavior error stack converged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
