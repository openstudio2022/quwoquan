"""启动环境矩阵门禁实现包。

唯一稳定入口是
``quwoquan_app/scripts/runtime/platform/verify_startup_environment_matrix.py``
（薄壳 re-export）；本包按职责切分：

- ``context``：环境/设备矩阵常量、runtime package 必需字段与 schema 标识。
- ``package_probe``：runtime package、iOS 编译输入与 launcher handoff 探针。
- ``evidence_validation``：runtime / readback / observability 证据校验。
- ``reporting``：CaseResult 汇总、状态判定与报告写出。
- ``cli``：主流程 ``main``。
"""
from __future__ import annotations

from . import cli  # noqa: F401
from .cli import main  # noqa: F401
from .context import (  # noqa: F401
    APP_DIR,
    DEVICE_PROFILES,
    ENVIRONMENTS,
    OBSERVABILITY_EVIDENCE_SCHEMA,
    READBACK_EVIDENCE_SCHEMA,
    REQUIRED_RUNTIME_FIELDS,
    RUNTIME_CASES,
    RUNTIME_EVIDENCE_SCHEMA,
    RUNTIME_TARGETS,
    SHA256_PATTERN,
    SPEC_REFS,
)
from .evidence_validation import (  # noqa: F401
    _missing_spec_refs,
    _validate_observability_evidence,
    _validate_readback_evidence,
    _validate_runtime_evidence,
    _validate_runtime_sample,
)
from .package_probe import (  # noqa: F401
    _ios_compile_defines,
    _launcher_handoff,
    _run,
    _runtime_package,
    _validate_compile_defines,
    _validate_runtime_package,
)
from .reporting import (  # noqa: F401
    _case,
    _case_counts,
    _report_status,
    _write_report,
)
