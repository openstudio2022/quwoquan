"""canonical coverage baseline 的加载、字段校验与整体写入。

基线只接受 ``measuredFromGreenTests: true`` 的全单元同次绿采集；旧
`coverage_baseline.json` 已硬切退休，禁止 alias/fallback/dual-read。除 import
重组外与拆分前逐字一致；被测试 monkeypatch 的符号（``BASELINE_PATH``、
``RETIRED_BASELINE_PATH``、``discover_units``）经包命名空间 ``cc`` 在调用期解析。
"""

from __future__ import annotations

import json
from typing import Sequence

import quwoquan_ops.gate.canonical_coverage as cc

from .constants import (
    BASELINE_SCHEMA,
    CANONICAL_BASELINE_GOVERNANCE,
    CANONICAL_POLICY,
    METRICS_BY_KIND,
    METRIC_STATUS_UNMEASURED,
    RULE_ID,
    SHA256_DIGEST_RE,
    CoverageError,
)
from .attribution import percent
from .receipts import _validate_receipt_payload, _write_json_atomic, receipt_digest
from .units import collection_targets, unit_kind, unit_scope

POLICY_NUMERIC_KEYS = (
    "tolerance_percentage_points",
    "improvement_slack_percentage_points",
    "granularity_units",
)
POLICY_REASON_KEYS = (
    "tolerance_reason",
    "improvement_slack_reason",
    "granularity_units_reason",
)
BASELINE_TOP_LEVEL_FIELDS = {
    "_governance",
    "schema",
    "ruleId",
    "policy",
    "receipts",
    "units",
}
BASELINE_GOVERNANCE_REQUIRED_FIELDS = {
    "owner",
    "reason",
    "expires_when",
    "measure",
}
BASELINE_GOVERNANCE_OPTIONAL_FIELDS = {"superseded_measure"}
BASELINE_GOVERNANCE_FIELDS = (
    BASELINE_GOVERNANCE_REQUIRED_FIELDS | BASELINE_GOVERNANCE_OPTIONAL_FIELDS
)
BASELINE_UNIT_FIELDS = {
    "kind",
    "scope",
    "measuredFromGreenTests",
    "receiptDigests",
    "metrics",
}


