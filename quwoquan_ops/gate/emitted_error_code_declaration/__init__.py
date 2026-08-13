"""反向错误码治理门禁实现包：实现发射了 stable code 但契约无声明位。

包内模块职责：

- ``constants``：扫描范围、发射形态清单与共享正则的唯一定义处。
- ``models``：Emission/声明/扫描结果 dataclass 与公共读文件工具。
- ``declarations``：两个声明源（errors.yaml 与 runtime_failure_codes.yaml）的解析。
- ``vocabulary``：runtime errors 的 module/kind/reason 常量与 helper 映射。
- ``resolution``：作用域内标识符解析与各语言生产源文件枚举。
- ``go_generated_scan``：Go 侧 generated factory / stable const 生产调用扫描。
- ``literal_scan``：Go/Dart/Swift stable-code 字面量发射扫描与注释剥离。
- ``app_scan``：App 生成错误 enum 成员流入 typed failure 的证据与 Python 字面量扫描。
- ``local_ctor_scan``：文件内局部错误构造器与 config module 注入的发射解析。
- ``scan``：发射扫描主流程与 NewCode / helper 站点分类。
- ``baseline``：迁移基线加载与校验。
- ``report``：evaluate 主流程、CLI 参数与 main 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from .baseline import Baseline, load_baseline  # noqa: E402
from .constants import (  # noqa: E402
    BASELINE_PATH,
    BASELINE_SCHEMA,
    CODE_PATTERN,
    EMISSION_FORMS,
    ROOT,
    RUNTIME_ERRORS_GO,
    RUNTIME_FAILURE_CODES_YAML,
    SERVICE_DIR,
)
from .declarations import (  # noqa: E402
    _iter_declaration_entries,
    declaration_sources,
    load_declarations,
    load_declared_codes,
)
from .models import (  # noqa: E402
    Emission,
    ErrorDeclaration,
    RuntimeErrorVocabulary,
    ScanResult,
    SOURCE_EVIDENCE_SURFACES,
    UnresolvedSite,
)
from .report import evaluate, main  # noqa: E402
from .scan import scan_emissions  # noqa: E402
from .vocabulary import load_runtime_vocabulary  # noqa: E402

__all__ = [
    "BASELINE_PATH",
    "BASELINE_SCHEMA",
    "Baseline",
    "CODE_PATTERN",
    "EMISSION_FORMS",
    "Emission",
    "ErrorDeclaration",
    "ROOT",
    "RUNTIME_ERRORS_GO",
    "RUNTIME_FAILURE_CODES_YAML",
    "RuntimeErrorVocabulary",
    "SERVICE_DIR",
    "SOURCE_EVIDENCE_SURFACES",
    "ScanResult",
    "UnresolvedSite",
    "_iter_declaration_entries",
    "declaration_sources",
    "evaluate",
    "load_baseline",
    "load_declarations",
    "load_declared_codes",
    "load_runtime_vocabulary",
    "main",
    "scan_emissions",
]
