"""对象级告警覆盖门禁的仓库根引导、路径常量与共享正则。

本模块必须最先被包内其它模块 import：它负责把仓库根挂进 ``sys.path``，
供 ``quwoquan_ops`` 侧共享库 import 使用。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_BOOTSTRAP = next(
    path
    for path in Path(__file__).resolve().parents
    if (path / "repository_root.py").is_file()
)
sys.path.insert(0, str(_BOOTSTRAP))

from repository_root import repository_root  # noqa: E402

REPO_ROOT = repository_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTRACT_GRAPH = REPO_ROOT / "quwoquan_service/generated/contract_graph.json"
SERVICES_ROOT = REPO_ROOT / "quwoquan_service/services"
MONITORING_ROOT = REPO_ROOT / "quwoquan_ops/observability/monitoring"
ALERTS_ROOT = MONITORING_ROOT / "alerts"
DASHBOARDS_ROOT = MONITORING_ROOT / "dashboards"
PROMETHEUS_CONFIG = MONITORING_ROOT / "prometheus.yml"

# 生成产物 header 与漂移提示引用的是稳定 CLI 入口文件名；实现搬进包内后
# 该名字必须与同目录薄入口 ``verify_object_alert_coverage.py`` 保持同步，
# 不能改用本模块自身的 ``__file__``。
SCRIPT_NAME = "verify_object_alert_coverage.py"
RECORDING_RULE_DIR_SUFFIX = "_contract"
COVERAGE_ALERTS_NAME = "contract_object_coverage.yaml"
COVERAGE_DASHBOARD_NAME = "l2_contract_object_coverage.json"
COVERAGE_DASHBOARD_UID = "qwq-l2-contract-object-coverage"
PROMETHEUS_RULE_GLOB = "/etc/prometheus/rules/*_contract/*.yaml"
PROMETHEUS_COVERAGE_RULE = f"/etc/prometheus/rules/{COVERAGE_ALERTS_NAME}"

REQUEST_SOURCE_METRIC = "http_server_requests_total"
DURATION_SOURCE_METRIC = "http_server_duration_seconds_bucket"

GENERATED_HEADER = (
    "# Code generated from quwoquan_service/generated/contract_graph.json.\n"
    f"# Regenerate with {SCRIPT_NAME} --write.\n"
)

_PROMQL_SELECTOR_RE = re.compile(
    r"(?P<metric>[a-zA-Z_:][a-zA-Z0-9_:]*)\s*\{(?P<labels>[^{}]*)\}"
)
_PROMQL_LABEL_RE = re.compile(
    r'(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\s*'
    r'(?P<operator>=~|!~|=|!=)\s*"(?P<value>(?:\\.|[^"])*)"'
)
_PATH_PARAMETER_RE = re.compile(r"\{[^{} /]+\}")
_RECORD_METRIC_RE = re.compile(
    r"^quwoquan_(?P<domain>[a-z0-9_]+)_contract_operation_"
    r"(?P<dimension>requests_total|duration_seconds_bucket)$"
)


def _number_label(value: float) -> str:
    return str(int(value)) if value.is_integer() else format(value, "g")


def _quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
