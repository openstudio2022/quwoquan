"""三层测试目录门禁实现包（由 ``verify_test_directory_layout.py`` 薄入口消费）。

包内模块职责：

- ``constants``：目录闭集、后缀映射与命名正则（含 Data local_contract 实时派生）。
- ``common``：失败聚合与各域共用的遍历/后缀/桥接标记校验原语。
- ``dart_lexer``：最小 Dart 词法与 library/part 闭包解析。
- ``app_support``：端侧 support owner、UAT 依赖真实度与跨对象 Journey 边界。
- ``app_layout``：端侧对象名册派生、残留棘轮与 verify_app 编排。
- ``data``：Data 三层目录与命名校验。
- ``ops``：Ops concern 分域、pytest 命名与 conformance 声明矩阵。
- ``service``：Service/control-plane/runtime 与横切区校验。
- ``report``：CLI 参数处理与全域编排 main 入口。
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
    APP_PACKAGES_ROOT,
    APP_ROOT,
    CONTROL_PLANE_ROOT,
    DATA_ROOT,
    LAYERS,
    OPS_ACCEPTANCE_ROOT,
    OPS_TEST_ROOT,
    ROOT,
    RUNTIME_ROOT,
    RUNTIME_TEST_ROOT,
    SERVICE_DOMAIN_ROOT,
    SERVICE_ROOT,
    contains_generated_bridge_marker,
    evidence_path_is_canonical,
    iter_canonical_files,
)

sys.dont_write_bytecode = True

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.gate import object_path_map as opm  # noqa: E402

from .app_layout import (  # noqa: E402
    allowed_app_layer_dirs,
    app_object_roster,
    app_object_test_dirs,
    require_app_object_test_path,
    verify_app,
    verify_app_object_source_files,
    verify_app_patrol_runner_root,
    verify_app_python_evidence_boundaries,
    verify_app_unmigrated_residue,
)
from .app_support import (  # noqa: E402
    _app_local_journey_dart_boundary,
    _dart_imported_support_targets,
    _dart_non_directive_identifiers,
    _dart_tokens_have_local_boundary,
    _dart_typed_double_declarations,
    _python_local_journey_has_boundary,
    _relative_support_target,
    app_local_journey_has_test_boundary,
    app_patrol_user_acceptance_targets,
    app_support_authored_edge_is_forbidden,
    app_support_exports_are_forbidden,
    app_support_path_identity,
    verify_app_journeys,
    verify_app_support_layout,
    verify_app_user_acceptance_support_edges,
)
from .common import (  # noqa: E402
    Failures,
    ensure_allowed_children,
    expected_suffix,
    iter_app_test_files,
    iter_test_files,
    rel,
    require_layer_suffix,
    verify_no_generated_bridges,
    verify_support_has_no_tests,
)
from .constants import (  # noqa: E402
    APP_CROSS_OBJECT_JOURNEY_ROOT,
    APP_JOURNEY_DIR_RE,
    APP_PATROL_IMPORT_URI,
    APP_PATROL_RUNNER_FILES,
    APP_PATROL_RUNNER_ROOT,
    APP_TEST_ROOT_DIRS,
    APP_UNMIGRATED_LAYER_DIRS,
    DATA_LAYER_DIRS,
    DATA_TEST_NAME_RE,
    DATA_TEST_ROOT_DIRS,
    IGNORED_TEST_CACHE_DIRS,
    OPS_ACCEPTANCE_DIRS,
    OPS_TEST_ROOT_DIRS,
    SERVICE_TEST_DIRS,
    TEST_SUFFIX_BY_LAYER,
    TEST_SUPPORT_BARREL_NAME_RE,
    _DART_URI_SCHEME_RE,
    _SERVICE_DOMAIN_RE,
    _data_local_contract_layer_dirs,
)
from .dart_lexer import (  # noqa: E402
    _dart_directive_uris,
    _dart_export_uris,
    _dart_import_uris,
    _dart_library_names,
    _dart_library_sources,
    _dart_part_of_targets,
    _dart_part_uris,
    _dart_source_tokens,
)
from .data import verify_data  # noqa: E402
from .ops import (  # noqa: E402
    OPS_CONFORMANCE_DECLARATIONS_PER_LAYER_CEILING,
    OPS_LOCAL_CONTRACT_CONCERN_DIRS,
    _CONFORMANCE_HEADER_RE,
    _CONFORMANCE_LAYER_ROOTS,
    _conformance_declaration_identity,
    require_ops_pytest_prefix,
    verify_ops,
    verify_ops_conformance_declaration_matrix,
    verify_ops_local_contract_concerns,
    verify_ops_local_contract_python_roles,
)
from .report import main  # noqa: E402
from .service import (  # noqa: E402
    require_cross_cutting_go_layer_suffix,
    require_service_object_test_path,
    service_object_test_roster,
    verify_all_canonical_files_recognized,
    verify_runtime,
    verify_runtime_tests_dir,
    verify_service,
    verify_service_domain_cross_cutting,
    verify_service_tests_dir,
)

#: 覆盖单文件时代的全部模块级符号（含测试消费的下划线私有名），
#: 供薄入口 ``from ... import *`` 一次性 re-export。
__all__ = [
    "APP_CROSS_OBJECT_JOURNEY_ROOT",
    "APP_JOURNEY_DIR_RE",
    "APP_PACKAGES_ROOT",
    "APP_PATROL_IMPORT_URI",
    "APP_PATROL_RUNNER_FILES",
    "APP_PATROL_RUNNER_ROOT",
    "APP_ROOT",
    "APP_TEST_ROOT_DIRS",
    "APP_UNMIGRATED_LAYER_DIRS",
    "CONTROL_PLANE_ROOT",
    "DATA_LAYER_DIRS",
    "DATA_ROOT",
    "DATA_TEST_NAME_RE",
    "DATA_TEST_ROOT_DIRS",
    "Failures",
    "IGNORED_TEST_CACHE_DIRS",
    "LAYERS",
    "OPS_ACCEPTANCE_DIRS",
    "OPS_ACCEPTANCE_ROOT",
    "OPS_CONFORMANCE_DECLARATIONS_PER_LAYER_CEILING",
    "OPS_LOCAL_CONTRACT_CONCERN_DIRS",
    "OPS_TEST_ROOT",
    "OPS_TEST_ROOT_DIRS",
    "ROOT",
    "RUNTIME_ROOT",
    "RUNTIME_TEST_ROOT",
    "SERVICE_DOMAIN_ROOT",
    "SERVICE_ROOT",
    "SERVICE_TEST_DIRS",
    "TEST_SUFFIX_BY_LAYER",
    "TEST_SUPPORT_BARREL_NAME_RE",
    "_CONFORMANCE_HEADER_RE",
    "_CONFORMANCE_LAYER_ROOTS",
    "_DART_URI_SCHEME_RE",
    "_SERVICE_DOMAIN_RE",
    "_app_local_journey_dart_boundary",
    "_conformance_declaration_identity",
    "_dart_directive_uris",
    "_dart_export_uris",
    "_dart_import_uris",
    "_dart_imported_support_targets",
    "_dart_library_names",
    "_dart_library_sources",
    "_dart_non_directive_identifiers",
    "_dart_part_of_targets",
    "_dart_part_uris",
    "_dart_source_tokens",
    "_dart_tokens_have_local_boundary",
    "_dart_typed_double_declarations",
    "_data_local_contract_layer_dirs",
    "_python_local_journey_has_boundary",
    "_relative_support_target",
    "allowed_app_layer_dirs",
    "app_local_journey_has_test_boundary",
    "app_object_roster",
    "app_object_test_dirs",
    "app_patrol_user_acceptance_targets",
    "app_support_authored_edge_is_forbidden",
    "app_support_exports_are_forbidden",
    "app_support_path_identity",
    "contains_generated_bridge_marker",
    "ensure_allowed_children",
    "evidence_path_is_canonical",
    "expected_suffix",
    "iter_app_test_files",
    "iter_canonical_files",
    "iter_test_files",
    "main",
    "opm",
    "rel",
    "require_app_object_test_path",
    "require_cross_cutting_go_layer_suffix",
    "require_layer_suffix",
    "require_ops_pytest_prefix",
    "require_service_object_test_path",
    "service_object_test_roster",
    "verify_all_canonical_files_recognized",
    "verify_app",
    "verify_app_journeys",
    "verify_app_object_source_files",
    "verify_app_patrol_runner_root",
    "verify_app_python_evidence_boundaries",
    "verify_app_support_layout",
    "verify_app_unmigrated_residue",
    "verify_app_user_acceptance_support_edges",
    "verify_data",
    "verify_no_generated_bridges",
    "verify_ops",
    "verify_ops_conformance_declaration_matrix",
    "verify_ops_local_contract_concerns",
    "verify_ops_local_contract_python_roles",
    "verify_runtime",
    "verify_runtime_tests_dir",
    "verify_service",
    "verify_service_domain_cross_cutting",
    "verify_service_tests_dir",
    "verify_support_has_no_tests",
]
