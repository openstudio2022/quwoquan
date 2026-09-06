#!/usr/bin/env python3
"""Execute the non-promotable prod-hosted first-party container prevalidation.

This helper is private to stackctl.  It never reads or writes the production
release ledger and it performs the complete host preflight before any image is
pulled, streamed, or started.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.output_paths import deployment_render_dir
from quwoquan_ops.cli.prod.prod_hosted_topology import (
    DeploymentReplica,
    ProdHostedTopologyError,
    load_access_manifest,
    resolve_plan,
)

ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
DEFAULT_KEY_DIR = Path.home() / ".ssh" / "quwoquan-prod"
DIGEST_REF = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}")


class PrevalidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlaneProjection:
    name: str
    account: str
    ssh_secret: str
    startup_services: tuple[str, ...]
    image_only_services: tuple[str, ...]
    exposed_ports: tuple[int, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Private prod-hosted first-party prevalidation executor."
    )
    parser.add_argument("--host", default="")
    parser.add_argument("--host-id", action="append", default=[])
    parser.add_argument("--frozen-diagnostic-snapshot", required=True, type=Path)
    parser.add_argument("--image-transport-tag", required=True)
    parser.add_argument("--candidate-digest", required=True)
    parser.add_argument("--data-mode", choices=("isolated", "external"), required=True)
    parser.add_argument("--scope", choices=("first-party",), required=True)
    parser.add_argument("--key-dir", type=Path, default=DEFAULT_KEY_DIR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PrevalidationError(f"{path} must contain an object")
    return payload


def load_projection() -> tuple[dict[str, Any], dict[str, PlaneProjection]]:
    access = _load_yaml(ACCESS_MANIFEST)
    spec = access.get("prevalidation")
    if not isinstance(spec, dict) or spec.get("promotable") is not False:
        raise PrevalidationError("prevalidation must be explicitly non-promotable")
    release_evidence = spec.get("releaseEvidence")
    if not isinstance(release_evidence, dict) or any(
        release_evidence.get(key) is not False
        for key in ("eligible", "writeLedger", "writeReceipt")
    ):
        raise PrevalidationError("prevalidation release evidence must remain disabled")
    readiness = spec.get("readinessPolicy") or {}
    if not (
        readiness.get("requireContainerRunning") is True
        and readiness.get("requireHealthyExceptProviderBound") is True
        and readiness.get("providerReadinessStatus") == "GATE_BLOCK"
    ):
        raise PrevalidationError(
            "prevalidation must keep container runtime and Provider readiness separate"
        )
    if spec.get("capacityStrategy") != "constrained-per-replica-host":
        raise PrevalidationError("prevalidation capacity strategy must be explicit")
    reclaim = spec.get("staleRuntimeReclaimPolicy") or {}
    if not (
        reclaim.get("enabled") is True
        and reclaim.get("plane") == "service"
        and reclaim.get("removeVolumes") is False
        and reclaim.get("pruneUnusedImages") is True
        and reclaim.get("containerNamePrefixes")
        and reclaim.get("allowedStates")
    ):
        raise PrevalidationError(
            "prevalidation stale runtime reclaim must be scoped and volume-preserving"
        )
    plane_specs = {
        str(item.get("plane")): item
        for item in (access.get("planes") or [])
        if isinstance(item, dict)
    }
    projections: dict[str, PlaneProjection] = {}
    for name in ("service", "edge"):
        plane = plane_specs.get(name)
        projected = (spec.get("planes") or {}).get(name)
        if not isinstance(plane, dict) or not isinstance(projected, dict):
            raise PrevalidationError(f"prevalidation plane is missing: {name}")
        startup = tuple(str(item) for item in projected.get("startupServices") or [])
        image_only = tuple(
            str(item) for item in projected.get("imageAndConfigOnlyServices") or []
        )
        governed = {
            str(item) for item in plane.get("rootlessGovernedComposeServices") or []
        }
        if not startup or not set(startup + image_only).issubset(governed):
            raise PrevalidationError(f"prevalidation escapes {name} plane ownership")
        if set(startup) & set(image_only):
            raise PrevalidationError(f"prevalidation startup/image-only overlap: {name}")
        ports = tuple(int(item) for item in projected.get("exposedPorts") or [])
        if not ports or any(port < 1024 or port > 65535 for port in ports):
            raise PrevalidationError(f"prevalidation ports are invalid: {name}")
        projections[name] = PlaneProjection(
            name=name,
            account=str(plane.get("account") or ""),
            ssh_secret=str(plane.get("sshKeySecret") or ""),
            startup_services=startup,
            image_only_services=image_only,
            exposed_ports=ports,
        )
    if projections["service"].image_only_services != ("integration-service",):
        raise PrevalidationError("integration-service must be image/config-only")
    startup_services = {
        service
        for projection in projections.values()
        for service in projection.startup_services
    }
    provider_bound = {
        str(item) for item in readiness.get("providerBoundServices") or []
    }
    if not provider_bound or not provider_bound.issubset(startup_services):
        raise PrevalidationError(
            "provider-bound health exceptions must be explicit startup services"
        )
    excluded = spec.get("excluded") or {}
    workloads = {str(item) for item in excluded.get("workloads") or []}
    if not {"livekit", "coturn"}.issubset(workloads):
        raise PrevalidationError("LiveKit SFU and Coturn must be excluded")
    isolated = spec.get("isolatedData") or {}
    if (
        isolated.get("empty") is not True
        or isolated.get("seedAllowed") is not False
        or isolated.get("productionDataAllowed") is not False
        or isolated.get("releaseEvidenceEligible") is not False
    ):
        raise PrevalidationError("isolated data projection must remain empty/non-evidence")
    images = isolated.get("images") or {}
    services = [str(item) for item in isolated.get("services") or []]
    if set(images) != set(services) or any(
        DIGEST_REF.fullmatch(str(images.get(service) or "")) is None
        for service in services
    ):
        raise PrevalidationError("isolated data images must all be digest-pinned")
    return spec, projections


def _resolve_key(projection: PlaneProjection, key_dir: Path) -> Path:
    for suffix in ("_FILE", "_PATH"):
        value = os.environ.get(f"{projection.ssh_secret}{suffix}", "").strip()
        if value:
            path = Path(value).expanduser()
            if path.is_file():
                return path
            raise PrevalidationError(f"SSH key path is invalid for {projection.name}")
    path = key_dir.expanduser() / projection.account
    if not path.is_file():
        raise PrevalidationError(
            f"SSH isolation key is missing for {projection.account}: {path}"
        )
    return path


def _remote_snapshot_script() -> str:
    return r'''
import json
import os
import pathlib
import platform
import re
import subprocess

def run(argv):
    result = subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}

mem_total = 0
for line in pathlib.Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
    if line.startswith("MemTotal:"):
        mem_total = int(line.split()[1]) * 1024
        break
stat = os.statvfs(pathlib.Path.home())
listeners = run(["bash", "-lc", "ss -ltnH 2>/dev/null || netstat -ltn 2>/dev/null || true"])
ports = sorted({int(value) for value in re.findall(r":([0-9]{2,5})(?:\s|$)", listeners["stdout"])})
podman = run(["podman", "info", "--format", "json"])
rootless = False
if podman["returncode"] == 0:
    try:
        info = json.loads(podman["stdout"])
        rootless = bool((((info.get("host") or {}).get("security") or {}).get("rootless")))
    except json.JSONDecodeError:
        pass
linger = run(["loginctl", "show-user", os.environ.get("USER", ""), "-p", "Linger", "--value"])
user_systemd = run(["systemctl", "--user", "is-system-running"])
storage = run(["podman", "system", "df", "--format", "json"])
container_reclaimable = 0
if storage["returncode"] == 0:
    try:
        for item in json.loads(storage["stdout"]):
            if item.get("Type") in {"Images", "Containers"}:
                container_reclaimable += int(item.get("RawReclaimable") or 0)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
print(json.dumps({
    "account": run(["whoami"])["stdout"].strip(),
    "architecture": platform.machine(),
    "cpuCores": os.cpu_count() or 0,
    "memoryBytes": mem_total,
    "containerFreeBytes": stat.f_bavail * stat.f_frsize,
    "containerReclaimableBytes": container_reclaimable,
    "containerEffectiveFreeBytes": stat.f_bavail * stat.f_frsize + container_reclaimable,
    "listeningPorts": ports,
    "podmanRootless": rootless,
    "linger": linger["stdout"].strip() == "yes",
    "userSystemd": user_systemd["stdout"].strip(),
}))
'''


def collect_host_snapshots(
    host: str,
    projections: dict[str, PlaneProjection],
    key_dir: Path,
) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for name, projection in projections.items():
        key = _resolve_key(projection, key_dir)
        result = subprocess.run(
            [
                "ssh",
                "-i",
                str(key),
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=accept-new",
                f"{projection.account}@{host}",
                "python3 -",
            ],
            input=_remote_snapshot_script(),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise PrevalidationError(
                f"SSH isolation preflight failed for {projection.account}: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        try:
            snapshot = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise PrevalidationError(
                f"host preflight returned invalid JSON for {projection.account}"
            ) from error
        if snapshot.get("account") != projection.account:
            raise PrevalidationError(
                f"SSH isolation account mismatch: {snapshot.get('account')} != {projection.account}"
            )
        snapshots[name] = snapshot
    return snapshots


def evaluate_host_snapshots(
    snapshots: dict[str, dict[str, Any]],
    spec: dict[str, Any],
    projections: dict[str, PlaneProjection],
    *,
    data_mode: str,
) -> list[str]:
    minimum = spec.get("minimumHostResources") or {}
    service = snapshots.get("service") or {}
    issues: list[str] = []
    checks = (
        (int(service.get("cpuCores") or 0), int(minimum.get("cpuCores") or 0), "CPU cores"),
        (int(service.get("memoryBytes") or 0), int(minimum.get("memoryBytes") or 0), "memory bytes"),
        (
            int(service.get("containerFreeBytes") or 0),
            int(minimum.get("containerFreeBytes") or 0),
            "container free bytes",
        ),
        (
            int(service.get("containerEffectiveFreeBytes") or 0),
            int(minimum.get("containerEffectiveFreeBytes") or 0),
            "effective container free bytes",
        ),
    )
    for actual, required, label in checks:
        if actual < required:
            issues.append(f"{label} insufficient: {actual} < {required}")
    architectures = {str(item) for item in minimum.get("architectures") or []}
    if str(service.get("architecture") or "") not in architectures:
        issues.append(
            f"architecture unsupported: {service.get('architecture')} not in {sorted(architectures)}"
        )
    occupied = {
        int(port)
        for snapshot in snapshots.values()
        for port in snapshot.get("listeningPorts") or []
    }
    target_ports = {
        port for projection in projections.values() for port in projection.exposed_ports
    }
    conflicts = sorted(target_ports & occupied)
    if conflicts:
        issues.append(f"prevalidation target ports already occupied: {conflicts}")
    if data_mode == "external":
        missing = sorted({19400, 19410, 19420} - occupied)
        if missing:
            issues.append(f"external data ports are not listening: {missing}")
    for name, snapshot in snapshots.items():
        if snapshot.get("podmanRootless") is not True:
            issues.append(f"{name} plane Podman is not rootless")
        if snapshot.get("linger") is not True:
            issues.append(f"{name} plane user linger is disabled")
        if str(snapshot.get("userSystemd") or "") not in {"running", "degraded"}:
            issues.append(f"{name} plane user systemd is unavailable")
    return issues


def _reclaim_stale_runtime(
    *,
    host: str,
    projection: PlaneProjection,
    key_dir: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    if projection.name != str(policy.get("plane") or ""):
        return {"plane": projection.name, "status": "not-required"}
    key = _resolve_key(projection, key_dir)
    script = _remote_reclaim_script(projection=projection, policy=policy)
    result = subprocess.run(
        [
            "ssh",
            "-i",
            str(key),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{projection.account}@{host}",
            "python3 -",
        ],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise PrevalidationError(
            "scoped stale runtime reclaim failed: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise PrevalidationError("stale runtime reclaim returned invalid JSON") from error
    required = int(
        ((policy.get("minimumHostResources") or {}).get("postReclaimContainerFreeBytes"))
        or 0
    )
    if required and int(report.get("containerFreeBytes") or 0) < required:
        raise PrevalidationError(
            "container free bytes remain insufficient after scoped reclaim: "
            f"{report.get('containerFreeBytes')} < {required}"
        )
    return report


def _remote_reclaim_script(
    *,
    projection: PlaneProjection,
    policy: dict[str, Any],
) -> str:
    encoded_policy = base64.b64encode(
        json.dumps(policy, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii")
    return f'''
import base64
import json
import os
import pathlib
import re
import subprocess
import time

policy = json.loads(base64.b64decode("{encoded_policy}").decode("utf-8"))

def run(argv):
    return subprocess.run(
        argv,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

listed = run(["podman", "ps", "-a", "--format", "json"])
if listed.returncode != 0:
    raise SystemExit(listed.stderr or listed.stdout)
containers = json.loads(listed.stdout)
prefixes = tuple(str(item) for item in policy.get("containerNamePrefixes") or [])
allowed = {{str(item).lower() for item in policy.get("allowedStates") or []}}
preserved = {{str(item) for item in policy.get("preservedContainers") or []}}
selected = set()
for item in containers:
    names = item.get("Names") or []
    if isinstance(names, str):
        names = [names]
    state = str(item.get("State") or "").lower()
    for name in names:
        if name in preserved:
            continue
        if name.startswith(prefixes) and state in allowed:
            selected.add(name)

# Compose-created containers can depend on one another. Remove one at a time
# and retry dependency-order failures until a pass makes no progress.
remaining = set(selected)
removed_names = []
while remaining:
    progressed = False
    failures = []
    for name in sorted(remaining):
        removed = run(["podman", "rm", name])
        if removed.returncode == 0:
            remaining.remove(name)
            removed_names.append(name)
            progressed = True
        else:
            failures.append(removed.stderr or removed.stdout)
    if not progressed:
        raise SystemExit("dependency-order retries made no progress: " + "; ".join(failures))

external_removed = []
external = policy.get("externalBuildContainers") or {{}}
if external.get("enabled"):
    external_listed = run(["podman", "ps", "--external", "-a", "--format", "json"])
    if external_listed.returncode != 0:
        raise SystemExit(external_listed.stderr or external_listed.stdout)
    external_states = {{str(item).lower() for item in external.get("allowedStates") or []}}
    require_pid_zero = external.get("requirePidZero") is True
    minimum_age_seconds = int(external.get("minimumAgeSeconds") or 0)
    external_name_pattern = re.compile(str(external.get("namePattern") or "(?!)"))
    now = int(time.time())
    for item in json.loads(external_listed.stdout):
        state = str(item.get("State") or "").lower()
        if state not in external_states:
            continue
        pid = int(item.get("Pid") or item.get("PID") or 0)
        if require_pid_zero and pid != 0:
            continue
        created = int(item.get("Created") or 0)
        if created <= 0 or now - created < minimum_age_seconds:
            continue
        names = item.get("Names") or []
        if isinstance(names, str):
            names = [names]
        name = str(names[0]) if names else ""
        if external_name_pattern.fullmatch(name) is None:
            continue
        container_id = str(item.get("Id") or item.get("ID") or "")
        if not container_id:
            continue
        external_removed_result = run(["podman", "rm", container_id])
        if external_removed_result.returncode != 0:
            raise SystemExit(external_removed_result.stderr or external_removed_result.stdout)
        external_removed.append(name)

image_prune_output = ""
if policy.get("pruneUnusedImages"):
    prune = run(["podman", "image", "prune", "-a", "-f"])
    if prune.returncode != 0:
        raise SystemExit(prune.stderr or prune.stdout)
    image_prune_output = prune.stdout.strip()
stat = os.statvfs(pathlib.Path.home())
print(json.dumps({{
    "plane": "{projection.name}",
    "status": "completed",
    "removedContainers": sorted(removed_names),
    "removedExternalBuildContainers": sorted(external_removed),
    "preservedContainers": sorted(preserved),
    "volumesRemoved": False,
    "containerFreeBytes": stat.f_bavail * stat.f_frsize,
    "imagePrune": image_prune_output,
}}))
'''


def _run(argv: list[str], *, env: dict[str, str] | None = None) -> dict[str, Any]:
    result = subprocess.run(
        argv,
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        check=False,
    )
    payload: dict[str, Any] = {
        "argv": argv,
        "exitCode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if result.returncode != 0:
        raise PrevalidationError(
            f"command failed ({' '.join(argv[:3])}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return payload


def _install_unit(
    *,
    host: str,
    projection: PlaneProjection,
    key_dir: Path,
    replica_id: str,
    remote_root: str,
) -> dict[str, Any]:
    key = _resolve_key(projection, key_dir)
    unit = f"quwoquan-{projection.name}-prevalidate-{replica_id}.service"
    command = (
        "set -euo pipefail; "
        "unit_dir=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user; "
        "install -d -m 700 \"$unit_dir\"; "
        f"install -m 600 {remote_root}/systemd/{unit} \"$unit_dir/{unit}\"; "
        "systemctl --user daemon-reload; "
        f"systemctl --user enable --now {unit}; "
        f"systemctl --user is-enabled --quiet {unit}; "
        f"systemctl --user is-active --quiet {unit}"
    )
    result = subprocess.run(
        [
            "ssh",
            "-i",
            str(key),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{projection.account}@{host}",
            "bash -s",
        ],
        input=command,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise PrevalidationError(
            f"systemd activation failed for {projection.name}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return {
        "plane": projection.name,
        "replicaId": replica_id,
        "unit": unit,
        "exitCode": result.returncode,
        "stdout": result.stdout,
    }


def execute_deployment(
    args: argparse.Namespace,
    spec: dict[str, Any],
    projections: dict[str, PlaneProjection],
    placements: dict[str, DeploymentReplica],
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    image_reports: dict[str, Any] = {}
    reclaim_policy = dict(spec.get("staleRuntimeReclaimPolicy") or {})
    reclaim_policy["minimumHostResources"] = dict(
        spec.get("minimumHostResources") or {}
    )
    reclaim_reports = [
        _reclaim_stale_runtime(
            host=placements[projection.name].ssh_host,
            projection=projection,
            key_dir=args.key_dir,
            policy=reclaim_policy,
        )
        for projection in projections.values()
    ]
    readiness_policy = spec.get("readinessPolicy") or {}
    provider_bound_services = set(
        str(item) for item in readiness_policy.get("providerBoundServices") or []
    )
    for name, projection in projections.items():
        placement = placements[name]
        render_dir = deployment_render_dir(
            "prod", target="prod-hosted", name=placement.render_name
        )
        steps.append(
            _run(
                [
                    "python3",
                    "quwoquan_ops/cli/prod/render_prod_plane_stack.py",
                    "--plane",
                    name,
                    "--instance",
                    "prevalidate",
                    "--replica-id",
                    placement.replica_id,
                    "--host-id",
                    placement.host_id,
                    "--candidate-digest",
                    args.candidate_digest,
                    "--image-transport-tag",
                    args.image_transport_tag,
                    "--output-dir",
                    str(render_dir),
                    "--host",
                    placement.ssh_host,
                    "--data-mode",
                    args.data_mode,
                    "--prevalidate-scope",
                    args.scope,
                ]
            )
        )
        services = ",".join(
            projection.startup_services + projection.image_only_services
        )
        image_step = _run(
            [
                "python3",
                "quwoquan_ops/cli/prod/load_prod_plane_images.py",
                "--plane",
                name,
                "--host",
                placement.ssh_host,
                "--key-dir",
                str(args.key_dir),
                "--services",
                services,
                "--image-transport-tag",
                args.image_transport_tag,
                "--frozen-diagnostic-snapshot",
                str(args.frozen_diagnostic_snapshot),
                "--platform",
                "linux/amd64",
            ]
        )
        steps.append(image_step)
        image_reports[name] = json.loads(image_step["stdout"])
        steps.append(
            _run(
                [
                    "bash",
                    "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh",
                    "--plane",
                    name,
                    "--host",
                    placement.ssh_host,
                    "--source-dir",
                    str(render_dir),
                    "--root-suffix",
                    f"instances/prevalidate/{placement.replica_id}",
                ]
            )
        )
    units = [
        _install_unit(
            host=placements[item.name].ssh_host,
            projection=item,
            key_dir=args.key_dir,
            replica_id=placements[item.name].replica_id,
            remote_root=placements[item.name].remote_root,
        )
        for item in projections.values()
    ]
    runtime: dict[str, Any] = {}
    for _ in range(12):
        runtime = {}
        ready = True
        for name, projection in projections.items():
            placement = placements[name]
            inspect_argv = [
                "python3",
                "quwoquan_ops/cli/prod/inspect_prod_plane_runtime.py",
                "--plane",
                name,
                "--instance",
                "prevalidate",
                "--host-id",
                placement.host_id,
                "--replica-id",
                placement.replica_id,
                "--key-dir",
                str(args.key_dir),
            ]
            if args.host:
                inspect_argv.extend(["--host", args.host])
            step = _run(
                inspect_argv
            )
            report = json.loads(step["stdout"])
            runtime[name] = report
            containers = report.get("containers") or []
            by_service = {
                str(item.get("composeService")): item
                for item in containers
                if item.get("composeService")
            }
            present = set(projection.startup_services).issubset(by_service)
            delivered = image_reports.get(name) or {}
            delivered_digests = delivered.get("remoteImageContentDigests") or {}
            digest_matches = all(
                (by_service.get(service) or {}).get("imageId")
                == delivered_digests.get(service)
                for service in projection.startup_services
            ) and all(
                delivered_digests.get(service)
                for service in projection.image_only_services
            )
            running = all(
                (by_service.get(service) or {}).get("running") is True
                for service in projection.startup_services
            )
            first_party_health = all(
                service in provider_bound_services
                or (by_service.get(service) or {}).get("health")
                not in {"starting", "unhealthy"}
                for service in projection.startup_services
            )
            data_ready = True
            if name == "service" and args.data_mode == "isolated":
                isolated_services = tuple(
                    str(item)
                    for item in ((spec.get("isolatedData") or {}).get("services") or [])
                )
                persistent = set(isolated_services) - {"mongo-init", "object-storage-init"}
                initializers = {"mongo-init", "object-storage-init"}
                data_ready = set(isolated_services).issubset(by_service) and all(
                    (by_service.get(service) or {}).get("running") is True
                    and (by_service.get(service) or {}).get("health")
                    not in {"starting", "unhealthy"}
                    for service in persistent
                ) and all(
                    (
                        (by_service.get(service) or {}).get("running") is True
                        or (
                            (by_service.get(service) or {}).get("status") == "exited"
                            and int((by_service.get(service) or {}).get("exitCode") or 0) == 0
                        )
                    )
                    for service in initializers
                )
            unit = report.get("unit") or {}
            ready = (
                ready
                and present
                and running
                and first_party_health
                and data_ready
                and digest_matches
                and delivered.get("contentDigestVerified") is True
                and unit.get("enabled")
                and unit.get("active")
            )
        if ready:
            break
        time.sleep(5)
    else:
        raise PrevalidationError(
            "prevalidation units, isolated data, or first-party container runtime did not become ready"
        )
    return {
        "status": "passed",
        "namespace": spec.get("namespace"),
        "replicaId": next(iter(placements.values())).replica_id,
        "hostId": next(iter(placements.values())).host_id,
        "containerRuntime": "running",
        "providerReadiness": {
            "status": str(
                readiness_policy.get("providerReadinessStatus") or "GATE_BLOCK"
            ),
            "services": sorted(provider_bound_services),
            "excludedCapabilities": list(
                ((spec.get("excluded") or {}).get("capabilities") or [])
            ),
        },
        "dataEvidence": {
            "mode": args.data_mode,
            "releaseEvidenceEligible": False,
        },
        "staleRuntimeReclaim": reclaim_reports,
        "units": units,
        "runtime": runtime,
        "imageDelivery": image_reports,
        "steps": steps,
    }


def main() -> int:
    args = parse_args()
    result: dict[str, Any] = {
        "schema": "prod-hosted-first-party-prevalidation",
        "hostOverride": args.host,
        "selectedHostIds": list(args.host_id),
        "dataMode": args.data_mode,
        "scope": args.scope,
        "dryRun": args.dry_run,
        "containerDeployment": {"status": "not-run"},
        "releaseEligibility": {
            "status": "GATE_BLOCK",
            "promotable": False,
            "ledgerWritten": False,
            "receiptWritten": False,
        },
        "providerReadiness": {
            "status": "GATE_BLOCK",
            "excludedCapabilities": [],
        },
    }
    try:
        spec, projections = load_projection()
        result["providerReadiness"]["excludedCapabilities"] = list(
            ((spec.get("excluded") or {}).get("capabilities") or [])
        )
        if args.scope not in (spec.get("scopes") or []):
            raise PrevalidationError(f"scope is not allowed: {args.scope}")
        if args.data_mode not in (spec.get("allowedDataModes") or []):
            raise PrevalidationError(f"data mode is not allowed: {args.data_mode}")
        plan = resolve_plan(
            load_access_manifest(),
            instance="prevalidate",
            host_ids=args.host_id or None,
            ssh_host_override=args.host,
        )
        groups: dict[str, dict[str, DeploymentReplica]] = {}
        for placement in plan:
            groups.setdefault(placement.replica_id, {})[placement.plane] = placement
        preflight_replicas: list[dict[str, Any]] = []
        all_issues: list[str] = []
        for replica_id, placements in groups.items():
            if set(placements) != {"service", "edge"}:
                raise PrevalidationError(
                    f"prevalidation replica {replica_id} must include service and edge"
                )
            hosts = {item.ssh_host for item in placements.values()}
            if len(hosts) != 1:
                raise PrevalidationError(
                    f"prevalidation replica {replica_id} is not co-located"
                )
            host = next(iter(hosts))
            snapshots = collect_host_snapshots(host, projections, args.key_dir)
            issues = evaluate_host_snapshots(
                snapshots, spec, projections, data_mode=args.data_mode
            )
            scoped_issues = [f"{replica_id}: {issue}" for issue in issues]
            all_issues.extend(scoped_issues)
            preflight_replicas.append(
                {
                    "replicaId": replica_id,
                    "hostId": placements["service"].host_id,
                    "sshHost": host,
                    "status": "GATE_BLOCK" if issues else "checked",
                    "planes": snapshots,
                    "issues": scoped_issues,
                }
            )
        result["hostPreflight"] = {
            "status": "GATE_BLOCK" if all_issues else "checked",
            "replicas": preflight_replicas,
        }
        if len(preflight_replicas) == 1:
            result["hostPreflight"]["planes"] = preflight_replicas[0]["planes"]
        if all_issues:
            result["containerDeployment"] = {
                "status": "GATE_BLOCK",
                "issues": all_issues,
            }
            print(json.dumps(result, ensure_ascii=False))
            return 2
        if args.dry_run:
            result["containerDeployment"] = {
                "status": "planned",
                "namespace": spec.get("namespace"),
                "replicas": [
                    {
                        "replicaId": replica_id,
                        "hostId": placements["service"].host_id,
                        "planes": {
                            name: {
                                "startupServices": list(item.startup_services),
                                "imageAndConfigOnlyServices": list(
                                    item.image_only_services
                                ),
                            }
                            for name, item in projections.items()
                        },
                    }
                    for replica_id, placements in groups.items()
                ],
            }
        else:
            deployments = [
                execute_deployment(args, spec, projections, placements)
                for placements in groups.values()
            ]
            result["containerDeployment"] = {
                "status": "passed",
                "replicas": deployments,
            }
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        PrevalidationError,
        ProdHostedTopologyError,
    ) as error:
        result["containerDeployment"] = {
            "status": "GATE_BLOCK",
            "issues": [str(error)],
        }
        print(json.dumps(result, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
