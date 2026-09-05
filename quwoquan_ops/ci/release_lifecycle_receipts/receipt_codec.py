"""release lifecycle receipts 的摘要、时间戳与 canonical receipt 组装原语。

原单文件 ``render_release_lifecycle_receipts.py`` 拆分出的编解码子模块。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .constants import STAGES


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _digest_file(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _receipt_id(receipt: dict[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receiptId", None)
    return hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return payload


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} timestamp is missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} timestamp has no timezone")
    return value


def _manifest_source(manifest: dict[str, Any]) -> tuple[str, str, str]:
    candidate = str(manifest["releaseCompositionId"])
    source = manifest["source"]
    return candidate, str(source["gitSha"]), str(source["treeDigest"])


def _canonical_receipt(
    *,
    schema: str,
    status: str,
    manifest: dict[str, Any],
    evidence_projection: dict[str, Any],
    verified_at: str,
) -> dict[str, Any]:
    candidate, git_sha, tree_digest = _manifest_source(manifest)
    return {
        "schema": schema,
        "environment": "prod",
        "status": status,
        "releaseCompositionId": candidate,
        "sourceGitSha": git_sha,
        "sourceTreeDigest": tree_digest,
        "evidenceDigest": _digest_bytes(_canonical_bytes(evidence_projection)),
        "evidence": evidence_projection,
        "verifiedAt": verified_at,
    }


def _parse_binding(values: list[str], label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for raw in values:
        stage, separator, path = raw.partition("=")
        if not separator or stage not in STAGES or not path:
            raise ValueError(f"{label} must use STAGE=PATH")
        if stage in result:
            raise ValueError(f"duplicate {label} stage: {stage}")
        result[stage] = Path(path).expanduser().resolve()
    return result


def _validate_archive_prefix(value: str) -> str:
    normalized = value.strip().strip("/")
    if (
        not normalized
        or normalized.startswith(".")
        or ".." in Path(normalized).parts
        or Path(normalized).is_absolute()
    ):
        raise ValueError("release evidence archive prefix is unsafe")
    return normalized


def _window_seconds(value: object) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)([smh])", str(value or "").strip())
    if match is None:
        raise ValueError("SLO soak window is invalid")
    multiplier = {"s": 1, "m": 60, "h": 3600}[match.group(2)]
    return int(match.group(1)) * multiplier
