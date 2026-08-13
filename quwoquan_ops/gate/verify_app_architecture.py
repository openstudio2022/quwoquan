#!/usr/bin/env python3
"""端侧对象化架构门禁 v1，云侧 `verify_service_architecture.py` 的对等物。

目标形态（与云侧 DDD 同构，层名等价见
`object_path_map.APP_TO_CLOUD_LAYER_EQUIVALENCE`）：

    quwoquan_app/lib/
    ├─ service/<service>/<context>/<object>/{domain,application,adapters,presentation}/
    ├─ runtime/        # 唯一公共 runtime 横切面（transport/codec/errors/config/auth/
    │                  # di/observability/platform/shell）
    ├─ design_system/  # 唯一设计系统横切面
    └─ l10n/           # flutter gen-l10n 的 arb 根，取自 quwoquan_app/l10n.yaml

三个非 service 根都是 `object_path_map.APP_CROSS_CUTTING_ROOTS` 的成员：顶层白名单
与派生器的横切根是同一份集合，不存在「合法顶层但派生器认为待搬迁」的第三类目录。

v1 校验五条规则：

R1 `app_lib_top_level`
    `lib/` 顶层只允许 `service/` 容器、`APP_CROSS_CUTTING_ROOTS` 的三个横切根
    （`runtime/`、`design_system/`、l10n 根），以及入口文件 `main*.dart`。

R2 `cross_cutting_target_reverse_import`
    横切面禁止依赖业务对象（在**目标空间**求值）。

R3 `cross_cutting_physical_reverse_import`
    同一方向性约束在**物理空间**的完整表达。

R4 `cross_object_private_import`
    两个不同业务对象之间的 import/export 只能指向目标对象显式的
    `application/public/**` seam；DEC-019 的绝对零容忍规则。

R5 `runtime_di_presentation_purity`
    `runtime/di/**` 只承担 provider、factory、typed `WidgetBuilder` 与 composition
    装配；禁止在组合根定义 Widget 类、业务文案与业务状态。

组合根例外（与云侧 `cmd/` 同义，不是逃逸）：`runtime/di/**` 与顶层入口
`main*.dart` 是装配点，不纳入 R2/R3 的横切面禁令范围。除此之外没有任何豁免。

strict-zero 语义：R1-R5 任一实测条目都直接 BLOCK。迁移期 baseline 已退休。

实现单轨落在 ``app_architecture/`` 包内；本文件只是稳定 CLI 入口，
并为既有消费者 re-export 包 API。

用法
----
    python3 quwoquan_ops/gate/verify_app_architecture.py
    python3 quwoquan_ops/gate/verify_app_architecture.py --domain content
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_BOOTSTRAP = next(
    path
    for path in Path(__file__).resolve().parents
    if (path / "repository_root.py").is_file()
)
if str(_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP))

from repository_root import repository_root  # noqa: E402

DEFAULT_ROOT = repository_root()
if str(DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT))

from quwoquan_ops.gate.app_architecture import (  # noqa: E402
    APPLICATION_PUBLIC_SEGMENT,
    AppObjectLibraryIdentity,
    AppSourceIndex,
    BASELINE_PATH,
    CLOUD_CONTRACTS_URI_PREFIX,
    COMPOSITION_ROOT_TARGET_PREFIXES,
    DART_URI_DIRECTIVE_KINDS,
    DOMAIN_RULES,
    DartUriDirective,
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
    ResolvedDartUriDirective,
    SHARED_RULES,
    TOP_LEVEL_ENTRY_RE,
    _dart_source_tokens,
    _dart_type_declarations,
    _lib_relative,
    _normalized,
    _percent_decode_uri,
    _resolve_import_uri,
    _rule_entries,
    allowed_top_level_directories,
    derive_target_root,
    evaluate,
    is_composition_root,
    is_cross_object_public_seam,
    l10n_top_level_segment,
    load_roster,
    main,
    parse_dart_uri_directives,
    scan_cross_object_private_import_violations,
    scan_reverse_import_violations,
    scan_runtime_di_presentation_purity_violations,
    scan_top_level_violations,
    scoped_domains,
    summarize,
    verify_retired_baseline_absent,
    violation_entries,
)

__all__ = [
    "APPLICATION_PUBLIC_SEGMENT",
    "AppObjectLibraryIdentity",
    "AppSourceIndex",
    "BASELINE_PATH",
    "CLOUD_CONTRACTS_URI_PREFIX",
    "COMPOSITION_ROOT_TARGET_PREFIXES",
    "DART_URI_DIRECTIVE_KINDS",
    "DEFAULT_ROOT",
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


if __name__ == "__main__":
    raise SystemExit(main())
