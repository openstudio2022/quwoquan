"""端侧对象化架构门禁 v1 实现包：R1-R5 strict-zero 规则求值与 CLI。

包内模块职责：

- ``constants``：规则 ID、baseline 路径、组合根/词法常量的唯一定义处。
- ``dart_lexer``：最小 Dart 词法扫描、URI directive 解析与类型声明提取。
- ``attribution``：真相源载入、R1 顶层白名单与对象归属派生（经 object_path_map）。
- ``rules``：R2/R3 横切面反向 import、R4 跨对象 public seam、R5 runtime/di purity。
- ``report``：五条规则求值、strict-zero 违规汇总与 CLI ``main`` 入口。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_GATE_ROOT = Path(__file__).resolve().parents[1]
if str(_GATE_ROOT) not in sys.path:
    sys.path.insert(0, str(_GATE_ROOT))

from repository_root import repository_root  # noqa: E402

_REPO_ROOT = repository_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from .attribution import (  # noqa: E402
    AppObjectLibraryIdentity,
    AppSourceIndex,
    ResolvedDartUriDirective,
    _lib_relative,
    _percent_decode_uri,
    _resolve_import_uri,
    allowed_top_level_directories,
    derive_target_root,
    is_composition_root,
    l10n_top_level_segment,
    load_roster,
    scan_top_level_violations,
)
from .constants import (  # noqa: E402
    APPLICATION_PUBLIC_SEGMENT,
    BASELINE_PATH,
    CLOUD_CONTRACTS_URI_PREFIX,
    COMPOSITION_ROOT_TARGET_PREFIXES,
    DART_URI_DIRECTIVE_KINDS,
    DOMAIN_RULES,
    LIB_PREFIX,
    PACKAGE_URI_PREFIX,
    PERCENT_ESCAPE_RE,
    ROOT,
    RULE_CROSS_OBJECT_PRIVATE_IMPORT,
    RULE_ID,
    RULE_PHYSICAL_REVERSE_IMPORT,
    RULE_RUNTIME_DI_PRESENTATION_PURITY,
    RULE_TARGET_REVERSE_IMPORT,
    RULE_TOP_LEVEL,
    RUNTIME_DI_COPY_ARGUMENTS,
    RUNTIME_DI_ROOT,
    RUNTIME_DI_TEXT_WIDGETS,
    RUNTIME_DI_WIDGET_BASES,
    SHARED_RULES,
    TOP_LEVEL_ENTRY_RE,
)
from .dart_lexer import (  # noqa: E402
    DartUriDirective,
    _dart_source_tokens,
    _dart_type_declarations,
    parse_dart_uri_directives,
)
from .report import (  # noqa: E402
    _normalized,
    _rule_entries,
    evaluate,
    main,
    scoped_domains,
    summarize,
    verify_retired_baseline_absent,
    violation_entries,
)
from .rules import (  # noqa: E402
    is_cross_object_public_seam,
    scan_cross_object_private_import_violations,
    scan_reverse_import_violations,
    scan_runtime_di_presentation_purity_violations,
)

__all__ = [
    "APPLICATION_PUBLIC_SEGMENT",
    "AppObjectLibraryIdentity",
    "AppSourceIndex",
    "BASELINE_PATH",
    "CLOUD_CONTRACTS_URI_PREFIX",
    "COMPOSITION_ROOT_TARGET_PREFIXES",
    "DART_URI_DIRECTIVE_KINDS",
    "DOMAIN_RULES",
    "DartUriDirective",
    "LIB_PREFIX",
    "PACKAGE_URI_PREFIX",
    "PERCENT_ESCAPE_RE",
    "ROOT",
    "RULE_CROSS_OBJECT_PRIVATE_IMPORT",
    "RULE_ID",
    "RULE_PHYSICAL_REVERSE_IMPORT",
    "RULE_RUNTIME_DI_PRESENTATION_PURITY",
    "RULE_TARGET_REVERSE_IMPORT",
    "RULE_TOP_LEVEL",
    "RUNTIME_DI_COPY_ARGUMENTS",
    "RUNTIME_DI_ROOT",
    "RUNTIME_DI_TEXT_WIDGETS",
    "RUNTIME_DI_WIDGET_BASES",
    "ResolvedDartUriDirective",
    "SHARED_RULES",
    "TOP_LEVEL_ENTRY_RE",
    "allowed_top_level_directories",
    "derive_target_root",
    "evaluate",
    "is_composition_root",
    "is_cross_object_public_seam",
    "l10n_top_level_segment",
    "load_roster",
    "main",
    "parse_dart_uri_directives",
    "scan_cross_object_private_import_violations",
    "scan_reverse_import_violations",
    "scan_runtime_di_presentation_purity_violations",
    "scan_top_level_violations",
    "scoped_domains",
    "summarize",
    "verify_retired_baseline_absent",
    "violation_entries",
]
