#!/usr/bin/env python3
"""Compare a candidate ContractGraph with the last immutable Prod-full graph.

完整语义（model_version 单轨、hosted 基线回执、兼容窗口、quiesced 存储迁移）
见同目录实现包 ``domain_model_compatibility/``，CLI 文档与退出码在
``domain_model_compatibility/cli.py`` 的模块 docstring（`--help` 输出与其同源）。

本文件只是稳定 CLI 入口，并为既有消费者（local_contract 测试、
`quwoquan_service/Makefile` 的 `verify-domain-model-compatibility` 目标）
re-export 包 API（含私有 ``_`` 符号）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 仓库禁止源码树出现 __pycache__；入口可能被无 -B 的方式直接执行，
# 导入实现包前先关闭字节码写入。
sys.dont_write_bytecode = True

_PACKAGE_PARENT = str(Path(__file__).resolve().parent)
if _PACKAGE_PARENT not in sys.path:
    sys.path.insert(0, _PACKAGE_PARENT)

# local_contract 测试用 spec_from_file_location("domain_model_compatibility", 本文件)
# 加载入口，会把「入口自身」以实现包同名注册进 sys.modules；此时下方 import 会命中
# 正在初始化的自己而不是子包。检测到这种自注册就让位，让包名指向真正的实现包。
_registered = sys.modules.get("domain_model_compatibility")
if _registered is not None and getattr(_registered, "__file__", None) == __file__:
    del sys.modules["domain_model_compatibility"]

from domain_model_compatibility import (  # noqa: E402
    COMPATIBILITY_LEVELS,
    ChangeSet,
    FieldShape,
    GraphView,
    HOSTED_AUTHORITY,
    HOSTED_READBACK_SCHEMA,
    HOSTED_RECEIPT_SCHEMA,
    InputError,
    MIGRATION_SCHEMA,
    MODEL_VERSION_RE,
    ModelVersion,
    NULLABLE_CONSTRAINTS,
    RECEIPT_ID_RE,
    REPORT_SCHEMA,
    REQUIRED_CONSTRAINTS,
    SHA256_RE,
    WINDOW_SCHEMA,
    _authorization_signature,
    _by_object,
    _canonical_bytes,
    _column_required_without_default,
    _compare_columns,
    _compare_command_operation,
    _compare_field_shapes,
    _compare_indexes,
    _compare_query_operation,
    _compare_storage,
    _compare_storage_fields,
    _digest_value,
    _enum_catalog,
    _extract_graphql_operations,
    _field_map,
    _file_digest,
    _find_raw_field,
    _index_records,
    _index_signatures,
    _list,
    _load_migration_plan,
    _load_window,
    _mapping,
    _migration_valid,
    _operation_changes,
    _operation_fields,
    _read_json,
    _receipt_id,
    _reject_duplicate_keys,
    _storage_collections,
    _storage_tables,
    _string,
    _validate_baseline_receipt,
    _window_closed,
    _write_report,
    build_report,
    main,
    parse_args,
)

if __name__ == "__main__":
    raise SystemExit(main())
