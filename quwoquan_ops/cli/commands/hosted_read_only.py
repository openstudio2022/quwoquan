"""Explicit prod-hosted read-only orchestration and mutation rejection."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from pathlib import Path
from collections.abc import Mapping
from typing import Any

PROFILE = "hosted-read-only"
ALLOWED_CHECKS = ("status", "health", "verify", "inspect")
PROHIBITED_ACTIONS = (
    "up",
    "deploy",
    "repair",
    "rollout",
    "rollback",
    "restart",
    "device-patrol",
    "local-app",
    "actor-mutation",
)


def register_identity_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--deployment-instance", choices=("prevalidate", "gray", "prod"), default="prod")
    parser.add_argument("--ssh-host", default="", help="SSH management host; never a public base")
    parser.add_argument("--host-id", default="")
    parser.add_argument("--candidate-digest", default="")


def identity_arguments(args: argparse.Namespace) -> dict[str, str]:
    return {
        name: str(getattr(args, name, default) or "").strip()
        for name, default in (
            ("deployment_instance", "prod"), ("ssh_host", ""),
            ("host_id", ""), ("candidate_digest", ""),
        )
    }


def _hosted_candidate(candidate_digest: str, instance: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """验证封存字节而非当前本地 startup pointer；不授予正式 authority。"""
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib.deployment_candidate_manifest import prod_hosted_rehearsal as rehearsal

    if re.fullmatch(r"sha256:[0-9a-f]{64}", candidate_digest) is None:
        raise ValueError("hosted identity requires an explicit exact --candidate-digest")
    candidate = _stackctl.load_candidate_manifest(
        "prod", "prod-hosted", candidate_digest, require_full=True, purpose="self_verify",
    )
    if candidate.get("baselineId") != candidate_digest:
        raise ValueError("hosted candidate identity drift")
    root = _stackctl.deployment_candidate_dir("prod-hosted", candidate_digest)
    oci = json.loads((root / "packages/runtime-shared/oci-images.json").read_text(encoding="utf-8"))
    if not isinstance(oci, dict):
        raise ValueError("hosted OCI manifest must be an object")
    if rehearsal.is_rehearsal_oci_manifest(oci):
        if instance != "prevalidate":
            raise ValueError("local-build rehearsal requires deployment instance prevalidate")
        rehearsal.validate_rehearsal_oci_manifest(oci)
        source_revision = str(candidate.get("sourceRevision") or "")
        if re.fullmatch(r"[0-9a-f]{40}", source_revision) is None:
            raise ValueError("rehearsal source identity is missing")
        # 诊断已部署封存候选不要求当前工作树干净，但它仍必须来自本地 dev1.0 历史。
        ancestry = _stackctl.run(["git", "merge-base", "--is-ancestor", source_revision, rehearsal.DEV_REF])
        if ancestry.returncode != 0:
            raise ValueError("rehearsal candidate source is not reachable from dev1.0")
    return candidate, oci


def _hosted_material_readback(placement: Any) -> dict[str, Any]:
    """经既有 SSH 凭据解析器读实际配置摘要；不执行渲染、容器 exec 或远端写入。"""
    import os
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.prod.inspect_prod_plane_runtime import DEFAULT_KEY_DIR, _resolve_key_source

    key_dir = Path(os.environ.get("PROD_SSH_KEY_DIR", "") or DEFAULT_KEY_DIR).expanduser()
    try:
        key_args, _ = _resolve_key_source(placement.ssh_key_secret, placement.account, key_dir)
    except SystemExit as error:
        raise ValueError("hosted material SSH credential is unavailable") from error
    script = "\n".join([
        "import hashlib, json, pathlib, sys",
        "root = pathlib.Path(sys.argv[1])",
        "provenance = json.loads((root / 'provenance.json').read_text())",
        "identity = json.loads((root / 'runtime/artifact-identity.json').read_text())",
        "configs = {}",
        "for service, source in provenance.get('configSources', {}).items():",
        "    if not isinstance(source, dict) or not source.get('configurationDigest'): continue",
        "    path = root / 'runtime/config-root' / (service + '.yaml')",
        "    projection = source.get('prevalidationProjection') or {}",
        "    configs[service] = {'version': source['configurationDigest'], 'digest': 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest(), 'expectedDigest': projection.get('projectedConfigDigest') or source.get('effectiveConfigDigest')}",
        "print(json.dumps({'candidateDigest': provenance.get('candidateDigest'), 'instance': provenance.get('instance'), 'plane': provenance.get('plane'), 'dataMode': provenance.get('dataMode'), 'artifactIdentity': identity, 'configs': configs}))",
    ])
    remote = shlex.join(["python3", "-c", script, placement.remote_root])
    result = _stackctl.run([
        "ssh", *key_args, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=10", f"{placement.account}@{placement.ssh_host}", remote,
    ], timeout_seconds=30)
    if result.returncode != 0:
        raise ValueError("hosted material readback failed")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise ValueError("hosted material readback is not an object")
    return payload


def _hosted_container_state(
    item: Mapping[str, Any], *, service: str, provider_bound: set[str],
) -> tuple[str, str, bool]:
    """与 executor._runtime_blockers 同义：例外只限已配置的 Provider 深探针。"""
    if item.get("oomKilled") is True:
        return "CONTAINER_OOM", "", False
    if service in {"mongo-init", "object-storage-init"}:
        completed = (
            not item.get("error") and item.get("status") == "exited"
            and item.get("running") is False
            and type(item.get("exitCode")) is int and item["exitCode"] == 0
        )
        return ("" if completed else "INITIALIZATION_NOT_COMPLETED"), "", completed
    if item.get("error"):
        return "CONTAINER_START_FAILED", "", False
    if item.get("running") is not True:
        return "CONTAINER_NOT_RUNNING", "", False
    health = item.get("health")
    if health in {None, "", "not-configured"}:
        return "", "HEALTHCHECK_NOT_CONFIGURED", False
    healthy = health == "healthy" or (
        service in provider_bound and health in {"starting", "unhealthy"}
    )
    return "", ("" if healthy else "CONTAINER_UNHEALTHY"), False


def _hosted_runtime_checks(
    runtime: Mapping[str, Any], placement: Any, *, required: tuple[str, ...],
    oci: Mapping[str, Any], candidate_digest: str, provider_bound: set[str],
    material: Mapping[str, Any], support: tuple[str, ...] = (),
    support_images: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """只投影安全身份字段；原始 inspect 环境变量可能含密钥，不复制到聚合报告。"""
    from quwoquan_ops.cli.lib.deployment_candidate_manifest.prod_hosted_rehearsal import compose_service_image_owner
    from quwoquan_ops.cli.prod.load_prod_plane_images import normalize_image_id

    identity_issues: list[str] = []
    container_issues: list[str] = []
    first_party_issues: list[str] = []
    expected = {
        "instance": placement.instance, "plane": placement.plane,
        "hostId": placement.host_id, "host": placement.ssh_host,
        "replicaId": placement.replica_id, "project": placement.project,
        "account": placement.account, "composeRoot": placement.remote_root,
    }
    prefix = f"{placement.host_id}/{placement.plane}/{placement.replica_id}"
    for key, value in expected.items():
        if not value or runtime.get(key) != value:
            identity_issues.append(f"{prefix}: hosted {key} missing or drifted")
    artifact = material.get("artifactIdentity") or {}
    if (
        material.get("candidateDigest") != candidate_digest
        or material.get("instance") != placement.instance
        or material.get("plane") != placement.plane
        or artifact.get("schema") != "qwq.environment-artifact-identity"
        or artifact.get("environment") != "prod"
        or artifact.get("configDigest") != candidate_digest
    ):
        identity_issues.append(f"{prefix}: hosted material candidate identity missing or drifted")
    unit = runtime.get("unit") or {}
    if unit.get("name") != placement.systemd_unit:
        identity_issues.append(f"{prefix}: hosted systemd unit identity drifted")
    if runtime.get("error") or runtime.get("exitCode"):
        identity_issues.append(f"{prefix}: hosted runtime readback failed")
    if not runtime.get("composeFileExists") or not runtime.get("envFileExists"):
        container_issues.append(f"{prefix}: runtime compose/env file missing")
    if unit.get("enabled") is not True or unit.get("active") is not True:
        container_issues.append(f"{prefix}: systemd unit is not enabled and active")
    containers = runtime.get("containers") or []
    by_service = {str(item.get("composeService") or ""): item for item in containers}
    if len(by_service) != len(containers):
        identity_issues.append(f"{prefix}: CONTAINER_DUPLICATE: compose service identity is ambiguous")
    raw_by_id = {item.get("Id"): item for item in runtime.get("inspect") or []}
    if not required or not containers:
        container_issues.append(f"{prefix}: required container observation is empty")
    observations: list[dict[str, Any]] = []
    for service in required:
        item = by_service.get(service) or {}
        raw = raw_by_id.get(item.get("id")) or {}
        config = raw.get("Config") or {}
        labels = config.get("Labels") or {}
        project = labels.get("com.docker.compose.project") or labels.get("io.podman.compose.project")
        compose_service = labels.get("com.docker.compose.service") or labels.get("io.podman.compose.service")
        if project != placement.project or compose_service != service:
            identity_issues.append(f"{prefix}/{service}: container project/service label identity drifted")
        environment = dict(
            value.split("=", 1) for value in config.get("Env") or []
            if isinstance(value, str) and "=" in value
        )
        descriptor = (oci.get("images") or {}).get(compose_service_image_owner(service)) or {}
        expected_digest = str(descriptor.get("imageDigest") or "")
        config_identity = (material.get("configs") or {}).get(service) or {}
        mounts = {item.get("Destination"): item for item in raw.get("Mounts") or []}
        config_mount = mounts.get("/etc/qwq-config") or {}
        artifact_mount = mounts.get("/etc/quwoquan/artifact-identity.json") or {}
        if (
            config_mount.get("Source") != placement.remote_root + "/runtime/config-root"
            or config_mount.get("RW") is not False
            or artifact_mount.get("Source") != placement.remote_root + "/runtime/artifact-identity.json"
            or artifact_mount.get("RW") is not False
            or not config_identity.get("digest")
            or config_identity.get("digest") != config_identity.get("expectedDigest")
            or environment.get("CONFIG_VERSION") != config_identity.get("version")
        ):
            identity_issues.append(f"{prefix}/{service}: hosted mounted configuration identity drifted")
        if (
            not expected_digest or item.get("imageId") != expected_digest
            or normalize_image_id(raw.get("Image")) != expected_digest
            or environment.get("IMAGE_VERSION") != candidate_digest.removeprefix("sha256:")
            or environment.get("APP_ENV") != "prod"
            or not environment.get("CONFIG_VERSION")
        ):
            identity_issues.append(f"{prefix}/{service}: candidate image/config identity missing or drifted")
        if oci.get("materialSource") == "local-build" and environment.get("QWQ_NONPROMOTABLE_PREVALIDATION") != "first-party":
            identity_issues.append(f"{prefix}/{service}: rehearsal runtime identity missing")
        container_issue, health_issue, _ = _hosted_container_state(
            item, service=service, provider_bound=provider_bound,
        )
        if container_issue:
            container_issues.append(f"{prefix}/{service}: {container_issue}")
        if health_issue:
            first_party_issues.append(f"{prefix}/{service}: {health_issue}")
        health = str(item.get("health") or "")
        observations.append({
            "service": service, "imageId": str(item.get("imageId") or ""),
            "running": item.get("running") is True, "health": health,
            "providerBound": service in provider_bound,
        })
    for service in support:
        item = by_service.get(service) or {}
        raw = raw_by_id.get(item.get("id")) or {}
        config = raw.get("Config") or {}
        labels = config.get("Labels") or {}
        project = labels.get("com.docker.compose.project") or labels.get("io.podman.compose.project")
        compose_service = labels.get("com.docker.compose.service") or labels.get("io.podman.compose.service")
        if project != placement.project or compose_service != service:
            identity_issues.append(f"{prefix}/{service}: support project/service label identity drifted")
        expected_ref = (support_images or {}).get(service, "")
        reference_match = (
            re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", expected_ref) is not None
            and item.get("image") == expected_ref and config.get("Image") == expected_ref
        )
        if not reference_match:
            identity_issues.append(f"{prefix}/{service}: support pinned image reference missing or drifted")
        try:
            observed_digest = normalize_image_id(item.get("imageId"))
            if normalize_image_id(raw.get("Image")) != observed_digest:
                raise ValueError("container inspect image ID mismatch")
        except ValueError:
            observed_digest = ""
            identity_issues.append(f"{prefix}/{service}: support image ID missing or drifted")
        container_issue, health_issue, completed = _hosted_container_state(
            item, service=service, provider_bound=set(),
        )
        if container_issue:
            container_issues.append(f"{prefix}/{service}: {container_issue}")
        if health_issue:
            first_party_issues.append(f"{prefix}/{service}: {health_issue}")
        observations.append({
            "service": service, "running": item.get("running") is True,
            "health": item.get("health"), "completedTask": completed,
            "imageRef": str(item.get("image") or ""), "imageId": observed_digest,
            "pinnedReferenceVerified": reference_match,
            # manifest digest 不是 image config ID；缺 candidate 封存 ID 不能合成其相等证明。
            "candidateContentDigestVerified": False,
            "candidateContentDigestReason": "support candidate content digest is unavailable; pinned reference is not an image ID proof",
        })
    return {
        **expected, "containers": observations, "identityIssues": identity_issues,
        "containerIssues": container_issues, "firstPartyIssues": first_party_issues,
    }


def hosted_availability_report(
    *, target_name: str, environment: str, deployment_instance: str,
    ssh_host: str, host_id: str, candidate_digest: str,
) -> dict[str, Any]:
    """hosted 只消费当前 SSH 读回与 exact candidate；绝不查本地运行收据。"""
    import quwoquan_ops.cli.stackctl as _stackctl
    from quwoquan_ops.cli.lib import read_only_user_availability as availability
    from quwoquan_ops.cli.prod.render_prod_plane_stack_lib.constants import PROD_CADDY_IMAGE

    identity_issues: list[str] = []
    candidate: dict[str, Any] = {}
    oci: dict[str, Any] = {}
    observations: list[dict[str, Any]] = []
    access: dict[str, Any] = {}
    plan: list[Any] = []
    try:
        if target_name != "prod-hosted" or environment != "prod":
            raise ValueError("hosted target/environment identity mismatch")
        access = _stackctl.load_prod_hosted_access_manifest()
        plan = _stackctl.resolve_prod_hosted_plan(
            access, instance=deployment_instance, host_ids=[host_id] if host_id else None,
            ssh_host_override=ssh_host,
        )
        if not plan:
            raise ValueError("hosted deployment placement observation is empty")
        candidate, oci = _hosted_candidate(candidate_digest, deployment_instance)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        identity_issues.append(str(error))
    prevalidation = access.get("prevalidation") or {}
    provider_bound = set((prevalidation.get("readinessPolicy") or {}).get("providerBoundServices") or []) if deployment_instance == "prevalidate" else set()
    for placement in plan:
        try:
            runtime = _stackctl._prod_plane_runtime_report(
                placement.plane, instance=placement.instance, host=placement.ssh_host,
                host_id=placement.host_id, replica_id=placement.replica_id,
            )
            required = tuple(
                ((prevalidation.get("planes") or {}).get(placement.plane) or {}).get("startupServices") or []
            ) if deployment_instance == "prevalidate" else placement.governed_services
            material: dict[str, Any] = {}
            try:
                material = _hosted_material_readback(placement)
            except (OSError, RuntimeError, TypeError, ValueError) as error:
                identity_issues.append(f"{placement.plane}: {error}")
            support = tuple(placement.support_services)
            support_images = {"gamma-proxy": PROD_CADDY_IMAGE}
            if deployment_instance == "prevalidate" and placement.plane == "service":
                if material.get("dataMode") == "isolated":
                    isolated = prevalidation.get("isolatedData") or {}
                    support += tuple(isolated.get("services") or [])
                    support_images.update(isolated.get("images") or {})
                elif material.get("dataMode") != "external":
                    identity_issues.append("hosted prevalidation data mode is missing or unknown")
            observation = _hosted_runtime_checks(
                runtime, placement, required=required, oci=oci,
                candidate_digest=candidate_digest, provider_bound=provider_bound,
                material=material, support=support, support_images=support_images,
            )
            observations.append(observation)
            identity_issues.extend(observation["identityIssues"])
        except (OSError, RuntimeError, TypeError, ValueError, AttributeError) as error:
            identity_issues.append(f"{placement.plane}: hosted runtime observation failed: {error}")
    container_issues = [issue for item in observations for issue in item["containerIssues"]]
    first_party_issues = [issue for item in observations for issue in item["firstPartyIssues"]]
    if not observations:
        container_issues.append("no hosted container runtime was observed")
    identity_ready = bool(candidate and observations) and not identity_issues
    container_ready = identity_ready and not container_issues
    first_party_ready = container_ready and not first_party_issues
    non_promotable = bool(identity_ready and oci.get("materialSource") == "local-build")
    unavailable = {
        "provider_ready": "exact hosted Provider readiness evidence is unavailable",
        "release_active": "exact hosted content activation readback is unavailable",
        "content_exact_queries_ready": "exact hosted content query readback is unavailable",
        "device_bound": "exact hosted device binding evidence is unavailable",
        "content_live_passed": "exact hosted content UAT evidence is unavailable",
    }
    layers = [
        {"name": "build_ready", "status": "ready" if candidate else "blocked", "issues": identity_issues if not candidate else []},
        {"name": "runtime_full_ready", "status": "ready" if first_party_ready else "blocked", "issues": identity_issues + container_issues + first_party_issues},
        *[{"name": name, "status": "unavailable", "issues": [issue]} for name, issue in unavailable.items()],
    ]
    blocker_class = availability._first_blocker_class(layers)
    release_eligibility = {
        "status": "GATE_BLOCK", "nonPromotable": non_promotable,
        "issues": ["read-only runtime diagnosis grants no formal release qualification"],
    }
    return {
        "schema": availability.SCHEMA, "target": target_name, "environment": environment,
        "observedAt": _stackctl.utc_now(), "status": "failed",
        "firstBlockerClass": blocker_class,
        "firstBlocker": next((issue for layer in layers for issue in layer["issues"]), ""),
        "userAvailability": layers,
        "metrics": availability._metrics(target_name=target_name, layers=layers, overall_status="failed", first_blocker_class=blocker_class),
        "evidence": {
            "candidate": {"status": "validated" if candidate else "unavailable", "baselineId": candidate_digest if candidate else "", "materialSource": oci.get("materialSource", "factory")},
            "runtime": {
                "selectedMode": "hosted", "instance": deployment_instance,
                "identity": {"status": "ready" if identity_ready else "blocked", "issues": identity_issues},
                "replicas": observations,
            },
            "containerRuntime": {"status": "ready" if container_ready else "blocked", "issues": identity_issues + container_issues},
            "firstPartyReadiness": {"status": "ready" if first_party_ready else "blocked", "issues": identity_issues + container_issues + first_party_issues},
            "providerReadiness": {"status": "unavailable", "issues": [unavailable["provider_ready"]]},
            "contentUAT": {"status": "unavailable", "issues": [unavailable["content_live_passed"]]},
            "releaseEligibility": release_eligibility,
            "rehearsal": {"validated": non_promotable, "nonPromotable": non_promotable, "legalStaticPlaceholder": non_promotable and oci.get("legalStaticPlaceholder") is True},
        },
    }


def rejection(action: str) -> dict[str, Any]:
    normalized = str(action or "").strip()
    return {
        "exitCode": 2,
        "summary": f"prod-hosted {PROFILE} rejects mutation",
        "details": [
            f"action {normalized or '<empty>'} is prohibited by {PROFILE}",
            "allowed checks: status, health, release verify, inspect",
        ],
        "profile": PROFILE,
        "target": "prod-hosted",
        "status": "gate_block",
        "prohibitedAction": normalized,
    }


def command_hosted_read_only(args: argparse.Namespace) -> dict[str, Any]:
    import quwoquan_ops.cli.stackctl as _stackctl

    checks = tuple(dict.fromkeys(str(item).strip() for item in args.check if str(item).strip()))
    if not checks:
        checks = ALLOWED_CHECKS
    invalid = sorted(set(checks) - set(ALLOWED_CHECKS))
    if invalid:
        return rejection(invalid[0])
    if args.target != "prod-hosted":
        return {
            "exitCode": 2,
            "summary": f"{PROFILE} requires prod-hosted",
            "details": ["--target must be prod-hosted"],
            "profile": PROFILE,
        }

    identity = identity_arguments(args)
    results: list[dict[str, Any]] = []
    for check in checks:
        if check == "status":
            # status 的通用入口仍是 local startup 编排；这里直接消费 hosted 只读聚合。
            report = _stackctl._read_only_user_availability_report("prod-hosted", **identity)
            child = {
                "exitCode": 0 if report["status"] == "ready" else 1,
                "summary": "prod-hosted runtime availability: " + report["status"],
                "details": [report["firstBlocker"]], "runtimeDiagnostics": report["evidence"],
            }
        elif check == "health":
            child = _stackctl.command_health(
                argparse.Namespace(
                    **identity, command="health", target="prod-hosted", scope="full",
                    read_only=True, output_format="json", report_dir="",
                )
            )
        elif check == "verify":
            # 通用 verify 仍读取本地 startup envelope，不能让 hosted reader 调用它冒充 authority。
            child = {
                "exitCode": 2,
                "summary": "hosted release verification is GATE_BLOCK",
                "details": ["exact hosted formal release authority reader is unavailable in this diagnostic scope; local verify receipts are forbidden"],
                "runtimeDiagnostics": {"releaseEligibility": {"status": "GATE_BLOCK"}},
            }
        else:
            child = _stackctl.command_inspect(
                argparse.Namespace(
                    **identity, command="inspect", target="prod-hosted", kind="release",
                    scope="release", currentness=True, output_format="json", report_dir="",
                )
            )
        results.append({
            "check": check,
            "exitCode": child.get("exitCode"),
            "summary": child.get("summary", ""),
            "reportDir": child.get("reportDir", ""),
            "details": list(child.get("details") or []),
            "runtimeDiagnostics": child.get("runtimeDiagnostics", {}),
        })
    failed = [item for item in results if item.get("exitCode") != 0]
    return {
        "exitCode": 0 if not failed else 2,
        "summary": (
            "prod-hosted read-only inspection passed"
            if not failed
            else "prod-hosted read-only inspection is GATE_BLOCK"
        ),
        "details": [item["summary"] for item in results],
        "profile": PROFILE,
        "target": "prod-hosted",
        "readOnly": True,
        "remoteMutationPerformed": False,
        "devicePatrol": {"status": "not_executed", "reason": "hosted-read-only forbids device Patrol"},
        "localApp": {"status": "not_executed", "reason": "hosted-read-only forbids local App launch"},
        "actorMutation": {"status": "not_executed", "reason": "hosted-read-only forbids actor mutation"},
        "checks": results,
    }


def register_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser("hosted-read-only")
    parser.add_argument("--target", choices=("prod-hosted",), default="prod-hosted")
    parser.add_argument("--check", action="append", choices=ALLOWED_CHECKS, default=[])
    register_identity_arguments(parser)
