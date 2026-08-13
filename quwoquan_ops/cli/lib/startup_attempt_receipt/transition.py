"""startup attempt 状态机 transition（逐字搬移）。

``startup_attempt_path`` / ``_prevalidate_write_path`` 是测试的 patch 锚点，
一律经 ``_pkg.`` 属性访问。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import quwoquan_ops.cli.lib.startup_attempt_receipt as _pkg

from .constants import (
    SCHEMA,
    STATUSES,
    WORKLOADS,
    _DIGEST,
    _IMMUTABLE_RECEIPT_IDENTITY_FIELDS,
    _TRANSITIONS,
)
from .fanout_transaction import (
    _fanout_destinations,
    _recover_fanout_transaction,
    _transactional_fanout_write,
)
from .receipt_contract import _read, _utc_now, validate_startup_attempt


def transition_startup_attempt(
    *,
    env: str,
    target: str,
    attempt_id: str,
    status: str,
    workload: str = "",
    compose_project: str = "",
    candidate_digest: str = "",
    configuration_digest: str = "",
    provider_runtime_digest: str = "",
    observability_log_sink_digest: str = "",
    image_transport_tag: str = "",
    image_composition: Mapping[str, Any] | None = None,
    run_root: str = "",
    failure: str = "",
    cleanup_failure: str = "",
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"startup attempt status is invalid: {status}")
    path = _pkg.startup_attempt_path(target)
    _recover_fanout_transaction(
        path,
        expected_env=env,
        expected_target=target,
    )
    previous = _read(path)
    previous_status = str(previous.get("status")) if previous else None
    if status not in _TRANSITIONS.get(previous_status, set()):
        raise ValueError(
            f"startup attempt transition is invalid: {previous_status!r} -> {status!r}"
        )
    normalized_attempt = str(attempt_id or "").strip()
    if status == "prepared":
        if not normalized_attempt:
            raise ValueError("prepared startup attempt requires attemptId")
        if previous is not None and normalized_attempt == previous.get("attemptId"):
            raise ValueError("prepared startup attempt requires a new attemptId")
        started_at = _utc_now()
        identity = {
            "env": str(env or "").strip(),
            "target": str(target or "").strip(),
            "workload": str(workload or "").strip(),
            "composeProject": str(compose_project or "").strip(),
            "candidateDigest": str(candidate_digest or "").strip(),
            "configurationDigest": str(configuration_digest or "").strip(),
            "providerRuntimeDigest": str(provider_runtime_digest or "").strip(),
            "observabilityLogSinkDigest": str(
                observability_log_sink_digest or ""
            ).strip(),
            "imageTransportTag": str(image_transport_tag or "").strip(),
            "imageComposition": dict(image_composition or {}),
            "runRoot": str(run_root or "").strip(),
        }
        if identity["workload"] not in WORKLOADS:
            raise ValueError("prepared startup attempt requires workload")
        if not identity["composeProject"]:
            raise ValueError("prepared startup attempt requires Compose project")
        if _DIGEST.fullmatch(str(identity["candidateDigest"])) is None:
            raise ValueError("prepared startup attempt requires candidate digest")
        if _DIGEST.fullmatch(str(identity["configurationDigest"])) is None:
            raise ValueError("prepared startup attempt requires configuration digest")
        if _DIGEST.fullmatch(str(identity["providerRuntimeDigest"])) is None:
            raise ValueError("prepared startup attempt requires Provider runtime digest")
        if identity["workload"] in {"full", "content-commercial"} and _DIGEST.fullmatch(
            str(identity["observabilityLogSinkDigest"])
        ) is None:
            raise ValueError(
                "prepared startup attempt requires observability log-sink digest"
            )
        if not identity["imageComposition"]:
            raise ValueError("prepared startup attempt requires image composition")
        if identity["imageTransportTag"] != identity["imageComposition"].get(
            "imageVersion"
        ):
            raise ValueError("prepared startup attempt image composition mismatch")
    else:
        if previous is None:
            raise ValueError("startup attempt transition requires an existing receipt")
        if normalized_attempt and normalized_attempt != previous.get("attemptId"):
            raise ValueError("startup attempt identity mismatch")
        normalized_attempt = str(previous["attemptId"])
        started_at = str(previous["startedAt"])
        assert previous is not None
        supplied_identity = {
            "workload": workload,
            "composeProject": compose_project,
            "candidateDigest": candidate_digest,
            "configurationDigest": configuration_digest,
            "providerRuntimeDigest": provider_runtime_digest,
            "observabilityLogSinkDigest": observability_log_sink_digest,
            "imageTransportTag": image_transport_tag,
            "runRoot": run_root,
        }
        for field, supplied in supplied_identity.items():
            normalized = str(supplied or "").strip()
            if normalized and normalized != str(previous.get(field) or "").strip():
                raise ValueError(f"startup attempt identity mismatch: {field}")
        if image_composition is not None and dict(image_composition) != previous.get(
            "imageComposition"
        ):
            raise ValueError("startup attempt identity mismatch: imageComposition")
        identity = {
            field: previous[field]
            for field in (
                "env",
                "target",
                "workload",
                "composeProject",
                "candidateDigest",
                "configurationDigest",
                "providerRuntimeDigest",
                "observabilityLogSinkDigest",
                "imageTransportTag",
                "imageComposition",
                "runRoot",
            )
        }

    payload = {
        "schema": SCHEMA,
        "attemptId": normalized_attempt,
        "env": identity["env"],
        "target": identity["target"],
        "status": status,
        "workload": identity["workload"],
        "composeProject": identity["composeProject"],
        "candidateDigest": identity["candidateDigest"],
        "configurationDigest": identity["configurationDigest"],
        "providerRuntimeDigest": identity["providerRuntimeDigest"],
        "observabilityLogSinkDigest": identity["observabilityLogSinkDigest"],
        "imageTransportTag": identity["imageTransportTag"],
        "imageComposition": identity["imageComposition"],
        "runRoot": identity["runRoot"],
        "startedAt": started_at,
        "updatedAt": _utc_now(),
        "failure": str(failure or "").strip() or None,
        "cleanupFailure": str(cleanup_failure or "").strip() or None,
    }
    if payload["env"] != env or payload["target"] != target:
        raise ValueError("startup attempt target identity mismatch")
    validate_startup_attempt(payload, expected_env=env, expected_target=target)
    run_receipt_path: Path | None = None
    run_path_text = str(payload["runRoot"] or "").strip()
    if run_path_text:
        run_receipt_path = Path(run_path_text) / "startup_attempt.json"
        existing_run_receipt = _read(run_receipt_path)
        if existing_run_receipt is not None:
            if existing_run_receipt["attemptId"] != payload["attemptId"]:
                raise ValueError(
                    "startup attempt runRoot already belongs to a different attempt"
                )
            for field in _IMMUTABLE_RECEIPT_IDENTITY_FIELDS:
                if existing_run_receipt[field] != payload[field]:
                    raise ValueError(
                        f"startup attempt runRoot identity mismatch: {field}"
                    )
    destinations = _fanout_destinations(path, payload)
    for destination in destinations:
        _pkg._prevalidate_write_path(destination)
    _transactional_fanout_write(path, destinations, payload)
    return payload
