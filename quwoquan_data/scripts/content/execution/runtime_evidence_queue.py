"""Resolve runtime evidence queues only from immutable execution envelopes."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.control_types import QueueBackend

from content.execution.queue_backend import (
    load_execution_queue_backend,
    resolve_execution_queue_backend,
)
from content.execution.runtime_evidence_contract import (
    CARRIERS,
    ProviderBinding,
    RuntimeEvidenceError,
    canonical_digest,
)
from content.execution.runtime_evidence_sampling import (
    LocalQueueEvidenceProvider,
    QueueEvidenceProvider,
)


class QueueEvidenceBlocker(RuntimeEvidenceError):
    """Typed fail-closed result for a missing governed live queue observer."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _frozen_envelopes(
    execution_ids: Mapping[str, str],
) -> tuple[QueueBackend, list[dict[str, Any]]]:
    if set(execution_ids) != set(CARRIERS):
        raise QueueEvidenceBlocker(
            "DATA.RUNTIME_EVIDENCE.QUEUE_LANE_SET_INVALID",
            "exactly homepage/article/image/video queue envelopes are required",
        )
    rows: list[dict[str, Any]] = []
    backends: set[QueueBackend] = set()
    for carrier in CARRIERS:
        execution_id = str(execution_ids[carrier])
        try:
            backend = resolve_execution_queue_backend(
                execution_id,
                requested=None,
            )
            envelope = load_execution_queue_backend(execution_id)
        except (OSError, TypeError, ValueError) as exc:
            raise QueueEvidenceBlocker(
                "DATA.RUNTIME_EVIDENCE.QUEUE_ENVELOPE_INVALID",
                f"{carrier}/{execution_id}: {exc}",
            ) from exc
        if envelope.get("queueBackend") != backend.value:
            raise QueueEvidenceBlocker(
                "DATA.RUNTIME_EVIDENCE.QUEUE_ENVELOPE_BACKEND_DRIFT",
                f"{carrier}/{execution_id}",
            )
        backends.add(backend)
        row = {
            "carrier": carrier,
            "executionId": execution_id,
            "queueBackend": backend.value,
            "envelopeDigest": envelope["envelopeDigest"],
            "queuePolicyDigest": envelope["queuePolicyDigest"],
            "executionManifestDigest": envelope.get("executionManifestDigest"),
            "sourceDigest": envelope.get("sourceDigest"),
            "targetSetDigest": envelope.get("targetSetDigest"),
        }
        if backend is QueueBackend.RELIABLE_TASK:
            row.update(
                {
                    "observerBinaryRef": envelope.get("observerBinaryRef"),
                    "observerBinarySha256": envelope.get(
                        "observerBinarySha256"
                    ),
                }
            )
        rows.append(row)
    if len(backends) != 1:
        raise QueueEvidenceBlocker(
            "DATA.RUNTIME_EVIDENCE.QUEUE_BACKEND_MIXED",
            "one runtime evidence session cannot mix queue backends",
        )
    return next(iter(backends)), rows


def resolve_frozen_queue_evidence_provider(
    execution_ids: Mapping[str, str],
) -> QueueEvidenceProvider:
    """Return the observer selected only by immutable execution envelopes."""
    backend, envelopes = _frozen_envelopes(execution_ids)
    configuration_digest = canonical_digest(
        {
            "schema": "quwoquan_data.runtime_queue_evidence_binding",
            "version": 1,
            "backend": backend.value,
            "executionEnvelopes": envelopes,
        }
    )
    if backend is QueueBackend.RELIABLE_TASK:
        from content.execution.runtime_evidence_reliabletask import (
            ReliableTaskQueueEvidenceProvider,
        )

        return ReliableTaskQueueEvidenceProvider(envelopes=envelopes)
    return LocalQueueEvidenceProvider(
        binding=ProviderBinding(
            provider_id="local_object_queue_v1",
            configuration_digest=configuration_digest,
        )
    )


__all__ = [
    "QueueEvidenceBlocker",
    "resolve_frozen_queue_evidence_provider",
]
