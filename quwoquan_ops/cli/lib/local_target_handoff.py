"""Canonical local resolver handoff for Alpha/Beta/Gamma targets.

The handoff keeps canonical HTTPS host names intact.  Stackctl connects those
names to the target-scoped loopback gateway while TLS still verifies the
original host name against the target's local-managed root certificate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from quwoquan_ops.cli.lib.common import write_json
from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.output_paths import deployment_target_path


LOCAL_TARGETS = ("alpha-local", "beta-local", "gamma-local")
LOOPBACK_ADDRESS = "127.0.0.1"


class LocalTargetHandoffError(RuntimeError):
    pass


def canonical_hosts(target: str) -> tuple[str, ...]:
    if target not in LOCAL_TARGETS:
        raise LocalTargetHandoffError(
            f"GATE_BLOCK: local resolver handoff is not owned by {target}"
        )
    resolved_roles = get_target(
        load_environment_topology(), target
    ).get("resolvedUrlRoles") or {}
    hosts = tuple(
        sorted(
            {
                str(role.get("host") or "").strip()
                for role in resolved_roles.values()
                if isinstance(role, dict) and str(role.get("host") or "").strip()
            }
        )
    )
    if not hosts:
        raise LocalTargetHandoffError(
            f"GATE_BLOCK: {target} has no canonical local hosts"
        )
    return hosts


def target_for_hostname(hostname: str) -> str | None:
    normalized = str(hostname or "").strip().lower().rstrip(".")
    if not normalized:
        return None
    matches = [target for target in LOCAL_TARGETS if normalized in canonical_hosts(target)]
    if len(matches) > 1:
        raise LocalTargetHandoffError(
            f"GATE_BLOCK: canonical hostname has multiple local owners: {normalized}"
        )
    return matches[0] if matches else None


def _handoff_payload(target: str) -> dict[str, Any]:
    hosts = list(canonical_hosts(target))
    canonical = {
        "schema": "quwoquan.local-target-handoff",
        "target": target,
        "address": LOOPBACK_ADDRESS,
        "hosts": hosts,
        "tlsProfile": "local-managed",
    }
    digest = "sha256:" + hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    payload = {**canonical, "handoffDigest": digest, "status": "ready"}
    return payload


def materialize_handoff(target: str) -> dict[str, Any]:
    payload = _handoff_payload(target)
    path = deployment_target_path(target, "resolver", "handoff.json")
    write_json(path, payload)
    return {**payload, "path": str(path)}


def load_handoff(target: str) -> dict[str, Any]:
    path = deployment_target_path(target, "resolver", "handoff.json")
    if not path.is_file():
        raise LocalTargetHandoffError(
            f"GATE_BLOCK: local resolver handoff is missing for {target}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = _handoff_payload(target)
    if payload.get("handoffDigest") != expected.get("handoffDigest"):
        raise LocalTargetHandoffError(
            f"GATE_BLOCK: local resolver handoff drift for {target}"
        )
    return {**payload, "path": str(path)}
