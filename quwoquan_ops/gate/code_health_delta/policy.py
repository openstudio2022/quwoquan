"""Closed, versioned code-health policy loader."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class PolicyError(ValueError):
    """Raised when policy bytes cannot produce one deterministic ruleset."""


POLICY_ID = "incremental-code-health-v2"
_TOP_LEVEL = frozenset({
    "schema_version", "policy_id", "owner", "terminals", "source_categories",
    "classification", "thresholds", "rollout", "performance", "notes", "report",
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
        "split_analysis_churn", "split_analysis_files", "split_analysis_scopes",
    }),
}
_ROLLOUT_FIELDS = frozenset({"automatic_promotion", "calibration"})
_CALIBRATION_FIELDS = frozenset({
    "started_at", "minimum_days", "minimum_pull_requests",
    "maximum_confirmed_false_positive_rate", "minimum_reviewed_per_code",
})
_PERFORMANCE_FIELDS = frozenset({
    "local_p95_seconds", "ci_p95_seconds", "ci_hard_timeout_seconds",
    "delivery_critical_path_max_growth_percent",
    "delivery_critical_path_max_growth_seconds", "delivery_outcome_regression_percent",
})
#: 纯文档字段：记录判罚实现与各 code 的固定 terminal，不允许出现任何会被误读为开关的键。
_NOTES_FIELDS = frozenset({
    "metrics_provider", "external_analyzers_not_adopted", "advisory_only_codes", "blocking_codes",
})
_REPORT_FIELDS = frozenset({
    "root", "weekly_top_hotspots", "history_first_parent", "history_date",
    "cloc_count_duplicate_paths", "size_observation_tiers",
})


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


def _validate_notes(raw: Any) -> dict[str, Any]:
    notes = _closed_mapping(raw, _NOTES_FIELDS, "notes")
    _non_empty_string(notes["metrics_provider"], "notes.metrics_provider")
    for field in ("external_analyzers_not_adopted", "advisory_only_codes", "blocking_codes"):
        _string_list(notes[field], f"notes.{field}")
    if set(notes["advisory_only_codes"]) & set(notes["blocking_codes"]):
        raise PolicyError("notes 中同一 code 不能既是 advisory 又是 blocking")
    return notes


def load_policy(path: Path) -> dict[str, Any]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise PolicyError(f"code health policy 无法读取: {exc}") from exc
    document = _closed_mapping(document, _TOP_LEVEL, "code health policy 顶层")
    if document["schema_version"] != 1 or document["policy_id"] != POLICY_ID:
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
    _validate_thresholds(document.get("thresholds"))
    _validate_rollout(document.get("rollout"))
    _validate_performance(document.get("performance"))
    _validate_notes(document.get("notes"))
    _validate_report(document.get("report"))
    return document


def _ratio(value: Any, upper: float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= upper:
        raise PolicyError(f"{label} 必须为 0..{upper:g}")


def _validate_thresholds(raw: Any) -> None:
    thresholds = _closed_mapping(raw, frozenset(_THRESHOLD_FIELDS), "thresholds")
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
            "split_analysis_churn", "split_analysis_files", "split_analysis_scopes",
        )),
    ):
        for key in keys:
            _positive_int(thresholds[section][key], f"thresholds.{section}.{key}")
    _ratio(thresholds["duplication"]["advisory_percent"], 100, "duplication.advisory_percent")
    change_size = thresholds["change_size"]
    if (change_size["warn_handwritten_churn"] >= change_size["split_analysis_churn"]
            or change_size["warn_handwritten_files"] >= change_size["split_analysis_files"]):
        raise PolicyError("change_size warn 阈值必须小于 split_analysis 阈值")


def _validate_rollout(raw: Any) -> None:
    rollout = _closed_mapping(raw, _ROLLOUT_FIELDS, "rollout")
    if rollout["automatic_promotion"] is not False:
        raise PolicyError("automatic_promotion 必须显式为 false")
    calibration = _closed_mapping(rollout.get("calibration"), _CALIBRATION_FIELDS, "rollout.calibration")
    _non_empty_string(calibration["started_at"], "calibration.started_at")
    _positive_int(calibration["minimum_days"], "minimum_days")
    _positive_int(calibration["minimum_pull_requests"], "minimum_pull_requests")
    _positive_int(calibration["minimum_reviewed_per_code"], "minimum_reviewed_per_code")
    _ratio(calibration["maximum_confirmed_false_positive_rate"], 1, "maximum_confirmed_false_positive_rate")


def _validate_performance(raw: Any) -> None:
    performance = _closed_mapping(raw, _PERFORMANCE_FIELDS, "performance")
    for field in _PERFORMANCE_FIELDS:
        _positive_int(performance[field], f"performance.{field}")
    if performance["ci_p95_seconds"] >= performance["ci_hard_timeout_seconds"]:
        raise PolicyError("ci_p95_seconds 必须小于 ci_hard_timeout_seconds")


def _validate_report(raw: Any) -> None:
    report = _closed_mapping(raw, _REPORT_FIELDS, "report")
    report_root = _non_empty_string(report["root"], "report.root")
    if not report_root.startswith(".qwq_output/"):
        raise PolicyError("report.root 必须位于 .qwq_output")
    _positive_int(report["weekly_top_hotspots"], "report.weekly_top_hotspots")
    if report["history_first_parent"] is not True or report["history_date"] != "committer":
        raise PolicyError("weekly history 必须使用 first-parent committer date")
    if report["cloc_count_duplicate_paths"] is not True:
        raise PolicyError("weekly cloc 必须计算重复路径")
    tiers = report["size_observation_tiers"]
    if (not isinstance(tiers, list) or not tiers
            or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in tiers)
            or tiers != sorted(set(tiers))):
        raise PolicyError("report.size_observation_tiers 必须为严格递增的正整数列表")
