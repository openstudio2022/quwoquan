#!/usr/bin/env python3
"""
verify_behavior_error_stack_convergence.py

阻断 behavior 上报重新引入自建异常/自建 post retry 栈。behavior 可以保留离线队列和
压缩传输，但 HTTP 失败必须统一经 CloudErrorMapper -> CloudException/runtimeFailure。
"""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
TARGET = "quwoquan_app/lib/cloud/services/behavior/behavior_repository.dart"
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
