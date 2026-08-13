"""Input loading, canonical destinations and stdout shaping for the source-pool CLI.

CLI 薄绑定只负责参数解析与 handler 分发；把「读入 → typed 失败归一 → canonical
落点派生 → 输出成型」这组无状态转换放在这里，让 handler 保持薄。
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json

from content.source.research.scale_source_pool import (
    SOURCE_POOL_INVALID,
    ScaleSourcePoolError,
)
from content.source.research.scale_source_pool_candidates import (
    validate_scale_source_pool_candidates,
)


def typed_error(error: Exception) -> ScaleSourcePoolError:
    if isinstance(error, ScaleSourcePoolError):
        return error
    code = str(getattr(error, "code", "") or "").strip()
    raw_issues = getattr(error, "issues", None)
    if code and isinstance(raw_issues, tuple | list):
        return ScaleSourcePoolError(code, raw_issues)
    issue = str(getattr(error, "issue", "") or "").strip()
    if code and issue:
        return ScaleSourcePoolError(code, [issue])
    return ScaleSourcePoolError(SOURCE_POOL_INVALID, [str(error)])


def load_object(path: str, *, label: str) -> dict[str, Any]:
    try:
        payload = read_json(Path(path).expanduser().resolve())
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise typed_error(exc) from exc
    if not isinstance(payload, dict):
        raise ScaleSourcePoolError(SOURCE_POOL_INVALID, [f"{label} must be an object"])
    return payload


def load_candidates(path: str) -> list[Mapping[str, Any]]:
    try:
        payload = read_json(Path(path).expanduser().resolve())
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise typed_error(exc) from exc
    if (
        isinstance(payload, dict)
        and payload.get("schema") == "quwoquan_data.scale_source_pool_candidates"
    ):
        payload = validate_scale_source_pool_candidates(payload)
    candidates = payload.get("candidates") if isinstance(payload, dict) else payload
    if not isinstance(candidates, list) or any(
        not isinstance(candidate, Mapping) for candidate in candidates
    ):
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            ["candidates input must be an array of objects"],
        )
    return candidates


def load_array(path: str, *, label: str) -> list[Mapping[str, Any]]:
    try:
        payload = read_json(Path(path).expanduser().resolve())
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise typed_error(exc) from exc
    if not isinstance(payload, list) or any(not isinstance(row, Mapping) for row in payload):
        raise ScaleSourcePoolError(SOURCE_POOL_INVALID, [f"{label} must be an array of objects"])
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def canonical_pool_destination(
    plan: Mapping[str, Any],
    *,
    output_root: Path,
) -> Path:
    target_scale = str(plan.get("targetScale") or "").strip().lower()
    digest = str(plan.get("planDigest") or "").removeprefix("sha256:")
    if not target_scale or len(digest) != 64:
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            ["targetScale/planDigest cannot derive canonical pool path"],
        )
    return output_root / "scale-source-pools" / target_scale / f"{digest}.json"


def canonical_candidates_destination(
    candidates: Mapping[str, Any],
    *,
    output_root: Path,
) -> Path:
    target_scale = str(candidates.get("targetScale") or "").strip().lower()
    digest = str(candidates.get("candidatesDigest") or "").removeprefix("sha256:")
    if not target_scale or len(digest) != 64:
        raise ScaleSourcePoolError(
            SOURCE_POOL_INVALID,
            ["targetScale/candidatesDigest cannot derive canonical candidate path"],
        )
    return (
        output_root
        / "scale-source-pool-candidates"
        / target_scale
        / f"{digest}.json"
    )


def print_document(document: Mapping[str, Any]) -> None:
    print(json.dumps(dict(document), ensure_ascii=False, indent=2, sort_keys=True))
