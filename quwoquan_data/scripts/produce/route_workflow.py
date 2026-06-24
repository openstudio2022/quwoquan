"""通用线路类 evidence / writing-pack / review workflow（兼容门面）。

实现按高内聚职责拆在 route_core/route_analysis/route_assets/route_compose/route_review；
本文件保留历史 import 与 monkeypatch 入口。
"""
from __future__ import annotations

from produce.route_core import *  # noqa: F401,F403
from produce.route_analysis import *  # noqa: F401,F403
from produce.route_assets import *  # noqa: F401,F403
from produce.route_compose import *  # noqa: F401,F403
from produce.route_review import *  # noqa: F401,F403

__all__ = [name for name in globals() if not name.startswith("__")]
