"""``python -m quwoquan_ops.cli.lib.local_environment_auth`` CLI 入口。

原单文件 ``if __name__ == "__main__"`` 块逐字搬移；用法与输出文本不变。
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from .secret_material import _print_shell_environment

if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--shell":
        _print_shell_environment(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(
            "usage: python -m quwoquan_ops.cli.lib.local_environment_auth "
            "--shell <alpha|beta|gamma> <alpha-local|beta-local|gamma-local>"
        )
