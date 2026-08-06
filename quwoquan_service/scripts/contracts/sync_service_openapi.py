#!/usr/bin/env python3
"""Persist generated OpenAPI snapshots beside their owning service.

The compiler view is disposable and cannot be a truth source. qwq-contract
generates one snapshot per metadata domain in that view; this step maps each
domain back through the owning contracts/domain.yaml and atomically updates the
service's generated/openapi.yaml artifact.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

import yaml


SERVICE_ROOT = Path(__file__).resolve().parents[2]


def contract_roots() -> list[Path]:
    roots = sorted((SERVICE_ROOT / "services").glob("*/contracts"))
    roots.extend(sorted((SERVICE_ROOT / "control-plane").glob("*/contracts")))
    return [item for item in roots if (item / "domain.yaml").is_file()]


def domain_of(contracts: Path) -> str:
    payload = yaml.safe_load((contracts / "domain.yaml").read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"domain"}:
        raise ValueError(f"{contracts / 'domain.yaml'} must only declare domain")
    domain = str(payload["domain"]).strip()
    if not domain or "/" in domain or domain.startswith("_"):
        raise ValueError(f"invalid domain {domain!r}: {contracts / 'domain.yaml'}")
    return domain


def owns_http_routes(contracts: Path) -> bool:
    """Return whether the domain owns at least one HTTP operation snapshot.

    Infrastructure-only domains such as api-edge may own errors, storage and an
    internal facade while deliberately exposing no second HTTP API. They remain
    ContractGraph contributors but must not be forced to publish an empty
    OpenAPI truth source.
    """
    for operations in sorted(contracts.rglob("operations.yaml")):
        payload = yaml.safe_load(operations.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{operations} must contain a mapping")
        routes = payload.get("api_routes", [])
        if routes is None:
            routes = []
        if not isinstance(routes, list):
            raise ValueError(f"{operations} api_routes must contain a list")
        if routes:
            return True
    return False


def atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, target)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def sync(view: Path) -> int:
    contributors: dict[str, list[Path]] = {}
    for contracts in contract_roots():
        domain = domain_of(contracts)
        contributors.setdefault(domain, []).append(contracts)

    owners: dict[str, Path] = {}
    service_root = SERVICE_ROOT / "services"
    for domain, roots in sorted(contributors.items()):
        service_owners = [item for item in roots if service_root in item.parents]
        if len(service_owners) != 1:
            raise ValueError(
                f"domain {domain} must have exactly one domain-service OpenAPI owner; "
                f"contributors={roots}"
            )
        owner = service_owners[0]
        if owns_http_routes(owner):
            owners[domain] = owner

    snapshots = {
        item.parent.name: item
        for item in sorted(view.glob("*/openapi.yaml"))
        if not item.parent.name.startswith("_")
    }
    missing = sorted(set(owners) - set(snapshots))
    unexpected = sorted(set(snapshots) - set(owners))
    if missing or unexpected:
        raise ValueError(
            f"OpenAPI ownership mismatch: missing={missing}, unexpected={unexpected}"
        )

    for domain, contracts in sorted(owners.items()):
        target = contracts.parent / "generated" / "openapi.yaml"
        atomic_write(target, snapshots[domain].read_bytes())
    return len(owners)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-view", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = sync(args.contract_view.resolve())
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"[sync-service-openapi] FAIL: {exc}")
        return 1
    print(f"[sync-service-openapi] OK: {count} owner snapshot(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
