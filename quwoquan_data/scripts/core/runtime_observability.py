"""Canonical runtime diagnostics for data-engineering execution boundaries."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Mapping

from core.generated.runtime_log_catalog import (
    FAILURE_CODES,
    FORBIDDEN_ATTRIBUTE_KEYS,
    FORBIDDEN_FIELDS,
    HIGH_CARDINALITY_METRIC_KEYS,
    MAX_ATTRIBUTES,
    MAX_ATTRIBUTES_BYTES,
    MAX_ATTRIBUTE_KEY_LENGTH,
    MAX_ATTRIBUTE_VALUE_LENGTH,
    MAX_MESSAGE_BYTES,
    OBSERVABILITY_SCHEMA,
    SIGNAL_REGISTRY,
)


_SECRET_VALUE = re.compile(
    r"(access_token|token|authcode|authorization|signature|secret)=([^&#\s]+)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class DataRuntimeLogResource:
    environment: str
    service: str = "quwoquan_data"
    component: str = ""

    def wire(self) -> dict[str, str]:
        values = {
            "sourceType": "data",
            "service": self.service,
            "environment": self.environment,
        }
        if self.component:
            values["component"] = self.component
        return values


class DataRuntimeLogger:
    """Append-only JSONL writer for execution/stage facts.

    This module deliberately records only canonical envelope fields.  Stage
    reports remain the durable business evidence; this stream makes failures,
    durations and correlations queryable without leaking source content.
    """

    def __init__(
        self,
        path: Path,
        *,
        resource: DataRuntimeLogResource,
        execution_id: str = "",
        work_package_id: str = "",
        environment_run_id: str = "",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._path = path
        self._resource = resource
        self._execution_id = execution_id
        self._work_package_id = work_package_id
        self._environment_run_id = environment_run_id
        self._now = now or (lambda: datetime.now(UTC))

    def runtime(
        self,
        *,
        event: str,
        result: str,
        message: str,
        attributes: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        return self._append(
            log_kind="runtime",
            severity="INFO",
            signal="data.runtime.stage",
            message=message,
            event=event,
            result=result,
            attributes=attributes,
        )

    def exception(
        self,
        *,
        error_code: str,
        message: str,
        failure_point: str = "",
        attributes: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        merged = dict(attributes or {})
        if failure_point:
            merged["failurePoint"] = failure_point
        return self._append(
            log_kind="exception",
            severity="ERROR",
            signal="data.exception.stage",
            message=message,
            error_code=error_code,
            fingerprint=_fingerprint(error_code, failure_point or message),
            attributes=merged,
        )

    def _append(
        self,
        *,
        log_kind: str,
        severity: str,
        signal: str,
        message: str,
        event: str = "",
        result: str = "",
        error_code: str = "",
        fingerprint: str = "",
        attributes: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        contract = SIGNAL_REGISTRY[signal]
        if contract["logKind"] != log_kind:
            raise ValueError(f"signal/log kind mismatch: {signal}/{log_kind}")
        timestamp = _iso(self._now())
        record: dict[str, object] = {
            "schema": OBSERVABILITY_SCHEMA,
            "recordId": _record_id(timestamp),
            "occurredAt": timestamp,
            "observedAt": timestamp,
            "logKind": log_kind,
            "severity": severity,
            "signal": signal,
            "message": _bounded(_redact(message), MAX_MESSAGE_BYTES),
            "resource": self._resource.wire(),
        }
        correlation = {
            key: value
            for key, value in {
                "executionId": self._execution_id,
                "workPackageId": self._work_package_id,
                "environmentRunId": self._environment_run_id,
            }.items()
            if value and key in contract["correlationKeys"]
        }
        if correlation:
            record["correlation"] = correlation
        if event:
            record["event"] = event
        if result:
            record["result"] = result
        if error_code:
            record["errorCode"] = error_code
        if fingerprint:
            record["fingerprint"] = fingerprint
        sanitized = _attributes(attributes or {}, set(contract["attributeAllowlist"]))
        if sanitized:
            record["attributes"] = sanitized
        target_path = self._path
        if self._path.name == "runtime.log" and log_kind != "runtime":
            target_path = self._path.with_name(f"{log_kind}.log")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
        return record


def default_data_exception_code() -> str:
    """Stable fallback used only when a caller has no domain-specific code."""
    return FAILURE_CODES["data_stage_failure"]


def _attributes(values: Mapping[str, object], allowlist: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    forbidden = {
        *_normalize_all(FORBIDDEN_FIELDS),
        *_normalize_all(FORBIDDEN_ATTRIBUTE_KEYS),
        *_normalize_all(HIGH_CARDINALITY_METRIC_KEYS),
    }
    for raw_key in sorted(values, key=str):
        key = str(raw_key).strip()
        normalized = _normalize(key)
        if (
            not key
            or key not in allowlist
            or len(key) > MAX_ATTRIBUTE_KEY_LENGTH
            or normalized in forbidden
            or any(item != "ip" and item in normalized for item in forbidden)
        ):
            continue
        value = values[raw_key]
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        result[key] = _bounded(_redact(text), MAX_ATTRIBUTE_VALUE_LENGTH)
        encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(result) > MAX_ATTRIBUTES or len(encoded) > MAX_ATTRIBUTES_BYTES:
            result.pop(key)
            break
    return result


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _record_id(timestamp: str) -> str:
    return f"r.{timestamp.replace(':', '').replace('-', '').replace('.', '')}.{secrets.token_hex(8)}"


def _fingerprint(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:24]


def _normalize(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _normalize_all(values: tuple[str, ...] | list[str]) -> set[str]:
    return {_normalize(value) for value in values}


def _redact(value: str) -> str:
    value = _BEARER.sub("Bearer ***", value)
    value = _SECRET_VALUE.sub(r"\1=***", value)
    return _EMAIL.sub("***", value)


def _bounded(value: str, max_bytes: int) -> str:
    if len(value.encode("utf-8")) <= max_bytes:
        return value
    suffix = "…"
    while value and len((value + suffix).encode("utf-8")) > max_bytes:
        value = value[:-1]
    return value + suffix
