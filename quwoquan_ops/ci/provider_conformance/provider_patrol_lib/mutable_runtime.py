"""Provider Patrol mutable test-live 运行时：计划装载与身份校验。

可被测试 patch 的符号（target_local_dir、get_target、load_environment_topology、
compile_provider_runtime_composition、validate_provider_runtime_composition）
一律经薄入口 `_rppu` 在调用时读取。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from quwoquan_ops.ci.provider_conformance import (
    run_provider_patrol_uat as _rppu,
)
from quwoquan_ops.cli.lib.runtime_port_ownership import require_published_endpoint_port
from quwoquan_ops.ci.provider_conformance.provider_patrol_lib.runtime_identity import (
    ROOT,
    _NONPROD_ENVIRONMENTS,
    _UNKNOWN_IDENTITIES,
    ProviderPatrolRuntimeIdentity,
    _require_digest,
)

_MUTABLE_PLAN_FIELDS = frozenset({
    "schema", "environment", "target", "composeProject", "portProfile",
    "portBlock", "publishedPorts", "composeFiles", "executionComposeFiles",
    "composeProfiles", "composeDigest", "configurationDigest",
    "providerRuntimeDigest", "observabilityLogSinkDigest", "mediaLocalRef",
    "mediaRoot", "tlsProfile",
    "resolverHandoffDigest", "publicWebPackage", "workspaceIdentity",
    "graphqlReadRegistry", "serviceCoreModules",
})


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
    if plan.get("schema") != "stackctl.mutable_test_live_runtime":
        raise ValueError("mutable test-live runtime plan schema mismatch")
    receipt_fields = (
        "environment", "target", "composeProject", "portProfile", "portBlock",
        "publishedPorts", "composeDigest", "configurationDigest",
        "providerRuntimeDigest", "observabilityLogSinkDigest", "tlsProfile",
        "resolverHandoffDigest",
        "publicWebPackage",
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
    target_root = _rppu.target_local_dir(str(receipt.get("target") or "")).expanduser()
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
        receipt.get("schema") != "stackctl.mutable_test_live_startup_attempt"
        or receipt.get("launchPolicy") != "test_live"
        or receipt.get("nonPromotable") is not True
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

    target = _rppu.get_target(_rppu.load_environment_topology(), target_name)
    plan, _ = _load_mutable_runtime_plan(receipt, target_contract=target)
    composition = _rppu.validate_provider_runtime_composition(
        _rppu.compile_provider_runtime_composition(
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
    try:
        sms_port = require_published_endpoint_port(
            receipt.get("publishedPorts"),
            role="sms-provider-substitute",
            protocol="tcp",
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"mutable test-live SMS published port is invalid: {exc}"
        ) from exc

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
        elasticsearch_compose_digest=_require_digest(
            receipt.get("observabilityLogSinkDigest"),
            label="mutable Elasticsearch Compose",
        ),
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
