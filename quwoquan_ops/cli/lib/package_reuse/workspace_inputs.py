"""部署输入闭包声明与 workspace snapshot（逐字迁自原单文件）。

``ROOT`` 与 ``deployment_input_digest`` 经包属性（``_pkg.``）消费，
保持测试对包属性 monkeypatch 的既有语义。
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

import quwoquan_ops.cli.lib.package_reuse as _pkg

from .input_capsule import (
    _baseline_id,
    _digest_record,
    _enumerated_deployment_inputs,
    _normalized_input_roots,
    _path_entry,
)


def deployment_input_roots(
    env_name: str,
    target_name: str,
    service_packages: Sequence[str],
    *,
    release_attestation: str = "",
    rollback_release_attestation: str = "",
) -> list[str]:
    """Return the declared source closure actually read by runtime packaging."""

    expected_targets = (
        {"prod-sim", "prod-hosted"}
        if env_name == "prod"
        else {f"{env_name}-local"}
    )
    if target_name not in expected_targets:
        raise ValueError("deployment input closure target/environment mismatch")
    _normalized_service_packages(service_packages)
    roots = {
        # Current Dockerfiles use COPY . . from this build context. Until that
        # context is narrowed, the entire service tree is a real image input.
        "quwoquan_service",
        "quwoquan_service/.dockerignore",
        "quwoquan_service/go.mod",
        "quwoquan_service/go.sum",
        "quwoquan_service/generated/contract_graph.json",
        "quwoquan_service/contracts/metadata",
        "quwoquan_service/tools/codegen_graphql_read_registry",
        "quwoquan_service/scripts/runtime/packaging",
        "quwoquan_app/configs/default/app_runtime.yaml",
        f"quwoquan_app/configs/{env_name}/app_runtime.yaml",
        "quwoquan_app/config/schema.yaml",
        "quwoquan_app/scripts/env/build_app_env_package.sh",
        "quwoquan_app/scripts/env/print_app_env_dart_defines.py",
        "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
        "quwoquan_ops/cli/stackctl.py",
        "quwoquan_ops/cli/legal_static.py",
        "quwoquan_ops/cli/print_local_port_profile.py",
        "quwoquan_ops/cli/render_runtime_config.py",
        "quwoquan_ops/cli/lib",
        "quwoquan_ops/environments/domain_governance.yaml",
        "quwoquan_ops/environments/local_env_port_manifest.yaml",
        "quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml",
        "quwoquan_ops/environments/compose/object-storage-lifecycle.json",
        "quwoquan_ops/environments/gamma/local/Caddyfile",
        "quwoquan_ops/environments/external_provider_bindings.yaml",
        "quwoquan_ops/external/livekit/base/livekit.yaml",
        *_provider_endpoint_contract_inputs(),
        # product-ops compose 以 bind 方式挂载遥测告警策略;candidate 必须封装该文件。
        "quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml",
        *(f"quwoquan_ops/environments/{name}/runtime.yaml" for name in ("alpha", "beta", "gamma", "prod")),
    }
    for value in (release_attestation, rollback_release_attestation):
        normalized = str(value or "").strip()
        if normalized:
            roots.add(str(Path(normalized).expanduser().absolute()))
    return sorted(roots)


def deployment_input_digest(
    roots: Sequence[str],
    *,
    timeout_seconds: float | None = None,
) -> tuple[str, int]:
    """Digest tracked/untracked bytes in the declared package source closure."""

    _normalized_roots, source_entries = _enumerated_deployment_inputs(roots)
    deadline = (
        time.monotonic() + timeout_seconds
        if timeout_seconds is not None and timeout_seconds > 0
        else None
    )

    def entries() -> Iterable[tuple[str, str, bytes]]:
        for logical_path, path, _relative in source_entries:
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("deployment input currentness check timed out")
            kind, content = _path_entry(path)
            yield logical_path, kind, content

    return _digest_record(entries())


def workspace_snapshot(
    *,
    deployment_roots: Sequence[str],
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Return one identity bound only to the declared deployment closure."""

    normalized_roots = _normalized_input_roots(deployment_roots)
    repo_roots = [value for value in normalized_roots if not Path(value).is_absolute()]

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_pkg.ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    source_revision = revision.stdout.strip()
    if revision.returncode != 0 or len(source_revision) != 40:
        raise ValueError("cannot resolve workspace source revision")
    status = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--",
            *repo_roots,
        ],
        cwd=_pkg.ROOT,
        capture_output=True,
        check=False,
    )
    if status.returncode != 0:
        detail = status.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            "cannot resolve workspace index/worktree state"
            + (f": {detail}" if detail else "")
        )
    input_digest, input_count = _pkg.deployment_input_digest(
        normalized_roots,
        timeout_seconds=timeout_seconds,
    )
    status_digest = "sha256:" + hashlib.sha256(status.stdout).hexdigest()
    identity_payload = {
        "deploymentInputRoots": normalized_roots,
        "deploymentInputDigest": input_digest,
        "deploymentInputFileCount": input_count,
    }
    return {
        **identity_payload,
        "sourceRevision": source_revision,
        "workspaceStatusDigest": status_digest,
        "baselineId": _baseline_id(identity_payload),
    }


