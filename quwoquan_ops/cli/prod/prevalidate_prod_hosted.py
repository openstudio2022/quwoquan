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

from quwoquan_ops.cli.lib.data_plane_binding import DATA_PLANE_BINDING_PACKAGE_REF
from quwoquan_ops.cli.lib.deployment_candidate_manifest import load_candidate_manifest
from quwoquan_ops.cli.lib.output_paths import (
    active_deployment_candidate,
    deployment_candidate_dir,
    deployment_render_dir,
)
from quwoquan_ops.cli.prod.load_prod_plane_images import normalize_image_id
from quwoquan_ops.cli.prod.prod_hosted_topology import (
    DeploymentReplica,
    ProdHostedTopologyError,
    load_access_manifest,
    resolve_plan,
)

ACCESS_MANIFEST = ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
DEFAULT_KEY_DIR = Path.home() / ".ssh" / "quwoquan-prod"
DIGEST_REF = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}")


COMMAND_TIMEOUT_SECONDS = 120
TRANSFER_TIMEOUT_SECONDS = 3600
ACTIVATION_TIMEOUT_SECONDS = 300
# systemd 终态清理、属性读回与 SSH 传输分别留余量，外层不抢先截断首因。
ACTIVATION_COMMAND_TIMEOUT_SECONDS = ACTIVATION_TIMEOUT_SECONDS + 30
ACTIVATION_REMOTE_TIMEOUT_SECONDS = ACTIVATION_TIMEOUT_SECONDS + 120
ACTIVATION_SSH_TIMEOUT_SECONDS = ACTIVATION_REMOTE_TIMEOUT_SECONDS + 30
SSH_OPTIONS = (
    "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
    "-o", "ConnectTimeout=12", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3",
)
READINESS_TIMEOUT_SECONDS = 300
READINESS_POLL_SECONDS = 5


class PrevalidationError(RuntimeError):
    def __init__(self, message: str, *, code: str = "PREVALIDATION_FAILED", **diagnostics: Any):
        super().__init__(message)
        self.blocker = {"code": code, "message": message, **diagnostics}


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
    # 两类互斥的不可提升输入：reviewed main 的 GHCR frozen snapshot，或 integration
    # exact dev candidate 的本机 local-build rehearsal 物料（DEC-013）。
    material = parser.add_mutually_exclusive_group(required=True)
    material.add_argument("--frozen-diagnostic-snapshot", type=Path, default=None)
    material.add_argument("--exact-candidate", default="")
    parser.add_argument("--image-transport-tag", required=True)
    parser.add_argument("--candidate-digest", required=True)
    parser.add_argument("--data-mode", choices=("isolated", "external"), required=True)
    parser.add_argument("--data-plane-binding", type=Path, default=None)
    parser.add_argument("--scope", choices=("first-party",), required=True)
    parser.add_argument("--key-dir", type=Path, default=DEFAULT_KEY_DIR)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()