def _validate_baseline_metric(unit: str, metric: str, entry: object) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{cc.BASELINE_PATH}: {unit}/{metric} 必须是 object")
    if entry.get("status") == METRIC_STATUS_UNMEASURED:
        raise ValueError(
            f"{cc.BASELINE_PATH}: {unit}/{metric} 不得把 unmeasured 写入 baseline；"
            "未采集不是绿测试覆盖结果"
        )
    if set(entry) != {"covered", "total", "percent"}:
        raise ValueError(f"{cc.BASELINE_PATH}: {unit}/{metric} measured fields mismatch")
    covered = entry.get("covered")
    total = entry.get("total")
    value = entry.get("percent")
    if (
        not isinstance(covered, int)
        or isinstance(covered, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total <= 0
        or covered <= 0
        or covered > total
        or not isinstance(value, (int, float))
        or isinstance(value, bool)
        or float(value) != percent(covered, total)
    ):
        raise ValueError(
            f"{cc.BASELINE_PATH}: {unit}/{metric} measured value 非自洽实测值"
        )


def _validate_baseline_receipt_registry(receipts: object) -> dict[str, dict]:
    if not isinstance(receipts, dict):
        raise ValueError(f"{cc.BASELINE_PATH}: receipts 必须是 object")
    validated: dict[str, dict] = {}
    for declared_digest, payload in receipts.items():
        if SHA256_DIGEST_RE.fullmatch(str(declared_digest or "")) is None:
            raise ValueError(f"{cc.BASELINE_PATH}: receipt key 非 canonical sha256")
        try:
            receipt = _validate_receipt_payload(
                payload, expected_target=None, require_green=True
            )
        except CoverageError as error:
            raise ValueError(
                f"{cc.BASELINE_PATH}: receipt {declared_digest}: {error}"
            ) from error
        actual_digest = receipt_digest(receipt)
        if declared_digest != actual_digest:
            raise ValueError(
                f"{cc.BASELINE_PATH}: receipt {declared_digest} 内容摘要伪造，"
                f"实测 {actual_digest}"
            )
        validated[declared_digest] = receipt
    return validated


def _validate_unit_receipt_refs(
    unit: str,
    entry: dict,
    receipt_registry: dict[str, dict],
) -> None:
    refs = entry.get("receiptDigests")
    if (
        not isinstance(refs, list)
        or not refs
        or refs != sorted(set(refs))
        or any(SHA256_DIGEST_RE.fullmatch(str(ref or "")) is None for ref in refs)
    ):
        raise ValueError(
            f"{cc.BASELINE_PATH}: {unit}.receiptDigests 必须是非空、去重、有序 sha256 列表"
        )
    missing = sorted(set(refs) - set(receipt_registry))
    if missing:
        raise ValueError(
            f"{cc.BASELINE_PATH}: {unit}.receiptDigests 引用缺失 receipt: {missing}"
        )
    actual_targets = sorted(receipt_registry[ref]["target"] for ref in refs)
    expected_targets = sorted(collection_targets([unit]))
    if actual_targets != expected_targets:
        raise ValueError(
            f"{cc.BASELINE_PATH}: {unit}.receiptDigests target 绑定伪造；"
            f"baseline={actual_targets}, expected={expected_targets}"
        )


def load_baseline() -> dict:
    if cc.RETIRED_BASELINE_PATH.is_file():
        raise ValueError(
            f"{cc.RETIRED_BASELINE_PATH}: 旧 coverage baseline 已硬切退休；"
            "删除旧输入后仅生成 canonical baseline"
        )
    if not cc.BASELINE_PATH.is_file():
        raise FileNotFoundError(cc.BASELINE_PATH)
    document = json.loads(cc.BASELINE_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{cc.BASELINE_PATH}: baseline 必须是 object")
    if set(document) != BASELINE_TOP_LEVEL_FIELDS:
        missing = sorted(BASELINE_TOP_LEVEL_FIELDS - set(document))
        extra = sorted(set(document) - BASELINE_TOP_LEVEL_FIELDS)
        if "receipts" in missing:
            raise ValueError(
                f"{cc.BASELINE_PATH}: baseline 缺少可复核 receipt provenance；"
                "旧 measuredFromGreenTests 布尔值不得冒充绿测试来源"
            )
        raise ValueError(
            f"{cc.BASELINE_PATH}: baseline fields mismatch; missing={missing}, extra={extra}"
        )
    if document.get("schema") != BASELINE_SCHEMA:
        raise ValueError(
            f"{cc.BASELINE_PATH}: schema 必须是 {BASELINE_SCHEMA}，"
            f"实测 {document.get('schema')!r}"
        )
    if document.get("ruleId") != RULE_ID:
        raise ValueError(
            f"{cc.BASELINE_PATH}: ruleId 必须是 {RULE_ID}，实测 {document.get('ruleId')!r}"
        )
    governance = document.get("_governance")
    governance_fields = set(governance) if isinstance(governance, dict) else set()
    if (
        not isinstance(governance, dict)
        or not BASELINE_GOVERNANCE_REQUIRED_FIELDS.issubset(governance_fields)
        or not governance_fields.issubset(BASELINE_GOVERNANCE_FIELDS)
    ):
        raise ValueError(f"{cc.BASELINE_PATH}: _governance fields mismatch")
    for key in governance_fields:
        if not str(governance.get(key) or "").strip():
            raise ValueError(f"{cc.BASELINE_PATH}: _governance.{key} 不得为空")
    policy = document.get("policy") or {}
    if not isinstance(policy, dict) or set(policy) != set(POLICY_NUMERIC_KEYS) | set(
        POLICY_REASON_KEYS
    ):
        raise ValueError(f"{cc.BASELINE_PATH}: policy fields mismatch")
    for key in POLICY_NUMERIC_KEYS:
        value = policy.get(key)
        if not isinstance(value, (int, float)) or value < 0:
            raise ValueError(
                f"{cc.BASELINE_PATH}: policy.{key} 必须是非负数，实测 {value!r}"
            )
    for key in POLICY_REASON_KEYS:
        if not str(policy.get(key) or "").strip():
            raise ValueError(f"{cc.BASELINE_PATH}: policy.{key} 必须写明理由")
    receipt_registry = _validate_baseline_receipt_registry(document.get("receipts"))
    units = document.get("units")
    if not isinstance(units, dict):
        raise ValueError(f"{cc.BASELINE_PATH}: units 必须是 object")
    for unit, entry in units.items():
        if not isinstance(unit, str) or not isinstance(entry, dict):
            raise ValueError(f"{cc.BASELINE_PATH}: unit entry 非法: {unit!r}")
        if set(entry) != BASELINE_UNIT_FIELDS:
            raise ValueError(f"{cc.BASELINE_PATH}: {unit} fields mismatch")
        try:
            expected_kind = unit_kind(unit)
        except CoverageError as error:
            raise ValueError(f"{cc.BASELINE_PATH}: {error}") from error
        if entry.get("kind") != expected_kind:
            raise ValueError(f"{cc.BASELINE_PATH}: {unit}.kind 与单元不一致")
        if not str(entry.get("scope") or "").strip():
            raise ValueError(f"{cc.BASELINE_PATH}: {unit}.scope 不得为空")
        if entry.get("measuredFromGreenTests") is not True:
            raise ValueError(
                f"{cc.BASELINE_PATH}: {unit}.measuredFromGreenTests 必须是 true；"
                "红测试或旧暂定基线不得复用"
            )
        _validate_unit_receipt_refs(unit, entry, receipt_registry)
        metrics = entry.get("metrics")
        expected_metrics = set(METRICS_BY_KIND[expected_kind])
        if not isinstance(metrics, dict) or set(metrics) != expected_metrics:
            raise ValueError(f"{cc.BASELINE_PATH}: {unit}.metrics 维度不完整")
        for metric, metric_entry in metrics.items():
            _validate_baseline_metric(unit, metric, metric_entry)
    referenced_receipts = {
        digest for entry in units.values() for digest in entry["receiptDigests"]
    }
    unreferenced = sorted(set(receipt_registry) - referenced_receipts)
    if unreferenced:
        raise ValueError(
            f"{cc.BASELINE_PATH}: receipts 含未被任何 baseline entry 引用的条目: {unreferenced}"
        )
    return document


def unit_entry(
    metrics: dict[str, dict],
    unit: str,
    *,
    receipts: Sequence[dict],
) -> dict:
    kind = unit_kind(unit)
    expected_metrics = set(METRICS_BY_KIND[kind])
    if not isinstance(metrics, dict) or set(metrics) != expected_metrics:
        actual_metrics = (
            sorted(metrics) if isinstance(metrics, dict) else type(metrics).__name__
        )
        raise CoverageError(
            f"{unit}: baseline metrics 维度不完整；"
            f"expected={sorted(expected_metrics)}, actual={actual_metrics}"
        )
    for metric, entry in metrics.items():
        try:
            _validate_baseline_metric(unit, metric, entry)
        except ValueError as error:
            raise CoverageError(str(error)) from error
    validated_receipts = [
        _validate_receipt_payload(receipt, expected_target=None, require_green=True)
        for receipt in receipts
    ]
    receipt_refs = sorted(receipt_digest(receipt) for receipt in validated_receipts)
    registry = {receipt_digest(receipt): receipt for receipt in validated_receipts}
    provisional = {"receiptDigests": receipt_refs}
    _validate_unit_receipt_refs(unit, provisional, registry)
    return {
        "kind": kind,
        "scope": unit_scope(unit),
        "measuredFromGreenTests": True,
        "receiptDigests": receipt_refs,
        "metrics": {
            metric: dict(metrics[metric])
            for metric in sorted(METRICS_BY_KIND[kind])
        },
    }


def write_baseline(
    measured: dict[str, dict],
    *,
    units: Sequence[str],
    unit_receipts: dict[str, Sequence[dict]],
    known_units: Sequence[str] | None = None,
) -> dict:
    """以全单元同次绿产物整体写入唯一 baseline。"""
    if cc.RETIRED_BASELINE_PATH.is_file():
        raise CoverageError(
            f"{cc.RETIRED_BASELINE_PATH}: 旧 coverage baseline 已硬切退休；"
            "禁止 alias、fallback、dual-read 或原位改名"
        )
    all_units = set(cc.discover_units())
    if set(units) != all_units:
        raise CoverageError(
            "canonical coverage baseline 只能由 App、Cloud、Python、Ops "
            "全单元同次全绿采集整体写入；禁止 scope/unit 分区更新"
        )
    if known_units is not None and set(known_units) != all_units:
        raise CoverageError(
            "canonical coverage baseline roster 与当前全单元名册不一致"
        )
    missing_receipts = sorted(set(units) - set(unit_receipts))
    extra_receipts = sorted(set(unit_receipts) - set(units))
    if missing_receipts or extra_receipts:
        raise CoverageError(
            "baseline provenance 与求值单元不一致；"
            f"missing={missing_receipts}, extra={extra_receipts}"
        )
    if cc.BASELINE_PATH.exists():
        try:
            load_baseline()
        except (ValueError, json.JSONDecodeError) as error:
            raise CoverageError(
                "非 canonical coverage baseline 已硬切退休；"
                "禁止兼容读取、别名或迁移旧数字"
            ) from error
    payload = {
        "_governance": dict(CANONICAL_BASELINE_GOVERNANCE),
        "schema": BASELINE_SCHEMA,
        "ruleId": RULE_ID,
        "policy": dict(CANONICAL_POLICY),
        "receipts": {},
        "units": {},
    }
    for unit in units:
        receipts = list(unit_receipts[unit])
        for receipt in receipts:
            validated = _validate_receipt_payload(
                receipt, expected_target=None, require_green=True
            )
            payload["receipts"][receipt_digest(validated)] = dict(validated)
        payload["units"][unit] = unit_entry(measured[unit], unit, receipts=receipts)

    referenced_receipts = {
        digest
        for entry in payload["units"].values()
        for digest in entry["receiptDigests"]
    }
    payload["receipts"] = {
        digest: payload["receipts"][digest] for digest in sorted(referenced_receipts)
    }
    reserved = {
        "_governance",
        "schema",
        "ruleId",
        "policy",
        "receipts",
        "units",
    }
    ordered = {
        "_governance": payload["_governance"],
        "schema": BASELINE_SCHEMA,
        "ruleId": RULE_ID,
        "policy": payload["policy"],
        "receipts": payload["receipts"],
    }
    # baseline schema 不接受计数 allowance 或其他附加字段；所有 production
    # source 必须进入对象/cross-cutting 单元，否则在归属阶段立即 BLOCK。
    for key in list(payload):
        if key not in reserved:
            payload.pop(key)
    ordered["units"] = {
        unit: payload["units"][unit] for unit in sorted(payload["units"])
    }
    _write_json_atomic(cc.BASELINE_PATH, ordered)
    return ordered
