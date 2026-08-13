#!/usr/bin/env python3
"""Resolve the prod-hosted SSH deployment-instance and replica plan.

The access-isolation manifest owns host placement. Runtime public endpoints stay
in runtime.yaml and secret material stays outside the repository. This module
only returns logical SSH credential IDs and deterministic rootless Podman
identities.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[3]
ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
INSTANCES = ("prevalidate", "gray", "prod")
EXECUTION_PLANES = ("service", "edge")
STAGE_INSTANCE = {
    "canary": "gray",
    "5": "gray",
    "20": "gray",
    "50": "gray",
    "100": "prod",
}
_SAFE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
_SSH_HOST = re.compile(r"[A-Za-z0-9.-]+")


class ProdHostedTopologyError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeploymentReplica:
    instance: str
    plane: str
    replica_id: str
    replica_ordinal: int
    replica_count: int
    host_id: str
    ssh_host: str
    account: str
    ssh_key_secret: str
    compose_root: str
    remote_root: str
    project: str
    systemd_unit: str
    render_name: str
    governed_services: tuple[str, ...]
    support_services: tuple[str, ...]
    credentials_path: str

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["replicaId"] = payload.pop("replica_id")
        payload["replicaOrdinal"] = payload.pop("replica_ordinal")
        payload["replicaCount"] = payload.pop("replica_count")
        payload["hostId"] = payload.pop("host_id")
        payload["sshHost"] = payload.pop("ssh_host")
        payload["sshKeySecret"] = payload.pop("ssh_key_secret")
        payload["composeRoot"] = payload.pop("compose_root")
        payload["remoteRoot"] = payload.pop("remote_root")
        payload["systemdUnit"] = payload.pop("systemd_unit")
        payload["renderName"] = payload.pop("render_name")
        payload["governedServices"] = list(payload.pop("governed_services"))
        payload["supportServices"] = list(payload.pop("support_services"))
        payload["credentialsPath"] = payload.pop("credentials_path")
        return payload


def load_access_manifest(path: Path = ACCESS_MANIFEST) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ProdHostedTopologyError(f"cannot read access manifest: {error}") from error
    if not isinstance(payload, dict):
        raise ProdHostedTopologyError("access manifest must contain an object")
    return payload


def _require_safe_id(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if _SAFE_ID.fullmatch(normalized) is None:
        raise ProdHostedTopologyError(f"{label} must be a safe lowercase identifier")
    return normalized


def _safe_absolute_path(value: Any, label: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    path = PurePosixPath(normalized)
    if not normalized or not path.is_absolute() or ".." in path.parts:
        raise ProdHostedTopologyError(f"{label} must be a safe absolute path")
    return normalized


def _plane_specs(access: dict[str, Any]) -> dict[str, dict[str, Any]]:
    specs = {
        str(item.get("plane") or ""): item
        for item in access.get("planes") or []
        if isinstance(item, dict)
    }
    for plane in EXECUTION_PLANES:
        spec = specs.get(plane)
        if not isinstance(spec, dict) or spec.get("access") != "read-write":
            raise ProdHostedTopologyError(
                f"execution plane {plane} must be a read-write access-isolation plane"
            )
        _safe_absolute_path(spec.get("composeProjectRoot"), f"{plane}.composeProjectRoot")
        _safe_absolute_path(spec.get("credentialsPath"), f"{plane}.credentialsPath")
    return specs


def _host_specs(access: dict[str, Any]) -> dict[str, dict[str, Any]]:
    management = access.get("management")
    if not isinstance(management, dict):
        raise ProdHostedTopologyError("management must be an object")
    hosts: dict[str, dict[str, Any]] = {}
    for raw in management.get("hosts") or []:
        if not isinstance(raw, dict):
            raise ProdHostedTopologyError("management.hosts entries must be objects")
        host_id = _require_safe_id(raw.get("id"), "management.hosts.id")
        ssh_host = str(raw.get("sshHost") or "").strip()
        if _SSH_HOST.fullmatch(ssh_host) is None:
            raise ProdHostedTopologyError(
                f"management host {host_id} must declare a bare SSH host"
            )
        planes = tuple(str(item) for item in raw.get("planes") or [])
        if not set(EXECUTION_PLANES).issubset(planes):
            raise ProdHostedTopologyError(
                f"management host {host_id} must allow service and edge planes"
            )
        if host_id in hosts:
            raise ProdHostedTopologyError(f"duplicate management host id: {host_id}")
        forbidden = {"privateKey", "password", "token", "secretValue"} & set(raw)
        if forbidden:
            raise ProdHostedTopologyError(
                f"management host {host_id} contains repository secret material fields"
            )
        hosts[host_id] = {
            "sshHost": ssh_host,
            "planes": planes,
        }
    if not hosts:
        raise ProdHostedTopologyError("management.hosts must not be empty")
    default_host_id = _require_safe_id(
        management.get("defaultHostId"), "management.defaultHostId"
    )
    if default_host_id not in hosts:
        raise ProdHostedTopologyError("management.defaultHostId is unknown")
    management_host = str(management.get("sshHost") or "").strip()
    if management_host and management_host != hosts[default_host_id]["sshHost"]:
        raise ProdHostedTopologyError(
            "management.sshHost must match the default management host"
        )
    return hosts


def _instance_specs(access: dict[str, Any]) -> dict[str, dict[str, Any]]:
    specs = access.get("deploymentInstances")
    if not isinstance(specs, dict) or set(specs) != set(INSTANCES):
        raise ProdHostedTopologyError(
            f"deploymentInstances must be exactly {list(INSTANCES)}"
        )
    expected_stages = {
        "prevalidate": [],
        "gray": ["canary", "5", "20", "50"],
        "prod": ["100"],
    }
    for instance, raw in specs.items():
        if not isinstance(raw, dict):
            raise ProdHostedTopologyError(f"deploymentInstances.{instance} must be an object")
        if raw.get("rolloutStages") != expected_stages[instance]:
            raise ProdHostedTopologyError(
                f"deploymentInstances.{instance}.rolloutStages is invalid"
            )
        replicas = raw.get("replicas")
        if not isinstance(replicas, dict) or set(replicas) != set(EXECUTION_PLANES):
            raise ProdHostedTopologyError(
                f"deploymentInstances.{instance}.replicas must own service and edge"
            )
    return specs


def validate_access_manifest(access: dict[str, Any]) -> None:
    planes = _plane_specs(access)
    hosts = _host_specs(access)
    instances = _instance_specs(access)
    placements: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for instance in INSTANCES:
        raw_instance = instances[instance]
        for plane in EXECUTION_PLANES:
            raw_replicas = raw_instance["replicas"][plane]
            if not isinstance(raw_replicas, list) or not raw_replicas:
                raise ProdHostedTopologyError(
                    f"deploymentInstances.{instance}.replicas.{plane} must not be empty"
                )
            seen_ids: set[str] = set()
            seen_hosts: set[str] = set()
            placement: list[tuple[str, str]] = []
            for raw_replica in raw_replicas:
                if not isinstance(raw_replica, dict):
                    raise ProdHostedTopologyError(
                        f"{instance}.{plane} replica entries must be objects"
                    )
                replica_id = _require_safe_id(
                    raw_replica.get("id"), f"{instance}.{plane}.replica.id"
                )
                host_id = _require_safe_id(
                    raw_replica.get("hostId"), f"{instance}.{plane}.replica.hostId"
                )
                if replica_id in seen_ids:
                    raise ProdHostedTopologyError(
                        f"duplicate replica id in {instance}.{plane}: {replica_id}"
                    )
                if host_id in seen_hosts:
                    raise ProdHostedTopologyError(
                        f"{instance}.{plane} places multiple published-port replicas on {host_id}"
                    )
                if host_id not in hosts or plane not in hosts[host_id]["planes"]:
                    raise ProdHostedTopologyError(
                        f"{instance}.{plane}.{replica_id} uses an incompatible host: {host_id}"
                    )
                seen_ids.add(replica_id)
                seen_hosts.add(host_id)
                placement.append((replica_id, host_id))
            placements[(instance, plane)] = placement
            if not planes[plane].get("rootlessGovernedComposeServices"):
                raise ProdHostedTopologyError(
                    f"{plane} lacks rootless governed compose services"
                )
    for instance in INSTANCES:
        if placements[(instance, "service")] != placements[(instance, "edge")]:
            raise ProdHostedTopologyError(
                f"{instance} service/edge replicas must be co-located with matching ids"
            )
    for plane in EXECUTION_PLANES:
        if placements[("gray", plane)] != placements[("prod", plane)]:
            raise ProdHostedTopologyError(
                f"gray/prod {plane} replicas must be co-located with matching ids"
            )


def resolve_plan(
    access: dict[str, Any],
    *,
    instance: str,
    planes: Iterable[str] | None = None,
    host_ids: Iterable[str] | None = None,
    ssh_host_override: str = "",
    service_filter: str = "",
) -> list[DeploymentReplica]:
    validate_access_manifest(access)
    if instance not in INSTANCES:
        raise ProdHostedTopologyError(f"unsupported deployment instance: {instance}")
    selected_planes = tuple(planes or EXECUTION_PLANES)
    if not selected_planes or not set(selected_planes).issubset(EXECUTION_PLANES):
        raise ProdHostedTopologyError("plan planes must be service and/or edge")
    selected_host_ids = {str(item) for item in host_ids or []}
    hosts = _host_specs(access)
    unknown_hosts = selected_host_ids - set(hosts)
    if unknown_hosts:
        raise ProdHostedTopologyError(
            f"unknown selected host ids: {sorted(unknown_hosts)}"
        )
    if ssh_host_override and _SSH_HOST.fullmatch(ssh_host_override) is None:
        raise ProdHostedTopologyError("--ssh-host must be a bare hostname or IP")
    instance_spec = _instance_specs(access)[instance]
    plane_specs = _plane_specs(access)
    plan: list[DeploymentReplica] = []
    for plane in selected_planes:
        raw_replicas = instance_spec["replicas"][plane]
        replica_count = len(raw_replicas)
        plane_spec = plane_specs[plane]
        governed = tuple(
            str(item)
            for item in plane_spec.get("rootlessGovernedComposeServices") or []
            if str(item).strip()
        )
        if plane == "service" and service_filter:
            target = {
                "service-plane": "__all__",
            }.get(service_filter, service_filter)
            if target != "__all__":
                governed = tuple(item for item in governed if item == target)
                if not governed:
                    raise ProdHostedTopologyError(
                        f"service filter is not governed by service plane: {service_filter}"
                    )
        support = tuple(
            str(item)
            for item in plane_spec.get("rootlessSupportComposeServices") or []
            if str(item).strip()
        )
        compose_root = _safe_absolute_path(
            plane_spec.get("composeProjectRoot"), f"{plane}.composeProjectRoot"
        )
        for ordinal, raw_replica in enumerate(raw_replicas):
            replica_id = str(raw_replica["id"])
            host_id = str(raw_replica["hostId"])
            if selected_host_ids and host_id not in selected_host_ids:
                continue
            ssh_host = str(hosts[host_id]["sshHost"])
            if ssh_host_override:
                if len(hosts) != 1:
                    raise ProdHostedTopologyError(
                        "a single --ssh-host override is unsafe for a multi-host manifest"
                    )
                ssh_host = ssh_host_override
            identity = f"{plane}-{instance}-{replica_id}"
            remote_root = f"{compose_root}/instances/{instance}/{replica_id}"
            plan.append(
                DeploymentReplica(
                    instance=instance,
                    plane=plane,
                    replica_id=replica_id,
                    replica_ordinal=ordinal,
                    replica_count=replica_count,
                    host_id=host_id,
                    ssh_host=ssh_host,
                    account=str(plane_spec.get("account") or ""),
                    ssh_key_secret=str(plane_spec.get("sshKeySecret") or ""),
                    compose_root=compose_root,
                    remote_root=remote_root,
                    project=f"quwoquan-{identity}",
                    systemd_unit=f"quwoquan-{identity}.service",
                    render_name=identity,
                    governed_services=governed,
                    support_services=support,
                    credentials_path=_safe_absolute_path(
                        plane_spec.get("credentialsPath"), f"{plane}.credentialsPath"
                    ),
                )
            )
    if not plan:
        raise ProdHostedTopologyError("deployment plan selection is empty")
    return plan


def require_release_redundancy(plan: list[DeploymentReplica]) -> None:
    """Fail closed until formal rollout has real multi-host replica inventory."""

    if not plan:
        raise ProdHostedTopologyError("formal rollout deployment plan is empty")
    instances = {item.instance for item in plan}
    if len(instances) != 1 or next(iter(instances)) not in {"gray", "prod"}:
        raise ProdHostedTopologyError(
            "formal rollout redundancy applies only to gray/prod instances"
        )
    selected_planes = {item.plane for item in plan}
    if selected_planes != set(EXECUTION_PLANES):
        raise ProdHostedTopologyError(
            "formal rollout redundancy requires the complete service+edge inventory; "
            "filtered plane plans are not promotable"
        )
    host_ids = {item.host_id for item in plan}
    issues: list[str] = []
    if len(host_ids) < 2:
        issues.append("at least two real inventory hosts are required")
    for plane in sorted({item.plane for item in plan}):
        placements = [item for item in plan if item.plane == plane]
        plane_hosts = {item.host_id for item in placements}
        if len(placements) < 2 or len(plane_hosts) < 2:
            issues.append(
                f"{plane} requires at least two replicas on distinct inventory hosts"
            )
    if issues:
        raise ProdHostedTopologyError(
            "formal rollout inventory is not redundant: " + "; ".join(issues)
        )


def instance_for_stage(stage: str) -> str:
    try:
        return STAGE_INSTANCE[stage]
    except KeyError as error:
        raise ProdHostedTopologyError(f"unsupported rollout stage: {stage}") from error


def plan_payload(plan: list[DeploymentReplica]) -> dict[str, Any]:
    instances = {item.instance for item in plan}
    return {
        "schema": "prod-hosted-deployment-plan",
        "target": "prod-hosted",
        "environment": "prod",
        "instance": next(iter(instances)) if len(instances) == 1 else "mixed",
        "replicaCount": len(plan),
        "hosts": sorted({item.host_id for item in plan}),
        "placements": [item.to_payload() for item in plan],
        "secretMaterialEmbedded": False,
    }


def placement_check_name(placement: DeploymentReplica | Mapping[str, Any]) -> str:
    if isinstance(placement, DeploymentReplica):
        plane = placement.plane
        host_id = placement.host_id
        replica_id = placement.replica_id
    else:
        plane = str(placement.get("plane") or "")
        host_id = str(placement.get("hostId") or placement.get("host_id") or "")
        replica_id = str(placement.get("replicaId") or placement.get("replica_id") or "")
    if not plane or not host_id or not replica_id:
        raise ProdHostedTopologyError("placement check name requires plane/hostId/replicaId")
    return f"host:{host_id}:plane:{plane}:replica:{replica_id}"


def expected_placement_check_names(plan: list[DeploymentReplica]) -> list[str]:
    return [placement_check_name(item) for item in plan]


def validate_host_coverage(
    post_checks: Iterable[Mapping[str, Any]],
    plan: list[DeploymentReplica],
) -> list[str]:
    """Return issues when formal CAS lacks a passed check for every placement."""

    expected = expected_placement_check_names(plan)
    observed: dict[str, str] = {}
    for item in post_checks:
        name = str(item.get("name") or "").strip()
        if not name.startswith("host:"):
            continue
        status = str(item.get("status") or "").strip()
        if not status and "exitCode" in item:
            status = "passed" if int(item.get("exitCode") or 1) == 0 else "failed"
        observed[name] = status
    issues: list[str] = []
    for name in expected:
        status = observed.get(name)
        if status is None:
            issues.append(f"missing host coverage check: {name}")
        elif status != "passed":
            issues.append(f"host coverage check not passed: {name} status={status}")
    unexpected = sorted(set(observed) - set(expected))
    for name in unexpected:
        issues.append(f"unexpected host coverage check: {name}")
    return issues


def _tsv(plan: list[DeploymentReplica]) -> str:
    rows: list[str] = []
    for item in plan:
        rows.append(
            "\t".join(
                (
                    item.plane,
                    item.account,
                    item.compose_root,
                    item.ssh_key_secret,
                    ",".join(item.governed_services) or "-",
                    ",".join(item.support_services) or "-",
                    item.credentials_path,
                    item.host_id,
                    item.ssh_host,
                    item.replica_id,
                    str(item.replica_count),
                    item.remote_root,
                    item.project,
                    item.systemd_unit,
                    item.render_name,
                )
            )
        )
    return "\n".join(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a read-only prod-hosted host/instance/replica plan."
    )
    parser.add_argument("--manifest", type=Path, default=ACCESS_MANIFEST)
    parser.add_argument("--instance", choices=INSTANCES, default="")
    parser.add_argument("--stage", choices=tuple(STAGE_INSTANCE), default="")
    parser.add_argument("--plane", action="append", choices=EXECUTION_PLANES)
    parser.add_argument("--host-id", action="append", default=[])
    parser.add_argument("--ssh-host", default="")
    parser.add_argument("--service-filter", default="")
    parser.add_argument(
        "--require-release-redundancy",
        action="store_true",
        help=(
            "GATE_BLOCK unless the complete gray/prod service+edge inventory "
            "has two real hosts and replicas per plane"
        ),
    )
    parser.add_argument("--format", choices=("json", "tsv"), default="json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        instance = args.instance or instance_for_stage(args.stage)
        if args.instance and args.stage and args.instance != instance_for_stage(args.stage):
            raise ProdHostedTopologyError(
                f"stage {args.stage} does not belong to instance {args.instance}"
            )
        if not instance:
            raise ProdHostedTopologyError("--instance or --stage is required")
        plan = resolve_plan(
            load_access_manifest(args.manifest),
            instance=instance,
            planes=args.plane,
            host_ids=args.host_id,
            ssh_host_override=args.ssh_host,
            service_filter=args.service_filter,
        )
        if args.require_release_redundancy:
            require_release_redundancy(plan)
    except ProdHostedTopologyError as error:
        print(f"GATE_BLOCK: {error}", file=sys.stderr)
        return 2
    if args.format == "tsv":
        print(_tsv(plan))
    else:
        print(json.dumps(plan_payload(plan), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
