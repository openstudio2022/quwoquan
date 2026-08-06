"""Anonymous, non-bypassing reachability probe for image discovery plans."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from core.paths import SOURCE_ACQUISITION_ROOT
from core.schema import assert_valid


PROBE_ROOT = SOURCE_ACQUISITION_ROOT / "discovery-probes"


class ProfessionalImageDiscoveryProbeError(ValueError):
    """The discovery plan cannot be probed without weakening its contract."""


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProfessionalImageDiscoveryProbeError("discovery plan must be an object")
    assert_valid(
        payload,
        "source",
        "professional_image_discovery_plan",
        label="professional image discovery plan",
    )
    stable = {
        key: payload[key]
        for key in (
            "catalogRef",
            "catalogDigest",
            "dimensions",
            "candidateCount",
            "providerCandidateCounts",
            "candidates",
        )
    }
    if payload.get("planDigest") != _digest(stable):
        raise ProfessionalImageDiscoveryProbeError("discovery plan digest mismatch")
    return payload


def _probe_url(url: str, *, timeout_seconds: float) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "quwoquan-data-research-discovery-probe/1.0",
            "Range": "bytes=0-1023",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response.read(1024)
            status = int(getattr(response, "status", 200) or 200)
        return {
            "reachable": 200 <= status < 400,
            "statusCode": status,
            "errorCode": "" if 200 <= status < 400 else "http_error",
            "errorDetail": "",
        }
    except urllib.error.HTTPError as exc:
        controlled = exc.code in {401, 403, 407, 429}
        return {
            "reachable": False,
            "statusCode": int(exc.code),
            "errorCode": "access_controlled" if controlled else "http_error",
            "errorDetail": f"HTTP {exc.code}",
        }
    except (TimeoutError, socket.timeout) as exc:
        return {
            "reachable": False,
            "statusCode": None,
            "errorCode": "timeout",
            "errorDetail": type(exc).__name__,
        }
    except urllib.error.URLError as exc:
        reason = exc.reason
        dns = isinstance(reason, socket.gaierror)
        return {
            "reachable": False,
            "statusCode": None,
            "errorCode": "dns_unavailable" if dns else "network_error",
            "errorDetail": type(reason).__name__,
        }


def _write_create_once(path: Path, payload: Mapping[str, object]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise ProfessionalImageDiscoveryProbeError(
                f"discovery probe create-once conflict: {path}"
            )
        return
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def probe_professional_image_discovery_plan(
    plan_path: Path,
    *,
    timeout_seconds: float,
    output_root: Path = PROBE_ROOT,
) -> tuple[dict[str, object], Path]:
    plan = _load_plan(plan_path.expanduser().resolve())
    first_by_provider: dict[str, Mapping[str, object]] = {}
    for candidate in plan["candidates"]:
        provider = str(candidate["provider"])
        first_by_provider.setdefault(provider, candidate)
    probes: list[dict[str, object]] = []
    for provider in [str(row["provider"]) for row in plan["providerCandidateCounts"]]:
        candidate = first_by_provider[provider]
        probes.append(
            {
                "candidateId": str(candidate["candidateId"]),
                "provider": provider,
                "url": str(candidate["discoveryUrl"]),
                **_probe_url(
                    str(candidate["discoveryUrl"]),
                    timeout_seconds=float(timeout_seconds),
                ),
            }
        )
    planned = Counter(str(row["provider"]) for row in probes)
    reachable = defaultdict(int)
    for row in probes:
        if bool(row["reachable"]):
            reachable[str(row["provider"])] += 1
    provider_counts = [
        {
            "provider": provider,
            "plannedProbeCount": planned[provider],
            "reachableProbeCount": reachable[provider],
        }
        for provider in first_by_provider
    ]
    stable: dict[str, object] = {
        "schema": "quwoquan_data.professional_image_discovery_probe",
        "planId": str(plan["planId"]),
        "planDigest": str(plan["planDigest"]),
        "probedAt": _now(),
        "overallReady": all(bool(row["reachable"]) for row in probes),
        "providerProbeCounts": provider_counts,
        "probes": probes,
    }
    payload = {**stable, "receiptDigest": _digest(stable)}
    assert_valid(
        payload,
        "source",
        "professional_image_discovery_probe",
        label="professional image discovery probe",
    )
    destination = (
        output_root.expanduser().resolve()
        / f"{str(payload['receiptDigest']).removeprefix('sha256:')}.json"
    )
    _write_create_once(destination, payload)
    return payload, destination


__all__ = [
    "PROBE_ROOT",
    "ProfessionalImageDiscoveryProbeError",
    "probe_professional_image_discovery_plan",
]
