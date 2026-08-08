"""Create-once observer binary identity bound to one immutable campaign plan."""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from core.io import read_json, write_json
from core.schema import assert_valid

from content.execution.campaign.submission import campaign_root
from content.execution.campaign.workspace import CampaignRuntimePaths
from content.execution.identity import validate_execution_id
from content.execution.runtime_evidence.reliabletask_observer_build import (
    observer_build_attestation_digest,
    prepare_controller_observer_binary,
)
from content.execution.runtime_evidence.reliabletask_process import (
    PreparedReliableTaskObserverBinary,
    ReliableTaskObserverBinaryBinding,
    validate_frozen_observer_binary,
)

CAMPAIGN_OBSERVER_BINARY_SCHEMA = (
    "quwoquan_data.content_campaign_observer_binary_envelope"
)
CAMPAIGN_OBSERVER_BINARY_REF = "observer_binary_envelope.json"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
ObserverPreparer = Callable[[], PreparedReliableTaskObserverBinary]


def _digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def campaign_observer_binary_path(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
) -> Path:
    return (
        campaign_root(
            validate_execution_id(root_execution_id),
            root=runtime.campaigns_root,
        )
        / CAMPAIGN_OBSERVER_BINARY_REF
    )


def _validate_envelope(
    payload: Mapping[str, Any],
    *,
    root_execution_id: str,
    plan_digest: str,
) -> ReliableTaskObserverBinaryBinding:
    assert_valid(
        dict(payload),
        "execution",
        "content_campaign_observer_binary_envelope",
        label=f"campaign observer binary:{root_execution_id}",
    )
    stable = {
        key: value for key, value in payload.items() if key != "envelopeDigest"
    }
    if payload.get("schema") != CAMPAIGN_OBSERVER_BINARY_SCHEMA:
        raise ValueError("campaign observer binary schema mismatch")
    if str(payload.get("rootExecutionId") or "") != root_execution_id:
        raise ValueError("campaign observer binary root execution mismatch")
    if str(payload.get("planDigest") or "") != plan_digest:
        raise ValueError("campaign observer binary plan digest drift")
    if str(payload.get("envelopeDigest") or "") != _digest(stable):
        raise ValueError("campaign observer binary envelope digest mismatch")
    source_digest = str(payload.get("observerSourceDigest") or "")
    if _DIGEST.fullmatch(source_digest) is None:
        raise ValueError("campaign observer binary source digest is invalid")
    binding = ReliableTaskObserverBinaryBinding(
        ref=str(payload.get("observerBinaryRef") or ""),
        sha256=str(payload.get("observerBinarySha256") or ""),
    )
    source_segment = source_digest.removeprefix("sha256:")
    if Path(binding.ref).parent.name != source_segment:
        raise ValueError("campaign observer binary ref/source identity mismatch")
    expected_attestation = observer_build_attestation_digest(
        source_digest=source_digest,
        binding=binding,
    )
    if (
        str(payload.get("observerBuildAttestationDigest") or "")
        != expected_attestation
    ):
        raise ValueError("campaign observer binary build attestation drift")
    validate_frozen_observer_binary(binding)
    return binding


def resolve_campaign_observer_binary(
    runtime: CampaignRuntimePaths,
    root_execution_id: str,
    *,
    plan_digest: str,
    preparer: ObserverPreparer = prepare_controller_observer_binary,
) -> ReliableTaskObserverBinaryBinding:
    """Create once from controller source, then recover only the frozen identity."""
    root_id = validate_execution_id(root_execution_id)
    path = campaign_observer_binary_path(runtime, root_id)
    if path.is_file():
        payload = read_json(path)
        if not isinstance(payload, dict):
            raise TypeError("campaign observer binary envelope must be an object")
        return _validate_envelope(
            payload,
            root_execution_id=root_id,
            plan_digest=plan_digest,
        )

    prepared = preparer()
    stable = {
        "schema": CAMPAIGN_OBSERVER_BINARY_SCHEMA,
        "rootExecutionId": root_id,
        "planDigest": plan_digest,
        "observerSourceDigest": prepared.source_digest,
        "observerBinaryRef": prepared.binding.ref,
        "observerBinarySha256": prepared.binding.sha256,
        "observerBuildAttestationDigest": prepared.build_attestation_digest,
    }
    payload = {**stable, "envelopeDigest": _digest(stable)}
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, payload)
    return _validate_envelope(
        payload,
        root_execution_id=root_id,
        plan_digest=plan_digest,
    )


__all__ = [
    "CAMPAIGN_OBSERVER_BINARY_REF",
    "CAMPAIGN_OBSERVER_BINARY_SCHEMA",
    "campaign_observer_binary_path",
    "resolve_campaign_observer_binary",
]
