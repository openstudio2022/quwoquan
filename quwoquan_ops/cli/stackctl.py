#!/usr/bin/env python3
from __future__ import annotations

import argparse
import codecs
import contextlib
import fcntl
import hashlib
import json
import os
import re
import selectors
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.lib.common import (
    artifact_run_dir,
    ensure_list,
    load_json_yaml,
    relpath,
    run,
    utc_now,
    write_json,
    write_markdown,
)
from quwoquan_ops.cli.lib.android_official_release import (
    AndroidOfficialReleaseError,
    package_android_official_release,
)
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError,
    package_web_official_release,
)
from quwoquan_ops.cli.lib.official_distribution_release import (
    OfficialDistributionReleaseError,
    deploy_official_distribution,
    inspect_official_distribution,
)
from quwoquan_ops.cli.prod.collect_release_artifact_descriptors import (
    ARTIFACT_SCHEMAS as _RELEASE_ARTIFACT_SCHEMAS,
)
from quwoquan_ops.cli.prod import collect_release_artifact_descriptors
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact
from quwoquan_ops.cli.lib.compose_layout import compose_file_args, gamma_compose_files
from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS,
    TARGETS,
    get_environment,
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.media_delivery_manifest import (
    build_media_delivery_url,
    load_media_delivery_manifest,
)
from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
    open_local_acceptance_session,
    prepare_local_environment_auth,
    request_local_environment_json,
    resolve_running_local_deployment_work_root,
)
from quwoquan_ops.cli.lib.local_gamma_object_storage import (
    prepare_local_gamma_object_storage,
)
from quwoquan_ops.cli.lib.product_telemetry_log_sink import (
    load_product_telemetry_log_sink,
)
from quwoquan_ops.cli.lib.local_provider_credentials import (
    prepare_local_provider_credentials,
)
from quwoquan_ops.cli.lib.video_playback_evidence import (
    read_native_video_playback_evidence,
)
from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeOutcome,
    ProbeSource,
    ReadinessPhase,
    ShipReadinessReceipt,
    VerificationProfile,
    load_content_release_readiness_policy,
)
from quwoquan_ops.cli.lib.data_execution_fleet import (
    resolve_data_execution_fleet_endpoint,
)
from quwoquan_ops.cli.lib.local_gamma_media import (
    LocalGammaMediaError,
    materialize_local_gamma_media,
)
from quwoquan_ops.cli.lib.local_runtime_reservation import (
    assert_local_runtime_available,
    local_runtime_operation_lock_path,
)
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    DEFAULT_BUILD_GRACE_SECONDS,
    acquire_consumer_lease,
    active_consumer_leases,
    release_consumer_lease,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix import (
    PROFILE_LOCAL_ENV_GATE,
    run_local_env_gate_matrix,
)
from quwoquan_ops.cli.lib.local_postgres_migration_drift import (
    format_drift_gate_block,
    probe_migration_drift,
    wipe_local_postgres_volumes,
)
from quwoquan_ops.cli.lib.package_reuse import (
    can_reuse_package,
    write_package_fingerprint,
)
from quwoquan_ops.cli.lib.dev_up import (
    DEV_UP_ENVS,
    DEV_UP_STACK_TARGETS,
    app_target_for_env,
    build_start_app_command,
    launch_app,
    pick_dev_up_env,
    resolve_device_id,
)
from quwoquan_ops.cli.lib.filter_catalog_release import (
    PUBLISH_TOKEN_ENV_DEFAULT,
    execute_filter_catalog_command,
)
from quwoquan_ops.cli.lib.port_manifest import canonical_port, load_port_manifest, profile_ports
from quwoquan_ops.cli.lib.observability import (
    append_log_line,
    env_from_report_dir,
    parse_log_records,
    run_dir as observability_run_dir,
    run_id_from_report_dir,
    write_run_manifest,
    write_stackctl_links,
)
from quwoquan_ops.cli.lib.output_paths import (
    app_deployment_package_dir,
    deployment_target_for_env,
    deployment_target_path,
    env_observability_run_dir,
    env_runs_root,
    legal_static_deployment_package_dir,
    portal_deployment_package_dir,
    repo_local_dir,
    repo_run_dir,
    remove_deployment_tree,
    runtime_shared_deployment_package_dir,
    service_deployment_package_dir,
    web_deployment_package_dir,
    target_cache_dir,
    target_process_dir,
)


VERIFY_COMMAND_GROUPS = {
    "topology": [
        ["python3", "quwoquan_ops/gate/verify_stackctl_args_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_environment_assembly.py"],
        ["python3", "quwoquan_ops/gate/verify_local_env_port_manifest.py"],
    ],
    "config": [
        ["python3", "quwoquan_app/scripts/env/verify_public_vs_upstream_url_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_prod_rollout_stackctl_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_media_delivery_contract.py"],
        # N2-2：gamma-local 推荐 policy overlay 与 metadata 单真相源一致性
        # （objectCards 环境开关是唯一允许差异）。
        ["python3", "quwoquan_ops/gate/verify_gamma_policy_overlay.py"],
    ],
    "packaging": [
        ["python3", "quwoquan_ops/gate/verify_environment_packaging_contract.py"],
        ["python3", "quwoquan_ops/gate/verify_env_artifact_isolation.py"],
        ["python3", "quwoquan_app/scripts/env/verify_prod_package_purity.py"],
    ],
}

PROD_RELEASE_UNIT = "prod-stack"

DEFAULT_TARGET_BY_ENV = {
    "alpha": "alpha-local",
    "beta": "beta-local",
    "gamma": "gamma-local",
    "prod": "prod-hosted",
}

GAMMA_CONTENT_UAT_TARGET = "gamma-local"
RELEASE_HOMEPAGE_UAT_TEST_TARGET = (
    "test/user_acceptance/patrol/entity/"
    "release_homepage__consumer_render__functional__user_acceptance_test.dart"
)
VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET = "test/user_acceptance/patrol/environment/video_playback_canary__user_acceptance_test.dart"

# CLI summaries should retain every concise prerequisite failure while keeping
# the terminal surface bounded. Full child-process output remains in report.json.
COMMAND_SUMMARY_DETAIL_LIMIT = 12
# A cold iOS simulator build can legitimately take several minutes while
# Xcode compiles native plugins. Treat it as a launch failure only after this
# bounded first-build allowance, rather than reporting a false environment
# failure while the app continues to start in the background.
ALPHA_APP_FIRST_BUILD_TIMEOUT_SECONDS = 300.0
PROVIDER_CONFORMANCE_SCRIPT = "quwoquan_ops/cli/lib/provider_conformance.py"
# Keep argparse choices local so `stackctl up` (used by Xcode build phases) does
# not eagerly import PyYAML-dependent provider-conformance modules.
PROVIDER_CONFORMANCE_EVIDENCE_ENVIRONMENTS = ("alpha", "beta", "gamma", "prod")
PROVIDER_CONFORMANCE_LAYERS = (
    "local_contract",
    "api_integration",
    "user_acceptance",
)
_PROVIDER_CAPABILITY_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]+)+$"
)


def _provider_conformance_runner():
    from quwoquan_ops.cli import provider_conformance_runner

    return provider_conformance_runner


def _external_provider_governance():
    from quwoquan_ops.cli.lib import external_provider_governance

    return external_provider_governance


def _provider_conformance():
    from quwoquan_ops.cli.lib import provider_conformance

    return provider_conformance
GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS: tuple[tuple[str, str], ...] = (
    ("recommendation-service", "LOCAL_GAMMA_RECOMMENDATION_SERVICE_IMAGE"),
    ("content-service", "LOCAL_GAMMA_CONTENT_SERVICE_IMAGE"),
    ("chat-service", "LOCAL_GAMMA_CHAT_SERVICE_IMAGE"),
    ("user-service", "LOCAL_GAMMA_USER_SERVICE_IMAGE"),
    ("assistant-service", "LOCAL_GAMMA_ASSISTANT_SERVICE_IMAGE"),
    ("product-ops-service", "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_IMAGE"),
    ("platform-ops-service", "LOCAL_GAMMA_PLATFORM_OPS_SERVICE_IMAGE"),
    ("tag-service", "LOCAL_GAMMA_TAG_SERVICE_IMAGE"),
    ("search-service", "LOCAL_GAMMA_SEARCH_SERVICE_IMAGE"),
    ("entity-service", "LOCAL_GAMMA_ENTITY_SERVICE_IMAGE"),
    ("circle-service", "LOCAL_GAMMA_CIRCLE_SERVICE_IMAGE"),
    ("integration-service", "LOCAL_GAMMA_INTEGRATION_SERVICE_IMAGE"),
    ("notification-service", "LOCAL_GAMMA_NOTIFICATION_SERVICE_IMAGE"),
    ("rtc-service", "LOCAL_GAMMA_RTC_SERVICE_IMAGE"),
    ("realtime-gateway", "LOCAL_GAMMA_REALTIME_GATEWAY_IMAGE"),
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _sha256_tree(directory: Path) -> str:
    """生成目录的路径敏感内容摘要，作为静态包可复算的供应链证据。"""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256_file(path).encode("ascii"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _packaged_service_source_image_ref(env_name: str, service: str) -> str:
    report_path = service_deployment_package_dir(env_name, service) / "provenance.json"
    if not report_path.is_file():
        raise FileNotFoundError(f"service package provenance missing: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    try:
        source_digest = str(report["digests"]["sourceTree"])
    except (KeyError, TypeError) as exc:
        raise ValueError(
            f"service source provenance missing: {report_path}"
        ) from exc
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", source_digest):
        raise ValueError(f"invalid service source digest: {report_path}")
    repository = service.replace("-", "_")
    return f"localhost/quwoquan_service_{repository}:{source_digest[7:19]}"


def _bind_gamma_packaged_service_image_refs(
    env_name: str,
    environment: dict[str, str],
) -> None:
    """把本次 package 的源码指纹显式绑定到 Gamma Compose 镜像引用。"""

    for service, environment_key in GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        environment[environment_key] = _packaged_service_source_image_ref(
            env_name,
            service,
        )


def _bind_gamma_external_provider_environment(
    environment: dict[str, str],
) -> str | None:
    """Materialize Gamma-local Port-equivalent provider substitutes."""
    for key in (
        "PRODUCT_OPS_SLS_REGION",
        "PRODUCT_OPS_SLS_ENDPOINT",
        "PRODUCT_OPS_SLS_PROJECT",
        "PRODUCT_OPS_SLS_RAW_LOGSTORE",
        "PRODUCT_OPS_SLS_STARTUP_DIAGNOSTIC_LOGSTORE",
        "PRODUCT_OPS_SLS_RUNTIME_LOGSTORE",
        "PRODUCT_OPS_SLS_AGGREGATE_LOGSTORE",
        "PRODUCT_OPS_SLS_TIMEOUT_MS",
        "PRODUCT_OPS_LOCAL_LOG_SINK_ENDPOINT",
        "PRODUCT_OPS_LOCAL_LOG_SINK_ACCESS_KEY",
        "ALIBABA_CLOUD_ACCESS_KEY_ID",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
        "ALIBABA_CLOUD_SECURITY_TOKEN",
    ):
        environment[key] = ""
    storage_error = _bind_gamma_object_storage_environment(environment)
    if storage_error is not None:
        return storage_error
    return _bind_local_external_provider_environment(
        environment,
        environment_name="gamma",
        target_name="gamma-local",
        storage_prefix="LOCAL_GAMMA",
    )


def _bind_gamma_object_storage_environment(
    environment: dict[str, str],
) -> str | None:
    """Materialize only the platform-owned Gamma object-storage binding."""
    try:
        storage = prepare_local_gamma_object_storage(
            edge_port=profile_ports(
                load_port_manifest(),
                "gamma-local",
            )["object-storage-edge"],
        )
    except (RuntimeError, ValueError) as exc:
        return f"gamma-local object storage materialization failed: {exc}"
    environment.update(storage.environment)
    environment.setdefault(
        "LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL",
        storage.host_endpoint,
    )
    _sync_object_storage_binding_aliases(environment, prefix="LOCAL_GAMMA")
    return None


def _bind_gamma_down_compose_placeholders(environment: dict[str, str]) -> None:
    """Satisfy Compose interpolation for teardown without runtime credentials."""

    storage_placeholders = {
        "ENDPOINT": "https://unused.invalid",
        "BUCKET": "unused",
        "REGION": "unused",
        "ACCESS_KEY_ID": "unused",
        "ACCESS_KEY_SECRET": "unused",
        "CDN_SIGN_KEY": "unused",
        "CA_FILE": "/dev/null",
        "TLS_DIR": "/tmp",
    }
    for suffix, value in storage_placeholders.items():
        source_key = f"LOCAL_GAMMA_OBJECT_STORAGE_{suffix}"
        compose_key = f"QWQ_COMPOSE_OBJECT_STORAGE_{suffix}"
        environment.setdefault(source_key, value)
        environment.setdefault(compose_key, environment[source_key])


def _bind_beta_external_provider_environment(
    environment: dict[str, str],
) -> str | None:
    """Materialize Beta-local Port-equivalent provider substitutes."""

    return _bind_local_external_provider_environment(
        environment,
        environment_name="beta",
        target_name="beta-local",
        storage_prefix="BETA",
    )


def _bind_local_external_provider_environment(
    environment: dict[str, str],
    *,
    environment_name: str,
    target_name: str,
    storage_prefix: str,
) -> str | None:
    """Materialize one non-prod environment's local Provider credentials."""

    try:
        values = prepare_local_provider_credentials(
            environment=environment_name,
            target_name=target_name,
        )
    except (RuntimeError, ValueError) as exc:
        return f"{target_name} external provider materialization failed: {exc}"
    environment.update(values)
    _sync_object_storage_binding_aliases(environment, prefix=storage_prefix)
    if values.get("CONTENT_EMBEDDING_FIXTURE_ENDPOINT"):
        environment.setdefault(
            "CONTENT_EMBEDDING_ENDPOINT",
            values["CONTENT_EMBEDDING_FIXTURE_ENDPOINT"],
        )
        environment.setdefault(
            "QWQ_COMPOSE_EMBEDDING_ENDPOINT",
            values["CONTENT_EMBEDDING_FIXTURE_ENDPOINT"],
        )
    if values.get("CONTENT_EMBEDDING_FIXTURE_API_KEY"):
        environment.setdefault(
            "CONTENT_EMBEDDING_API_KEY",
            values["CONTENT_EMBEDDING_FIXTURE_API_KEY"],
        )
        environment.setdefault(
            "QWQ_COMPOSE_EMBEDDING_API_KEY",
            values["CONTENT_EMBEDDING_FIXTURE_API_KEY"],
        )
    return None


def _sync_object_storage_binding_aliases(
    environment: dict[str, str],
    *,
    prefix: str,
) -> None:
    """Align CONTENT_OSS_* / QWQ_COMPOSE_OBJECT_STORAGE_* with MinIO materializer."""

    storage_to_content = {
        f"{prefix}_OBJECT_STORAGE_ENDPOINT": "CONTENT_OSS_ENDPOINT",
        f"{prefix}_OBJECT_STORAGE_BUCKET": "CONTENT_OSS_BUCKET",
        f"{prefix}_OBJECT_STORAGE_REGION": "CONTENT_OSS_REGION",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_ID": "CONTENT_OSS_ACCESS_KEY_ID",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_SECRET": "CONTENT_OSS_ACCESS_KEY_SECRET",
        f"{prefix}_OBJECT_STORAGE_CDN_DOMAIN": "CONTENT_CDN_DOMAIN",
        f"{prefix}_OBJECT_STORAGE_CDN_SIGN_KEY": "CONTENT_CDN_SIGN_KEY",
        f"{prefix}_OBJECT_STORAGE_CA_FILE": "CONTENT_OSS_CA_FILE",
    }
    storage_to_compose = {
        f"{prefix}_OBJECT_STORAGE_ENDPOINT": "QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT",
        f"{prefix}_OBJECT_STORAGE_BUCKET": "QWQ_COMPOSE_OBJECT_STORAGE_BUCKET",
        f"{prefix}_OBJECT_STORAGE_REGION": "QWQ_COMPOSE_OBJECT_STORAGE_REGION",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_ID": "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_SECRET": "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_SECRET",
        f"{prefix}_OBJECT_STORAGE_CDN_DOMAIN": "QWQ_COMPOSE_OBJECT_STORAGE_CDN_DOMAIN",
        f"{prefix}_OBJECT_STORAGE_CDN_SIGN_KEY": "QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY",
        f"{prefix}_OBJECT_STORAGE_CA_FILE": "QWQ_COMPOSE_OBJECT_STORAGE_CA_FILE",
    }
    for storage_key, content_key in storage_to_content.items():
        value = environment.get(storage_key)
        if value:
            environment[content_key] = value
    for storage_key, compose_key in storage_to_compose.items():
        value = environment.get(storage_key)
        if value:
            environment[compose_key] = value


def _gamma_start_command(args: argparse.Namespace) -> list[str]:
    command = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"]
    if getattr(args, "skip_build", False):
        command.append("--skip-build")
    if getattr(args, "build_only", False):
        command.append("--build-only")
        build_services = str(getattr(args, "build_services", "")).strip()
        if build_services:
            command.extend(["--build-services", build_services])
    return command


def _build_runtime_shared_package(env_name: str, *, target: str = "") -> Path:
    """将运行栈共享静态配置封装为环境 package，禁止启动期直读仓内源文件。"""
    target_name = deployment_target_for_env(env_name, target=target)
    package_dir = runtime_shared_deployment_package_dir(
        env_name,
        target=target_name,
    )
    if package_dir.exists():
        remove_deployment_tree(
            target_name,
            "packages",
            "runtime-shared",
        )
    package_dir.mkdir(parents=True, exist_ok=True)
    sources = (
        ROOT / "quwoquan_service" / "runtime" / "reliabletask" / "resources" / "module_catalog.yaml",
        ROOT / "quwoquan_service" / "runtime" / "reliabletask" / "resources" / "retention_policy.yaml",
    )
    files: dict[str, dict[str, str]] = {}
    for source in sources:
        if not source.is_file():
            raise FileNotFoundError(f"missing runtime shared package source: {source}")
        destination = package_dir / source.name
        shutil.copy2(source, destination)
        files[source.name] = {
            "source": relpath(source),
            "sha256": _sha256_file(destination),
        }
    write_json(
        package_dir / "manifest.json",
        {
            "schema": "qwq.runtime_shared_package",
            "environment": env_name,
            "createdAt": utc_now(),
            "provenance": {"files": files},
        },
    )
    return package_dir


def _materialize_prod_release_artifact(*, target: str = "") -> str:
    """校验 CI release artifact 与服务自治 prod 包一致，并记录供应链证据。

    release artifact 是可删除的发布证据，不再成为第二份运行配置。运行时始终只消费
    服务包中的 config/config.yaml，其 CONFIG_VERSION 为内容摘要。
    """
    artifact_root_value = os.environ.get("QWQ_PROD_RELEASE_ARTIFACT_ROOT", "").strip()
    if not artifact_root_value:
        return ""
    artifact_root = Path(artifact_root_value).expanduser()
    if not artifact_root.is_absolute():
        artifact_root = ROOT / artifact_root
    manifest_path = artifact_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"prod release artifact manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config_version = str((manifest.get("versions") or {}).get("configVersion") or "").strip()
    release_files = manifest.get("releaseFiles")
    if not config_version or not isinstance(release_files, dict):
        raise ValueError(f"invalid prod release artifact manifest: {manifest_path}")
    package_root = deployment_target_path(
        deployment_target_for_env("prod", target=target),
        "packages",
        "services",
    )
    artifact_digest = _sha256_file(manifest_path)
    for service, relative_path in release_files.items():
        source = artifact_root / str(relative_path)
        if not source.is_file():
            raise FileNotFoundError(f"prod release artifact file missing: {source}")
        destination_dir = package_root / str(service)
        report_path = destination_dir / "provenance.json"
        effective_config = destination_dir / "config/config.yaml"
        if not report_path.is_file() or not effective_config.is_file():
            raise FileNotFoundError(f"prod service package missing: {destination_dir}")
        source_digest = _sha256_file(source)
        effective_digest = _sha256_file(effective_config)
        if source_digest != effective_digest:
            raise ValueError(
                f"release artifact config differs from autonomous package: {service}"
            )
        provenance = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(provenance, dict):
            raise ValueError(f"service package provenance missing: {report_path}")
        if (provenance.get("digests") or {}).get("config") != effective_digest:
            raise ValueError(f"service package config provenance invalid: {report_path}")
        provenance["releaseArtifact"] = {
            "manifest": relpath(manifest_path),
            "manifestSha256": artifact_digest,
            "releaseId": config_version,
            "verifiedConfigDigest": effective_digest,
        }
        write_json(report_path, provenance)
    return config_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified environment packaging, startup, verification, inspection, and rollout control.",
    )
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    parser.add_argument("--report-dir", default="")
    subparsers = parser.add_subparsers(dest="command", required=True)

    package_parser = subparsers.add_parser("package")
    package_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    package_parser.add_argument("--env", choices=ENVIRONMENTS, required=True)
    package_parser.add_argument(
        "--kind",
        choices=[
            "runtime",
            "legal-static",
            "ops-portal",
            "app-release",
            "web",
            "release-manifest",
        ],
        default="runtime",
    )
    package_parser.add_argument("--service", default="")
    package_parser.add_argument("--include-services", action="store_true")
    package_parser.add_argument("--target", choices=TARGETS, default="")
    package_parser.add_argument("--version", default="")
    package_parser.add_argument("--ops-base-url", default="")
    package_parser.add_argument("--content-base-url", default="")
    package_parser.add_argument("--entity-base-url", default="")
    package_parser.add_argument("--oidc-issuer", default="")
    package_parser.add_argument("--oidc-client-id", default="")
    package_parser.add_argument("--oidc-audience", default="")
    package_parser.add_argument("--oidc-scope", default="")
    package_parser.add_argument("--skip-install", action="store_true")
    package_parser.add_argument("--apk-path", default="")
    package_parser.add_argument("--verify-remote-apk", action="store_true")
    package_parser.add_argument("--release-artifact-dir", default="")
    package_parser.add_argument("--public-web-manifest", default="")
    package_parser.add_argument("--android-release-manifest", default="")
    package_parser.add_argument("--ops-portal-provenance", default="")
    package_parser.add_argument("--contract-graph", default="")
    package_parser.add_argument("--provider-bindings", default="")
    package_parser.add_argument("--test-evidence", default="")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    verify_parser.add_argument("--env", choices=ENVIRONMENTS, default="")
    verify_parser.add_argument("--target", choices=TARGETS, default="")
    verify_parser.add_argument("--service", default="")
    verify_parser.add_argument(
        "--kind",
        choices=[
            "topology",
            "config",
            "packaging",
            "distribution",
            "legal-static",
            "config-slo",
            "all",
        ],
        default="all",
    )
    verify_parser.add_argument(
        "--profile",
        choices=[profile.value for profile in VerificationProfile],
        default=VerificationProfile.BASELINE.value,
    )
    verify_parser.add_argument("--error-rate", default="")
    verify_parser.add_argument("--p95-ms", default="")
    verify_parser.add_argument("--redis-error-rate", default="")
    verify_parser.add_argument(
        "--backup-recovery-receipt",
        default="",
        help="prod release 的 hosted 灾备隔离恢复 receipt；缺失即阻断",
    )
    verify_parser.add_argument(
        "--reuse-package",
        action="store_true",
        help="若近期 package fingerprint 仍有效则跳过 verify 内嵌 package",
    )
    verify_parser.add_argument("--distribution-root", default="")
    verify_parser.add_argument("--verify-hosted", action="store_true")

    matrix_parser = subparsers.add_parser(
        "matrix",
        help="串行本地四环境门禁矩阵（local-env-gate）",
    )
    matrix_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    matrix_parser.add_argument(
        "--profile",
        choices=(PROFILE_LOCAL_ENV_GATE,),
        default=PROFILE_LOCAL_ENV_GATE,
    )
    matrix_parser.add_argument(
        "--cache-mode",
        choices=("auto", "warm", "cold"),
        default="auto",
        help="warm 启用 skip-build + gamma data-plane 短路；cold 强制重建",
    )
    matrix_parser.add_argument(
        "--skip-l0",
        action="store_true",
        help="跳过 make commit-gate（仅编排环境段）",
    )
    matrix_parser.add_argument(
        "--no-auto-wipe-drift",
        action="store_true",
        help="迁移 checksum 漂移时不自动 wipe local postgres",
    )

    provider_conformance_parser = subparsers.add_parser(
        "provider-conformance",
        help="执行一个 Provider Conformance 九格单元并写入受证明证据",
    )
    provider_conformance_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    provider_conformance_parser.add_argument("--adapter-id", default="")
    provider_conformance_parser.add_argument("--capability-id", default="")
    provider_conformance_parser.add_argument(
        "--env",
        default="",
        choices=("", *PROVIDER_CONFORMANCE_EVIDENCE_ENVIRONMENTS),
    )
    provider_conformance_parser.add_argument(
        "--layer",
        default="",
        choices=("", *PROVIDER_CONFORMANCE_LAYERS),
    )
    provider_conformance_parser.add_argument("--matrix", action="store_true")
    provider_conformance_parser.add_argument("--execute", action="store_true")
    provider_conformance_parser.add_argument("--image-digest", default="")
    provider_conformance_parser.add_argument("--data-digest", default="")

    up_parser = subparsers.add_parser("up")
    up_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    up_parser.add_argument("--target", choices=TARGETS, default="")
    up_parser.add_argument("--env", choices=DEV_UP_ENVS, default="")
    up_parser.add_argument("--device-id", default="")
    up_parser.add_argument("--skip-app", action="store_true")
    up_parser.add_argument("--skip-build", action="store_true")
    up_parser.add_argument(
        "--build-only",
        action="store_true",
        help="仅构建 Gamma 本地服务镜像，不启动 Compose 或 App。",
    )
    up_parser.add_argument(
        "--build-services",
        default="",
        help="与 --build-only 配合，构建逗号分隔的 Gamma 服务镜像。",
    )
    up_parser.add_argument(
        "--workload",
        choices=["content-release", "full"],
        default="full",
    )
    up_parser.add_argument("--rollout-mode", choices=["gray-initial", "carry-on", "full"], default="")

    log_sink_control_parser = subparsers.add_parser(
        "product-telemetry-log-sink",
        help="在 beta/gamma 本地目标受控执行产品遥测日志端口验证。",
    )
    log_sink_control_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    log_sink_control_parser.add_argument(
        "--target",
        choices=("beta-local", "gamma-local"),
        required=True,
    )
    log_sink_control_parser.add_argument(
        "--action",
        choices=("all", "cold-start", "health", "send-query", "permission-failure"),
        default="all",
    )

    down_parser = subparsers.add_parser("down")
    down_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    down_parser.add_argument("--target", choices=TARGETS, required=True)

    consumer_lease_parser = subparsers.add_parser(
        "consumer-lease",
        help="protect a local runtime while a true-device app consumes it",
    )
    consumer_lease_parser.add_argument(
        "action",
        choices=("acquire", "release", "status"),
    )
    consumer_lease_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local", "prod-sim"),
        required=True,
    )
    consumer_lease_parser.add_argument("--device", default="")
    consumer_lease_parser.add_argument("--consumer", default="flutter-run")
    consumer_lease_parser.add_argument(
        "--package-name",
        default="com.quwoquan.quwoquan_app",
    )
    consumer_lease_parser.add_argument(
        "--ports",
        default="17000,17010,17100",
        help="comma-separated adb reverse ports",
    )
    consumer_lease_parser.add_argument(
        "--build-grace-seconds",
        type=int,
        default=DEFAULT_BUILD_GRACE_SECONDS,
    )

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    status_parser.add_argument("--target", choices=TARGETS, required=True)

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    health_parser.add_argument("--target", choices=TARGETS, required=True)
    health_parser.add_argument(
        "--scope",
        choices=["edge", "media", "service", "content-import", "content-consumer", "full"],
        # 缺省跟随最近一次 up 的 workload（content-release → content-consumer /
        # content-import）；显式 --scope full 仍可做完整探针。
        default=argparse.SUPPRESS,
    )
    health_parser.add_argument("--request-timeout-seconds", type=int, default=0)
    health_parser.add_argument("--retry-attempts", type=int, default=0)
    health_parser.add_argument("--retry-sleep-seconds", type=float, default=-1.0)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    inspect_parser.add_argument("--target", choices=TARGETS, required=True)
    inspect_parser.add_argument(
        "--ssh-host",
        default="",
        help="SSH-only host for prod-hosted runtime inspection; never an App public base",
    )
    inspect_parser.add_argument(
        "--scope",
        choices=[
            "logs",
            "network",
            "data",
            "metrics",
            "config",
            "security",
            "release",
            "all",
        ],
        default="all",
    )
    inspect_parser.add_argument(
        "--kind",
        dest="scope",
        choices=[
            "logs",
            "network",
            "data",
            "metrics",
            "config",
            "security",
            "release",
            "all",
        ],
    )
    inspect_parser.add_argument("--distribution-root", default="")
    inspect_parser.add_argument("--verify-hosted", action="store_true")

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    doctor_parser.add_argument("--target", choices=TARGETS, required=True)
    doctor_parser.add_argument(
        "--ssh-host",
        default="",
        help="SSH-only host for prod-hosted runtime diagnosis; never an App public base",
    )

    content_readiness_parser = subparsers.add_parser(
        "content-readiness",
        help="验证指定内容发布 phase 的环境能力，不创建内容工作包",
    )
    content_readiness_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    content_readiness_parser.add_argument(
        "--phase",
        choices=[phase.value for phase in ReadinessPhase],
        required=True,
    )
    content_readiness_parser.add_argument("--env", choices=ENVIRONMENTS, required=True)

    subparsers.add_parser(
        "data-execution-fleet",
        help="解析 Data ReliableTask 唯一的本地 Mongo+Redis 运行端点。",
    )

    content_uat_parser = subparsers.add_parser(
        "content-uat",
        help="以当前 Gamma data-release 的运行案例执行实体主页真实端侧消费验收",
    )
    content_uat_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    content_uat_parser.add_argument(
        "--target",
        choices=(GAMMA_CONTENT_UAT_TARGET,),
        default=GAMMA_CONTENT_UAT_TARGET,
    )
    content_uat_parser.add_argument("--release-uat-cases", required=True)
    content_uat_parser.add_argument(
        "--platform",
        choices=("android", "ios", "all"),
        default="all",
    )
    content_uat_parser.add_argument("--device-id", action="append", default=[])

    filter_catalog_parser = subparsers.add_parser(
        "filter-catalog",
        help="按环境绑定的受信发布身份发布或复核 FilterCatalogRelease",
    )
    filter_catalog_parser.add_argument(
        "--target",
        choices=("beta-local", "gamma-local", "prod-hosted"),
        required=True,
    )
    filter_catalog_parser.add_argument(
        "--action",
        choices=("stage", "activate", "stage-and-activate", "verify", "rollback"),
        required=True,
    )
    filter_catalog_parser.add_argument("--rollback-release-id", default="")
    filter_catalog_parser.add_argument(
        "--token-env",
        default=PUBLISH_TOKEN_ENV_DEFAULT,
        help="prod service-principal bearer 的环境变量名；值绝不进入 argv 或报告",
    )
    filter_catalog_parser.add_argument(
        "--prod-gray-activation",
        action="store_true",
        help="仅在 prod gray 已获人工审批后允许 activate",
    )

    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    repair_parser.add_argument("--target", choices=TARGETS, required=True)
    repair_parser.add_argument(
        "--fix",
        choices=[
            "rebuild-packages",
            "reclaim-build-cache",
            "restart-stack",
            "reclaim-ports",
            "materialize-media",
        ],
        required=True,
    )

    roll_parser = subparsers.add_parser("roll")
    roll_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    roll_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    roll_parser.add_argument("--mode", choices=("restart", "rollout"), default="restart")
    roll_parser.add_argument("--stage", default="")
    roll_parser.add_argument("--image-version", default="")
    roll_parser.add_argument("--previous-image-version", default="")
    roll_parser.add_argument("--image-repository-root", default="")
    roll_parser.add_argument("--image-registry", default="")
    roll_parser.add_argument("--registry-username", default="")
    roll_parser.add_argument("--registry-password", default="")

    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    deploy_parser.add_argument("--target", choices=TARGETS, default="")
    deploy_parser.add_argument("--env", choices=ENVIRONMENTS, default="")
    deploy_parser.add_argument(
        "--mode",
        choices=(
            "restart",
            "rollout",
            "cold-build",
            "config-gray",
            "config-rollback",
            "environment-assembly",
            "prevalidate",
        ),
        default="",
    )
    deploy_parser.add_argument(
        "--stage",
        choices=("gray-initial", "carry-on", "full"),
        default="",
        help="显式 rollout stage；未指定时按 step 映射为 5=gray-initial、25/50=carry-on、100=full",
    )
    deploy_parser.add_argument("--image-version", default="")
    deploy_parser.add_argument("--previous-image-version", default="")
    deploy_parser.add_argument("--image-repository-root", default="")
    deploy_parser.add_argument("--image-registry", default="")
    deploy_parser.add_argument("--registry-username", default="")
    deploy_parser.add_argument("--registry-password", default="")
    deploy_parser.add_argument("--service", default="")
    deploy_parser.add_argument("--from-image", default="")
    deploy_parser.add_argument("--to-image", default="")
    deploy_parser.add_argument("--from-config", default="")
    deploy_parser.add_argument("--to-config", default="")
    deploy_parser.add_argument("--rollback-config", default="")
    deploy_parser.add_argument("--step", default="")
    deploy_parser.add_argument("--cloud-provider", choices=["aliyun", "volcengine", "huaweicloud"], default="aliyun")
    deploy_parser.add_argument("--dry-run", choices=["true", "false"], default="false")
    deploy_parser.add_argument(
        "--artifact-kind",
        choices=("web", "app-release"),
        default="",
        help="部署同一 ReleaseManifest 绑定的官方 Web 或 Android 分发物",
    )
    deploy_parser.add_argument(
        "--artifact-manifest",
        default="",
        help="stackctl package 生成的 Web/APK 子清单",
    )
    deploy_parser.add_argument(
        "--distribution-root",
        default="",
        help="CDN/origin 挂载的目标根；prod 非 dry-run 必须显式提供或注入 QWQ_DISTRIBUTION_ROOT",
    )
    deploy_parser.add_argument(
        "--expected-current",
        default="",
        help="Web releaseId 或 Android buildNumber 的 CAS 前值",
    )
    deploy_parser.add_argument("--verify-hosted", action="store_true")
    deploy_parser.add_argument(
        "--release-manifest",
        default="",
        help=(
            "Service Pipeline 产出的 deployable manifest.json，或 "
            "oci://ghcr.io/.../release-artifact@sha256:...；真实生产发布必须提供"
        ),
    )
    deploy_parser.add_argument(
        "--prometheus-url",
        default="",
        help="生产 SLO readback 的 Prometheus base URL；非 dry-run 必须提供",
    )
    deploy_parser.add_argument(
        "--release-image-digest",
        default="",
        help="候选 OCI image 的 sha256；hosted receipt 必须绑定",
    )
    deploy_parser.add_argument(
        "--release-config-digest",
        default="",
        help="候选配置 bundle 的 sha256；hosted receipt 必须绑定",
    )
    deploy_parser.add_argument(
        "--contract-graph-digest",
        default="",
        help="候选 ContractGraph 的 sha256；hosted receipt 必须绑定",
    )
    deploy_parser.add_argument(
        "--adapter-digest",
        default="",
        help="候选 Provider adapter 的 sha256；hosted receipt 必须绑定",
    )
    deploy_parser.add_argument(
        "--ssh-host",
        default="",
        help="prod-hosted SSH 地址；只用于管理面，禁止成为 App public base",
    )
    deploy_parser.add_argument(
        "--data-mode",
        choices=("isolated", "external"),
        default="",
    )
    deploy_parser.add_argument(
        "--prevalidate-scope",
        choices=("first-party",),
        default="",
    )

    receipt_parser = subparsers.add_parser("hosted-release-receipt")
    receipt_parser.add_argument("--service", required=True)
    receipt_parser.add_argument("--receipt-id", required=True)
    receipt_parser.add_argument(
        "--purpose",
        choices=("last-good", "rollback"),
        required=True,
    )
    receipt_parser.add_argument("--image-digest", required=True)
    receipt_parser.add_argument("--config-digest", required=True)
    receipt_parser.add_argument("--contract-graph-digest", required=True)
    receipt_parser.add_argument("--adapter-digest", required=True)
    return parser


def resolve_report_dir(args: argparse.Namespace, env_name: str, target: str) -> Path:
    report_dir = getattr(args, "report_dir", "") or ""
    if report_dir:
        return Path(report_dir)
    return artifact_run_dir(env_name, args.command, target=target or "local")


def _start_timing() -> tuple[float, str]:
    return time.monotonic(), utc_now()


def _finish_timing(started_monotonic: float, started_at: str) -> dict[str, Any]:
    return {
        "startedAt": started_at,
        "endedAt": utc_now(),
        "durationMs": int((time.monotonic() - started_monotonic) * 1000),
    }


def _format_duration_ms(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "0ms"
    seconds = max(int(duration_ms), 0) / 1000.0
    if seconds < 1:
        return f"{int(duration_ms)}ms"
    return f"{seconds:.2f}s"


def _is_interactive_terminal() -> bool:
    return sys.stdout.isatty() and sys.stderr.isatty()


def _progress_print(message: str) -> None:
    if _is_interactive_terminal():
        print(message, flush=True)


def _format_stage_header(index: int, total: int, name: str) -> str:
    return f"[step {index}/{total}] {name}"


def _redact_controlled_values(text: str, values: tuple[str, ...]) -> str:
    redacted = text
    for value in sorted({item for item in values if len(item) >= 4}, key=len, reverse=True):
        redacted = redacted.replace(value, "<redacted>")
    return redacted


def _redact_controlled_payload(value: Any, values: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return _redact_controlled_values(value, values)
    if isinstance(value, list):
        return [_redact_controlled_payload(item, values) for item in value]
    if isinstance(value, dict):
        return {
            key: _redact_controlled_payload(item, values)
            for key, item in value.items()
        }
    return value


def _run_with_live_output(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    prefix: str = "",
    redaction_values: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged_env.update(env)
    process = subprocess.Popen(
        argv,
        cwd=str(cwd or ROOT),
        env=merged_env,
        text=False,
        bufsize=0,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    chunks: list[bytes] = []
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    interactive = _is_interactive_terminal()
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    exit_observed_at: float | None = None

    def emit_available_text(text: str, *, flush_partial: bool = False) -> None:
        nonlocal pending
        pending += text
        if not interactive:
            if flush_partial:
                pending = ""
            return
        while True:
            newline_index = pending.find("\n")
            if newline_index < 0:
                break
            line = pending[: newline_index + 1]
            pending = pending[newline_index + 1 :]
            line = _redact_controlled_values(line, redaction_values)
            if prefix:
                print(f"{prefix}{line}", end="", flush=True)
            else:
                print(line, end="", flush=True)
        if flush_partial and pending:
            pending = _redact_controlled_values(pending, redaction_values)
            if prefix:
                print(f"{prefix}{pending}", end="", flush=True)
            else:
                print(pending, end="", flush=True)
            pending = ""

    try:
        while True:
            events = selector.select(timeout=0.2)
            saw_output = False
            for _key, _mask in events:
                try:
                    data = os.read(process.stdout.fileno(), 4096)
                except BlockingIOError:
                    continue
                if not data:
                    exit_observed_at = 0.0
                    continue
                saw_output = True
                chunks.append(data)
                emit_available_text(decoder.decode(data))
            if saw_output:
                exit_observed_at = None
                continue
            if process.poll() is None:
                continue
            if exit_observed_at is None:
                exit_observed_at = time.monotonic()
                continue
            if exit_observed_at == 0.0 or time.monotonic() - exit_observed_at >= 0.5:
                break
    finally:
        selector.close()
        emit_available_text(decoder.decode(b"", final=True), flush_partial=True)
        process.stdout.close()
        if process.poll() is None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
    stdout = _redact_controlled_values(
        b"".join(chunks).decode("utf-8", errors="replace"),
        redaction_values,
    )
    return subprocess.CompletedProcess(
        argv,
        process.returncode,
        stdout=stdout,
        stderr="",
    )


def _tail_file_for_startup(
    log_path: Path,
    *,
    process: subprocess.Popen[str] | None = None,
    prefix: str = "[app] ",
    idle_timeout_seconds: float = 2.5,
    max_follow_seconds: float = 20.0,
    ready_patterns: tuple[str, ...] = (),
    failure_patterns: tuple[str, ...] = (),
    ready_idle_timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    emit_output = _is_interactive_terminal()
    deadline = time.monotonic() + max_follow_seconds
    while time.monotonic() < deadline:
        if log_path.exists():
            break
        if process is not None and process.poll() is not None:
            return {"followed": False, "lines": 0, "reason": "process-exited-before-log"}
        time.sleep(0.1)
    if not log_path.exists():
        return {"followed": False, "lines": 0, "reason": "log-not-created"}

    if emit_output:
        print(f"{prefix}tailing startup log: {relpath(log_path)}", flush=True)
    line_count = 0
    last_activity = time.monotonic()
    ready_seen = False
    failure_seen = False
    failure_line = ""
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        while True:
            line = handle.readline()
            if line:
                line_count += 1
                last_activity = time.monotonic()
                if emit_output:
                    print(f"{prefix}{line}", end="", flush=True)
                if ready_patterns and any(pattern in line for pattern in ready_patterns):
                    ready_seen = True
                if failure_patterns and any(pattern in line for pattern in failure_patterns):
                    failure_seen = True
                    if not failure_line:
                        failure_line = line.strip()
                continue
            if process is not None and process.poll() is not None:
                break
            now = time.monotonic()
            if now >= deadline:
                break
            effective_idle_timeout = ready_idle_timeout_seconds if ready_seen else None
            if effective_idle_timeout is not None and line_count > 0 and now - last_activity >= effective_idle_timeout:
                break
            time.sleep(0.15)
    reason = "idle"
    if process is not None and process.poll() is not None:
        reason = "process-exited"
    elif time.monotonic() >= deadline:
        reason = "timeout"
    if emit_output:
        print(f"{prefix}startup log tail finished ({reason})", flush=True)
    return {
        "followed": True,
        "lines": line_count,
        "reason": reason,
        "readySeen": ready_seen,
        "readyPatterns": list(ready_patterns),
        "failureSeen": failure_seen,
        "failureLine": failure_line,
        "failurePatterns": list(failure_patterns),
        "processExitCode": process.poll() if process is not None else None,
    }


def _prod_plane_runtime_report(
    plane: str,
    report_path: Path | None = None,
    *,
    instance: str = "prod",
    host: str = "",
) -> dict[str, Any]:
    argv = ["python3", "quwoquan_ops/cli/prod/inspect_prod_plane_runtime.py", "--plane", plane]
    argv.extend(["--instance", instance])
    if host:
        argv.extend(["--host", host])
    if report_path is not None:
        argv.extend(["--output", str(report_path)])
    result = run(argv)
    if result.returncode != 0:
        return {
            "plane": plane,
            "error": "inspect command failed",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitCode": result.returncode,
        }
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "plane": plane,
            "error": "inspect output is not valid json",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exitCode": result.returncode,
        }


def _prod_plane_runtime_findings(
    runtime: dict[str, Any],
    *,
    plane: str,
) -> list[str]:
    prefix = f"prod {plane} plane rootless runtime"
    if runtime.get("error") or int(runtime.get("exitCode", 0) or 0) != 0:
        return [f"{prefix} inspect failed"]
    findings: list[str] = []
    if not runtime.get("composeFileExists"):
        findings.append(f"{prefix} compose file is missing")
    if not runtime.get("envFileExists"):
        findings.append(f"{prefix} env file is missing")
    unit = runtime.get("unit") or {}
    if unit.get("enabled") is not True:
        findings.append(f"{prefix} systemd unit is not enabled")
    if unit.get("active") is not True:
        findings.append(f"{prefix} systemd unit is not active")
    containers = runtime.get("containers") or []
    if not containers:
        findings.append(f"{prefix} has no project containers")
    for container in containers:
        name = str(container.get("name") or "unknown")
        if container.get("running") is not True:
            findings.append(f"{prefix} container is not running: {name}")
        if container.get("health") in {"starting", "unhealthy"}:
            findings.append(
                f"{prefix} container health is {container.get('health')}: {name}"
            )
    return findings


def _app_launch_failure_detail(
    tail_result: dict[str, Any],
    *,
    default_message: str,
    require_ready: bool = True,
    process_exit_code: int | None = None,
) -> str | None:
    if bool(tail_result.get("failureSeen")):
        return str(tail_result.get("failureLine") or default_message)
    if process_exit_code not in (None, 0):
        return f"{default_message}: process exited with code {process_exit_code}"
    if require_ready and not bool(tail_result.get("readySeen")):
        reason = str(tail_result.get("reason") or "idle")
        return f"{default_message}: app did not reach Flutter ready state before {reason}"
    return None


def _tail_multiple_logs_for_startup(
    log_specs: list[tuple[str, Path]],
    *,
    idle_timeout_seconds: float = 2.5,
    max_follow_seconds: float = 20.0,
) -> dict[str, Any]:
    if not _is_interactive_terminal():
        return {"followed": False, "logs": [], "reason": "non-interactive"}
    existing_specs = [(label, path) for label, path in log_specs if path.exists()]
    if not existing_specs:
        return {"followed": False, "logs": [], "reason": "log-not-created"}

    for label, path in existing_specs:
        print(f"[{label}] tailing startup log: {relpath(path)}", flush=True)

    handles = {
        label: path.open("r", encoding="utf-8", errors="replace")
        for label, path in existing_specs
    }
    line_counts = {label: 0 for label, _ in existing_specs}
    last_activity = time.monotonic()
    deadline = time.monotonic() + max_follow_seconds
    try:
        while True:
            saw_output = False
            for label, _path in existing_specs:
                line = handles[label].readline()
                if not line:
                    continue
                saw_output = True
                line_counts[label] += 1
                last_activity = time.monotonic()
                print(f"[{label}] {line}", end="", flush=True)
            now = time.monotonic()
            if now >= deadline:
                reason = "timeout"
                break
            if saw_output:
                continue
            if sum(line_counts.values()) > 0 and now - last_activity >= idle_timeout_seconds:
                reason = "idle"
                break
            time.sleep(0.15)
    finally:
        for handle in handles.values():
            handle.close()

    for label, _path in existing_specs:
        print(f"[{label}] startup log tail finished ({reason})", flush=True)
    return {
        "followed": True,
        "logs": [
            {
                "label": label,
                "path": relpath(path),
                "lines": line_counts[label],
            }
            for label, path in existing_specs
        ],
        "reason": reason,
    }


def _tail_gamma_container_logs() -> dict[str, Any]:
    if not _is_interactive_terminal():
        return {"followed": False, "reason": "non-interactive", "backend": ""}

    compose_files = gamma_compose_files(ROOT)
    if any(not compose_file.exists() for compose_file in compose_files):
        return {"followed": False, "reason": "compose-file-missing", "backend": ""}

    docker_result = subprocess.run(
        ["docker", "--version"],
        text=True,
        capture_output=True,
        check=False,
    )
    use_podman = docker_result.returncode == 0 and "podman" in (docker_result.stdout + docker_result.stderr).lower()
    if use_podman:
        if subprocess.run(["podman", "--version"], text=True, capture_output=True, check=False).returncode != 0:
            return {"followed": False, "reason": "podman-missing", "backend": "podman"}
        containers = {
            "gamma-proxy": "quwoquan_service_gamma-proxy_1",
            "content-service": "quwoquan_service_content-service_1",
            "assistant-service": "quwoquan_service_assistant-service_1",
            "user-service": "quwoquan_service_user-service_1",
            "chat-service": "quwoquan_service_chat-service_1",
            "integration-service": "quwoquan_service_integration-service_1",
            "notification-service": "quwoquan_service_notification-service_1",
        }
        log_paths: list[tuple[str, Path]] = []
        with tempfile.TemporaryDirectory(prefix="gamma-tail-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            spawned: list[subprocess.Popen[str]] = []
            try:
                for label, container_name in containers.items():
                    inspect = subprocess.run(
                        ["podman", "inspect", container_name],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    if inspect.returncode != 0:
                        continue
                    log_path = tmp_root / f"{label}.log"
                    handle = log_path.open("w", encoding="utf-8")
                    proc = subprocess.Popen(
                        ["podman", "logs", "-f", "--tail", "40", container_name],
                        stdout=handle,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    handle.close()
                    spawned.append(proc)
                    log_paths.append((f"gamma-{label}", log_path))
                result = _tail_multiple_logs_for_startup(
                    log_paths,
                    idle_timeout_seconds=6.0,
                    max_follow_seconds=45.0,
                )
                result["backend"] = "podman"
                return result
            finally:
                for proc in spawned:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            proc.kill()
        return {"followed": False, "reason": "no-podman-containers", "backend": "podman"}

    if subprocess.run(["docker", "compose", "version"], text=True, capture_output=True, check=False).returncode != 0:
        return {"followed": False, "reason": "docker-compose-missing", "backend": "docker"}

    services = [
        "gamma-proxy",
        "content-service",
        "assistant-service",
        "user-service",
        "chat-service",
        "integration-service",
        "notification-service",
    ]
    with tempfile.TemporaryDirectory(prefix="gamma-tail-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        log_paths = [(f"gamma-{service}", tmp_root / f"{service}.log") for service in services]
        handles = {label: path.open("w", encoding="utf-8") for label, path in log_paths}
        process = subprocess.Popen(
            [
                "docker",
                "compose",
                *compose_file_args(compose_files),
                "logs",
                "-f",
                "--tail",
                "40",
                *services,
            ],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdout is not None
        try:
            deadline = time.monotonic() + 4.0
            while time.monotonic() < deadline:
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue
                for label, handle in handles.items():
                    service_name = label.removeprefix("gamma-")
                    if line.startswith(f"{service_name}"):
                        handle.write(line)
                        handle.flush()
            result = _tail_multiple_logs_for_startup(
                log_paths,
                idle_timeout_seconds=6.0,
                max_follow_seconds=45.0,
            )
            result["backend"] = "docker"
            return result
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            for handle in handles.values():
                handle.close()


def _local_runtime_log_root(target: str) -> Path:
    state_path = target_process_dir(target) / "local_run.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"local run state unavailable for {target}: {state_path}: {exc}") from exc
    observability_root = Path(str(payload.get("observabilityRoot") or ""))
    if not observability_root.is_absolute():
        raise RuntimeError(f"local run observabilityRoot must be absolute: {state_path}")
    return observability_root / "logs" / "service"


def _write_summary_bundle(
    report_dir: Path,
    *,
    command: str,
    target: str,
    status: str,
    summary: str,
    details: list[str],
    extra: dict[str, Any] | None = None,
    timing: dict[str, Any] | None = None,
) -> None:
    payload = {
        "command": command,
        "target": target,
        "status": status,
        "summary": summary,
        "details": details,
        "generatedAt": utc_now(),
    }
    if timing:
        payload.update(timing)
    if extra:
        payload.update(extra)
    write_json(report_dir / "summary.json", payload)
    env_name = env_from_report_dir(report_dir, target)
    run_id = run_id_from_report_dir(report_dir)
    obs_dir = observability_run_dir(env_name, run_id)
    write_run_manifest(
        obs_dir,
        env_name=env_name,
        run_id=run_id,
        command=command,
        target=target,
        report_dir=report_dir,
    )
    append_log_line(
        obs_dir / "logs" / "ci" / "stackctl" / "deploy.log",
        {
            "occurredAt": payload["generatedAt"],
            "severity": "ERROR" if status in {"failed", "gate_block"} else "INFO",
            "step": command,
            "result": status,
            "message": summary,
        },
    )
    write_stackctl_links(
        report_dir,
        env_name=env_name,
        run_id=run_id,
        obs_dir=obs_dir,
    )
    summary_lines = [
        f"# stackctl {command}",
        "",
        f"- target: `{target}`",
        f"- status: `{status}`",
        f"- summary: {summary}",
    ]
    if timing:
        summary_lines.extend(
            [
                f"- startedAt: `{timing.get('startedAt', '')}`",
                f"- endedAt: `{timing.get('endedAt', '')}`",
                f"- duration: `{_format_duration_ms(int(timing.get('durationMs', 0) or 0))}`",
            ]
        )
    write_markdown(
        report_dir / "summary.md",
        "\n".join(summary_lines + [*[f"- {line}" for line in details]]),
    )


def _write_stdout_markdown(report_dir: Path, sections: list[tuple[str, str]]) -> None:
    lines: list[str] = ["# stackctl stdout", ""]
    for title, content in sections:
        if not content.strip():
            continue
        lines.extend([f"## {title}", "", "```text", content.rstrip(), "```", ""])
    write_markdown(report_dir / "stdout.md", "\n".join(lines))


def _provider_readiness_failure_categories(
    report: dict[str, Any] | None,
    *,
    report_is_valid: bool,
    required_capabilities_ready: bool,
    child_exit_code: int,
) -> list[str]:
    """Map Provider diagnostics to stable, non-sensitive remediation categories."""
    categories: set[str] = set()
    if not report_is_valid:
        categories.add("provider-readiness-report")
    if not required_capabilities_ready:
        categories.add("readiness")
    if child_exit_code != 0:
        categories.add("provider-readiness")
    issues = report.get("issues") if isinstance(report, dict) else []
    if not isinstance(issues, list):
        return sorted(categories | {"provider-readiness-report"})
    for issue in issues:
        if not isinstance(issue, str):
            categories.add("provider-readiness-report")
            continue
        normalized = issue.lower()
        if any(
            marker in normalized
            for marker in (
                "evidence",
                "artifactref",
                "nine-cell",
                "executedat",
                "24-hour",
            )
        ):
            categories.add("evidence")
        if any(marker in normalized for marker in ("config", "binding", "state")):
            categories.add("configuration")
        if any(
            marker in normalized
            for marker in ("adapter", "commit", "imagedigest", "adapterdigest")
        ):
            categories.add("adapter-continuity")
        if any(marker in normalized for marker in ("capability", "required", "ready")):
            categories.add("readiness")
    return sorted(categories or {"provider-readiness"})


def _sanitized_provider_readiness_report(
    environment: str,
    *,
    child_exit_code: int,
    child_stdout: str,
) -> tuple[dict[str, Any], bool]:
    """Keep Provider readiness evidence locatable without persisting child output."""
    parsed: dict[str, Any] | None = None
    try:
        candidate = json.loads(child_stdout)
    except json.JSONDecodeError:
        candidate = None
    if isinstance(candidate, dict):
        parsed = candidate

    issues = parsed.get("issues") if parsed is not None else None
    readiness = parsed.get("readiness") if parsed is not None else None
    environment_readiness = (
        readiness.get(environment)
        if isinstance(readiness, dict)
        else None
    )
    report_is_valid = (
        parsed is not None
        and parsed.get("schema") == "provider-conformance-readiness"
        and parsed.get("version") == 1
        and isinstance(issues, list)
        and all(isinstance(issue, str) for issue in issues)
        and isinstance(environment_readiness, dict)
        and isinstance(parsed.get("evidenceCount"), int)
        and parsed["evidenceCount"] >= 0
    )
    required_capabilities: list[dict[str, Any]] = []
    required_capabilities_ready = report_is_valid
    if isinstance(environment_readiness, dict):
        for capability_id, capability in sorted(environment_readiness.items()):
            if (
                not isinstance(capability_id, str)
                or not _PROVIDER_CAPABILITY_ID_PATTERN.fullmatch(capability_id)
                or not isinstance(capability, dict)
                or not isinstance(capability.get("required"), bool)
                or not isinstance(capability.get("capability_ready"), bool)
            ):
                report_is_valid = False
                required_capabilities_ready = False
                continue
            if capability["required"]:
                ready = capability["capability_ready"]
                required_capabilities.append(
                    {
                        "capabilityId": capability_id,
                        "ready": ready,
                    }
                )
                required_capabilities_ready = required_capabilities_ready and ready
    else:
        required_capabilities_ready = False

    categories = _provider_readiness_failure_categories(
        parsed,
        report_is_valid=report_is_valid,
        required_capabilities_ready=required_capabilities_ready,
        child_exit_code=child_exit_code,
    )
    passed = (
        child_exit_code == 0
        and report_is_valid
        and not issues
        and required_capabilities_ready
    )
    return (
        {
            "schema": "stackctl-provider-readiness-preflight",
            "environment": environment,
            "status": "passed" if passed else "gate_block",
            "providerExitCode": child_exit_code,
            "evidenceCount": parsed["evidenceCount"] if report_is_valid else 0,
            "requiredCapabilities": required_capabilities,
            "failureCategories": [] if passed else categories,
        },
        passed,
    )


def _run_provider_readiness_preflight(
    environment: str,
    report_dir: Path,
) -> dict[str, Any]:
    """Run the single Provider readiness CLI and persist only its safe projection."""
    command = [
        "python3",
        PROVIDER_CONFORMANCE_SCRIPT,
        "--require-ready",
        environment,
    ]
    try:
        result = run(command)
        child_exit_code = result.returncode
        child_stdout = str(result.stdout or "")
    except OSError:
        child_exit_code = 127
        child_stdout = ""
    report, passed = _sanitized_provider_readiness_report(
        environment,
        child_exit_code=child_exit_code,
        child_stdout=child_stdout,
    )
    report_path = report_dir / "provider-readiness.json"
    write_json(report_path, report)
    failure_categories = report["failureCategories"]
    details = (
        []
        if passed
        else [
            "provider readiness preflight is GATE_BLOCK "
            f"({', '.join(failure_categories)}); inspect {relpath(report_path)}"
        ]
    )
    return {
        "kind": "provider-readiness",
        "environment": environment,
        "argv": command,
        "exitCode": 0 if passed else 2,
        "reportPath": relpath(report_path),
        "details": details,
        "report": report,
    }


def _selected_verify_commands(
    kind: str,
    env_name: str = "",
    *,
    target_name: str = "",
    profile: VerificationProfile,
) -> list[list[str]]:
    packaging_commands = [
        ["python3", "quwoquan_ops/gate/verify_environment_packaging_contract.py"]
        + (["--env", env_name] if env_name in ENVIRONMENTS else []),
        ["python3", "quwoquan_ops/gate/verify_env_artifact_isolation.py"]
        + (["--env", env_name] if env_name in ENVIRONMENTS else []),
        [
            "python3",
            "quwoquan_app/scripts/env/verify_prod_package_purity.py",
            "--target",
            target_name
            if env_name == "prod" and target_name
            else DEFAULT_TARGET_BY_ENV["prod"],
        ],
    ]
    if target_name:
        packaging_commands[0].extend(["--target", target_name])
        packaging_commands[1].extend(["--target", target_name])
    if kind == "all":
        commands: list[list[str]] = []
        group_names = ("topology", "config")
        if profile is not VerificationProfile.BASELINE:
            group_names = (*group_names, "packaging")
        for group_name in group_names:
            if group_name == "packaging":
                commands.extend(packaging_commands)
                continue
            commands.extend(VERIFY_COMMAND_GROUPS[group_name])
        return commands
    if kind == "packaging":
        return packaging_commands
    return list(VERIFY_COMMAND_GROUPS[kind])


def _local_target_edge_ready(target_name: str) -> bool:
    try:
        manifest = load_port_manifest()
    except Exception:
        return False
    for plane in ("api-edge", "product-ops-edge", "media-edge"):
        try:
            port = canonical_port(manifest, target_name, plane)
        except Exception:
            return False
        if not socket_probe(port):
            return False
    return True


def _local_target_runtime_ready(
    target_name: str,
    *,
    workload: str = "full",
) -> bool:
    try:
        topology = load_environment_topology()
        target = get_target(topology, target_name)
        profile_name = str(target.get("portProfile") or "")
        manifest = load_port_manifest()
    except Exception:
        return False
    if not profile_name:
        return _local_target_edge_ready(target_name)
    for role_name in _expected_local_roles(target_name, workload=workload):
        if role_name not in manifest.get("roles", {}):
            return False
        try:
            port = canonical_port(manifest, profile_name, role_name)
        except Exception:
            return False
        if not socket_probe(port):
            return False
    return True


def _gamma_data_plane_watermark_path() -> Path:
    from quwoquan_ops.cli.lib.output_paths import output_root

    return (
        output_root()
        / "env"
        / "gamma"
        / "local"
        / "gamma-local"
        / "cache"
        / "data-plane-watermark.json"
    )


def _gamma_data_plane_reuse_ready() -> bool:
    """True when gamma up wrote a ready data-plane watermark (seed/ES already done)."""
    path = _gamma_data_plane_watermark_path()
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return str(payload.get("status") or "") == "ready" and bool(payload.get("digest"))


def _selected_profile_commands(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None = None,
    service: str = "",
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    if profile.requires_environment and target_name in {
        "alpha-local",
        "beta-local",
        "gamma-local",
        "prod-sim",
    }:
        workload = (
            "content-release"
            if profile in {
                VerificationProfile.SMOKE,
                VerificationProfile.INTEGRATION,
            }
            else "full"
        )
        skip_nested_up = os.environ.get("STACKCTL_SKIP_NESTED_UP", "").strip() in {
            "1",
            "true",
            "TRUE",
            "yes",
            "YES",
        }
        if skip_nested_up or _local_target_runtime_ready(
            target_name, workload=workload
        ):
            commands.append(
                {
                    "name": f"{target_name}-health-preflight",
                    "argv": [
                        "python3",
                        "-c",
                        (
                            "print('local runtime ports already listening; "
                            f"skip stackctl up for {target_name}')"
                            if not skip_nested_up
                            else (
                                "print('STACKCTL_SKIP_NESTED_UP=1; "
                                f"skip nested stackctl up for {target_name}')"
                            )
                        ),
                    ],
                    "cwd": ROOT,
                }
            )
        else:
            commands.append(
                {
                    "name": f"{target_name}-up",
                    "argv": [
                        "python3",
                        "quwoquan_ops/cli/stackctl.py",
                        "up",
                        "--target",
                        target_name,
                        "--workload",
                        workload,
                        "--skip-app",
                    ],
                    "cwd": ROOT,
                }
            )
    if service:
        if (
            service == "assistant-service"
            and target_name == "gamma-local"
            and profile
            in {
                VerificationProfile.INTEGRATION,
                VerificationProfile.RELEASE,
            }
        ):
            command = _assistant_learning_gamma_api_integration_profile_command(
                target_name,
                profile,
                report_dir,
            )
            if command is not None:
                commands.append(command)
        if (
            service == "user-service"
            and target_name == "gamma-local"
            and profile
            in {
                VerificationProfile.INTEGRATION,
                VerificationProfile.RELEASE,
            }
        ):
            command = _profile_proposal_gamma_api_integration_profile_command(
                target_name,
                profile,
                report_dir,
            )
            if command is not None:
                commands.append(command)
        return commands
    if profile is VerificationProfile.SMOKE:
        commands.extend(
            [
                {
                    "name": "content-media-url-tests",
                    "argv": [
                        "python3",
                        "quwoquan_app/scripts/env/run_flutter_test_guarded.py",
                        "test/local_contract/core/media/content_media_url__local_contract_test.dart",
                        "test/local_contract/cloud/chat/chat_avatar_url_resolution__local_contract_test.dart",
                    ],
                    "cwd": ROOT,
                },
            ]
        )
    if (
        profile in {VerificationProfile.INTEGRATION, VerificationProfile.RELEASE}
        and target_name in {"beta-local", "gamma-local", "prod-hosted"}
    ):
        commands.append(
            {
                "name": "filter-catalog-active-release",
                "argv": [
                    "python3",
                    "quwoquan_ops/cli/stackctl.py",
                    "--output-format",
                    "json",
                    "filter-catalog",
                    "--target",
                    target_name,
                    "--action",
                    "verify",
                ],
                "cwd": ROOT,
            }
        )
    report_feedback_command = _report_feedback_lifecycle_profile_command(
        env_name,
        target_name,
        profile,
        report_dir,
    )
    if (
        report_feedback_command is not None
        and _current_runtime_health_scope(target_name) != "content-consumer"
    ):
        # content-release 不启 notification/product-ops；举报回流依赖
        # /app-messages，只能在 full workload 上证明。
        commands.append(report_feedback_command)
    media_publication_command = _media_publication_lifecycle_profile_command(
        env_name,
        target_name,
        profile,
        report_dir,
    )
    if media_publication_command is not None:
        commands.append(media_publication_command)
    chat_group_lifecycle_command = _chat_group_lifecycle_profile_command(
        env_name,
        target_name,
        profile,
        report_dir,
    )
    if (
        chat_group_lifecycle_command is not None
        and _current_runtime_health_scope(target_name) != "content-consumer"
    ):
        # content-release 不启 chat-service；建群到 inbox 旅程仅 full workload 证明。
        commands.append(chat_group_lifecycle_command)
    reliabletask_command = _reliabletask_gamma_api_integration_profile_command(
        target_name,
        profile,
        report_dir,
    )
    if reliabletask_command is not None:
        commands.append(reliabletask_command)
    onboarding_author_impact_command = (
        _onboarding_author_impact_gamma_api_integration_profile_command(
            target_name,
            profile,
            report_dir,
        )
    )
    if onboarding_author_impact_command is not None:
        commands.append(onboarding_author_impact_command)
    search_remote_api_command = _search_remote_api_integration_profile_command(
        target_name,
        profile,
        report_dir,
    )
    if search_remote_api_command is not None:
        commands.append(search_remote_api_command)
    if profile is VerificationProfile.RELEASE:
        if target_name == "prod-hosted":
            target = get_target(load_environment_topology(), target_name)
            public_bases = target.get("publicBases") or {}
            commands.append(
                {
                    "name": "prod-public-health",
                    "argv": [
                        "python3",
                        "quwoquan_ops/cli/stackctl.py",
                        "--output-format",
                        "json",
                        "health",
                        "--target",
                        "prod-hosted",
                        "--scope",
                        "full",
                    ],
                    "env": {"CLOUD_GATEWAY_BASE_URL": str(public_bases["api"])},
                }
            )
        media_preflight_command = _target_media_preflight_profile_command(
            target_name,
            report_dir,
        )
        if media_preflight_command is not None:
            commands.append(media_preflight_command)
        media_surface_command = _seeded_media_surface_profile_command(
            env_name,
            target_name,
        )
        if media_surface_command is not None:
            media_surface_command["stopOnFailure"] = True
            commands.append(media_surface_command)
        smoke_command = _environment_page_smoke_profile_command(
            env_name,
            target_name,
            report_dir,
        )
        if smoke_command is not None:
            commands.append(smoke_command)
        if env_name == "gamma" and target_name == "gamma-local":
            search_api_report = (
                report_dir
                / "search-remote-api-integration"
                / "search_remote_api_uat_report.json"
                if report_dir is not None
                else env_runs_root("gamma")
                / "search-remote-api-integration"
                / target_name
                / "search_remote_api_uat_report.json"
            )
            search_smoke_command = _environment_page_smoke_profile_command(
                env_name,
                target_name,
                report_dir,
                suite_name="search-remote-patrol",
                patrol_target=(
                    "test/user_acceptance/patrol/search/"
                    "cross_domain_search_journey__user_acceptance_test.dart"
                ),
                remote_api_evidence_report=search_api_report,
            )
            if search_smoke_command is not None:
                commands.append(search_smoke_command)
        commands.append(
            {
                "name": "prod-rollout-stackctl-contract",
                "argv": ["python3", "quwoquan_ops/gate/verify_prod_rollout_stackctl_contract.py"],
            }
        )
    return commands


def _reliabletask_gamma_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind the real Gamma Mongo/Redis ReliableTask suite to release verification."""

    if (
        target_name != "gamma-local"
        or profile is not VerificationProfile.RELEASE
    ):
        return None

    evidence_root = (
        report_dir / "reliabletask-gamma-api-integration"
        if report_dir is not None
        else env_runs_root("gamma")
        / "reliabletask-gamma-api-integration"
        / target_name
    )
    report_path = evidence_root / "reliabletask_api_integration_report.json"
    return {
        "name": "gamma-local-reliabletask-api-integration",
        "argv": [
            "bash",
            "quwoquan_ops/cli/gamma/run_reliabletask_gamma_api_integration.sh",
            "--reuse-stack",
        ],
        "cwd": ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "GAMMA_RELIABLETASK_API_INTEGRATION_REPORT": str(report_path),
        },
        "stopOnFailure": True,
        "reportPath": relpath(report_path),
    }


def _onboarding_author_impact_gamma_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind production Remote onboarding/AuthorImpact API UAT to Gamma release."""

    if (
        target_name != "gamma-local"
        or profile is not VerificationProfile.RELEASE
    ):
        return None

    evidence_root = (
        report_dir / "onboarding-author-impact-gamma-api-integration"
        if report_dir is not None
        else env_runs_root("gamma")
        / "onboarding-author-impact-gamma-api-integration"
        / target_name
    )
    report_path = evidence_root / "onboarding_author_impact_api_uat_report.json"
    return {
        "name": "gamma-local-onboarding-author-impact-api-integration",
        "argv": [
            "bash",
            "quwoquan_app/scripts/gamma/"
            "run_local_gamma_onboarding_author_impact_api_uat.sh",
        ],
        "cwd": ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "LOCAL_GAMMA_ONBOARDING_AUTHOR_IMPACT_API_UAT_REPORT": str(
                report_path
            ),
        },
        "stopOnFailure": True,
        "reportPath": relpath(report_path),
    }


def _search_remote_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind Gamma search/query feedback Remote evidence to release verification."""

    if (
        target_name != "gamma-local"
        or profile is not VerificationProfile.RELEASE
    ):
        return None

    evidence_root = (
        report_dir / "search-remote-api-integration"
        if report_dir is not None
        else env_runs_root("gamma")
        / "search-remote-api-integration"
        / target_name
    )
    report_path = evidence_root / "search_remote_api_uat_report.json"
    return {
        "name": "gamma-local-search-remote-api-integration",
        "argv": [
            "bash",
            "quwoquan_app/scripts/gamma/run_local_gamma_search_api_uat.sh",
        ],
        "cwd": ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "LOCAL_GAMMA_SEARCH_API_UAT_REPORT": str(report_path),
        },
        "stopOnFailure": True,
        "reportPath": relpath(report_path),
    }


def _assistant_learning_gamma_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind generated Assistant learning Remote evidence to Gamma verification."""

    if (
        target_name != "gamma-local"
        or profile
        not in {
            VerificationProfile.INTEGRATION,
            VerificationProfile.RELEASE,
        }
    ):
        return None

    evidence_root = (
        report_dir / "assistant-learning-remote-api-integration"
        if report_dir is not None
        else env_runs_root("gamma")
        / "assistant-learning-remote-api-integration"
        / target_name
    )
    report_path = evidence_root / "assistant_learning_remote_api_uat_report.json"
    return {
        "name": "gamma-local-assistant-learning-remote-api-integration",
        "argv": [
            "bash",
            "quwoquan_app/scripts/gamma/"
            "run_local_gamma_assistant_learning_api_uat.sh",
        ],
        "cwd": ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "LOCAL_GAMMA_ASSISTANT_LEARNING_API_UAT_REPORT": str(
                report_path,
            ),
        },
        "stopOnFailure": True,
        "reportPath": relpath(report_path),
    }


def _profile_proposal_gamma_api_integration_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind generated ProfileUpdateProposal Remote evidence to Gamma verification."""

    if (
        target_name != "gamma-local"
        or profile
        not in {
            VerificationProfile.INTEGRATION,
            VerificationProfile.RELEASE,
        }
    ):
        return None

    evidence_root = (
        report_dir / "profile-proposal-remote-api-integration"
        if report_dir is not None
        else env_runs_root("gamma")
        / "profile-proposal-remote-api-integration"
        / target_name
    )
    report_path = evidence_root / "profile_proposal_remote_api_uat_report.json"
    return {
        "name": "gamma-local-profile-proposal-remote-api-integration",
        "argv": [
            "bash",
            "quwoquan_app/scripts/gamma/"
            "run_local_gamma_profile_proposal_api_uat.sh",
        ],
        "cwd": ROOT,
        "env": {
            "QWQ_RUN_ROOT": str(evidence_root),
            "LOCAL_GAMMA_PROFILE_PROPOSAL_API_UAT_REPORT": str(report_path),
        },
        "stopOnFailure": True,
        "reportPath": relpath(report_path),
    }


def _report_feedback_lifecycle_profile_command(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """为本地可变更环境和只读生产环境绑定同一对象级旅程证据。"""

    mode = ""
    if target_name == "beta-local" and profile is VerificationProfile.INTEGRATION:
        mode = "lifecycle"
    elif target_name == "gamma-local" and profile is VerificationProfile.RELEASE:
        mode = "lifecycle"
    elif target_name == "prod-hosted" and profile is VerificationProfile.RELEASE:
        # 生产证据只能验证举报人的私有可读状态；写入、运营裁决和
        # 负反馈补偿均不得在真实生产环境由自动化触发。
        mode = "read-only"
    if not mode:
        return None

    topology = load_environment_topology()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "").strip()
    if not api_base_url:
        raise ValueError(
            f"{target_name} lacks publicBases.api for report-feedback lifecycle probe"
        )
    probe_report = (
        report_dir / "report-feedback-lifecycle.json"
        if report_dir is not None
        else env_runs_root(env_name)
        / "report-feedback-lifecycle"
        / target_name
        / "report-feedback-lifecycle.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
        "content-service/smoke/run_report_feedback_lifecycle_probe.py",
        "--env",
        env_name,
        "--base-url",
        api_base_url,
        "--mode",
        mode,
        "--report",
        str(probe_report),
    ]
    resolve_host = _local_public_connect_host(
        topology,
        target_name,
        api_base_url,
    )
    if resolve_host:
        argv.extend(["--resolve-host", resolve_host])
    return {
        "name": f"{target_name}-report-feedback-lifecycle",
        "argv": argv,
        "cwd": ROOT,
        "stopOnFailure": True,
        "reportPath": relpath(probe_report),
    }


def _media_publication_lifecycle_profile_command(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """将真实媒体上传、处理和发布闭环绑定到适用环境验证。"""

    mode = ""
    if target_name == "beta-local" and profile is VerificationProfile.INTEGRATION:
        mode = "lifecycle"
    elif target_name == "gamma-local" and profile is VerificationProfile.RELEASE:
        mode = "lifecycle"
    elif target_name == "prod-sim" and profile is VerificationProfile.INTEGRATION:
        # prod-sim 是唯一允许受控可变 canary 的生产镜像演练目标。
        mode = "lifecycle"
    elif target_name == "prod-hosted" and profile is VerificationProfile.RELEASE:
        # hosted production 不允许由默认验证链写入，只做显式凭据的只读探测。
        mode = "read-only"
    if not mode:
        return None

    topology = load_environment_topology()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "").strip()
    if not api_base_url:
        raise ValueError(
            f"{target_name} lacks publicBases.api for media publication lifecycle probe"
        )
    moderation_base_url = ""
    if mode == "lifecycle":
        origins = target.get("origins") or {}
        moderation_base_url = str(origins.get("contentService") or "").strip()
        if not moderation_base_url:
            raise ValueError(
                f"{target_name} lacks origins.contentService for media moderation lifecycle"
            )
    probe_report = (
        report_dir / "media-publication-lifecycle.json"
        if report_dir is not None
        else env_runs_root(env_name)
        / "media-publication-lifecycle"
        / target_name
        / "media-publication-lifecycle.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
        "content-service/smoke/run_media_publication_lifecycle_probe.py",
        "--env",
        env_name,
        "--target-name",
        target_name,
        "--base-url",
        api_base_url,
        "--mode",
        mode,
        "--report",
        str(probe_report),
    ]
    if moderation_base_url:
        argv.extend(["--moderation-base-url", moderation_base_url])
    resolve_host = _local_public_connect_host(
        topology,
        target_name,
        api_base_url,
    )
    if resolve_host:
        argv.extend(["--resolve-host", resolve_host])
    return {
        "name": f"{target_name}-media-publication-lifecycle",
        "argv": argv,
        "cwd": ROOT,
        "stopOnFailure": True,
        "reportPath": relpath(probe_report),
    }


def _chat_group_lifecycle_profile_command(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """将群候选、建群、mention 与 Inbox 闭环绑定到统一环境验证链。"""

    mutating = False
    if target_name == "beta-local" and profile is VerificationProfile.INTEGRATION:
        mutating = True
    elif target_name == "gamma-local" and profile is VerificationProfile.RELEASE:
        mutating = True
    elif target_name == "prod-hosted" and profile is VerificationProfile.RELEASE:
        # 真实生产只能读取受控验收账号的既有来源；Probe 本身会拒绝 prod 写入。
        mutating = False
    else:
        return None

    topology = load_environment_topology()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "").strip()
    if not api_base_url:
        raise ValueError(
            f"{target_name} lacks publicBases.api for chat group lifecycle probe"
        )
    probe_report = (
        report_dir / "chat-group-lifecycle.json"
        if report_dir is not None
        else env_runs_root(env_name)
        / "chat-group-lifecycle"
        / target_name
        / "chat-group-lifecycle.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
        "chat-service/smoke/run_chat_group_lifecycle_probe.py",
        "--env",
        env_name,
        "--base-url",
        api_base_url,
        "--require-nonempty-sources",
        "--report",
        str(probe_report),
    ]
    if mutating:
        argv.append("--mutating")
    resolve_host = _local_public_connect_host(
        topology,
        target_name,
        api_base_url,
    )
    if resolve_host:
        argv.extend(["--resolve-host", resolve_host])
    return {
        "name": f"{target_name}-chat-group-lifecycle",
        "argv": argv,
        "cwd": ROOT,
        "stopOnFailure": True,
        "reportPath": relpath(probe_report),
    }


def _target_media_preflight_profile_command(
    target_name: str,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """在设备 Patrol 之前验证 canonical media 的 Range/MIME。"""

    if target_name == "prod-hosted":
        health_report_path = (
            report_dir / "video-range-mime-preflight" / "report.json"
            if report_dir is not None
            else env_runs_root("prod")
            / "device-matrix"
            / "video-range-mime-preflight"
            / target_name
            / "report.json"
        )
        return {
            "name": "prod-hosted-release-video-canary-preflight",
            "argv": [
                "python3",
                "quwoquan_ops/cli/smoke/verify_video_playback_canary.py",
                "--target",
                "prod-hosted",
                "--report",
                str(health_report_path),
            ],
            "stopOnFailure": True,
            "reportPath": relpath(health_report_path),
        }
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        return None
    health_report_dir = (
        report_dir / "video-range-mime-preflight"
        if report_dir is not None
        else env_runs_root(get_target(load_environment_topology(), target_name)["env"])
        / "device-matrix"
        / "video-range-mime-preflight"
        / target_name
    )
    return {
        "name": f"{target_name}-video-range-mime-preflight",
        "argv": [
            "python3",
            "quwoquan_ops/cli/stackctl.py",
            "--output-format",
            "json",
            "--report-dir",
            str(health_report_dir),
            "health",
            "--target",
            target_name,
            "--scope",
            "media",
        ],
        "stopOnFailure": True,
        "reportPath": relpath(health_report_dir / "report.json"),
    }


def _read_json_object(path_value: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _current_commit_sha() -> str:
    configured = os.environ.get("GITHUB_SHA", "").strip()
    if configured:
        return configured
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _runtime_media_config_hash(target_name: str) -> str:
    """将当前 target 的 topology 与 App runtime 配置绑定到 T4 证据。"""

    topology = load_environment_topology()
    target = get_target(topology, target_name)
    env_name = str(target.get("env") or "").strip()
    config_path = ROOT / "quwoquan_app" / "configs" / env_name / "app_runtime.yaml"
    digest = hashlib.sha256()
    digest.update(
        json.dumps(target, ensure_ascii=False, sort_keys=True).encode("utf-8"),
    )
    if config_path.is_file():
        digest.update(config_path.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _local_video_canary_slice_key() -> str:
    try:
        assets = load_media_delivery_manifest()
    except ValueError:
        return ""
    for asset in assets:
        if (
            str(asset.get("logicalAssetId") or "").strip()
            == "media-canary-seek-125s-video"
        ):
            return str(asset.get("publicSliceKey") or "").strip().lstrip("/")
    return ""


def _video_canary_identity(target_name: str) -> dict[str, Any]:
    target = get_target(load_environment_topology(), target_name)
    playback_canary = target.get("playbackCanary")
    published_release = (
        isinstance(playback_canary, dict)
        and str(playback_canary.get("source") or "").strip()
        == "published-release"
    )
    if published_release:
        try:
            asset_version = int(
                os.environ.get("VIDEO_PLAYBACK_CANARY_ASSET_VERSION", "0").strip(),
            )
        except ValueError:
            asset_version = 0
        return {
            "assetId": os.environ.get(
                "VIDEO_PLAYBACK_CANARY_ASSET_ID",
                "",
            ).strip(),
            "assetVersion": asset_version,
            "probeHash": os.environ.get(
                "VIDEO_PLAYBACK_CANARY_PROBE_HASH",
                "",
            ).strip(),
        }
    descriptor_path = (
        ROOT
        / "quwoquan_service"
        / "contracts"
        / "metadata"
        / "_shared"
        / "test_fixtures"
        / "media"
        / "media"
        / "video"
        / "s"
        / "media-canary-seek-125s"
        / "v1"
        / "descriptor.json"
    )
    descriptor = _read_json_object(str(descriptor_path))
    return {
        "assetId": str(
            descriptor.get("assetId") or "media-canary-seek-125s",
        ).strip(),
        "assetVersion": int(descriptor.get("assetVersion") or 1),
        "probeHash": str(descriptor.get("probeHash") or "").strip(),
    }


def _video_canary_public_slice_key(target_name: str) -> str:
    target = get_target(load_environment_topology(), target_name)
    playback_canary = target.get("playbackCanary")
    if not isinstance(playback_canary, dict):
        return ""
    configured = str(playback_canary.get("publicSliceKey") or "").strip()
    if configured:
        return configured.lstrip("/")
    env_name = str(playback_canary.get("publicSliceKeyEnv") or "").strip()
    if env_name:
        return os.environ.get(env_name, "").strip().lstrip("/")
    return _local_video_canary_slice_key()


def _video_canary_post_id(target_name: str) -> str:
    target = get_target(load_environment_topology(), target_name)
    playback_canary = target.get("playbackCanary")
    if not isinstance(playback_canary, dict):
        return ""
    configured = str(playback_canary.get("workId") or "").strip()
    if configured:
        return configured
    env_name = str(playback_canary.get("workIdEnv") or "").strip()
    return os.environ.get(env_name or "VIDEO_PLAYBACK_CANARY_WORK_ID", "").strip()


def _profile_step(steps: list[dict[str, Any]], name_fragment: str) -> dict[str, Any]:
    for step in steps:
        if name_fragment in str(step.get("name") or ""):
            return step
    return {}


def _video_range_evidence_from_preflight(
    steps: list[dict[str, Any]],
    target_name: str,
) -> dict[str, Any]:
    """从同一次 T4 preflight 的结构化 health/report 取 Range 与 MIME。"""

    if target_name == "prod-hosted":
        step = _profile_step(steps, "release-video-canary-preflight")
        try:
            payload = json.loads(str(step.get("stdout") or ""))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            return {
                "statusCode": payload.get("rangeStatus"),
                "mimeType": payload.get("contentType"),
                "reportPath": str(step.get("reportPath") or ""),
            }
        return {}

    step = _profile_step(steps, "video-range-mime-preflight")
    report = _read_json_object(str(step.get("reportPath") or ""))
    checks = report.get("checks")
    if not isinstance(checks, list):
        return {}
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("name") or "") != "media-public-content-video-primary":
            continue
        return {
            "statusCode": check.get("statusCode"),
            "mimeType": check.get("contentType"),
            "reportPath": str(step.get("reportPath") or ""),
        }
    return {}


def _video_ui_evidence_from_smoke(steps: list[dict[str, Any]]) -> dict[str, Any]:
    step = _profile_step(steps, "environment-page-smoke")
    report_path = str(step.get("reportPath") or "")
    report = _read_json_object(report_path)
    runs = report.get("runs")
    if not isinstance(runs, list):
        runs = []
    successful_runs = [
        item
        for item in runs
        if isinstance(item, dict) and item.get("exitCode") == 0
    ]
    native_evidence_run: dict[str, Any] | None = None
    physical_ios_run: dict[str, Any] | None = None
    for run_item in successful_runs:
        device = run_item.get("device")
        evidence = run_item.get("evidence")
        if not isinstance(device, dict) or not isinstance(evidence, dict):
            continue
        platform = str(device.get("targetPlatform") or "").lower()
        if (
            platform.startswith("ios")
            and device.get("emulator") is False
            and physical_ios_run is None
        ):
            physical_ios_run = run_item
        if not platform.startswith("android"):
            continue
        playback = evidence.get("videoPlayback")
        if not isinstance(playback, dict):
            continue
        if (
            native_evidence_run is None
            and device.get("emulator") is False
            and playback.get("nativeFirstFrame") is True
            and playback.get("nativeSeekSettled") is True
        ):
            native_evidence_run = run_item
    selected_run = native_evidence_run or (
        successful_runs[0] if successful_runs else None
    )
    screenshot_path = ""
    selected_evidence = (
        selected_run.get("evidence") if isinstance(selected_run, dict) else None
    )
    if isinstance(selected_evidence, dict):
        evidence = selected_evidence
        screenshot = evidence.get("afterScreenshot")
        if isinstance(screenshot, dict):
            screenshot_path = str(screenshot.get("path") or "").strip()
    native_playback_raw_log_path = (
        str(selected_evidence.get("rawLogPath") or "").strip()
        if native_evidence_run is not None and isinstance(selected_evidence, dict)
        else ""
    )
    native_playback_log = Path(native_playback_raw_log_path)
    if native_playback_raw_log_path and not native_playback_log.is_absolute():
        native_playback_log = ROOT / native_playback_log
    native_playback = read_native_video_playback_evidence(native_playback_log)
    physical_android_native_evidence = (
        native_evidence_run is not None
        and native_playback.get("nativeFirstFrame") is True
        and native_playback.get("nativeSeekSettled") is True
    )
    passed = (
        str(report.get("status") or "").strip().lower() == "passed"
        and bool(successful_runs)
    )
    output_summaries = "\n".join(
        str(item.get("outputSummary") or "")
        for item in runs
        if isinstance(item, dict)
    )
    if passed:
        stage_rendered: bool | None = True
        player_ready = True
        player_error: bool | None = False
        player_state = "ready"
    elif "configured video canary stage should render" in output_summaries:
        stage_rendered = False
        player_ready = False
        player_error = None
        player_state = "stage-not-rendered"
    elif "native video player entered its explicit error state" in output_summaries:
        stage_rendered = True
        player_ready = False
        player_error = True
        player_state = "explicit-error"
    elif "native video player must reach ready state" in output_summaries:
        stage_rendered = True
        player_ready = False
        player_error = None
        player_state = "ready-timeout"
    else:
        stage_rendered = None
        player_ready = False
        player_error = None
        player_state = "unverified"
    return {
        "stageRendered": stage_rendered,
        "playerReady": player_ready,
        "playerError": player_error,
        "playerState": player_state,
        "reportPath": report_path,
        "screenshotPath": screenshot_path,
        "recordingPath": os.environ.get(
            "VIDEO_PLAYBACK_CANARY_RECORDING_PATH",
            "",
        ).strip(),
        "seekTargetsVerified": passed,
        "nativeFirstFrame": physical_android_native_evidence,
        "nativeSeekSettled": physical_android_native_evidence,
        "nativeEvidenceFromPhysicalAndroidDevice": physical_android_native_evidence,
        "nativeEvidenceDevicePlatform": (
            "android" if physical_android_native_evidence else ""
        ),
        "nativeEvidenceDeviceEmulator": (
            False if physical_android_native_evidence else None
        ),
        "nativePlaybackRawLogPath": native_playback_raw_log_path,
        "physicalIosPatrolPassed": physical_ios_run is not None,
        "seekEvidenceSource": (
            "native_settled"
            if physical_android_native_evidence
            else "unverified"
        ),
        "qoeReadbackPath": os.environ.get(
            "VIDEO_PLAYBACK_QOE_READBACK_PATH",
            "",
        ).strip(),
        "perfettoTracePath": os.environ.get(
            "VIDEO_PLAYBACK_PERFETTO_TRACE_PATH",
            "",
        ).strip(),
        "perfettoSummaryPath": os.environ.get(
            "VIDEO_PLAYBACK_PERFETTO_SUMMARY_PATH",
            "",
        ).strip(),
    }


def _runtime_media_t4_evidence(
    *,
    target_name: str,
    steps: list[dict[str, Any]],
    started_at: str,
    ended_at: str,
) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    env_name = str(target.get("env") or "").strip()
    public_bases = target.get("publicBases")
    public_bases = public_bases if isinstance(public_bases, dict) else {}
    public_slice_key = _video_canary_public_slice_key(target_name)
    service_evidence = {
        "videoRange": _video_range_evidence_from_preflight(steps, target_name),
    }
    ui_evidence = _video_ui_evidence_from_smoke(steps)
    media_identity = _video_canary_identity(target_name)
    post_id = _video_canary_post_id(target_name)
    video_range = service_evidence["videoRange"]
    dry_run = os.environ.get("STACKCTL_PAGE_SMOKE_DRY_RUN", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    is_passed = (
        bool(public_slice_key)
        and bool(post_id)
        and bool(media_identity.get("assetId"))
        and int(media_identity.get("assetVersion") or 0) > 0
        and bool(media_identity.get("probeHash"))
        and not dry_run
        and video_range.get("statusCode") == 206
        and str(video_range.get("mimeType") or "").lower().startswith("video/")
        and ui_evidence["playerReady"] is True
        and ui_evidence["playerError"] is False
        and ui_evidence["nativeFirstFrame"] is True
        and ui_evidence["nativeSeekSettled"] is True
        and ui_evidence["nativeEvidenceFromPhysicalAndroidDevice"] is True
        and ui_evidence["physicalIosPatrolPassed"] is True
        and bool(ui_evidence["qoeReadbackPath"])
        and bool(ui_evidence["perfettoTracePath"])
        and bool(ui_evidence["perfettoSummaryPath"])
    )
    return {
        "schema": "runtime-media-video-playback-t4-report",
        "scenario": "runtime_media.video_playback_t4",
        "status": "passed" if is_passed else "failed",
        "dryRun": dry_run,
        "startedAt": started_at,
        "endedAt": ended_at,
        "environment": {
            "env": env_name,
            "target": target_name,
            "rolloutStage": (
                os.environ.get("PROD_ROLLOUT_STAGE", "").strip()
                if target_name == "prod-hosted"
                else "local"
            ),
            "mediaVideoBaseUrl": str(public_bases.get("mediaVideo") or "").rstrip("/"),
            "commitSha": _current_commit_sha(),
            "configHash": _runtime_media_config_hash(target_name),
        },
        "media": {
            "publicSliceKey": public_slice_key,
            **media_identity,
        },
        "post": {
            "postId": post_id,
        },
        "serviceEvidence": service_evidence,
        "uiEvidence": ui_evidence,
    }


def _seeded_media_surface_profile_command(
    env_name: str,
    target_name: str,
) -> dict[str, Any] | None:
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        return None
    target = get_target(load_environment_topology(), target_name)
    runtime_env = str(target.get("env") or env_name or "")
    if runtime_env not in {"alpha", "beta", "gamma", "prod"}:
        return None
    return {
        "name": "seeded-media-surface",
        "argv": [
            "python3",
            "quwoquan_ops/gate/verify_alpha_media_fixture_surface.py",
            "--env",
            runtime_env,
            "--target",
            target_name,
        ],
    }


def _environment_page_smoke_profile_command(
    env_name: str,
    target_name: str,
    report_dir: Path | None,
    *,
    suite_name: str = "environment-page-smoke",
    patrol_target: str = VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
    remote_api_evidence_report: Path | None = None,
) -> dict[str, Any] | None:
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}:
        return None
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    required_bases = {
        "api",
        "productOps",
        "mediaAvatar",
        "mediaImage",
        "mediaVideo",
        "mediaUpload",
    }
    if not required_bases.issubset(public_bases):
        return None
    runtime_env = str(target.get("env") or env_name or "alpha")
    if target_name in {"prod-sim", "prod-hosted"}:
        runtime_env = "prod"
    playback_canary = target.get("playbackCanary")
    configured_canary_work_id = (
        str(playback_canary.get("workId") or "").strip()
        if isinstance(playback_canary, dict)
        else ""
    )
    canary_work_id_env = (
        str(playback_canary.get("workIdEnv") or "").strip()
        if isinstance(playback_canary, dict)
        else ""
    ) or "VIDEO_PLAYBACK_CANARY_WORK_ID"
    video_playback_canary_work_id = (
        configured_canary_work_id
        or os.environ.get(canary_work_id_env, "").strip()
    )
    token = "" if target_name == "gamma-local" else _resolve_test_auth_token(runtime_env)
    smoke_report = (
        report_dir / suite_name / "report.json"
        if report_dir is not None
        else env_runs_root(env_name)
        / "device-matrix"
        / suite_name
        / f"{target_name}.json"
    )
    argv = [
        "python3",
        "quwoquan_ops/cli/smoke/run_environment_patrol_smoke.py",
        "--report",
        str(smoke_report),
        "--env-name",
        "local-gamma" if target_name == "gamma-local" else target_name,
        "--runtime-env",
        runtime_env,
        "--api-contract-env",
        runtime_env,
        "--gateway-base-url",
        str(public_bases["api"]),
        "--product-ops-base-url",
        str(public_bases["productOps"]),
        "--media-avatar-base-url",
        str(public_bases["mediaAvatar"]),
        "--media-image-base-url",
        str(public_bases["mediaImage"]),
        "--media-video-base-url",
        str(public_bases["mediaVideo"]),
        "--media-upload-base-url",
        str(public_bases["mediaUpload"]),
        "--rtc-media-connection-url",
        str(public_bases["rtc"]),
        "--target",
        patrol_target,
    ]
    if remote_api_evidence_report is not None:
        argv.extend(
            (
                "--remote-api-evidence-report",
                str(remote_api_evidence_report),
            )
        )
    if patrol_target.endswith(
        "test/user_acceptance/patrol/environment/"
        "video_playback_canary__user_acceptance_test.dart"
    ):
        argv.extend(
            (
                "--video-playback-canary-work-id",
                video_playback_canary_work_id,
            )
        )
    platform = os.environ.get("STACKCTL_PAGE_SMOKE_PLATFORM", "").strip()
    if platform:
        argv.extend(["--platform", platform])
    device_id = os.environ.get("STACKCTL_PAGE_SMOKE_DEVICE_ID", "").strip()
    if device_id:
        argv.extend(["--device-id", device_id])
    if os.environ.get("STACKCTL_PAGE_SMOKE_DRY_RUN", "").strip() in {"1", "true", "yes"}:
        argv.append("--dry-run")
    command_env: dict[str, str] = {}
    if target_name != "gamma-local":
        if token:
            command_env["TEST_AUTH_TOKEN"] = token
        for key in (
            "TEST_REFRESH_TOKEN",
            "APP_CURRENT_OWNER_ID",
            "APP_CURRENT_SUB_ACCOUNT_ID",
        ):
            value = os.environ.get(key, "").strip()
            if value:
                command_env[key] = value
    command = {
        "name": f"{target_name}-{suite_name}",
        "argv": argv,
        "cwd": ROOT,
        "blocking": True,
        "reportPath": relpath(smoke_report),
    }
    if command_env:
        command["env"] = command_env
    return command


def _content_release_uat_command(
    *,
    target_name: str,
    release_uat_cases: Path,
    platform: str,
    device_ids: list[str],
    report_dir: Path,
) -> dict[str, Any]:
    """Build the release-bound Patrol command from the canonical environment topology."""
    command = _environment_page_smoke_profile_command(
        "gamma",
        target_name,
        report_dir,
    )
    if command is None:
        raise ValueError(f"content UAT topology is incomplete for {target_name}")
    argv = list(command["argv"])
    target_index = argv.index("--target") + 1
    argv[target_index] = RELEASE_HOMEPAGE_UAT_TEST_TARGET
    argv.extend(("--release-uat-cases", str(release_uat_cases), "--platform", platform))
    for device_id in device_ids:
        argv.extend(("--device-id", device_id))
    command["name"] = f"{target_name}-content-release-uat"
    command["argv"] = argv
    return command


def fetch_url(
    url: str,
    timeout: float = 6.0,
    *,
    retry_attempts: int = 2,
    retry_sleep_seconds: float = 2.0,
    headers: dict[str, str] | None = None,
    resolve_host: str = "",
) -> tuple[bool, int | None, str, str]:
    retry_markers = (
        "timed out",
        "Remote end closed connection without response",
        "Connection reset",
        "Connection closed",
        "UNEXPECTED_EOF_WHILE_READING",
        "EOF occurred in violation of protocol",
    )
    total_attempts = max(1, retry_attempts)
    for attempt in range(1, total_attempts + 1):
        try:
            request = urllib.request.Request(url, headers=headers or {})
            with _temporary_host_resolution(url, resolve_host):
                if resolve_host:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({}),
                        urllib.request.HTTPSHandler(context=ssl._create_unverified_context()),
                    )
                    response = opener.open(request, timeout=timeout)
                else:
                    response = urllib.request.urlopen(
                        request,
                        timeout=timeout,
                        context=ssl._create_unverified_context(),
                    )
            with response:
                body = response.read().decode("utf-8", errors="replace")
                return (
                    True,
                    int(response.status),
                    body[:500],
                    str(response.headers.get("Content-Type") or ""),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return False, int(exc.code), body[:500], str(exc.headers.get("Content-Type") or "")
        except Exception as exc:
            if attempt >= total_attempts or not _is_retryable_fetch_error(
                exc, retry_markers
            ):
                return False, None, str(exc), ""
            time.sleep(max(0.0, retry_sleep_seconds) * attempt)
    return False, None, "unknown fetch failure", ""


def _is_retryable_fetch_error(exc: Exception, retry_markers: tuple[str, ...]) -> bool:
    if isinstance(
        exc,
        (
            TimeoutError,
            ConnectionAbortedError,
            ConnectionRefusedError,
            ConnectionResetError,
        ),
    ):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(
            reason,
            (
                TimeoutError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                ConnectionResetError,
            ),
        ):
            return True
    return any(marker in str(exc) for marker in retry_markers)


@contextlib.contextmanager
def _temporary_host_resolution(url: str, resolve_host: str):
    """Connect a local public host to loopback while retaining its TLS SNI name."""
    expected_host = urllib.parse.urlparse(url).hostname or ""
    if not resolve_host or not expected_host:
        yield
        return

    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host: str | bytes | None, *args: Any, **kwargs: Any) -> Any:
        if host == expected_host:
            return original_getaddrinfo(resolve_host, *args, **kwargs)
        return original_getaddrinfo(host, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    try:
        yield
    finally:
        socket.getaddrinfo = original_getaddrinfo


def _local_public_connect_host(
    topology: dict[str, Any],
    target_name: str,
    url: str,
) -> str:
    target = get_target(topology, target_name)
    if str(target.get("backend") or "").strip() != "local":
        return ""
    hostname = urllib.parse.urlparse(url).hostname or ""
    public_bases = target.get("publicBases") or {}
    public_hosts = {
        urllib.parse.urlparse(str(base)).hostname
        for base in public_bases.values()
        if urllib.parse.urlparse(str(base)).hostname
    }
    return "127.0.0.1" if hostname in public_hosts else ""


def _content_release_public_ready_attempts(target: dict[str, Any]) -> int:
    data_release = target.get("dataRelease")
    if not isinstance(data_release, dict):
        raise RuntimeError("GATE_BLOCK: content release target has no dataRelease policy")
    value = data_release.get("publicReadyTimeoutSeconds")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RuntimeError(
            "GATE_BLOCK: dataRelease.publicReadyTimeoutSeconds must be a positive integer"
        )
    return value


def _read_json_payload(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return load_json_yaml(path)
    except Exception:  # noqa: BLE001
        return None


def _resolve_test_auth_token(env_name: str) -> str:
    token_envs = {
        "alpha": ("ALPHA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "beta": ("BETA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "gamma": ("GAMMA_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
        "prod": ("PROD_TEST_AUTH_TOKEN", "TEST_AUTH_TOKEN"),
    }
    for key in token_envs.get(env_name, ("TEST_AUTH_TOKEN",)):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _run_script_probe(
    *,
    name: str,
    scope: str,
    argv: list[str],
    report_file: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[dict[str, Any], str, list[str]]:
    result = run(argv, env=env)
    output = "\n".join(filter(None, [result.stdout, result.stderr])).strip()
    report_payload = _read_json_payload(report_file) if report_file else None
    report_status = ""
    report_findings: list[str] = []
    preview = output[:500]
    if isinstance(report_payload, dict):
        report_status = str(report_payload.get("status", "")).strip().lower()
        preview = str(
            report_payload.get("blockingReason")
            or report_payload.get("summary")
            or report_payload.get("status")
            or preview
        )[:500]
        for item in ensure_list(report_payload.get("findings")):
            if isinstance(item, str) and item.strip():
                report_findings.append(item.strip())
        blocking_reason = str(report_payload.get("blockingReason", "")).strip()
        if blocking_reason:
            report_findings.append(blocking_reason)
    ok = result.returncode == 0 and report_status not in {"failed", "gate_block", "error"}
    if not ok and not report_findings:
        report_findings.append(
            f"{scope}/{name} failed: exit={result.returncode} {argv[-1] if argv else name}"
        )
    payload = {
        "name": name,
        "scope": scope,
        "type": "script",
        "argv": argv,
        "ok": ok,
        "statusCode": result.returncode,
        "bodyPreview": preview,
        "skipped": False,
        "reportPath": relpath(report_file) if report_file else "",
    }
    return payload, output, report_findings


def _run_environment_integration_probe(
    topology: dict[str, Any],
    target_name: str,
    report_dir: Path,
) -> tuple[dict[str, Any], str, list[str]]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    public_bases = target.get("publicBases") or {}
    report_file = report_dir / "integration-probe.json"
    argv = [
        "python3",
        "quwoquan_ops/cli/probes/run_environment_integration_probe.py",
        "--env",
        env_name,
        "--base-url",
        str(public_bases["api"]),
        "--report",
        str(report_file),
    ]
    if target_name == "prod-hosted":
        argv.extend(
            [
                "--mode",
                "post-deploy",
                "--request-timeout-seconds",
                "20",
                "--retry-attempts",
                "3",
                "--retry-sleep-seconds",
                "3",
            ]
        )
    product_ops = str(public_bases.get("productOps") or "").strip()
    if product_ops:
        argv.extend(["--product-ops-base-url", product_ops])
    media_image = str(public_bases.get("mediaImage") or "").strip()
    if media_image:
        argv.extend(["--media-image-base-url", media_image])
    token = _resolve_test_auth_token(env_name)
    if env_name in {"beta", "gamma"} and not token:
        try:
            session_kwargs: dict[str, Any] = {
                "environment": env_name,
                "target_name": target_name,
            }
            deployment_work_root = resolve_running_local_deployment_work_root(
                target_name
            )
            if deployment_work_root is not None:
                session_kwargs["deployment_work_root"] = deployment_work_root
            token = open_local_acceptance_session(
                str(public_bases["api"]),
                **session_kwargs,
            ).access_token
        except (RuntimeError, ValueError) as exc:
            finding = f"{target_name} integration auth failed: {exc}"
            return (
                {
                    "name": "integration-readonly",
                    "scope": "full",
                    "type": "script",
                    "argv": argv,
                    "ok": False,
                    "statusCode": 1,
                    "bodyPreview": finding,
                    "skipped": False,
                    "reportPath": relpath(report_file),
                },
                finding,
                [finding],
            )
    probe_env: dict[str, str] | None = None
    if token:
        probe_env = {"TEST_AUTH_TOKEN": token}
        if env_name == "gamma":
            probe_env["GAMMA_TEST_AUTH_TOKEN"] = token
        elif env_name == "beta":
            probe_env["BETA_TEST_AUTH_TOKEN"] = token
        elif env_name == "prod":
            probe_env["PROD_TEST_AUTH_TOKEN"] = token
    return _run_script_probe(
        name="integration-readonly",
        scope="full",
        argv=argv,
        report_file=report_file,
        env=probe_env,
    )


def _script_probe_plan_for_target(
    topology: dict[str, Any],
    target_name: str,
) -> list[dict[str, Any]]:
    target = get_target(topology, target_name)
    if target_name == "alpha-local":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    if target_name == "beta-local":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    if target_name == "prod-sim":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    if target_name == "prod-hosted":
        return [
            {"name": "integration-readonly", "kind": "readonly-http"},
            {"name": "release-state", "kind": "rollout-state"},
        ]
    if str(target.get("env")) == "gamma" and target_name == "gamma-local":
        return [{"name": "integration-readonly", "kind": "readonly-http"}]
    return []


def _health_request_policy(target_name: str, scope: str) -> dict[str, float | int]:
    policy: dict[str, float | int] = {
        "timeoutSeconds": 6.0,
        "retryAttempts": 2,
        "retrySleepSeconds": 2.0,
    }
    if target_name == "prod-hosted":
        policy.update(
            {
                "timeoutSeconds": 15.0 if scope == "edge" else 20.0,
                "retryAttempts": 3,
                "retrySleepSeconds": 3.0,
            }
        )
    return policy


def _script_probes_for_target(
    topology: dict[str, Any],
    target_name: str,
    scope: str,
    report_dir: Path,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]], list[str]]:
    if scope != "full":
        return [], [], []
    statuses: list[dict[str, Any]] = []
    stdout_sections: list[tuple[str, str]] = []
    findings: list[str] = []

    if target_name in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}:
        status, output, probe_findings = _run_environment_integration_probe(
            topology,
            target_name,
            report_dir,
        )
        statuses.append(status)
        stdout_sections.append((status["name"], output))
        findings.extend(probe_findings)
    return statuses, stdout_sections, findings


def _release_state_dir() -> Path:
    # 这里只保存 hosted release ledger 的本机 readback cache；它绝不能作为发布真相。
    # 真实 ledger/receipt 只能经 prod service-plane SSH projection 写入并读回。
    configured = os.environ.get("QWQ_PROD_RELEASE_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return target_process_dir("prod-hosted") / "release-state"


def _load_release_state(service: str = PROD_RELEASE_UNIT) -> dict[str, str]:
    return _load_release_state_path(_release_state_dir() / f"{service}.state")


def _load_release_state_path(state_path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    if not state_path.exists():
        return payload
    for raw in state_path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        payload[key.strip()] = value.strip()
    return payload


def _release_stage_from_state(state: dict[str, str]) -> str:
    if state.get("schema") != "prod-release-ledger":
        raise RuntimeError("release ledger schema is not canonical")
    stage = state.get("stage", "").strip()
    if stage:
        return stage
    raise RuntimeError("release ledger missing canonical stage")


def _validate_release_transition(
    state: dict[str, str],
    *,
    from_image: str,
    to_image: str,
    from_config: str,
    to_config: str,
    stage: str,
    manifest_digest: str,
) -> tuple[str, int]:
    if not state:
        if stage != "gray-initial":
            raise RuntimeError("release ledger must start at gray-initial")
        return "advance", 0

    generation = int(state.get("generation") or 0)
    current_stage = _release_stage_from_state(state)
    same_target = (
        state.get("from_image") == from_image
        and state.get("to_image") == to_image
        and state.get("from_config") == from_config
        and state.get("to_config") == to_config
    )
    if same_target:
        if state.get("manifest_digest") and state.get("manifest_digest") != manifest_digest:
            raise RuntimeError("release ledger manifest digest drift")
        if current_stage == stage:
            decision = state.get("decision", "continue")
            if decision == "continue":
                return "replay", generation
            if decision in {"pause", "rollback_failed"}:
                return "reevaluate", generation
            raise RuntimeError(
                f"release ledger stage is not replayable with decision={decision}"
            )
        if state.get("decision", "continue") != "continue":
            raise RuntimeError("paused or failed release cannot advance to the next stage")
        expected_next = {"gray-initial": "carry-on", "carry-on": "full"}.get(current_stage)
        if expected_next != stage:
            raise RuntimeError(
                f"release ledger stage CAS conflict: {current_stage} cannot advance to {stage}"
            )
        return "advance", generation

    if stage != "gray-initial":
        raise RuntimeError("new release target must start at gray-initial")
    if state.get("to_image") != from_image or state.get("to_config") != from_config:
        raise RuntimeError(
            "release ledger base CAS conflict: requested from image/config do not match current stable target"
        )
    if current_stage != "full" or state.get("decision", "continue") not in {
        "continue",
        "rolled_back",
    }:
        raise RuntimeError("previous release is not in a stable full state")
    return "advance", generation


@contextlib.contextmanager
def _prod_release_lock() -> Any:
    lock_path = _release_state_dir() / ".global-deploy.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner = f"{os.getpid()}-{time.time_ns()}"
    if lock_path.is_dir():
        raise RuntimeError(
            "release lock path must be a file; inspect and remove the directory: "
            f"{lock_path}"
        )
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.seek(0)
            holder = handle.read().strip() or "unknown"
            raise RuntimeError(
                f"prod release lock is held by {holder}: {lock_path}"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(owner + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _local_stack_operation_lock(target_name: str) -> Any:
    """为本机所有本地环境操作保留唯一的 Compose/package 临界区。"""
    target = str(target_name).strip()
    if target not in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        raise ValueError(f"local stack operation lock does not support {target!r}")
    lock_path = local_runtime_operation_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    owner = f"pid={os.getpid()} target={target} startedAt={utc_now()}"
    with lock_path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            handle.seek(0)
            holder = handle.read().strip() or "unknown"
            raise RuntimeError(
                f"local stack operation is already running: {holder}"
            ) from error
        handle.seek(0)
        handle.truncate()
        handle.write(owner + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        try:
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _required_release_candidate_digests(
    args: argparse.Namespace,
    manifest: dict[str, Any],
) -> dict[str, str]:
    """Derive and validate the RTC candidate tuple attested by hosted receipts."""
    graph_path = ROOT / "quwoquan_service/generated/contract_graph.json"
    if not graph_path.is_file():
        raise RuntimeError("hosted release receipt requires generated ContractGraph")
    graph_digest = "sha256:" + hashlib.sha256(graph_path.read_bytes()).hexdigest()
    images = manifest.get("images")
    rtc_image = images.get("rtc-service") if isinstance(images, dict) else None
    image_digest = str(rtc_image.get("digest") or "") if isinstance(rtc_image, dict) else ""
    governance = _external_provider_governance()
    conformance = _provider_conformance()
    compiled, governance_issues = governance.load_and_compile()
    if governance_issues:
        raise RuntimeError(
            "hosted release receipt provider binding is invalid: "
            + "; ".join(issue.render() for issue in governance_issues)
        )
    prod_bindings = (compiled.get("selectedBindings") or {}).get("prod") or {}
    rtc_binding = prod_bindings.get("rtc.room.transport")
    if not isinstance(rtc_binding, dict):
        raise RuntimeError("hosted release receipt cannot resolve prod RTC binding")
    binding_roots = conformance.compiled_capability_binding_roots(
        compiled,
        capability_id="rtc.room.transport",
    )
    config_digest = conformance.binding_config_digest(
        rtc_binding,
        binding_roots,
    )
    registry = governance.load_registry()
    livekit_adapter = next(
        (
            item
            for item in registry.get("adapters", [])
            if isinstance(item, dict)
            and item.get("adapter_id") == "infra.livekit_sfu"
        ),
        None,
    )
    if not isinstance(livekit_adapter, dict) or not str(
        livekit_adapter.get("implementation_path") or ""
    ):
        raise RuntimeError("hosted release receipt cannot resolve infra.livekit_sfu")
    implementation_path = ROOT / str(livekit_adapter["implementation_path"])
    adapter_digest = conformance.implementation_digest(implementation_path)
    fields = {
        "imageDigest": image_digest,
        "configDigest": config_digest,
        "contractGraphDigest": graph_digest,
        "adapterDigest": str(adapter_digest or ""),
    }
    invalid = [
        name
        for name, value in fields.items()
        if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
    ]
    if invalid:
        raise RuntimeError(
            "hosted release receipt cannot derive sha256 candidate digests for "
            + ", ".join(invalid)
        )
    requested = {
        "imageDigest": str(getattr(args, "release_image_digest", "") or "").strip(),
        "configDigest": str(getattr(args, "release_config_digest", "") or "").strip(),
        "contractGraphDigest": str(
            getattr(args, "contract_graph_digest", "") or ""
        ).strip(),
        "adapterDigest": str(getattr(args, "adapter_digest", "") or "").strip(),
    }
    mismatched = [
        name
        for name, value in requested.items()
        if value and value != fields[name]
    ]
    if mismatched:
        raise RuntimeError(
            "hosted release receipt candidate digest mismatch for "
            + ", ".join(mismatched)
        )
    return fields


def _archive_release_artifact(manifest_path: Path, manifest_digest: str) -> Path:
    archive_root = _release_state_dir() / "artifacts"
    archive_root.mkdir(parents=True, exist_ok=True)
    digest_id = manifest_digest.removeprefix("sha256:")
    if re.fullmatch(r"[0-9a-f]{64}", digest_id) is None:
        raise RuntimeError("release artifact digest is invalid")
    target = archive_root / digest_id
    source = manifest_path.parent
    if target.exists():
        archived_manifest = target / "manifest.json"
        if not archived_manifest.is_file():
            raise RuntimeError(f"release artifact archive is incomplete: {target}")
        archived = json.loads(archived_manifest.read_text(encoding="utf-8"))
        declared = str(archived.get("manifestDigest") or "") if isinstance(archived, dict) else ""
        if declared != manifest_digest:
            raise RuntimeError(f"release artifact archive digest collision: {target}")
        return target
    temporary = archive_root / f".{digest_id}.{os.getpid()}.tmp"
    shutil.copytree(source, temporary)
    os.replace(temporary, target)
    archives = sorted(
        (path for path in archive_root.iterdir() if path.is_dir() and not path.name.startswith(".")),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for stale in archives[2:]:
        shutil.rmtree(stale)
    return target


def _fetch_hosted_release_ledger_projection(
    service: str,
    *,
    allow_uninitialized: bool,
) -> tuple[dict[str, str], Path | None]:
    """Fetch a digest-verified state/receipt pair from the hosted authority."""
    readback = _run_hosted_release_ledger(service=service, action="fetch")
    state = readback["state"]
    receipt = readback["receipt"]
    if not state:
        if allow_uninitialized:
            return {}, None
        raise RuntimeError("hosted release ledger is uninitialized")
    return _cache_hosted_release_readback(service, state, receipt)


def _sync_release_ledger_projection(
    service: str,
    receipt_id: str,
) -> Path:
    """Read back an already committed hosted receipt; never publish local state."""
    hosted_state, hosted_receipt_path = _fetch_hosted_release_ledger_projection(
        service,
        allow_uninitialized=False,
    )
    if hosted_receipt_path is None:
        raise RuntimeError("hosted release receipt readback is missing")
    if hosted_state.get("receipt_id") != receipt_id:
        raise RuntimeError("hosted release ledger readback does not match committed transition")
    return hosted_receipt_path


def _hosted_receipt_id(receipt: dict[str, Any]) -> str:
    unsigned = dict(receipt)
    unsigned.pop("receiptId", None)
    return hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _validate_hosted_release_readback(
    payload: object,
    *,
    service: str,
) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "authority", "state", "receipt", "receiptRef"}
        or payload.get("schema") != "prod-hosted-release-readback"
        or payload.get("authority") != "prod-hosted-service-plane"
        or not isinstance(payload.get("state"), dict)
        or not isinstance(payload.get("receipt"), dict)
    ):
        raise RuntimeError("hosted release ledger returned an invalid readback")
    state = payload["state"]
    receipt = payload["receipt"]
    if not state and not receipt and payload.get("receiptRef") == "":
        return payload
    receipt_id = str(receipt.get("receiptId") or "")
    if (
        state.get("schema") != "prod-release-ledger"
        or state.get("authority") != "prod-hosted-service-plane"
        or state.get("service") != service
        or receipt.get("schema") != "prod-hosted-release-receipt"
        or receipt.get("authority") != "prod-hosted-service-plane"
        or receipt.get("service") != service
        or re.fullmatch(r"[0-9a-f]{64}", receipt_id) is None
        or receipt_id != _hosted_receipt_id(receipt)
        or state.get("receipt_id") != receipt_id
        or payload.get("receiptRef") != f"receipt:hosted:{receipt_id}"
        or str(receipt.get("committedGeneration")) != state.get("generation")
        or receipt.get("manifestDigest") != state.get("manifest_digest")
        or receipt.get("imageDigest") != state.get("image_digest")
        or receipt.get("configDigest") != state.get("config_digest")
        or receipt.get("contractGraphDigest") != state.get("contract_graph_digest")
        or receipt.get("adapterDigest") != state.get("adapter_digest")
        or receipt.get("rollbackOutcome") != state.get("rollback_outcome")
    ):
        raise RuntimeError("hosted release ledger receipt digest or state binding is invalid")
    return payload


def _run_hosted_release_ledger(
    *,
    service: str,
    action: str,
    request: dict[str, Any] | None = None,
    receipt_id: str = "",
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="quwoquan-hosted-release-ledger-") as temporary:
        root = Path(temporary)
        output_path = root / "readback.json"
        command = [
            "bash",
            "quwoquan_ops/cli/prod/sync_prod_plane_stack.sh",
            "--plane",
            "service",
            "--operation",
            f"release-ledger-{action}",
            "--service",
            service,
            "--output-path",
            str(output_path),
        ]
        if action == "commit":
            if request is None:
                raise RuntimeError("hosted release ledger commit request is missing")
            request_path = root / "request.json"
            write_json(request_path, request)
            command.extend(("--request-path", str(request_path)))
        elif action == "receipt":
            command.extend(("--receipt-id", receipt_id))
        result = run(command)
        if result.returncode != 0:
            raise RuntimeError(
                f"hosted release ledger {action} failed: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("hosted release ledger readback is not valid JSON") from error
    if action == "receipt":
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema", "authority", "receipt", "receiptRef"}
            or payload.get("schema") != "prod-hosted-release-receipt-readback"
            or payload.get("authority") != "prod-hosted-service-plane"
            or not isinstance(payload.get("receipt"), dict)
        ):
            raise RuntimeError("hosted release receipt returned an invalid readback")
        receipt = payload["receipt"]
        actual_id = str(receipt.get("receiptId") or "")
        if (
            actual_id != receipt_id
            or actual_id != _hosted_receipt_id(receipt)
            or payload.get("receiptRef") != f"receipt:hosted:{receipt_id}"
            or receipt.get("schema") != "prod-hosted-release-receipt"
            or receipt.get("authority") != "prod-hosted-service-plane"
            or receipt.get("service") != service
        ):
            raise RuntimeError("hosted release receipt digest is invalid")
        return payload
    return _validate_hosted_release_readback(payload, service=service)


def _cache_hosted_release_readback(
    service: str,
    state: dict[str, str],
    receipt: dict[str, Any],
) -> tuple[dict[str, str], Path]:
    """Persist a disposable local copy after hosted digest verification."""
    cache_dir = _release_state_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_path = cache_dir / f"{service}.state"
    state_path.write_text(
        "\n".join(f"{key}={value}" for key, value in state.items()) + "\n",
        encoding="utf-8",
    )
    receipt_id = str(receipt["receiptId"])
    receipt_path = cache_dir / "receipts" / f"{receipt_id}.json"
    write_json(receipt_path, receipt)
    return state, receipt_path


def _release_check_receipts(
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "name": f"post-check-{index}",
            "status": "passed"
            if int(item.get("exitCode", 1) or 0) == 0
            else "failed",
            "receiptDigest": "sha256:"
            + hashlib.sha256(
                json.dumps(
                    item,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
        }
        for index, item in enumerate(checks, start=1)
    ]


def _commit_hosted_release_transition(
    *,
    service: str,
    from_image: str,
    to_image: str,
    from_config: str,
    to_config: str,
    step: str,
    stage: str,
    decision: str,
    manifest_digest: str,
    expected_generation: int,
    receipt_id: str,
    slo_readback: dict[str, Any] | None,
    candidate_digests: dict[str, str],
    last_good_target: dict[str, str],
    post_deploy_checks: list[dict[str, Any]],
    rollback_outcome: str,
) -> tuple[dict[str, str], Path]:
    del receipt_id
    request = {
        "schema": "prod-hosted-release-transition-request",
        "service": service,
        "fromImage": from_image,
        "toImage": to_image,
        "fromConfig": from_config,
        "toConfig": to_config,
        "step": step,
        "stage": stage,
        "decision": decision,
        "rollbackOutcome": rollback_outcome,
        "manifestDigest": manifest_digest,
        "imageDigest": candidate_digests["imageDigest"],
        "configDigest": candidate_digests["configDigest"],
        "contractGraphDigest": candidate_digests["contractGraphDigest"],
        "adapterDigest": candidate_digests["adapterDigest"],
        "expectedGeneration": expected_generation,
        "sloReadback": slo_readback or {},
        "postChecks": _release_check_receipts(post_deploy_checks),
        "lastGoodTarget": last_good_target,
        "verifiedAt": utc_now(),
    }
    committed = _run_hosted_release_ledger(
        service=service,
        action="commit",
        request=request,
    )
    fetched = _run_hosted_release_ledger(service=service, action="fetch")
    if (
        committed["receiptRef"] != fetched["receiptRef"]
        or committed["receipt"] != fetched["receipt"]
        or committed["state"] != fetched["state"]
    ):
        raise RuntimeError("hosted release ledger commit/readback mismatch")
    return _cache_hosted_release_readback(
        service,
        fetched["state"],
        fetched["receipt"],
    )


def socket_probe(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def print_result(args: argparse.Namespace, payload: dict[str, Any]) -> int:
    if args.output_format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(payload["summary"])
        report_dir = payload.get("reportDir")
        if report_dir:
            print(f"report: {report_dir}")
        for line in payload.get("details", []):
            print(f"- {line}")
    return int(payload.get("exitCode", 0))


def _legal_static_command(
    subcommand: str,
    env_name: str,
    *,
    target: str = "",
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    cmd = [
        "python3",
        "quwoquan_ops/cli/legal_static.py",
        subcommand,
        "--env",
        env_name,
    ]
    if target:
        cmd.extend(["--target", target])
    result = run(cmd, env={"QWQ_DEPLOY_TARGET": target} if target else None)
    payload: dict[str, Any] = {}
    if result.stdout.strip():
        try:
            loaded = json.loads(result.stdout)
            if isinstance(loaded, dict):
                payload = loaded
        except json.JSONDecodeError:
            payload = {}
    payload.setdefault("argv", cmd)
    payload.setdefault("exitCode", result.returncode)
    return result, payload


def _command_package_legal_static(args: argparse.Namespace) -> dict[str, Any]:
    env_name = args.env
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    if args.service or args.include_services:
        timing = _finish_timing(started_monotonic, started_at)
        details = ["legal-static packages cannot include service packages"]
        _write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="failed",
            summary=f"stackctl legal-static package failed for {env_name}",
            details=details,
            extra={"env": env_name, "kind": "legal-static"},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl legal-static package failed for {env_name}",
            "details": details,
            "reportDir": relpath(report_dir),
            **timing,
        }

    result, legal_payload = _legal_static_command(
        "package",
        env_name,
        target=target_name,
    )
    timing = _finish_timing(started_monotonic, started_at)
    status = "ok" if result.returncode == 0 else "failed"
    details = []
    if result.returncode == 0:
        details.append(f"legal-static package ready: {legal_payload.get('packageDir', '')}")
        if legal_payload.get("currentPointer"):
            details.append(f"legal-static current pointer: {legal_payload['currentPointer']}")
    else:
        issues = legal_payload.get("issues") if isinstance(legal_payload.get("issues"), list) else []
        details.extend(str(issue) for issue in issues)
        if not details:
            details.append(result.stderr.strip() or result.stdout.strip() or "legal-static package failed")
    report = {
        "status": status,
        "command": "package",
        "kind": "legal-static",
        "env": env_name,
        "target": target_name,
        "timestamp": utc_now(),
        "step": {
            "name": "legal-static-package",
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "payload": legal_payload,
        },
        **timing,
    }
    write_json(report_dir / "report.json", report)
    _write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status=status,
        summary=(
            f"stackctl legal-static package completed for {env_name}"
            if status == "ok"
            else f"stackctl legal-static package failed for {env_name}"
        ),
        details=details,
        extra={"env": env_name, "kind": "legal-static"},
        timing=timing,
    )
    _write_stdout_markdown(
        report_dir,
        [("legal-static-package", "\n".join(filter(None, [result.stdout, result.stderr])))],
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            f"stackctl legal-static package completed for {env_name}"
            if status == "ok"
            else f"stackctl legal-static package failed for {env_name}"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def _command_package_ops_portal(args: argparse.Namespace) -> dict[str, Any]:
    """通过 stackctl 构建 Portal 包，并补齐可复算的 package provenance。"""
    env_name = args.env
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    details: list[str] = []
    if env_name != "prod" or target_name != "prod-hosted":
        details.append("ops-portal package is supported only for prod/prod-hosted")
    if args.service or args.include_services:
        details.append("ops-portal packages cannot include service packages")
    version = str(getattr(args, "version", "") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", version):
        details.append("ops-portal package requires a safe --version")
    oidc_values = {
        "issuer": str(
            getattr(args, "oidc_issuer", "") or os.environ.get("PROD_OPS_OIDC_ISSUER", "")
        ).strip(),
        "clientId": str(
            getattr(args, "oidc_client_id", "")
            or os.environ.get("PROD_OPS_OIDC_CLIENT_ID", "")
        ).strip(),
        "audience": str(
            getattr(args, "oidc_audience", "")
            or os.environ.get("PROD_OPS_OIDC_AUDIENCE", "")
        ).strip(),
        "scope": str(
            getattr(args, "oidc_scope", "") or os.environ.get("PROD_OPS_OIDC_SCOPE", "")
        ).strip(),
    }
    missing_oidc = [name for name, value in oidc_values.items() if not value]
    if missing_oidc:
        details.append(
            "ops-portal package requires OIDC values: " + ", ".join(missing_oidc)
        )
    if details:
        timing = _finish_timing(started_monotonic, started_at)
        _write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="failed",
            summary=f"stackctl ops-portal package failed for {env_name}",
            details=details,
            extra={"env": env_name, "kind": "ops-portal"},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl ops-portal package failed for {env_name}",
            "details": details,
            "reportDir": relpath(report_dir),
            **timing,
        }

    command = [
        "python3",
        "quwoquan_ops/cli/prod/build_portal_release.py",
        "--version",
        version,
        "--oidc-issuer",
        oidc_values["issuer"],
        "--oidc-client-id",
        oidc_values["clientId"],
        "--oidc-audience",
        oidc_values["audience"],
        "--oidc-scope",
        oidc_values["scope"],
        "--target",
        target_name,
    ]
    for flag, attribute in (
        ("--ops-base-url", "ops_base_url"),
        ("--content-base-url", "content_base_url"),
        ("--entity-base-url", "entity_base_url"),
    ):
        value = str(getattr(args, attribute, "") or "").strip()
        if value:
            command.extend((flag, value))
    if getattr(args, "skip_install", False):
        command.append("--skip-install")

    result = run(command, env={"QWQ_DEPLOY_TARGET": target_name})
    package_dir = portal_deployment_package_dir(env_name, target=target_name) / version
    if result.returncode == 0:
        manifest_path = package_dir / "manifest.json"
        dist_dir = package_dir / "dist"
        if not manifest_path.is_file() or not dist_dir.is_dir():
            result = subprocess.CompletedProcess(
                command,
                1,
                stdout=result.stdout,
                stderr=(
                    "ops-portal builder did not produce manifest.json and dist/: "
                    f"{package_dir}"
                ),
            )
        else:
            revision_result = run(["git", "rev-parse", "HEAD"])
            revision = revision_result.stdout.strip()
            if (
                revision_result.returncode != 0
                or not re.fullmatch(r"[0-9a-f]{40}", revision)
            ):
                result = subprocess.CompletedProcess(
                    command,
                    1,
                    stdout=result.stdout,
                    stderr=(
                        "ops-portal package provenance requires git revision: "
                        + (revision_result.stderr.strip() or revision_result.stdout.strip())
                    ),
                )
            else:
                provenance = {
                    "schema": "qwq.ops_portal_package.v1",
                    "packageKind": "ops-portal",
                    "environment": env_name,
                    "target": target_name,
                    "version": version,
                    "gitRevision": revision,
                    "digests": {
                        "manifest": _sha256_file(manifest_path),
                        "distTree": _sha256_tree(dist_dir),
                    },
                }
                write_json(package_dir / "provenance.json", provenance)
                details.append(f"ops-portal package ready: {relpath(package_dir)}")
    if result.returncode != 0:
        details.extend(_command_details(result))
    timing = _finish_timing(started_monotonic, started_at)
    status = "ok" if result.returncode == 0 else "failed"
    write_json(
        report_dir / "report.json",
        {
            "status": status,
            "command": "package",
            "kind": "ops-portal",
            "env": env_name,
            "target": target_name,
            "step": {
                "argv": command,
                "exitCode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            **timing,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status=status,
        summary=(
            f"stackctl ops-portal package completed for {env_name}"
            if status == "ok"
            else f"stackctl ops-portal package failed for {env_name}"
        ),
        details=details,
        extra={"env": env_name, "kind": "ops-portal"},
        timing=timing,
    )
    _write_stdout_markdown(
        report_dir,
        [("ops-portal-package", "\n".join(filter(None, [result.stdout, result.stderr])))],
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            f"stackctl ops-portal package completed for {env_name}"
            if status == "ok"
            else f"stackctl ops-portal package failed for {env_name}"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def _command_package_release_manifest(args: argparse.Namespace) -> dict[str, Any]:
    """Attach the six real component artifacts to the existing service manifest."""
    env_name = args.env
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    if env_name != "prod" or target_name != "prod-hosted":
        issues = ["release-manifest assembly requires prod/prod-hosted"]
    else:
        issues = []
    artifact_dir_value = str(getattr(args, "release_artifact_dir", "") or "").strip()
    source_values = {
        "publicWeb": str(getattr(args, "public_web_manifest", "") or "").strip(),
        "androidOfficialRelease": str(
            getattr(args, "android_release_manifest", "") or ""
        ).strip(),
        "opsPortal": str(getattr(args, "ops_portal_provenance", "") or "").strip(),
        "contractGraph": str(getattr(args, "contract_graph", "") or "").strip(),
        "providerBindings": str(
            getattr(args, "provider_bindings", "") or ""
        ).strip(),
        "testEvidence": str(getattr(args, "test_evidence", "") or "").strip(),
    }
    if not artifact_dir_value:
        issues.append("release-manifest assembly requires --release-artifact-dir")
    for artifact_id, value in source_values.items():
        if not value:
            issues.append(f"release-manifest assembly requires {artifact_id}")
    manifest: dict[str, Any] = {}
    if not issues:
        artifact_dir = Path(artifact_dir_value).expanduser().resolve()
        descriptors_dir = artifact_dir / "artifact-descriptors"
        try:
            collect_release_artifact_descriptors.collect(
                artifact_dir=artifact_dir,
                descriptors_dir=descriptors_dir,
                sources={key: Path(value) for key, value in source_values.items()},
            )
            manifest = finalize_mainline_release_artifact.finalize(
                artifact_dir,
                None,
                descriptors_dir,
            )
        except (OSError, RuntimeError, ValueError) as error:
            issues.append(str(error))
    timing = _finish_timing(started_monotonic, started_at)
    status = "ok" if not issues else ProbeOutcome.GATE_BLOCK.value
    details = issues or [
        f"releaseManifestDigest={manifest.get('manifestDigest')}",
        "artifacts=" + ",".join(sorted(_REQUIRED_RELEASE_ARTIFACTS)),
    ]
    _write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status=status,
        summary=(
            "stackctl whole-app release manifest assembled"
            if not issues
            else "stackctl whole-app release manifest is GATE_BLOCK"
        ),
        details=details,
        extra={"env": env_name, "kind": "release-manifest"},
        timing=timing,
    )
    write_json(
        report_dir / "report.json",
        {
            "command": "package",
            "kind": "release-manifest",
            "env": env_name,
            "target": target_name,
            "status": status,
            "manifestDigest": manifest.get("manifestDigest"),
            "issues": issues,
            **timing,
        },
    )
    return {
        "exitCode": 0 if not issues else 2,
        "summary": (
            "stackctl whole-app release manifest assembled"
            if not issues
            else "stackctl whole-app release manifest is GATE_BLOCK"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_package(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "kind", "runtime") == "release-manifest":
        return _command_package_release_manifest(args)
    if getattr(args, "kind", "runtime") == "legal-static":
        return _command_package_legal_static(args)
    if getattr(args, "kind", "runtime") == "ops-portal":
        return _command_package_ops_portal(args)
    if getattr(args, "kind", "runtime") == "web":
        topology = load_environment_topology()
        env_name = args.env
        target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
        target = get_target(topology, target_name)
        public_bases = target.get("publicBases") or {}
        try:
            release = package_web_official_release(
                repo_root=ROOT,
                environment=env_name,
                package_root=web_deployment_package_dir(
                    env_name,
                    target=target_name,
                ),
                public_origin=str(public_bases.get("publicWeb") or ""),
            )
        except WebOfficialReleaseError as error:
            return {
                "exitCode": 2,
                "summary": f"stackctl Web package failed for {env_name}",
                "details": [str(error)],
            }
        return {
            "exitCode": 0,
            "summary": f"stackctl Web package completed for {env_name}",
            "details": [
                f"origin: {release['publicOrigin']}",
                f"release: {release['releaseId']}",
                f"manifest: {relpath(Path(str(release['manifestPath'])))}",
                f"noindex: {release['noindex']}",
            ],
        }
    if getattr(args, "kind", "runtime") == "app-release":
        topology = load_environment_topology()
        env_name = args.env
        target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
        target = get_target(topology, target_name)
        public_bases = target.get("publicBases") or {}
        package_root = app_deployment_package_dir(env_name, target=target_name)
        if not args.apk_path:
            return {
                "exitCode": 2,
                "summary": f"stackctl app release package blocked for {env_name}",
                "details": ["--apk-path must reference a signed release APK"],
            }
        try:
            release = package_android_official_release(
                apk_path=Path(args.apk_path),
                package_root=package_root,
                public_origin=str(public_bases.get("publicWeb") or ""),
                download_origin=str(public_bases.get("appDownload") or ""),
                expected_package="com.quwoquan.quwoquan_app",
                expected_signing_certificate_sha256=os.environ.get(
                    "QWQ_ANDROID_EXPECTED_SIGNING_CERTIFICATE_SHA256", ""
                ),
                verify_remote=bool(args.verify_remote_apk),
            )
        except AndroidOfficialReleaseError as error:
            return {
                "exitCode": 2,
                "summary": f"stackctl app release package failed for {env_name}",
                "details": [str(error)],
            }
        return {
            "exitCode": 0,
            "summary": f"stackctl app release package completed for {env_name}",
            "details": [
                f"android {release['versionName']} build {release['buildNumber']}",
                f"manifest: {relpath(Path(str(release['manifestPath'])))}",
                f"remoteVerified: {release['remoteVerified']}",
            ],
        }

    topology = load_environment_topology()
    env_name = args.env
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    details: list[str] = []
    reports: list[dict[str, Any]] = []
    package_environment = {"QWQ_DEPLOY_TARGET": target_name}

    if not args.service:
        app_cmd = ["bash", "quwoquan_app/scripts/env/build_app_env_package.sh", "--env", env_name]
        app_result = run(app_cmd, env=package_environment)
        reports.append(
            {
                "name": "app-package",
                "argv": app_cmd,
                "exitCode": app_result.returncode,
                "stdout": app_result.stdout,
                "stderr": app_result.stderr,
            }
        )
        if app_result.returncode != 0:
            timing = _finish_timing(started_monotonic, started_at)
            write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
            _write_summary_bundle(
                report_dir,
                command="package",
                target=target_name,
                status="failed",
                summary=f"stackctl package failed for {env_name}",
                details=[app_result.stderr.strip() or app_result.stdout.strip()],
                extra={"env": env_name},
                timing=timing,
            )
            _write_stdout_markdown(report_dir, [("app-package", "\n".join(filter(None, [app_result.stdout, app_result.stderr])))])
            return {
                "exitCode": app_result.returncode,
                "summary": f"stackctl package failed for {env_name}",
                "details": [app_result.stderr.strip() or app_result.stdout.strip()],
                "reportDir": relpath(report_dir),
                **timing,
            }
        details.append(
            f"app package ready: {relpath(app_deployment_package_dir(env_name, target=target_name))}"
        )

    if args.include_services or args.service:
        services = [args.service] if args.service else _all_services()
        for service in services:
            svc_cmd = [
                "bash",
                "quwoquan_service/scripts/runtime/build_service_env_package.sh",
                "--service",
                service,
                "--env",
                env_name,
            ]
            svc_result = run(svc_cmd, env=package_environment)
            reports.append(
                {
                    "name": f"service-package:{service}",
                    "argv": svc_cmd,
                    "exitCode": svc_result.returncode,
                    "stdout": svc_result.stdout,
                    "stderr": svc_result.stderr,
                }
            )
            if svc_result.returncode != 0:
                timing = _finish_timing(started_monotonic, started_at)
                write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
                _write_summary_bundle(
                    report_dir,
                    command="package",
                    target=target_name,
                    status="failed",
                    summary=f"stackctl package failed for {service}/{env_name}",
                    details=[svc_result.stderr.strip() or svc_result.stdout.strip()],
                    extra={"env": env_name},
                    timing=timing,
                )
                _write_stdout_markdown(
                    report_dir,
                    [(f"service-package:{service}", "\n".join(filter(None, [svc_result.stdout, svc_result.stderr])))],
                )
                return {
                    "exitCode": svc_result.returncode,
                    "summary": f"stackctl package failed for {service}/{env_name}",
                    "details": [svc_result.stderr.strip() or svc_result.stdout.strip()],
                    "reportDir": relpath(report_dir),
                    **timing,
                }
            details.append(
                "service package ready: "
                f"{relpath(service_deployment_package_dir(env_name, service, target=target_name))}"
            )

    if env_name == "prod" and not args.service:
        try:
            materialized_config_version = _materialize_prod_release_artifact(
                target=target_name
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            timing = _finish_timing(started_monotonic, started_at)
            write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
            _write_summary_bundle(
                report_dir,
                command="package",
                target=target_name,
                status="failed",
                summary="stackctl package failed while materializing prod release artifact",
                details=[str(exc)],
                extra={"env": env_name},
                timing=timing,
            )
            return {
                "exitCode": 1,
                "summary": "stackctl package failed while materializing prod release artifact",
                "details": [str(exc)],
                "reportDir": relpath(report_dir),
                **timing,
            }
        if materialized_config_version:
            details.append(
                f"prod release artifact materialized: configVersion={materialized_config_version}"
            )

    if not args.service:
        try:
            shared_package_dir = _build_runtime_shared_package(
                env_name,
                target=target_name,
            )
        except (OSError, FileNotFoundError) as exc:
            timing = _finish_timing(started_monotonic, started_at)
            write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
            _write_summary_bundle(
                report_dir,
                command="package",
                target=target_name,
                status="failed",
                summary=f"stackctl package failed while building shared runtime package for {env_name}",
                details=[str(exc)],
                extra={"env": env_name},
                timing=timing,
            )
            return {
                "exitCode": 1,
                "summary": f"stackctl package failed while building shared runtime package for {env_name}",
                "details": [str(exc)],
                "reportDir": relpath(report_dir),
                **timing,
            }
        details.append(f"runtime shared package ready: {relpath(shared_package_dir)}")

    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok",
        "command": "package",
        "env": env_name,
        "target": target_name,
        "timestamp": utc_now(),
        "reportDir": relpath(report_dir),
        "steps": reports,
        **timing,
    }
    if topology is not None:
        payload["topologyTarget"] = get_target(topology, target_name)
    write_json(report_dir / "report.json", payload)
    _write_summary_bundle(
        report_dir,
        command="package",
        target=target_name,
        status="ok",
        summary=f"stackctl package completed for {env_name}",
        details=details,
        extra={"env": env_name},
        timing=timing,
    )
    fingerprint = write_package_fingerprint(
        env_name,
        target_name,
        report_dir=relpath(report_dir),
        include_services=bool(args.include_services or args.service),
        details=details,
    )
    details.append(f"package fingerprint: {relpath(fingerprint)}")
    return {
        "exitCode": 0,
        "summary": f"stackctl package completed for {env_name}",
        "details": details,
        "reportDir": relpath(report_dir),
        "packageFingerprint": relpath(fingerprint),
        **timing,
    }


def _command_verify_legal_static(
    args: argparse.Namespace,
    profile: VerificationProfile,
) -> dict[str, Any]:
    env_name = args.env or (get_target(load_environment_topology(), args.target).get("env") if args.target else "all")
    target_name = args.target or (DEFAULT_TARGET_BY_ENV[env_name] if env_name in ENVIRONMENTS else "repo")
    report_dir = resolve_report_dir(args, env_name if env_name in ENVIRONMENTS else "repo", target_name)
    started_monotonic, started_at = _start_timing()
    package_envs = [env_name] if env_name in ENVIRONMENTS else list(ENVIRONMENTS)
    steps: list[dict[str, Any]] = []
    issues: list[str] = []
    stdout_sections: list[tuple[str, str]] = []

    for package_env in package_envs:
        package_args = argparse.Namespace(
            command="package",
            kind="legal-static",
            env=package_env,
            service="",
            include_services=False,
            target=args.target or DEFAULT_TARGET_BY_ENV[package_env],
            output_format="json",
            report_dir=str(report_dir / f"package-{package_env}"),
        )
        package_payload = command_package(package_args)
        steps.append(
            {
                "kind": "package",
                "packageKind": "legal-static",
                "env": package_env,
                "exitCode": package_payload["exitCode"],
                "details": package_payload.get("details", []),
                "reportDir": package_payload.get("reportDir", ""),
            }
        )
        if package_payload["exitCode"] != 0:
            issues.append(
                f"legal-static package failed for {package_env}: "
                + "; ".join(package_payload.get("details", []))
            )
            continue

        verify_result, verify_payload = _legal_static_command(
            "verify-package",
            package_env,
            target=package_args.target,
        )
        steps.append(
            {
                "kind": "verify",
                "packageKind": "legal-static",
                "env": package_env,
                "exitCode": verify_result.returncode,
                "stdout": verify_result.stdout,
                "stderr": verify_result.stderr,
                "payload": verify_payload,
            }
        )
        stdout_sections.append(
            (
                f"legal-static-verify:{package_env}",
                "\n".join(filter(None, [verify_result.stdout, verify_result.stderr])),
            )
        )
        if verify_result.returncode != 0:
            verify_issues = verify_payload.get("issues") if isinstance(verify_payload.get("issues"), list) else []
            detail = "; ".join(str(issue) for issue in verify_issues)
            issues.append(
                f"legal-static verify failed for {package_env}: "
                + (detail or verify_result.stderr.strip() or verify_result.stdout.strip())
            )

    timing = _finish_timing(started_monotonic, started_at)
    blocked = bool(issues) and profile is VerificationProfile.RELEASE
    payload = {
        "status": (
            "ok"
            if not issues
            else ProbeOutcome.GATE_BLOCK.value
            if blocked
            else "failed"
        ),
        "command": "verify",
        "kind": "legal-static",
        "profile": profile.value,
        "timestamp": utc_now(),
        "steps": steps,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": issues})
    _write_summary_bundle(
        report_dir,
        command="verify",
        target=target_name,
        status=payload["status"],
        summary="stackctl legal-static verify passed" if not issues else "stackctl legal-static verify failed",
        details=issues or [f"ran {len(steps)} legal-static checks"],
        extra={"kind": "legal-static", "profile": profile.value},
        timing=timing,
    )
    _write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not issues else 1,
        "summary": "stackctl legal-static verify passed" if not issues else "stackctl legal-static verify failed",
        "details": issues or [f"ran {len(steps)} legal-static checks"],
        "reportDir": relpath(report_dir),
        **timing,
    }


def _command_verify_config_slo(args: argparse.Namespace) -> dict[str, Any]:
    """以 stackctl 作为配置灰度 SLO 决策的唯一公开入口。"""
    report_dir = resolve_report_dir(args, "prod", "prod-hosted")
    started_monotonic, started_at = _start_timing()
    values = {
        "--error-rate": str(getattr(args, "error_rate", "") or "").strip(),
        "--p95-ms": str(getattr(args, "p95_ms", "") or "").strip(),
        "--redis-error-rate": str(
            getattr(args, "redis_error_rate", "") or ""
        ).strip(),
    }
    missing = [flag for flag, value in values.items() if not value]
    if missing:
        timing = _finish_timing(started_monotonic, started_at)
        details = ["config-slo requires " + ", ".join(missing)]
        _write_summary_bundle(
            report_dir,
            command="verify",
            target="prod-hosted",
            status="failed",
            summary="stackctl config-slo verification failed",
            details=details,
            extra={"kind": "config-slo"},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": "stackctl config-slo verification failed",
            "details": details,
            "reportDir": relpath(report_dir),
            **timing,
        }
    command = ["bash", "quwoquan_ops/cli/prod/config_release_slo_gate.sh"]
    for flag, value in values.items():
        command.extend((flag, value))
    result = run(command)
    timing = _finish_timing(started_monotonic, started_at)
    details = _command_details(result)
    status = "ok" if result.returncode == 0 else "failed"
    write_json(
        report_dir / "report.json",
        {
            "status": status,
            "command": "verify",
            "kind": "config-slo",
            "target": "prod-hosted",
            "argv": command,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            **timing,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="verify",
        target="prod-hosted",
        status=status,
        summary=(
            "stackctl config-slo verification passed"
            if status == "ok"
            else "stackctl config-slo verification failed"
        ),
        details=details,
        extra={"kind": "config-slo"},
        timing=timing,
    )
    _write_stdout_markdown(
        report_dir,
        [("config-slo", "\n".join(filter(None, [result.stdout, result.stderr])))],
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            "stackctl config-slo verification passed"
            if status == "ok"
            else "stackctl config-slo verification failed"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def _command_verify_service_environment(args: argparse.Namespace) -> dict[str, Any]:
    if not args.env:
        return {
            "exitCode": 2,
            "summary": "stackctl verify --service requires --env",
            "details": [],
        }
    env_name = args.env
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    profile = VerificationProfile(args.profile)
    report_dir = (
        Path(args.report_dir)
        if args.report_dir
        else artifact_run_dir(
            env_name,
            _service_verify_report_action(
                args.command,
                args.service,
                profile,
            ),
            target=target_name,
        )
    )
    started_monotonic, started_at = _start_timing()
    command = [
        "bash",
        "quwoquan_service/scripts/runtime/build_service_env_package.sh",
        "--service",
        args.service,
        "--env",
        env_name,
    ]
    result = run(command, env={"QWQ_DEPLOY_TARGET": target_name})
    issues: list[str] = []
    steps: list[dict[str, Any]] = [
        {
            "kind": "package",
            "argv": command,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    ]
    package_dir = service_deployment_package_dir(env_name, args.service, target=target_name)
    required = (
        package_dir / "image.lock",
        package_dir / "config/config.yaml",
        package_dir / "manifests/all.yaml",
        package_dir / "provenance.json",
    )
    if result.returncode != 0:
        issues.append(result.stderr.strip() or result.stdout.strip())
    for path in required:
        if not path.is_file():
            issues.append(f"missing service package artifact: {path}")
    if not issues:
        try:
            provenance = json.loads((package_dir / "provenance.json").read_text(encoding="utf-8"))
            if provenance.get("service") != args.service or provenance.get("environment") != env_name:
                issues.append("service package provenance identity mismatch")
            for value in (provenance.get("digests") or {}).values():
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)):
                    issues.append(f"invalid package digest: {value}")
        except (OSError, json.JSONDecodeError, TypeError) as error:
            issues.append(f"invalid service package provenance: {error}")
    if (
        not issues
        and profile is VerificationProfile.RELEASE
        and env_name in {"gamma", "prod"}
    ):
        provider_preflight = _run_provider_readiness_preflight(
            env_name,
            report_dir,
        )
        steps.append(
            {
                "kind": provider_preflight["kind"],
                "environment": env_name,
                "argv": provider_preflight["argv"],
                "exitCode": provider_preflight["exitCode"],
                "reportPath": provider_preflight["reportPath"],
                "details": provider_preflight["details"],
            }
        )
        if provider_preflight["exitCode"] != 0:
            issues.extend(provider_preflight["details"])
    if not issues:
        for profile_command in _selected_profile_commands(
            env_name,
            target_name,
            profile,
            report_dir,
            service=args.service,
        ):
            profile_result = run(
                profile_command["argv"],
                cwd=profile_command.get("cwd"),
                env=profile_command.get("env"),
            )
            blocking = bool(profile_command.get("blocking", True))
            steps.append(
                {
                    "kind": "profile",
                    "profile": profile.value,
                    "name": profile_command["name"],
                    "argv": profile_command["argv"],
                    "exitCode": profile_result.returncode,
                    "blocking": blocking,
                    "reportPath": profile_command.get("reportPath", ""),
                    "stdout": profile_result.stdout,
                    "stderr": profile_result.stderr,
                }
            )
            if profile_result.returncode != 0 and blocking:
                issues.append(
                    f"{profile_command['name']} failed: "
                    + (
                        profile_result.stderr.strip()
                        or profile_result.stdout.strip()
                        or "unknown profile failure"
                    )
                )
                if profile_command.get("stopOnFailure"):
                    break
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok" if not issues else "failed",
        "command": "verify",
        "service": args.service,
        "environment": env_name,
        "profile": profile.value,
        "packageDir": str(package_dir),
        "steps": steps,
        "issues": issues,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    return {
        "exitCode": 0 if not issues else 1,
        "summary": (
            f"stackctl verify passed for {args.service}/{env_name}"
            if not issues
            else f"stackctl verify failed for {args.service}/{env_name}"
        ),
        "details": issues
        or [f"package and {profile.value} profile verified: {package_dir}"],
        "reportDir": relpath(report_dir),
        **timing,
    }


def _service_verify_report_action(
    command: str,
    service: str,
    profile: VerificationProfile,
) -> str:
    return f"{command}-{service}-{profile.value}"


def _official_distribution_root(
    args: argparse.Namespace,
    *,
    target_name: str,
) -> tuple[Path, bool]:
    configured = str(
        getattr(args, "distribution_root", "")
        or os.environ.get("QWQ_DISTRIBUTION_ROOT", "")
    ).strip()
    if configured:
        return Path(configured).expanduser().resolve(), True
    return deployment_target_path(target_name, "distribution-origin"), False


def _inspect_distribution_for_target(
    args: argparse.Namespace,
    *,
    target_name: str,
) -> tuple[dict[str, Any], Path, bool]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    distribution_root, explicitly_configured = _official_distribution_root(
        args,
        target_name=target_name,
    )
    inspection = inspect_official_distribution(
        distribution_root=distribution_root,
        public_origin=str(public_bases.get("publicWeb") or ""),
        download_origin=str(public_bases.get("appDownload") or ""),
        verify_hosted=bool(getattr(args, "verify_hosted", False)),
    )
    if target_name == "prod-hosted" and not explicitly_configured:
        inspection["status"] = ProbeOutcome.GATE_BLOCK.value
        inspection.setdefault("issues", []).append(
            "prod distribution inspection requires QWQ_DISTRIBUTION_ROOT or --distribution-root"
        )
    inspection["distributionRoot"] = str(distribution_root)
    inspection["explicitlyConfigured"] = explicitly_configured
    return inspection, distribution_root, explicitly_configured


def _command_verify_distribution(args: argparse.Namespace) -> dict[str, Any]:
    env_name = args.env or (
        str(get_target(load_environment_topology(), args.target).get("env"))
        if args.target
        else ""
    )
    if env_name not in ENVIRONMENTS:
        return {
            "exitCode": 2,
            "summary": "stackctl verify distribution requires --env or --target",
            "details": ["distribution verification is environment-scoped"],
        }
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    try:
        inspection, _, _ = _inspect_distribution_for_target(
            args,
            target_name=target_name,
        )
        issues = list(inspection.get("issues") or [])
    except (OSError, ValueError, OfficialDistributionReleaseError) as error:
        inspection = {"status": ProbeOutcome.GATE_BLOCK.value, "issues": [str(error)]}
        issues = [str(error)]
    timing = _finish_timing(started_monotonic, started_at)
    write_json(
        report_dir / "distribution.json",
        {"command": "verify", "kind": "distribution", **inspection, **timing},
    )
    write_json(report_dir / "findings.json", {"issues": issues})
    return {
        "exitCode": 0 if not issues else 2,
        "summary": (
            f"stackctl distribution verification passed for {target_name}"
            if not issues
            else f"stackctl distribution verification is GATE_BLOCK for {target_name}"
        ),
        "details": issues or ["Web/PWA and Android distribution are ready"],
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_verify(args: argparse.Namespace) -> dict[str, Any]:
    service_name = str(getattr(args, "service", "") or "").strip()
    if service_name:
        return _command_verify_service_environment(args)
    if args.kind == "config-slo":
        return _command_verify_config_slo(args)
    if args.kind == "distribution":
        return _command_verify_distribution(args)
    profile = VerificationProfile(args.profile)
    if args.kind == "legal-static":
        if profile is VerificationProfile.BASELINE:
            return {
                "exitCode": 2,
                "summary": "stackctl verify baseline does not verify legal-static",
                "details": [
                    "baseline must not create or read disposable release output; "
                    "use smoke, integration, or release"
                ],
            }
        return _command_verify_legal_static(args, profile)

    env_name = args.env or (get_target(load_environment_topology(), args.target).get("env") if args.target else "")
    if profile is VerificationProfile.BASELINE and env_name:
        return {
            "exitCode": 2,
            "summary": "stackctl verify baseline does not accept an environment",
            "details": ["baseline must run without --env or --target"],
        }
    if profile.requires_environment and env_name not in ENVIRONMENTS:
        return {
            "exitCode": 2,
            "summary": f"stackctl verify {profile.value} requires --env or --target",
            "details": ["environment-scoped profiles must name one environment"],
        }
    if profile is VerificationProfile.BASELINE and args.kind == "packaging":
        return {
            "exitCode": 2,
            "summary": "stackctl verify baseline does not verify packaging",
            "details": [
                "baseline must not read disposable release output; use an environment profile"
            ],
        }
    target_name = args.target or (DEFAULT_TARGET_BY_ENV[env_name] if env_name in ENVIRONMENTS else "repo")
    report_dir = resolve_report_dir(args, env_name if env_name in ENVIRONMENTS else "repo", target_name)
    started_monotonic, started_at = _start_timing()
    steps: list[dict[str, Any]] = []
    issues: list[str] = []
    provider_readiness: dict[str, Any] = {}
    if (
        profile is VerificationProfile.RELEASE
        and env_name in {"gamma", "prod"}
    ):
        provider_preflight = _run_provider_readiness_preflight(env_name, report_dir)
        provider_readiness = provider_preflight["report"]
        steps.append(
            {
                "kind": provider_preflight["kind"],
                "environment": env_name,
                "argv": provider_preflight["argv"],
                "exitCode": provider_preflight["exitCode"],
                "reportPath": provider_preflight["reportPath"],
                "details": provider_preflight["details"],
            }
        )
        if provider_preflight["exitCode"] != 0:
            issues.extend(
                f"provider readiness: {detail}"
                for detail in provider_preflight["details"]
            )
    if profile is VerificationProfile.RELEASE and target_name == "prod-hosted":
        receipt = str(
            getattr(args, "backup_recovery_receipt", "")
            or os.environ.get("QWQ_PROD_BACKUP_RECOVERY_RECEIPT", "")
        ).strip()
        backup_report = report_dir / "backup-recovery.json"
        command = [
            "python3",
            "quwoquan_ops/cli/prod/backup_recovery.py",
            "--plan",
            "quwoquan_ops/environments/prod/backup-recovery.yaml",
            "--receipt",
            receipt,
            "--output",
            str(backup_report),
        ]
        if not receipt:
            steps.append(
                {
                    "kind": "backup-recovery",
                    "exitCode": 2,
                    "details": ["QWQ_PROD_BACKUP_RECOVERY_RECEIPT is required"],
                }
            )
            issues.append("backup recovery hosted receipt is required for prod release")
        else:
            result = run(command, env={"QWQ_DEPLOY_TARGET": target_name})
            steps.append(
                {
                    "kind": "backup-recovery",
                    "argv": command,
                    "exitCode": result.returncode,
                    "reportPath": str(backup_report),
                    "details": _command_details(result),
                }
            )
            if result.returncode != 0:
                issues.append("backup recovery receipt validation failed")
    if profile is VerificationProfile.RELEASE and args.kind == "all":
        try:
            distribution, _, _ = _inspect_distribution_for_target(
                args,
                target_name=target_name,
            )
            distribution_issues = list(distribution.get("issues") or [])
        except (OSError, ValueError, OfficialDistributionReleaseError) as error:
            distribution = {
                "status": ProbeOutcome.GATE_BLOCK.value,
                "issues": [str(error)],
            }
            distribution_issues = [str(error)]
        steps.append(
            {
                "kind": "distribution",
                "exitCode": 0 if not distribution_issues else 2,
                "details": distribution_issues,
                "inspection": distribution,
            }
        )
        issues.extend(
            f"distribution: {issue}" for issue in distribution_issues
        )
    package_envs = [env_name] if env_name in ENVIRONMENTS and profile.requires_environment else []
    reuse_package = bool(getattr(args, "reuse_package", False))
    for package_env in package_envs:
        package_target = args.target or DEFAULT_TARGET_BY_ENV[package_env]
        if reuse_package:
            ok, reuse_detail = can_reuse_package(
                package_env,
                package_target,
                include_services=True,
            )
            if ok:
                steps.append(
                    {
                        "kind": "package",
                        "env": package_env,
                        "exitCode": 0,
                        "reused": True,
                        "details": [reuse_detail],
                        "reportDir": "",
                    }
                )
                continue
            steps.append(
                {
                    "kind": "package",
                    "env": package_env,
                    "exitCode": 0,
                    "reused": False,
                    "details": [f"reuse unavailable: {reuse_detail}; packaging"],
                    "reportDir": "",
                }
            )
        package_args = argparse.Namespace(
            command="package",
            kind="runtime",
            env=package_env,
            service="",
            include_services=True,
            target=package_target,
            output_format="json",
            report_dir=str(report_dir / f"package-{package_env}"),
        )
        package_payload = command_package(package_args)
        steps.append(
            {
                "kind": "package",
                "env": package_env,
                "exitCode": package_payload["exitCode"],
                "reused": False,
                "details": package_payload.get("details", []),
                "reportDir": package_payload.get("reportDir", ""),
            }
        )
        if package_payload["exitCode"] != 0:
            issues.append(f"package failed for {package_env}: {'; '.join(package_payload.get('details', []))}")
    stdout_sections: list[tuple[str, str]] = []
    commands = _selected_verify_commands(
        args.kind,
        env_name if env_name in ENVIRONMENTS else "",
        target_name=target_name,
        profile=profile,
    )
    for command in commands:
        result = run(command, env={"QWQ_DEPLOY_TARGET": target_name})
        command_key = " ".join(command)
        steps.append(
            {
                "kind": "verify",
                "group": args.kind,
                "argv": command,
                "exitCode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        stdout_sections.append((command_key, "\n".join(filter(None, [result.stdout, result.stderr]))))
        if result.returncode != 0:
            issues.append(result.stderr.strip() or result.stdout.strip() or "unknown verify failure")
    if (phase := profile.readiness_phase) is not None:
        readiness_payload = command_content_readiness(
            argparse.Namespace(
                command="content-readiness",
                phase=phase.value,
                env=env_name,
                output_format="json",
                report_dir=str(report_dir / "content-readiness"),
            )
        )
        steps.append(
            {
                "kind": "readiness",
                "phase": phase.value,
                "exitCode": readiness_payload["exitCode"],
                "reportDir": readiness_payload.get("reportDir", ""),
                "details": readiness_payload.get("details", []),
            }
        )
        if readiness_payload["exitCode"] != 0:
            issues.extend(
                f"content readiness: {detail}"
                for detail in readiness_payload.get("details", [])
            )
    for profile_command in _selected_profile_commands(
        env_name,
        target_name,
        profile,
        report_dir,
        service=service_name,
    ):
        result = run(
            profile_command["argv"],
            cwd=profile_command.get("cwd"),
            env=profile_command.get("env"),
        )
        blocking = bool(profile_command.get("blocking", True))
        steps.append(
            {
                "kind": "profile",
                "profile": profile.value,
                "name": profile_command["name"],
                "argv": profile_command["argv"],
                "exitCode": result.returncode,
                "blocking": blocking,
                "reportPath": profile_command.get("reportPath", ""),
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        stdout_sections.append((profile_command["name"], "\n".join(filter(None, [result.stdout, result.stderr]))))
        if result.returncode != 0 and blocking:
            issues.append(
                f"{profile_command['name']} failed: "
                + (result.stderr.strip() or result.stdout.strip() or "unknown profile failure")
            )
            if profile_command.get("stopOnFailure"):
                break
    timing = _finish_timing(started_monotonic, started_at)
    t4_evidence_path = ""
    if (
        profile is VerificationProfile.RELEASE
        and target_name
        in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}
    ):
        t4_evidence = _runtime_media_t4_evidence(
            target_name=target_name,
            steps=steps,
            started_at=timing["startedAt"],
            ended_at=timing["endedAt"],
        )
        t4_evidence_file = report_dir / "runtime_media_t4_evidence.json"
        write_json(t4_evidence_file, t4_evidence)
        t4_evidence_path = relpath(t4_evidence_file)
        if t4_evidence["status"] != "passed":
            issues.append(
                "runtime media T4 evidence is incomplete; "
                f"inspect {t4_evidence_path}",
            )
    blocked = bool(issues) and profile is VerificationProfile.RELEASE
    payload = {
        "status": "ok" if not issues else "failed",
        "command": "verify",
        "timestamp": utc_now(),
        "kind": args.kind,
        "profile": profile.value,
        "providerReadiness": provider_readiness,
        "steps": steps,
        "runtimeMediaT4EvidencePath": t4_evidence_path,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": issues})
    _write_summary_bundle(
        report_dir,
        command="verify",
        target=target_name,
        status=payload["status"],
        summary=(
            "stackctl verify passed"
            if not issues
            else "stackctl verify is GATE_BLOCK"
            if blocked
            else "stackctl verify failed"
        ),
        details=issues or [f"ran {len(steps)} checks"],
        extra={"kind": args.kind, "profile": profile.value},
        timing=timing,
    )
    _write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not issues else 2 if blocked else 1,
        "summary": (
            "stackctl verify passed"
            if not issues
            else "stackctl verify is GATE_BLOCK"
            if blocked
            else "stackctl verify failed"
        ),
        "details": issues or [f"ran {len(steps)} checks"],
        "reportDir": relpath(report_dir),
        **timing,
    }


def _optional_product_telemetry_environment(
    environment: str,
    target_name: str,
) -> tuple[dict[str, str], str]:
    try:
        bundle = load_product_telemetry_log_sink(environment, target_name)
    except (RuntimeError, ValueError) as exc:
        return {"QWQ_PRODUCT_TELEMETRY_AVAILABLE": "0"}, str(exc)
    return {
        **bundle.environment,
        "QWQ_PRODUCT_TELEMETRY_AVAILABLE": "1",
    }, ""


def _log_sink_gate_block_receipt() -> dict[str, str]:
    return {
        "source": "unavailable",
        "status": "gate_block",
        "redactedDigest": "",
    }


def _write_full_workload_log_sink_gate_block(
    *,
    report_dir: Path,
    report_target: str,
    resolved_target: str,
    timing: dict[str, Any],
) -> dict[str, Any]:
    receipt = _log_sink_gate_block_receipt()
    details = [
        "commercial full workload requires product telemetry log-sink binding",
        "ensure the selected local topology exposes the declared log-sink endpoint",
        "use --workload content-release only for import/API/media validation",
    ]
    write_json(
        report_dir / "report.json",
        {
            "command": "up",
            "target": report_target,
            "resolvedTarget": resolved_target,
            "workload": "full",
            "commercialClaim": True,
            "status": "gate_block",
            "logSink": receipt,
            "steps": [],
            **timing,
        },
    )
    write_json(report_dir / "findings.json", {"issues": details})
    _write_summary_bundle(
        report_dir,
        command="up",
        target=report_target,
        status="gate_block",
        summary=f"stackctl up is GATE_BLOCK for {report_target}",
        details=details,
        extra={
            "workload": "full",
            "commercialClaim": True,
            "logSink": receipt,
        },
        timing=timing,
    )
    return {
        "exitCode": 2,
        "summary": f"stackctl up is GATE_BLOCK for {report_target}",
        "details": details,
        "reportDir": relpath(report_dir),
        "status": "gate_block",
        "workload": "full",
        "commercialClaim": True,
        "logSink": receipt,
        **timing,
    }


def _write_product_telemetry_log_sink_control_report(
    *,
    report_dir: Path,
    target_name: str,
    action: str,
    receipt: dict[str, str],
    action_statuses: list[dict[str, str]],
    gate_blocked: bool,
    timing: dict[str, Any],
) -> dict[str, Any]:
    """Persist only redacted log-sink binding evidence and outcome names."""
    status = "gate_block" if gate_blocked else "ok"
    summary = (
        f"product telemetry log-sink control is GATE_BLOCK for {target_name}"
        if gate_blocked
        else f"product telemetry log-sink control completed for {target_name}"
    )
    details = (
        [
            "commercial full workload requires product telemetry log-sink binding",
        ]
        if gate_blocked
        else [f"{item['action']}: {item['status']}" for item in action_statuses]
    )
    payload = {
        "command": "product-telemetry-log-sink",
        "target": target_name,
        "workload": "full",
        "commercialClaim": True,
        "action": action,
        "status": status,
        "logSink": receipt,
        "actions": action_statuses,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(
        report_dir / "findings.json",
        {"issues": details if gate_blocked else []},
    )
    _write_summary_bundle(
        report_dir,
        command="product-telemetry-log-sink",
        target=target_name,
        status=status,
        summary=summary,
        details=details,
        extra={
            "workload": "full",
            "commercialClaim": True,
            "logSink": receipt,
        },
        timing=timing,
    )
    return {
        "exitCode": 2 if gate_blocked else 0,
        "summary": summary,
        "details": details,
        "reportDir": relpath(report_dir),
        "workload": "full",
        "commercialClaim": True,
        "logSink": receipt,
        "actions": action_statuses,
        **timing,
    }


def _log_sink_control_actions(action: str) -> tuple[str, ...]:
    if action == "all":
        return ("cold-start", "health", "send-query", "permission-failure")
    return (action,)


def _log_sink_control_query_session(
    *,
    api_base: str,
    environment: str,
    target_name: str,
    resolve_host: str,
) -> LocalAcceptanceSession:
    """Resolve a query session without serializing a bearer token into evidence."""
    query_token = os.environ.get("PRODUCT_TELEMETRY_QUERY_TOKEN", "").strip()
    if query_token:
        return LocalAcceptanceSession(
            owner_id="log-sink-control",
            persona_id="log-sink-control",
            access_token=query_token,
        )
    if environment == "gamma" and target_name == "gamma-local":
        return open_local_acceptance_session(
            api_base,
            environment=environment,
            target_name=target_name,
            profile="product-telemetry-query",
            resolve_host=resolve_host,
        )
    raise RuntimeError("product telemetry query authorization is unavailable")


def _run_product_telemetry_log_sink_control_action(
    *,
    action: str,
    target_name: str,
    environment: str,
    report_dir: Path,
) -> None:
    if action == "cold-start":
        # The preceding package/up step has already produced provenance-bound
        # images. Cold-start verifies their restart path without silently
        # replacing that artifact with a new, unverified build.
        result = command_up(
            argparse.Namespace(
                command="up",
                env="",
                target=target_name,
                device_id="",
                skip_app=True,
                skip_build=True,
                build_only=False,
                build_services="",
                workload="full",
                rollout_mode="",
                output_format="json",
                report_dir=str(report_dir / "cold-start"),
            )
        )
        if int(result.get("exitCode", 1)) != 0:
            raise RuntimeError("cold-start failed")
        return

    if action == "health":
        result = command_health(
            argparse.Namespace(
                command="health",
                target=target_name,
                scope="full",
                output_format="json",
                report_dir=str(report_dir / "health"),
            )
        )
        if int(result.get("exitCode", 1)) != 0:
            raise RuntimeError("health failed")
        return

    topology = load_environment_topology()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    api_base = str(public_bases.get("api") or "").strip()
    product_ops_base = str(public_bases.get("productOps") or "").strip()
    if not api_base or not product_ops_base:
        raise RuntimeError("product-ops public base is unavailable")
    resolve_host = _local_public_connect_host(topology, target_name, api_base)

    session = open_local_acceptance_session(
        api_base,
        environment=environment,
        target_name=target_name,
        resolve_host=resolve_host,
    )
    if action == "permission-failure":
        try:
            request_local_environment_json(
                product_ops_base,
                path="/ops/events/summary",
                session=session,
                resolve_host=resolve_host,
            )
        except LocalEnvironmentHTTPError as exc:
            if exc.status == 403:
                return
            raise RuntimeError("permission probe returned unexpected status") from exc
        raise RuntimeError("permission probe unexpectedly succeeded")

    if action != "send-query":
        raise ValueError(f"unsupported product telemetry log-sink action: {action}")

    probe_record = {
        "logType": "event",
        "eventType": "chat_interaction_outcome",
        "sessionId": "s.c2xzX2NvbnRyb2w.1",
        "pageName": "chat_detail",
        "occurredAt": utc_now(),
        "deviceManufacturer": "LogSinkControl",
        "deviceModel": "LogSinkControl",
        "appVersion": "0.0.0-log-sink-control",
        "networkClass": "other",
        "devicePlatform": "web",
        "chatAction": "mention_send",
        "chatOutcome": "succeeded",
        "mentionScope": "member",
    }
    body = {"events": [probe_record]}
    canonical_body = json.dumps(
        body,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    idempotency_key = hashlib.sha256(canonical_body).hexdigest()
    request_local_environment_json(
        product_ops_base,
        path="/ops/events",
        session=session,
        method="POST",
        body=body,
        headers={"Idempotency-Key": idempotency_key},
        resolve_host=resolve_host,
    )
    query_session = _log_sink_control_query_session(
        api_base=api_base,
        environment=environment,
        target_name=target_name,
        resolve_host=resolve_host,
    )
    request_local_environment_json(
        product_ops_base,
        path="/ops/events/summary",
        session=query_session,
        resolve_host=resolve_host,
    )


def command_product_telemetry_log_sink(args: argparse.Namespace) -> dict[str, Any]:
    """Execute product telemetry probes through product-ops, never direct Provider."""
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    environment = str(target["env"])
    report_dir = resolve_report_dir(args, environment, args.target)
    started_monotonic, started_at = _start_timing()
    actions = _log_sink_control_actions(args.action)
    try:
        bundle = load_product_telemetry_log_sink(environment, args.target)
        receipt = bundle.redacted_receipt()
    except (RuntimeError, ValueError):
        timing = _finish_timing(started_monotonic, started_at)
        return _write_product_telemetry_log_sink_control_report(
            report_dir=report_dir,
            target_name=args.target,
            action=args.action,
            receipt=_log_sink_gate_block_receipt(),
            action_statuses=[],
            gate_blocked=True,
            timing=timing,
        )

    action_statuses: list[dict[str, str]] = []
    for action in actions:
        try:
            _run_product_telemetry_log_sink_control_action(
                action=action,
                target_name=args.target,
                environment=environment,
                report_dir=report_dir,
            )
        except (RuntimeError, ValueError, LocalEnvironmentHTTPError):
            action_statuses.append({"action": action, "status": "failed"})
            timing = _finish_timing(started_monotonic, started_at)
            return _write_product_telemetry_log_sink_control_report(
                report_dir=report_dir,
                target_name=args.target,
                action=args.action,
                receipt=receipt,
                action_statuses=action_statuses,
                gate_blocked=True,
                timing=timing,
            )
        action_statuses.append({"action": action, "status": "passed"})

    timing = _finish_timing(started_monotonic, started_at)
    return _write_product_telemetry_log_sink_control_report(
        report_dir=report_dir,
        target_name=args.target,
        action=args.action,
        receipt=receipt,
        action_statuses=action_statuses,
        gate_blocked=False,
        timing=timing,
    )


def command_up(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    started_monotonic, started_at = _start_timing()
    if not args.env and not args.target:
        try:
            args.env = pick_dev_up_env(label="[stackctl up]")
        except RuntimeError as exc:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl up failed",
                "details": [str(exc)],
                **timing,
            }

    if bool(args.env) == bool(args.target):
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up failed",
            "details": ["provide exactly one of --env or --target"],
            **timing,
        }

    requested_target = args.target
    if args.env:
        requested_target = DEV_UP_STACK_TARGETS[args.env]
        if not requested_target:
            requested_target = app_target_for_env(args.env)

    build_only = bool(getattr(args, "build_only", False))
    build_services = str(getattr(args, "build_services", "")).strip()
    if build_services and not build_only:
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up failed",
            "details": ["--build-services requires --build-only"],
            **timing,
        }
    if build_only and getattr(args, "skip_build", False):
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up failed",
            "details": ["--build-only cannot be combined with --skip-build"],
            **timing,
        }
    if build_only and requested_target != "gamma-local":
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up failed",
            "details": ["--build-only is supported only for gamma-local"],
            **timing,
        }

    target = get_target(topology, requested_target)
    env_name = str(target["env"])
    report_target = args.env or requested_target
    report_dir = resolve_report_dir(args, env_name, report_target)
    # Local alpha/beta: migrate checksum drift → wipe once before readiness wait.
    if requested_target in {"alpha-local", "beta-local"} and not build_only:
        drift = probe_migration_drift(requested_target)
        if drift.has_drift:
            auto_wipe = os.environ.get(
                "STACKCTL_AUTO_WIPE_MIGRATION_DRIFT", "1"
            ).strip() not in {"0", "false", "FALSE", "no", "NO"}
            if not auto_wipe:
                timing = _finish_timing(started_monotonic, started_at)
                details = [
                    format_drift_gate_block(drift),
                    "set STACKCTL_AUTO_WIPE_MIGRATION_DRIFT=1 to wipe",
                ]
                write_json(
                    report_dir / "report.json",
                    {
                        "command": "up",
                        "target": report_target,
                        "resolvedTarget": requested_target,
                        "status": "gate_block",
                        "migrationDrift": drift.detail,
                        "details": details,
                        **timing,
                    },
                )
                return {
                    "exitCode": 2,
                    "summary": (
                        f"stackctl up GATE_BLOCK: migration drift on {requested_target}"
                    ),
                    "details": details,
                    "reportDir": relpath(report_dir),
                    **timing,
                }
            wipe_ok, wipe_detail = wipe_local_postgres_volumes(requested_target)
            if not wipe_ok:
                timing = _finish_timing(started_monotonic, started_at)
                details = [format_drift_gate_block(drift), wipe_detail]
                return {
                    "exitCode": 2,
                    "summary": (
                        f"stackctl up GATE_BLOCK: drift wipe failed on {requested_target}"
                    ),
                    "details": details,
                    "reportDir": relpath(report_dir),
                    **timing,
                }
            _progress_print(
                f"[stackctl up] wiped local postgres for {requested_target} "
                "after migration drift"
            )
    # A content release starts only the import/consumer data plane. Device
    # selection belongs to a separate App UAT command, never to server startup.
    if args.workload == "content-release":
        args.skip_app = True
    commercial_claim = args.workload == "full"
    log_sink_receipt = {
        "source": "not-required",
        "status": "not-claimed",
        "redactedDigest": "",
    }
    log_sink_redaction_values: tuple[str, ...] = ()
    if args.workload == "full" and requested_target in {"beta-local", "gamma-local"}:
        try:
            log_sink_bundle = load_product_telemetry_log_sink(
                env_name,
                requested_target,
            )
            log_sink_receipt = log_sink_bundle.redacted_receipt()
            log_sink_redaction_values = tuple(log_sink_bundle.environment.values())
        except (RuntimeError, ValueError):
            timing = _finish_timing(started_monotonic, started_at)
            return _write_full_workload_log_sink_gate_block(
                report_dir=report_dir,
                report_target=report_target,
                resolved_target=requested_target,
                timing=timing,
            )
    local_operation_lock: Any | None = None
    if requested_target in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        local_lock_entered = False
        try:
            local_operation_lock = _local_stack_operation_lock(requested_target)
            local_operation_lock.__enter__()
            local_lock_entered = True
            assert_local_runtime_available(topology, requested_target)
        except RuntimeError as exc:
            if local_lock_entered and local_operation_lock is not None:
                local_operation_lock.__exit__(None, None, None)
                local_operation_lock = None
            timing = _finish_timing(started_monotonic, started_at)
            details = [
                str(exc),
                "wait for the active operation or stop the conflicting local runtime",
            ]
            write_json(
                report_dir / "report.json",
                {
                    "command": "up",
                    "target": report_target,
                    "resolvedTarget": requested_target,
                    "workload": args.workload,
                    "commercialClaim": commercial_claim,
                    "logSink": log_sink_receipt,
                    "steps": [
                        {
                            "name": f"{requested_target}-operation-lock",
                            "exitCode": 2,
                            "stdout": "",
                            "stderr": str(exc),
                        }
                    ],
                    **timing,
                },
            )
            _write_summary_bundle(
                report_dir,
                command="up",
                target=report_target,
                status="gate_block",
                summary=f"stackctl up is blocked for {report_target}",
                details=details,
                timing=timing,
            )
            return {
                "exitCode": 2,
                "summary": f"stackctl up is GATE_BLOCK for {report_target}",
                "details": details,
                "reportDir": relpath(report_dir),
                **timing,
            }
    steps: list[dict[str, Any]] = []
    interactive = _is_interactive_terminal()
    stage_index = 0
    expected_stage_total = (
        3
        if requested_target in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}
        and not args.skip_app
        else 2
    )
    if requested_target in {"prod-sim", "prod-hosted"} and not args.skip_app:
        expected_stage_total = 2
    elif requested_target == "prod-hosted" and args.skip_app:
        expected_stage_total = 1

    def announce(stage: str, message: str, *, numbered: bool = False) -> None:
        if interactive:
            if numbered:
                _progress_print(f"{stage} {message}")
            else:
                _progress_print(f"[stackctl up] {stage} {message}")

    def run_stage(
        stage: str,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        live_prefix: str = "",
    ) -> subprocess.CompletedProcess[str]:
        nonlocal stage_index
        stage_index += 1
        stage_header = _format_stage_header(stage_index, expected_stage_total, stage)
        announce(stage_header, "started", numbered=True)
        stage_started = time.monotonic()
        result = _run_with_live_output(
            argv,
            env=env,
            prefix=live_prefix,
            redaction_values=log_sink_redaction_values,
        )
        duration = _format_duration_ms(int((time.monotonic() - stage_started) * 1000))
        status = "completed" if result.returncode == 0 else f"failed (exit={result.returncode})"
        announce(stage_header, f"{status} in {duration}", numbered=True)
        return result

    def maybe_resolve_device_id(*, include_web: bool) -> str:
        if args.skip_app:
            return ""
        if args.device_id:
            return args.device_id
        return resolve_device_id(
            include_mobile=True,
            include_web=include_web,
            include_desktop=False,
            label="[stackctl up]",
        )

    def start_app_process(env_key: str, device_id: str) -> dict[str, Any]:
        nonlocal stage_index
        launch_log = report_dir / f"app-launch-{device_id.replace('/', '_')}.log"
        stage_index += 1
        stage_header = _format_stage_header(stage_index, expected_stage_total, "app-launch")
        announce(stage_header, f"starting for {env_key}/{device_id}", numbered=True)
        try:
            process = launch_app(
                env_key,
                device_id,
                topology=topology,
                rollout_mode=args.rollout_mode,
                log_path=launch_log,
            )
        except RuntimeError as exc:
            raise RuntimeError(f"app launch failed for {env_key}/{device_id}: {exc}") from exc
        return {
            "process": process,
            "command": build_start_app_command(
                env_key,
                device_id,
                topology=topology,
                rollout_mode=args.rollout_mode,
            ),
            "log_path": launch_log,
            "stageHeader": stage_header,
        }

    def tail_beta_background_logs() -> dict[str, Any]:
        beta_log_dir = _local_runtime_log_root("beta-local")
        return _tail_multiple_logs_for_startup(
            [
                ("beta-app", beta_log_dir / "app-beta" / "local" / "runtime.log"),
                ("beta-product-ops", beta_log_dir / "product-ops" / "local" / "runtime.log"),
                ("beta-platform-ops", beta_log_dir / "platform-ops" / "local" / "runtime.log"),
                ("beta-ops-portal", beta_log_dir / "ops-portal" / "local" / "runtime.log"),
            ],
            idle_timeout_seconds=4.0,
            max_follow_seconds=35.0,
        )

    def tail_alpha_background_logs() -> dict[str, Any]:
        alpha_log_dir = _local_runtime_log_root("alpha-local")
        return _tail_multiple_logs_for_startup(
            [
                ("alpha-content", alpha_log_dir / "content-service" / "local" / "runtime.log"),
                ("alpha-user", alpha_log_dir / "user-service" / "local" / "runtime.log"),
                ("alpha-entity", alpha_log_dir / "entity-service" / "local" / "runtime.log"),
                ("alpha-media", alpha_log_dir / "media-origin" / "local" / "runtime.log"),
            ],
            idle_timeout_seconds=4.0,
            max_follow_seconds=20.0,
        )

    def tail_prod_sim_background_logs() -> dict[str, Any]:
        prod_sim_log_dir = _local_runtime_log_root("prod-sim")
        return _tail_multiple_logs_for_startup(
            [
                ("prod-sim-api-edge", prod_sim_log_dir / "api-edge" / "local" / "runtime.log"),
                ("prod-sim-product-ops", prod_sim_log_dir / "product-ops" / "local" / "runtime.log"),
                ("prod-sim-media-edge", prod_sim_log_dir / "media-edge" / "local" / "runtime.log"),
                ("prod-sim-media-origin", prod_sim_log_dir / "media-origin" / "local" / "runtime.log"),
            ],
            idle_timeout_seconds=4.0,
            max_follow_seconds=20.0,
        )

    if requested_target == "beta-local":
        app_launch = None
        if not args.skip_app:
            args.device_id = maybe_resolve_device_id(include_web=True)
        cmd = ["bash", "quwoquan_ops/cli/beta/start_beta_stack.sh", "up"]
        if args.skip_build:
            cmd.append("--skip-build")
        env = _beta_env_from_port_manifest(topology, requested_target)
        env["START_APP"] = "0"
        telemetry_env, telemetry_advisory = _optional_product_telemetry_environment(
            "beta", "beta-local"
        )
        env.update(telemetry_env)
        env["QWQ_WORKLOAD"] = args.workload
        # Beta 的自治配置明确启用内容向量能力；content-release 只缩小
        # workload/观测面，不得暗中改写服务配置或绕过 provider binding。
        external_provider_error = _bind_beta_external_provider_environment(env)
        if external_provider_error:
            steps.append(
                {
                    "name": "beta-external-provider-prerequisite",
                    "exitCode": 2,
                    "stdout": "",
                    "stderr": external_provider_error,
                }
            )
        if telemetry_advisory:
            steps.append(
                {
                    "kind": "observability-prerequisite",
                    "exitCode": 0,
                    "blocking": False,
                    "stdout": "product telemetry unavailable; App startup continues",
                    "stderr": telemetry_advisory,
                }
            )
        if external_provider_error:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr=external_provider_error,
            )
        else:
            result = run_stage("beta-local", cmd, env=env, live_prefix="[beta] ")
            background_tail = tail_beta_background_logs()
            steps.append(
                {
                    "kind": "beta-background-tail",
                    "exitCode": 0,
                    "stdout": "tailed beta background logs",
                    "stderr": "",
                    "tail": background_tail,
                }
            )
        if result.returncode == 0:
            beta_content_port = canonical_port(
                load_port_manifest(),
                str(target["portProfile"]),
                "content-service",
            )
            beta_health_url = f"http://127.0.0.1:{beta_content_port}/healthz"
            beta_ready, beta_status, beta_body, beta_content_type = fetch_url(
                beta_health_url,
                retry_attempts=5,
                retry_sleep_seconds=1.0,
            )
            steps.append(
                {
                    "kind": "beta-backend-health-check",
                    "exitCode": 0 if beta_ready else 1,
                    "stdout": "checked beta backend health endpoint",
                    "stderr": "" if beta_ready else beta_body,
                    "url": beta_health_url,
                    "statusCode": beta_status,
                    "contentType": beta_content_type,
                }
            )
            if not beta_ready:
                result = subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr=f"beta backend health check failed: {beta_health_url}",
                )
        if result.returncode == 0 and args.workload == "content-release":
            public_ready_attempts = _content_release_public_ready_attempts(target)
            public_bases = target.get("publicBases") or {}
            release_surfaces = (
                ("api", "/healthz"),
                ("mediaImage", "/healthz"),
            )
            for base_key, path in release_surfaces:
                base_url = str(public_bases.get(base_key) or "").rstrip("/")
                if not base_url:
                    result = subprocess.CompletedProcess(
                        cmd,
                        1,
                        stdout="",
                        stderr=f"beta content release has no public base: {base_key}",
                    )
                    break
                public_url = f"{base_url}{path}"
                public_ready, public_status, public_body, public_content_type = fetch_url(
                    public_url,
                    retry_attempts=public_ready_attempts,
                    retry_sleep_seconds=1.0,
                    resolve_host=_local_public_connect_host(
                        topology,
                        requested_target,
                        public_url,
                    ),
                )
                steps.append(
                    {
                        "kind": "beta-content-release-public-health",
                        "surface": base_key,
                        "exitCode": 0 if public_ready else 1,
                        "stdout": "checked beta content release public health",
                        "stderr": "" if public_ready else public_body,
                        "url": public_url,
                        "statusCode": public_status,
                        "contentType": public_content_type,
                    }
                )
                if not public_ready:
                    result = subprocess.CompletedProcess(
                        cmd,
                        1,
                        stdout="",
                        stderr=f"beta content release public health failed: {public_url}",
                    )
                    break
        if result.returncode == 0 and not args.skip_app:
            try:
                app_launch = start_app_process("beta", args.device_id)
            except RuntimeError as exc:
                result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
            else:
                tail_result = _tail_file_for_startup(
                    app_launch["log_path"],
                    process=app_launch["process"],
                    prefix=f"[{app_launch['stageHeader']} app] ",
                    idle_timeout_seconds=6.0,
                    max_follow_seconds=90.0,
                    ready_patterns=(
                        "Syncing files to device",
                        "Flutter run key commands",
                        "A Dart VM Service",
                        "The Flutter DevTools debugger",
                    ),
                    failure_patterns=(
                        "Failed to build",
                        "BUILD FAILED",
                        "Error launching application on",
                        "Lost connection to device.",
                        "Target kernel_snapshot_program failed",
                        "app launch exited before reaching steady state",
                    ),
                    ready_idle_timeout_seconds=3.0,
                )
                app_exit_code = app_launch["process"].poll()
                failure_detail = _app_launch_failure_detail(
                    tail_result,
                    default_message="beta app launch failed",
                    process_exit_code=app_exit_code,
                )
                app_failed = failure_detail is not None
                steps.append(
                    {
                        "argv": app_launch["command"],
                        "exitCode": app_exit_code or 0,
                        "stdout": f"pid={app_launch['process'].pid}",
                        "stderr": f"log={relpath(app_launch['log_path'])}",
                        "tail": tail_result,
                    }
                )
                if app_failed:
                    result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(failure_detail))
                else:
                    cmd = app_launch["command"]
                    result = subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=f"pid={app_launch['process'].pid}",
                        stderr=f"log={relpath(app_launch['log_path'])}",
                    )
    elif requested_target == "gamma-local":
        env = _gamma_env_from_port_manifest(topology, requested_target)
        # All Gamma child reports share stackctl's explicit run identity.  Static
        # deployment inputs remain in source/deploy work roots, never in output.
        gamma_run_id = report_dir.name
        env["QWQ_RUN_ROOT"] = str(report_dir.resolve())
        env["QWQ_OBSERVABILITY_RUN_ROOT"] = str(
            env_observability_run_dir(env_name, gamma_run_id).resolve()
        )
        package_cmd = [
            "python3",
            "quwoquan_ops/cli/stackctl.py",
            "package",
            "--env",
            "gamma",
            "--include-services",
        ]
        telemetry_env, telemetry_advisory = _optional_product_telemetry_environment(
            "gamma", "gamma-local"
        )
        env.update(telemetry_env)
        env["QWQ_WORKLOAD"] = args.workload
        # Gamma 的自治配置明确启用内容向量能力；content-release 只缩小
        # workload/观测面，不得绕过 content-service 的必需 provider binding。
        # `docker compose build` 仍会插值 object-storage service，即使不会启动它；
        # 因而 build-only 也必须材料化平台自有的对象存储 binding。其余三方
        # Port 替身只在实际启动运行时材料化。
        external_provider_error = (
            _bind_gamma_object_storage_environment(env)
            if build_only
            else _bind_gamma_external_provider_environment(env)
        )
        if external_provider_error:
            steps.append(
                {
                    "name": "gamma-external-provider-prerequisite",
                    "exitCode": 2,
                    "stdout": "",
                    "stderr": external_provider_error,
                }
            )
        if telemetry_advisory:
            steps.append(
                {
                    "kind": "observability-prerequisite",
                    "exitCode": 0,
                    "blocking": False,
                    "stdout": "product telemetry unavailable; App startup continues",
                    "stderr": telemetry_advisory,
                }
            )
        gamma_start_script = "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh"
        syntax_cmd = ["bash", "-n", gamma_start_script]
        syntax_result = run(syntax_cmd, env=env)
        steps.append(
            {
                "name": "gamma-start-script-syntax",
                "argv": syntax_cmd,
                "exitCode": syntax_result.returncode,
                "stdout": syntax_result.stdout,
                "stderr": syntax_result.stderr,
            }
        )
        if syntax_result.returncode != 0 or external_provider_error is not None:
            package_result = subprocess.CompletedProcess(
                package_cmd,
                2,
                stdout="",
                stderr=external_provider_error or syntax_result.stderr,
            )
        elif args.skip_build:
            package_result = subprocess.CompletedProcess(
                package_cmd,
                0,
                stdout="reused existing gamma deployment packages (--skip-build)",
                stderr="",
            )
        else:
            package_result = run(package_cmd, env=env)
        steps.append(
            {
                "name": "gamma-package",
                "argv": package_cmd,
                "exitCode": package_result.returncode,
                "stdout": package_result.stdout,
                "stderr": package_result.stderr,
            }
        )
        cmd = _gamma_start_command(args)
        if package_result.returncode != 0:
            result = subprocess.CompletedProcess(
                cmd,
                package_result.returncode,
                stdout=package_result.stdout,
                stderr=package_result.stderr,
            )
        else:
            try:
                _bind_gamma_packaged_service_image_refs("gamma", env)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                result = subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr=str(exc),
                )
            else:
                result = run_stage(
                    "gamma-local",
                    cmd,
                    env=env,
                    live_prefix="[gamma-local] ",
                )
        if result.returncode == 0 and not args.skip_app and not build_only:
            args.device_id = maybe_resolve_device_id(include_web=True)
            try:
                app_launch = start_app_process("gamma", args.device_id)
            except RuntimeError as exc:
                result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
                app_launch = None
            if app_launch is not None:
                gamma_tail = _tail_gamma_container_logs()
                steps.append(
                    {
                        "kind": "gamma-background-tail",
                        "exitCode": 0,
                        "stdout": "tailed gamma container logs",
                        "stderr": "",
                        "tail": gamma_tail,
                    }
                )
                tail_result = _tail_file_for_startup(
                    app_launch["log_path"],
                    process=app_launch["process"],
                    prefix=f"[{app_launch['stageHeader']} app] ",
                    idle_timeout_seconds=6.0,
                    max_follow_seconds=90.0,
                    ready_patterns=(
                        "Syncing files to device",
                        "Flutter run key commands",
                        "A Dart VM Service",
                        "The Flutter DevTools debugger",
                    ),
                    failure_patterns=(
                        "Failed to build",
                        "BUILD FAILED",
                        "Error launching application on",
                        "Lost connection to device.",
                        "Target kernel_snapshot_program failed",
                        "app launch exited before reaching steady state",
                    ),
                    ready_idle_timeout_seconds=3.0,
                )
                app_exit_code = app_launch["process"].poll()
                failure_detail = _app_launch_failure_detail(
                    tail_result,
                    default_message="gamma app launch failed",
                    process_exit_code=app_exit_code,
                )
                app_failed = failure_detail is not None
                steps.append(
                    {
                        "argv": app_launch["command"],
                        "exitCode": app_exit_code or 0,
                        "stdout": f"pid={app_launch['process'].pid}",
                        "stderr": f"log={relpath(app_launch['log_path'])}",
                        "tail": tail_result,
                    }
                )
                if app_failed:
                    result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(failure_detail))
                else:
                    cmd = app_launch["command"]
                    result = subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=f"pid={app_launch['process'].pid}",
                        stderr=f"log={relpath(app_launch['log_path'])}",
                    )
    elif requested_target == "alpha-local":
        cmd = [
            "bash",
            "quwoquan_ops/cli/alpha/start_alpha_content_release_stack.sh",
            "up",
        ]
        alpha_env = os.environ.copy()
        alpha_env["QWQ_RUN_ROOT"] = str(report_dir.resolve())
        alpha_env["QWQ_OBSERVABILITY_RUN_ROOT"] = str(
            env_observability_run_dir(env_name, report_dir.name).resolve()
        )
        if args.workload != "content-release":
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr=(
                    "alpha-local only provides the real content-release workload; "
                    "commercial planes belong to beta/gamma release verification"
                ),
            )
        else:
            result = run_stage(
                "alpha-local",
                cmd,
                env=alpha_env,
                live_prefix="[alpha] ",
            )
        background_tail = tail_alpha_background_logs()
        steps.append(
            {
                "kind": "alpha-background-tail",
                "exitCode": 0,
                "stdout": "tailed alpha background logs",
                "stderr": "",
                "tail": background_tail,
            }
        )
        if result.returncode == 0:
            alpha_content_port = canonical_port(
                load_port_manifest(),
                str(target["portProfile"]),
                "content-service",
            )
            alpha_health_url = f"http://127.0.0.1:{alpha_content_port}/healthz"
            alpha_ready, alpha_status, alpha_body, alpha_content_type = fetch_url(
                alpha_health_url,
                retry_attempts=5,
                retry_sleep_seconds=1.0,
            )
            steps.append(
                {
                    "kind": "alpha-backend-health-check",
                    "exitCode": 0 if alpha_ready else 1,
                    "stdout": "checked alpha backend health endpoint",
                    "stderr": "" if alpha_ready else alpha_body,
                    "url": alpha_health_url,
                    "statusCode": alpha_status,
                    "contentType": alpha_content_type,
                }
            )
            if not alpha_ready:
                result = subprocess.CompletedProcess(
                    cmd,
                    1,
                    stdout="",
                    stderr=f"alpha backend health check failed: {alpha_health_url}",
                )
        if result.returncode == 0:
            public_ready_attempts = _content_release_public_ready_attempts(target)
            public_bases = target.get("publicBases") or {}
            for base_key, path in (("api", "/healthz"), ("mediaImage", "/healthz")):
                base_url = str(public_bases.get(base_key) or "").rstrip("/")
                if not base_url:
                    result = subprocess.CompletedProcess(
                        cmd,
                        1,
                        stdout="",
                        stderr=f"alpha content release has no public base: {base_key}",
                    )
                    break
                public_url = f"{base_url}{path}"
                public_ready, public_status, public_body, public_content_type = fetch_url(
                    public_url,
                    retry_attempts=public_ready_attempts,
                    retry_sleep_seconds=1.0,
                    resolve_host=_local_public_connect_host(
                        topology,
                        requested_target,
                        public_url,
                    ),
                )
                steps.append(
                    {
                        "kind": "alpha-content-release-public-health",
                        "surface": base_key,
                        "exitCode": 0 if public_ready else 1,
                        "stdout": "checked alpha content release public health",
                        "stderr": "" if public_ready else public_body,
                        "url": public_url,
                        "statusCode": public_status,
                        "contentType": public_content_type,
                    }
                )
                if not public_ready:
                    result = subprocess.CompletedProcess(
                        cmd,
                        1,
                        stdout="",
                        stderr=f"alpha content release public health failed: {public_url}",
                    )
                    break
        if result.returncode == 0 and not args.skip_app:
            args.device_id = maybe_resolve_device_id(include_web=True)
            try:
                app_launch = start_app_process("alpha", args.device_id)
            except RuntimeError as exc:
                result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
                app_launch = None
            if app_launch is not None:
                tail_result = _tail_file_for_startup(
                    app_launch["log_path"],
                    process=app_launch["process"],
                    prefix=f"[{app_launch['stageHeader']} app] ",
                    idle_timeout_seconds=6.0,
                    max_follow_seconds=ALPHA_APP_FIRST_BUILD_TIMEOUT_SECONDS,
                    ready_patterns=(
                        "Syncing files to device",
                        "Flutter run key commands",
                        "A Dart VM Service",
                        "The Flutter DevTools debugger",
                    ),
                    failure_patterns=(
                        "Failed to build",
                        "BUILD FAILED",
                        "Error launching application on",
                        "Lost connection to device.",
                        "Target kernel_snapshot_program failed",
                        "app launch exited before reaching steady state",
                    ),
                    ready_idle_timeout_seconds=3.0,
                )
                app_exit_code = app_launch["process"].poll()
                failure_detail = _app_launch_failure_detail(
                    tail_result,
                    default_message="alpha app launch failed",
                    process_exit_code=app_exit_code,
                )
                steps.append(
                    {
                        "argv": app_launch["command"],
                        "exitCode": app_exit_code or 0,
                        "stdout": f"pid={app_launch['process'].pid}",
                        "stderr": f"log={relpath(app_launch['log_path'])}",
                        "tail": tail_result,
                    }
                )
                if failure_detail is not None:
                    result = subprocess.CompletedProcess(
                        cmd,
                        1,
                        stdout="",
                        stderr=str(failure_detail),
                    )
                else:
                    cmd = app_launch["command"]
                    result = subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=f"pid={app_launch['process'].pid}",
                        stderr=f"log={relpath(app_launch['log_path'])}",
                    )
    elif requested_target == "prod-sim":
        cmd = ["bash", "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh", "up"]
        result = run_stage("prod-sim", cmd, live_prefix="[prod-sim] ")
        background_tail = tail_prod_sim_background_logs()
        steps.append(
            {
                "kind": "prod-sim-background-tail",
                "exitCode": 0,
                "stdout": "tailed prod-sim background logs",
                "stderr": "",
                "tail": background_tail,
            }
        )
        if result.returncode == 0 and not args.skip_app:
            args.device_id = maybe_resolve_device_id(include_web=True)
            try:
                app_launch = start_app_process("prod-sim", args.device_id)
            except RuntimeError as exc:
                result = subprocess.CompletedProcess(cmd, 1, stdout="", stderr=str(exc))
                app_launch = None
            if app_launch is not None:
                tail_result = _tail_file_for_startup(
                    app_launch["log_path"],
                    process=app_launch["process"],
                    prefix=f"[{app_launch['stageHeader']} app] ",
                    idle_timeout_seconds=8.0,
                    max_follow_seconds=120.0,
                    ready_patterns=(
                        "Syncing files to device",
                        "Flutter run key commands",
                        "A Dart VM Service",
                        "The Flutter DevTools debugger",
                    ),
                    failure_patterns=(
                        "Failed to build",
                        "Error launching application on",
                        "Lost connection to device.",
                        "Target kernel_snapshot_program failed",
                        "app launch exited before reaching steady state",
                    ),
                    ready_idle_timeout_seconds=3.0,
                )
                app_exit_code = app_launch["process"].poll()
                failure_detail = _app_launch_failure_detail(
                    tail_result,
                    default_message="prod-sim app launch failed",
                    process_exit_code=app_exit_code,
                )
                if failure_detail is not None:
                    result = subprocess.CompletedProcess(
                        app_launch["command"],
                        1,
                        stdout="",
                        stderr=str(failure_detail),
                    )
                else:
                    announce("prod-sim", "app launch reached steady state")
                    cmd = app_launch["command"]
                    result = subprocess.CompletedProcess(
                        cmd,
                        0,
                        stdout=f"pid={app_launch['process'].pid}",
                        stderr=f"log={relpath(app_launch['log_path'])}",
                    )
                steps.append(
                    {
                        "argv": app_launch["command"],
                        "exitCode": app_exit_code or 0,
                        "stdout": f"pid={app_launch['process'].pid}",
                        "stderr": f"log={relpath(app_launch['log_path'])}",
                        "tail": tail_result,
                    }
                )
    elif requested_target == "prod-hosted":
        announce("prod-hosted", "running edge health check")
        health_args = argparse.Namespace(
            command="health",
            target="prod-hosted",
            scope="edge",
            output_format="json",
            report_dir=str(report_dir / "health"),
        )
        health = command_health(health_args)
        steps.append(
            {
                "argv": ["python3", "quwoquan_ops/cli/stackctl.py", "health", "--target", "prod-hosted", "--scope", "edge"],
                "exitCode": int(health.get("exitCode", 1)),
                "stdout": health.get("summary", ""),
                "stderr": "\n".join(health.get("details", [])),
            }
        )
        if int(health.get("exitCode", 1)) != 0:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 1,
                "summary": "stackctl up failed for prod-hosted",
                "details": ["prod-hosted health failed; run `stackctl deploy --target prod-hosted ...` first", *health.get("details", [])],
                "reportDir": relpath(report_dir),
                **timing,
            }
        if args.skip_app:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 0,
                "summary": "stackctl up completed for prod",
                "details": ["prod-hosted edge health passed; app launch skipped"],
                "reportDir": relpath(report_dir),
                **timing,
            }
        args.device_id = maybe_resolve_device_id(include_web=True)
        try:
            app_launch = start_app_process("prod", args.device_id)
        except RuntimeError as exc:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 1,
                "summary": "stackctl up failed for prod-hosted",
                "details": [str(exc)],
                "reportDir": relpath(report_dir),
                **timing,
            }
        tail_result = _tail_file_for_startup(
            app_launch["log_path"],
            process=app_launch["process"],
            prefix=f"[{app_launch['stageHeader']} app] ",
            idle_timeout_seconds=6.0,
            max_follow_seconds=60.0,
            ready_patterns=(
                "Syncing files to device",
                "Flutter run key commands",
                "A Dart VM Service",
                "The Flutter DevTools debugger",
            ),
            failure_patterns=(
                "Failed to build",
                "Error launching application on",
                "Lost connection to device.",
                "Target kernel_snapshot_program failed",
                "app launch exited before reaching steady state",
            ),
            ready_idle_timeout_seconds=3.0,
        )
        app_exit_code = app_launch["process"].poll()
        failure_detail = _app_launch_failure_detail(
            tail_result,
            default_message="prod app launch failed",
            process_exit_code=app_exit_code,
        )
        app_failed = failure_detail is not None
        if not app_failed:
            announce("prod-hosted", "app launch reached steady state")
            cmd = app_launch["command"]
            result = subprocess.CompletedProcess(
                cmd,
                0,
                stdout=f"pid={app_launch['process'].pid}",
                stderr=f"log={relpath(app_launch['log_path'])}",
            )
        else:
            result = subprocess.CompletedProcess(
                app_launch["command"],
                1,
                stdout="",
                stderr=str(failure_detail),
            )
        steps.append(
            {
                "argv": app_launch["command"],
                "exitCode": app_exit_code or 0,
                "stdout": f"pid={app_launch['process'].pid}",
                "stderr": f"log={relpath(app_launch['log_path'])}",
                "tail": tail_result,
            }
        )
    else:
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": f"stackctl up is not implemented for {requested_target}",
            "details": ["use deploy for hosted gamma/prod targets"],
            **timing,
        }

    if log_sink_redaction_values:
        steps = _redact_controlled_payload(steps, log_sink_redaction_values)
        result = subprocess.CompletedProcess(
            result.args,
            result.returncode,
            stdout=_redact_controlled_values(
                str(result.stdout or ""),
                log_sink_redaction_values,
            ),
            stderr=_redact_controlled_values(
                str(result.stderr or ""),
                log_sink_redaction_values,
            ),
        )
    timing = _finish_timing(started_monotonic, started_at)
    steps.append(
        {
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    write_json(
        report_dir / "report.json",
        {
            "command": "up",
            "target": report_target,
            "resolvedTarget": requested_target,
            "workload": args.workload,
            "commercialClaim": commercial_claim,
            "logSink": log_sink_receipt,
            "steps": steps,
            **timing,
        },
    )
    terminal_status = (
        "ok" if result.returncode == 0 else "gate_block" if result.returncode == 2 else "failed"
    )
    terminal_summary = (
        f"stackctl up completed for {report_target}"
        if result.returncode == 0
        else f"stackctl up is GATE_BLOCK for {report_target}"
        if result.returncode == 2
        else f"stackctl up failed for {report_target}"
    )
    _write_summary_bundle(
        report_dir,
        command="up",
        target=report_target,
        status=terminal_status,
        summary=terminal_summary,
        details=_command_details(result),
        extra={
            "workload": args.workload,
            "commercialClaim": commercial_claim,
            "logSink": log_sink_receipt,
        },
        timing=timing,
    )
    payload = {
        "exitCode": result.returncode,
        "summary": terminal_summary,
        "details": _command_details(result),
        "reportDir": relpath(report_dir),
        "commercialClaim": commercial_claim,
        "logSink": log_sink_receipt,
        **timing,
    }
    if local_operation_lock is not None:
        local_operation_lock.__exit__(None, None, None)
    return payload


def command_consumer_lease(args: argparse.Namespace) -> dict[str, Any]:
    action = str(args.action)
    target = str(args.target)
    device = str(getattr(args, "device", "") or "").strip()
    consumer = str(getattr(args, "consumer", "flutter-run") or "flutter-run").strip()
    if action in {"acquire", "release"} and not device:
        return {
            "exitCode": 2,
            "summary": f"consumer-lease {action} requires --device",
            "details": ["select one connected Android device explicitly"],
        }
    try:
        if action == "acquire":
            ports = [
                int(value.strip())
                for value in str(args.ports).split(",")
                if value.strip()
            ]
            with _local_stack_operation_lock(target):
                lease = acquire_consumer_lease(
                    target=target,
                    device=device,
                    consumer=consumer,
                    package_name=str(args.package_name),
                    ports=ports,
                    build_grace_seconds=int(args.build_grace_seconds),
                )
            return {
                "exitCode": 0,
                "summary": f"consumer lease acquired for {target}",
                "details": [
                    f"device={device}",
                    f"consumer={consumer}",
                    f"ports={','.join(str(port) for port in ports)}",
                    f"leaseId={lease['leaseId']}",
                    f"lease={relpath(Path(str(lease['path'])))}",
                ],
                "lease": lease,
            }
        if action == "release":
            with _local_stack_operation_lock(target):
                released = release_consumer_lease(
                    target=target,
                    device=device,
                    consumer=consumer,
                )
            return {
                "exitCode": 0,
                "summary": f"consumer lease released for {target}",
                "details": [
                    f"device={device}",
                    f"consumer={consumer}",
                    f"existed={str(released).lower()}",
                ],
            }
        leases = active_consumer_leases(target)
        return {
            "exitCode": 0,
            "summary": f"consumer lease status for {target}",
            "details": [
                (
                    f"device={lease.get('device')} consumer={lease.get('consumer')} "
                    f"state={lease.get('state')} detail={lease.get('detail')}"
                )
                for lease in leases
            ]
            or ["no active consumer lease"],
            "leases": leases,
        }
    except (RuntimeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "summary": f"consumer-lease {action} is GATE_BLOCK for {target}",
            "details": [str(exc)],
        }


def _consumer_lease_down_gate(
    args: argparse.Namespace,
    leases: list[dict[str, Any]],
) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    report_dir = resolve_report_dir(args, str(target["env"]), args.target)
    details = [
        (
            f"active consumer lease: device={lease.get('device')} "
            f"consumer={lease.get('consumer')} state={lease.get('state')} "
            f"startedAt={lease.get('startedAt')}"
        )
        for lease in leases
    ]
    details.append(
        "release the app session with stackctl consumer-lease release before down"
    )
    write_json(
        report_dir / "report.json",
        {
            "command": "down",
            "target": args.target,
            "status": "gate_block",
            "reason": "active_consumer_lease",
            "details": details,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="down",
        target=args.target,
        status="gate_block",
        summary=f"stackctl down is blocked for {args.target}",
        details=details,
    )
    return {
        "exitCode": 2,
        "summary": f"stackctl down is GATE_BLOCK for {args.target}",
        "details": details,
        "reportDir": relpath(report_dir),
    }


def command_down(args: argparse.Namespace) -> dict[str, Any]:
    if args.target not in {"alpha-local", "beta-local", "gamma-local", "prod-sim"}:
        return _command_down_unlocked(args)
    try:
        with _local_stack_operation_lock(args.target):
            leases = active_consumer_leases(args.target)
            if leases:
                return _consumer_lease_down_gate(args, leases)
            return _command_down_unlocked(args)
    except RuntimeError as exc:
        topology = load_environment_topology()
        target = get_target(topology, args.target)
        report_dir = resolve_report_dir(
            args,
            str(target["env"]),
            args.target,
        )
        details = [
            str(exc),
            "wait for the active Patrol/UAT runtime lease to finish",
        ]
        write_json(
            report_dir / "report.json",
            {
                "command": "down",
                "target": args.target,
                "status": "gate_block",
                "details": details,
            },
        )
        _write_summary_bundle(
            report_dir,
            command="down",
            target=args.target,
            status="gate_block",
            summary=f"stackctl down is blocked for {args.target}",
            details=details,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl down is GATE_BLOCK for {args.target}",
            "details": details,
            "reportDir": relpath(report_dir),
        }


def _command_down_unlocked(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)

    if args.target == "beta-local":
        cmd = ["bash", "quwoquan_ops/cli/beta/start_beta_stack.sh", "down"]
        result = run(cmd)
    elif args.target == "gamma-local":
        cmd = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh", "--down"]
        env = _gamma_env_from_port_manifest(topology, args.target)
        _bind_gamma_down_compose_placeholders(env)
        result = run(cmd, env=env)
    elif args.target == "alpha-local":
        release_cmd = [
            "bash",
            "quwoquan_ops/cli/alpha/start_alpha_content_release_stack.sh",
            "down",
        ]
        app_cmd = [
            "bash",
            "quwoquan_app/scripts/device/stop_app_instance.sh",
            "--env",
            "alpha",
            "--quiet",
        ]
        release_result = run(release_cmd)
        app_result = run(app_cmd)
        cmd = [*release_cmd, "&&", *app_cmd]
        result = next(
            (
                candidate
                for candidate in (release_result, app_result)
                if candidate.returncode != 0
            ),
            release_result,
        )
    elif args.target == "prod-sim":
        app_cmd = [
            "bash",
            "quwoquan_app/scripts/device/stop_app_instance.sh",
            "--env",
            "prod",
        ]
        app_result = run(app_cmd)
        stack_cmd = ["bash", "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh", "down"]
        stack_result = run(stack_cmd)
        cmd = [*app_cmd, "&&", *stack_cmd]
        result = stack_result if stack_result.returncode != 0 else app_result
    else:
        return {
            "exitCode": 2,
            "summary": f"stackctl down is not implemented for {args.target}",
            "details": ["hosted targets should be rolled back or redeployed via deploy commands"],
        }

    write_json(
        report_dir / "report.json",
        {
            "command": "down",
            "target": args.target,
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="down",
        target=args.target,
        status="ok" if result.returncode == 0 else "failed",
        summary=f"stackctl down {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        details=_command_details(result),
    )
    return {
        "exitCode": result.returncode,
        "summary": f"stackctl down {'completed' if result.returncode == 0 else 'failed'} for {args.target}",
        "details": _command_details(result),
        "reportDir": relpath(report_dir),
    }


def _current_runtime_health_scope(target_name: str) -> str:
    """Return the health scope promised by the most recent local runtime start.

    A content-release stack intentionally does not start the commercial Ops and
    assistant planes.  Its runtime receipt is the authority for status; a
    missing or malformed receipt remains fail-closed to the full scope.
    """
    if target_name not in {"alpha-local", "beta-local", "gamma-local"}:
        return "full"
    process_dir = target_process_dir(target_name)
    alpha_release_state = process_dir / "content-release.json"
    if target_name == "alpha-local":
        try:
            alpha_release = json.loads(alpha_release_state.read_text(encoding="utf-8"))
            if alpha_release.get("workload") == "content-release":
                return "content-import"
        except (OSError, TypeError, json.JSONDecodeError):
            return "full"
        return "full"
    stack_state_path = process_dir / "stack.state"
    try:
        for line in stack_state_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key == "workload":
                workload = value.strip().strip("'\"")
                if workload == "content-release":
                    return "content-consumer"
                if workload == "full":
                    return "full"
    except OSError:
        pass

    try:
        gamma_status = json.loads(
            (process_dir / "stack_status.json").read_text(encoding="utf-8")
        )
        if gamma_status.get("status") == "passed":
            workload = str(gamma_status.get("workload") or "").strip()
            if workload == "content-release":
                return "content-consumer"
            if workload == "full":
                return "full"
    except (OSError, TypeError, json.JSONDecodeError):
        pass

    # Managed stacks may predate the explicit workload field. Their
    # most recent parent receipt remains a best-effort fallback until restart.
    state_path = process_dir / "local_run.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        run_root = Path(str(state["runRoot"]))
        receipt = json.loads((run_root / "report.json").read_text(encoding="utf-8"))
    except (KeyError, OSError, TypeError, json.JSONDecodeError):
        return "full"
    if (
        receipt.get("command") == "up"
        and receipt.get("resolvedTarget") == target_name
        and receipt.get("workload") == "content-release"
    ):
        return "content-consumer"
    return "full"


def command_data_execution_fleet(_args: argparse.Namespace) -> dict[str, Any]:
    endpoint = resolve_data_execution_fleet_endpoint()
    return {
        "exitCode": 0,
        "summary": "stackctl data execution fleet resolved",
        "details": [f"target={endpoint.target}"],
        "fleet": endpoint.document(),
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    scope = _current_runtime_health_scope(args.target)
    health_args = argparse.Namespace(
        command="health",
        target=args.target,
        scope=scope,
        output_format=getattr(args, "output_format", "text"),
        report_dir=str(resolve_report_dir(args, str(get_target(load_environment_topology(), args.target)["env"]), args.target)),
    )
    return command_health(health_args)


def command_health(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _start_timing()
    if not hasattr(args, "scope"):
        args.scope = _current_runtime_health_scope(args.target)
    checks = _health_checks_for_target(topology, args.target, args.scope)
    policy = _health_request_policy(args.target, args.scope)
    timeout_seconds = (
        max(1.0, float(args.request_timeout_seconds))
        if getattr(args, "request_timeout_seconds", 0)
        else float(policy["timeoutSeconds"])
    )
    retry_attempts = (
        max(1, int(args.retry_attempts))
        if getattr(args, "retry_attempts", 0)
        else int(policy["retryAttempts"])
    )
    retry_sleep_seconds = (
        max(0.0, float(args.retry_sleep_seconds))
        if getattr(args, "retry_sleep_seconds", -1.0) >= 0
        else float(policy["retrySleepSeconds"])
    )
    statuses: list[dict[str, Any]] = []
    findings: list[str] = []
    stdout_sections: list[tuple[str, str]] = []
    for item in checks:
        if item.get("skip"):
            statuses.append(
                {
                    "name": item["name"],
                    "scope": item["scope"],
                    "url": item["url"],
                    "ok": True,
                    "statusCode": None,
                    "bodyPreview": str(item.get("reason", "skipped")),
                    "skipped": True,
                }
            )
            continue
        ok, status_code, body, content_type = fetch_url(
            item["url"],
            timeout=timeout_seconds,
            retry_attempts=retry_attempts,
            retry_sleep_seconds=retry_sleep_seconds,
            headers=item.get("headers"),
            resolve_host=_local_public_connect_host(topology, args.target, item["url"]),
        )
        expected_status = item.get("expectedStatus")
        if ok and expected_status is not None and status_code != int(expected_status):
            ok = False
            body = f"expected HTTP {expected_status}, got {status_code}"
        expected_content_type_prefix = str(item.get("expectedContentTypePrefix") or "")
        if (
            ok
            and expected_content_type_prefix
            and not content_type.lower().startswith(expected_content_type_prefix.lower())
        ):
            ok = False
            body = (
                f"expected Content-Type {expected_content_type_prefix}*, "
                f"got {content_type or '<empty>'}"
            )
        if not ok:
            findings.append(f"{item['scope']}/{item['name']} failed: {status_code or 'ERR'} {item['url']}")
        statuses.append(
            {
                "name": item["name"],
                "scope": item["scope"],
                "url": item["url"],
                "ok": ok,
                "statusCode": status_code,
                "contentType": content_type,
                "bodyPreview": body,
                "skipped": False,
            }
        )
        stdout_sections.append((item["name"], f"{status_code or 'ERR'} {item['url']}\n{body}"))
    script_statuses, script_stdout_sections, script_findings = _script_probes_for_target(
        topology,
        args.target,
        args.scope,
        report_dir,
    )
    statuses.extend(script_statuses)
    stdout_sections.extend(script_stdout_sections)
    findings.extend(script_findings)
    ok_count = sum(1 for item in statuses if item["ok"])
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "command": "health",
        "target": args.target,
        "scope": args.scope,
        "requestTimeoutSeconds": timeout_seconds,
        "retryAttempts": retry_attempts,
        "retrySleepSeconds": retry_sleep_seconds,
        "checks": statuses,
        "findings": findings,
        "timestamp": utc_now(),
        "scriptProbes": _script_probe_plan_for_target(topology, args.target),
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "health.json", {"target": args.target, "scope": args.scope, "checks": statuses})
    write_json(report_dir / "findings.json", {"target": args.target, "scope": args.scope, "issues": findings})
    _write_summary_bundle(
        report_dir,
        command="health",
        target=args.target,
        status="ok" if not findings else "failed",
        summary=f"stackctl health {args.target}: {ok_count}/{len(statuses)} healthy",
        details=findings or [f"scope={args.scope}", f"healthy checks={ok_count}/{len(statuses)}"],
        extra={"scope": args.scope},
        timing=timing,
    )
    _write_stdout_markdown(report_dir, stdout_sections)
    return {
        "exitCode": 0 if not findings else 1,
        "summary": f"stackctl health {args.target}: {ok_count}/{len(statuses)} healthy",
        "details": findings
        or [
            "{name} -> {status} {target}".format(
                name=item["name"],
                status=item.get("statusCode") or "OK",
                target=item.get("url") or item.get("reportPath") or item.get("bodyPreview", ""),
            ).strip()
            for item in statuses
        ],
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_inspect(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _start_timing()
    scopes = (
        ["logs", "network", "data", "metrics", "config", "security", "release"]
        if args.scope == "all"
        else [args.scope]
    )
    inspection: dict[str, Any] = {}
    findings: list[str] = []
    if "network" in scopes:
        inspection["network"] = _network_report(args.target)
    if "config" in scopes:
        inspection["config"] = {
            "target": target,
            "portProfile": target.get("portProfile"),
            "publicBases": target.get("publicBases", {}),
            "origins": target.get("origins", {}),
            "releaseState": (
                _load_release_state(PROD_RELEASE_UNIT)
                if args.target == "prod-hosted"
                else {}
            ),
        }
        if args.target == "prod-hosted":
            runtime = _prod_plane_runtime_report(
                "service",
                report_dir / "prod_rootless_service_runtime.json",
                host=str(getattr(args, "ssh_host", "") or ""),
            )
            inspection["config"]["rootlessRuntime"] = runtime
            findings.extend(_prod_plane_runtime_findings(runtime, plane="service"))
            edge_runtime = _prod_plane_runtime_report(
                "edge",
                report_dir / "prod_rootless_edge_runtime.json",
                host=str(getattr(args, "ssh_host", "") or ""),
            )
            inspection["config"]["edgeRootlessRuntime"] = edge_runtime
            findings.extend(_prod_plane_runtime_findings(edge_runtime, plane="edge"))
    if "logs" in scopes:
        inspection["logs"] = _local_log_report(args.target)
    if "data" in scopes:
        inspection["data"] = _data_report(args.target)
    if "metrics" in scopes:
        inspection["metrics"] = _metrics_report(topology, args.target)
    if "security" in scopes:
        inspection["security"] = _security_report(topology, args.target)
    if "release" in scopes:
        try:
            release_inspection, _, _ = _inspect_distribution_for_target(
                args,
                target_name=args.target,
            )
            inspection["release"] = release_inspection
            findings.extend(
                f"release distribution: {issue}"
                for issue in release_inspection.get("issues", [])
            )
        except (OSError, ValueError, OfficialDistributionReleaseError) as error:
            inspection["release"] = {
                "status": ProbeOutcome.GATE_BLOCK.value,
                "issues": [str(error)],
            }
            findings.append(f"release distribution: {error}")
    output_inspection = dict(inspection)
    if "config" in inspection:
        config_workspace = deployment_target_path(
            args.target,
            "inspection",
            report_dir.name,
        )
        config_workspace.mkdir(parents=True, exist_ok=True)
        write_json(config_workspace / "config.json", inspection["config"])
        output_inspection["config"] = {
            "status": "stored_outside_output",
            "externalConfigRef": (
                f"deployment-work://{args.target}/inspection/"
                f"{report_dir.name}/config.json"
            ),
        }
    timing = _finish_timing(started_monotonic, started_at)
    write_json(
        report_dir / "report.json",
        {
            "command": "inspect",
            "inspection": output_inspection,
            "findings": findings,
            **timing,
        },
    )
    for key, value in inspection.items():
        if key == "config":
            continue
        write_json(report_dir / f"{key}.json", value)
    write_json(
        report_dir / "findings.json",
        {"target": args.target, "scope": args.scope, "issues": findings},
    )
    details = findings or [f"{key}: collected" for key in inspection]
    status = "failed" if findings else "ok"
    summary = (
        f"stackctl inspect failed for {args.target}"
        if findings
        else f"stackctl inspect completed for {args.target}"
    )
    _write_summary_bundle(
        report_dir,
        command="inspect",
        target=args.target,
        status=status,
        summary=summary,
        details=details,
        extra={"scope": args.scope},
        timing=timing,
    )
    return {
        "exitCode": 1 if findings else 0,
        "summary": summary,
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _start_timing()
    findings: list[str] = []
    advisories: list[str] = []
    deployment_prerequisite_failed = False
    if args.target in {"beta-local", "gamma-local"}:
        try:
            load_product_telemetry_log_sink(env_name, args.target)
        except (RuntimeError, ValueError) as exc:
            deployment_prerequisite_failed = True
            findings.append(f"deployment prerequisite failed: {exc}")
    if args.target in {"prod-sim", "prod-hosted"}:
        legal_result, legal_payload = _legal_static_command("validate", env_name)
        if legal_result.returncode != 0:
            deployment_prerequisite_failed = True
            findings.append("deployment prerequisite failed: prod legal-static source is invalid")
            legal_issues = legal_payload.get("issues")
            if isinstance(legal_issues, list):
                findings.extend(
                    f"legal-static validation: {issue}"
                    for issue in legal_issues
                    if isinstance(issue, str) and issue.strip()
                )
    health_args = argparse.Namespace(
        command="health",
        target=args.target,
        scope="full",
        output_format="json",
        report_dir=str(report_dir / "health"),
    )
    health = command_health(health_args)
    if health["exitCode"] != 0:
        findings.append("health checks are failing")
    if target.get("portProfile"):
        network = _network_report(args.target)
        closed = [item["name"] for item in network["ports"] if not item["open"]]
        if closed:
            findings.append(f"ports not listening: {', '.join(closed)}")
    elif args.target == "prod-hosted":
        public_bases = target.get("publicBases") or {}
        if not public_bases.get("api"):
            findings.append("public api base url is missing")
        if not public_bases.get("productOps"):
            findings.append("product-ops base url is missing")
        if args.target == "prod-hosted":
            state = _load_release_state(PROD_RELEASE_UNIT)
            if not state:
                advisories.append(
                    "prod rollout release-state is missing (local cache empty; hosted deploy workflow can resolve current state via service-plane SSH)"
                )
            elif not state.get("to_image") or not state.get("to_config"):
                findings.append("prod release-state missing image/config target")
            runtime = _prod_plane_runtime_report(
                "service",
                report_dir / "prod_rootless_service_runtime.json",
                host=str(getattr(args, "ssh_host", "") or ""),
            )
            findings.extend(_prod_plane_runtime_findings(runtime, plane="service"))
            edge_runtime = _prod_plane_runtime_report(
                "edge",
                report_dir / "prod_rootless_edge_runtime.json",
                host=str(getattr(args, "ssh_host", "") or ""),
            )
            findings.extend(_prod_plane_runtime_findings(edge_runtime, plane="edge"))
    packages = [
        app_deployment_package_dir(env_name, target=args.target) / "report.json"
    ]
    require_package_artifacts = bool(target.get("portProfile"))
    if require_package_artifacts and not all(path.exists() for path in packages):
        findings.append("packaged app artifact is missing")
    repair_plan = []
    if findings:
        if deployment_prerequisite_failed:
            repair_plan.append(
                "ensure the declared local Provider topology and any required "
                "QWQ_DEPLOY_WORK_ROOT material are available, then rerun `stackctl doctor`"
            )
            if args.target in {"prod-sim", "prod-hosted"}:
                repair_plan.append(
                    "replace prod legal-static placeholder identity fields with approved legal facts and rerun `stackctl doctor`"
                )
        if any("health checks" in item for item in findings):
            repair_plan.append("run `stackctl health --target <target> --scope full` to confirm failing probes")
        if not deployment_prerequisite_failed and any(
            "ports not listening" in item for item in findings
        ):
            repair_plan.append("run `stackctl repair --target <target> --fix restart-stack` for local targets")
        if any("artifact" in item for item in findings):
            repair_plan.append("run `stackctl repair --target <target> --fix rebuild-packages`")
    timing = _finish_timing(started_monotonic, started_at)
    write_json(
        report_dir / "report.json",
        {
            "command": "doctor",
            "target": args.target,
            "findings": findings,
            "advisories": advisories,
            "repairPlan": repair_plan,
            "timestamp": utc_now(),
            **timing,
        },
    )
    write_json(
        report_dir / "findings.json",
        {"target": args.target, "issues": findings, "advisories": advisories},
    )
    write_json(report_dir / "repair_plan.json", {"target": args.target, "actions": repair_plan})
    _write_summary_bundle(
        report_dir,
        command="doctor",
        target=args.target,
        status="ok" if not findings else "failed",
        summary="stackctl doctor found no issues" if not findings else "stackctl doctor found issues",
        details=findings + advisories or ["no issues found"],
        timing=timing,
    )
    return {
        "exitCode": 0 if not findings else 1,
        "summary": "stackctl doctor found no issues" if not findings else "stackctl doctor found issues",
        "details": findings + advisories or ["no issues found"],
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_filter_catalog(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    environment = str(target["env"])
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "")
    report_dir = resolve_report_dir(args, environment, args.target)
    started_monotonic, started_at = _start_timing()
    if not api_base_url:
        detail = "target topology has no public API base"
        timing = _finish_timing(started_monotonic, started_at)
        _write_filter_catalog_command_report(
            report_dir=report_dir,
            target_name=args.target,
            action=args.action,
            status="gate_block",
            details=[detail],
            publish_receipt=None,
            argv=(),
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": "stackctl filter-catalog is GATE_BLOCK",
            "details": [detail],
            "reportDir": relpath(report_dir),
            **timing,
        }
    try:
        execution = execute_filter_catalog_command(
            repo_root=ROOT,
            target_name=args.target,
            environment=environment,
            api_base_url=api_base_url,
            action=args.action,
            rollback_release_id=args.rollback_release_id,
            token_env=args.token_env,
            prod_gray_activation=bool(args.prod_gray_activation),
            diagnostic_log_path=(
                target_process_dir(args.target) / "stdout" / "filter-catalog.log"
            ),
        )
    except (RuntimeError, ValueError) as exc:
        detail = str(exc)
        timing = _finish_timing(started_monotonic, started_at)
        _write_filter_catalog_command_report(
            report_dir=report_dir,
            target_name=args.target,
            action=args.action,
            status="gate_block",
            details=[detail],
            publish_receipt=None,
            argv=(),
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": "stackctl filter-catalog is GATE_BLOCK",
            "details": [detail],
            "reportDir": relpath(report_dir),
            **timing,
        }

    publish_receipt: dict[str, Any] | None = None
    details: list[str]
    status = "ok"
    exit_code = 0
    if execution.return_code == 0:
        try:
            decoded = json.loads(execution.stdout)
            if not isinstance(decoded, dict) or not bool(decoded.get("passed")):
                raise ValueError("qwq-data filter-catalog publish did not emit a passed receipt")
            publish_receipt = decoded
            details = [
                f"{args.action} release={decoded.get('releaseId', '')}",
                f"digest={decoded.get('canonicalDigest', '')}",
            ]
        except (json.JSONDecodeError, ValueError) as exc:
            status = "failed"
            exit_code = 1
            details = [f"invalid filter catalog publish receipt: {exc}"]
    else:
        status = "failed"
        exit_code = 1
        details = [
            _filter_catalog_failure_detail(
                stderr=execution.stderr,
                stdout=execution.stdout,
                return_code=execution.return_code,
            )
        ]
    timing = _finish_timing(started_monotonic, started_at)
    _write_filter_catalog_command_report(
        report_dir=report_dir,
        target_name=args.target,
        action=args.action,
        status=status,
        details=details,
        publish_receipt=publish_receipt,
        argv=execution.argv,
        timing=timing,
    )
    return {
        "exitCode": exit_code,
        "summary": (
            "stackctl filter-catalog passed"
            if exit_code == 0
            else "stackctl filter-catalog failed"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def _filter_catalog_failure_detail(
    *,
    stderr: str,
    stdout: str,
    return_code: int,
) -> str:
    """从 Data CLI 输出提取可排障摘要，不把 bearer token 写入报告。"""
    combined = "\n".join(
        part.strip() for part in (stderr or "", stdout or "") if part and part.strip()
    )
    for line in combined.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if "authorization" in lower or "bearer " in lower:
            continue
        if "gate_block" in lower or "http " in lower or "filtercatalog" in lower.replace(
            "-", ""
        ).replace("_", ""):
            return stripped
    if combined:
        first = next((line.strip() for line in combined.splitlines() if line.strip()), "")
        if first:
            return first[:300]
    return (
        f"qwq-data filter-catalog publish failed (exit={return_code}); "
        "see process/stdout/filter-catalog.log for redacted child output"
    )


def _write_filter_catalog_command_report(
    *,
    report_dir: Path,
    target_name: str,
    action: str,
    status: str,
    details: list[str],
    publish_receipt: dict[str, Any] | None,
    argv: tuple[str, ...],
    timing: dict[str, Any],
) -> None:
    payload = {
        "command": "filter-catalog",
        "target": target_name,
        "action": action,
        "status": status,
        "details": details,
        "argv": list(argv),
        "publishReceipt": publish_receipt,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": details if status != "ok" else []})
    _write_summary_bundle(
        report_dir,
        command="filter-catalog",
        target=target_name,
        status=status,
        summary=(
            "FilterCatalogRelease publish receipt verified"
            if status == "ok"
            else "FilterCatalogRelease publish is blocked or failed"
        ),
        details=details,
        extra={"action": action, "publishReceipt": publish_receipt},
        timing=timing,
    )


def command_content_readiness(args: argparse.Namespace) -> dict[str, Any]:
    """Assess one release phase against its minimal, typed capability set.

    This is deliberately not a global doctor and is never an execution-create
    precondition.  It is called when an environment is actually about to import,
    serve consumers, or claim commercial observability.
    """
    phase = ReadinessPhase(args.phase)
    policy = load_content_release_readiness_policy()
    requirement = policy.requirement_for(phase=phase, environment=args.env)
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else repo_run_dir("content-readiness", target=f"{args.env}-{phase.value}")
    )
    started_monotonic, started_at = _start_timing()
    health = command_health(
        argparse.Namespace(
            command="health",
            target=requirement.target,
            scope=requirement.health_scope,
            output_format="json",
            report_dir=str(report_dir / "health"),
        )
    )
    details = list(health.get("details", [])) if int(health["exitCode"]) != 0 else []
    executed_checks = [
        item
        for item in _read_json_object(str(report_dir / "health" / "report.json")).get("checks", [])
        if isinstance(item, dict) and str(item.get("name") or "") and not item.get("skipped")
    ]
    probes = [str(item["name"]) for item in executed_checks]
    executed_scopes = {str(item.get("scope") or "") for item in executed_checks}
    for capability in requirement.capabilities:
        binding = policy.probe_binding_for(capability)
        if binding.source is ProbeSource.HEALTH_SCOPE and binding.health_scope not in executed_scopes:
            details.append(
                f"capability {capability.value} declares probe scope "
                f"{binding.health_scope} but no probe executed for {requirement.target}"
            )
        if binding.source is ProbeSource.LOG_SINK_CONTROL:
            action = binding.control_action
            if not action:
                details.append(
                    f"capability {capability.value} has no log-sink control action"
                )
                continue
            log_sink_result = command_product_telemetry_log_sink(
                argparse.Namespace(
                    command="product-telemetry-log-sink",
                    target=requirement.target,
                    action=action,
                    output_format="json",
                    report_dir=str(report_dir / "product-telemetry-log-sink"),
                )
            )
            probes.append(f"product-telemetry-log-sink:{action}")
            if int(log_sink_result["exitCode"]) != 0:
                details.extend(
                    f"capability {capability.value}: {item}"
                    for item in log_sink_result.get("details", [])
                )
    if phase is ReadinessPhase.COMMERCIAL:
        doctor = command_doctor(
            argparse.Namespace(
                command="doctor",
                target=requirement.target,
                output_format="json",
                report_dir=str(report_dir / "commercial-prerequisites"),
            )
        )
        if int(doctor["exitCode"]) != 0:
            details.extend(str(item) for item in doctor.get("details", []))
    outcome = ProbeOutcome.PASS if not details else ProbeOutcome.GATE_BLOCK
    timing = _finish_timing(started_monotonic, started_at)
    receipt = ShipReadinessReceipt(
        policy_id=policy.policy_id,
        phase=phase,
        environment=requirement.environment,
        target=requirement.target,
        workload=requirement.workload,
        outcome=outcome,
        capabilities=requirement.capabilities,
        probes=tuple(probes),
        report_dir=relpath(report_dir),
    )
    payload = {
        "schema": "quwoquan_ops.ship_readiness_receipt",
        "policyId": receipt.policy_id,
        "phase": receipt.phase.value,
        "environment": receipt.environment,
        "target": receipt.target,
        "workload": receipt.workload,
        "outcome": receipt.outcome.value,
        "capabilities": [item.value for item in receipt.capabilities],
        "probes": list(receipt.probes),
        "reportDir": receipt.report_dir,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": details})
    _write_summary_bundle(
        report_dir,
        command="content-readiness",
        target=requirement.target,
        status="ok" if outcome is ProbeOutcome.PASS else "blocked",
        summary=(
            f"content readiness {phase.value}/{args.env} passed"
            if outcome is ProbeOutcome.PASS
            else f"content readiness {phase.value}/{args.env} is GATE_BLOCK"
        ),
        details=details or ["all required capabilities are available"],
        extra={"policyId": policy.policy_id, "phase": phase.value, "outcome": outcome.value},
        timing=timing,
    )
    return {
        **payload,
        "exitCode": 0 if outcome is ProbeOutcome.PASS else 2,
        "summary": (
            f"content readiness {phase.value}/{args.env} passed"
            if outcome is ProbeOutcome.PASS
            else f"content readiness {phase.value}/{args.env} is GATE_BLOCK"
        ),
        "details": details or ["all required capabilities are available"],
    }


def command_content_uat(args: argparse.Namespace) -> dict[str, Any]:
    """Run the release-bound homepage Patrol suite against Gamma consumer APIs."""
    report_dir = resolve_report_dir(args, "gamma", args.target)
    started_monotonic, started_at = _start_timing()
    cases_path = Path(args.release_uat_cases).expanduser()
    allowed_root = env_runs_root("gamma") / "data-release"
    try:
        resolved_cases = cases_path.resolve(strict=True)
        resolved_cases.relative_to(allowed_root.resolve(strict=True))
        command = _content_release_uat_command(
            target_name=args.target,
            release_uat_cases=resolved_cases,
            platform=args.platform,
            device_ids=list(args.device_id),
            report_dir=report_dir,
        )
    except (OSError, ValueError) as exc:
        timing = _finish_timing(started_monotonic, started_at)
        details = [str(exc)]
        payload = {
            "command": "content-uat",
            "target": args.target,
            "status": ProbeOutcome.GATE_BLOCK.value,
            "releaseUatCases": str(cases_path),
            "details": details,
            **timing,
        }
        write_json(report_dir / "report.json", payload)
        write_json(report_dir / "findings.json", {"issues": details})
        _write_summary_bundle(
            report_dir,
            command="content-uat",
            target=args.target,
            status="gate_block",
            summary="content UAT is GATE_BLOCK",
            details=details,
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": "content UAT is GATE_BLOCK",
            "details": details,
            "reportDir": relpath(report_dir),
            **timing,
        }

    result = run(
        command["argv"],
        cwd=command["cwd"],
        env=command.get("env"),
    )
    runner_report = _read_json_object(str(ROOT / str(command["reportPath"])))
    runner_status = str(runner_report.get("status") or "failed")
    status = "ok" if result.returncode == 0 and runner_status == "passed" else (
        "gate_block" if result.returncode == 2 or runner_status == "gate_block" else "failed"
    )
    details = _command_details(result)
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "command": "content-uat",
        "target": args.target,
        "status": status,
        "releaseUatCases": relpath(resolved_cases),
        "runnerReport": command["reportPath"],
        "runnerStatus": runner_status,
        "details": details,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": details if status != "ok" else []})
    _write_summary_bundle(
        report_dir,
        command="content-uat",
        target=args.target,
        status=status,
        summary=(
            "content UAT passed"
            if status == "ok"
            else "content UAT is GATE_BLOCK" if status == "gate_block" else "content UAT failed"
        ),
        details=details,
        extra={
            "releaseUatCases": relpath(resolved_cases),
            "runnerReport": command["reportPath"],
            "runnerStatus": runner_status,
        },
        timing=timing,
    )
    return {
        "exitCode": 0 if status == "ok" else 2 if status == "gate_block" else 1,
        "summary": (
            "content UAT passed"
            if status == "ok"
            else "content UAT is GATE_BLOCK" if status == "gate_block" else "content UAT failed"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_repair(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    steps: list[dict[str, Any]] = []
    if args.fix == "reclaim-build-cache":
        if args.target != "gamma-local":
            summary = "reclaim-build-cache is only available for gamma-local"
            _write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=[summary],
            )
            return {
                "exitCode": 2,
                "summary": summary,
                "details": [summary],
                "reportDir": relpath(report_dir),
            }
        before = run(["docker", "system", "df"])
        reclaim = run(["docker", "builder", "prune", "--all", "--force"])
        after = run(["docker", "system", "df"])
        steps = [
            {
                "name": "docker-storage-before",
                "exitCode": before.returncode,
                "stdout": before.stdout,
                "stderr": before.stderr,
            },
            {
                "name": "docker-unused-build-cache-prune",
                "exitCode": reclaim.returncode,
                "stdout": reclaim.stdout,
                "stderr": reclaim.stderr,
            },
            {
                "name": "docker-storage-after",
                "exitCode": after.returncode,
                "stdout": after.stdout,
                "stderr": after.stderr,
            },
        ]
        succeeded = all(step["exitCode"] == 0 for step in steps)
        summary = (
            "gamma-local unused Docker build cache reclaimed"
            if succeeded
            else "gamma-local Docker build cache reclaim failed"
        )
        write_json(
            report_dir / "report.json",
            {"command": "repair", "target": args.target, "fix": args.fix, "steps": steps},
        )
        write_json(
            report_dir / "repair_plan.json",
            {
                "target": args.target,
                "fix": args.fix,
                "actions": ["remove unused Docker build cache only"],
            },
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok" if succeeded else "failed",
            summary=summary,
            details=[
                "only unused Docker builder cache is eligible; containers, images, volumes, and release data are preserved"
            ],
        )
        return {
            "exitCode": 0 if succeeded else 1,
            "summary": summary,
            "details": [
                "only unused Docker builder cache is eligible; containers, images, volumes, and release data are preserved"
            ],
            "reportDir": relpath(report_dir),
        }
    if args.fix == "rebuild-packages":
        package_args = argparse.Namespace(
            command="package",
            env=env_name,
            service="",
            include_services=True,
            target=args.target,
            output_format="json",
            report_dir=str(report_dir / "rebuild-packages"),
        )
        payload = command_package(package_args)
        write_json(report_dir / "report.json", {"command": "repair", "nested": payload})
        write_json(
            report_dir / "repair_plan.json",
            {"target": args.target, "fix": args.fix, "actions": ["rebuild environment packages"]},
        )
        return payload
    if args.fix == "materialize-media":
        if args.target != "gamma-local":
            summary = (
                "materialize-media is only available for gamma-local curated "
                "media; prod uses a published release canary"
            )
            write_json(
                report_dir / "repair_plan.json",
                {"target": args.target, "fix": args.fix, "actions": [], "error": summary},
            )
            _write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=[summary],
            )
            return {
                "exitCode": 2,
                "summary": summary,
                "details": [summary],
                "reportDir": relpath(report_dir),
            }
        try:
            materialized = materialize_local_gamma_media(
                target_cache_dir(args.target) / "media",
            )
        except (LocalGammaMediaError, OSError) as exc:
            summary = f"gamma local media materialization failed: {exc}"
            write_json(
                report_dir / "repair_plan.json",
                {"target": args.target, "fix": args.fix, "actions": [], "error": summary},
            )
            _write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=[summary],
            )
            return {
                "exitCode": 1,
                "summary": summary,
                "details": [summary],
                "reportDir": relpath(report_dir),
            }
        write_json(report_dir / "media_materialization.json", materialized)
        write_json(
            report_dir / "repair_plan.json",
            {
                "target": args.target,
                "fix": args.fix,
                "actions": ["materialize canonical local-gamma media cache"],
            },
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok",
            summary="gamma local canonical media materialized",
            details=[
                f"copied files: {materialized['copiedFiles']}",
                f"canonical video: {materialized['publicSliceKey']}",
            ],
        )
        return {
            "exitCode": 0,
            "summary": "gamma local canonical media materialized",
            "details": [
                f"copied files: {materialized['copiedFiles']}",
                f"canonical video: {materialized['publicSliceKey']}",
            ],
            "reportDir": relpath(report_dir),
        }
    if args.fix == "restart-stack":
        # Restart is destructive for local state. Validate every external
        # deployment prerequisite before stopping a currently running stack;
        # otherwise a failed `up` would turn a partial outage into a full one.
        if args.target in {"beta-local", "gamma-local"}:
            try:
                load_product_telemetry_log_sink(env_name, args.target)
            except (RuntimeError, ValueError) as exc:
                summary = (
                    "stackctl repair restart-stack blocked before stop: "
                    f"deployment prerequisite failed: {exc}"
                )
                write_json(
                    report_dir / "report.json",
                    {
                        "command": "repair",
                        "target": args.target,
                        "fix": args.fix,
                        "steps": [],
                        "blockedBeforeStop": True,
                        "reason": str(exc),
                    },
                )
                write_json(
                    report_dir / "repair_plan.json",
                    {
                        "target": args.target,
                        "fix": args.fix,
                        "actions": [
                            "ensure the declared local Provider topology is available and QWQ_DEPLOY_WORK_ROOT is writable when materialization is required",
                            "rerun stackctl doctor before restart-stack",
                        ],
                    },
                )
                _write_summary_bundle(
                    report_dir,
                    command="repair",
                    target=args.target,
                    status="failed",
                    summary=summary,
                    details=[str(exc)],
                )
                return {
                    "exitCode": 2,
                    "summary": summary,
                    "details": [str(exc)],
                    "reportDir": relpath(report_dir),
                }
        down_args = argparse.Namespace(command="down", target=args.target, output_format="json", report_dir=str(report_dir / "down"))
        up_args = argparse.Namespace(
            command="up",
            env="",
            target=args.target,
            device_id="",
            skip_app=True,
            skip_build=False,
            workload="full",
            rollout_mode="",
            output_format="json",
            report_dir=str(report_dir / "up"),
        )
        down_payload = command_down(down_args)
        up_payload = command_up(up_args)
        steps = [down_payload, up_payload]
        write_json(report_dir / "report.json", {"command": "repair", "steps": steps})
        write_json(
            report_dir / "repair_plan.json",
            {"target": args.target, "fix": args.fix, "actions": ["stop stack", "start stack"]},
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok" if up_payload["exitCode"] == 0 else "failed",
            summary=f"stackctl repair restart-stack completed for {args.target}",
            details=[down_payload["summary"], up_payload["summary"]],
        )
        return {
            "exitCode": 0 if up_payload["exitCode"] == 0 else up_payload["exitCode"],
            "summary": f"stackctl repair restart-stack completed for {args.target}",
            "details": [down_payload["summary"], up_payload["summary"]],
            "reportDir": relpath(report_dir),
        }
    if args.fix == "reclaim-ports":
        ports = _network_report(args.target)["ports"]
        occupied = [item for item in ports if item["open"]]
        write_json(report_dir / "report.json", {"command": "repair", "target": args.target, "occupied": occupied})
        write_json(
            report_dir / "repair_plan.json",
            {
                "target": args.target,
                "fix": args.fix,
                "actions": [f"inspect listener on {item['name']}:{item['port']}" for item in occupied],
            },
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok",
            summary=f"stackctl repair reclaim-ports inspected {args.target}",
            details=[f"{item['name']} listens on {item['port']}" for item in occupied] or ["no occupied canonical ports"],
        )
        return {
            "exitCode": 0,
            "summary": f"stackctl repair reclaim-ports inspected {args.target}",
            "details": [f"{item['name']} listens on {item['port']}" for item in occupied] or ["no occupied canonical ports"],
            "reportDir": relpath(report_dir),
        }
    return {
        "exitCode": 2,
        "summary": f"unsupported repair fix: {args.fix}",
        "details": [],
    }


_REQUIRED_RELEASE_ARTIFACTS = {
    "publicWeb",
    "androidOfficialRelease",
    "opsPortal",
    "contractGraph",
    "providerBindings",
    "testEvidence",
}


def _validate_release_artifacts(
    manifest: dict[str, Any],
    *,
    artifact_root: Path,
) -> None:
    required = manifest.get("requiredArtifacts")
    artifacts = manifest.get("artifacts")
    if (
        not isinstance(required, list)
        or set(required) != _REQUIRED_RELEASE_ARTIFACTS
        or not isinstance(artifacts, dict)
        or set(artifacts) != _REQUIRED_RELEASE_ARTIFACTS
    ):
        raise RuntimeError(
            "release manifest must bind Web, Android, Portal, ContractGraph, "
            "Provider bindings, and three-layer test evidence"
        )
    for artifact_id in sorted(_REQUIRED_RELEASE_ARTIFACTS):
        artifact = artifacts.get(artifact_id)
        if (
            not isinstance(artifact, dict)
            or artifact.get("schema") != _RELEASE_ARTIFACT_SCHEMAS[artifact_id]
        ):
            raise RuntimeError(f"release manifest artifact is invalid: {artifact_id}")
        relative = Path(str(artifact.get("path") or ""))
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise RuntimeError(f"release manifest artifact path is unsafe: {artifact_id}")
        path = (artifact_root / relative).resolve()
        if artifact_root.resolve() not in path.parents or not path.is_file():
            raise RuntimeError(f"release manifest artifact is missing: {artifact_id}")
        digest_field = (
            "manifestSHA256"
            if artifact_id in {"publicWeb", "androidOfficialRelease"}
            else "contentSHA256"
        )
        expected = str(artifact.get(digest_field) or "")
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if expected != actual:
            raise RuntimeError(f"release manifest artifact digest mismatch: {artifact_id}")


def _deployable_release_manifest(
    path_value: str,
    *,
    image_version: str,
    config_version: str,
) -> tuple[Path, str, dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"release manifest unreadable: {error}") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("release manifest must be an object")
    if (
        manifest.get("schema") != "mainline-release-artifact"
        or manifest.get("status") != "deployable"
    ):
        raise RuntimeError("release manifest is not deployable")
    declared_digest = str(manifest.get("manifestDigest") or "")
    unsigned = dict(manifest)
    unsigned.pop("manifestDigest", None)
    actual_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if declared_digest != actual_digest:
        raise RuntimeError("release manifest digest mismatch")
    versions = manifest.get("versions")
    if not isinstance(versions, dict):
        raise RuntimeError("release manifest versions are missing")
    if versions.get("imageVersion") != image_version:
        raise RuntimeError("release manifest image version mismatch")
    if versions.get("configVersion") != config_version:
        raise RuntimeError("release manifest config version mismatch")
    source = manifest.get("source")
    source_sha = str(source.get("gitSha") or "") if isinstance(source, dict) else ""
    head = run(["git", "rev-parse", "HEAD"])
    if head.returncode != 0 or source_sha != head.stdout.strip():
        raise RuntimeError(
            "release manifest source SHA does not match checked-out deployment code"
        )
    governance_path = path.parent / "governance-receipt.json"
    try:
        governance = json.loads(governance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"release governance receipt is missing or invalid: {error}") from error
    if (
        not isinstance(governance, dict)
        or governance.get("schema") != "prod-release-governance-receipt"
        or governance.get("repository") != (manifest.get("source") or {}).get("repository")
        or governance.get("gitSha") != source_sha
        or governance.get("manifestDigest") != declared_digest
        or not governance.get("approvers")
        or len(set(governance.get("distinctPrincipals") or [])) < 2
    ):
        raise RuntimeError("release governance receipt does not bind this reviewed artifact")
    required_images = manifest.get("requiredImages")
    images = manifest.get("images")
    if (
        not isinstance(required_images, list)
        or not required_images
        or not isinstance(images, dict)
        or set(required_images) != set(images)
    ):
        raise RuntimeError("release manifest image set is incomplete")
    for service in required_images:
        image = images.get(service)
        if not isinstance(image, dict):
            raise RuntimeError(f"release manifest image is invalid: {service}")
        digest = str(image.get("digest") or "")
        repository = str(image.get("repository") or "")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise RuntimeError(f"release manifest image digest is invalid: {service}")
        if image.get("ref") != f"{repository}@{digest}":
            raise RuntimeError(f"release manifest image ref is not digest-pinned: {service}")
        attestations = image.get("attestations")
        if not isinstance(attestations, dict) or not all(
            attestations.get(kind) == f"oci://{repository}@{digest}#{kind}"
            for kind in ("spdxSbom", "slsaProvenance")
        ):
            raise RuntimeError(f"release manifest attestations are incomplete: {service}")
    release_files = manifest.get("releaseFiles")
    release_digests = manifest.get("releaseFileDigests")
    if not isinstance(release_files, dict) or not isinstance(release_digests, dict):
        raise RuntimeError("release manifest config digests are missing")
    for service, relative in release_files.items():
        config_path = path.parent / str(relative)
        if not config_path.is_file():
            raise RuntimeError(f"release manifest config file is missing: {service}")
        digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
        if release_digests.get(service) != f"sha256:{digest}":
            raise RuntimeError(f"release manifest config digest mismatch: {service}")
    _validate_release_artifacts(manifest, artifact_root=path.parent)
    return path, declared_digest, manifest


def _materialize_prevalidation_release_manifest(path_value: str) -> Path:
    if not path_value.startswith("oci://"):
        return Path(path_value).expanduser().resolve()
    image_ref = path_value.removeprefix("oci://").strip()
    match = re.fullmatch(
        r"ghcr\.io/[a-z0-9._/-]+/release-artifact@(sha256:([0-9a-f]{64}))",
        image_ref,
    )
    if match is None:
        raise RuntimeError(
            "prevalidation OCI release artifact must be a GHCR digest ref"
        )
    destination = deployment_target_path(
        "prod-hosted", "release-artifacts", match.group(2)
    )
    fetch = run(
        [
            "python3",
            "quwoquan_ops/cli/prod/fetch_mainline_release_artifact.py",
            "--ref",
            image_ref,
            "--output-dir",
            str(destination),
        ]
    )
    if fetch.returncode != 0:
        raise RuntimeError(
            "immutable OCI release artifact fetch failed: "
            + (fetch.stderr.strip() or fetch.stdout.strip())
        )
    return destination / "manifest.json"


def _prevalidation_release_manifest(
    path_value: str,
) -> tuple[Path, str, dict[str, Any], str, str]:
    """Validate a Service Pipeline artifact without entering release governance.

    Prevalidation deliberately does not require/read a governance receipt: it is
    non-promotable and cannot write a hosted release receipt.  It still requires
    the exact reviewed main source, a clean checkout, GHCR digest refs, SBOM/
    provenance references, and byte-identical config snapshots.
    """
    path = _materialize_prevalidation_release_manifest(path_value)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"release manifest unreadable: {error}") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("release manifest must be an object")
    if (
        manifest.get("schema") != "mainline-release-artifact"
        or manifest.get("artifactName") != "mainline-release-artifact"
        or manifest.get("status") != "deployable"
    ):
        raise RuntimeError("prevalidation requires a deployable Service Pipeline artifact")
    unsigned = dict(manifest)
    declared_digest = str(unsigned.pop("manifestDigest", ""))
    actual_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if declared_digest != actual_digest:
        raise RuntimeError("release manifest digest mismatch")
    source = manifest.get("source")
    source_sha = str(source.get("gitSha") or "") if isinstance(source, dict) else ""
    repository = str(source.get("repository") or "") if isinstance(source, dict) else ""
    run_number = source.get("runNumber") if isinstance(source, dict) else None
    if re.fullmatch(r"[0-9a-f]{40}", source_sha) is None or not repository or not isinstance(run_number, int):
        raise RuntimeError("release manifest source is not a Service Pipeline commit")
    versions = manifest.get("versions")
    image_version = str(versions.get("imageVersion") or "") if isinstance(versions, dict) else ""
    config_version = str(versions.get("configVersion") or "") if isinstance(versions, dict) else ""
    if not image_version or not config_version or image_version == "latest":
        raise RuntimeError("release manifest versions must be immutable")
    required_images = manifest.get("requiredImages")
    images = manifest.get("images")
    if (
        not isinstance(required_images, list)
        or not required_images
        or not isinstance(images, dict)
        or set(required_images) != set(images)
    ):
        raise RuntimeError("release manifest image set is incomplete")
    access = load_json_yaml(
        ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
    )
    prevalidation = access.get("prevalidation") if isinstance(access, dict) else None
    projected = prevalidation.get("planes") if isinstance(prevalidation, dict) else None
    required_prevalidation_images = {
        str(service)
        for plane in (projected or {}).values()
        if isinstance(plane, dict)
        for key in ("startupServices", "imageAndConfigOnlyServices")
        for service in (plane.get(key) or [])
    }
    if not required_prevalidation_images.issubset(set(required_images)):
        missing = sorted(required_prevalidation_images - set(required_images))
        raise RuntimeError(f"release manifest misses prevalidation images: {missing}")
    expected_prefix = f"ghcr.io/{repository.strip('/').lower()}/"
    for service in required_images:
        image = images.get(service)
        if not isinstance(image, dict):
            raise RuntimeError(f"release manifest image is invalid: {service}")
        digest = str(image.get("digest") or "")
        image_repository = str(image.get("repository") or "")
        ref = str(image.get("ref") or "")
        if (
            not image_repository.lower().startswith(expected_prefix)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            or ref != f"{image_repository}@{digest}"
            or ":latest" in ref
        ):
            raise RuntimeError(f"release image is not a GHCR digest ref: {service}")
        attestations = image.get("attestations")
        if not isinstance(attestations, dict) or not all(
            attestations.get(kind) == f"oci://{ref}#{kind}"
            for kind in ("spdxSbom", "slsaProvenance")
        ):
            raise RuntimeError(f"release manifest attestations are incomplete: {service}")
    release_files = manifest.get("releaseFiles")
    release_digests = manifest.get("releaseFileDigests")
    if not isinstance(release_files, dict) or not isinstance(release_digests, dict):
        raise RuntimeError("release manifest config digests are missing")
    for service, relative in release_files.items():
        config_path = path.parent / str(relative)
        if not config_path.is_file():
            raise RuntimeError(f"release manifest config file is missing: {service}")
        digest = "sha256:" + hashlib.sha256(config_path.read_bytes()).hexdigest()
        if release_digests.get(service) != digest:
            raise RuntimeError(f"release manifest config digest mismatch: {service}")
    _validate_release_artifacts(manifest, artifact_root=path.parent)
    head = run(["git", "rev-parse", "HEAD"])
    if head.returncode != 0 or head.stdout.strip() != source_sha:
        raise RuntimeError("release manifest source SHA does not match checked-out code")
    dirty = run(["git", "status", "--porcelain", "--untracked-files=normal"])
    if dirty.returncode != 0 or dirty.stdout.strip():
        raise RuntimeError("prod-hosted prevalidation refuses an uncommitted worktree")
    reviewed_main = run(["git", "merge-base", "--is-ancestor", source_sha, "origin/main"])
    if reviewed_main.returncode != 0:
        raise RuntimeError("release manifest source is not present on reviewed origin/main")
    return path, declared_digest, manifest, image_version, config_version


def _verify_release_registry_attestations(manifest: dict[str, Any]) -> None:
    images = manifest.get("images")
    if not isinstance(images, dict):
        raise RuntimeError("release manifest images are missing")
    for service, image in images.items():
        if not isinstance(image, dict):
            raise RuntimeError(f"release manifest image is invalid: {service}")
        ref = str(image.get("ref") or "")
        result = run(["docker", "buildx", "imagetools", "inspect", ref])
        if result.returncode != 0:
            raise RuntimeError(
                f"OCI digest/attestation lookup failed for {service}: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        evidence = f"{result.stdout}\n{result.stderr}".lower()
        if "provenance" not in evidence or "sbom" not in evidence:
            raise RuntimeError(
                f"OCI registry does not expose both provenance and SBOM for {service}"
            )


def _prod_gray_canary_contract(rollout_stage: str) -> dict[str, Any]:
    policy_path = ROOT / "quwoquan_ops" / "environments" / "prod" / "rollout" / "routing_policy.yaml"
    payload = load_json_yaml(policy_path)
    policy = payload.get("policy") if isinstance(payload, dict) else None
    if not isinstance(policy, dict) or not policy.get("enabled"):
        raise RuntimeError("production gray routing policy must be enabled")
    canary = policy.get("syntheticCanary")
    if not isinstance(canary, dict):
        raise RuntimeError("production gray routing policy requires syntheticCanary")
    headers = canary.get("headers")
    requests = int(canary.get("requests") or 0)
    path = str(canary.get("path") or "").strip()
    if (
        not isinstance(headers, dict)
        or requests < 100
        or not path.startswith("/")
    ):
        raise RuntimeError("production gray synthetic canary contract is incomplete")
    stage_dimensions = policy.get("stageDimensions")
    if not isinstance(stage_dimensions, dict):
        raise RuntimeError("production gray routing stageDimensions are missing")
    dimensions = stage_dimensions.get(rollout_stage)
    if not isinstance(dimensions, dict):
        raise RuntimeError(
            f"production gray routing dimensions are missing for stage {rollout_stage}"
        )
    header_dimensions = {
        "X-Client-App-Version": "appVersions",
        "X-Client-User-Id": "userIds",
        "X-Client-Region-Code": "provinces",
        "X-Client-Carrier": "carriers",
    }
    matching_headers = {
        header: str(headers.get(header) or "")
        for header, dimension in header_dimensions.items()
        if str(headers.get(header) or "")
        in {str(value) for value in dimensions.get(dimension) or []}
    }
    if rollout_stage == "full":
        # full 阶段没有灰度路由维度；canary 只验证稳定面 healthz，不能把此前
        # stage 的用户/地区 header 误报为仍在灰度。
        return {
            **canary,
            "headers": {
                key: value
                for key, value in headers.items()
                if key not in header_dimensions
            },
            "rolloutStage": rollout_stage,
            "expectedRoute": "stable",
        }
    if not matching_headers:
        raise RuntimeError("synthetic canary headers do not match any enabled gray dimension")
    return {
        **canary,
        "rolloutStage": rollout_stage,
        "expectedRoute": "gray",
    }


def _emit_prod_gray_canary_traffic(canary: dict[str, Any]) -> dict[str, Any]:
    topology = load_environment_topology()
    api_base = str(
        ((((topology or {}).get("targets") or {}).get("prod-hosted") or {}).get("publicBases") or {}).get("api")
        or ""
    ).rstrip("/")
    if not api_base.startswith("https://"):
        raise RuntimeError("prod synthetic canary requires HTTPS api public base")
    path = str(canary["path"])
    requests = int(canary["requests"])
    interval_ms = int(canary.get("intervalMs") or 0)
    headers = {str(key): str(value) for key, value in canary["headers"].items()}
    started = time.monotonic()
    for index in range(requests):
        request = urllib.request.Request(
            f"{api_base}{path}",
            headers={**headers, "User-Agent": "quwoquan-release-canary/1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(
                        f"synthetic canary request {index + 1} returned {response.status}"
                    )
        except OSError as error:
            raise RuntimeError(
                f"synthetic canary request {index + 1}/{requests} failed: {error}"
            ) from error
        if interval_ms > 0 and index + 1 < requests:
            time.sleep(interval_ms / 1000)
    return {
        "source": "prod-public-api",
        "path": path,
        "requests": requests,
        "headers": sorted(headers),
        "durationMs": int((time.monotonic() - started) * 1000),
    }


def _prometheus_query_value(base_url: str, expression: str) -> float:
    request_url = f"{base_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': expression})}"
    request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Prometheus SLO readback request failed: {error}") from error
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus SLO readback returned non-success: {payload.get('error', 'unknown error')}")
    results = ((payload.get("data") or {}).get("result") or [])
    if len(results) != 1:
        raise RuntimeError(f"Prometheus SLO readback expected one sample, got {len(results)}")
    value = (results[0].get("value") or [])
    if len(value) != 2:
        raise RuntimeError("Prometheus SLO readback sample is malformed")
    try:
        return float(value[1])
    except (TypeError, ValueError) as error:
        raise RuntimeError("Prometheus SLO readback value is not numeric") from error


def _read_prometheus_slo(base_url: str, service: str) -> dict[str, Any]:
    policy_path = ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    policy = load_json_yaml(policy_path)
    if not isinstance(policy, dict) or not isinstance(policy.get("readback"), dict):
        raise RuntimeError(f"invalid SLO readback policy: {policy_path}")
    readback_policy = policy["readback"]
    window = str(readback_policy.get("window") or "").strip()
    minimum_samples = int(readback_policy.get("minimum_samples") or 0)
    if not window or minimum_samples <= 0:
        raise RuntimeError(f"SLO readback policy requires window/minimum_samples: {policy_path}")
    labels: list[str] = []
    if service.strip():
        labels.append(f'service="{service.strip()}"')
    service_label = "{" + ",".join(labels) + "}"
    error_labels = [*labels, 'status=~"5.."']
    error_selector = "{" + ",".join(error_labels) + "}"
    queries = {
        "errorRate": (
            f"sum(rate(http_server_requests_total{error_selector}[{window}]))"
            f" / (sum(rate(http_server_requests_total{service_label}[{window}])) + 0.001)"
        ),
        "p95Ms": (
            f"histogram_quantile(0.95, sum(rate(http_server_duration_seconds_bucket"
            f"{service_label}[{window}])) by (le)) * 1000"
        ),
        "redisErrorRate": (
            f'sum(rate(redis_operations_total{{status="error"}}[{window}]))'
            f" / (sum(rate(redis_operations_total[{window}])) + 0.001)"
        ),
        "sampleCount": f"sum(increase(http_server_requests_total{service_label}[{window}]))",
    }
    values = {name: _prometheus_query_value(base_url, expression) for name, expression in queries.items()}
    if values["sampleCount"] < minimum_samples:
        raise RuntimeError(
            f"Prometheus SLO readback has insufficient samples: "
            f"{values['sampleCount']} < {minimum_samples}"
        )
    result: dict[str, Any] = {
        "source": "prometheus",
        "baseUrl": base_url.rstrip("/"),
        "queriedAt": utc_now(),
        "window": window,
        "minimumSamples": minimum_samples,
        "queries": queries,
        "values": values,
    }
    recommendation = _read_recommendation_slo(
        base_url, service, window, readback_policy.get("recommendation")
    )
    if recommendation is not None:
        result["recommendation"] = recommendation
    return result


def _slo_settle_seconds(stage: str) -> int:
    policy_path = ROOT / "quwoquan_ops/policies/config-release/slo_thresholds.yaml"
    policy = load_json_yaml(policy_path)
    readback = policy.get("readback") if isinstance(policy, dict) else None
    settle = readback.get("settle_seconds") if isinstance(readback, dict) else None
    if not isinstance(settle, dict):
        raise RuntimeError(f"SLO readback policy requires settle_seconds: {policy_path}")
    seconds = int(settle.get(stage) or 0)
    if seconds < 0:
        raise RuntimeError(f"SLO settle seconds cannot be negative for {stage}")
    return seconds


def _read_recommendation_slo(
    base_url: str,
    service: str,
    window: str,
    rec_policy: Any,
) -> dict[str, Any] | None:
    """N2-5：prod gray readback 纳入推荐业务指标（空 feed 率 / 负反馈率 / CTR）。

    仅对策略声明的推荐服务（content-service）生效；空 feed 率与负反馈率超
    critical 抛错阻断放量，CTR 在 impression 样本不足时诚实跳过（只观察不拦截）。
    """
    if not isinstance(rec_policy, dict):
        return None
    if service.strip() != str(rec_policy.get("service") or "").strip():
        return None
    # 指标名与 runtime/recommendation/observability.go 的真实 emitter 对齐
    # （recommendation_alert_metric_existence 契约同源）；杜绝死查询。
    queries = {
        "emptyFeedRate": (
            f"sum(increase(rec_pipeline_empty_results_total[{window}]))"
            f" / (sum(increase(rec_pipeline_requests_total[{window}])) + 0.001)"
        ),
        "negativeFeedbackRate": (
            f"sum(increase(recommendation_feed_negative_feedback_total[{window}]))"
            f" / (sum(increase(recommendation_feed_impressed_total[{window}])) + 0.001)"
        ),
        "impressionCount": f"sum(increase(recommendation_feed_impressed_total[{window}]))",
        "ctr": (
            f'sum(increase(recommendation_feed_engagement_total{{action="click"}}[{window}]))'
            f" / (sum(increase(recommendation_feed_impressed_total[{window}])) + 0.001)"
        ),
    }
    values = {
        name: _prometheus_query_value(base_url, expression)
        for name, expression in queries.items()
    }
    breaches: list[str] = []
    warnings: list[str] = []
    for metric, value_key in (
        ("empty_feed_rate", "emptyFeedRate"),
        ("negative_feedback_rate", "negativeFeedbackRate"),
    ):
        thresholds = rec_policy.get(metric)
        if not isinstance(thresholds, dict):
            continue
        critical = float(thresholds.get("critical") or 0)
        warn = float(thresholds.get("warn") or 0)
        value = values[value_key]
        if critical > 0 and value >= critical:
            breaches.append(f"{metric}={value:.4f} >= critical {critical}")
        elif warn > 0 and value >= warn:
            warnings.append(f"{metric}={value:.4f} >= warn {warn}")
    min_impressions = int(rec_policy.get("min_impressions") or 0)
    ctr_evaluated = values["impressionCount"] >= min_impressions > 0
    if ctr_evaluated:
        ctr_floor = float(rec_policy.get("ctr_floor_warn") or 0)
        if ctr_floor > 0 and values["ctr"] < ctr_floor:
            warnings.append(f"ctr={values['ctr']:.4f} < floor {ctr_floor}")
    if breaches:
        raise RuntimeError(
            "recommendation SLO readback breached critical thresholds: "
            + "; ".join(breaches)
        )
    return {
        "queries": queries,
        "values": values,
        "ctrEvaluated": ctr_evaluated,
        "warnings": warnings,
    }


def _decision_from_slo_output(output: str, rollout_stage: str) -> tuple[str, str]:
    if "decision=pause" in output:
        if rollout_stage == "full":
            return "rollback", "full rollout cannot remain paused on warning SLO"
        return "pause", "slo gate decision=pause"
    if "decision=rollback" in output:
        return "rollback", "slo gate decision=rollback"
    return "continue", ""


def _command_deploy_with_lock(args: argparse.Namespace) -> dict[str, Any]:
    report_dir = resolve_report_dir(args, "prod" if args.target == "prod-hosted" else "gamma", args.target)
    started_monotonic, started_at = _start_timing()
    post_deploy_checks: list[dict[str, Any]] = []
    rollback_post_checks: list[dict[str, Any]] = []
    deploy_result: Any | None = None
    rollback_result: Any | None = None
    rollback_reason = ""
    rollback_state: dict[str, str] | None = None
    rollout_decision = "continue"
    rollout_stage = ""
    dry_run_requested = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    slo_readback: dict[str, Any] | None = None
    prometheus_url = ""
    release_manifest_path: Path | None = None
    release_manifest_digest = ""
    release_manifest_payload: dict[str, Any] = {}
    expected_generation = 0
    transition_action = "advance"
    release_receipt_id = ""
    committed_release_state: dict[str, str] | None = None
    release_receipt_path: Path | None = None
    release_state_snapshot: dict[str, str] = {}
    release_candidate_digests: dict[str, str] = {}
    last_good_target: dict[str, str] = {}
    gray_canary_contract: dict[str, Any] | None = None
    gray_canary_traffic: dict[str, Any] | None = None
    provider_readiness: dict[str, Any] = {}
    if args.target == "prod-hosted":
        try:
            rollout_stage = _resolve_prod_rollout_stage(args.step, args.stage)
        except ValueError as error:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": f"stackctl deploy rollout stage invalid: {error}",
                "details": [],
                **timing,
            }
        if rollout_stage == "gray-initial":
            provider_preflight = _run_provider_readiness_preflight("prod", report_dir)
            provider_readiness = provider_preflight["report"]
            if provider_preflight["exitCode"] != 0:
                timing = _finish_timing(started_monotonic, started_at)
                payload = {
                    "status": ProbeOutcome.GATE_BLOCK.value,
                    "command": "deploy",
                    "target": args.target,
                    "rolloutStage": rollout_stage,
                    "providerReadiness": provider_readiness,
                    "steps": [
                        {
                            "kind": provider_preflight["kind"],
                            "environment": "prod",
                            "argv": provider_preflight["argv"],
                            "exitCode": provider_preflight["exitCode"],
                            "reportPath": provider_preflight["reportPath"],
                            "details": provider_preflight["details"],
                        }
                    ],
                    **timing,
                }
                write_json(report_dir / "report.json", payload)
                write_json(
                    report_dir / "findings.json",
                    {"target": args.target, "issues": provider_preflight["details"]},
                )
                _write_summary_bundle(
                    report_dir,
                    command="deploy",
                    target=args.target,
                    status="blocked",
                    summary="stackctl deploy is GATE_BLOCK by Provider readiness",
                    details=provider_preflight["details"],
                    timing=timing,
                )
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy is GATE_BLOCK by Provider readiness",
                    "details": provider_preflight["details"],
                    "reportDir": relpath(report_dir),
                    **timing,
                }
        prometheus_url = str(
            getattr(args, "prometheus_url", "")
            or os.environ.get("PROMETHEUS_URL", "")
        ).strip()
        if not dry_run_requested and not prometheus_url:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: non-dry-run prod rollout requires PROMETHEUS_URL readback",
                "details": [],
                **timing,
            }
        if not dry_run_requested:
            try:
                gray_canary_contract = _prod_gray_canary_contract(rollout_stage)
            except RuntimeError as error:
                timing = _finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy blocked: gray canary contract is invalid",
                    "details": [str(error)],
                    **timing,
                }
        required = [
            args.service,
            args.from_image,
            args.to_image,
            args.from_config,
            args.to_config,
            args.step,
        ]
        if not all(required):
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy prod-hosted requires service/image/config/step arguments",
                "details": [],
                **timing,
            }
        manifest_value = str(
            getattr(args, "release_manifest", "")
            or os.environ.get("RELEASE_MANIFEST", "")
        ).strip()
        if not manifest_value:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: immutable release manifest is required",
                "details": [],
                **timing,
            }
        try:
            (
                release_manifest_path,
                release_manifest_digest,
                release_manifest_payload,
            ) = _deployable_release_manifest(
                manifest_value,
                image_version=args.to_image,
                config_version=args.to_config,
            )
            if not dry_run_requested:
                release_candidate_digests = _required_release_candidate_digests(
                    args,
                    release_manifest_payload,
                )
            if dry_run_requested:
                release_state_snapshot = _load_release_state(args.service)
            else:
                release_state_snapshot, _ = _fetch_hosted_release_ledger_projection(
                    args.service,
                    allow_uninitialized=rollout_stage == "gray-initial",
                )
            last_good_target = {
                "image": release_state_snapshot.get("to_image", args.from_image),
                "config": release_state_snapshot.get("to_config", args.from_config),
            }
            transition_action, expected_generation = _validate_release_transition(
                release_state_snapshot,
                from_image=args.from_image,
                to_image=args.to_image,
                from_config=args.from_config,
                to_config=args.to_config,
                stage=rollout_stage,
                manifest_digest=release_manifest_digest,
            )
            if not dry_run_requested:
                _verify_release_registry_attestations(release_manifest_payload)
                _archive_release_artifact(
                    release_manifest_path,
                    release_manifest_digest,
                )
        except RuntimeError as error:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: release manifest or ledger validation failed",
                "details": [str(error)],
                **timing,
            }
        release_receipt_id = hashlib.sha256(
            (
                f"{args.service}\0{release_manifest_digest}\0{rollout_stage}\0"
                f"{expected_generation + (0 if transition_action == 'replay' else 1)}"
            ).encode("utf-8")
        ).hexdigest()
        if transition_action == "replay" and not dry_run_requested:
            release_receipt_id = release_state_snapshot.get("receipt_id", "")
            receipt_path = (
                _release_state_dir() / "receipts" / f"{release_receipt_id}.json"
            )
            if not release_receipt_id or not receipt_path.is_file():
                timing = _finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy blocked: committed ledger receipt is missing",
                    "details": [str(receipt_path)],
                    **timing,
                }
            try:
                release_receipt_path = _sync_release_ledger_projection(
                    args.service,
                    release_receipt_id,
                )
            except RuntimeError as error:
                timing = _finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy replay could not sync release projection",
                    "details": [str(error)],
                    **timing,
                }
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 0,
                "summary": "stackctl deploy replay matched committed release ledger",
                "details": [f"receipt: {release_receipt_id}"],
                "releaseReceiptId": release_receipt_id,
                **timing,
            }
        package_cmd = [
            "python3",
            "quwoquan_ops/cli/stackctl.py",
            "package",
            "--env",
            "prod",
            "--include-services",
        ]
        package_result = run(package_cmd)
        if package_result.returncode != 0:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": package_result.returncode,
                "summary": "stackctl deploy blocked: prod environment package failed",
                "details": [package_result.stderr.strip() or package_result.stdout.strip()],
                **timing,
            }
        cmd: list[str] = []
        deploy_result = run(
            ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
            env={
                "CLOUD_PROVIDER": args.cloud_provider,
                "SERVICE": args.service,
                "IMAGE_VERSION": args.to_image,
                "CONFIG_VERSION": args.to_config,
                "PREVIOUS_IMAGE_VERSION": args.from_image,
                "ROLLOUT_STAGE": rollout_stage,
                "DRY_RUN": args.dry_run,
                "RELEASE_MANIFEST": str(release_manifest_path),
                "RELEASE_MANIFEST_DIGEST": release_manifest_digest,
            },
        )
        if deploy_result.returncode != 0:
            result = subprocess.CompletedProcess(
                ["prod-apply"],
                deploy_result.returncode,
                stdout="decision=rollback",
                stderr=(
                    "production apply failed; stackctl will rollback every plane: "
                    + (deploy_result.stderr.strip() or deploy_result.stdout.strip())
                ),
            )
        elif dry_run_requested:
            result = subprocess.CompletedProcess(
                cmd,
                0,
                stdout="prod dry-run skipped config_release_apply_stage.sh and remained read-only",
                stderr="",
            )
        else:
            try:
                if gray_canary_contract is None:
                    raise RuntimeError("gray canary contract was not loaded")
                gray_canary_traffic = _emit_prod_gray_canary_traffic(
                    gray_canary_contract
                )
                settle_seconds = _slo_settle_seconds(rollout_stage)
                if settle_seconds:
                    time.sleep(settle_seconds)
                slo_service = (
                    "content-service"
                    if args.service == PROD_RELEASE_UNIT
                    else args.service
                )
                slo_readback = _read_prometheus_slo(prometheus_url, slo_service)
                slo_readback["canaryTraffic"] = gray_canary_traffic
            except RuntimeError as error:
                slo_readback = {
                    "canaryTraffic": gray_canary_traffic or {},
                    "error": str(error),
                }
                result = subprocess.CompletedProcess(
                    ["prometheus-slo-readback"],
                    11,
                    stdout="decision=rollback",
                    stderr=str(error),
                )
            else:
                args.error_rate = str(slo_readback["values"]["errorRate"])
                args.p95_ms = str(slo_readback["values"]["p95Ms"])
                args.redis_error_rate = str(slo_readback["values"]["redisErrorRate"])
                cmd = [
                    "bash",
                    "quwoquan_ops/cli/prod/config_release_apply_stage.sh",
                    "--service",
                    args.service,
                    "--from-image",
                    args.from_image,
                    "--to-image",
                    args.to_image,
                    "--from-config",
                    args.from_config,
                    "--to-config",
                    args.to_config,
                    "--step",
                    args.step,
                    "--error-rate",
                    args.error_rate,
                    "--p95-ms",
                    args.p95_ms,
                    "--redis-error-rate",
                    args.redis_error_rate,
                ]
                result = run(cmd)
    run_post_deploy_checks = result.returncode == 0 and not (
        args.target == "prod-hosted" and dry_run_requested
    )
    if run_post_deploy_checks:
        def _deploy_health_args(target_name: str, scope_name: str, out_dir: Path) -> argparse.Namespace:
            return argparse.Namespace(
                command="health",
                target=target_name,
                scope=scope_name,
                output_format="json",
                report_dir=str(out_dir),
                request_timeout_seconds=0,
                retry_attempts=0,
                retry_sleep_seconds=-1.0,
            )

        for nested_command, nested_scope in (
            ("health", "full"),
            ("inspect", "all"),
            ("doctor", ""),
        ):
            nested_dir = report_dir / nested_command
            if nested_command == "health":
                nested_args = _deploy_health_args(args.target, nested_scope, nested_dir)
                post_deploy_checks.append(command_health(nested_args))
            elif nested_command == "inspect":
                nested_args = argparse.Namespace(
                    command="inspect",
                    target=args.target,
                    scope=nested_scope,
                    output_format="json",
                    report_dir=str(nested_dir),
                )
                post_deploy_checks.append(command_inspect(nested_args))
            else:
                nested_args = argparse.Namespace(
                    command="doctor",
                    target=args.target,
                    output_format="json",
                    report_dir=str(nested_dir),
                )
                post_deploy_checks.append(command_doctor(nested_args))
        if args.target == "prod-hosted" and rollout_stage == "gray-initial":
            nested_dir = report_dir / "environment-page-smoke"
            nested_args = argparse.Namespace(
                command="verify",
                env="",
                target=args.target,
                kind="topology",
                profile="release",
                output_format="json",
                report_dir=str(nested_dir),
            )
            post_deploy_checks.append(command_verify(nested_args))
    post_deploy_failures = [
        item["summary"]
        for item in post_deploy_checks
        if int(item.get("exitCode", 0) or 0) != 0
    ]
    final_exit_code = result.returncode
    findings = list(post_deploy_failures)
    if final_exit_code == 0 and post_deploy_failures:
        final_exit_code = 1
    if args.target == "prod-hosted":
        stdout_combined = "\n".join(filter(None, [result.stdout, result.stderr]))
        slo_decision, slo_reason = _decision_from_slo_output(
            stdout_combined,
            rollout_stage,
        )
        if slo_decision != "continue":
            rollout_decision = slo_decision
            rollback_reason = slo_reason if slo_decision == "rollback" else ""
            findings.append(slo_reason)
        elif final_exit_code != 0 and post_deploy_failures:
            rollback_reason = "post-deploy checks failed"
            findings.append(rollback_reason)
        if dry_run_requested and result.returncode == 0:
            findings.append("prod dry-run: skipped hosted post-deploy health/inspect/doctor and rollback")
        if rollback_reason and not dry_run_requested:
            rollback_env = {
                "CLOUD_PROVIDER": args.cloud_provider,
                "SERVICE": args.service,
                "IMAGE_VERSION": args.from_image,
                "CONFIG_VERSION": args.from_config,
                "PREVIOUS_IMAGE_VERSION": args.to_image,
                "ROLLOUT_STAGE": "full",
                "DRY_RUN": "false",
                "PROD_IMAGE_DELIVERY_MODE": "skip",
            }
            rollback_result = run(
                ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
                env=rollback_env,
            )
            if rollback_result.returncode == 0:
                for nested_command, nested_scope in (("health", "full"),):
                    nested_dir = report_dir / "rollback" / nested_command
                    if nested_command == "health":
                        nested_args = argparse.Namespace(
                            command="health",
                            target=args.target,
                            scope=nested_scope,
                            output_format="json",
                            report_dir=str(nested_dir),
                        )
                        rollback_post_checks.append(command_health(nested_args))
                rollback_failures = [
                    item["summary"]
                    for item in rollback_post_checks
                    if int(item.get("exitCode", 0) or 0) != 0
                ]
                findings.extend(f"rollback {item}" for item in rollback_failures)
                if rollback_failures and final_exit_code == 0:
                    final_exit_code = 1
                rollback_decision = (
                    "rollback_failed" if rollback_failures else "rolled_back"
                )
                rollback_state, release_receipt_path = _commit_hosted_release_transition(
                    service=args.service,
                    from_image=args.to_image,
                    to_image=args.from_image,
                    from_config=args.to_config,
                    to_config=args.from_config,
                    step="100",
                    stage="full",
                    decision=rollback_decision,
                    manifest_digest=release_manifest_digest,
                    expected_generation=expected_generation,
                    receipt_id=release_receipt_id,
                    slo_readback=slo_readback,
                    candidate_digests=release_candidate_digests,
                    last_good_target=last_good_target,
                    post_deploy_checks=post_deploy_checks + rollback_post_checks,
                    rollback_outcome=rollback_decision,
                )
                committed_release_state = rollback_state
            else:
                findings.append("live rollback apply failed")
                final_exit_code = rollback_result.returncode
                committed_release_state, release_receipt_path = _commit_hosted_release_transition(
                    service=args.service,
                    from_image=args.from_image,
                    to_image=args.to_image,
                    from_config=args.from_config,
                    to_config=args.to_config,
                    step=args.step,
                    stage=rollout_stage,
                    decision="rollback_failed",
                    manifest_digest=release_manifest_digest,
                    expected_generation=expected_generation,
                    receipt_id=release_receipt_id,
                    slo_readback=slo_readback,
                    candidate_digests=release_candidate_digests,
                    last_good_target=last_good_target,
                    post_deploy_checks=post_deploy_checks + rollback_post_checks,
                    rollback_outcome="rollback_failed",
                )
        elif rollout_decision == "pause" and final_exit_code == 10:
            final_exit_code = 10
            if not dry_run_requested:
                committed_release_state, release_receipt_path = _commit_hosted_release_transition(
                    service=args.service,
                    from_image=args.from_image,
                    to_image=args.to_image,
                    from_config=args.from_config,
                    to_config=args.to_config,
                    step=args.step,
                    stage=rollout_stage,
                    decision="pause",
                    manifest_digest=release_manifest_digest,
                    expected_generation=expected_generation,
                    receipt_id=release_receipt_id,
                    slo_readback=slo_readback,
                    candidate_digests=release_candidate_digests,
                    last_good_target=last_good_target,
                    post_deploy_checks=post_deploy_checks,
                    rollback_outcome="not_triggered",
                )
        elif final_exit_code == 0 and not dry_run_requested:
            committed_last_good_target = (
                {"image": args.to_image, "config": args.to_config}
                if rollout_stage == "full"
                else last_good_target
            )
            committed_release_state, release_receipt_path = _commit_hosted_release_transition(
                service=args.service,
                from_image=args.from_image,
                to_image=args.to_image,
                from_config=args.from_config,
                to_config=args.to_config,
                step=args.step,
                stage=rollout_stage,
                decision="continue",
                manifest_digest=release_manifest_digest,
                expected_generation=expected_generation,
                receipt_id=release_receipt_id,
                slo_readback=slo_readback,
                candidate_digests=release_candidate_digests,
                last_good_target=committed_last_good_target,
                post_deploy_checks=post_deploy_checks,
                rollback_outcome="not_triggered",
            )
        if committed_release_state is not None:
            release_receipt_id = committed_release_state["receipt_id"]
            release_receipt_path = _sync_release_ledger_projection(
                args.service,
                release_receipt_id,
            )
    timing = _finish_timing(started_monotonic, started_at)
    write_json(
        report_dir / "report.json",
        {
            "command": "deploy",
            "target": args.target,
            "argv": cmd,
            "exitCode": final_exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "rolloutStage": rollout_stage,
            "rolloutDecision": rollout_decision,
            "releaseManifestDigest": release_manifest_digest,
            "releaseReceiptId": release_receipt_id,
            "releaseReceiptRef": (
                f"receipt:hosted:{release_receipt_id}"
                if release_receipt_path is not None and release_receipt_id
                else ""
            ),
            "releaseReceiptAuthority": (
                "prod-hosted-service-plane"
                if release_receipt_path is not None
                else ""
            ),
            "releaseReceiptPath": (
                str(release_receipt_path) if release_receipt_path is not None else ""
            ),
            "releaseState": committed_release_state or {},
            "wiredWorkloads": _prod_rollout_workloads() if args.target == "prod-hosted" else [],
            "providerReadiness": provider_readiness,
            "postDeployChecks": post_deploy_checks,
            "postDeployFailures": post_deploy_failures,
            "rollbackPostChecks": rollback_post_checks,
            "sloReadback": slo_readback or {},
            "dryRun": dry_run_requested,
            "rollback": {
                "triggered": bool(rollback_reason),
                "reason": rollback_reason,
                "result": (
                    {
                        "exitCode": rollback_result.returncode,
                        "stdout": rollback_result.stdout,
                        "stderr": rollback_result.stderr,
                    }
                    if rollback_result is not None
                    else {}
                ),
                "releaseState": rollback_state or {},
            },
            **timing,
        },
    )
    write_json(report_dir / "findings.json", {"target": args.target, "issues": findings})
    _write_summary_bundle(
        report_dir,
        command="deploy",
        target=args.target,
        status="ok" if final_exit_code == 0 else "failed",
        summary=f"stackctl deploy {'completed' if final_exit_code == 0 else 'failed'} for {args.target}",
        details=(_command_details(deploy_result) if args.target == "prod-hosted" else []) + _command_details(result) + ([f"rollout stage: {rollout_stage}"] if args.target == "prod-hosted" else []) + [
            f"post-deploy {item['summary']}"
            for item in post_deploy_checks
        ] + [
            f"rollback-check {item['summary']}"
            for item in rollback_post_checks
        ] + ([f"wired workloads: {', '.join(w['rolloutRef'] for w in _prod_rollout_workloads()) or 'none'}"] if args.target == "prod-hosted" else []) + ([f"rollout decision: {rollout_decision}"] if args.target == "prod-hosted" else []) + ([f"rollback triggered: {rollback_reason}"] if rollback_reason else []) + (["dry-run remained read-only"] if dry_run_requested and args.target == "prod-hosted" else []),
        timing=timing,
    )
    _write_stdout_markdown(
        report_dir,
        [
            ("deploy", "\n".join(filter(None, [result.stdout, result.stderr]))),
            *(
                [("prod-apply", "\n".join(filter(None, [deploy_result.stdout, deploy_result.stderr])))]
                if args.target == "prod-hosted"
                else []
            ),
            *(
                [("prod-rollback", "\n".join(filter(None, [rollback_result.stdout, rollback_result.stderr])))]
                if rollback_result is not None
                else []
            ),
        ],
    )
    return {
        "exitCode": final_exit_code,
        "summary": f"stackctl deploy {'completed' if final_exit_code == 0 else 'failed'} for {args.target}",
        "details": (_command_details(deploy_result) if args.target == "prod-hosted" else []) + _command_details(result) + findings + [
            f"rollback-check {item['summary']}"
            for item in rollback_post_checks
        ] + ([f"rollout decision: {rollout_decision}"] if args.target == "prod-hosted" else []) + ([f"rollback triggered: {rollback_reason}"] if rollback_reason else []) + (["dry-run remained read-only"] if dry_run_requested and args.target == "prod-hosted" else []),
        "reportDir": relpath(report_dir),
        **timing,
    }


def _command_deploy_service_environment(args: argparse.Namespace) -> dict[str, Any]:
    env_name = args.env
    target_name = args.target or DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    package_command = [
        "bash",
        "quwoquan_service/scripts/runtime/build_service_env_package.sh",
        "--service",
        args.service,
        "--env",
        env_name,
    ]
    package_result = run(package_command, env={"QWQ_DEPLOY_TARGET": target_name})
    if package_result.returncode != 0:
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": package_result.returncode,
            "summary": f"stackctl deploy packaging failed for {args.service}/{env_name}",
            "details": [package_result.stderr.strip() or package_result.stdout.strip()],
            **timing,
        }
    manifest = service_deployment_package_dir(
        env_name,
        args.service,
        target=target_name,
    ) / "manifests/all.yaml"
    dry_run = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    if env_name == "prod" and not dry_run:
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl service deploy blocked: prod requires the rollout transaction command",
            "details": ["use --target prod-hosted with release manifest and SLO readback"],
            **timing,
        }
    apply_command = ["kubectl", "apply", "-f", str(manifest)]
    if dry_run:
        apply_command.extend(["--dry-run=client"])
    apply_result = run(apply_command)
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok" if apply_result.returncode == 0 else "failed",
        "command": "deploy",
        "service": args.service,
        "environment": env_name,
        "dryRun": dry_run,
        "manifest": str(manifest),
        "apply": {
            "argv": apply_command,
            "exitCode": apply_result.returncode,
            "stdout": apply_result.stdout,
            "stderr": apply_result.stderr,
        },
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    return {
        "exitCode": apply_result.returncode,
        "summary": (
            f"stackctl deploy completed for {args.service}/{env_name}"
            if apply_result.returncode == 0
            else f"stackctl deploy failed for {args.service}/{env_name}"
        ),
        "details": _command_details(apply_result),
        "reportDir": relpath(report_dir),
        **timing,
    }


def _command_private_deploy_operation(
    args: argparse.Namespace,
    *,
    operation: str,
    command: list[str],
) -> dict[str, Any]:
    """执行已收口到 stackctl 的私有 Bash 实现，并留下统一报告。"""
    report_dir = resolve_report_dir(args, "prod", "prod-hosted")
    started_monotonic, started_at = _start_timing()
    result = run(command, env={"QWQ_DEPLOY_TARGET": "prod-hosted"})
    timing = _finish_timing(started_monotonic, started_at)
    details = _command_details(result)
    status = "ok" if result.returncode == 0 else "failed"
    write_json(
        report_dir / "report.json",
        {
            "status": status,
            "command": "deploy",
            "operation": operation,
            "target": "prod-hosted",
            "argv": command,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            **timing,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="deploy",
        target="prod-hosted",
        status=status,
        summary=(
            f"stackctl {operation} completed"
            if status == "ok"
            else f"stackctl {operation} failed"
        ),
        details=details,
        extra={"operation": operation},
        timing=timing,
    )
    _write_stdout_markdown(
        report_dir,
        [(operation, "\n".join(filter(None, [result.stdout, result.stderr])))],
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            f"stackctl {operation} completed"
            if status == "ok"
            else f"stackctl {operation} failed"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def _command_config_gray_rollout(args: argparse.Namespace) -> dict[str, Any]:
    required = (
        ("--service", str(args.service or "").strip()),
        ("--from-image", str(args.from_image or "").strip()),
        ("--to-image", str(args.to_image or "").strip()),
        ("--from-config", str(args.from_config or "").strip()),
        ("--to-config", str(args.to_config or "").strip()),
        ("--step", str(args.step or "").strip()),
    )
    missing = [flag for flag, value in required if not value]
    if missing:
        return {
            "exitCode": 2,
            "summary": "stackctl config-gray rollout failed",
            "details": ["config-gray requires " + ", ".join(missing)],
        }
    command = ["bash", "quwoquan_ops/cli/prod/config_release_gray_rollout.sh"]
    for flag, value in required:
        command.extend((flag, value))
    return _command_private_deploy_operation(
        args,
        operation="config-gray rollout",
        command=command,
    )


def _command_config_rollback(args: argparse.Namespace) -> dict[str, Any]:
    service = str(args.service or "").strip()
    target_config = str(getattr(args, "rollback_config", "") or "").strip()
    missing = [
        flag
        for flag, value in (("--service", service), ("--rollback-config", target_config))
        if not value
    ]
    if missing:
        return {
            "exitCode": 2,
            "summary": "stackctl config rollback failed",
            "details": ["config-rollback requires " + ", ".join(missing)],
        }
    return _command_private_deploy_operation(
        args,
        operation="config rollback",
        command=[
            "bash",
            "quwoquan_ops/cli/prod/config_release_rollback.sh",
            "--service",
            service,
            "--to-config-version",
            target_config,
        ],
    )


def _command_environment_assembly(args: argparse.Namespace) -> dict[str, Any]:
    env_name = str(getattr(args, "env", "") or "").strip()
    if env_name not in {"beta", "gamma"} or getattr(args, "target", ""):
        return {
            "exitCode": 2,
            "summary": "stackctl environment assembly failed",
            "details": [
                "environment-assembly requires --env beta|gamma and no --target"
            ],
        }
    target_name = DEFAULT_TARGET_BY_ENV[env_name]
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    command = ["bash", "quwoquan_ops/cli/shared/deploy_integration_k8s.sh"]
    result = run(command, env={"DEPLOY_ENV": env_name})
    timing = _finish_timing(started_monotonic, started_at)
    details = _command_details(result)
    status = "ok" if result.returncode == 0 else "failed"
    write_json(
        report_dir / "report.json",
        {
            "status": status,
            "command": "deploy",
            "operation": "environment-assembly",
            "env": env_name,
            "target": target_name,
            "argv": command,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            **timing,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="deploy",
        target=target_name,
        status=status,
        summary=(
            f"stackctl environment assembly completed for {env_name}"
            if status == "ok"
            else f"stackctl environment assembly failed for {env_name}"
        ),
        details=details,
        extra={"env": env_name, "operation": "environment-assembly"},
        timing=timing,
    )
    return {
        "exitCode": result.returncode,
        "summary": (
            f"stackctl environment assembly completed for {env_name}"
            if status == "ok"
            else f"stackctl environment assembly failed for {env_name}"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def _prod_prevalidation_executor(
    args: argparse.Namespace,
    *,
    manifest_path: Path,
    image_version: str,
    config_version: str,
    dry_run: bool,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    argv = [
        "python3",
        "quwoquan_ops/cli/prod/prevalidate_prod_hosted.py",
        "--host",
        str(args.ssh_host),
        "--release-manifest",
        str(manifest_path),
        "--image-version",
        image_version,
        "--config-version",
        config_version,
        "--data-mode",
        str(args.data_mode),
        "--scope",
        str(args.prevalidate_scope),
    ]
    if dry_run:
        argv.append("--dry-run")
    result = run(argv)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {
            "containerDeployment": {
                "status": "GATE_BLOCK",
                "issues": [
                    result.stderr.strip()
                    or result.stdout.strip()
                    or "prevalidation executor returned no JSON"
                ],
            },
            "releaseEligibility": {
                "status": "GATE_BLOCK",
                "promotable": False,
                "ledgerWritten": False,
                "receiptWritten": False,
            },
        }
    return result, payload


def _validate_prod_prevalidation_public_bases() -> None:
    topology = load_environment_topology()
    target = get_target(topology, "prod-hosted")
    public_bases = target.get("publicBases") or {}
    for name, value in public_bases.items():
        parsed = urllib.parse.urlparse(str(value))
        host = parsed.hostname or ""
        if (
            parsed.scheme not in {"https", "wss"}
            or not host
            or re.fullmatch(r"\d+(?:\.\d+){3}", host)
            or host.endswith((".test", ".example", ".localhost"))
        ):
            raise RuntimeError(
                f"prod-hosted publicBases.{name} must remain canonical public HTTPS DNS"
            )


def _command_prod_prevalidate(args: argparse.Namespace) -> dict[str, Any]:
    report_dir = resolve_report_dir(args, "prod", "prod-hosted")
    started_monotonic, started_at = _start_timing()
    timing: dict[str, Any]
    request_issues: list[str] = []
    formal_fields = {
        name: str(getattr(args, name, "") or "").strip()
        for name in (
            "stage",
            "service",
            "from_image",
            "to_image",
            "from_config",
            "to_config",
            "rollback_config",
            "step",
            "prometheus_url",
            "release_image_digest",
            "release_config_digest",
            "contract_graph_digest",
            "adapter_digest",
            "previous_image_version",
            "image_repository_root",
            "image_registry",
            "registry_username",
            "registry_password",
        )
    }
    if args.target != "prod-hosted" or args.env:
        request_issues.append("prevalidate requires --target prod-hosted and no --env")
    if args.prevalidate_scope != "first-party":
        request_issues.append("prevalidate requires --prevalidate-scope first-party")
    if args.data_mode not in {"isolated", "external"}:
        request_issues.append("prevalidate requires --data-mode isolated|external")
    if any(formal_fields.values()):
        names = sorted(name.replace("_", "-") for name, value in formal_fields.items() if value)
        request_issues.append(
            "prevalidate rejects formal rollout/SLO/rollback arguments: " + ", ".join(names)
        )
    ssh_host = str(args.ssh_host or "").strip()
    if (
        not ssh_host
        or "://" in ssh_host
        or re.fullmatch(r"[A-Za-z0-9.-]+", ssh_host) is None
    ):
        request_issues.append("prevalidate requires a valid SSH-only --ssh-host")
    try:
        _validate_prod_prevalidation_public_bases()
    except RuntimeError as error:
        request_issues.append(str(error))

    manifest_value = str(
        getattr(args, "release_manifest", "")
        or os.environ.get("RELEASE_MANIFEST", "")
    ).strip()
    manifest_path = (
        Path(manifest_value).expanduser().resolve()
        if manifest_value and not manifest_value.startswith("oci://")
        else ROOT
    )
    manifest_digest = ""
    manifest_payload: dict[str, Any] = {}
    image_version = "unresolved"
    config_version = "unresolved"
    if not manifest_value:
        request_issues.append("immutable Service Pipeline --release-manifest is required")
    else:
        try:
            (
                manifest_path,
                manifest_digest,
                manifest_payload,
                image_version,
                config_version,
            ) = _prevalidation_release_manifest(manifest_value)
        except RuntimeError as error:
            request_issues.append(str(error))

    host_payload: dict[str, Any] = {}
    host_result: subprocess.CompletedProcess[str] | None = None
    if ssh_host and args.data_mode and args.prevalidate_scope:
        host_result, host_payload = _prod_prevalidation_executor(
            args,
            manifest_path=manifest_path,
            image_version=image_version,
            config_version=config_version,
            dry_run=True,
        )
        host_issues = (
            (host_payload.get("hostPreflight") or {}).get("issues")
            or (host_payload.get("containerDeployment") or {}).get("issues")
            or []
        )
        request_issues.extend(str(item) for item in host_issues if str(item) not in request_issues)

    deployment_payload = host_payload.get("containerDeployment") or {
        "status": "not-run"
    }
    package_step: dict[str, Any] | None = None
    executor_step: dict[str, Any] | None = None
    dry_run = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    exit_code = 2 if request_issues else 0
    if not request_issues:
        package_result = run(
            [
                "python3",
                "quwoquan_ops/cli/stackctl.py",
                "package",
                "--env",
                "prod",
                "--target",
                "prod-hosted",
                "--include-services",
            ],
            env={"QWQ_PROD_RELEASE_ARTIFACT_ROOT": str(manifest_path.parent)},
        )
        package_step = {
            "exitCode": package_result.returncode,
            "stdout": package_result.stdout,
            "stderr": package_result.stderr,
        }
        if package_result.returncode != 0:
            exit_code = package_result.returncode or 2
            request_issues.append(
                package_result.stderr.strip()
                or package_result.stdout.strip()
                or "prod package failed"
            )
            deployment_payload = {
                "status": "GATE_BLOCK",
                "issues": list(request_issues),
            }
        elif not dry_run:
            executor_result, executor_payload = _prod_prevalidation_executor(
                args,
                manifest_path=manifest_path,
                image_version=image_version,
                config_version=config_version,
                dry_run=False,
            )
            executor_step = {
                "exitCode": executor_result.returncode,
                "stderr": executor_result.stderr,
            }
            deployment_payload = executor_payload.get("containerDeployment") or {
                "status": "GATE_BLOCK"
            }
            exit_code = executor_result.returncode
            if exit_code != 0:
                request_issues.extend(
                    str(item)
                    for item in deployment_payload.get("issues") or []
                    if str(item) not in request_issues
                )

    release_eligibility = {
        "status": "GATE_BLOCK",
        "promotable": False,
        "ledgerWritten": False,
        "receiptWritten": False,
        "reason": (
            "first-party container prevalidation cannot satisfy Provider, SFU, "
            "production data, observability, disaster recovery, or rollout evidence"
        ),
    }
    access = load_json_yaml(
        ROOT / "quwoquan_ops/environments/prod/access-isolation.yaml"
    )
    prevalidation = access.get("prevalidation") if isinstance(access, dict) else {}
    excluded = prevalidation.get("excluded") if isinstance(prevalidation, dict) else {}
    provider_readiness = host_payload.get("providerReadiness") or {
        "status": "GATE_BLOCK",
        "excludedCapabilities": list(
            (excluded.get("capabilities") or [])
            if isinstance(excluded, dict)
            else []
        ),
    }
    timing = _finish_timing(started_monotonic, started_at)
    report = {
        "schema": "prod-hosted-first-party-prevalidation-report",
        "command": "deploy",
        "target": "prod-hosted",
        "mode": "prevalidate",
        "sshHost": ssh_host,
        "dataMode": str(args.data_mode),
        "scope": str(args.prevalidate_scope),
        "dryRun": dry_run,
        "releaseManifest": {
            "path": str(manifest_path) if manifest_value else "",
            "digest": manifest_digest,
            "source": manifest_payload.get("source") or {},
            "versions": manifest_payload.get("versions") or {},
        },
        "hostPreflight": host_payload.get("hostPreflight") or {},
        "containerDeployment": deployment_payload,
        "providerReadiness": provider_readiness,
        "releaseEligibility": release_eligibility,
        "issues": request_issues,
        "package": package_step,
        "executor": executor_step,
        **timing,
    }
    write_json(report_dir / "report.json", report)
    status = "ok" if exit_code == 0 else "gate_block"
    details = [
        f"containerDeployment={deployment_payload.get('status', 'unknown')}",
        f"providerReadiness={provider_readiness.get('status', 'GATE_BLOCK')}",
        "releaseEligibility=GATE_BLOCK",
        *request_issues,
    ]
    _write_summary_bundle(
        report_dir,
        command="deploy",
        target="prod-hosted",
        status=status,
        summary=(
            "stackctl prod-hosted first-party prevalidation completed"
            if exit_code == 0
            else "stackctl prod-hosted first-party prevalidation is GATE_BLOCK"
        ),
        details=details,
        extra={
            "mode": "prevalidate",
            "containerDeployment": deployment_payload.get("status"),
            "providerReadiness": provider_readiness.get("status", "GATE_BLOCK"),
            "releaseEligibility": "GATE_BLOCK",
        },
        timing=timing,
    )
    return {
        "exitCode": exit_code,
        "summary": (
            "stackctl prod-hosted first-party prevalidation completed; release remains GATE_BLOCK"
            if exit_code == 0
            else "stackctl prod-hosted first-party prevalidation is GATE_BLOCK"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        "containerDeployment": deployment_payload.get("status"),
        "providerReadiness": provider_readiness.get("status", "GATE_BLOCK"),
        "releaseEligibility": "GATE_BLOCK",
        **timing,
    }


def _command_deploy_distribution(args: argparse.Namespace) -> dict[str, Any]:
    env_name = str(getattr(args, "env", "") or "").strip()
    target_name = str(getattr(args, "target", "") or "").strip()
    topology = load_environment_topology()
    if target_name:
        target_env = str(get_target(topology, target_name).get("env") or "")
        if env_name and env_name != target_env:
            return {
                "exitCode": 2,
                "summary": "stackctl distribution deploy is GATE_BLOCK",
                "details": ["--env and --target resolve to different environments"],
            }
        env_name = target_env
    elif env_name in ENVIRONMENTS:
        target_name = DEFAULT_TARGET_BY_ENV[env_name]
    else:
        return {
            "exitCode": 2,
            "summary": "stackctl distribution deploy is GATE_BLOCK",
            "details": ["distribution deploy requires --env or --target"],
        }
    artifact_manifest = str(getattr(args, "artifact_manifest", "") or "").strip()
    release_manifest = str(getattr(args, "release_manifest", "") or "").strip()
    if not artifact_manifest or not release_manifest:
        return {
            "exitCode": 2,
            "summary": "stackctl distribution deploy is GATE_BLOCK",
            "details": [
                "--artifact-manifest and --release-manifest are both required; "
                "a package cannot be deployed outside its candidate ReleaseManifest"
            ],
        }
    dry_run = str(getattr(args, "dry_run", "false")).lower() == "true"
    distribution_root, explicitly_configured = _official_distribution_root(
        args,
        target_name=target_name,
    )
    if target_name == "prod-hosted" and not dry_run and not explicitly_configured:
        return {
            "exitCode": 2,
            "summary": "stackctl production distribution deploy is GATE_BLOCK",
            "details": [
                "prod non-dry-run requires --distribution-root or QWQ_DISTRIBUTION_ROOT "
                "mounted to the official CDN/origin publishing root"
            ],
        }
    if target_name == "prod-hosted" and not dry_run:
        try:
            release_payload = json.loads(Path(release_manifest).read_text(encoding="utf-8"))
            versions = release_payload.get("versions") if isinstance(release_payload, dict) else None
            image_version = str(versions.get("imageVersion") or "") if isinstance(versions, dict) else ""
            config_version = str(versions.get("configVersion") or "") if isinstance(versions, dict) else ""
            _deployable_release_manifest(
                release_manifest,
                image_version=image_version,
                config_version=config_version,
            )
        except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as error:
            return {
                "exitCode": 2,
                "summary": "stackctl production distribution deploy is GATE_BLOCK",
                "details": [f"governed ReleaseManifest validation failed: {error}"],
            }
    report_dir = resolve_report_dir(args, env_name, target_name)
    started_monotonic, started_at = _start_timing()
    try:
        if dry_run:
            with tempfile.TemporaryDirectory(prefix="qwq-distribution-dry-run-") as root:
                receipt = deploy_official_distribution(
                    kind=str(args.artifact_kind),
                    package_manifest_path=Path(artifact_manifest),
                    release_manifest_path=Path(release_manifest),
                    distribution_root=Path(root),
                )
            receipt["status"] = "validated"
            receipt["dryRun"] = True
            receipt.pop("receiptPath", None)
        else:
            receipt = deploy_official_distribution(
                kind=str(args.artifact_kind),
                package_manifest_path=Path(artifact_manifest),
                release_manifest_path=Path(release_manifest),
                distribution_root=distribution_root,
                expected_current=str(getattr(args, "expected_current", "") or ""),
            )
            receipt["status"] = "deployed"
            receipt["dryRun"] = False
        issues: list[str] = []
        hosted_inspection: dict[str, Any] = {}
        if bool(getattr(args, "verify_hosted", False)) and not dry_run:
            target = get_target(topology, target_name)
            public_bases = target.get("publicBases") or {}
            hosted_inspection = inspect_official_distribution(
                distribution_root=distribution_root,
                public_origin=str(public_bases.get("publicWeb") or ""),
                download_origin=str(public_bases.get("appDownload") or ""),
                verify_hosted=True,
            )
            issues.extend(hosted_inspection.get("issues") or [])
    except (OSError, ValueError, OfficialDistributionReleaseError) as error:
        receipt = {}
        hosted_inspection = {}
        issues = [str(error)]
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "schema": "stackctl-official-distribution-deploy-report",
        "command": "deploy",
        "artifactKind": args.artifact_kind,
        "environment": env_name,
        "target": target_name,
        "distributionRoot": str(distribution_root),
        "explicitlyConfigured": explicitly_configured,
        "receipt": receipt,
        "hostedInspection": hosted_inspection,
        "issues": issues,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": issues})
    return {
        "exitCode": 0 if not issues else 2,
        "summary": (
            f"stackctl {args.artifact_kind} distribution "
            + ("validated" if dry_run else "deployed")
            if not issues
            else f"stackctl {args.artifact_kind} distribution is GATE_BLOCK"
        ),
        "details": issues or [
            f"releaseManifestDigest={receipt.get('releaseManifestDigest')}",
            f"receiptSHA256={receipt.get('receiptSHA256')}",
        ],
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_deploy(args: argparse.Namespace) -> dict[str, Any]:
    if str(getattr(args, "artifact_kind", "") or ""):
        return _command_deploy_distribution(args)
    if args.mode == "environment-assembly":
        return _command_environment_assembly(args)
    if args.mode == "prevalidate":
        return _command_prod_prevalidate(args)
    if args.mode in {"config-gray", "config-rollback"}:
        if args.target != "prod-hosted" or args.env:
            return {
                "exitCode": 2,
                "summary": f"stackctl {args.mode} failed",
                "details": [f"{args.mode} requires --target prod-hosted"],
            }
        try:
            with _prod_release_lock():
                if args.mode == "config-gray":
                    return _command_config_gray_rollout(args)
                return _command_config_rollback(args)
        except RuntimeError as error:
            return {
                "exitCode": 2,
                "summary": f"stackctl {args.mode} blocked by prod release transaction",
                "details": [str(error)],
            }
    if getattr(args, "service", "") and getattr(args, "env", ""):
        return _command_deploy_service_environment(args)
    if not args.target:
        return {
            "exitCode": 2,
            "summary": "stackctl deploy requires --service/--env or --target",
            "details": [],
        }
    dry_run = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    if args.target != "prod-hosted" or dry_run:
        return _command_deploy_with_lock(args)
    try:
        with _prod_release_lock():
            return _command_deploy_with_lock(args)
    except RuntimeError as error:
        return {
            "exitCode": 2,
            "summary": "stackctl deploy blocked by prod release transaction",
            "details": [str(error)],
        }


def command_hosted_release_receipt(args: argparse.Namespace) -> dict[str, Any]:
    """Resolve a release receipt from the hosted service plane, never local output."""
    receipt_id = str(args.receipt_id or "").strip()
    if re.fullmatch(r"[0-9a-f]{64}", receipt_id) is None:
        return {
            "exitCode": 2,
            "summary": "hosted release receipt readback failed",
            "details": ["receipt id must be a lowercase SHA-256 value"],
        }
    expected_candidate = {
        "imageDigest": str(args.image_digest or "").strip(),
        "configDigest": str(args.config_digest or "").strip(),
        "contractGraphDigest": str(args.contract_graph_digest or "").strip(),
        "adapterDigest": str(args.adapter_digest or "").strip(),
    }
    if any(
        re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
        for value in expected_candidate.values()
    ):
        return {
            "exitCode": 2,
            "summary": "hosted release receipt readback failed",
            "details": ["candidate digests must all be canonical sha256 values"],
        }
    try:
        readback = _run_hosted_release_ledger(
            service=str(args.service).strip(),
            action="receipt",
            receipt_id=receipt_id,
        )
        receipt = readback["receipt"]
        receipt_bytes = (
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if not isinstance(receipt, dict) or receipt.get("receiptId") != receipt_id:
            raise RuntimeError("hosted receipt identity is invalid")
        if receipt.get("service") != str(args.service).strip():
            raise RuntimeError("hosted receipt service does not match request")
        if any(receipt.get(field) != value for field, value in expected_candidate.items()):
            raise RuntimeError("hosted receipt candidate binding does not match UAT")
        purpose = str(args.purpose)
        if purpose == "last-good" and not (
            receipt.get("stage") == "full"
            and receipt.get("decision") == "continue"
            and receipt.get("rollbackOutcome") == "not_triggered"
            and receipt.get("lastGoodTarget")
            == {
                "image": receipt.get("toImage"),
                "config": receipt.get("toConfig"),
            }
        ):
            raise RuntimeError("hosted receipt is not a stable full last-good release")
        if purpose == "rollback" and not (
            receipt.get("decision") == "rolled_back"
            and receipt.get("rollbackOutcome") == "rolled_back"
            and receipt.get("lastGoodTarget")
            == {
                "image": receipt.get("toImage"),
                "config": receipt.get("toConfig"),
            }
        ):
            raise RuntimeError("hosted receipt does not prove a successful rollback")
    except (RuntimeError, json.JSONDecodeError) as error:
        return {
            "exitCode": 2,
            "summary": "hosted release receipt readback failed",
            "details": [str(error)],
        }
    digest = "sha256:" + hashlib.sha256(receipt_bytes).hexdigest()
    return {
        "exitCode": 0,
        "summary": "hosted release receipt readback verified",
        "details": [f"receipt: receipt:hosted:{receipt_id}"],
        "receiptRef": f"receipt:hosted:{receipt_id}",
        "receiptDigest": digest,
        "candidate": expected_candidate,
        "purpose": purpose,
    }


def command_roll(args: argparse.Namespace) -> dict[str, Any]:
    started_monotonic, started_at = _start_timing()

    if args.target in {"alpha-local", "beta-local", "gamma-local"}:
        env_map = {
            "alpha-local": "alpha",
            "beta-local": "beta",
            "gamma-local": "gamma",
        }
        nested_args = argparse.Namespace(
            command="up",
            env=env_map[args.target],
            target=args.target,
            device_id="",
            skip_app=True,
            skip_build=False,
            workload="full",
            rollout_mode="",
            output_format="json",
            report_dir=getattr(args, "report_dir", ""),
        )
        payload = command_up(nested_args)
        payload["summary"] = f"stackctl roll {args.mode} completed for {args.target}"
        return payload

    timing = _finish_timing(started_monotonic, started_at)
    return {
        "exitCode": 2,
        "summary": f"stackctl roll does not support target {args.target}",
        "details": [],
        **timing,
    }


def _all_services() -> list[str]:
    services: list[str] = []
    for path in ROOT.glob("quwoquan_service/services/*/config/schema.yaml"):
        services.append(path.parents[1].name)
    if (ROOT / "quwoquan_service/control-plane/platform-ops/config/schema.yaml").is_file():
        services.append("platform-ops-service")
    return sorted(set(services))


def _beta_env_from_port_manifest(
    topology: dict[str, Any],
    target_name: str,
) -> dict[str, str]:
    manifest = load_port_manifest()
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    port_profile = str(target.get("portProfile") or "")
    if not port_profile:
        raise RuntimeError(f"GATE_BLOCK: {target_name} lacks a port profile")
    build_images = target.get("buildImages")
    if not isinstance(build_images, dict):
        raise RuntimeError(
            f"GATE_BLOCK: {target_name}.buildImages policy must be an object"
        )

    def required_build_image(name: str) -> str:
        value = build_images.get(name)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                f"GATE_BLOCK: {target_name}.buildImages.{name} must be a non-empty string"
            )
        return value.strip()

    ports = profile_ports(manifest, port_profile)
    return {
        "GATEWAY_PORT": str(ports["api-edge"]),
        "PRODUCT_OPS_PORT": str(ports["product-ops-edge"]),
        "PLATFORM_OPS_PORT": str(ports["platform-ops-edge"]),
        "OPS_PORTAL_PORT": str(ports["ops-portal"]),
        "MEDIA_PORT": str(ports["media-edge"]),
        "ASSISTANT_PORT": str(ports["assistant-service"]),
        "CHAT_PORT": str(ports["chat-service"]),
        "QWQ_COMPOSE_GO_BASE_IMAGE": required_build_image("goBaseImage"),
        "QWQ_COMPOSE_ALPINE_BASE_IMAGE": required_build_image("alpineBaseImage"),
        "QWQ_COMPOSE_PUBLIC_WEB_BASE_URL": str(public_bases["publicWeb"]),
        "QWQ_COMPOSE_MEDIA_AVATAR_BASE_URL": str(public_bases["mediaAvatar"]),
    }


def _gamma_env_from_port_manifest(topology: dict[str, Any], target_name: str) -> dict[str, str]:
    manifest = load_port_manifest()
    profile_name = str(get_target(topology, target_name).get("portProfile"))
    ports = profile_ports(manifest, profile_name)
    target = get_target(topology, target_name)
    public_bases = target.get("publicBases") or {}
    startup = target.get("startup")
    if not isinstance(startup, dict):
        raise RuntimeError(
            f"GATE_BLOCK: {target_name} startup policy must be an object"
        )
    build_images = target.get("buildImages")
    if not isinstance(build_images, dict):
        raise RuntimeError(
            f"GATE_BLOCK: {target_name} buildImages policy must be an object"
        )

    def required_positive_seconds(name: str) -> str:
        value = startup.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RuntimeError(
                f"GATE_BLOCK: {target_name}.startup.{name} must be a positive integer"
            )
        return str(value)

    def required_build_image(name: str) -> str:
        value = build_images.get(name)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(
                f"GATE_BLOCK: {target_name}.buildImages.{name} must be a non-empty string"
            )
        return value.strip()

    environment = {
        "LOCAL_GAMMA_HTTP_PORT": str(ports["api-edge"]),
        "LOCAL_GAMMA_PRODUCT_OPS_PORT": str(ports["product-ops-edge"]),
        "LOCAL_GAMMA_PLATFORM_OPS_PORT": str(ports["platform-ops-edge"]),
        "LOCAL_GAMMA_MEDIA_EDGE_PORT": str(ports["media-edge"]),
        "LOCAL_GAMMA_MEDIA_AVATAR_BASE_URL": str(public_bases["mediaAvatar"]),
        "LOCAL_GAMMA_MEDIA_IMAGE_BASE_URL": str(public_bases["mediaImage"]),
        "LOCAL_GAMMA_MEDIA_VIDEO_BASE_URL": str(public_bases["mediaVideo"]),
        "LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
        "LOCAL_GAMMA_RTC_MEDIA_CONNECTION_URL": str(public_bases["rtc"]),
        "LOCAL_GAMMA_CONTENT_PORT": str(ports["content-service"]),
        "LOCAL_GAMMA_CHAT_PORT": str(ports["chat-service"]),
        "LOCAL_GAMMA_USER_PORT": str(ports["user-service"]),
        "LOCAL_GAMMA_ASSISTANT_PORT": str(ports["assistant-service"]),
        "LOCAL_GAMMA_INTEGRATION_PORT": str(ports["integration-service"]),
        "LOCAL_GAMMA_NOTIFICATION_PORT": str(ports["notification-service"]),
        "LOCAL_GAMMA_REALTIME_PORT": str(ports["realtime-gateway"]),
        "LOCAL_GAMMA_RTC_PORT": str(ports["rtc-service"]),
        "LOCAL_GAMMA_REC_MODEL_PORT": str(ports["recommendation-service"]),
        "LOCAL_GAMMA_PRODUCT_OPS_SERVICE_PORT": str(ports["product-ops-service"]),
        "LOCAL_GAMMA_PLATFORM_OPS_SERVICE_PORT": str(ports["platform-ops-service"]),
        "LOCAL_GAMMA_TAG_PORT": str(ports["tag-service"]),
        "LOCAL_GAMMA_SEARCH_PORT": str(ports["search-service"]),
        "LOCAL_GAMMA_MONGO_PORT": str(ports["mongodb"]),
        "LOCAL_GAMMA_REDIS_PORT": str(ports["redis"]),
        "LOCAL_GAMMA_POSTGRES_PORT": str(ports["postgres"]),
        "LOCAL_GAMMA_ES_PORT": str(ports["elasticsearch"]),
        "LOCAL_GAMMA_DOCKER_PROBE_TIMEOUT_SECONDS": required_positive_seconds(
            "dockerProbeTimeoutSeconds"
        ),
        "LOCAL_GAMMA_COMPOSE_BUILD_TIMEOUT_SECONDS": required_positive_seconds(
            "composeBuildTimeoutSeconds"
        ),
        "LOCAL_GAMMA_COMPOSE_BUILD_NO_PROGRESS_TIMEOUT_SECONDS": required_positive_seconds(
            "composeBuildNoProgressTimeoutSeconds"
        ),
        "LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS": required_positive_seconds(
            "composeUpTimeoutSeconds"
        ),
        "LOCAL_GAMMA_GO_BASE_IMAGE": required_build_image("goBaseImage"),
        "LOCAL_GAMMA_ALPINE_BASE_IMAGE": required_build_image("alpineBaseImage"),
        "QWQ_COMPOSE_PUBLIC_WEB_BASE_URL": str(public_bases["publicWeb"]),
        "QWQ_COMPOSE_MEDIA_AVATAR_BASE_URL": str(public_bases["mediaAvatar"]),
    }
    environment.update(
        prepare_local_environment_auth("gamma", "gamma-local").environment
    )
    return environment


def _health_checks_for_target(topology: dict[str, Any], target_name: str, scope: str) -> list[dict[str, Any]]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    public_bases = target.get("publicBases") or {}
    origins = target.get("origins") or {}
    service_policy = ((env_cfg.get("artifactPolicy") or {}).get("service") or {})
    allow_fixture_refs = bool(service_policy.get("allowFixtureRefs")) or target_name == "prod-sim"
    checks: list[dict[str, Any]] = []
    if scope in {"edge", "full", "content-import", "content-consumer"}:
        checks.append(
            {
                "name": "api-health",
                "scope": "edge",
                "url": f"{str(public_bases['api']).rstrip('/')}/healthz",
            }
        )
    if scope in {"edge", "full"}:
        checks.append(
            {
                "name": "product-ops-health",
                "scope": "edge",
                "url": f"{str(public_bases['productOps']).rstrip('/')}/healthz",
            }
        )
    if scope in {"media", "full", "content-import", "content-consumer"} and "mediaImage" in public_bases:
        checks.append(
            {
                "name": "media-edge-health",
                "scope": "media",
                "url": f"{str(public_bases['mediaImage']).rstrip('/')}/healthz",
            }
        )
        if allow_fixture_refs:
            for asset in load_media_delivery_manifest():
                url = build_media_delivery_url(public_bases, asset)
                check = {
                    "name": f"media-public-{asset['logicalAssetId']}",
                    "scope": "media",
                    "url": url,
                }
                mime_type = str(asset.get("mimeType") or "").strip().lower()
                if mime_type.startswith("video/"):
                    check["headers"] = {"Range": "bytes=0-1"}
                    check["expectedStatus"] = 206
                    check["expectedContentTypePrefix"] = "video/"
                elif mime_type:
                    check["expectedContentTypePrefix"] = mime_type
                checks.append(check)
        media_origin = str(origins.get("mediaOrigin") or "").rstrip("/")
        if media_origin and allow_fixture_refs:
            origin_bases = {
                "mediaAvatar": media_origin,
                "mediaImage": media_origin,
                "mediaVideo": media_origin,
            }
            for asset in load_media_delivery_manifest():
                url = build_media_delivery_url(
                    origin_bases,
                    asset,
                    require_https=False,
                )
                check = {
                    "name": f"media-origin-{asset['logicalAssetId']}",
                    "scope": "media",
                    "url": url,
                }
                mime_type = str(asset.get("mimeType") or "").strip().lower()
                if mime_type.startswith("video/"):
                    check["headers"] = {"Range": "bytes=0-1"}
                    check["expectedStatus"] = 206
                    check["expectedContentTypePrefix"] = "video/"
                elif mime_type:
                    check["expectedContentTypePrefix"] = mime_type
                checks.append(check)
    if scope in {"service", "full"}:
        checks.extend(_service_health_checks_for_target(target_name))
    if scope in {"content-import", "content-consumer", "full"}:
        checks.extend(_content_data_plane_health_checks(target_name))
    if scope in {"content-consumer", "full"}:
        checks.extend(_content_consumer_health_checks(target_name, public_bases))
    if scope == "full":
        checks.extend(_full_scope_health_checks(target_name, public_bases, env_cfg))
    return checks


_CONTENT_DATA_PLANE_ROLES = frozenset(
    {"content-service", "entity-service", "tag-service", "search-service"}
)


def _content_data_plane_health_checks(target_name: str) -> list[dict[str, Any]]:
    """Only probes required by immutable content import and API consumption."""
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        if target_name == "prod-hosted":
            api_base = str((target.get("publicBases") or {}).get("api") or "").rstrip("/")
            if not api_base:
                return []
            # prod edge /healthz is routed directly to content-service.  This is
            # the hosted data-plane liveness proof; local-only loopback ports
            # and SSH management addresses must never become App/public config.
            return [
                {
                    "name": "content-service-public",
                    "scope": "content-import",
                    "url": f"{api_base}/healthz",
                }
            ]
        return []
    manifest = load_port_manifest()
    role_names = [
        role_name
        for role_name in _expected_local_roles(target_name)
        if role_name in _CONTENT_DATA_PLANE_ROLES
    ]
    checks: list[dict[str, Any]] = []
    for role_name in role_names:
        port = canonical_port(manifest, str(profile_name), role_name)
        checks.append(
            {
                "name": role_name,
                "scope": "content-import",
                "url": f"http://127.0.0.1:{port}/healthz",
            }
        )
    return checks


def _content_consumer_health_checks(
    target_name: str,
    public_bases: dict[str, Any],
) -> list[dict[str, Any]]:
    if target_name not in {"alpha-local", "beta-local", "gamma-local", "prod-hosted"}:
        return []
    api_base = str(public_bases.get("api") or "").rstrip("/")
    if not api_base:
        return []
    return [
        {"name": "app-config", "scope": "content-consumer", "url": f"{api_base}/config/app"},
        {"name": "content-feed", "scope": "content-consumer", "url": f"{api_base}/content/feed?limit=1"},
    ]


def _service_health_checks_for_target(target_name: str) -> list[dict[str, Any]]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    mock_flags = (topology["environments"][env_name].get("mockBoundaryFlags") or {})
    if mock_flags.get("servicePlane"):
        return [
            {
                "name": "service-plane-mocked",
                "scope": "service",
                "url": "",
                "skip": True,
                "reason": "service plane is mocked in this target",
            }
        ]
    profile_name = target.get("portProfile")
    if not profile_name:
        return []
    manifest = load_port_manifest()
    checks: list[dict[str, Any]] = []
    non_service_paths = {
        "realtime-gateway": "/healthz",
        "livekit-http": "/",
        "livekit-metrics": "/metrics",
    }
    for role_name in _expected_local_roles(target_name):
        if not role_name.endswith("-service") and role_name not in non_service_paths:
            continue
        port = canonical_port(manifest, str(profile_name), role_name)
        path = non_service_paths.get(role_name, "/healthz")
        if role_name == "recommendation-service":
            path = "/health"
        checks.append(
            {
                "name": role_name,
                "scope": "service",
                "url": f"http://127.0.0.1:{port}{path}",
            }
        )
    return checks


def _full_scope_health_checks(
    target_name: str,
    public_bases: dict[str, Any],
    env_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    env_name = str(env_cfg.get("artifactPolicy", {}).get("app", {}).get("runtimeEnv", ""))
    if target_name == "beta-local":
        notification_port = canonical_port(
            load_port_manifest(),
            "beta-local",
            "notification-service",
        )
        checks.append(
            {
                "name": "app-config",
                "scope": "full",
                "url": f"{str(public_bases['api']).rstrip('/')}/config/app",
            }
        )
        checks.extend(
            [
                {
                    "name": "content-feed",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/content/feed",
                },
                {
                    "name": "chat-contacts",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/chat/contacts",
                },
                {
                    "name": "notification-service-health",
                    "scope": "full",
                    "url": f"http://127.0.0.1:{notification_port}/healthz",
                },
                {
                    "name": "feed-intersections",
                    "scope": "full",
                    "url": (
                        f"{str(public_bases['api']).rstrip('/')}"
                        "/content/feed/intersections?limit=4&channel=recommend"
                    ),
                },
            ]
        )
    elif target_name == "gamma-local":
        checks.extend(
            [
                {
                    "name": "app-config",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/config/app",
                },
                {
                    "name": "gamma-route-smoke",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/content/feed?limit=1",
                },
                {
                    "name": "tag-public-catalog-smoke",
                    "scope": "full",
                    "url": (
                        f"{str(public_bases['api']).rstrip('/')}"
                        "/tag/resolve?tagRef=Topic%2F%E6%97%85%E8%A1%8C"
                    ),
                },
            ]
        )
    elif target_name == "prod-sim":
        checks.extend(
            [
                {
                    "name": "app-config",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/config/app",
                },
                {
                    "name": "prod-sim-route-smoke",
                    "scope": "full",
                    "url": f"{str(public_bases['api']).rstrip('/')}/content/feed?limit=1",
                },
            ]
        )
    return checks


def _network_report(target_name: str) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        public_bases = target.get("publicBases") or {}
        endpoints = [
            {"name": name, "url": value}
            for name, value in public_bases.items()
            if isinstance(value, str) and value.strip()
        ]
        return {
            "profile": "",
            "ports": [],
            "publicEndpoints": endpoints,
        }
    manifest = load_port_manifest()
    ports = []
    for role in _expected_local_roles(target_name):
        if role not in manifest["roles"]:
            continue
        port = canonical_port(manifest, profile_name, role)
        ports.append({"name": role, "port": port, "open": socket_probe(port)})
    return {
        "profile": profile_name,
        "ports": ports,
        "publicEndpoints": [],
    }


def _expected_local_roles(
    target_name: str,
    *,
    workload: str = "full",
) -> list[str]:
    if workload == "content-release" and target_name == "beta-local":
        # content-release 启动的就是这条 consumer data plane；不能要求
        # assistant/chat/Ops 等 full workload 才会启动的端口，否则集成验证
        # 会错误重启已经健康的发布环境。
        return [
            "api-edge",
            "media-edge",
            "media-origin",
            "content-service",
            "user-service",
            "entity-service",
        ]
    role_map = {
        "alpha-local": [
            "api-edge",
            "media-edge",
            "media-origin",
            "content-service",
            "user-service",
            "entity-service",
        ],
        "beta-local": [
            "api-edge",
            "product-ops-edge",
            "platform-ops-edge",
            "ops-portal",
            "media-edge",
            "media-origin",
            "content-service",
            "assistant-service",
            "chat-service",
            "notification-service",
            "fixture-gateway",
        ],
        "gamma-local": [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "chat-service",
            "user-service",
            "content-service",
            "assistant-service",
            "recommendation-service",
            "product-ops-service",
            "platform-ops-service",
            "tag-service",
            "search-service",
            "entity-service",
            "circle-service",
            "integration-service",
            "notification-service",
            "realtime-gateway",
            "rtc-service",
            "postgres",
            "mongodb",
            "redis",
            "elasticsearch",
        ],
        "prod-sim": [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "media-origin",
        ],
    }
    return role_map.get(target_name, [])


def _resolve_prod_rollout_stage(step: str, requested_stage: str = "") -> str:
    normalized_step = str(step).strip()
    try:
        percentage = int(normalized_step)
    except ValueError as error:
        raise ValueError(f"step 必须是 1..100 的整数，实际 {step!r}") from error
    if percentage < 1 or percentage > 100:
        raise ValueError(f"step 必须在 1..100，实际 {percentage}")

    explicit_stage = str(requested_stage).strip()
    if explicit_stage:
        if explicit_stage == "full" and percentage != 100:
            raise ValueError("full 必须与 step=100 同时使用")
        if explicit_stage != "full" and percentage == 100:
            raise ValueError("step=100 只能使用 full")
        return explicit_stage
    if percentage == 100:
        return "full"
    if percentage <= 5:
        return "gray-initial"
    return "carry-on"


def _prod_rollout_workloads() -> list[dict[str, Any]]:
    """Derive prod rollout workloads from service and external environment entries."""
    try:
        topology = load_environment_topology()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    prod = ((topology or {}).get("environments") or {}).get("prod") or {}
    for workload in prod.get("workloads") or []:
        deployment_ref = str(workload.get("deploymentRef") or "")
        out.append(
            {
                "name": workload.get("id"),
                "plane": workload.get("plane"),
                "deploymentRef": deployment_ref,
                "rolloutRef": deployment_ref,
            }
        )
    return out


def _local_log_report(target_name: str) -> dict[str, Any]:
    candidates: dict[str, Path] = {
        "alpha-state": target_process_dir("alpha-local"),
        "beta-state": target_process_dir("beta-local"),
        "beta-manual": target_process_dir("beta-local") / "app-beta-manual",
        "app-instances": repo_local_dir("app-instances"),
        "local-gamma": target_process_dir("gamma-local"),
        "release-state": _release_state_dir(),
    }
    hits = []
    for name, path in candidates.items():
        if path.exists():
            hits.append({"name": name, "path": relpath(path)})
    extra: dict[str, Any] = {}
    try:
        runtime_root = _local_runtime_log_root(target_name)
    except RuntimeError:
        runtime_root = None
    if runtime_root is not None:
        extra["runtimeDiagnostics"] = _runtime_log_evidence_report(runtime_root)
    else:
        extra["runtimeDiagnostics"] = {
            "availability": "not_started",
            "recordCount": 0,
            "reason": "local runtime observability root is unavailable",
        }
    if target_name == "prod-hosted":
        extra["prodReleaseState"] = _load_release_state(PROD_RELEASE_UNIT)
    return {"paths": hits, **extra}


def _runtime_log_evidence_report(log_root: Path) -> dict[str, Any]:
    """Summarize canonical records without copying raw messages into reports."""
    severity_counts: dict[str, int] = {}
    signal_counts: dict[str, int] = {}
    parse_issues: list[str] = []
    record_count = 0
    files = sorted(path for path in log_root.rglob("*.log") if path.is_file())
    for path in files:
        kind = path.stem
        try:
            records, issues = parse_log_records(
                kind,
                path.read_text(encoding="utf-8", errors="replace").splitlines(),
            )
        except ValueError:
            continue
        record_count += len(records)
        parse_issues.extend(
            f"{relpath(path)}: {issue}" for issue in issues[:5]
        )
        for record in records:
            severity = str(record.get("severity") or "UNKNOWN")
            signal = str(record.get("signal") or "unknown")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            signal_counts[signal] = signal_counts.get(signal, 0) + 1
    return {
        "availability": "available" if log_root.exists() else "not_started",
        "root": relpath(log_root),
        "files": [relpath(path) for path in files],
        "recordCount": record_count,
        "severityCounts": dict(sorted(severity_counts.items())),
        "topSignals": [
            {"signal": signal, "count": count}
            for signal, count in sorted(
                signal_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:10]
        ],
        "parseIssues": parse_issues[:20],
    }


def _data_report(target_name: str) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        return {"ports": []}
    manifest = load_port_manifest()
    return {
        "ports": {
            "postgres": canonical_port(manifest, profile_name, "postgres"),
            "mongodb": canonical_port(manifest, profile_name, "mongodb"),
            "redis": canonical_port(manifest, profile_name, "redis"),
        }
    }


def _metrics_report(topology: dict[str, Any], target_name: str) -> dict[str, Any]:
    checks = _health_checks_for_target(topology, target_name, "full")
    return {
        "probes": [
            {"name": item["name"], "url": item["url"]}
            for item in checks
        ],
        "scriptProbes": _script_probe_plan_for_target(topology, target_name),
    }


def _security_report(topology: dict[str, Any], target_name: str) -> dict[str, Any]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    return {
        "hostAllowlist": env_cfg.get("hostAllowlist", []),
        "forbiddenHostTokens": env_cfg.get("forbiddenHostTokens", []),
        "artifactPolicy": env_cfg.get("artifactPolicy", {}),
    }


def _command_details(result: Any) -> list[str]:
    details: list[str] = []
    for output in (str(result.stdout or ""), str(result.stderr or "")):
        for line in output.splitlines():
            normalized = line.strip()
            if normalized and normalized not in details:
                details.append(normalized)
    if not details:
        return [f"exit={result.returncode}"]
    if len(details) <= COMMAND_SUMMARY_DETAIL_LIMIT:
        return details
    retained = details[:COMMAND_SUMMARY_DETAIL_LIMIT]
    retained.append("additional command output retained in report.json")
    return retained


def command_provider_conformance(args: argparse.Namespace) -> dict[str, Any]:
    runner_args: list[str] = []
    if args.matrix:
        runner_args.extend(("--matrix", "--capability-id", args.capability_id))
    else:
        runner_args.extend(
            (
                "--adapter-id",
                args.adapter_id,
                "--environment",
                args.env,
                "--layer",
                args.layer,
            )
        )
    if args.execute:
        runner_args.append("--execute")
    for option, value in (
        ("--image-digest", args.image_digest),
        ("--data-digest", args.data_digest),
    ):
        if value:
            runner_args.extend((option, value))
    exit_code = _provider_conformance_runner().main(runner_args)
    return {
        "exitCode": exit_code,
        "summary": (
            "stackctl provider-conformance passed"
            if exit_code == 0
            else "stackctl provider-conformance failed"
        ),
        "details": [
            f"adapter={args.adapter_id or '<binding-derived>'}",
            f"capability={args.capability_id or '<single-cell>'}",
            f"environment={args.env or '<matrix>'}",
            f"layer={args.layer or '<matrix>'}",
            f"matrix={args.matrix}",
            f"executed={args.execute}",
        ],
    }


def command_matrix(args: argparse.Namespace) -> dict[str, Any]:
    profile = str(getattr(args, "profile", PROFILE_LOCAL_ENV_GATE) or PROFILE_LOCAL_ENV_GATE)
    if profile != PROFILE_LOCAL_ENV_GATE:
        return {
            "exitCode": 2,
            "summary": f"unsupported matrix profile: {profile}",
            "details": [f"supported: {PROFILE_LOCAL_ENV_GATE}"],
        }
    return run_local_env_gate_matrix(
        package_fn=command_package,
        up_fn=command_up,
        health_fn=command_health,
        verify_fn=command_verify,
        down_fn=command_down,
        include_l0=not bool(getattr(args, "skip_l0", False)),
        cache_mode=str(getattr(args, "cache_mode", "auto") or "auto"),
        auto_wipe_drift=not bool(getattr(args, "no_auto_wipe_drift", False)),
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "package": command_package,
        "verify": command_verify,
        "matrix": command_matrix,
        "provider-conformance": command_provider_conformance,
        "up": command_up,
        "product-telemetry-log-sink": command_product_telemetry_log_sink,
        "down": command_down,
        "consumer-lease": command_consumer_lease,
        "status": command_status,
        "health": command_health,
        "inspect": command_inspect,
        "doctor": command_doctor,
        "content-readiness": command_content_readiness,
        "data-execution-fleet": command_data_execution_fleet,
        "content-uat": command_content_uat,
        "filter-catalog": command_filter_catalog,
        "repair": command_repair,
        "roll": command_roll,
        "deploy": command_deploy,
        "hosted-release-receipt": command_hosted_release_receipt,
    }
    payload = dispatch[args.command](args)
    return print_result(args, payload)


if __name__ == "__main__":
    raise SystemExit(main())
