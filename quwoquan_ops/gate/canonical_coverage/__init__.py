"""唯一 canonical coverage rule 的实现包（按 ContractGraph 对象身份计量）。

规则语义、维度定义与用法见薄入口 ``verify_canonical_coverage.py`` 的模块
docstring；本包是它的单轨实现。包内模块职责：

- ``constants``：路径、单元前缀、policy、receipt 字段、正则与异常的唯一定义处。
- ``units``：单元发现——名册全部从 ContractGraph 派生，含采集目标折叠与 scope。
- ``parsing``：lcov 汇总/明细、Go coverprofile 与 Python trace 解析。
- ``provenance``：产物路径、输入闭包、各摘要与 collection identity。
- ``receipts``：原子落盘与 provenance receipt 写入/校验。
- ``collection``：端侧分片 flutter test、Python trace 与 Go coverprofile 采集。
- ``attribution``：端云 production source 归属与逐单元计量。
- ``baseline``：canonical baseline 的加载、校验与整体写入。
- ``report``：阈值、基线比对、汇总输出、argparse 与 ``main``。

本包命名空间等价于拆分前的单文件模块命名空间：薄入口在被 import 时把自己在
``sys.modules`` 中指向本包，包内实现对可被测试 monkeypatch 的符号一律经本包
命名空间做调用期解析，因此对入口模块属性的 monkeypatch 与拆分前语义一致。
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

sys.dont_write_bytecode = True

from quwoquan_ops.gate import object_path_map as opm  # noqa: E402
from quwoquan_ops.gate import verify_app_architecture as vaa  # noqa: E402

from .constants import (  # noqa: E402
    APP_COLLECTION_TARGET,
    APP_CROSS_CUTTING_UNIT_PREFIX,
    APP_ROOT,
    APP_SHARD_DIRECTORY_NAME,
    APP_SHARD_MAX_TEST_FILES,
    APP_SHARD_STATE_SCHEMA,
    APP_TEST_FILE_SUFFIX,
    APP_TEST_TARGET,
    APP_UNIT_PREFIX,
    ARTIFACT_RECEIPT_DIGEST_FIELDS,
    ARTIFACT_RECEIPT_FIELDS,
    ARTIFACT_RECEIPT_SCHEMA,
    BASELINE_PATH,
    BASELINE_SCHEMA,
    CANONICAL_BASELINE_GOVERNANCE,
    CANONICAL_POLICY,
    CLOUD_CROSS_CUTTING_ROOTS,
    CLOUD_CROSS_CUTTING_UNIT_PREFIX,
    CLOUD_UNIT_PREFIX,
    COVERAGE_CACHE_DIR,
    GIT_OBJECT_RE,
    KIND_CLOUD_STATEMENT,
    KIND_FLUTTER_LCOV,
    METRIC_STATUS_UNMEASURED,
    METRICS_BY_KIND,
    PYTHON_COVERAGE_TOOLCHAIN_LOCK,
    PYTHON_COVERAGE_TOOLCHAIN_MARKER,
    PYTHON_EXACT_REQUIREMENT_RE,
    PYTHON_MANAGED_ENV_RELATIVE,
    PYTHON_SERVICE_TEST_TARGET,
    PYTHON_TRACE_ARTIFACT_SCHEMA,
    PYTHON_TRACE_SOURCE_ROOTS,
    RETIRED_BASELINE_PATH,
    ROOT,
    RULE_ID,
    SERVICE_COVERPKG_PATTERNS,
    SERVICE_EXCLUDED_PACKAGE_MARKER,
    SERVICE_GO_TEST_PACKAGE_PARALLELISM,
    SERVICE_PACKAGE_PATTERNS,
    SERVICE_ROOT,
    SHA256_DIGEST_RE,
    SHARED_RUNTIME_COLLECTION_TARGET,
    SHARED_RUNTIME_COVERPKG_PATTERNS,
    SHARED_RUNTIME_PACKAGE_PATTERNS,
    CoverageError,
    RedTestRun,
    _display,
    _tail,
)
from .units import (  # noqa: E402
    _collection_target_language,
    _has_go_sources,
    _has_python_sources,
    _roster,
    _service_target_for_segment,
    app_cross_cutting_unit,
    app_object_unit,
    app_units,
    cloud_collection_targets,
    cloud_collection_targets_for_unit,
    cloud_cross_cutting_unit,
    cloud_object_unit,
    collection_targets,
    discover_app_units,
    discover_cloud_units,
    discover_units,
    expected_app_capability_units,
    go_collection_targets,
    python_collection_targets,
    unit_bucket,
    unit_kind,
    unit_scope,
)
from .parsing import (  # noqa: E402
    GO_BLOCK_RE,
    LCOV_BRANCH_DETAIL_RE,
    LCOV_BRANCH_SUMMARY_RE,
    LCOV_LINE_DETAIL_RE,
    LCOV_LINE_SUMMARY_RE,
    _assert_lcov_summaries_match_details,
    _lcov_branch_sort_key,
    _lcov_file_record,
    _lcov_identifier_sort_key,
    _merge_branch_taken,
    iter_lcov_lines,
    merge_lcov_file_record,
    merge_lcov_records,
    parse_go_coverprofile,
    parse_go_coverprofile_files,
    parse_lcov,
    parse_lcov_records,
    parse_python_trace_files,
    render_lcov,
)
from .app_runtime import (  # noqa: E402
    APP_COVERAGE_CLEARED_ENV_KEYS,
    APP_COVERAGE_CONCURRENCY,
    APP_COVERAGE_LAUNCH_POLICY,
    APP_COVERAGE_MAX_ATTEMPTS,
    APP_COVERAGE_RUNTIME_ENV,
    APP_COVERAGE_SERIAL_CONCURRENCY,
    APP_COVERAGE_TIMEOUT_SECONDS,
    APP_FLUTTER_TEST_RUNNER,
    APP_RUNTIME_DEFINE_RESOLVER,
    APP_TEST_SELECTION_POLICY,
    app_coverage_policy_identity,
    app_runtime_define_command,
    canonical_app_coverage_environment,
    guarded_app_coverage_command,
    resolved_app_runtime_defines,
    serial_app_test_files,
)
from .provenance import (  # noqa: E402
    LOCAL_DEPENDENCY_EXCLUDED_DIRECTORY_NAMES,
    PYTHON_TOOLCHAIN_PROBE,
    _app_collection_inputs,
    _app_local_path_dependency_roots,
    _app_source_closure_files,
    _attribution_inputs,
    _canonical_distribution_name,
    _canonical_json_digest,
    _collection_config_inputs,
    _collection_scope_digest,
    _git_head_identity,
    _flutter_toolchain_identity,
    _identity_command,
    _parse_python_coverage_toolchain_lock,
    _provenance_tree_files,
    _python_collection_executable,
    _python_toolchain_state,
    _required_safe_files,
    _service_collection_inputs,
    _sha256_bytes,
    _sha256_file,
    _toolchain_digest,
    _tree_digest,
    artifact_path,
    artifact_receipt_path,
    current_collection_identity,
)
from .receipts import (  # noqa: E402
    _validate_receipt_payload,
    _write_artifact_receipt,
    _write_json_atomic,
    _write_text_atomic,
    receipt_digest,
    validate_artifact_receipt,
)
from .collection import (  # noqa: E402
    PYTHON_TRACE_RUNNER,
    _app_shard_artifact_paths,
    _reusable_shard_lcov,
    _run,
    _run_app_shard,
    app_shard_directory,
    app_shard_plan,
    app_test_files,
    collect,
    collect_app,
    collect_python_service,
    collect_service,
    default_app_shard_count,
)
from .attribution import (  # noqa: E402
    LIB_PREFIX,
    AppAttribution,
    CloudAttribution,
    _measure_app_unit,
    _measure_cloud_unit,
    _metric,
    _read_artifact,
    _require_app_unit_measured,
    measure,
    percent,
)
from .baseline import (  # noqa: E402
    BASELINE_GOVERNANCE_FIELDS,
    BASELINE_TOP_LEVEL_FIELDS,
    BASELINE_UNIT_FIELDS,
    POLICY_NUMERIC_KEYS,
    POLICY_REASON_KEYS,
    _validate_baseline_metric,
    _validate_baseline_receipt_registry,
    _validate_unit_receipt_refs,
    load_baseline,
    unit_entry,
    write_baseline,
)
from .report import (  # noqa: E402
    _diff_metric,
    build_parser,
    diff,
    known_units_for,
    main,
    resolve_units,
    summarize,
    thresholds,
)
