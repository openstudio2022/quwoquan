"""Research isolation runtime proof 文档组装与 create-once 写入。

本模块是 ``research_isolation_runtime_probe`` 的职责伴生模块，承载 PASS 文档
的键契约、checksum、组装校验与 O_EXCL create-once 写入；不触碰任何 HTTP 边界。
文档语义（字段、唯一性、checksum）与
``quwoquan_data/scripts/content/release/environment/research_isolation_proof.py``
和 ``research_isolation_verification.py`` 逐点对齐。公开导入路径保持在
``quwoquan_ops.cli.lib.research_isolation_runtime_probe``，此处符号经入口模块
re-export，消费者与测试 monkeypatch 点零漂移。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROBE_ENVIRONMENTS = ("alpha", "beta", "gamma")

#: PASS 文档顶层键集合，必须与 research_isolation_verification schema 与
#: quwoquan_ops.cli.lib.research_content_isolation._PASS_KEYS 完全一致。
PASS_DOCUMENT_KEYS = frozenset(
    {
        "schema",
        "environment",
        "releaseId",
        "manifestDigest",
        "releaseClass",
        "productLifecycleState",
        "verifyRunId",
        "policyRef",
        "policySha256",
        "outcome",
        "subjectHash",
        "identityIssuance",
        "identityAttestation",
        "internalAppReadback",
        "anonymousContentProbe",
        "anonymousMediaProbe",
        "networkExposureReadback",
        "deniedCapabilities",
        "signedMedia",
        "positiveReadback",
        "verifiedAt",
        "verificationChecksum",
    }
)

_SEGMENT_KEYS = frozenset(
    {
        "subjectHash",
        "identityIssuance",
        "identityAttestation",
        "internalAppReadback",
        "anonymousContentProbe",
        "anonymousMediaProbe",
        "networkExposureReadback",
        "deniedCapabilities",
        "signedMedia",
        "positiveReadback",
    }
)


class ResearchIsolationProbeError(RuntimeError):
    """结构化探针失败；code 采用 MODULE.KIND.REASON 形态。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _document_checksum(value: Mapping[str, Any]) -> str:
    """与 research_isolation_verification._document_checksum 字节等价。"""

    return _digest_bytes(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_segment(value: str, *, label: str) -> str:
    text = str(value or "").strip()
    candidate = Path(text)
    if (
        not text
        or text in {".", ".."}
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or "/" in text
        or "\\" in text
    ):
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            f"{label} must be one safe path segment",
        )
    return text


def _segment_operations(segments: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    denied = segments["deniedCapabilities"]
    signed = segments["signedMedia"]
    rows = [
        segments["identityIssuance"]["operation"],
        segments["identityAttestation"]["operation"],
        segments["internalAppReadback"]["operation"],
        segments["anonymousContentProbe"]["operation"],
        segments["anonymousMediaProbe"]["operation"],
        segments["networkExposureReadback"]["operation"],
        denied["share"]["operation"],
        denied["export"]["operation"],
        signed["issuanceOperation"],
        signed["accessOperation"],
        signed["auditReadbackOperation"],
        segments["positiveReadback"]["operation"],
    ]
    if any(not isinstance(row, Mapping) for row in rows):
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROOF_EVIDENCE_INCOMPLETE",
            "runtime proof segments must carry all 12 operations",
        )
    return rows


def build_runtime_proof_document(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    policy_sha256: str,
    segments: Mapping[str, Any],
    verified_at: str | None = None,
) -> dict[str, Any]:
    """组装带 checksum 的 PASS 文档；requestId/traceId 全局唯一必须成立。"""

    environment = _safe_segment(environment, label="environment")
    release_id = _safe_segment(release_id, label="releaseId")
    verify_run_id = _safe_segment(verify_run_id, label="verifyRunId")
    if environment not in _PROBE_ENVIRONMENTS:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROBE_INPUT_INVALID",
            "environment must be one of alpha/beta/gamma",
        )
    for label, digest in (
        ("manifestDigest", manifest_digest),
        ("policySha256", policy_sha256),
    ):
        if _DIGEST.fullmatch(str(digest or "")) is None:
            raise ResearchIsolationProbeError(
                "OPS.RESEARCH.PROBE_INPUT_INVALID",
                f"{label} must be a canonical sha256 digest",
            )
    if set(segments) != _SEGMENT_KEYS:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROOF_EVIDENCE_INCOMPLETE",
            "runtime proof segments do not match the PASS evidence contract",
        )
    operations = _segment_operations(segments)
    request_ids = [str(row.get("requestId") or "") for row in operations]
    trace_ids = [str(row.get("traceId") or "") for row in operations]
    if (
        any(not value for value in request_ids)
        or any(not value for value in trace_ids)
        or len(request_ids) != len(set(request_ids))
        or len(trace_ids) != len(set(trace_ids))
    ):
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROOF_EVIDENCE_REUSED",
            "operation requestId/traceId must be globally unique across "
            "all 12 probe operations",
        )
    document: dict[str, Any] = {
        "schema": "quwoquan_data.research_isolation_verification",
        "environment": environment,
        "releaseId": release_id,
        "manifestDigest": manifest_digest,
        "releaseClass": "research",
        "productLifecycleState": "research",
        "verifyRunId": verify_run_id,
        "policyRef": f"quwoquan_ops/environments/{environment}/runtime.yaml",
        "policySha256": policy_sha256,
        "outcome": "PASS",
        **{key: segments[key] for key in sorted(_SEGMENT_KEYS)},
        "verifiedAt": verified_at or _utc_now_iso(),
    }
    document["verificationChecksum"] = _document_checksum(document)
    if set(document) != PASS_DOCUMENT_KEYS:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROOF_EVIDENCE_INCOMPLETE",
            "runtime proof document keys drift from the PASS contract",
        )
    return document


def write_runtime_proof_create_once(
    path: Path,
    document: Mapping[str, Any],
) -> Path:
    """O_EXCL create-once 写入；目标已存在（含 symlink）即失败。"""

    payload = (
        json.dumps(dict(document), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROOF_ALREADY_EXISTS",
            f"runtime proof path is already occupied: {path}",
        )
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise ResearchIsolationProbeError(
            "OPS.RESEARCH.PROOF_ALREADY_EXISTS",
            f"runtime proof already exists (create-once): {path}",
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


__all__ = [
    "PASS_DOCUMENT_KEYS",
    "ResearchIsolationProbeError",
    "build_runtime_proof_document",
    "write_runtime_proof_create_once",
]
