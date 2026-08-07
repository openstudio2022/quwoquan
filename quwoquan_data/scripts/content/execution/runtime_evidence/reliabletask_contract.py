"""Typed identity and digest values for the ReliableTask live observer."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from content.execution.runtime_evidence.reliabletask_process import observer_error


@dataclass(frozen=True, slots=True)
class ExpectedTask:
    job_id: str
    entity_ref: str
    stage: str
    source_revision: str

    def as_document(self) -> dict[str, str]:
        return {
            "jobId": self.job_id,
            "entityRef": self.entity_ref,
            "stage": self.stage,
            "sourceRevision": self.source_revision,
        }


@dataclass(frozen=True, slots=True)
class ExecutionTarget:
    carrier: str
    execution_id: str
    execution_envelope_digest: str
    expected_tasks: tuple[ExpectedTask, ...]
    campaign_binding: dict[str, object]


def sha256_digest(value: object) -> str:
    text = str(value or "").strip()
    if (
        not text.startswith("sha256:")
        or len(text) != 71
        or any(character not in "0123456789abcdef" for character in text[7:])
    ):
        raise observer_error("RESPONSE_INVALID", "sha256 digest is invalid")
    return text


def canonical_digest_any(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def campaign_binding(envelope: Mapping[str, Any]) -> dict[str, object]:
    source_digest = envelope.get("sourceDigest")
    if not isinstance(source_digest, Mapping):
        raise observer_error(
            "FROZEN_TARGET_INVALID",
            "campaign sourceDigest is invalid",
        )
    binding: dict[str, object] = {
        "rootExecutionId": envelope.get("rootExecutionId"),
        "campaignRunId": envelope.get("campaignRunId"),
        "campaignGeneration": envelope.get("campaignGeneration"),
        "campaignFencingToken": envelope.get("campaignFencingToken"),
        "campaignPlanDigest": envelope.get("campaignPlanDigest"),
        "campaignSourceRevision": envelope.get("campaignSourceRevision"),
        "campaignSourceDigest": source_digest.get("digest"),
        "campaignEntityCatalogDigest": envelope.get(
            "campaignEntityCatalogDigest"
        ),
    }
    if (
        not isinstance(binding["campaignGeneration"], int)
        or isinstance(binding["campaignGeneration"], bool)
        or int(binding["campaignGeneration"]) < 1
        or any(
            not isinstance(binding[field], str) or not str(binding[field]).strip()
            for field in ("rootExecutionId", "campaignRunId")
        )
    ):
        raise observer_error(
            "FROZEN_TARGET_INVALID",
            "campaign run identity is invalid",
        )
    for field in (
        "campaignFencingToken",
        "campaignPlanDigest",
        "campaignSourceRevision",
        "campaignSourceDigest",
        "campaignEntityCatalogDigest",
    ):
        sha256_digest(binding[field])
    return binding


__all__ = [
    "ExecutionTarget",
    "ExpectedTask",
    "campaign_binding",
    "canonical_digest_any",
    "sha256_digest",
]
