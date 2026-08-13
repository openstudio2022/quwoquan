"""verify_domain_model_compatibility 的实现包：re-export 全部原模块符号。

薄入口 ``verify_domain_model_compatibility.py`` 与 local_contract 测试都从这里
取符号；CLI 文档与退出码语义见 ``cli`` 模块 docstring。
"""

from .primitives import (
    COMPATIBILITY_LEVELS,
    HOSTED_AUTHORITY,
    HOSTED_READBACK_SCHEMA,
    HOSTED_RECEIPT_SCHEMA,
    InputError,
    MIGRATION_SCHEMA,
    MODEL_VERSION_RE,
    NULLABLE_CONSTRAINTS,
    RECEIPT_ID_RE,
    REPORT_SCHEMA,
    REQUIRED_CONSTRAINTS,
    SHA256_RE,
    WINDOW_SCHEMA,
    _canonical_bytes,
    _digest_value,
    _file_digest,
    _list,
    _mapping,
    _read_json,
    _receipt_id,
    _reject_duplicate_keys,
    _string,
)
from .graph_view import (
    ChangeSet,
    FieldShape,
    GraphView,
    ModelVersion,
    _enum_catalog,
    _extract_graphql_operations,
    _field_map,
    _find_raw_field,
    _index_records,
    _index_signatures,
    _storage_collections,
    _storage_tables,
)
from .comparison import (
    _authorization_signature,
    _column_required_without_default,
    _compare_columns,
    _compare_command_operation,
    _compare_field_shapes,
    _compare_indexes,
    _compare_query_operation,
    _compare_storage,
    _compare_storage_fields,
    _operation_fields,
)
from .evidence import (
    _load_migration_plan,
    _load_window,
    _migration_valid,
    _validate_baseline_receipt,
    _window_closed,
)
from .report import (
    _by_object,
    _operation_changes,
    _write_report,
    build_report,
)
from .cli import main, parse_args

__all__ = [
    "COMPATIBILITY_LEVELS",
    "ChangeSet",
    "FieldShape",
    "GraphView",
    "HOSTED_AUTHORITY",
    "HOSTED_READBACK_SCHEMA",
    "HOSTED_RECEIPT_SCHEMA",
    "InputError",
    "MIGRATION_SCHEMA",
    "MODEL_VERSION_RE",
    "ModelVersion",
    "NULLABLE_CONSTRAINTS",
    "RECEIPT_ID_RE",
    "REPORT_SCHEMA",
    "REQUIRED_CONSTRAINTS",
    "SHA256_RE",
    "WINDOW_SCHEMA",
    "build_report",
    "main",
    "parse_args",
]
