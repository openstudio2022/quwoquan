"""Run one fixed Provider user journey against its selected environment."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.deployment_candidate_manifest import (  # noqa: E402
    load_candidate_manifest,
)
from quwoquan_ops.cli.lib.environment_topology import (  # noqa: E402
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import (  # noqa: E402
    read_latest_debug_otp,
)
from quwoquan_ops.cli.lib.local_environment_auth import (  # noqa: E402
    materialize_local_capture_ui_acceptance_phone,
)
from quwoquan_ops.cli.lib.output_paths import (  # noqa: E402
    deployment_candidate_dir,
    target_local_dir,
)
from quwoquan_ops.cli.lib.provider_runtime_composition import (  # noqa: E402
    compile_provider_runtime_composition,
    validate_provider_runtime_composition,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import (  # noqa: E402
    load_startup_attempt,
)
from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (  # noqa: E402
    load_test_live_startup_attempt,
)
from quwoquan_ops.ci.provider_conformance.protected_otp_broker import (  # noqa: E402
    ProtectedOTPBroker,
    ProtectedOTPBrokerBinding,
)


_TARGET_NAMES = {
    "alpha": ("alpha-local", "alpha-local"),
    "beta": ("beta-local", "local-beta"),
    "gamma": ("gamma-local", "local-gamma"),
    "prod": ("prod-hosted", "prod-hosted"),
}
_NONPROD_ENVIRONMENTS = frozenset({"alpha", "beta", "gamma"})
_DIGEST_PREFIX = "sha256:"
_UNKNOWN_IDENTITIES = frozenset({"", "unknown", "none", "null", "n/a"})
_SMS_CAPABILITY_ID = "identity.sms.otp"
_SMS_ASSERTION_COUNT = 12
_LOCAL_CAPTURE_UI_ACTOR_POOL_SIZE = 128
_PROTECTED_SMS_DEFINE_KEYS = frozenset({
    "QWQ_PROVIDER_UAT_SMS_PHONE",
    "QWQ_PROVIDER_UAT_SMS_OTP",
    "QWQ_PROVIDER_UAT_OTP_BROKER_URL",
    "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN",
    "QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64",
})
_MUTABLE_PLAN_FIELDS = frozenset({
    "schema", "environment", "target", "composeProject", "portProfile",
    "portBlock", "publishedPorts", "composeFiles", "executionComposeFiles",
    "composeProfiles", "composeDigest", "configurationDigest",
    "providerRuntimeDigest", "mediaLocalRef", "mediaRoot", "tlsProfile",
    "resolverHandoffDigest", "workspaceIdentity",
})
_RUNTIME_IDENTITY_ENV = "QWQ_PROVIDER_CONFORMANCE_RUNTIME_IDENTITY"
_RUNTIME_IDENTITY_SCHEMA = "stackctl.provider_conformance_runtime_identity.v1"
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
    candidate_root = deployment_candidate_dir(target_name, baseline_id).resolve()
    manifest = load_candidate_manifest(
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

    startup = load_startup_attempt(target_name)
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


def _read_regular_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        before = path.lstat()
    except OSError as exc:
        raise ValueError(f"{label} is unavailable") from exc
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} must be a regular file")
    try:
        raw = path.read_bytes()
        after = path.lstat()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(f"{label} changed while it was read")
    if not isinstance(value, dict):
        raise ValueError(f"{label} root must be an object")
    return value, raw


def _load_mutable_runtime_plan(
    receipt: dict[str, Any],
    *,
    target_contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    environment = str(receipt.get("environment") or "").strip()
    raw_run_root = Path(str(receipt.get("runRoot") or ""))
    run_root = Path(os.path.abspath(raw_run_root))
    expected_runs_root = (
        ROOT / f".qwq_output/env/{environment}/runs"
    ).resolve()
    if (
        not raw_run_root.is_absolute()
        or raw_run_root != run_root
        or not run_root.is_relative_to(expected_runs_root)
    ):
        raise ValueError("mutable test-live runtime runRoot is unsafe")
    current = expected_runs_root
    for part in run_root.relative_to(expected_runs_root).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("mutable test-live runtime runRoot contains a symlink")
    plan_path = run_root / "mutable-runtime-plan.json"
    plan, _ = _read_regular_json(plan_path, label="mutable test-live runtime plan")
    if set(plan) != _MUTABLE_PLAN_FIELDS:
        raise ValueError("mutable test-live runtime plan fields mismatch")
    if plan.get("schema") != "stackctl.mutable_test_live_runtime.v1":
        raise ValueError("mutable test-live runtime plan schema mismatch")
    receipt_fields = (
        "environment", "target", "composeProject", "portProfile", "portBlock",
        "publishedPorts", "composeDigest", "configurationDigest",
        "providerRuntimeDigest", "tlsProfile", "resolverHandoffDigest",
    )
    for field in receipt_fields:
        if plan.get(field) != receipt.get(field):
            raise ValueError(
                f"mutable test-live runtime plan/receipt drift: {field}"
            )
    workspace = plan.get("workspaceIdentity")
    if not isinstance(workspace, dict) or workspace != {
        "sourceRevision": receipt.get("sourceRevision"),
        "workspaceStatusDigest": receipt.get("workspaceStatusDigest"),
        "mutableStateDigest": receipt.get("mutableStateDigest"),
    }:
        raise ValueError("mutable test-live runtime plan/workspace drift")
    data_release = target_contract.get("dataRelease")
    raw_media_ref = data_release.get("mediaLocalRef") if isinstance(data_release, dict) else ""
    media_local_ref = str(raw_media_ref).strip()
    media_relative = Path(media_local_ref)
    if (
        not isinstance(data_release, dict)
        or data_release.get("mode") != "local-import"
        or not media_local_ref
        or media_relative.is_absolute()
        or media_relative == Path(".")
        or any(part in {"", ".", ".."} for part in media_relative.parts)
    ):
        raise ValueError("mutable test-live target mediaLocalRef is unsafe")
    if plan.get("mediaLocalRef") != media_local_ref:
        raise ValueError("mutable test-live runtime plan/topology mediaLocalRef drift")
    target_root = target_local_dir(str(receipt.get("target") or "")).expanduser()
    if not target_root.is_dir() or target_root.is_symlink():
        raise ValueError("mutable test-live target-local media root is unavailable")
    canonical_target_root = target_root.resolve()
    current = target_root
    for part in media_relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("mutable test-live mediaRoot contains a symlink")
    canonical_media_root = current.resolve()
    if not current.is_dir() or not canonical_media_root.is_relative_to(canonical_target_root):
        raise ValueError("mutable test-live mediaRoot escapes target-local root")
    try:
        expected_media_root = canonical_media_root.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        expected_media_root = canonical_media_root.as_posix()
    if plan.get("mediaRoot") != expected_media_root:
        raise ValueError("mutable test-live runtime plan mediaRoot drift")
    compose_files = plan.get("composeFiles")
    execution_files = plan.get("executionComposeFiles")
    profiles = plan.get("composeProfiles")
    if (
        not isinstance(compose_files, list)
        or not isinstance(execution_files, list)
        or len(execution_files) != len(compose_files)
        or not isinstance(profiles, list)
        or profiles != sorted(set(profiles))
    ):
        raise ValueError("mutable test-live Compose closure is invalid")
    expected_sources = {
        "quwoquan_ops/external/provider-protocol-substitute/deploy/compose.yaml",
        "quwoquan_ops/external/sms-provider-substitute/deploy/compose.yaml",
    }
    expected_profiles = {
        "nonprod-provider-protocol-substitute",
        "nonprod-sms-provider-substitute",
    }
    if (
        not expected_sources.issubset(set(compose_files))
        or not expected_profiles.issubset(set(profiles))
    ):
        raise ValueError("mutable test-live Provider/SMS Compose closure is incomplete")
    rendered_root = (run_root / "mutable-runtime/compose").resolve()
    rendered_services: dict[str, dict[str, Any]] = {}
    for raw_path in execution_files:
        relative = Path(str(raw_path or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("mutable test-live rendered Compose path is unsafe")
        rendered_path = (ROOT / relative).resolve()
        if not rendered_path.is_relative_to(rendered_root):
            raise ValueError("mutable test-live rendered Compose path escapes runRoot")
        rendered, _ = _read_regular_json(
            rendered_path,
            label="mutable test-live rendered Compose",
        )
        services = rendered.get("services")
        if services is not None and not isinstance(services, dict):
            raise ValueError("mutable test-live rendered Compose services are invalid")
        for role in ("provider-protocol-substitute", "sms-provider-substitute"):
            service = (services or {}).get(role)
            if service is None:
                continue
            if role in rendered_services or not isinstance(service, dict):
                raise ValueError(
                    f"mutable test-live rendered {role} identity is ambiguous"
                )
            rendered_services[role] = service
    if set(rendered_services) != {
        "provider-protocol-substitute",
        "sms-provider-substitute",
    }:
        raise ValueError("mutable test-live rendered Provider/SMS services are missing")
    required_environment_keys = {
        "provider-protocol-substitute": {
            "PROVIDER_SUBSTITUTE_OPERATOR_TOKEN", "QWQ_PROVIDER_RUNTIME_DIGEST",
            "PROVIDER_SUBSTITUTE_TLS_CERT_FILE", "PROVIDER_SUBSTITUTE_TLS_KEY_FILE",
        },
        "sms-provider-substitute": {
            "SMS_SUBSTITUTE_OPERATOR_TOKEN", "SMS_SUBSTITUTE_PROVIDER_TOKEN",
            "SMS_SUBSTITUTE_CAPTURE_KEY_B64", "SMS_SUBSTITUTE_TLS_CERT_FILE",
            "SMS_SUBSTITUTE_TLS_KEY_FILE",
        },
    }
    secret_placeholder_keys = {
        "provider-protocol-substitute": {"PROVIDER_SUBSTITUTE_OPERATOR_TOKEN"},
        "sms-provider-substitute": {
            "SMS_SUBSTITUTE_OPERATOR_TOKEN", "SMS_SUBSTITUTE_PROVIDER_TOKEN",
            "SMS_SUBSTITUTE_CAPTURE_KEY_B64",
        },
    }
    for role, required_keys in required_environment_keys.items():
        service = rendered_services[role]
        environment = service.get("environment")
        if (
            not isinstance(service.get("build"), dict)
            or not isinstance(environment, dict)
            or not required_keys.issubset(environment)
        ):
            raise ValueError(
                f"mutable test-live rendered {role} safety identity is incomplete"
            )
        if any(
            not str(environment[key]).startswith("${")
            or ":?" not in str(environment[key])
            for key in secret_placeholder_keys[role]
        ):
            raise ValueError(
                f"mutable test-live rendered {role} contains secret material"
            )
    return plan, rendered_services


def _load_mutable_test_live_runtime_identity(
    environment: str,
    target_name: str,
    receipt: dict[str, Any],
) -> ProviderPatrolRuntimeIdentity:
    if environment not in _NONPROD_ENVIRONMENTS:
        raise ValueError("mutable Provider Patrol runtime is nonprod-only")
    if target_name != f"{environment}-local":
        raise ValueError("Provider Patrol runtime target/environment mismatch")
    if (
        receipt.get("schema") != "stackctl.mutable_test_live_startup_attempt.v1"
        or receipt.get("launchPolicy") != "test_live"
        or receipt.get("nonPromotable") is not True
        or receipt.get("contentBindingState") != "unbound"
        or receipt.get("status") != "running"
        or receipt.get("workload") != "full"
        or receipt.get("environment") != environment
        or receipt.get("target") != target_name
        or receipt.get("failure") not in {None, ""}
    ):
        raise ValueError("mutable test-live startup receipt is not current running")
    attempt_id = str(receipt.get("attemptId") or "").strip()
    if attempt_id.lower() in _UNKNOWN_IDENTITIES:
        raise ValueError("mutable test-live startup receipt has no attempt identity")

    target = get_target(load_environment_topology(), target_name)
    plan, _ = _load_mutable_runtime_plan(receipt, target_contract=target)
    composition = validate_provider_runtime_composition(
        compile_provider_runtime_composition(
            environment=environment,
            target=target_name,
        ),
        expected_environment=environment,
        expected_target=target_name,
    )
    provider_runtime_digest = _require_digest(
        receipt.get("providerRuntimeDigest"),
        label="mutable Provider runtime composition",
    )
    if composition.get("runtimeCompositionDigest") != provider_runtime_digest:
        raise ValueError(
            "mutable test-live Provider runtime differs from rendered source"
        )
    workloads = {
        str(item.get("role") or ""): item
        for item in composition.get("workloads") or []
        if isinstance(item, dict)
    }
    if not {
        "provider-protocol-substitute",
        "sms-provider-substitute",
    }.issubset(workloads):
        raise ValueError("mutable test-live Provider/SMS workload identity is missing")
    sms_binding = next(
        (
            item
            for item in composition.get("bindings") or []
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
    if not local_capture_sms_enabled:
        raise ValueError("mutable test-live SMS local-capture Binding is unavailable")
    published_ports = receipt.get("publishedPorts")
    sms_port = (
        published_ports.get("sms-provider-substitute")
        if isinstance(published_ports, dict)
        else None
    )
    if not isinstance(sms_port, int) or isinstance(sms_port, bool):
        raise ValueError("mutable test-live SMS published port is invalid")

    public_bases = target.get("publicBases") if isinstance(target, dict) else None
    if not isinstance(public_bases, dict):
        raise ValueError(f"{target_name} publicBases are required")
    safe_workloads = tuple(
        {
            "role": role,
            "adapterIds": list(workloads[role]["adapterIds"]),
            "capabilityIds": list(workloads[role]["capabilityIds"]),
            "contractDigest": _require_digest(
                workloads[role].get("contractDigest"),
                label=f"{role} endpoint contract",
            ),
            "composeDigest": _require_digest(
                workloads[role].get("composeDigest"),
                label=f"{role} Compose",
            ),
        }
        for role in sorted(workloads)
        if role in {"provider-protocol-substitute", "sms-provider-substitute"}
    )
    return ProviderPatrolRuntimeIdentity(
        environment=environment,
        target=target_name,
        public_bases=dict(public_bases),
        baseline_id=_require_digest(
            receipt.get("composeDigest"),
            label="mutable test-live Compose",
        ),
        source_revision=str(receipt.get("sourceRevision") or "").strip(),
        package_digest="",
        image_digest="",
        runtime_config_digest=_require_digest(
            receipt.get("configurationDigest"),
            label="mutable runtime configuration",
        ),
        environment_runtime_digest="",
        provider_runtime_digest=provider_runtime_digest,
        elasticsearch_binding_digest="",
        elasticsearch_image_digest="",
        elasticsearch_compose_digest="",
        elasticsearch_cluster_ref="",
        release_id="",
        release_digest="",
        attempt_id=attempt_id,
        local_capture_sms_enabled=True,
        launch_policy="test_live",
        non_promotable=True,
        compose_digest=str(plan["composeDigest"]),
        resolver_handoff_digest=_require_digest(
            receipt.get("resolverHandoffDigest"),
            label="mutable resolver handoff",
        ),
        workspace_status_digest=_require_digest(
            receipt.get("workspaceStatusDigest"),
            label="mutable workspace status",
        ),
        mutable_state_digest=_require_digest(
            receipt.get("mutableStateDigest"),
            label="mutable workspace state",
        ),
        provider_binding_digest=_require_digest(
            composition.get("bindingDigest"),
            label="mutable Provider Binding",
        ),
        provider_workloads=safe_workloads,
        sms_published_port=sms_port,
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
        return _load_nonprod_runtime_identity(
            environment,
            target_name,
            candidate_digest=_require_digest(
                handoff.get("candidateDigest"),
                label="selected candidate",
            ),
            startup_attempt_id=str(handoff["startupAttemptId"]),
            provider_runtime_digest=selected_provider_digest,
        )

    mutable_receipt = load_test_live_startup_attempt(target_name)
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
    return _load_mutable_test_live_runtime_identity(
        environment,
        target_name,
        mutable_receipt,
    )


def _validated_broker_port(binding: ProtectedOTPBrokerBinding) -> int:
    parsed = urlparse(binding.url)
    try:
        port = int(parsed.port or 0)
    except ValueError as exc:
        raise ValueError("protected OTP broker URL has an invalid port") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/v1/otp"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or port <= 0
    ):
        raise ValueError("protected OTP broker must use the exact HTTPS loopback URL")
    _require_digest(binding.ca_digest, label="protected OTP broker CA")
    _require_digest(
        binding.certificate_digest,
        label="protected OTP broker certificate",
    )
    try:
        ca_bytes = base64.b64decode(
            binding.ca_certificate_base64,
            validate=True,
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("protected OTP broker CA certificate is invalid") from exc
    if _sha256_bytes(ca_bytes) != binding.ca_digest:
        raise ValueError("protected OTP broker CA certificate digest mismatch")
    return port


def _runtime_evidence(
    identity: ProviderPatrolRuntimeIdentity,
    binding: ProtectedOTPBrokerBinding | None,
) -> dict[str, Any]:
    if identity.launch_policy == "test_live":
        evidence: dict[str, Any] = {
            "environment": identity.environment,
            "target": identity.target,
            "launchPolicy": "test_live",
            "nonPromotable": True,
            "sourceRevision": identity.source_revision,
            "composeDigest": identity.compose_digest,
            "configurationDigest": identity.runtime_config_digest,
            "resolverHandoffDigest": identity.resolver_handoff_digest,
            "workspaceStatusDigest": identity.workspace_status_digest,
            "mutableStateDigest": identity.mutable_state_digest,
            "providerRuntime": {
                "bindingDigest": identity.provider_binding_digest,
                "runtimeCompositionDigest": identity.provider_runtime_digest,
                "workloads": list(identity.provider_workloads),
            },
            "smsProvider": {
                "adapterId": "ext.sms.local_capture",
                "endpointRef": "local_topology:sms-provider-substitute",
                "publishedPort": identity.sms_published_port,
            },
            "startup": {"workload": "full", "attemptId": identity.attempt_id},
        }
    else:
        evidence = {
            "environment": identity.environment,
            "target": identity.target,
            "baselineId": identity.baseline_id,
            "sourceRevision": identity.source_revision,
            "packageDigest": identity.package_digest,
            "imageDigest": identity.image_digest,
            "runtimeConfigDigest": identity.runtime_config_digest,
            "environmentRuntimeDigest": identity.environment_runtime_digest,
            "providerRuntimeDigest": identity.provider_runtime_digest,
            "elasticsearch": {
                "adapterId": "ext.obs.elasticsearch",
                "bindingDigest": identity.elasticsearch_binding_digest,
                "imageDigest": identity.elasticsearch_image_digest,
                "composeDigest": identity.elasticsearch_compose_digest,
                "clusterRef": identity.elasticsearch_cluster_ref,
            },
            "release": {
                "releaseId": identity.release_id,
                "releaseDigest": identity.release_digest,
            },
            "startup": {"workload": "full", "attemptId": identity.attempt_id},
        }
    if binding is not None:
        evidence["protectedOtpBrokerTls"] = {
            "scheme": "https",
            "minimumTlsVersion": "TLSv1.3",
            "caDigest": binding.ca_digest,
            "certificateDigest": binding.certificate_digest,
        }
    return evidence


def _declared_provider_assertion_ids() -> tuple[str, ...]:
    raw = _required_environment("QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS must be a JSON list"
        ) from exc
    if (
        not isinstance(payload, list)
        or not payload
        or any(
            not isinstance(item, str)
            or not item
            or item != item.strip()
            or not item.startswith("provider.")
            for item in payload
        )
        or len(set(payload)) != len(payload)
    ):
        raise ValueError(
            "Provider Patrol assertion IDs must be a unique provider.* string list"
        )
    capability_id = _required_environment(
        "QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID"
    )
    if capability_id == _SMS_CAPABILITY_ID and len(payload) != _SMS_ASSERTION_COUNT:
        raise ValueError(
            "identity.sms.otp Provider Patrol requires exactly 12 source assertions"
        )
    return tuple(payload)


def _validated_test_execution(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "framework",
        "executed",
        "failed",
        "skipped",
    }:
        raise ValueError(f"{label} testExecution shape is invalid")
    executed = value.get("executed")
    failed = value.get("failed")
    skipped = value.get("skipped")
    if (
        value.get("framework") not in {"patrol", "xctest"}
        or isinstance(executed, bool)
        or not isinstance(executed, int)
        or executed <= 0
        or isinstance(failed, bool)
        or not isinstance(failed, int)
        or failed != 0
        or isinstance(skipped, bool)
        or not isinstance(skipped, int)
        or skipped != 0
    ):
        raise ValueError(
            f"{label} must bind non-zero executed tests with zero failures/skips"
        )
    return dict(value)


def _safe_patrol_log(
    report: dict[str, Any],
    *,
    run_evidence: dict[str, Any],
    case_evidence: dict[str, Any],
) -> tuple[str, bytes]:
    raw_evidence_root = str(report.get("evidenceRoot") or "").strip()
    raw_run_directory = str(run_evidence.get("runDirectory") or "").strip()
    raw_log_ref = str(run_evidence.get("rawLogPath") or "").strip()
    if case_evidence.get("patrolLogPath") != raw_log_ref:
        raise ValueError("Provider Patrol case/run log evidence is inconsistent")
    relative_values = tuple(
        Path(value)
        for value in (raw_evidence_root, raw_run_directory, raw_log_ref)
    )
    if any(
        not str(value)
        or value.is_absolute()
        or value == Path(".")
        or any(part in {"", ".", ".."} for part in value.parts)
        for value in relative_values
    ):
        raise ValueError("Provider Patrol evidence paths are unsafe")
    evidence_root = (ROOT / relative_values[0]).resolve()
    run_directory = (ROOT / relative_values[1]).resolve()
    log_path = (ROOT / relative_values[2]).resolve()
    if (
        not evidence_root.is_relative_to(ROOT.resolve())
        or not run_directory.is_relative_to(evidence_root)
        or log_path != run_directory / "patrol.log"
    ):
        raise ValueError("Provider Patrol log does not belong to its run evidence")
    current = ROOT
    for part in relative_values[2].parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Provider Patrol log path contains a symlink")
    try:
        before = log_path.lstat()
        raw = log_path.read_bytes()
        after = log_path.lstat()
    except OSError as exc:
        raise ValueError("Provider Patrol log evidence is unavailable") from exc
    if (
        not log_path.is_file()
        or log_path.is_symlink()
        or not raw
        or before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError("Provider Patrol log evidence is not a stable regular file")
    return raw_log_ref, raw


def _patrol_assertion_evidence(
    report: dict[str, Any],
    *,
    assertion_ids: tuple[str, ...],
    sensitive_values: tuple[str, ...],
) -> list[dict[str, Any]]:
    if (
        not assertion_ids
        or len(set(assertion_ids)) != len(assertion_ids)
        or any(
            not assertion_id
            or assertion_id != assertion_id.strip()
            or not assertion_id.startswith("provider.")
            for assertion_id in assertion_ids
        )
    ):
        raise ValueError("Provider Patrol source assertions are invalid")
    if report.get("status") != "passed" or "assertions" in report:
        raise ValueError(
            "Provider Patrol assertions require a fresh passed source report"
        )
    runs = report.get("runs")
    cases = report.get("caseResults")
    if (
        not isinstance(runs, list)
        or not runs
        or not isinstance(cases, list)
        or len(cases) != len(runs)
    ):
        raise ValueError(
            "Provider Patrol assertions require one real case for every device run"
        )
    normalized_sensitive_values = _sensitive_representations(sensitive_values)
    cases_by_device: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Provider Patrol run/case evidence must be objects")
        device_id = str(case.get("deviceId") or "").strip()
        if (
            device_id.lower() in _UNKNOWN_IDENTITIES
            or device_id in cases_by_device
        ):
            raise ValueError("Provider Patrol run/case identity is invalid")
        cases_by_device[device_id] = case

    matrix: list[dict[str, str]] = []
    for run in runs:
        if not isinstance(run, dict):
            raise ValueError("Provider Patrol run/case evidence must be objects")
        device = run.get("device")
        run_evidence = run.get("evidence")
        if not isinstance(device, dict) or not isinstance(run_evidence, dict):
            raise ValueError("Provider Patrol run/case evidence must be objects")
        device_id = str(device.get("id") or "").strip()
        case = cases_by_device.pop(device_id, None)
        case_evidence = case.get("evidence") if isinstance(case, dict) else None
        case_id = str((case or {}).get("caseId") or "").strip()
        if (
            device_id.lower() in _UNKNOWN_IDENTITIES
            or case_id.lower() in _UNKNOWN_IDENTITIES
            or not isinstance(case_evidence, dict)
            or run.get("exitCode") != 0
            or run.get("timedOut") is not False
            or (case or {}).get("status") != "passed"
        ):
            raise ValueError("Provider Patrol run/case is not a passed real execution")
        run_execution = _validated_test_execution(
            run.get("testExecution"),
            label=f"Provider Patrol run {device_id}",
        )
        case_execution = _validated_test_execution(
            (case or {}).get("testExecution"),
            label=f"Provider Patrol case {device_id}",
        )
        if run_execution != case_execution:
            raise ValueError("Provider Patrol run/case testExecution is inconsistent")
        raw_log_ref, log_raw = _safe_patrol_log(
            report,
            run_evidence=run_evidence,
            case_evidence=case_evidence,
        )
        if any(
            value in log_raw
            for value in normalized_sensitive_values
        ):
            raise ValueError("Provider Patrol log exposed a protected UAT value")
        execution_digest = _sha256_bytes(
            json.dumps(
                run_execution,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        matrix.append(
            {
                "caseId": case_id,
                "deviceId": device_id,
                "targetPlatform": str(device.get("targetPlatform") or ""),
                "logDigest": _sha256_bytes(log_raw),
                "logRef": raw_log_ref,
                "testExecutionDigest": execution_digest,
            }
        )
    if cases_by_device:
        raise ValueError("Provider Patrol case/run device matrix is inconsistent")
    matrix.sort(key=lambda item: (item["targetPlatform"], item["deviceId"]))
    matrix_digest = _sha256_bytes(
        json.dumps(
            matrix,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    execution_digest = _sha256_bytes(
        "\n".join(item["testExecutionDigest"] for item in matrix).encode("utf-8")
    )
    anchor_case_id = matrix[0]["caseId"]
    assertions: list[dict[str, Any]] = []
    for assertion_id in assertion_ids:
        assertion_digest = _sha256_bytes(
            f"{matrix_digest}\n{assertion_id}".encode("utf-8")
        )
        assertions.append(
            {
                "assertionId": assertion_id,
                "caseId": anchor_case_id,
                "status": "passed",
                "logRef": f"log:patrol-matrix:{matrix_digest}",
                "traceRef": (
                    f"trace:patrol-matrix:{matrix_digest}:{assertion_digest}"
                ),
                "metricRefs": [
                    "metric:patrol-matrix-test-execution:"
                    f"{execution_digest}:{assertion_digest}"
                ],
            }
        )
    return assertions


def _sensitive_representations(
    sensitive_values: tuple[str, ...],
) -> tuple[bytes, ...]:
    representations: list[bytes] = []
    for value in dict.fromkeys(item for item in sensitive_values if item):
        raw = value.encode("utf-8")
        standard = base64.b64encode(raw)
        urlsafe = base64.urlsafe_b64encode(raw)
        representations.extend(
            (raw, standard, standard.rstrip(b"="), urlsafe, urlsafe.rstrip(b"="))
        )
    return tuple(dict.fromkeys(item for item in representations if item))


def _bind_runtime_evidence_to_patrol_report(
    report_path: Path,
    *,
    identity: ProviderPatrolRuntimeIdentity,
    binding: ProtectedOTPBrokerBinding | None,
    assertion_ids: tuple[str, ...] = (),
    sensitive_values: tuple[str, ...] = (),
) -> None:
    if not report_path.is_file() or report_path.is_symlink():
        raise ValueError("Provider Patrol did not produce a safe report")
    try:
        report_raw = report_path.read_bytes()
        report = json.loads(report_raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Provider Patrol report is unreadable") from exc
    if not isinstance(report, dict):
        raise ValueError("Provider Patrol report root must be an object")
    if (
        report.get("suiteId") != "environment_page_smoke"
        or report.get("runtimeEnv") != identity.environment
        or report.get("apiContractEnv") != identity.environment
        or report.get("candidateDigest") != identity.baseline_id
        or "runtimeIdentityEvidence" in report
    ):
        raise ValueError("Provider Patrol report runtime identity mismatch")
    if binding is not None and binding.token.encode("utf-8") in report_raw:
        raise ValueError("Provider Patrol report exposed the protected broker token")
    if any(
        value in report_raw
        for value in _sensitive_representations(sensitive_values)
    ):
        raise ValueError("Provider Patrol report exposed a protected UAT value")
    if assertion_ids:
        report["assertions"] = _patrol_assertion_evidence(
            report,
            assertion_ids=assertion_ids,
            sensitive_values=sensitive_values,
        )
    report["runtimeIdentityEvidence"] = _runtime_evidence(identity, binding)
    rendered = (
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    if binding is not None and binding.token.encode("utf-8") in rendered:
        raise ValueError("Provider Patrol TLS evidence exposed the broker token")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{report_path.name}.",
        suffix=".tmp",
        dir=report_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, report_path.stat().st_mode & 0o777)
        temporary.replace(report_path)
    finally:
        temporary.unlink(missing_ok=True)


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _required_url(public_bases: dict[str, Any], name: str) -> str:
    value = str(public_bases.get(name) or "").strip()
    if not value:
        raise ValueError(f"environment topology publicBases.{name} is required")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument(
        "--platform",
        choices=("android", "ios", "all"),
        default="android",
    )
    parser.add_argument("--unauthenticated", action="store_true")
    parser.add_argument("--define-key", action="append", default=[])
    parser.add_argument("--local-capture-otp-broker", action="store_true")
    return parser.parse_args()


def _configure_android_broker_reverse(
    *,
    action: str,
    device_id: str,
    port: int,
) -> None:
    if not device_id:
        raise ValueError(
            "local-capture Android OTP UAT requires "
            "QWQ_PROVIDER_CONFORMANCE_DEVICE_ID"
        )
    endpoint = f"tcp:{port}"
    command = ["adb", "-s", device_id, "reverse"]
    if action == "add":
        command.extend((endpoint, endpoint))
    elif action == "remove":
        command.extend(("--remove", endpoint))
    else:
        raise ValueError("unsupported Android broker reverse action")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and action == "add":
        raise RuntimeError("failed to install protected OTP broker port reverse")


def _android_broker_device_ids(
    *,
    platform: str,
    explicit_device_id: str,
) -> tuple[str, ...]:
    if platform not in {"android", "all"}:
        return ()
    if explicit_device_id:
        return (explicit_device_id,)
    completed = subprocess.run(
        ["adb", "devices"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("failed to discover Android OTP broker devices")
    device_ids = tuple(
        fields[0]
        for line in completed.stdout.splitlines()[1:]
        for fields in (line.split(),)
        if len(fields) >= 2 and fields[1] == "device"
    )
    if not device_ids:
        raise RuntimeError("local-capture OTP UAT requires an Android device")
    return device_ids


def _local_capture_phone_values(raw_value: str) -> tuple[str, str]:
    """Return App-local digits and the Provider's canonical E.164 recipient."""

    normalized = raw_value.strip()
    local_digits = normalized[3:] if normalized.startswith("+86") else normalized
    if (
        len(local_digits) != 11
        or not local_digits.isascii()
        or not local_digits.isdigit()
        or not local_digits.startswith("1")
    ):
        raise ValueError(
            "local-capture OTP UAT requires an 11-digit +86 phone identity"
        )
    return local_digits, f"+86{local_digits}"


