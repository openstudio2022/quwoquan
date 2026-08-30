#!/usr/bin/env python3
"""反向错误码治理门禁：实现发射了 stable code，但两个声明源都没有声明位。

维度语义、声明源、发射形态与基线纪律的完整说明见
``emitted_error_code_declaration/report.py`` 的模块 docstring（即 CLI --help 文案）。

实现单轨落在 ``emitted_error_code_declaration/`` 包内；本文件只是稳定 CLI 入口，
并为既有消费者 re-export 包 API。

用法：
  python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py
  python3 quwoquan_ops/gate/verify_emitted_error_code_declaration.py --report
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from quwoquan_ops.gate.emitted_error_code_declaration import (  # noqa: E402
    BASELINE_PATH,
    BASELINE_SCHEMA,
    Baseline,
    CODE_PATTERN,
    EMISSION_FORMS,
    Emission,
    ErrorDeclaration,
    ROOT,
    RUNTIME_ERRORS_GO,
    RUNTIME_FAILURE_CODES_YAML,
    RuntimeErrorVocabulary,
    SERVICE_DIR,
    SOURCE_EVIDENCE_SURFACES,
    ScanResult,
    UnresolvedSite,
    _iter_declaration_entries,
    declaration_sources,
    evaluate,
    load_baseline,
    load_declarations,
    load_declared_codes,
    load_runtime_vocabulary,
    main,
    scan_emissions,
)

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


if __name__ == "__main__":
    sys.exit(main())
