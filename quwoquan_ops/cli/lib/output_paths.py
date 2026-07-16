"""The only local output-root contract.

``.qwq_output`` contains only release payloads, run evidence, process records
and disposable caches. Deployment source configuration and certificate exports are
outside the repository output tree; configuration/network truth stays in domain
deploy assets and Ops environment manifests.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / ".qwq_output"
DEPLOY_ENVS = frozenset({"alpha", "beta", "gamma", "prod"})
ENV_SEGMENTS = DEPLOY_ENVS | {"repo"}


def safe_segment(value: str, *, fallback: str = "run") -> str:
    text = str(value or "").strip().replace("/", "-").replace("\\", "-")
    return text if text and text not in {".", ".."} else fallback


def output_root() -> Path:
    return Path(os.environ.get("QWQ_OUTPUT_ROOT") or DEFAULT_OUTPUT_ROOT)


def env_for_target(target: str) -> str:
    target = str(target or "").strip()
    for env in sorted(DEPLOY_ENVS):
        if target == env or target.startswith(f"{env}-"):
            return env
    raise ValueError(f"cannot resolve environment from target {target!r}")


def normalize_env(env_name: str, *, target: str = "") -> str:
    env_name = str(env_name or "").strip()
    if env_name in DEPLOY_ENVS:
        return env_name
    if not env_name and target:
        return env_for_target(target)
    raise ValueError(f"unknown environment {env_name!r}; expected one of {sorted(DEPLOY_ENVS)}")


def _timestamped_dir(parent: Path, command_name: str, target: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return parent / f"{stamp}-{safe_segment(command_name)}-{safe_segment(target, fallback='local')}"


def env_root(env_name: str) -> Path:
    return output_root() / "env" / normalize_env(env_name)


def env_runs_root(env_name: str) -> Path:
    return env_root(env_name) / "runs"


def env_run_dir(env_name: str, command_name: str, *, target: str = "local") -> Path:
    return _timestamped_dir(env_runs_root(normalize_env(env_name, target=target)), command_name, target)


def env_observability_root(env_name: str) -> Path:
    return env_root(env_name) / "observability"


def env_observability_run_dir(env_name: str, run_id: str) -> Path:
    return env_observability_root(env_name) / safe_segment(run_id)


def env_release_root(env_name: str) -> Path:
    return env_root(env_name) / "release"


def app_release_dir(env_name: str) -> Path:
    return env_release_root(env_name) / "app"


def service_release_dir(env_name: str, service: str) -> Path:
    return env_release_root(env_name) / "service" / safe_segment(service, fallback="service")


def legal_static_release_dir(env_name: str) -> Path:
    return env_release_root(env_name) / "legal-static"


def env_local_root(env_name: str) -> Path:
    return env_root(env_name) / "local"


def target_local_dir(target: str) -> Path:
    return env_local_root(env_for_target(target)) / safe_segment(target, fallback="local")


def target_process_dir(target: str) -> Path:
    return target_local_dir(target) / "process"


def target_cache_dir(target: str) -> Path:
    return target_local_dir(target) / "cache"


def deployment_work_root(target: str) -> Path:
    """Ephemeral rendered deployment files; never a repository output/config source."""
    configured = os.environ.get("QWQ_DEPLOY_WORK_ROOT", "").strip()
    base = (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".cache" / "quwoquan" / "deploy"
    )
    return base / safe_segment(target, fallback="local")


def certificate_export_dir(target: str) -> Path:
    """Temporary host copy of a container-managed CA for device trust injection."""
    return deployment_work_root(target) / "certificates"


def repo_root() -> Path:
    return output_root() / "env" / "repo"


def repo_runs_root() -> Path:
    return repo_root() / "runs"


def repo_run_dir(command_name: str, *, target: str = "repo") -> Path:
    return _timestamped_dir(repo_runs_root(), command_name, target)


def repo_local_dir(name: str) -> Path:
    return repo_root() / "local" / safe_segment(name, fallback="workspace") / "process"


def data_root() -> Path:
    return output_root() / "data"


def data_tasks_root() -> Path:
    return data_root() / "tasks"


def data_releases_root() -> Path:
    return data_root() / "releases"


def data_local_root() -> Path:
    return data_root() / "local"


def env_data_release_run_dir(env_name: str, release_id: str, run_id: str) -> Path:
    return env_runs_root(env_name) / "data-release" / safe_segment(release_id, fallback="release") / safe_segment(run_id)