def _local_capture_ui_actor_index(report_path: Path) -> int:
    """Select one protected UAT identity without persisting a second cursor."""

    digest = hashlib.sha256(str(report_path.resolve()).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % _LOCAL_CAPTURE_UI_ACTOR_POOL_SIZE


def main() -> int:
    args = _parse_args()
    environment = _required_environment(
        "QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT"
    )
    try:
        target_name, environment_alias = _TARGET_NAMES[environment]
    except KeyError as exc:
        raise ValueError(
            f"unsupported Provider Patrol environment: {environment}"
        ) from exc
    runtime_identity: ProviderPatrolRuntimeIdentity | None = None
    assertion_ids: tuple[str, ...] = ()
    if environment in _NONPROD_ENVIRONMENTS:
        runtime_identity = _select_nonprod_runtime_identity(
            environment,
            target_name,
        )
        assertion_ids = _declared_provider_assertion_ids()
        public_bases = runtime_identity.public_bases
    else:
        target = get_target(load_environment_topology(), target_name)
        public_bases = target.get("publicBases")
    if not isinstance(public_bases, dict):
        raise ValueError(f"{target_name} publicBases are required")

    result_path = Path(
        _required_environment("QWQ_PROVIDER_CONFORMANCE_RESULT_PATH")
    )
    report_path = result_path.with_name(f"{result_path.stem}.patrol-report.json")
    command = [
        sys.executable,
        "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
        "--env-name",
        environment_alias,
        "--runtime-env",
        environment,
        "--api-contract-env",
        environment,
        "--gateway-base-url",
        _required_url(public_bases, "api"),
        "--product-ops-base-url",
        _required_url(public_bases, "productOps"),
        "--media-avatar-base-url",
        _required_url(public_bases, "mediaAvatar"),
        "--media-image-base-url",
        _required_url(public_bases, "mediaImage"),
        "--media-video-base-url",
        _required_url(public_bases, "mediaVideo"),
        "--media-upload-base-url",
        _required_url(public_bases, "mediaUpload"),
        "--rtc-media-connection-url",
        _required_url(public_bases, "rtc"),
        "--target",
        args.target,
        "--platform",
        args.platform,
        "--report",
        str(report_path),
    ]
    if runtime_identity is not None:
        _append_runtime_identity_arguments(command, runtime_identity)
    device_id = os.environ.get(
        "QWQ_PROVIDER_CONFORMANCE_DEVICE_ID", ""
    ).strip()
    if device_id:
        command.extend(("--device-id", device_id))
    command_environment = dict(os.environ)
    local_capture_recipient = ""
    local_capture_sensitive_values: tuple[str, ...] = ()
    if args.local_capture_otp_broker:
        raw_phone = command_environment.get(
            "QWQ_PROVIDER_UAT_SMS_PHONE", ""
        ).strip()
        if not raw_phone:
            raw_phone = materialize_local_capture_ui_acceptance_phone(
                environment=environment,
                target_name=target_name,
                actor_index=_local_capture_ui_actor_index(report_path),
            )
        app_phone, local_capture_recipient = _local_capture_phone_values(
            raw_phone
        )
        command_environment["QWQ_PROVIDER_UAT_SMS_PHONE"] = app_phone
        local_capture_sensitive_values = (
            app_phone,
            local_capture_recipient,
        )
    define_keys = tuple(
        str(key).strip() for key in args.define_key if str(key).strip()
    )
    if args.local_capture_otp_broker:
        define_keys += (
            "QWQ_PROVIDER_UAT_OTP_BROKER_URL",
            "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN",
            "QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64",
        )
    invalid_define_keys = [
        key
        for key in define_keys
        if not key.startswith("QWQ_PROVIDER_UAT_")
    ]
    if invalid_define_keys:
        raise ValueError("Provider Patrol define keys must use QWQ_PROVIDER_UAT_*")
    generated_define_keys = {
        "QWQ_PROVIDER_UAT_OTP_BROKER_URL",
        "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN",
        "QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64",
    } if args.local_capture_otp_broker else set()
    missing_define_keys = [
        key
        for key in define_keys
        if key not in generated_define_keys
        and not command_environment.get(key, "").strip()
    ]
    if missing_define_keys:
        raise ValueError(
            "Provider Patrol define values are required: "
            + ", ".join(missing_define_keys)
        )
    if define_keys:
        command_environment["QWQ_PROVIDER_UAT_DART_DEFINE_KEYS"] = ",".join(
            define_keys
        )
    if args.unauthenticated:
        command.append("--unauthenticated-auth-entry")
        for key in (
            "TEST_AUTH_TOKEN",
            "TEST_REFRESH_TOKEN",
            "APP_CURRENT_OWNER_ID",
            "APP_CURRENT_PERSONA_ID",
        ):
            command_environment.pop(key, None)
    broker: ProtectedOTPBroker | None = None
    broker_binding: ProtectedOTPBrokerBinding | None = None
    broker_port = 0
    broker_reverse_device_ids: list[str] = []
    try:
        if args.local_capture_otp_broker:
            if environment not in {"alpha", "beta", "gamma"}:
                raise ValueError(
                    "local-capture OTP broker is forbidden for Prod evidence"
                )
            if command_environment.get("QWQ_PROVIDER_UAT_SMS_OTP", "").strip():
                raise ValueError(
                    "local-capture OTP UAT must not preload an OTP"
                )
            if (
                runtime_identity is None
                or not runtime_identity.local_capture_sms_enabled
            ):
                raise ValueError(
                    "active candidate does not select the SMS local-capture "
                    "Provider composition"
                )
            broker = ProtectedOTPBroker(
                environment=environment,
                target_name=target_name,
                recipient=local_capture_recipient,
                reader=read_latest_debug_otp,
                max_consumptions=2 if args.platform == "all" else 1,
            )
            broker_binding = broker.start()
            command_environment[
                "QWQ_PROVIDER_UAT_OTP_BROKER_URL"
            ] = broker_binding.url
            command_environment[
                "QWQ_PROVIDER_UAT_OTP_BROKER_TOKEN"
            ] = broker_binding.token
            command_environment[
                "QWQ_PROVIDER_UAT_OTP_BROKER_CA_B64"
            ] = broker_binding.ca_certificate_base64
            broker_port = _validated_broker_port(broker_binding)
            for android_device_id in _android_broker_device_ids(
                platform=args.platform,
                explicit_device_id=device_id,
            ):
                _configure_android_broker_reverse(
                    action="add",
                    device_id=android_device_id,
                    port=broker_port,
                )
                broker_reverse_device_ids.append(android_device_id)
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=command_environment,
            check=False,
        )
        if runtime_identity is not None:
            try:
                _bind_runtime_evidence_to_patrol_report(
                    report_path,
                    identity=runtime_identity,
                    binding=broker_binding,
                    assertion_ids=assertion_ids,
                    sensitive_values=tuple(
                        dict.fromkeys(
                            (
                                *local_capture_sensitive_values,
                                *(
                                    command_environment.get(key, "").strip()
                                    for key in define_keys
                                    if key in _PROTECTED_SMS_DEFINE_KEYS
                                    if command_environment.get(key, "").strip()
                                ),
                                *(
                                    f"{key}={command_environment.get(key, '').strip()}"
                                    for key in define_keys
                                    if key in _PROTECTED_SMS_DEFINE_KEYS
                                    if command_environment.get(key, "").strip()
                                ),
                            )
                        )
                    ),
                )
            except (OSError, ValueError) as exc:
                print(f"GATE_BLOCK: {exc}", file=sys.stderr)
                return 2
        return completed.returncode
    finally:
        for android_device_id in broker_reverse_device_ids:
            _configure_android_broker_reverse(
                action="remove",
                device_id=android_device_id,
                port=broker_port,
            )
        if broker is not None:
            broker.close()


if __name__ == "__main__":
    raise SystemExit(main())
