from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import ROOT, utc_now, write_json
from quwoquan_ops.cli.lib.generated.runtime_log_catalog import (
    CORRELATION_OPTIONAL_FIELDS,
    ENVELOPE_OPTIONAL_FIELDS,
    ENVELOPE_REQUIRED_FIELDS,
    FORBIDDEN_ATTRIBUTE_KEYS,
    FORBIDDEN_FIELDS,
    HIGH_CARDINALITY_METRIC_KEYS,
    LEVELS,
    LOG_FIELD_ORDER,
    LOG_KINDS,
    MAX_ATTRIBUTES,
    MAX_ATTRIBUTES_BYTES,
    MAX_ATTRIBUTE_KEY_LENGTH,
    MAX_ATTRIBUTE_VALUE_LENGTH,
    MAX_MESSAGE_BYTES,
    OBSERVABILITY_SCHEMA,
    REQUIRED_KIND_FIELDS as CATALOG_REQUIRED_KIND_FIELDS,
    RESOURCE_OPTIONAL_FIELDS,
    RESOURCE_REQUIRED_FIELDS,
    SIGNAL_REGISTRY,
    SIGNAL_LOG_KINDS,
    SIGNALS,
)
from quwoquan_ops.cli.lib.output_paths import (
    env_observability_run_dir,
    normalize_env,
    repo_root,
)


OBSERVABILITY_ROOT = ROOT / ".qwq_output"

ENVS = frozenset({"alpha", "beta", "gamma", "prod", "repo"})
FORBIDDEN_INLINE_FIELDS = frozenset(
    {
        *FORBIDDEN_FIELDS,
        "sessionId",
    }
)
COMMON_LOG_FIELDS = frozenset(ENVELOPE_REQUIRED_FIELDS)
LOG_FILE_SUFFIX = ".log"
KIND_FIELDS = {
    kind: frozenset(fields)
    for kind, fields in LOG_FIELD_ORDER.items()
}
REQUIRED_KIND_FIELDS = {
    kind: frozenset(fields)
    for kind, fields in CATALOG_REQUIRED_KIND_FIELDS.items()
}
def run_dir(env_name: str, run_id: str) -> Path:
    if env_name == "repo":
        return repo_root() / "observability" / _safe_segment(run_id)
    if env_name == "data":
        raise ValueError(
            "data observability must use the repo run root, not a second data root"
        )
    return env_observability_run_dir(normalize_env(env_name), run_id)


def run_id_from_report_dir(report_dir: Path) -> str:
    return _safe_segment(report_dir.name or "run")


def env_from_report_dir(report_dir: Path, target: str = "") -> str:
    parts = report_dir.parts
    if ".qwq_output" in parts:
        index = parts.index(".qwq_output")
        if len(parts) > index + 2 and parts[index + 1] == "env":
            env_segment = parts[index + 2]
            if env_segment in ENVS:
                return env_segment
    parent = report_dir.parent.name
    if parent in ENVS:
        return parent
    target = target.strip()
    if target.startswith("alpha"):
        return "alpha"
    if target.startswith("beta"):
        return "beta"
    if target.startswith("gamma"):
        return "gamma"
    if target.startswith("prod"):
        return "prod"
    return "repo"


def write_run_manifest(
    base_dir: Path,
    *,
    env_name: str,
    run_id: str,
    command: str,
    target: str,
    report_dir: Path,
) -> Path:
    manifest = {
        "schema": OBSERVABILITY_SCHEMA,
        "env": env_name,
        "runId": run_id,
        "command": command,
        "target": target,
        "reportDir": _repo_rel(report_dir),
        "generatedAt": utc_now(),
    }
    path = base_dir / "manifest.json"
    write_json(path, manifest)
    return path