def validate_rehearsal_candidate(args: argparse.Namespace) -> dict[str, Any]:
    """`--exact-candidate` 只接受已封存的 local-build rehearsal 候选（SIT-003 t1/t3）。"""

    if not args.exact_candidate:
        return {"materialSource": "factory"}
    if args.exact_candidate != args.candidate_digest:
        raise PrevalidationError("rehearsal exact candidate must equal --candidate-digest")
    if args.image_transport_tag != args.candidate_digest.removeprefix("sha256:"):
        raise PrevalidationError(
            "rehearsal image transport tag must be the candidate digest hex"
        )
    from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
        prod_hosted_rehearsal as rehearsal,
    )

    # 渲染面按 active candidate pointer 读取服务包；exact candidate 必须就是它，
    # 否则交付的镜像与渲染的配置会来自两个不同候选。
    active = active_deployment_candidate("prod-hosted")
    active_id = str((active or {}).get("baselineId") or "")
    if active_id != args.exact_candidate:
        raise PrevalidationError(
            "rehearsal exact candidate must be the active prod-hosted candidate: "
            f"active={active_id or 'none'}"
        )
    candidate_root = deployment_candidate_dir("prod-hosted", args.exact_candidate)
    oci_path = candidate_root / "packages/runtime-shared/oci-images.json"
    try:
        oci = json.loads(oci_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PrevalidationError(f"rehearsal candidate OCI manifest unreadable: {error}") from error
    if not rehearsal.is_rehearsal_oci_manifest(oci):
        raise PrevalidationError("rehearsal candidate must be local-build material")
    candidate = load_candidate_manifest(
        "prod",
        "prod-hosted",
        args.exact_candidate,
        require_full=True,
        purpose="self_verify",
    )
    try:
        source = rehearsal.rehearsal_candidate_source_gate(
            candidate, repo_root=ROOT, candidate_root=candidate_root
        )
        rehearsal.verify_local_rehearsal_images(oci)
    except rehearsal.RehearsalError as error:
        raise PrevalidationError(str(error)) from error
    return {
        "materialSource": rehearsal.REHEARSAL_MATERIAL_SOURCE,
        "platform": rehearsal.REHEARSAL_PLATFORM,
        "nonPromotable": True,
        "legalStaticPlaceholder": bool(oci.get("legalStaticPlaceholder")),
        "publicEntry": str(oci.get("publicEntry") or ""),
        "sourceRevision": source["sourceRevision"],
    }


def validate_external_data_plane_candidate(args: argparse.Namespace) -> Path | None:
    if args.data_mode != "external":
        return None
    candidate_root = deployment_candidate_dir("prod-hosted", args.candidate_digest)
    expected = candidate_root / DATA_PLANE_BINDING_PACKAGE_REF.as_posix()
    binding = args.data_plane_binding
    if (
        binding is None
        or not binding.is_absolute()
        or binding != expected
        or binding.is_symlink()
        or not binding.is_file()
    ):
        raise PrevalidationError(
            "external prevalidation requires the candidate-owned data-plane binding"
        )
    candidate = load_candidate_manifest(
        "prod",
        "prod-hosted",
        args.candidate_digest,
        require_full=True,
        purpose="self_verify",
    )
    if candidate.get("baselineId") != args.candidate_digest:
        raise PrevalidationError("external prevalidation candidate identity mismatch")
    return binding

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
        ports = tuple(int(item["published"]) for item in projected.get("publishedPorts") or [])
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
        timeout=15,
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
        result = _bounded_command(
            [
                "ssh", *SSH_OPTIONS, "-i", str(key),
                f"{projection.account}@{host}",
                "python3 -",
            ],
            input=_remote_snapshot_script(),
            phase="preflight",
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise PrevalidationError(
                f"SSH isolation preflight failed for {projection.account}",
                code="PREFLIGHT_SSH_FAILED", plane=name, exitCode=result.returncode,
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
    result = _bounded_command(
        [
            "ssh", *SSH_OPTIONS, "-i", str(key),
            f"{projection.account}@{host}",
            "python3 -",
        ],
        input=script,
        phase="reclaim",
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise PrevalidationError(
            "scoped stale runtime reclaim failed",
            code="RECLAIM_FAILED", plane=projection.name, exitCode=result.returncode,
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
        timeout=15,
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

# 未引用的镜像可能属于尚未启动的候选，不做全库 prune。
stat = os.statvfs(pathlib.Path.home())
print(json.dumps({{
    "plane": "{projection.name}",
    "status": "completed",
    "removedContainers": sorted(removed_names),
    "removedExternalBuildContainers": sorted(external_removed),
    "preservedContainers": sorted(preserved),
    "volumesRemoved": False,
    "containerFreeBytes": stat.f_bavail * stat.f_frsize,
    "imagePrune": "skipped-candidate-preservation",
}}))
'''


def _bounded_command(
    argv: list[str], *, phase: str, timeout: float = COMMAND_TIMEOUT_SECONDS, **kwargs: Any,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as error:
        raise PrevalidationError(
            f"{phase} exceeded {timeout:g}s", code=f"{phase.upper()}_TIMEOUT",
            phase=phase, timeoutSeconds=timeout,
        ) from error


def _run(
    argv: list[str], *, env: dict[str, str] | None = None,
    phase: str = "command", timeout: float = COMMAND_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    result = _bounded_command(
        argv, phase=phase, timeout=timeout,
        cwd=ROOT,
        env={**os.environ, **(env or {}), "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, check=False,
    )
    payload: dict[str, Any] = {
        "argv": argv,
        "exitCode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        cause = re.match(r"(?:FAIL: )?([A-Z][A-Z_]+):", detail)
        cause_code = cause.group(1) if cause else ""
        code = f"{phase.upper()}_TIMEOUT" if cause_code.endswith("_TIMEOUT") else f"{phase.upper()}_FAILED"
        raise PrevalidationError(
            f"{phase} failed ({' '.join(argv[:3])}): {detail}",
            code=code, phase=phase, exitCode=result.returncode, causeCode=cause_code,
        )
    return payload


def _remote_activation_script(unit: str, remote_root: str) -> str:
    """仅在受管 prevalidate unit 内串行重放；不运行 compose 的销毁路径。"""
    return f'''
import fcntl
import json
import os
import pathlib
import re
import subprocess
import time

unit = {unit!r}
source = pathlib.Path({remote_root!r}) / "systemd" / unit
deadline = time.monotonic() + {ACTIVATION_REMOTE_TIMEOUT_SECONDS}
report = {{"status": "GATE_BLOCK"}}
step = "install"
lock = None

def run(arguments, budget):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired(arguments, budget)
    return subprocess.run(
        ["systemctl", "--user"] + arguments, timeout=min(budget, remaining),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False,
    )

try:
    os.umask(0o077)
    unit_dir = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home() / ".config") / "systemd/user"
    unit_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = os.open(str(unit_dir / (unit + ".activate.lock")), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    step = "lock"
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    step = "install"
    (unit_dir / unit).write_bytes(source.read_bytes())
    (unit_dir / unit).chmod(0o600)
    override_dir = unit_dir / (unit + ".d")
    override_dir.mkdir(mode=0o700, exist_ok=True)
    # daemon-reload 先清除旧 ExecStop，restart 才不会执行 compose 销毁动作。
    # drop-in 随 prevalidate unit 保留；正式 unit 与其他账号完全不受影响。
    (override_dir / "activate.conf").write_text(
        "[Service]\\nExecStop=\\nExecStopPost=\\nTimeoutStartSec={ACTIVATION_TIMEOUT_SECONDS}\\nTimeoutStopSec=15\\n", encoding="utf-8",
    )
    commands = [
        (["daemon-reload"], 15), (["enable", unit], 15),
        (["restart", unit], {ACTIVATION_COMMAND_TIMEOUT_SECONDS}),
        (["is-enabled", "--quiet", unit], 15), (["is-active", "--quiet", unit], 15),
    ]
    for arguments, budget in commands:
        step = arguments[0]
        completed = run(arguments, budget)
        if completed.returncode != 0:
            report["firstBlocker"] = {{"code": "ACTIVATION_FAILED", "step": step, "exitCode": completed.returncode}}
            break
    else:
        report["status"] = "passed"
except BlockingIOError:
    report["firstBlocker"] = {{"code": "ACTIVATION_BUSY", "step": step}}
except subprocess.TimeoutExpired:
    report["firstBlocker"] = {{"code": "ACTIVATION_TIMEOUT", "step": step}}
except OSError:
    report["firstBlocker"] = {{"code": "ACTIVATION_FAILED", "step": step}}

# 只读闭集属性，不读 journal、环境或原始 stderr；诊断失败不能覆盖 activation 首因。
try:
    if step in {{"restart", "is-enabled", "is-active"}} and "firstBlocker" in report:
        properties = ["Result", "ExecMainCode", "ExecMainStatus", "ActiveState", "SubState"]
        try:
            diagnostic = run(["show", unit] + [value for key in properties for value in ("-p", key)], 15)
            if diagnostic.returncode != 0:
                report["diagnosticBlocker"] = {{"code": "ACTIVATION_DIAGNOSTIC_FAILED", "exitCode": diagnostic.returncode}}
            else:
                state = {{}}
                for line in diagnostic.stdout.splitlines():
                    key, separator, value = line.partition("=")
                    if separator and key in properties and re.fullmatch(r"[a-z0-9-]{{1,64}}", value):
                        state[key] = value
                report["systemdState"] = state
                if step == "restart" and state.get("Result") == "timeout":
                    report["firstBlocker"]["code"] = "ACTIVATION_TIMEOUT"
        except (OSError, subprocess.TimeoutExpired) as error:
            report["diagnosticBlocker"] = {{"code": "ACTIVATION_DIAGNOSTIC_TIMEOUT" if isinstance(error, subprocess.TimeoutExpired) else "ACTIVATION_DIAGNOSTIC_FAILED"}}
finally:
    if lock is not None:
        os.close(lock)
print(json.dumps(report))
if report["status"] != "passed":
    raise SystemExit(2)
'''


def _install_unit(
    *, host: str, projection: PlaneProjection, key_dir: Path,
    replica_id: str, remote_root: str,
) -> dict[str, Any]:
    if projection.name not in {"service", "edge"} or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", replica_id) is None:
        raise PrevalidationError("activation must target a managed prevalidate unit", code="ACTIVATION_SCOPE_INVALID")
    key = _resolve_key(projection, key_dir)
    unit = f"quwoquan-{projection.name}-prevalidate-{replica_id}.service"
    try:
        result = _bounded_command(
            ["ssh", *SSH_OPTIONS, "-i", str(key), f"{projection.account}@{host}", "python3 -"],
            input=_remote_activation_script(unit, remote_root), phase="activation",
            timeout=ACTIVATION_SSH_TIMEOUT_SECONDS, text=True, capture_output=True, check=False,
        )
    except PrevalidationError as error:
        error.blocker.update(plane=projection.name, unit=unit, firstReason={"code": "ACTIVATION_TRANSPORT_TIMEOUT"})
        raise
    try:
        report = json.loads(result.stdout) if result.returncode in {0, 2} else {}
    except json.JSONDecodeError:
        report = {}
    if not isinstance(report, dict):
        report = {}
    if result.returncode != 0 or report.get("status") != "passed":
        first = report.get("firstBlocker") or {"code": "ACTIVATION_FAILED", "step": "transport", "exitCode": result.returncode}
        raise PrevalidationError(
            f"systemd activation failed for {projection.name} at {first.get('step')}",
            code=first["code"], plane=projection.name, unit=unit, firstReason=first,
            systemdState=report.get("systemdState") or {}, diagnosticBlocker=report.get("diagnosticBlocker"),
        )
    return {"plane": projection.name, "replicaId": replica_id, "unit": unit,
            "exitCode": result.returncode, "status": "passed"}


def _runtime_blockers(
    report: dict[str, Any], projection: PlaneProjection, spec: dict[str, Any],
    delivered: dict[str, Any], *, data_mode: str,
) -> list[dict[str, Any]]:
    """按 required 闭包判定；Provider 例外不豁免存活、身份或探针存在性。"""
    blockers: list[dict[str, Any]] = []

    def add(code: str, service: str = "", *, terminal: bool = False, **details: Any) -> None:
        blockers.append({"code": code, "plane": projection.name, "service": service,
                         "terminal": terminal, **details})

    by_service: dict[str, Any] = {}
    for item in report.get("containers") or []:
        service = str(item.get("composeService") or "")
        if service in by_service:
            add("CONTAINER_DUPLICATE", service, terminal=True)
        by_service[service] = item
    required = list(projection.startup_services)
    initializers = {"mongo-init", "object-storage-init"}
    if projection.name == "service":
        required.append("gamma-proxy")
        if data_mode == "isolated":
            required.extend((spec.get("isolatedData") or {}).get("services") or [])
    provider_bound = set((spec.get("readinessPolicy") or {}).get("providerBoundServices") or [])
    for service in dict.fromkeys(required):
        container = by_service.get(service)
        if container is None:
            add("CONTAINER_UNSCHEDULED", service)
            continue
        state = {key: container.get(key) for key in ("status", "running", "exitCode", "health", "error")}
        if container.get("oomKilled") is True:
            add("CONTAINER_OOM", service, terminal=True, **state)
        elif service in initializers:
            if container.get("error"):
                add("INITIALIZATION_FAILED", service, terminal=True, **state)
            elif container.get("status") == "exited":
                if container.get("running") is not False or type(container.get("exitCode")) is not int or container["exitCode"] != 0:
                    add("INITIALIZATION_FAILED", service, terminal=True, **state)
            elif container.get("status") in {"dead", "stopped"}:
                add("INITIALIZATION_FAILED", service, terminal=True, **state)
            else:
                add("INITIALIZATION_PENDING", service, **state)
        elif container.get("error"):
            add("CONTAINER_START_FAILED", service, terminal=True, **state)
        elif container.get("running") is not True:
            add("CONTAINER_EXITED" if container.get("status") in {"exited", "dead", "stopped"} else "CONTAINER_UNSCHEDULED",
                service, terminal=container.get("status") in {"exited", "dead", "stopped"}, **state)
        elif container.get("health") in {None, "", "not-configured"}:
            add("HEALTHCHECK_NOT_CONFIGURED", service, terminal=True, **state)
        elif container.get("health") != "healthy" and not (
            service in provider_bound and container.get("health") in {"starting", "unhealthy"}
        ):
            add("CONTAINER_UNHEALTHY", service, **state)
    digests = delivered.get("remoteImageContentDigests") or {}
    if delivered.get("contentDigestVerified") is not True:
        add("IMAGE_DELIVERY_UNVERIFIED", terminal=True)
    for service in projection.startup_services + projection.image_only_services:
        try:
            expected = normalize_image_id(digests.get(service))
            if service in projection.startup_services and service in by_service:
                if normalize_image_id(by_service[service].get("imageId")) != expected:
                    add("IMAGE_DIGEST_MISMATCH", service, terminal=True)
        except ValueError:
            add("IMAGE_ID_INVALID", service, terminal=True)
    unit = report.get("unit") or {}
    if unit.get("enabled") is not True or unit.get("active") is not True:
        add("UNIT_NOT_READY", unit=unit.get("name"), enabled=unit.get("enabled"), active=unit.get("active"))
    return blockers


def _wait_for_readiness(
    args: argparse.Namespace, spec: dict[str, Any], projections: dict[str, PlaneProjection],
    placements: dict[str, DeploymentReplica], image_reports: dict[str, Any],
) -> dict[str, Any]:
    deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
    first_reason: dict[str, Any] | None = None
    runtime: dict[str, Any] = {}
    latest: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        latest = []
        for name, projection in projections.items():
            placement = placements[name]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            argv = ["python3", "quwoquan_ops/cli/prod/inspect_prod_plane_runtime.py",
                    "--plane", name, "--instance", "prevalidate", "--host-id", placement.host_id,
                    "--replica-id", placement.replica_id, "--key-dir", str(args.key_dir)]
            if args.host:
                argv.extend(["--host", args.host])
            try:
                step = _run(argv, phase="readiness", timeout=min(COMMAND_TIMEOUT_SECONDS, remaining))
                report = json.loads(step["stdout"])
            except PrevalidationError as error:
                error.blocker["firstReason"] = first_reason or dict(error.blocker)
                raise
            runtime[name] = report
            latest.extend(_runtime_blockers(report, projection, spec, image_reports.get(name) or {}, data_mode=args.data_mode))
            if latest and first_reason is None:
                first_reason = latest[0]
            terminal = next((item for item in latest if item["terminal"]), None)
            if terminal:
                raise PrevalidationError(
                    f"{terminal['code']}: {terminal['plane']}/{terminal['service']}",
                    code=terminal["code"], firstReason=first_reason, blockers=latest,
                )
        remaining = deadline - time.monotonic()
        if not latest and len(runtime) == len(projections) and remaining > 0:
            return runtime
        if remaining > 0:
            time.sleep(min(READINESS_POLL_SECONDS, remaining))
    raise PrevalidationError(
        "prevalidation readiness deadline exceeded", code="READINESS_TIMEOUT",
        timeoutSeconds=READINESS_TIMEOUT_SECONDS, firstReason=first_reason, blockers=latest,
    )


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
                    *(
                        ["--data-plane-binding", str(args.data_plane_binding)]
                        if args.data_mode == "external"
                        else []
                    ),
                ]
            )
        )
        services = ",".join(
            projection.startup_services + projection.image_only_services
        )
        if args.exact_candidate:
            image_source_argv = [
                "--image-source",
                "local",
                "--candidate-oci-manifest",
                str(
                    deployment_candidate_dir("prod-hosted", args.exact_candidate)
                    / "packages/runtime-shared/oci-images.json"
                ),
            ]
        else:
            image_source_argv = [
                "--image-source",
                "factory",
                "--frozen-diagnostic-snapshot",
                str(args.frozen_diagnostic_snapshot),
            ]
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
                "--candidate-digest",
                args.candidate_digest,
                "--image-transport-tag",
                args.image_transport_tag,
                *image_source_argv,
                "--platform",
                "linux/amd64",
            ], phase="transfer", timeout=TRANSFER_TIMEOUT_SECONDS,
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
                ], phase="transfer", timeout=TRANSFER_TIMEOUT_SECONDS,
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
    runtime = _wait_for_readiness(args, spec, projections, placements, image_reports)
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
        result["material"] = validate_rehearsal_candidate(args)
        validate_external_data_plane_candidate(args)
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
            "firstBlocker": error.blocker if isinstance(error, PrevalidationError) else {
                "code": "PREVALIDATION_FAILED", "message": str(error),
            },
        }
        print(json.dumps(result, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
