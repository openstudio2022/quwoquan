"""release lifecycle receipts 实现子包。

对外唯一入口与 monkeypatch 锚点是同目录薄入口
``quwoquan_ops/ci/render_release_lifecycle_receipts.py``（workflow 以脚本路径
调用、consumer 以模块 import）；请勿直接 import 本子包的子模块。
"""

from __future__ import annotations
