"""no-fake 测试证据门禁实现包（由 ``verify_test_no_fake.py`` 薄入口消费）。

包内模块职责：

- ``patterns``：占位/skip/替身/环境命名正则与替身库名册的唯一定义处。
- ``lexer``：Go/Dart/TS/Python 最小词法与 import 边提取。
- ``support_edges``：替身识别与第一方 test support 依赖边递归判定。
- ``fixtures``：App 本地 fixture 的环境命名判定与字符串取值提取。
- ``snapshot``：仓库物理树一次性快照采集与文本缓存。
- ``report``：失败聚合、各类源码校验与 CLI main 入口。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 同目录的 test_directory_layout_lib 是共享真相源；包内模块以顶层名 import 它，
# 与既有 scaffold 脚本形态保持一致，因此先把 scaffold 目录挂到 sys.path。
_SCAFFOLD_ROOT = Path(__file__).resolve().parents[1]
if str(_SCAFFOLD_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCAFFOLD_ROOT))

from test_directory_layout_lib import (  # noqa: E402
    ROOT,
    contains_generated_bridge_marker,
    iter_canonical_files,
)

from .fixtures import (  # noqa: E402
    _environment_class_names,
    _environment_data_names_for_file,
    _source_string_literals,
    _structured_scalar_strings,
    app_local_fixture_environment_names,
    app_local_fixture_environment_path_names,
    is_app_local_fixture_source,
    is_app_user_acceptance_source,
)
from .lexer import (  # noqa: E402
    _c_style_tokens,
    _dart_directive_modules,
    _dart_named_directive_values,
    _go_imported_modules,
    _lexical_code_text,
    _python_imported_modules,
    _python_tree,
    authored_support_modules,
    imported_modules,
)
from .patterns import (  # noqa: E402
    _SUBSTITUTE_INFRA_SUFFIX,
    DART_TEST_RE,
    ENVIRONMENT_CLASS_NAME_RE,
    ENVIRONMENT_DATA_NAME_RE,
    ENVIRONMENT_PATH_SEGMENT_RE,
    FAKE_BUILD_TAG_RE,
    FIRST_PARTY_DOUBLE_PATH_RE,
    FIRST_PARTY_DOUBLE_TYPE_RE,
    GO_TEST_ENTRYPOINT_RE,
    PLACEHOLDER_PATTERNS,
    PYTHON_TEST_RE,
    SKIP_PATTERNS,
    SUBSTITUTE_CALL_NAME_RE,
    SUBSTITUTE_COMPOSITE_NAME_RE,
    SUBSTITUTE_LIBRARY_IMPORTS,
)
from .report import (  # noqa: E402
    Failures,
    _app_user_acceptance_single_source_markers,
    app_user_acceptance_local_injection_markers,
    main,
    verify_all_test_sources,
    verify_app_local_fixture_naming,
    verify_canonical_files,
    verify_test_artifacts,
)
from .snapshot import (  # noqa: E402
    EXCLUDED_SCAN_DIRS,
    SNAPSHOT_TEXT_SUFFIXES,
    _read_text,
    _snapshot_needs_text,
    scan_repository_files,
    scan_repository_snapshot,
)
from .support_edges import (  # noqa: E402
    _dart_library_source_texts,
    _declared_double_types,
    _first_party_support_targets,
    _is_test_support_path,
    _snapshot_directories,
    _snapshot_files_by_parent,
    _snapshot_path_exists,
    _support_source_files,
    _support_target_contains_substitute,
    first_party_substitute_support_imports,
    first_party_support_imports,
    lexical_memory_modes,
    lexical_substitute_names,
    substitute_library_imports,
)

#: 覆盖单文件时代的全部模块级符号（含测试消费的下划线私有名），
#: 供薄入口 ``from ... import *`` 一次性 re-export。
__all__ = [
    "DART_TEST_RE",
    "ENVIRONMENT_CLASS_NAME_RE",
    "ENVIRONMENT_DATA_NAME_RE",
    "ENVIRONMENT_PATH_SEGMENT_RE",
    "EXCLUDED_SCAN_DIRS",
    "FAKE_BUILD_TAG_RE",
    "FIRST_PARTY_DOUBLE_PATH_RE",
    "FIRST_PARTY_DOUBLE_TYPE_RE",
    "Failures",
    "GO_TEST_ENTRYPOINT_RE",
    "PLACEHOLDER_PATTERNS",
    "PYTHON_TEST_RE",
    "ROOT",
    "SKIP_PATTERNS",
    "SNAPSHOT_TEXT_SUFFIXES",
    "SUBSTITUTE_CALL_NAME_RE",
    "SUBSTITUTE_COMPOSITE_NAME_RE",
    "SUBSTITUTE_LIBRARY_IMPORTS",
    "_SUBSTITUTE_INFRA_SUFFIX",
    "_app_user_acceptance_single_source_markers",
    "_c_style_tokens",
    "_dart_directive_modules",
    "_dart_library_source_texts",
    "_dart_named_directive_values",
    "_declared_double_types",
    "_environment_class_names",
    "_environment_data_names_for_file",
    "_first_party_support_targets",
    "_go_imported_modules",
    "_is_test_support_path",
    "_lexical_code_text",
    "_python_imported_modules",
    "_python_tree",
    "_read_text",
    "_snapshot_directories",
    "_snapshot_files_by_parent",
    "_snapshot_needs_text",
    "_snapshot_path_exists",
    "_source_string_literals",
    "_structured_scalar_strings",
    "_support_source_files",
    "_support_target_contains_substitute",
    "app_local_fixture_environment_names",
    "app_local_fixture_environment_path_names",
    "app_user_acceptance_local_injection_markers",
    "authored_support_modules",
    "contains_generated_bridge_marker",
    "first_party_substitute_support_imports",
    "first_party_support_imports",
    "imported_modules",
    "is_app_local_fixture_source",
    "is_app_user_acceptance_source",
    "iter_canonical_files",
    "lexical_memory_modes",
    "lexical_substitute_names",
    "main",
    "scan_repository_files",
    "scan_repository_snapshot",
    "substitute_library_imports",
    "verify_all_test_sources",
    "verify_app_local_fixture_naming",
    "verify_canonical_files",
    "verify_test_artifacts",
]
