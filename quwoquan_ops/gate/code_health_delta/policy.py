"""Closed, versioned code-health policy loader."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class PolicyError(ValueError):
    """Raised when policy bytes cannot produce one deterministic ruleset."""


_TOP_LEVEL = frozenset({
    "schema_version", "policy_id", "owner", "terminals", "source_categories",
    "classification", "thresholds", "rollout", "performance", "tools", "report",
})
_CATEGORIES = (
    "handwritten-production", "test", "generated", "vendor",
    "contract-metadata", "config-data", "docs",
)
_CLASSIFICATION_FIELDS = frozenset({
    "source_extensions", "generated_markers", "vendor_markers", "test_markers",
    "contract_markers", "docs_prefixes", "config_extensions",
})
_THRESHOLD_FIELDS = {
    "file_lines": frozenset({"advisory", "block"}),
    "complexity": frozenset({"cyclomatic_advisory", "cognitive_advisory"}),
    "duplication": frozenset({"advisory_percent", "minimum_measured_new_lines", "block_lines"}),
    "change_size": frozenset({
        "warn_handwritten_churn", "warn_handwritten_files",
        "split_analysis_churn", "split_analysis_files",
    }),
}
_ROLLOUT_FIELDS = frozenset({"advisory_metrics", "first_day_blockers", "automatic_promotion", "calibration"})
_CALIBRATION_FIELDS = frozenset({
    "started_at", "minimum_days", "minimum_pull_requests",
    "maximum_confirmed_false_positive_rate",
})
_PERFORMANCE_FIELDS = frozenset({
    "local_p95_seconds", "ci_p95_seconds", "ci_hard_timeout_seconds",
    "delivery_critical_path_max_growth_percent",
    "delivery_critical_path_max_growth_seconds", "delivery_outcome_regression_percent",
})
_TOOL_FIELDS = {
    "python": frozenset({"provider", "rules", "version", "status"}),
    "go": frozenset({"provider", "rules", "version", "status"}),
    "clone": frozenset({"provider", "version", "status"}),
    "dart": frozenset({"provider", "rules", "version", "status"}),
    "builtin": frozenset({"provider", "version", "status"}),
}
_REPORT_FIELDS = frozenset({
    "root", "weekly_top_hotspots", "history_first_parent", "history_date",
    "cloc_count_duplicate_paths",
})
_ALLOWED_TOOL_STATUSES = frozenset({"active", "advisory-unavailable"})


def _closed_mapping(value: Any, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise PolicyError(f"{label} 字段不闭合")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PolicyError(f"{label} 必须为正整数")
    return value


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{label} 必须为非空字符串")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise PolicyError(f"{label} 必须为非空字符串列表")
    if len(value) != len(set(value)):
        raise PolicyError(f"{label} 不得包含重复值")
    return value


def _validate_tools(raw: Any) -> dict[str, Any]:
    tools = _closed_mapping(raw, frozenset(_TOOL_FIELDS), "tools")
    for name, fields in _TOOL_FIELDS.items():
        tool = _closed_mapping(tools.get(name), fields, f"tools.{name}")
        _non_empty_string(tool.get("provider"), f"tools.{name}.provider")
        version = tool.get("version")
        if (isinstance(version, bool) or not isinstance(version, (str, int))
                or (isinstance(version, str) and not version)):
            raise PolicyError(f"tools.{name}.version 必须为 exact string/int 或 unavailable")
        status = tool.get("status")
        if status not in _ALLOWED_TOOL_STATUSES:
            raise PolicyError(f"tools.{name}.status 非法")
        if "rules" in fields:
            _string_list(tool.get("rules"), f"tools.{name}.rules")
        if status == "active" and version == "unavailable":
            raise PolicyError(f"tools.{name} active 时必须声明 exact version")
        if status == "advisory-unavailable" and version != "unavailable":
            raise PolicyError(f"tools.{name} unavailable 状态与 version 不一致")
    return tools


def load_policy(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PolicyError(f"code health policy 无法读取: {exc}") from exc
    document = _closed_mapping(document, _TOP_LEVEL, "code health policy 顶层")
    if document["schema_version"] != 1 or document["policy_id"] != "incremental-code-health-v1":
        raise PolicyError("code health policy identity 非法")
    if document["owner"] != "incremental-code-health-governance":
        raise PolicyError("code health policy owner 非法")
    if document["terminals"] != ["PASS", "PR_WARN", "GATE_BLOCK"]:
        raise PolicyError("code health terminals 必须为 PASS/PR_WARN/GATE_BLOCK")
    if tuple(document["source_categories"]) != _CATEGORIES:
        raise PolicyError("source_categories 必须为 canonical 七类闭集")

    classification = _closed_mapping(document.get("classification"), _CLASSIFICATION_FIELDS, "classification")
    for field in _CLASSIFICATION_FIELDS:
        _string_list(classification.get(field), f"classification.{field}")

    thresholds = _closed_mapping(document.get("thresholds"), frozenset(_THRESHOLD_FIELDS), "thresholds")
    for section, fields in _THRESHOLD_FIELDS.items():
        _closed_mapping(thresholds.get(section), fields, f"thresholds.{section}")
    file_lines = thresholds["file_lines"]
    advisory = _positive_int(file_lines["advisory"], "file_lines.advisory")
    block = _positive_int(file_lines["block"], "file_lines.block")
    if advisory >= block:
        raise PolicyError("file_lines.advisory 必须小于 block")
    for section, keys in (
        ("complexity", ("cyclomatic_advisory", "cognitive_advisory")),
        ("duplication", ("minimum_measured_new_lines", "block_lines")),
        ("change_size", (
            "warn_handwritten_churn", "warn_handwritten_files",
            "split_analysis_churn", "split_analysis_files",
        )),
    ):
        for key in keys:
            _positive_int(thresholds[section][key], f"thresholds.{section}.{key}")
    duplication_percent = thresholds["duplication"]["advisory_percent"]
    if (isinstance(duplication_percent, bool)
            or not isinstance(duplication_percent, (int, float))
            or not 0 <= float(duplication_percent) <= 100):
        raise PolicyError("duplication.advisory_percent 必须为 0..100")
    change_size = thresholds["change_size"]
    if (change_size["warn_handwritten_churn"] >= change_size["split_analysis_churn"]
            or change_size["warn_handwritten_files"] >= change_size["split_analysis_files"]):
        raise PolicyError("change_size warn 阈值必须小于 split_analysis 阈值")

    rollout = _closed_mapping(document.get("rollout"), _ROLLOUT_FIELDS, "rollout")
    if rollout["automatic_promotion"] is not False:
        raise PolicyError("automatic_promotion 必须显式为 false")
    _string_list(rollout["advisory_metrics"], "rollout.advisory_metrics")
    _string_list(rollout["first_day_blockers"], "rollout.first_day_blockers")
    calibration = _closed_mapping(rollout.get("calibration"), _CALIBRATION_FIELDS, "rollout.calibration")
    _non_empty_string(calibration["started_at"], "calibration.started_at")
    _positive_int(calibration["minimum_days"], "minimum_days")
    _positive_int(calibration["minimum_pull_requests"], "minimum_pull_requests")
    false_positive = calibration["maximum_confirmed_false_positive_rate"]
    if (isinstance(false_positive, bool)
            or not isinstance(false_positive, (int, float))
            or not 0 <= float(false_positive) <= 1):
        raise PolicyError("maximum_confirmed_false_positive_rate 必须为 0..1")

    performance = _closed_mapping(document.get("performance"), _PERFORMANCE_FIELDS, "performance")
    for field in _PERFORMANCE_FIELDS:
        _positive_int(performance[field], f"performance.{field}")
    if performance["ci_p95_seconds"] >= performance["ci_hard_timeout_seconds"]:
        raise PolicyError("ci_p95_seconds 必须小于 ci_hard_timeout_seconds")

    _validate_tools(document.get("tools"))

    report = _closed_mapping(document.get("report"), _REPORT_FIELDS, "report")
    report_root = _non_empty_string(report["root"], "report.root")
    if not report_root.startswith(".qwq_output/"):
        raise PolicyError("report.root 必须位于 .qwq_output")
    _positive_int(report["weekly_top_hotspots"], "report.weekly_top_hotspots")
    if report["history_first_parent"] is not True or report["history_date"] != "committer":
        raise PolicyError("weekly history 必须使用 first-parent committer date")
    if report["cloc_count_duplicate_paths"] is not True:
        raise PolicyError("weekly cloc 必须计算重复路径")
    return document
