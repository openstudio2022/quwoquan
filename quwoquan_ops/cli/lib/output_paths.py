"""The only local output-root contract.

``.qwq_output`` contains only redacted run evidence, observability records,
process records and disposable caches. Deployment packages, rendered
configuration and certificate exports are outside the repository output tree;
configuration/network truth stays in domain deploy assets and Ops environment
manifests.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

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
ACTIVE_CANDIDATE_SCHEMA = "stackctl-active-deployment-candidate"
PACKAGE_ROOT_OVERRIDE_ENV = "QWQ_DEPLOY_PACKAGE_ROOT_OVERRIDE"
_BASELINE_ID = re.compile(r"sha256:[0-9a-f]{64}")


def safe_segment(value: str, *, fallback: str = "run") -> str:
    text = str(value or "").strip().replace("/", "-").replace("\\", "-")
    return text if text and text not in {".", ".."} else fallback


def output_root() -> Path:
    return Path(os.environ.get("QWQ_OUTPUT_ROOT") or DEFAULT_OUTPUT_ROOT)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _deployment_segment(value: str, *, label: str, fallback: str = "") -> str:
    text = str(value or "").strip() or fallback
    candidate = Path(text)
    if (
        not text
        or text in {".", ".."}
        or "/" in text
        or "\\" in text
        or candidate.is_absolute()
        or len(candidate.parts) != 1
    ):
        raise ValueError(f"deployment {label} must be one safe path segment: {value!r}")
    return text


def _require_external_deployment_base(base: Path) -> None:
    repository_root = ROOT.resolve()
    repository_output_root = output_root().expanduser().resolve()
    if _is_within(base, repository_root):
        raise ValueError(
            "QWQ_DEPLOY_WORK_ROOT must be outside the repository source tree"
        )
    if _is_within(base, repository_output_root) or _is_within(
        repository_output_root,
        base,
    ):
        raise ValueError(
            "QWQ_DEPLOY_WORK_ROOT must be outside QWQ_OUTPUT_ROOT and must not overlap it; "
            ".qwq_output cannot contain deployment configuration or payloads"
        )


def _require_target_scoped_path(path: Path, *, target_root: Path) -> Path:
    candidate = target_root
    try:
        relative_parts = path.relative_to(target_root).parts
    except ValueError as exc:
        raise ValueError(
            f"deployment path escapes target-scoped workspace {target_root}: {path}"
        ) from exc
    for part in relative_parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError(
                "deployment path cannot traverse a symbolic link: "
                f"{candidate}"
            )
    resolved = path.resolve()
    if not _is_within(resolved, target_root):
        raise ValueError(
            f"deployment path escapes target-scoped workspace {target_root}: {path}"
        )
    return resolved


def deployment_target_path_in_work_root(
    work_root: str | Path,
    target: str,
    *segments: str,
) -> Path:
    """Return a validated target path below an explicit external workspace."""
    base = Path(work_root).expanduser().resolve()
    _require_external_deployment_base(base)
    target_segment = _deployment_segment(target, label="target", fallback="local")
    target_root = (base / target_segment).resolve()
    if not _is_within(target_root, base):
        raise ValueError(
            "deployment target cannot escape explicit deployment workspace: "
            f"{target_root}"
        )
    _require_external_deployment_base(target_root)
    normalized_segments = tuple(
        _deployment_segment(segment, label="path segment")
        for segment in segments
    )
    candidate = target_root.joinpath(*normalized_segments)
    return _require_target_scoped_path(candidate, target_root=target_root)


def deployment_target_path(target: str, *segments: str) -> Path:
    """Return a real path below exactly one validated deployment target."""
    return deployment_target_path_in_work_root(
        deployment_work_root(target).parent,
        target,
        *segments,
    )


def resolve_deployment_target_path(
    configured_path: str | Path | None,
    *,
    target: str,
    segments: tuple[str, ...],
) -> Path:
    """Accept only the canonical resolver-derived path for a deployment output."""
    expected = deployment_target_path(target, *segments)
    if configured_path is None or not str(configured_path).strip():
        return expected
    configured = Path(configured_path).expanduser().resolve()
    if configured != expected:
        raise ValueError(
            "deployment output must resolve to its target-scoped workspace: "
            f"expected {expected}, got {configured}"
        )
    return expected


def remove_deployment_tree(target: str, *segments: str) -> Path:
    """Remove only a resolver-derived non-symlink deployment directory."""
    if not segments:
        raise ValueError("refusing to remove a deployment target root")
    if segments[0] == "packages":
        package_root = deployment_package_root(env_for_target(target), target=target)
        path = package_root.joinpath(*segments[1:])
        _require_target_scoped_path(path, target_root=deployment_work_root(target))
    else:
        path = deployment_target_path(target, *segments)
    if path.exists():
        shutil.rmtree(path)
    return path


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


def run_evidence_dir(parent: Path, command_name: str, target: str) -> Path:
    """Return a collision-resistant directory for one immutable command run.

    A second-resolution timestamp is not a run identity: concurrent read-only
    inspections used to resolve to the same directory and could overwrite each
    other's evidence.  Keep the sortable UTC prefix, add microseconds for
    readability, and use a random run identity so independent processes never
    intentionally share an evidence directory.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_identity = uuid4().hex
    return parent / (
        f"{stamp}-{run_identity}-{safe_segment(command_name)}-"
        f"{safe_segment(target, fallback='local')}"
    )


def env_root(env_name: str) -> Path:
    return output_root() / "env" / normalize_env(env_name)


