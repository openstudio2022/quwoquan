"""债务基线 YAML 的解析与校验。"""

from __future__ import annotations

from pathlib import Path

from .constants import BASELINE_SCHEMA, DIGEST_RE, PATH_RE, REQUIRED_BUCKETS
from .fsscan import _load_yaml_mapping
from .models import HitSummary


def _parse_entries(value: object, *, label: str) -> dict[str, HitSummary]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是 mapping")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"{label}.entries 必须是 list")
    parsed: dict[str, HitSummary] = {}
    seen_order: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{label}.entries 条目必须是 mapping")
        path = str(entry.get("path") or "").strip()
        count = entry.get("count")
        digest = str(entry.get("digest") or "").strip()
        if not PATH_RE.fullmatch(path) or "*" in path:
            raise ValueError(f"{label}: 基线只接受精确相对路径，不接受通配符: {path!r}")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError(f"{label}: {path} count 必须是正整数")
        if DIGEST_RE.fullmatch(digest) is None:
            raise ValueError(f"{label}: {path} digest 必须是 canonical sha256")
        if path in parsed:
            raise ValueError(f"{label}: 重复路径 {path}")
        parsed[path] = HitSummary(count=count, digest=digest, samples=())
        seen_order.append(path)
    if seen_order != sorted(seen_order):
        raise ValueError(f"{label}.entries 必须按 path 升序")
    for required in ("owner", "retirement_condition"):
        if not str(value.get(required) or "").strip():
            raise ValueError(f"{label}.{required} 必填")
    return parsed


def load_baseline(path: Path) -> tuple[dict[str, dict[str, HitSummary]], dict]:
    document = _load_yaml_mapping(path, label="vertical architecture baseline")
    if document.get("schema") != BASELINE_SCHEMA:
        raise ValueError(f"baseline schema 必须是 {BASELINE_SCHEMA}")
    allowed_sections = {"schema", "governance", *REQUIRED_BUCKETS}
    unsupported_sections = sorted(set(document) - allowed_sections)
    if unsupported_sections:
        raise ValueError(
            "baseline 不再接受 travel-service allowance/dependency 或其他迁移期 section: "
            + ", ".join(unsupported_sections)
        )
    governance = document.get("governance")
    if not isinstance(governance, dict):
        raise ValueError("baseline.governance 必须是 mapping")
    for required in ("owner", "reason", "retirement_condition"):
        if not str(governance.get(required) or "").strip():
            raise ValueError(f"baseline.governance.{required} 必填")

    buckets: dict[str, dict[str, HitSummary]] = {}
    for name in REQUIRED_BUCKETS:
        buckets[name] = _parse_entries(document.get(name), label=name)
    return buckets, document
