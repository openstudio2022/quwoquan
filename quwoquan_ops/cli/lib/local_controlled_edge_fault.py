from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from quwoquan_ops.cli.lib.environment_topology import (
    get_target,
    load_environment_topology,
    require_formal_release_compose_project,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import load_startup_attempt


LOCAL_TARGETS = frozenset({"alpha-local", "beta-local", "gamma-local"})
CONTROLLED_EDGE_SERVICES = ("api-edge", "gamma-proxy")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
HealthProbe = Callable[[str], bool]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
    )


def _probe_health(url: str) -> bool:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            return int(response.status) == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _command_failure(
    result: subprocess.CompletedProcess[str],
    *,
    action: str,
) -> RuntimeError:
    detail = (result.stderr or result.stdout or "").strip()
    return RuntimeError(
        f"controlled edge fault {action} failed"
        + (f": {detail[:600]}" if detail else f" (exit={result.returncode})")
    )


def _runtime_binding(target_name: str) -> dict[str, Any]:
    if target_name not in LOCAL_TARGETS:
        raise ValueError("controlled edge fault accepts only Alpha/Beta/Gamma local targets")
    receipt = load_startup_attempt(target_name)
    if not isinstance(receipt, dict) or receipt.get("status") != "running":
        raise ValueError(f"{target_name} has no running runtime receipt")
    environment = target_name.removesuffix("-local")
    if receipt.get("target") != target_name or receipt.get("env") != environment:
        raise ValueError("controlled edge fault runtime receipt target mismatch")
    if receipt.get("workload") != "full":
        raise ValueError("controlled edge fault requires the full App runtime workload")
    project = str(receipt.get("composeProject") or "").strip()
    try:
        require_formal_release_compose_project(target_name, project)
    except ValueError as exc:
        raise ValueError(
            "controlled edge fault runtime receipt Compose project mismatch"
        ) from exc
    configuration_digest = str(receipt.get("configurationDigest") or "").strip()
    if _DIGEST.fullmatch(configuration_digest) is None:
        raise ValueError("controlled edge fault runtime receipt has no configuration digest")
    composition = receipt.get("imageComposition")
    if not isinstance(composition, dict) or not isinstance(composition.get("images"), dict):
        raise ValueError("controlled edge fault runtime receipt has no image composition")
    return {
        "environment": environment,
        "target": target_name,
        "composeProject": project,
        "configurationDigest": configuration_digest,
        "images": composition["images"],
    }


def _container_for_service(
    *,
    project: str,
    service: str,
    images: dict[str, Any],
    runner: CommandRunner,
) -> dict[str, str]:
    lookup = runner(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            f"label=com.docker.compose.service={service}",
        ]
    )
    if lookup.returncode != 0:
        raise _command_failure(lookup, action=f"resolve {service}")
    container_ids = [line.strip() for line in lookup.stdout.splitlines() if line.strip()]
    if len(container_ids) != 1:
        raise ValueError(
            f"controlled edge fault requires exactly one {service} container; "
            f"found {len(container_ids)}"
        )
    container_id = container_ids[0]
    inspected = runner(["docker", "inspect", container_id])
    if inspected.returncode != 0:
        raise _command_failure(inspected, action=f"inspect {service}")
    try:
        payload = json.loads(inspected.stdout)
        container = payload[0]
        labels = container["Config"]["Labels"]
        image_ref = str(container["Config"]["Image"])
        runtime_image_id = str(container["Image"])
        status = str(container["State"]["Status"])
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"controlled edge fault inspect is invalid for {service}") from error
    if (
        labels.get("com.docker.compose.project") != project
        or labels.get("com.docker.compose.service") != service
    ):
        raise ValueError(f"controlled edge fault container labels mismatch for {service}")
    descriptor = images.get(service)
    expected_ref = (
        str(descriptor.get("ref") or "").strip()
        if isinstance(descriptor, dict)
        else ""
    )
    if service == "api-edge" and (not expected_ref or image_ref != expected_ref):
        raise ValueError("controlled edge fault api-edge image does not match runtime receipt")
    if status != "running":
        raise ValueError(f"controlled edge fault requires running {service}; status={status}")
    return {
        "service": service,
        "containerId": container_id,
        "imageRef": image_ref,
        "runtimeImageId": runtime_image_id,
        "statusBefore": status,
    }


