from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / ".qwq_output"

DEPLOY_ENVS = frozenset({"alpha", "beta", "gamma", "prod"})
ENV_SEGMENTS = DEPLOY_ENVS | {"repo"}
DATA_SEGMENT = "data"


def safe_segment(value: str, *, fallback: str = "run") -> str:
    text = str(value or "").strip().replace("/", "-")
    return text or fallback


def output_root() -> Path:
    return OUTPUT_ROOT


def env_for_target(target: str) -> str:
    target = str(target or "").strip()
    if target.startswith("alpha"):
        return "alpha"
    if target.startswith("beta"):
        return "beta"
    if target.startswith("gamma"):
        return "gamma"
    if target.startswith("prod"):
        return "prod"
    return "repo"


def normalize_env(env_name: str, *, target: str = "") -> str:
    env_name = str(env_name or "").strip()
    if env_name in ENV_SEGMENTS:
        return env_name
    if env_name == DATA_SEGMENT:
        return DATA_SEGMENT
    return env_for_target(target)


def env_root(env_name: str) -> Path:
    env = normalize_env(env_name)
    if env == DATA_SEGMENT:
        raise ValueError("data output must use data_* helpers")
    return OUTPUT_ROOT / "env" / env


def env_runs_root(env_name: str) -> Path:
    return env_root(env_name) / "runs"


def env_run_dir(env_name: str, command_name: str, *, target: str = "local") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    env = normalize_env(env_name, target=target)
    return env_runs_root(env) / f"{stamp}-{safe_segment(command_name)}-{safe_segment(target, fallback='local')}"


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


def repo_local_dir(name: str) -> Path:
    return env_local_root("repo") / safe_segment(name, fallback="local")


def data_root() -> Path:
    return OUTPUT_ROOT / DATA_SEGMENT


def data_runs_root() -> Path:
    return data_root() / "runs"


def data_run_dir(command_name: str, *, target: str = "data") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return data_runs_root() / f"{stamp}-{safe_segment(command_name)}-{safe_segment(target, fallback='data')}"


def data_observability_root() -> Path:
    return data_root() / "observability"


def data_observability_run_dir(run_id: str) -> Path:
    return data_observability_root() / safe_segment(run_id)


def data_release_root() -> Path:
    return data_root() / "release"


def data_local_root() -> Path:
    return data_root() / "local" / "runtime"
