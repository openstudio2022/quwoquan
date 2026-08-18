"""Internal provider SPI and candidate-bound control-plane model."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol

from .api import BusinessObjectRef, CapabilityRef, CapabilityRequest, ReceiptRef


@dataclass(frozen=True)
class CandidateBinding:
    environment: str
    target: str
    source_revision: str
    baseline_id: str
    package_digest: str
    runtime_config_digest: str
    release_id: str
    release_digest: str
    import_run_id: str
    readiness_phase: str
    readiness_receipt_digest: str
    release_posts: tuple[BusinessObjectRef, ...]
    release_creators: tuple[BusinessObjectRef, ...]
    release_entities: tuple[BusinessObjectRef, ...]
    release_homepages: tuple[BusinessObjectRef, ...]
    release_tags: tuple[BusinessObjectRef, ...]
    release_media_assets: tuple[BusinessObjectRef, ...]

    def __post_init__(self) -> None:
        if self.environment not in {"alpha", "beta", "gamma"}:
            raise ValueError("test-data mutation is forbidden outside Alpha/Beta/Gamma")
        expected_target = f"{self.environment}-local"
        if self.target != expected_target:
            raise ValueError("candidate target/environment mismatch")
        if re.fullmatch(r"[0-9a-f]{40}", self.source_revision) is None:
            raise ValueError("source_revision must be a canonical Git revision")
        for name in (
            "baseline_id",
            "package_digest",
            "runtime_config_digest",
            "release_digest",
            "readiness_receipt_digest",
        ):
            value = str(getattr(self, name))
            if not value.startswith("sha256:") or len(value) != 71:
                raise ValueError(f"{name} must be sha256")
        if not self.release_id or not self.import_run_id:
            raise ValueError("release and import run identities are required")
        if self.readiness_phase not in {"consumer", "research", "commercial"}:
            raise ValueError(
                "test-data readiness phase must be consumer, research or commercial"
            )
        for name, object_type in (
            ("release_posts", "Post"),
            ("release_creators", "Creator"),
            ("release_entities", "Entity"),
            ("release_homepages", "EntityHomepage"),
            ("release_tags", "Tag"),
            ("release_media_assets", "MediaAsset"),
        ):
            values = getattr(self, name)
            if not values:
                raise ValueError(f"{name} must contain release-bound references")
            if any(
                not isinstance(value, BusinessObjectRef)
                or value.object_type != object_type
                for value in values
            ):
                raise TypeError(
                    f"{name} must contain only {object_type} BusinessObjectRef values"
                )
            ids = tuple(value.object_id for value in values)
            if len(ids) != len(set(ids)):
                raise ValueError(f"{name} contains duplicate release-bound references")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "environment": self.environment,
                "target": self.target,
                "sourceRevision": self.source_revision,
                "baselineId": self.baseline_id,
                "packageDigest": self.package_digest,
                "runtimeConfigDigest": self.runtime_config_digest,
                "releaseId": self.release_id,
                "releaseDigest": self.release_digest,
                "importRunId": self.import_run_id,
                "readinessPhase": self.readiness_phase,
                "readinessReceiptDigest": self.readiness_receipt_digest,
                "releaseClosure": {
                    "posts": _reference_document(self.release_posts),
                    "creators": _reference_document(self.release_creators),
                    "entities": _reference_document(self.release_entities),
                    "homepages": _reference_document(self.release_homepages),
                    "tags": _reference_document(self.release_tags),
                    "mediaAssets": _reference_document(self.release_media_assets),
                },
            }
        )


@dataclass(frozen=True)
class TestDataContext:
    candidate: CandidateBinding
    base_url: str
    output_root: Path
    provider_evidence: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    max_concurrency: int = 4
    runtime: Any = field(default=None, repr=False, compare=False)
    test_data_instance_id: str = ""

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise ValueError("test-data control plane requires canonical HTTPS")
        if not 1 <= self.max_concurrency <= 16:
            raise ValueError("max_concurrency must be between 1 and 16")


@dataclass(frozen=True)
class CapabilityDefinition:
    capability: CapabilityRef[Any, Any]
    operations: tuple[str, ...]
    concurrency_limit: int = 4

    def __post_init__(self) -> None:
        if not 1 <= self.concurrency_limit <= 16:
            raise ValueError("capability concurrency_limit must be between 1 and 16")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "capabilityKey": self.capability.key.value,
                "ownerService": self.capability.owner_service,
                "paramsType": self.capability.params_type.__qualname__,
                "resultType": self.capability.result_type.__qualname__,
                "operations": list(self.operations),
                "requiredProviderCapabilities": list(
                    item.value
                    for item in self.capability.required_provider_capabilities
                ),
                "mutatesEnvironment": self.capability.mutates_environment,
                "candidateCacheable": self.capability.candidate_cacheable,
            }
        )


@dataclass(frozen=True)
class ProviderPlan:
    request_id: str
    capability_definition_digest: str
    operations: tuple[str, ...]
    resolved_params: object


@dataclass(frozen=True)
class ProvisionedCapability:
    value: object
    cleanup_handle: tuple[BusinessObjectRef, ...] = ()
    cleanup_context: object | None = field(default=None, repr=False, compare=False)
    operation_count: int = 0
    operation_receipts: tuple[Mapping[str, Any], ...] = ()


class PartialProvisioningError(RuntimeError):
    """Provider mutation failed after creating a cleanup-addressable fact."""

    def __init__(
        self,
        message: str,
        *,
        provisioned: ProvisionedCapability,
    ) -> None:
        super().__init__(message)
        self.provisioned = provisioned


@dataclass(frozen=True)
class ReadbackResult:
    passed: bool
    operation_count: int = 0
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CleanupResult:
    state: str
    operation_count: int = 0
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state not in {"released", "quarantined"}:
            raise ValueError("cleanup state must be released or quarantined")


class AcceptanceDataProvider(Protocol):
    def describe(self) -> tuple[CapabilityDefinition, ...]: ...

    def plan(
        self,
        context: TestDataContext,
        request: CapabilityRequest[Any, Any],
        resolved_params: object,
    ) -> ProviderPlan: ...

    def provision(
        self,
        context: TestDataContext,
        plan: ProviderPlan,
    ) -> ProvisionedCapability: ...

    def readback(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> ReadbackResult: ...

    def cleanup(
        self,
        context: TestDataContext,
        provisioned: ProvisionedCapability,
    ) -> CleanupResult: ...


@dataclass(frozen=True)
class NodeResult:
    provisioned: ProvisionedCapability
    receipt: ReceiptRef
    provision_ms: int
    readback_ms: int
    cleanup_ms: int = 0


def _reference_document(
    values: tuple[BusinessObjectRef, ...],
) -> list[dict[str, str]]:
    return [
        {"objectType": value.object_type, "objectId": value.object_id}
        for value in values
    ]


def canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