@dataclass
class ControlledEdgeFault:
    target: str
    environment: str
    compose_project: str
    configuration_digest: str
    health_url: str
    containers: list[dict[str, str]]
    started_at: str
    runner: CommandRunner = field(repr=False)
    health_probe: HealthProbe = field(repr=False)
    sleep: Callable[[float], None] = field(repr=False)
    restored_at: str = ""

    @property
    def restored(self) -> bool:
        return bool(self.restored_at)

    def restore(self, *, timeout_seconds: float = 60.0) -> dict[str, Any]:
        if self.restored:
            return self.receipt()
        container_ids = [item["containerId"] for item in self.containers]
        started = self.runner(["docker", "start", *container_ids])
        if started.returncode != 0:
            raise _command_failure(started, action="restore containers")
        deadline = time.monotonic() + timeout_seconds
        last_states: dict[str, str] = {}
        while time.monotonic() < deadline:
            all_running = True
            for container in self.containers:
                inspected = self.runner(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{.State.Status}}",
                        container["containerId"],
                    ]
                )
                state = inspected.stdout.strip() if inspected.returncode == 0 else "inspect_failed"
                last_states[container["service"]] = state
                all_running = all_running and state == "running"
            if all_running and self.health_probe(self.health_url):
                self.restored_at = _utc_now()
                for container in self.containers:
                    container["statusAfter"] = last_states[container["service"]]
                return self.receipt()
            self.sleep(0.5)
        raise RuntimeError(
            "controlled edge fault restore did not regain API health: "
            + ", ".join(
                f"{service}={state}" for service, state in sorted(last_states.items())
            )
        )

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": "quwoquan_ops.controlled_edge_fault",
            "status": "restored" if self.restored else "fault_active",
            "target": self.target,
            "environment": self.environment,
            "composeProject": self.compose_project,
            "configurationDigest": self.configuration_digest,
            "healthUrl": self.health_url,
            "services": [dict(item) for item in self.containers],
            "faultStartedAt": self.started_at,
            "restoredAt": self.restored_at or None,
        }


def begin_controlled_edge_fault(
    target_name: str,
    *,
    runner: CommandRunner = _run,
    health_probe: HealthProbe = _probe_health,
    sleep: Callable[[float], None] = time.sleep,
) -> ControlledEdgeFault:
    binding = _runtime_binding(target_name)
    topology_target = get_target(load_environment_topology(), target_name)
    public_bases = topology_target.get("publicBases")
    if not isinstance(public_bases, dict) or not str(public_bases.get("api") or "").strip():
        raise ValueError("controlled edge fault target has no canonical API public base")
    health_url = str(public_bases["api"]).rstrip("/") + "/healthz"
    containers = [
        _container_for_service(
            project=str(binding["composeProject"]),
            service=service,
            images=dict(binding["images"]),
            runner=runner,
        )
        for service in CONTROLLED_EDGE_SERVICES
    ]
    container_ids = [item["containerId"] for item in containers]
    fault = ControlledEdgeFault(
        target=target_name,
        environment=str(binding["environment"]),
        compose_project=str(binding["composeProject"]),
        configuration_digest=str(binding["configurationDigest"]),
        health_url=health_url,
        containers=containers,
        started_at=_utc_now(),
        runner=runner,
        health_probe=health_probe,
        sleep=sleep,
    )
    stopped = runner(["docker", "stop", "--time", "10", *container_ids])
    if stopped.returncode != 0:
        failure = _command_failure(stopped, action="stop containers")
        try:
            fault.restore()
        except Exception as restore_error:  # noqa: BLE001
            raise RuntimeError(
                f"{failure}; fail-safe restore failed: {restore_error}"
            ) from restore_error
        raise failure
    if health_probe(health_url):
        fault.restore()
        raise RuntimeError("controlled edge fault did not make the canonical API unavailable")
    return fault
