"""治理常量、标识正则与 adapter 替身判定（原单文件逐字搬运）。"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
SERVICES_ROOT = ROOT / "quwoquan_service" / "services"
ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
NONPROD_ENVIRONMENTS = ("alpha", "beta", "gamma")
RELEASE_ADAPTER_ENVIRONMENTS = ("prod",)
STATES = {"enabled", "blocked", "not_required"}
READY_IMPLEMENTATION_STATUSES = frozenset({"production"})
MESSAGE_TRANSPORT_REMOTE_UAT_PREREQUISITE_SCHEMA = (
    "provider-conformance-user-acceptance-prerequisite"
)
MESSAGE_TRANSPORT_CAPABILITY_ID = "runtime.message.transport"
MESSAGE_TRANSPORT_REQUIRED_METRICS = (
    "pending_lag",
    "dead_letter",
    "publish_p95",
    "consume_p95",
)
CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
ADAPTER_RE = re.compile(r"^(?:ext|infra|data)\.[a-z0-9_]+(?:\.[a-z0-9_]+)*$")
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
# Platform-local adapters can be production-grade when the selected topology is remote.
PLATFORM_LOCAL_ADAPTERS = frozenset(
    {
        "infra.redis.message_transport",
        "infra.minio.object_storage",
    }
)
FIRST_PARTY_AUTHORITY_ADAPTER = "ext.first_party.http_authority"
LOCAL_SUBSTITUTE_MARKERS = (
    "fixture",
    "mock",
    "fake",
    "local_recorder",
    "local_capture",
    "local_log_sink",
    "protocol_substitute",
    "minio",
    "_local",
    ".local.",
)


def is_local_substitute_adapter(adapter_id: str) -> bool:
    """Return True when adapter is a non-prod Port-equivalent substitute."""
    if adapter_id in PLATFORM_LOCAL_ADAPTERS:
        return True
    return any(marker in adapter_id for marker in LOCAL_SUBSTITUTE_MARKERS)


def is_prod_forbidden_adapter(adapter_id: str) -> bool:
    """Return True when adapter must not be selected in a release environment."""
    if adapter_id == "infra.redis.message_transport":
        return False
    return any(marker in adapter_id for marker in LOCAL_SUBSTITUTE_MARKERS)


def requires_provider_conformance(binding: Mapping[str, Any]) -> bool:
    """Separate third-party/infra Provider cells from first-party service calls."""
    adapter_id = str(binding.get("adapter_id") or "")
    return (
        binding.get("state") != "not_required"
        and bool(adapter_id)
        and adapter_id != FIRST_PARTY_AUTHORITY_ADAPTER
    )
