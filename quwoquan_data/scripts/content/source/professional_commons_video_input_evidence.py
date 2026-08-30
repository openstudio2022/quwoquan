"""Create-once 落盘、路径安全引用与独立人审证据链（Commons 视频输入）。

Commons 公开视频进入统一 acquisition 链路前，必须留下可复核的准入证据：
create-once 写入保证同一 candidate 不被就地篡改，safe ref/file 保证证据不逃逸
acquisition root，review evidence 把 reviewer 的 request/attempt 与 digest 绑定，
replay 时可逐项校验漂移。
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.io import read_json
from content.source.professional_safety_evidence import file_sha256

REVIEW_FIELDS = frozenset(
    {
        "status",
        "entityMatch",
        "privacyRisk",
        "minorRisk",
        "maliciousMediaRisk",
        "watermarkStatus",
        "qualityStatus",
        "findings",
    }
)


class CommonsVideoInputError(RuntimeError):
    """Commons 公开视频输入无法形成可复核准入的 typed failure。"""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def digest(value: object) -> str:
    body = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def write_once(path: Path, value: Mapping[str, Any]) -> Path:
    body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != body:
            raise CommonsVideoInputError(
                "DATA.SOURCE.REVIEW_CREATE_ONCE_CONFLICT",
                f"create-once collision: {path}",
            ) from None
        return path
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def safe_ref(path: Path, root: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved == resolved_root or resolved_root not in resolved.parents:
        raise CommonsVideoInputError(
            "DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE",
            f"evidence escapes Commons acquisition root: {path}",
        )
    return resolved.relative_to(resolved_root).as_posix()


def safe_file(root: Path, ref: str) -> Path:
    relative = Path(str(ref or ""))
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    if (
        not str(relative)
        or relative.is_absolute()
        or ".." in relative.parts
        or resolved_root not in candidate.parents
        or candidate.is_symlink()
        or not candidate.is_file()
    ):
        raise CommonsVideoInputError(
            "DATA.SOURCE.REVIEW_EVIDENCE_UNSAFE",
            f"review evidence reference is unsafe: {ref}",
        )
    return candidate


def parse_judgment(text: str) -> dict[str, Any] | None:
    candidates = [text.strip()]
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    for value in candidates:
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict) and set(parsed) == REVIEW_FIELDS:
            return parsed
    return None


__all__ = [
    "CommonsVideoInputError", "REVIEW_FIELDS", "digest", "parse_judgment",
    "safe_file", "safe_ref", "write_once",
]
