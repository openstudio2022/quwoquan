from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import ROOT, utc_now, write_json
from quwoquan_ops.cli.lib.output_paths import (
    data_observability_run_dir,
    env_observability_run_dir,
    normalize_env,
)


OBSERVABILITY_ROOT = ROOT / ".qwq_output"
OBSERVABILITY_CONTRACT_VERSION = "observability.slim.v1"

ENVS = frozenset({"alpha", "beta", "gamma", "prod", "repo"})
LOG_KINDS = frozenset(
    {"deploy", "runtime", "access", "event", "exception", "audit"}
)
LEVELS = frozenset({"DEBUG", "INFO", "WARN", "ERROR"})
FORBIDDEN_INLINE_FIELDS = frozenset(
    {
        "schema" + "Version",
        "signal",
        "log" + "Kind",
        "env",
        "source" + "Type",
        "service",
        "component",
        "instanceId",
        "runId",
        "releaseId",
        "dataReleaseId",
        "sessionId",
        "timestamp",
        "severity",
        "message",
        "requestId",
        "traceId",
        "spanId",
    }
)
COMMON_LOG_FIELDS = frozenset({"ts", "level", "msg", "req", "trace", "span", "attrs"})
LOG_FILE_SUFFIX = ".log"
LOG_FIELD_ORDER = {
    "deploy": ("ts", "level", "step", "result", "msg"),
    "runtime": ("ts", "level", "event", "result", "req", "trace", "msg"),
    "access": ("ts", "level", "method", "route", "status", "durMs", "req", "trace", "msg"),
    "event": ("ts", "level", "event", "result", "req", "trace", "msg"),
    "exception": ("ts", "level", "err", "req", "trace", "msg"),
    "audit": ("ts", "level", "action", "target", "result", "msg"),
}
KIND_FIELDS = {
    kind: frozenset(fields) - {"ts", "level", "msg"}
    for kind, fields in LOG_FIELD_ORDER.items()
}
REQUIRED_KIND_FIELDS = {
    "deploy": frozenset({"step", "result"}),
    "runtime": frozenset({"event", "result"}),
    "access": frozenset({"method", "route", "status", "durMs"}),
    "event": frozenset({"event", "result"}),
    "exception": frozenset({"err"}),
    "audit": frozenset({"action", "target", "result"}),
}
ATTRS_MAX_BYTES = 4096
SECRET_KEY_PATTERN = re.compile(r"(password|passwd|secret|token|api[_-]?key|credential)", re.I)
RECORD_START_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T[^,]*,(DEBUG|INFO|WARN|ERROR),"
)


def run_dir(env_name: str, run_id: str) -> Path:
    env = normalize_env(env_name)
    if env == "data":
        return data_observability_run_dir(run_id)
    return env_observability_run_dir(env, run_id)


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
        if len(parts) > index + 1 and parts[index + 1] == "data":
            return "data"
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
    release_id: str = "",
    data_release_id: str = "",
) -> Path:
    manifest = {
        "contractVersion": OBSERVABILITY_CONTRACT_VERSION,
        "env": env_name,
        "runId": run_id,
        "command": command,
        "target": target,
        "releaseId": release_id,
        "dataReleaseId": data_release_id,
        "reportDir": _repo_rel(report_dir),
        "generatedAt": utc_now(),
    }
    path = base_dir / "manifest.json"
    write_json(path, manifest)
    return path


def append_log_line(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    kind = path.stem
    with path.open("a", encoding="utf-8") as handle:
        handle.write(format_log_record(kind, compact_log_payload(payload)) + "\n")


def compact_log_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: value for key, value in payload.items() if value not in ("", None, {}, [])}
    if "ts" not in cleaned:
        cleaned["ts"] = utc_now()
    if "level" not in cleaned:
        cleaned["level"] = "INFO"
    if "msg" not in cleaned:
        cleaned["msg"] = str(cleaned.get("event") or cleaned.get("step") or cleaned.get("action") or "")
    return cleaned


def format_log_record(kind: str, payload: dict[str, Any]) -> str:
    fields = LOG_FIELD_ORDER.get(kind)
    if not fields:
        raise ValueError(f"unknown log kind: {kind}")
    message = _message_with_attrs(payload)
    values: list[str] = []
    for field in fields:
        value = message if field == "msg" else payload.get(field, "")
        values.append(_field_text(value, allow_newline=field == "msg"))
    first, *continuation = values[-1].split("\n")
    line = ",".join(values[:-1] + [first])
    if continuation:
        line += "".join(f"\n\t{part}" for part in continuation)
    return line