def workspace_drift_details(
    start: dict[str, object],
    end: dict[str, object],
) -> list[str]:
    """Return report-safe evidence when package inputs change mid-flight."""

    closure_fields = (
        "deploymentInputRoots",
        "deploymentInputDigest",
        "deploymentInputFileCount",
    )
    if all(start.get(field) == end.get(field) for field in closure_fields):
        return []
    return [
        "workspace changed while package was being materialized",
        f"startBaselineId={start.get('baselineId', '')}",
        f"endBaselineId={end.get('baselineId', '')}",
        f"startSourceRevision={start.get('sourceRevision', '')}",
        f"endSourceRevision={end.get('sourceRevision', '')}",
        (
            "startWorkspaceStatusDigest="
            f"{start.get('workspaceStatusDigest', '')}"
        ),
        (
            "endWorkspaceStatusDigest="
            f"{end.get('workspaceStatusDigest', '')}"
        ),
        (
            "startDeploymentInputDigest="
            f"{start.get('deploymentInputDigest', '')}"
        ),
        (
            "endDeploymentInputDigest="
            f"{end.get('deploymentInputDigest', '')}"
        ),
    ]


def _provider_endpoint_contract_inputs() -> list[str]:
    """Return the Provider endpoint contracts packaging reads from the capsule.

    ``compile_provider_runtime_composition`` resolves every endpoint workload
    from ``<source_root>/quwoquan_ops/external`` and seals each workload's
    Compose bytes into the candidate, so both files are real package inputs.
    They are derived from the workspace rather than hard-coded so a new
    workload role cannot be sealed from a capsule that never captured it.
    """

    external_root = _pkg.ROOT / "quwoquan_ops" / "external"
    inputs: list[str] = []
    for contract in sorted(external_root.glob("*/contract/endpoints.yaml")):
        inputs.append(contract.relative_to(_pkg.ROOT).as_posix())
        compose = contract.parents[1] / "deploy" / "compose.yaml"
        if compose.is_file():
            inputs.append(compose.relative_to(_pkg.ROOT).as_posix())
    if not inputs:
        raise ValueError("Provider endpoint contract closure is empty")
    return inputs


def _expected_service_packages() -> list[str]:
    service_root = _pkg.ROOT / "quwoquan_service" / "services"
    services = sorted(
        path.name for path in service_root.iterdir() if path.is_dir()
    )
    if (
        _pkg.ROOT
        / "quwoquan_service"
        / "control-plane"
        / "platform-ops"
        / "config"
        / "schema.yaml"
    ).is_file():
        services.append("platform-ops-service")
    if not services:
        raise ValueError("canonical service package set is empty")
    return sorted(services)


def _normalized_service_packages(values: Sequence[str]) -> list[str]:
    normalized = sorted(str(value).strip() for value in values)
    if (
        not normalized
        or any(not value for value in normalized)
        or len(normalized) != len(set(normalized))
    ):
        raise ValueError("service package identity set is invalid")
    return normalized
