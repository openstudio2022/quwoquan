"""stackctl app 预检域 canonical Data release readiness 真相源家族。

从 stackctl.py 逐字迁出(批 5 曾判定留守;app-content 预检/UAT 域于批 6
迁出后,本家族随其主要消费者迁入本模块)。本模块保留 schema 常量与校验
原语:

- `_DATA_READINESS_SCHEMA` / `_DATA_ACTIVATION_SCHEMA` /
  `_DATA_LIFECYCLE_EXIT_SCHEMA` / `_DATA_READINESS_DIGEST_RE` /
  `_DATA_CONSUMER_READINESS_QUERY_NAMES` /
  `_DATA_COMMERCIAL_READINESS_QUERY_NAMES`:canonical Data 回执 schema 与
  查询名集合;
- `_data_readiness_segment` / `_data_release_readiness_path` /
  `_canonical_document_checksum` / `_validated_string_set`:路径段、
  checksum 与字符串集合校验原语;
- `_validate_data_activation_envelope` / `_validate_data_operation_evidence`:
  activation envelope 与 operation evidence 的 fail-closed 校验。

回执装载与身份绑定家族(`_load_test_data_release_readiness` /
`_load_data_release_readiness` / `_load_data_release_lifecycle_exit`)在
`commands/app_preflight_readiness.py`;本模块以薄 re-export 保持对
stackctl 的符号面零漂移。

verify_kinds / verify_shared / test_data_surface / content_acceptance 等
兄弟域模块与 app 预检域经 stackctl 命名空间消费本家族。测试经
``mock.patch.object(stackctl, ...)`` patch 本模块符号与协作符号,因此
函数体内一律经函数内延迟导入 `_stackctl` 属性访问(含本模块符号互调),
保持 monkeypatch 语义并避免顶层循环 import。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.content_release_readiness import ReadinessPhase

from quwoquan_ops.cli.commands.app_preflight_readiness import (
    _load_data_release_lifecycle_exit,
    _load_data_release_readiness,
    _load_test_data_release_readiness,
)


_DATA_READINESS_SCHEMA = "quwoquan_data.environment_release_readiness"
_DATA_ACTIVATION_SCHEMA = "quwoquan_data.environment_activation_envelope"
_DATA_LIFECYCLE_EXIT_SCHEMA = "quwoquan_data.environment_release_lifecycle_exit"
_DATA_READINESS_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# App 视频书唯一消费 premium_stream 池：consumer 与 commercial readiness 都
# 必须证明 premium_stream release-bound 非空读回（对齐 environment-topology-
# and-packaging spec；typed_video 绿不代表视频书绿）。
_DATA_CONSUMER_READINESS_QUERY_NAMES = frozenset(
    {
        "discovery_work",
        "typed_article",
        "typed_image",
        "typed_video",
        "homepage_recommend",
        "premium_stream",
    }
)
_DATA_COMMERCIAL_READINESS_QUERY_NAMES = frozenset(
    {*_DATA_CONSUMER_READINESS_QUERY_NAMES}
)


def _data_readiness_segment(value: str, *, label: str) -> str:
    segment = str(value or "").strip()
    candidate = Path(segment)
    if (
        not segment
        or segment in {".", ".."}
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or "/" in segment
        or "\\" in segment
    ):
        raise ValueError(f"{label} must be one non-empty path segment")
    return segment


def _data_release_readiness_path(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
) -> Path:
    import quwoquan_ops.cli.stackctl as _stackctl

    release_segment = _stackctl._data_readiness_segment(release_id, label="releaseId")
    verify_segment = _stackctl._data_readiness_segment(verify_run_id, label="verifyRunId")
    return (
        _stackctl.env_runs_root(environment)
        / "data-release"
        / release_segment
        / verify_segment
        / "release-readiness.json"
    )


def _canonical_document_checksum(document: dict[str, Any]) -> str:
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _validate_data_activation_envelope(
    receipt: dict[str, Any],
    *,
    evidence_root: Path,
    issues: list[str],
) -> None:
    """Recompute the environment-specific activation/import/readback binding."""
    import quwoquan_ops.cli.stackctl as _stackctl

    retired = sorted(
        field
        for field in ("appUatEnvelope", "appUatEnvelopeDigest")
        if field in receipt
    )
    if retired:
        issues.append(
            "Data readiness contains retired App UAT fields: " + ", ".join(retired)
        )

    import_ref = str(receipt.get("contentImportReportRef") or "").strip()
    import_path = (evidence_root / import_ref).resolve()
    try:
        import_path.relative_to(evidence_root)
        import_digest = "sha256:" + hashlib.sha256(import_path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        import_digest = ""
        issues.append("Data activation import report is missing or unsafe")
    expected: dict[str, Any] = {
        "schema": _stackctl._DATA_ACTIVATION_SCHEMA,
        "environment": receipt.get("environment"),
        "releaseId": receipt.get("releaseId"),
        "manifestDigest": receipt.get("manifestDigest"),
        "releaseClass": receipt.get("releaseClass"),
        "productLifecycleState": receipt.get("productLifecycleState"),
        "readinessPhase": receipt.get("readinessPhase"),
        "importRunId": receipt.get("importRunId"),
        "verifyRunId": receipt.get("verifyRunId"),
        "importReportRef": import_ref,
        "importReportDigest": import_digest,
    }
    if "sourceIdentities" in receipt or "sourceIdentitySetDigest" in receipt:
        expected["sourceIdentities"] = receipt.get("sourceIdentities")
        expected["sourceIdentitySetDigest"] = receipt.get(
            "sourceIdentitySetDigest"
        )
    else:
        expected["sourceRevision"] = receipt.get("sourceRevision")
        expected["sourceDigest"] = receipt.get("sourceDigest")
        expected["entityCatalogDigest"] = receipt.get("entityCatalogDigest")
    for field in ("milestone", "previousEnvironmentActivation"):
        if field in receipt:
            expected[field] = receipt.get(field)
    if receipt.get("readinessPhase") == ReadinessPhase.RESEARCH.value:
        isolation_ref = str(
            receipt.get("researchIsolationVerificationRef") or ""
        ).strip()
        isolation_digest = str(
            receipt.get("researchIsolationVerificationDigest") or ""
        ).strip()
        isolation_path = (evidence_root / isolation_ref).resolve()
        isolation: dict[str, Any] = {}
        try:
            isolation_path.relative_to(evidence_root)
            isolation_bytes = isolation_path.read_bytes()
            raw_isolation = json.loads(isolation_bytes)
            if not isinstance(raw_isolation, dict):
                raise ValueError("isolation receipt is not an object")
            isolation = raw_isolation
            if (
                "sha256:" + hashlib.sha256(isolation_bytes).hexdigest()
                != isolation_digest
            ):
                raise ValueError("isolation receipt digest drift")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issues.append(f"Data activation research isolation is invalid: {exc}")
        expected["researchIsolationPolicy"] = {
            "policyRef": isolation.get("policyRef"),
            "policyDigest": isolation.get("policySha256"),
            "verificationRef": isolation_ref,
            "verificationDigest": isolation_digest,
            "subjectHash": isolation.get("subjectHash"),
        }
    activation = receipt.get("activationEnvelope")
    if activation != expected:
        issues.append(
            "Data readiness activationEnvelope drifts from release/import/readback"
        )
    if receipt.get("activationEnvelopeDigest") != _stackctl._canonical_document_checksum(
        expected
    ):
        issues.append("Data readiness activationEnvelopeDigest drift")


def _validate_data_operation_evidence(
    value: object,
    *,
    label: str,
    expected_path: str,
    expected_page_id: str,
    expected_status: int,
    issues: list[str],
) -> tuple[str, str]:
    required = {
        "path",
        "pageId",
        "status",
        "requestId",
        "traceId",
        "startedAt",
        "endedAt",
        "durationMs",
    }
    if not isinstance(value, dict):
        issues.append(f"Data readiness {label} must be an object")
        return "", ""
    if set(value) != required:
        issues.append(
            f"Data readiness {label} must contain only canonical operation evidence"
        )
    if value.get("path") != expected_path:
        issues.append(f"Data readiness {label}.path is not canonical")
    if value.get("pageId") != expected_page_id:
        issues.append(f"Data readiness {label}.pageId is not canonical")
    if value.get("status") != expected_status:
        issues.append(f"Data readiness {label}.status must be {expected_status}")
    request_id = str(value.get("requestId") or "").strip()
    trace_id = str(value.get("traceId") or "").strip()
    started_at = str(value.get("startedAt") or "").strip()
    ended_at = str(value.get("endedAt") or "").strip()
    duration_ms = value.get("durationMs")
    if not request_id or not trace_id:
        issues.append(f"Data readiness {label} lacks requestId/traceId")
    if not started_at or not ended_at or ended_at < started_at:
        issues.append(f"Data readiness {label} timing is invalid")
    if (
        not isinstance(duration_ms, int)
        or isinstance(duration_ms, bool)
        or duration_ms < 0
    ):
        issues.append(f"Data readiness {label}.durationMs is invalid")
    return request_id, trace_id


def _validated_string_set(
    value: object,
    *,
    label: str,
    issues: list[str],
) -> set[str]:
    if not isinstance(value, list):
        issues.append(f"Data readiness {label} must be an array")
        return set()
    items = [str(item).strip() for item in value]
    if not items or any(not item for item in items) or len(items) != len(set(items)):
        issues.append(
            f"Data readiness {label} must contain unique non-empty strings"
        )
        return set(items)
    return set(items)
