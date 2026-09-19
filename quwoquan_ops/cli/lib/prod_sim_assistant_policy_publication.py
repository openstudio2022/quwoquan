"""Package-bound Assistant policy publication for prod-sim local rehearsal.

prod-sim compose does not run the hosted policy-publish Job.  StartAssistantRun
resolves assistant-default from Mongo; an empty rehearsal volume therefore
fails closed with run_policy_unavailable.  This publisher applies the frozen
image's revision chain onto the live service-core Mongo using the same
assistant-policy-publish command hosted uses, without promoting the result.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from collections.abc import Callable, Mapping
from typing import Any

import yaml

from .environment_topology import formal_release_compose_project_name
from .output_paths import ROOT, deployment_target_path

PROD_SIM_TARGET = "prod-sim"
SERVICE_CORE = "service-core"
CONTAINER_CONFIG_ROOT = "/etc/qwq-config"
CONTAINER_POLICY_ROOT = "/app/resources/policies"
CONTAINER_PUBLISHER = "/tmp/qwq-assistant-policy-publish"
_REVISION = re.compile(r"^assistant/assistant-default/rollouts/revision-(\d+)\.json$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_GOARCH = {
    "amd64": "amd64",
    "x86_64": "amd64",
    "arm64": "arm64",
    "aarch64": "arm64",
}

RunCommand = Callable[..., subprocess.CompletedProcess[str]]


class ProdSimAssistantPolicyPublicationError(RuntimeError):
    pass


def _run(
    command: list[str],
    *,
    runner: RunCommand,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = runner(
        command,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if not isinstance(completed, subprocess.CompletedProcess):
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy publisher command result is invalid"
        )
    return completed


def _require_ok(completed: subprocess.CompletedProcess[str], *, action: str) -> str:
    if completed.returncode != 0:
        detail = str(completed.stderr or completed.stdout or "").strip().splitlines()
        last = detail[-1].strip() if detail else ""
        lowered = last.lower()
        if any(token in lowered for token in ("mongodb://", "postgres://", "password", "secret")):
            last = ""
        suffix = f": {last}" if last else ""
        raise ProdSimAssistantPolicyPublicationError(
            f"prod-sim assistant policy {action} failed{suffix}"
        )
    return str(completed.stdout or "")


def linux_goarch(architecture: str) -> str:
    mapped = _GOARCH.get(str(architecture or "").strip().lower())
    if mapped is None:
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy publisher architecture is unsupported"
        )
    return mapped


def publication_chain(
    *,
    current_rollout_ref: str,
    load_rollout: Callable[[str], Mapping[str, Any]],
) -> list[tuple[str, str]]:
    current = str(current_rollout_ref or "").strip()
    if _REVISION.fullmatch(current) is None:
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy rollout ref is invalid"
        )
    chain: list[tuple[str, str]] = []
    seen: set[str] = set()
    while current:
        if current in seen:
            raise ProdSimAssistantPolicyPublicationError(
                "prod-sim assistant policy rollout chain is cyclic"
            )
        seen.add(current)
        artifact = load_rollout(current)
        assignments = artifact.get("assignments") if isinstance(artifact, dict) else None
        if not isinstance(assignments, list) or not assignments:
            raise ProdSimAssistantPolicyPublicationError(
                "prod-sim assistant policy rollout assignments are unavailable"
            )
        digest = str((assignments[0] or {}).get("releaseDigest") or "").strip()
        if _DIGEST.fullmatch(digest) is None:
            raise ProdSimAssistantPolicyPublicationError(
                "prod-sim assistant policy release digest is invalid"
            )
        release_ref = f"assistant/assistant-default/releases/{digest}.json"
        chain.append((release_ref, current))
        expected = artifact.get("expectedRevision")
        if expected == 0:
            break
        if not isinstance(expected, int) or expected < 1:
            raise ProdSimAssistantPolicyPublicationError(
                "prod-sim assistant policy expected revision is invalid"
            )
        current = f"assistant/assistant-default/rollouts/revision-{expected}.json"
        if _REVISION.fullmatch(current) is None:
            raise ProdSimAssistantPolicyPublicationError(
                "prod-sim assistant policy predecessor rollout ref is invalid"
            )
    chain.reverse()
    if not chain:
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy publication chain is empty"
        )
    return chain


def _container_name(compose_project: str) -> str:
    return f"{compose_project}-{SERVICE_CORE}-1"


def _exec(
    container: str,
    args: list[str],
    *,
    runner: RunCommand,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return _run(
        ["docker", "exec", container, *args],
        runner=runner,
        timeout=timeout,
    )


def _inspect_architecture(container: str, *, runner: RunCommand) -> str:
    completed = _exec(container, ["uname", "-m"], runner=runner, timeout=30)
    architecture = _require_ok(completed, action="inspect").strip()
    return linux_goarch(architecture)


def _load_container_json(
    container: str,
    path: str,
    *,
    runner: RunCommand,
) -> dict[str, Any]:
    if not path.startswith(CONTAINER_POLICY_ROOT + "/") or ".." in path:
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy artifact path is invalid"
        )
    completed = _exec(container, ["cat", path], runner=runner)
    try:
        payload = json.loads(_require_ok(completed, action="artifact read"))
    except json.JSONDecodeError as error:
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy artifact is invalid"
        ) from error
    if not isinstance(payload, dict):
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy artifact is invalid"
        )
    return payload


def _assistant_runtime_snapshot(
    container: str, *, runner: RunCommand
) -> tuple[str, str]:
    completed = _exec(
        container,
        ["cat", f"{CONTAINER_CONFIG_ROOT}/assistant-service.yaml"],
        runner=runner,
    )
    try:
        config = yaml.safe_load(_require_ok(completed, action="config read"))
    except yaml.YAMLError as error:
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant runtime config is invalid"
        ) from error
    if not isinstance(config, dict):
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant runtime config is invalid"
        )
    identity = config.get("config")
    version = (
        str((identity or {}).get("version") or "").strip()
        if isinstance(identity, dict)
        else ""
    )
    if not version.startswith("sha256:") or len(version) != 71:
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant config version is invalid"
        )
    publication = config.get("policy_publication")
    rollout_ref = (
        str((publication or {}).get("rollout_artifact_ref") or "").strip()
        if isinstance(publication, dict)
        else ""
    )
    if _REVISION.fullmatch(rollout_ref) is None:
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy_publication.rollout_artifact_ref is invalid"
        )
    return version, rollout_ref


def _build_publisher(*, architecture: str, runner: RunCommand) -> Path:
    local_go = shutil.which("go")
    if not local_go:
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy publisher requires a local Go toolchain"
        )
    binary = deployment_target_path(PROD_SIM_TARGET, "tools", "assistant-policy-publish")
    binary.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "CGO_ENABLED": "0",
        "GOOS": "linux",
        "GOARCH": architecture,
        "GOFLAGS": "-mod=readonly",
    }
    completed = _run(
        [
            local_go,
            "build",
            "-buildvcs=false",
            "-o",
            str(binary),
            "./services/assistant-service/cmd/policy-publish",
        ],
        runner=runner,
        cwd=ROOT / "quwoquan_service",
        env=env,
        timeout=180,
    )
    if completed.returncode != 0:
        _require_ok(completed, action="publisher build")
    if not binary.is_file() or binary.is_symlink():
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy publisher binary is missing"
        )
    return binary


def publish_prod_sim_assistant_policy(
    *,
    compose_project: str | None = None,
    runner: RunCommand = subprocess.run,
) -> dict[str, Any]:
    project = require_compose_project(compose_project)
    container = _container_name(project)
    architecture = _inspect_architecture(container, runner=runner)
    version, rollout_ref = _assistant_runtime_snapshot(container, runner=runner)

    def load_rollout(reference: str) -> dict[str, Any]:
        return _load_container_json(
            container,
            f"{CONTAINER_POLICY_ROOT}/{reference}",
            runner=runner,
        )

    chain = publication_chain(current_rollout_ref=rollout_ref, load_rollout=load_rollout)
    binary = _build_publisher(architecture=architecture, runner=runner)
    copied = _run(
        ["docker", "cp", str(binary), f"{container}:{CONTAINER_PUBLISHER}"],
        runner=runner,
        timeout=60,
    )
    _require_ok(copied, action="publisher copy")
    publications: list[dict[str, Any]] = []
    try:
        for release_ref, step_rollout_ref in chain:
            published = _exec(
                container,
                [
                    CONTAINER_PUBLISHER,
                    "--env",
                    "prod",
                    "--config-root",
                    CONTAINER_CONFIG_ROOT,
                    "--config-version",
                    version,
                    "--resource-root",
                    CONTAINER_POLICY_ROOT,
                    "--release-ref",
                    release_ref,
                    "--rollout-ref",
                    step_rollout_ref,
                ],
                runner=runner,
                timeout=60,
            )
            raw = _require_ok(published, action="publication")
            try:
                report = json.loads(raw.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError) as error:
                raise ProdSimAssistantPolicyPublicationError(
                    "prod-sim assistant policy publication report is invalid"
                ) from error
            if not isinstance(report, dict) or not report.get("policyId"):
                raise ProdSimAssistantPolicyPublicationError(
                    "prod-sim assistant policy publication report is incomplete"
                )
            publications.append(
                {
                    "releaseRef": release_ref,
                    "rolloutRef": step_rollout_ref,
                    "policyId": report.get("policyId"),
                    "rolloutRevision": report.get("rolloutRevision"),
                    "stageReplayed": bool(report.get("stageReplayed")),
                    "activationReplayed": bool(report.get("activationReplayed")),
                }
            )
    finally:
        _run(
            ["docker", "exec", container, "rm", "-f", CONTAINER_PUBLISHER],
            runner=runner,
            timeout=30,
        )
    return {
        "schema": "stackctl-prod-sim-assistant-policy-publication",
        "target": PROD_SIM_TARGET,
        "composeProject": project,
        "configVersion": version,
        "publications": publications,
    }


def require_compose_project(compose_project: str | None) -> str:
    project = str(compose_project or "").strip()
    if not project:
        project = formal_release_compose_project_name(PROD_SIM_TARGET)
    expected = formal_release_compose_project_name(PROD_SIM_TARGET)
    if project != expected and not project.startswith(expected + "_"):
        raise ProdSimAssistantPolicyPublicationError(
            "prod-sim assistant policy publication compose project is invalid"
        )
    return project
