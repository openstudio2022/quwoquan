"""Resolve the environment-selected product telemetry log-sink material."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


_LOCAL_TARGETS = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
}
_LOCAL_ELASTICSEARCH_ENVIRONMENT = {
    "PRODUCT_OPS_ELASTICSEARCH_ENDPOINT": "http://elasticsearch:9200",
}


@dataclass(frozen=True)
class ProductTelemetryLogSink:
    environment: dict[str, str]
    secret_path: Path | None
    source: str
    status: str
    redacted_digest: str
    adapter_id: str = "ext.obs.elasticsearch"

    def redacted_receipt(self) -> dict[str, str]:
        """Return the only binding fields suitable for reports or stdout."""
        return {
            "adapterId": self.adapter_id,
            "source": self.source,
            "status": self.status,
            "redactedDigest": self.redacted_digest,
        }


def load_product_telemetry_log_sink(
    environment: str,
    target_name: str,
    *,
    process_environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> ProductTelemetryLogSink:
    """Resolve local substitute material without reading or creating secrets."""
    del process_environment, home
    expected_target = _LOCAL_TARGETS.get(environment)
    if expected_target != target_name:
        raise ValueError(
            f"unsupported product telemetry target: {environment}/{target_name}"
        )
    values = dict(_LOCAL_ELASTICSEARCH_ENVIRONMENT)
    source = f"{target_name}-elasticsearch-topology"
    return ProductTelemetryLogSink(
        environment=values,
        secret_path=None,
        source=source,
        status="ready",
        redacted_digest=_redacted_digest(values),
    )


def _redacted_digest(values: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for key in sorted(values):
        digest.update(key.encode("utf-8"))
        digest.update(b"=")
        digest.update(values[key].encode("utf-8"))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"
