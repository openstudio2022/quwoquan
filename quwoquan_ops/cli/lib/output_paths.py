"""The only local output-root contract.

``.qwq_output`` contains only redacted run evidence, observability records,
process records and disposable caches. Deployment packages, rendered
configuration and certificate exports are outside the repository output tree;
configuration/network truth stays in domain deploy assets and Ops environment
manifests.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = ROOT / ".qwq_output"
DEFAULT_DEPLOY_WORK_ROOT = Path.home() / ".cache" / "quwoquan" / "deploy"
DEPLOY_ENVS = frozenset({"alpha", "beta", "gamma", "prod"})
ENV_SEGMENTS = DEPLOY_ENVS | {"repo"}
DEFAULT_DEPLOY_TARGET_BY_ENV = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}


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


def env_local_root(env_name: str) -> Path:
    return env_root(env_name) / "local"


def target_local_dir(target: str) -> Path:
    return env_local_root(env_for_target(target)) / safe_segment(target, fallback="local")


def target_process_dir(target: str) -> Path:
    return target_local_dir(target) / "process"


def target_cache_dir(target: str) -> Path:
    return target_local_dir(target) / "cache"


def deployment_work_root(target: str) -> Path:
    """Return the external deployment workspace for configuration and payloads."""
    configured = os.environ.get("QWQ_DEPLOY_WORK_ROOT", "").strip()
    base = (
        Path(configured).expanduser()
        if configured
        else DEFAULT_DEPLOY_WORK_ROOT
    )
    resolved_base = base.resolve()
    try:
        resolved_base.relative_to(output_root().expanduser().resolve())
    except ValueError:
        pass
    else:
        raise ValueError(
            "QWQ_DEPLOY_WORK_ROOT must be outside QWQ_OUTPUT_ROOT; "
            ".qwq_output cannot contain deployment configuration or payloads"
        )
    return base / safe_segment(target, fallback="local")


def deployment_target_for_env(env_name: str, *, target: str = "") -> str:
    """Resolve the only deployment workspace target allowed for an environment."""
    env = normalize_env(env_name)
    requested = str(target or os.environ.get("QWQ_DEPLOY_TARGET", "")).strip()
    if not requested:
        return DEFAULT_DEPLOY_TARGET_BY_ENV[env]
    if env_for_target(requested) != env:
        raise ValueError(
            f"deployment target {requested!r} does not belong to environment {env!r}"
        )
    return safe_segment(requested, fallback=DEFAULT_DEPLOY_TARGET_BY_ENV[env])


def deployment_package_root(env_name: str, *, target: str = "") -> Path:
    """Return the external deployment-payload root for one environment target."""
    return deployment_work_root(
        deployment_target_for_env(env_name, target=target)
    ) / "packages"


def app_deployment_package_dir(env_name: str, *, target: str = "") -> Path:
    return deployment_package_root(env_name, target=target) / "app"


def service_deployment_package_dir(
    env_name: str,
    service: str,
    *,
    target: str = "",
) -> Path:
    return (
        deployment_package_root(env_name, target=target)
        / "service"
        / safe_segment(service, fallback="service")
    )


def legal_static_deployment_package_dir(env_name: str, *, target: str = "") -> Path:
    return deployment_package_root(env_name, target=target) / "legal-static"


def runtime_shared_deployment_package_dir(
    env_name: str,
    *,
    target: str = "",
) -> Path:
    return deployment_package_root(env_name, target=target) / "runtime-shared"


def portal_deployment_package_dir(env_name: str, *, target: str = "") -> Path:
    return deployment_package_root(env_name, target=target) / "ops-portal"


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
