"""全 Python 治理边界派生包：owner、角色、结构、行数预算与卫生违规。

包内模块职责：

- ``constants``：扫描范围、目录闭集与命名正则的唯一定义处。
- ``models``：Issue/Warning/记录 dataclass 与路径归一。
- ``inventory``：物理树枚举与 Python 治理边界分类。
- ``references``：入口引用图与脚本间 import 图。
- ``roles``：脚本角色派生与 orphan 候选判定。
- ``hygiene``：命名、缓存/临时文件卫生与无 owner tool。
- ``bytecode_guard``：可直接调用入口的字节码抑制守卫（防源码树 pyc 回潮）。
- ``structure``：App/Service/Ops/Data 目录结构规则。
- ``line_budget``：Python 文件行数硬顶（Data scripts 由其自有 600 行门负责）。
- ``report``：报告组装、CLI 参数与 main 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

_GATE_ROOT = Path(__file__).resolve().parents[1]
if str(_GATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_GATE_ROOT))

from repository_root import repository_root  # noqa: E402

_REPO_ROOT = repository_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from .report import derive_report, main, parse_args  # noqa: E402

__all__ = ["derive_report", "main", "parse_args"]
