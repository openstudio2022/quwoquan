"""Resolve Product Ops telemetry/runtime-log sink material from one candidate."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    validate_observability_log_sink_package,
)


@dataclass(frozen=True)
class ProductTelemetryLogSink:
    environment: dict[str, str]
    secret_path: Path | None
    source: str
    status: str
    material_digest: str
    binding_digest: str
    runtime_artifact_digest: str
    binding_identities: tuple[str, ...]
    adapter_id: str = "ext.obs.elasticsearch"

    def redacted_receipt(self) -> dict[str, Any]:
        """Return only digests and non-secret logical binding identities."""
        return {
            "adapterId": self.adapter_id,
            "source": self.source,
            "status": self.status,
            "materialDigest": self.material_digest,
            "bindingDigest": self.binding_digest,
            "runtimeArtifactDigest": self.runtime_artifact_digest,
            "bindingIdentities": list(self.binding_identities),
        }


def load_product_telemetry_log_sink(
    environment: str,
    target_name: str,
    *,
    runtime_composition: Mapping[str, Any] | None = None,
    process_environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> ProductTelemetryLogSink:
    """Project both logical Product Ops sinks from a validated candidate."""

    del home
    if runtime_composition is None:
        raise ValueError("candidate-bound observability log-sink package is required")
    composition = validate_observability_log_sink_package(
        dict(runtime_composition),
        expected_environment=environment,
        expected_target=target_name,
    )
    bindings = composition["bindings"]
    if composition["deploymentMode"] == "package-bound-local":
        runtime_endpoint = str(composition["runtimeEndpoint"])
        values = {
            str(binding["endpointEnvironmentKey"]): runtime_endpoint
            for binding in bindings
        }
    else:
        protected = process_environment or {}
        required_keys = tuple(
            key
            for binding in bindings
            for key in (
                str(binding["endpointEnvironmentKey"]),
                *(
                    str(secret_key)
                    for secret_key in binding["secretEnvironmentKeys"]
                ),
            )
        )
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
        for binding in bindings:
            endpoint_key = str(binding["endpointEnvironmentKey"])
            parsed = urlsplit(values[endpoint_key])
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError(
                    f"managed Product Ops Elasticsearch endpoint must use HTTPS: {endpoint_key}"
                )
        secret_values = [
            values[str(secret_key)]
            for binding in bindings
            for secret_key in binding["secretEnvironmentKeys"]
        ]
        if len(secret_values) != len(set(secret_values)):
            raise ValueError(
                "managed Product Ops Elasticsearch API keys must be role-isolated"
            )
    identities = tuple(
        str(binding["capabilityId"])
        for binding in bindings
    )
    return ProductTelemetryLogSink(
        environment=values,
        secret_path=None,
        source="candidate-bound-product-ops-log-sinks",
        status="ready",
        material_digest=_material_digest(values),
        binding_digest=str(composition["bindingDigest"]),
        runtime_artifact_digest=str(composition["composeDigest"]),
        binding_identities=identities,
    )


def _material_digest(values: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for key in sorted(values):
        digest.update(key.encode("utf-8"))
        digest.update(b"=")
        digest.update(values[key].encode("utf-8"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"
