#!/usr/bin/env python3
"""校验全域 commercial-ready operation 的对象级告警与仪表盘覆盖。

完整判定口径（domain-agnostic、对象分母、telemetry.metric 语义、`--write` 生成链）
见同目录实现包 ``object_alert_coverage/``，CLI 文档在 ``object_alert_coverage/cli.py``
的模块 docstring（`--help` 输出与其同源）。

本文件只是稳定 CLI 入口，并为既有消费者（`quwoquan_ops/gate/verify_metric_identity_homology.py`、
`quwoquan_ops/gate/verify_contract_alert_overlay.py`、local_contract 测试）re-export
包 API（含私有 ``_`` 符号）。
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

from object_alert_coverage import (  # noqa: E402
    ALERTS_ROOT,
    CONTRACT_GRAPH,
    COVERAGE_ALERTS_NAME,
    COVERAGE_DASHBOARD_NAME,
    COVERAGE_DASHBOARD_UID,
    DASHBOARDS_ROOT,
    DURATION_SOURCE_METRIC,
    GENERATED_HEADER,
    MONITORING_ROOT,
    PROMETHEUS_CONFIG,
    PROMETHEUS_COVERAGE_RULE,
    PROMETHEUS_RULE_GLOB,
    RECORDING_RULE_DIR_SUFFIX,
    REPO_ROOT,
    REQUEST_SOURCE_METRIC,
    SCRIPT_NAME,
    SERVICES_ROOT,
    ContractInputError,
    DomainReport,
    OBJECT_SURFACE_NONE,
    OBJECT_SURFACE_PENDING,
    OBJECT_SURFACE_READY,
    OBJECT_SURFACE_RUNTIME_ONLY,
    ObjectSurface,
    OperationContract,
    RuleExpression,
    VerificationReport,
    _GO_METRIC_OPTS,
    _LABEL_MATCHER_BLOCK,
    _PATH_PARAMETER_RE,
    _PROMQL_LABEL_RE,
    _PROMQL_SELECTOR_RE,
    _PY_METRIC_CTOR,
    _RECORD_METRIC_RE,
    _alert_name_domain,
    _decode_promql_string,
    _display_path,
    _domain_reports,
    _drift_issues,
    _escape_promql_regex_literal,
    _expression_covers,
    _go_opts_field,
    _group_name,
    _load_alert_expressions,
    _load_dashboard_expressions,
    _matcher_accepts,
    _number,
    _number_label,
    _parse_args,
    _print_report,
    _quoted,
    _record_metric_selectors,
    _recording_rule_files,
    _selector_labels,
    _threshold_label,
    _verify_consumer_selectors,
    _verify_metric_identifier_semantics,
    _verify_object_surfaces,
    _verify_prometheus_rule_files,
    _verify_recording_rules,
    _walk_dashboard_expressions,
    coverage_alert_document,
    coverage_dashboard_document,
    domain_ready_selector,
    generated_documents,
    load_domain_services,
    load_emitted_series,
    load_object_surfaces,
    load_operations,
    main,
    record_metric,
    record_metrics,
    recording_rule_documents,
    route_matcher,
    runtime_domain_services,
    source_expression,
    verify_coverage,
    write_generated_documents,
)

if __name__ == "__main__":
    raise SystemExit(main())
