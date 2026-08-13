"""Provider Patrol 运行时身份：不可变候选装载与 stackctl 交接选择。

可被测试 patch 的符号（deployment_candidate_dir、load_candidate_manifest、
load_startup_attempt、load_test_live_startup_attempt、
_load_nonprod_runtime_identity、_load_mutable_test_live_runtime_identity）
一律经薄入口 `_rppu` 在调用时读取，保持与拆分前单文件相同的 mock.patch 语义。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.provider_conformance import (
    run_provider_patrol_uat as _rppu,
)

ROOT = Path(__file__).resolve().parents[4]

_NONPROD_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma"})
_DIGEST_PREFIX = "sha256:"
_UNKNOWN_IDENTITIES = frozenset({"", "unknown", "none", "null", "n/a"})


_RUNTIME_IDENTITY_ENV = "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
_RUNTIME_IDENTITY_SCHEMA = "stackctl.provider_conformance_runtime_identity"
_RUNTIME_IDENTITY_COMMON_FIELDS = frozenset({
    "schema", "runtimeMode", "environment", "target", "workload",
    "startupAttemptId", "providerRuntimeDigest", "failureFree",
    "nonPromotable",
})
_RUNTIME_IDENTITY_IMMUTABLE_FIELDS = frozenset({"candidateDigest"})
_RUNTIME_IDENTITY_MUTABLE_FIELDS = frozenset({
    "mutableComposeDigest", "mutableConfigurationDigest", "mutableStateDigest",
    "mutableWorkspaceStatusDigest", "mutableResolverHandoffDigest",
    "mutableSourceRevision",
})


@dataclass(frozen=True)
class ProviderPatrolRuntimeIdentity:
    environment: str
    target: str
    public_bases: dict[str, Any]
    baseline_id: str
    source_revision: str
    package_digest: str
    image_digest: str
    runtime_config_digest: str
    environment_runtime_digest: str
    provider_runtime_digest: str
    elasticsearch_binding_digest: str
    elasticsearch_image_digest: str
    elasticsearch_compose_digest: str
    elasticsearch_cluster_ref: str
    release_id: str
    release_digest: str
    attempt_id: str
    local_capture_sms_enabled: bool
    launch_policy: str = "prod_release"
    non_promotable: bool = False
    compose_digest: str = ""
    resolver_handoff_digest: str = ""
    workspace_status_digest: str = ""
    mutable_state_digest: str = ""
    provider_binding_digest: str = ""
    provider_workloads: tuple[dict[str, Any], ...] = ()
    sms_published_port: int = 0


def _append_runtime_identity_arguments(
    command: list[str],
    identity: ProviderPatrolRuntimeIdentity,
) -> None:
    """Pass the already-verified stackctl runtime rail to Patrol explicitly."""

    if identity.launch_policy == "prod_release" and not identity.non_promotable:
        runtime_mode = "immutable_candidate"
    elif identity.launch_policy == "test_live" and identity.non_promotable:
        runtime_mode = "test_live"
    else:
        raise ValueError(
            "Provider Patrol runtime identity has an invalid launch policy boundary"
        )
    command.extend(
        (
            "--runtime-mode",
            runtime_mode,
            "--candidate-digest",
            identity.baseline_id,
        )
    )


def _sha256_bytes(value: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(value).hexdigest()


def _require_digest(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized.startswith(_DIGEST_PREFIX)
        or len(normalized) != 71
        or any(character not in "0123456789abcdef" for character in normalized[7:])
    ):
        raise ValueError(f"{label} must be a sha256 digest")
    return normalized


def _load_nonprod_runtime_identity(
    environment: str,
    target_name: str,
    *,
    candidate_digest: str | None = None,
    startup_attempt_id: str | None = None,
    provider_runtime_digest: str | None = None,
) -> ProviderPatrolRuntimeIdentity:
    explicit_values = (
        candidate_digest,
        startup_attempt_id,
        provider_runtime_digest,
    )
    if all(value is None for value in explicit_values):
        return _select_nonprod_runtime_identity(environment, target_name)
    if any(value is None for value in explicit_values):
        raise ValueError("selected immutable runtime identity is incomplete")
    assert candidate_digest is not None
    assert startup_attempt_id is not None
    assert provider_runtime_digest is not None
    if environment not in _NONPROD_ENVIRONMENTS:
        raise ValueError("package-bound Provider Patrol runtime is nonprod-only")
    if target_name != f"{environment}-local":
        raise ValueError("Provider Patrol runtime target/environment mismatch")
    baseline_id = _require_digest(
        candidate_digest,
        label="selected candidate baselineId",
    )
    selected_provider_runtime_digest = _require_digest(
        provider_runtime_digest,
        label="selected Provider runtime composition",
    )
    expected_attempt_id = str(startup_attempt_id or "").strip()
    if expected_attempt_id.lower() in _UNKNOWN_IDENTITIES:
        raise ValueError("selected startup attempt identity is required")
    candidate_root = _rppu.deployment_candidate_dir(target_name, baseline_id).resolve()
    manifest = _rppu.load_candidate_manifest(
        environment,
        target_name,
        baseline_id,
        require_full=True,
    )
    if manifest.get("baselineId") != baseline_id:
        raise ValueError("active candidate manifest baseline identity mismatch")

    runtime_path = candidate_root / "packages/app/environment_runtime.yaml"
    if not runtime_path.is_file() or runtime_path.is_symlink():
        raise ValueError("packaged environment runtime is unavailable")
    try:
        runtime_raw = runtime_path.read_bytes()
        packaged_runtime = json.loads(runtime_raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("packaged environment runtime is unreadable") from exc
    environment_runtime_digest = _sha256_bytes(runtime_raw)
    public_bases = (
        packaged_runtime.get("publicBases")
        if isinstance(packaged_runtime, dict)
        else None
    )
    if (
        not isinstance(packaged_runtime, dict)
        or packaged_runtime.get("schema") != "environment-runtime-package"
        or packaged_runtime.get("environment") != environment
        or packaged_runtime.get("target") != target_name
        or not isinstance(public_bases, dict)
        or manifest.get("environmentRuntimeDigest") != environment_runtime_digest
    ):
        raise ValueError("packaged environment runtime identity mismatch")

    provider_package = manifest.get("providerRuntime")
    composition = (
        provider_package.get("composition")
        if isinstance(provider_package, dict)
        else None
    )
    bindings = composition.get("bindings") if isinstance(composition, dict) else None
    packaged_provider_runtime_digest = _require_digest(
        composition.get("runtimeCompositionDigest")
        if isinstance(composition, dict)
        else "",
        label="Provider runtime composition",
    )
    if not isinstance(bindings, list) or not bindings:
        raise ValueError("packaged Provider runtime bindings are unavailable")
    sms_binding = next(
        (
            item
            for item in bindings
            if isinstance(item, dict)
            and item.get("capabilityId") == "identity.sms.otp"
        ),
        None,
    )
    local_capture_sms_enabled = bool(
        isinstance(sms_binding, dict)
        and sms_binding.get("state") == "enabled"
        and sms_binding.get("adapterId") == "ext.sms.local_capture"
        and sms_binding.get("endpointRef")
        == "local_topology:sms-provider-substitute"
    )

    log_sink = manifest.get("observabilityLogSink")
    if (
        not isinstance(log_sink, dict)
        or log_sink.get("adapterId") != "ext.obs.elasticsearch"
        or log_sink.get("deploymentMode") != "package-bound-local"
    ):
        raise ValueError("package-bound Elasticsearch log sink is unavailable")
    elasticsearch_compose_digest = _require_digest(
        log_sink.get("composeDigest"),
        label="Elasticsearch Compose",
    )

    startup = _rppu.load_startup_attempt(target_name)
    attempt_id = str((startup or {}).get("attemptId") or "").strip()
    if (
        not isinstance(startup, dict)
        or startup.get("status") != "running"
        or startup.get("workload") != "full"
        or startup.get("env") != environment
        or startup.get("target") != target_name
        or startup.get("candidateDigest") != baseline_id
        or startup.get("configurationDigest") != manifest.get("configurationDigest")
        or startup.get("providerRuntimeDigest") != packaged_provider_runtime_digest
        or packaged_provider_runtime_digest != selected_provider_runtime_digest
        or startup.get("observabilityLogSinkDigest")
        != elasticsearch_compose_digest
        or not str(startup.get("composeProject") or "").strip()
        or attempt_id.lower() in _UNKNOWN_IDENTITIES
        or attempt_id != expected_attempt_id
        or startup.get("failure") not in {None, ""}
        or startup.get("cleanupFailure") not in {None, ""}
    ):
        raise ValueError(
            "running full startup receipt is not bound to the active candidate, "
            "Provider composition, and Elasticsearch deployment"
        )

    release = manifest.get("release")
    candidate_release = release.get("candidate") if isinstance(release, dict) else None
    if not isinstance(candidate_release, dict):
        raise ValueError("active candidate release binding is unavailable")
    return ProviderPatrolRuntimeIdentity(
        environment=environment,
        target=target_name,
        public_bases=dict(public_bases),
        baseline_id=baseline_id,
        source_revision=str(manifest.get("sourceRevision") or "").strip(),
        package_digest=_require_digest(
            manifest.get("packageDigest"), label="candidate package"
        ),
        image_digest=_require_digest(
            manifest.get("imageDigest"), label="candidate image"
        ),
        runtime_config_digest=_require_digest(
            manifest.get("runtimeConfigDigest"), label="runtime configuration"
        ),
        environment_runtime_digest=environment_runtime_digest,
        provider_runtime_digest=packaged_provider_runtime_digest,
        elasticsearch_binding_digest=_require_digest(
            log_sink.get("bindingDigest"), label="Elasticsearch Binding"
        ),
        elasticsearch_image_digest=_require_digest(
            log_sink.get("imageDigest"), label="Elasticsearch image"
        ),
        elasticsearch_compose_digest=elasticsearch_compose_digest,
        elasticsearch_cluster_ref=str(log_sink.get("clusterRef") or "").strip(),
        release_id=str(candidate_release.get("releaseId") or "").strip(),
        release_digest=_require_digest(
            candidate_release.get("releaseDigest"), label="candidate release"
        ),
        attempt_id=attempt_id,
        local_capture_sms_enabled=local_capture_sms_enabled,
    )


def _select_nonprod_runtime_identity(
    environment: str,
    target_name: str,
) -> ProviderPatrolRuntimeIdentity:
    raw_handoff = os.environ.get(_RUNTIME_IDENTITY_ENV, "").strip()
    if not raw_handoff:
        raise ValueError("Provider Patrol runtime identity handoff is required")
    try:
        handoff = json.loads(raw_handoff)
    except json.JSONDecodeError as exc:
        raise ValueError("Provider Patrol runtime identity handoff is invalid") from exc
    if not isinstance(handoff, dict):
        raise ValueError("Provider Patrol runtime identity handoff must be an object")
    runtime_mode = str(handoff.get("runtimeMode") or "").strip()
    expected_fields = _RUNTIME_IDENTITY_COMMON_FIELDS | (
        _RUNTIME_IDENTITY_IMMUTABLE_FIELDS
        if runtime_mode == "immutable_candidate"
        else _RUNTIME_IDENTITY_MUTABLE_FIELDS
        if runtime_mode == "test_live"
        else frozenset()
    )
    if (
        not expected_fields
        or set(handoff) != expected_fields
        or handoff.get("schema") != _RUNTIME_IDENTITY_SCHEMA
        or handoff.get("environment") != environment
        or handoff.get("target") != target_name
        or handoff.get("workload") != "full"
        or handoff.get("failureFree") is not True
        or handoff.get("nonPromotable") is not (runtime_mode == "test_live")
        or str(handoff.get("startupAttemptId") or "").strip().lower()
        in _UNKNOWN_IDENTITIES
    ):
        raise ValueError("Provider Patrol runtime identity handoff does not match execution")
    selected_provider_digest = _require_digest(
        handoff.get("providerRuntimeDigest"),
        label="selected Provider runtime composition",
    )
    if runtime_mode == "immutable_candidate":
        return _rppu._load_nonprod_runtime_identity(
            environment,
            target_name,
            candidate_digest=_require_digest(
                handoff.get("candidateDigest"),
                label="selected candidate",
            ),
            startup_attempt_id=str(handoff["startupAttemptId"]),
            provider_runtime_digest=selected_provider_digest,
        )

    mutable_receipt = _rppu.load_test_live_startup_attempt(target_name)
    mutable_pairs = {
        "status": "running",
        "environment": environment,
        "target": target_name,
        "workload": "full",
        "attemptId": handoff["startupAttemptId"],
        "providerRuntimeDigest": selected_provider_digest,
        "composeDigest": handoff["mutableComposeDigest"],
        "configurationDigest": handoff["mutableConfigurationDigest"],
        "mutableStateDigest": handoff["mutableStateDigest"],
        "workspaceStatusDigest": handoff["mutableWorkspaceStatusDigest"],
        "resolverHandoffDigest": handoff["mutableResolverHandoffDigest"],
        "sourceRevision": handoff["mutableSourceRevision"],
        "failure": None,
        "cleanupFailure": None,
    }
    if (
        not isinstance(mutable_receipt, dict)
        or any(mutable_receipt.get(key) != value for key, value in mutable_pairs.items())
    ):
        raise ValueError(
            "mutable Provider Patrol runtime identity handoff does not match "
            "the canonical running receipt"
        )
    return _rppu._load_mutable_test_live_runtime_identity(
        environment,
        target_name,
        mutable_receipt,
    )