def env_runs_root(env_name: str) -> Path:
    return env_root(env_name) / "runs"


def env_run_dir(env_name: str, command_name: str, *, target: str = "local") -> Path:
    return run_evidence_dir(
        env_runs_root(normalize_env(env_name, target=target)),
        command_name,
        target,
    )


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
    """Return the real, external workspace for exactly one deployment target."""
    target_segment = _deployment_segment(target, label="target", fallback="local")
    configured = os.environ.get("QWQ_DEPLOY_WORK_ROOT", "").strip()
    base = (
        Path(configured).expanduser()
        if configured
        else DEFAULT_DEPLOY_WORK_ROOT
    )
    resolved_base = base.resolve()
    _require_external_deployment_base(resolved_base)
    target_root = (resolved_base / target_segment).resolve()
    if not _is_within(target_root, resolved_base):
        raise ValueError(
            "deployment target cannot escape QWQ_DEPLOY_WORK_ROOT via a symbolic link"
        )
    _require_external_deployment_base(target_root)
    return target_root


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
    return _deployment_segment(
        requested,
        label="target",
        fallback=DEFAULT_DEPLOY_TARGET_BY_ENV[env],
    )


def deployment_package_root(env_name: str, *, target: str = "") -> Path:
    """Return only the staging or atomically activated candidate package root."""
    target_name = deployment_target_for_env(env_name, target=target)
    override = os.environ.get(PACKAGE_ROOT_OVERRIDE_ENV, "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        _require_target_scoped_path(path, target_root=deployment_work_root(target_name))
        if path.name != "packages":
            raise ValueError("deployment package root override must end in packages")
        return path
    active = active_deployment_candidate(target_name)
    if active is None:
        # Read-only callers receive the historical location only until the first
        # atomic candidate is activated. stackctl up/verify separately reject it.
        return deployment_target_path(target_name, "packages")
    return deployment_candidate_dir(target_name, str(active["baselineId"])) / "packages"


def deployment_candidate_dir(target: str, baseline_id: str) -> Path:
    """Return the immutable full-runtime candidate for one baseline digest."""
    baseline = str(baseline_id or "").strip()
    if _BASELINE_ID.fullmatch(baseline) is None:
        raise ValueError("deployment baselineId must be sha256")
    return deployment_target_path(
        target,
        "candidates",
        "runtime-full",
        baseline.replace(":", "-"),
    )


def active_candidate_manifest_path(target: str) -> Path:
    return deployment_target_path(target, "active-runtime-candidate.json")


def active_deployment_candidate(target: str) -> dict[str, str] | None:
    """Read and validate the only activated package candidate for a target."""
    path = active_candidate_manifest_path(target)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"active deployment candidate is unreadable: {exc}") from exc
    required = {
        "schema",
        "candidateType",
        "target",
        "baselineId",
        "candidateDir",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError("active deployment candidate fields mismatch")
    baseline = str(payload.get("baselineId") or "")
    expected = deployment_candidate_dir(target, baseline)
    if (
        payload.get("schema") != ACTIVE_CANDIDATE_SCHEMA
        or payload.get("candidateType") != "runtime-full"
        or payload.get("target") != target
        or Path(str(payload.get("candidateDir") or "")).resolve() != expected
        or not (expected / "packages").is_dir()
        or not (expected / "manifest.json").is_file()
    ):
        raise ValueError("active deployment candidate identity mismatch")
    return {
        "schema": ACTIVE_CANDIDATE_SCHEMA,
        "candidateType": "runtime-full",
        "target": target,
        "baselineId": baseline,
        "candidateDir": str(expected),
    }


def activate_deployment_candidate(target: str, baseline_id: str) -> Path:
    """Atomically publish one already-complete candidate as the active input."""
    candidate = deployment_candidate_dir(target, baseline_id)
    if not (candidate / "packages").is_dir():
        raise ValueError("cannot activate a candidate without packages")
    manifest_path = candidate / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("cannot activate a candidate without manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot activate unreadable candidate manifest: {exc}") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("candidateType") != "runtime-full"
        or manifest.get("target") != target
        or manifest.get("baselineId") != baseline_id
    ):
        raise ValueError("cannot activate non-runtime or mismatched candidate")
    path = active_candidate_manifest_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": ACTIVE_CANDIDATE_SCHEMA,
        "candidateType": "runtime-full",
        "target": target,
        "baselineId": baseline_id,
        "candidateDir": str(candidate),
    }
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


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
        / "services"
        / _deployment_segment(service, label="service", fallback="service")
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


def web_deployment_package_dir(env_name: str, *, target: str = "") -> Path:
    return deployment_package_root(env_name, target=target) / "public-web"


def deployment_render_dir(
    env_name: str,
    *,
    target: str = "",
    name: str = "",
) -> Path:
    target_name = deployment_target_for_env(env_name, target=target)
    segments = ("rendered",)
    if name:
        segments += (_deployment_segment(name, label="render name"),)
    return deployment_target_path(target_name, *segments)


def certificate_export_dir(target: str) -> Path:
    """Host path for target-scoped public DNS-01 certificate material."""
    return deployment_target_path(target, "certificates")


def repo_root() -> Path:
    return output_root() / "env" / "repo"


def repo_runs_root() -> Path:
    return repo_root() / "runs"


def repo_run_dir(command_name: str, *, target: str = "repo") -> Path:
    return run_evidence_dir(repo_runs_root(), command_name, target)


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