def parse_log_records(kind: str, lines: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    records: list[dict[str, str]] = []
    issues: list[str] = []
    current: dict[str, str] | None = None
    current_line = 0
    for index, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        if raw_line.startswith((" ", "\t")):
            if current is None:
                issues.append(f"{index}: continuation without a record")
            else:
                current["msg"] = f"{current.get('msg', '')}\n{raw_line.lstrip()}"
            continue
        if not RECORD_START_PATTERN.match(raw_line):
            issues.append(f"{index}: log record must start with ts,level")
            current = None
            continue
        parsed, parse_issues = parse_log_line(kind, raw_line)
        if parse_issues:
            issues.extend(f"{index}: {issue}" for issue in parse_issues)
            current = None
            continue
        current = parsed
        current_line = index
        records.append(parsed)
        if len(records) >= 200:
            break
    return records, issues


def parse_log_line(kind: str, line: str) -> tuple[dict[str, str], list[str]]:
    fields = LOG_FIELD_ORDER.get(kind)
    if not fields:
        return {}, [f"unknown log kind: {kind}"]
    values = _split_fixed(line, len(fields))
    if len(values) != len(fields):
        return {}, [f"expected {len(fields)} comma fields, got {len(values)}"]
    return dict(zip(fields, values, strict=True)), []


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
    allowed = COMMON_LOG_FIELDS | KIND_FIELDS[kind]
    unknown = sorted(set(payload) - allowed)
    if unknown:
        issues.append(f"unknown field(s): {', '.join(unknown)}")
    forbidden = sorted(set(payload) & FORBIDDEN_INLINE_FIELDS)
    if forbidden:
        issues.append(f"forbidden repeated field(s): {', '.join(forbidden)}")
    for field in ("ts", "level", "msg"):
        if field not in payload or payload.get(field) in ("", None):
            issues.append(f"missing required field: {field}")
    level = str(payload.get("level") or "")
    if level and level not in LEVELS:
        issues.append(f"invalid level: {level}")
    for field in sorted(REQUIRED_KIND_FIELDS[kind]):
        if field not in payload or payload.get(field) in ("", None):
            issues.append(f"missing {kind} field: {field}")
    attrs = payload.get("attrs")
    if attrs is not None:
        if not isinstance(attrs, dict):
            issues.append("attrs must be an object")
        else:
            encoded = json.dumps(attrs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(encoded) > ATTRS_MAX_BYTES:
                issues.append(f"attrs too large: {len(encoded)} > {ATTRS_MAX_BYTES}")
            for key in _iter_attr_keys(attrs):
                if SECRET_KEY_PATTERN.search(key):
                    issues.append(f"attrs contains secret-like key: {key}")
                    break
    return issues


def validate_log_record(kind: str, payload: dict[str, str]) -> list[str]:
    issues = validate_log_payload(kind, payload)
    if any("," in str(payload.get(field, "")) for field in LOG_FIELD_ORDER.get(kind, ()) if field != "msg"):
        issues.append("non-message fields must not contain commas")
    return issues


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


def _message_with_attrs(payload: dict[str, Any]) -> str:
    message = str(payload.get("msg") or "")
    attrs = payload.get("attrs")
    if attrs in (None, {}, []):
        return message
    encoded = json.dumps(attrs, ensure_ascii=False, separators=(",", ":"))
    return f"{message} attrs={encoded}" if message else f"attrs={encoded}"


def _field_text(value: Any, *, allow_newline: bool = False) -> str:
    text = str(value if value is not None else "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not allow_newline:
        text = " ".join(text.splitlines())
        text = text.replace(",", "%2C")
    return text


def _split_fixed(line: str, field_count: int) -> list[str]:
    values: list[str] = []
    start = 0
    for _ in range(field_count - 1):
        index = line.find(",", start)
        if index < 0:
            return []
        values.append(line[start:index])
        start = index + 1
    values.append(line[start:])
    return values


def _repo_rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _safe_segment(value: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    return candidate.strip("._-") or "unknown"