def append_log_line(
    path: Path,
    payload: dict[str, Any],
    *,
    resource: dict[str, str] | None = None,
    correlation: dict[str, str] | None = None,
    signal: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kind = path.stem
    record = canonical_log_record(
        kind,
        payload,
        path=path,
        resource=resource,
        correlation=correlation,
        signal=signal,
    )
    issues = validate_log_payload(kind, record)
    if issues:
        raise ValueError(f"invalid {kind} runtime log: {'; '.join(issues)}")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(format_log_record(kind, record) + "\n")


def append_canonical_log_record(path: Path, payload: dict[str, Any]) -> None:
    """追加一个已规范化的运行日志，保留信封语义并再次执行脱敏。"""
    kind = str(payload.get("logKind") or "")
    if kind not in LOG_KINDS:
        raise ValueError(f"unknown canonical runtime log kind: {kind}")
    if path.stem != kind:
        raise ValueError(
            f"canonical runtime log path mismatch: expected {kind}.log, received {path.name}"
        )
    record = dict(payload)
    record["message"] = _bounded(
        _redact_text(str(record.get("message") or "")),
        MAX_MESSAGE_BYTES,
    )
    signal = str(record.get("signal") or "")
    attributes = record.get("attributes")
    if attributes is not None:
        normalized_attributes = _canonical_attributes(
            attributes,
            set(SIGNAL_REGISTRY.get(signal, {}).get("attributeAllowlist", ())),
        )
        if normalized_attributes:
            record["attributes"] = normalized_attributes
        else:
            record.pop("attributes", None)
    issues = validate_log_payload(kind, record)
    if issues:
        raise ValueError(f"invalid canonical {kind} runtime log: {'; '.join(issues)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(format_log_record(kind, record) + "\n")


def canonical_log_record(
    kind: str,
    payload: dict[str, Any],
    *,
    path: Path | None = None,
    resource: dict[str, str] | None = None,
    correlation: dict[str, str] | None = None,
    signal: str = "",
) -> dict[str, Any]:
    if kind not in LOG_KINDS:
        raise ValueError(f"unknown log kind: {kind}")
    source = dict(payload)
    source.pop("schema", None)
    declared_kind = str(source.pop("logKind", kind) or kind)
    if declared_kind != kind:
        raise ValueError(
            f"runtime log kind mismatch: expected {kind}, received {declared_kind}"
        )
    declared_signal = str(source.pop("signal", "") or "")
    occurred_at = str(source.pop("occurredAt", utc_now()))
    observed_at = str(source.pop("observedAt", occurred_at))
    severity = str(source.pop("severity", "INFO")).upper()
    message = _bounded(
        _redact_text(
            str(
                source.pop(
                    "message",
                    source.get("event")
                    or source.get("step")
                    or source.get("action")
                    or kind,
                )
            )
        ),
        MAX_MESSAGE_BYTES,
    )
    resolved_resource = dict(resource or source.pop("resource", {}) or {})
    if not resolved_resource:
        resolved_resource = _default_resource(path)
    resolved_correlation = dict(correlation or source.pop("correlation", {}) or {})
    _move_if_present(source, resolved_correlation, "requestId")
    _move_if_present(source, resolved_correlation, "traceId")
    _move_if_present(source, resolved_correlation, "spanId")
    _move_if_present(source, resolved_correlation, "operationId")
    _move_if_present(source, resolved_correlation, "pageName")
    _move_if_present(source, resolved_correlation, "surfaceId")
    _move_if_present(source, resolved_correlation, "executionId")
    _move_if_present(source, resolved_correlation, "workPackageId")
    _move_if_present(source, resolved_correlation, "environmentRunId")
    raw_attributes = source.pop("attributes", {})
    resolved_signal = signal or declared_signal or _default_signal(kind, resolved_resource)
    record: dict[str, Any] = {
        "schema": OBSERVABILITY_SCHEMA,
        "occurredAt": occurred_at,
        "observedAt": observed_at,
        "logKind": kind,
        "severity": severity,
        "signal": resolved_signal,
        "message": message,
        "resource": {
            key: str(value)
            for key, value in resolved_resource.items()
            if value not in ("", None)
        },
    }
    if resolved_correlation:
        record["correlation"] = {
            key: str(value)
            for key, value in resolved_correlation.items()
            if value not in ("", None)
        }
    for field in ENVELOPE_OPTIONAL_FIELDS:
        if field == "attributes":
            continue
        if field in source and source[field] not in ("", None, {}, []):
            value = source.pop(field)
            if field == "status":
                value = str(value)
            elif field == "durationMs":
                value = int(value)
            record[field] = value
    attribute_source = dict(raw_attributes) if isinstance(raw_attributes, dict) else {}
    attribute_source.update(source)
    signal_contract = SIGNAL_REGISTRY.get(resolved_signal, {})
    attributes = _canonical_attributes(
        attribute_source,
        set(signal_contract.get("attributeAllowlist", ())),
    )
    if attributes:
        record["attributes"] = attributes
    return record


def format_log_record(kind: str, payload: dict[str, Any]) -> str:
    if kind not in LOG_KINDS:
        raise ValueError(f"unknown log kind: {kind}")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def parse_log_records(kind: str, lines: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    for index, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        parsed, parse_issues = parse_log_line(kind, raw_line)
        if parse_issues:
            issues.extend(f"{index}: {issue}" for issue in parse_issues)
            continue
        records.append(parsed)
        if len(records) >= 200:
            break
    return records, issues


def parse_log_line(kind: str, line: str) -> tuple[dict[str, Any], list[str]]:
    if kind not in LOG_KINDS:
        return {}, [f"unknown log kind: {kind}"]
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        return {}, [f"runtime log must be one JSON object: {exc.msg}"]
    if not isinstance(payload, dict):
        return {}, ["runtime log must be a JSON object"]
    return payload, []


def write_stackctl_links(
    report_dir: Path,
    *,
    env_name: str,
    run_id: str,
    obs_dir: Path,
) -> Path:
    links = {
        "observabilityRun": _repo_rel(obs_dir),
        "manifest": _repo_rel(obs_dir / "manifest.json"),
        "logs": _repo_rel(obs_dir / "logs"),
        "metrics": _repo_rel(obs_dir / "metrics"),
        "traces": _repo_rel(obs_dir / "traces"),
        "env": env_name,
        "runId": run_id,
    }
    path = report_dir / "links.json"
    write_json(path, links)
    return path


def validate_log_payload(kind: str, payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if kind not in LOG_KINDS:
        return [f"unknown log kind: {kind}"]
    allowed = COMMON_LOG_FIELDS | ENVELOPE_OPTIONAL_FIELDS | KIND_FIELDS[kind]
    unknown = sorted(set(payload) - allowed)
    if unknown:
        issues.append(f"unknown field(s): {', '.join(unknown)}")
    forbidden = sorted(set(payload) & FORBIDDEN_INLINE_FIELDS)
    if forbidden:
        issues.append(f"forbidden field(s): {', '.join(forbidden)}")
    for field in ENVELOPE_REQUIRED_FIELDS:
        if field not in payload or payload.get(field) in ("", None):
            issues.append(f"missing required field: {field}")
    if payload.get("schema") not in ("", None, OBSERVABILITY_SCHEMA):
        issues.append("invalid schema")
    if payload.get("logKind") not in ("", None, kind):
        issues.append(f"logKind must equal {kind}")
    severity = str(payload.get("severity") or "")
    if severity and severity not in LEVELS:
        issues.append(f"invalid severity: {severity}")
    signal = str(payload.get("signal") or "")
    if signal and signal not in SIGNALS:
        issues.append(f"unregistered signal: {signal}")
    elif signal and SIGNAL_LOG_KINDS.get(signal) != kind:
        issues.append(f"signal {signal} does not match log kind {kind}")
    signal_contract = SIGNAL_REGISTRY.get(signal, {})
    message = str(payload.get("message") or "")
    if len(message.encode("utf-8")) > MAX_MESSAGE_BYTES:
        issues.append(f"message too large: {len(message.encode('utf-8'))} > {MAX_MESSAGE_BYTES}")
    for field in sorted(REQUIRED_KIND_FIELDS[kind]):
        if field not in payload or payload.get(field) in ("", None):
            issues.append(f"missing {kind} field: {field}")
    if "status" in payload and not isinstance(payload["status"], str):
        issues.append("status must be a string")
    if "durationMs" in payload and (
        isinstance(payload["durationMs"], bool)
        or not isinstance(payload["durationMs"], int)
        or payload["durationMs"] < 0
    ):
        issues.append("durationMs must be a non-negative integer")
    resource = payload.get("resource")
    if not isinstance(resource, dict):
        issues.append("resource must be an object")
    else:
        _validate_context_object(
            issues,
            "resource",
            resource,
            required=RESOURCE_REQUIRED_FIELDS,
            optional=RESOURCE_OPTIONAL_FIELDS,
        )
    correlation = payload.get("correlation")
    if correlation is not None:
        if not isinstance(correlation, dict):
            issues.append("correlation must be an object")
        else:
            _validate_context_object(
                issues,
                "correlation",
                correlation,
                required=(),
                optional=CORRELATION_OPTIONAL_FIELDS,
            )
            allowed_correlation = set(signal_contract.get("correlationKeys", ()))
            unregistered_correlation = sorted(
                set(correlation) - allowed_correlation
            )
            if unregistered_correlation:
                issues.append(
                    "correlation contains unregistered key(s): "
                    + ", ".join(unregistered_correlation)
                )
    attrs = payload.get("attributes")
    if attrs is not None:
        if not isinstance(attrs, dict):
            issues.append("attributes must be an object")
        else:
            encoded = json.dumps(attrs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(attrs) > MAX_ATTRIBUTES:
                issues.append(f"too many attributes: {len(attrs)} > {MAX_ATTRIBUTES}")
            if len(encoded) > MAX_ATTRIBUTES_BYTES:
                issues.append(f"attributes too large: {len(encoded)} > {MAX_ATTRIBUTES_BYTES}")
            for key in _iter_attr_keys(attrs):
                if _forbidden_attribute_key(key):
                    issues.append(f"attributes contains forbidden key: {key}")
                    break
                if key not in set(signal_contract.get("attributeAllowlist", ())):
                    issues.append(f"attributes contains unregistered key: {key}")
                    break
            for key, value in attrs.items():
                if not isinstance(value, str):
                    issues.append(f"attributes.{key} must be a string")
                    break
    return issues


def validate_log_record(kind: str, payload: dict[str, Any]) -> list[str]:
    return validate_log_payload(kind, payload)


def _iter_attr_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_iter_attr_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_iter_attr_keys(child))
    return keys


def _canonical_attributes(value: Any, allowed_keys: set[str]) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for raw_key in sorted(value, key=str):
        key = str(raw_key).strip()
        if (
            not key
            or len(key) > MAX_ATTRIBUTE_KEY_LENGTH
            or _forbidden_attribute_key(key)
            or key not in allowed_keys
        ):
            continue
        item = value[raw_key]
        if isinstance(item, str):
            text = item
        else:
            text = json.dumps(item, ensure_ascii=False, separators=(",", ":"), default=str)
        text = _bounded(_redact_text(text), MAX_ATTRIBUTE_VALUE_LENGTH)
        candidate = {**result, key: text}
        encoded = json.dumps(
            candidate,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(candidate) > MAX_ATTRIBUTES or len(encoded) > MAX_ATTRIBUTES_BYTES:
            break
        result[key] = text
    return result


def _forbidden_attribute_key(key: str) -> bool:
    normalized = _normalize_key(key)
    candidates = (
        *FORBIDDEN_FIELDS,
        *FORBIDDEN_ATTRIBUTE_KEYS,
        *HIGH_CARDINALITY_METRIC_KEYS,
    )
    for candidate in candidates:
        blocked = _normalize_key(candidate)
        if normalized == blocked or (blocked != "ip" and blocked in normalized):
            return True
    return False


def _normalize_key(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _redact_text(value: str) -> str:
    value = re.sub(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer ***", value, flags=re.I)
    value = re.sub(
        r"(access_token|token|authcode|authorization|signature|"
        r"x-amz-signature|x-amz-credential|secret)=([^&#\s]+)",
        r"\1=***",
        value,
        flags=re.I,
    )
    value = re.sub(
        r"\b(?:\d{3}[- ]?\d{4}[- ]?\d{4}|"
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b",
        "***",
        value,
    )
    return value


def _bounded(value: str, max_length: int) -> str:
    if len(value.encode("utf-8")) <= max_length:
        return value
    suffix = "…"
    while value and len((value + suffix).encode("utf-8")) > max_length:
        value = value[:-1]
    return value + suffix


def _validate_context_object(
    issues: list[str],
    name: str,
    value: dict[str, Any],
    *,
    required: tuple[str, ...] | list[str],
    optional: frozenset[str],
) -> None:
    allowed = set(required) | set(optional)
    unknown = sorted(set(value) - allowed)
    if unknown:
        issues.append(f"{name} has unknown field(s): {', '.join(unknown)}")
    forbidden = sorted(set(value) & FORBIDDEN_INLINE_FIELDS)
    if forbidden:
        issues.append(f"{name} has forbidden field(s): {', '.join(forbidden)}")
    for field in required:
        if value.get(field) in ("", None):
            issues.append(f"{name} missing required field: {field}")
    for field, item in value.items():
        if item is not None and not isinstance(item, str):
            issues.append(f"{name}.{field} must be a string")


def _default_resource(path: Path | None) -> dict[str, str]:
    environment = "repo"
    service = "quwoquan-ops"
    source_type = "ops"
    if path is not None:
        parts = path.parts
        if "stackctl" in parts:
            service = "stackctl"
        if "logs" in parts:
            index = parts.index("logs")
            if len(parts) > index + 2:
                candidate_source_type = parts[index + 1]
                candidate_service = parts[index + 2]
                if candidate_source_type in {
                    "app",
                    "data",
                    "ops",
                    "portal",
                    "service",
                } and candidate_service:
                    source_type = candidate_source_type
                    service = candidate_service
        if ".qwq_output" in parts:
            index = parts.index(".qwq_output")
            if len(parts) > index + 2 and parts[index + 1] == "env":
                environment = parts[index + 2]
    return {
        "sourceType": source_type,
        "service": service,
        "environment": environment,
    }


def _default_signal(kind: str, resource: dict[str, str]) -> str:
    source_type = resource.get("sourceType", "")
    if source_type == "data":
        if kind == "exception":
            return "data.exception.stage"
        return "data.runtime.stage"
    if kind == "audit":
        return "ops.audit.control"
    if kind == "deploy":
        return "ops.deploy.stackctl"
    if kind == "exception":
        return "ops.exception.runtime"
    return "ops.runtime.process"


def _move_if_present(
    source: dict[str, Any],
    destination: dict[str, Any],
    canonical: str,
) -> None:
    if canonical in source:
        destination[canonical] = source.pop(canonical)


def _repo_rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _safe_segment(value: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    return candidate.strip("._-") or "unknown"
