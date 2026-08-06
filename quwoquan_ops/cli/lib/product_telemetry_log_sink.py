"""Resolve the environment-selected product telemetry log-sink material."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    validate_observability_log_sink_package,
)


@dataclass(frozen=True)
class ProductTelemetryLogSink:
    environment: dict[str, str]
    secret_path: Path | None
    source: str
    status: str
    redacted_digest: str
    binding_digest: str
    runtime_artifact_digest: str
    cluster_ref: str
    adapter_id: str = "ext.obs.elasticsearch"

    def redacted_receipt(self) -> dict[str, str]:
        """Return the only binding fields suitable for reports or stdout."""
        return {
            "adapterId": self.adapter_id,
            "source": self.source,
            "status": self.status,
            "redactedDigest": self.redacted_digest,
            "bindingDigest": self.binding_digest,
            "runtimeArtifactDigest": self.runtime_artifact_digest,
            "clusterRef": self.cluster_ref,
        }


def load_product_telemetry_log_sink(
    environment: str,
    target_name: str,
    *,
    runtime_composition: Mapping[str, Any] | None = None,
    process_environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> ProductTelemetryLogSink:
    """Project Product Ops material only from a validated candidate contract."""

    del home
    if runtime_composition is None:
        raise ValueError("candidate-bound observability log-sink package is required")
    composition = validate_observability_log_sink_package(
        dict(runtime_composition),
        expected_environment=environment,
        expected_target=target_name,
    )
    endpoint_key = str(composition["endpointEnvironmentKey"])
    if composition["deploymentMode"] == "package-bound-local":
        values = {endpoint_key: str(composition["runtimeEndpoint"])}
    else:
        protected = process_environment or {}
        required_keys = (endpoint_key, *composition["secretEnvironmentKeys"])
        values = {
            key: str(protected.get(key) or "").strip()
            for key in required_keys
        }
        missing = [key for key, value in values.items() if not value]
        if missing:
            raise RuntimeError(
                "managed Product Ops Elasticsearch material is unavailable: "
                + ", ".join(missing)
            )
        if not values[endpoint_key].startswith("https://"):
            raise ValueError(
                "managed Product Ops Elasticsearch endpoint must use HTTPS"
            )
    source = str(composition["clusterRef"])
    return ProductTelemetryLogSink(
        environment=values,
        secret_path=None,
        source=source,
        status="ready",
        redacted_digest=_redacted_digest(values),
        binding_digest=str(composition["bindingDigest"]),
        runtime_artifact_digest=str(composition["composeDigest"]),
        cluster_ref=str(composition["clusterRef"]),
    )


def _redacted_digest(values: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for key in sorted(values):
        digest.update(key.encode("utf-8"))
        digest.update(b"=")
        digest.update(values[key].encode("utf-8"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"
