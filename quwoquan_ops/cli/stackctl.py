#!/usr/bin/env python3
from __future__ import annotations

import argparse
import codecs
import concurrent.futures
import contextlib
import fcntl
import getpass
import hashlib
import http.client
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
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

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
from quwoquan_ops.cli.prod import collect_release_artifact_descriptors
from quwoquan_ops.cli.prod import finalize_mainline_release_artifact
from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.cli.prod import oci_supply_chain
from quwoquan_ops.cli.prod.prod_hosted_topology import (
    ProdHostedTopologyError,
    instance_for_stage as prod_hosted_instance_for_stage,
    load_access_manifest as load_prod_hosted_access_manifest,
    placement_check_name as prod_hosted_placement_check_name,
    resolve_plan as resolve_prod_hosted_plan,
    validate_host_coverage as validate_prod_hosted_host_coverage,
)
from quwoquan_ops.cli.alpha import content_release_runtime as alpha_content_release_runtime
from quwoquan_ops.cli.lib.compose_layout import compose_file_args, gamma_compose_files
from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS,
    TARGETS,
    get_environment,
    get_target,
    load_environment_topology,
)
from quwoquan_ops.cli.lib.experiment_policy_activation import (
    ExperimentPolicyActivationError,
    activate_search_experiment_policy,
)
from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceSession,
    LocalEnvironmentHTTPError,
    mint_local_filter_catalog_service_token,
    mint_local_product_ops_operator_token,
    open_reference_acceptance_session,
    prepare_local_environment_auth,
    request_local_environment_json,
)
from quwoquan_ops.cli.lib.premium_pool_release import (
    PremiumPoolReleaseError,
    execute_premium_pool_readback,
    execute_premium_pool_upsert,
    load_premium_pool_candidate_binding,
    open_premium_pool_operator_session,
)
from quwoquan_ops.cli.lib.local_gamma_object_storage import (
    prepare_local_gamma_object_storage,
)
from quwoquan_ops.cli.lib.local_environment_object_storage import (
    prepare_local_environment_object_storage,
)
from quwoquan_ops.cli.lib.product_telemetry_log_sink import (
    load_product_telemetry_log_sink,
)
from quwoquan_ops.cli.lib.public_domain_tls import (
    PublicDomainTlsError,
    issue_certificate,
    load_policy as load_public_domain_policy,
    root_certificate_path,
    tls_profile,
    verify_certificate,
)
from quwoquan_ops.cli.lib.local_target_handoff import (
    LOOPBACK_ADDRESS,
    LocalTargetHandoffError,
    materialize_handoff,
    target_for_hostname,
)
from quwoquan_ops.cli.lib.local_device_trust import (
    LocalDeviceTrustError,
    install_device_trust,
    release_device_trust,
    verify_device_trust,
)
from quwoquan_ops.cli.lib.local_provider_credentials import (
    load_nonprod_provider_environment,
    provider_environment_reference_names,
)
from quwoquan_ops.cli.lib.local_sms_provider_substitute import (
    prepare_local_sms_provider_substitute,
)
from quwoquan_ops.cli.lib.local_integration_service_mtls import (
    prepare_local_integration_service_mtls,
)
from quwoquan_ops.cli.lib.local_assistant_skill_package_keys import (
    prepare_local_assistant_skill_package_keys,
)
from quwoquan_ops.cli.lib.local_provider_protocol_substitute import (
    prepare_local_provider_protocol_substitute,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import read_latest_debug_otp
from quwoquan_ops.cli.lib.video_playback_evidence import (
    read_native_video_playback_evidence,
)
from quwoquan_ops.cli.lib.release_video_delivery import (
    ReleaseVideoDeliveryError,
    load_release_video_binding,
)
from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeOutcome,
    ProbeSource,
    ReadinessPhase,
    ShipReadinessReceipt,
    VerificationProfile,
    load_content_release_readiness_policy,
)
from quwoquan_ops.cli.lib.research_content_isolation import (
    verify_research_content_isolation,
)
from quwoquan_ops.cli.lib.data_execution_fleet import (
    FLEET_ACTIONS,
    manage_data_execution_fleet,
    resolve_data_execution_fleet_endpoint,
)
from quwoquan_ops.cli.lib.local_runtime_reservation import (
    acquire_local_runtime_use_lock,
    assert_local_runtime_available,
    local_runtime_operation_lock_path,
)
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    DEFAULT_BUILD_GRACE_SECONDS,
    acquire_consumer_lease,
    active_consumer_leases,
    release_consumer_lease,
)
from quwoquan_ops.cli.lib.startup_attempt_receipt import (
    load_startup_attempt,
    transition_startup_attempt,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix import (
    CANONICAL_TARGETS as CANONICAL_LOCAL_GATE_TARGETS,
    PROFILE_LOCAL_ENV_GATE,
    run_local_env_gate_matrix,
)
from quwoquan_ops.cli.lib.immutable_image_composition import (
    bind_packaged_image_composition,
    compose_image_environment_key,
    first_party_service_names,
    immutable_image_digest,
    local_release_image_environment_key,
    packaged_service_source_image_ref,
)
from quwoquan_ops.cli.lib.immutable_configuration_composition import (
    packaged_configuration_digest,
)
from quwoquan_ops.cli.lib.local_postgres_migration_drift import (
    format_drift_gate_block,
    probe_migration_drift,
)
from quwoquan_ops.cli.lib.package_reuse import (
    can_reuse_package,
    workspace_snapshot,
    write_package_fingerprint,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    load_candidate_manifest,
    validate_release_attestations,
    write_candidate_manifest,
)
from quwoquan_ops.cli.lib.nonprod_business_data import NONPROD_TARGETS
from quwoquan_ops.cli.lib.nonprod_data_verification import (
    run_nonprod_business_data_verification,
)
from quwoquan_ops.cli.lib.nonprod_data_evidence import (
    PROVIDER_CAPABILITIES as NONPROD_PROVIDER_CAPABILITIES,
    RELIABILITY_CASE_IDS as NONPROD_RELIABILITY_CASE_IDS,
    assemble_nonprod_gate_evidence,
)
from quwoquan_ops.cli.lib.nonprod_data_provisioner import (
    NonprodCandidateIdentity,
    NonprodDataProvisioner,
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
    LOCAL_FILTER_CATALOG_TARGETS,
    MUTATING_ACTIONS as FILTER_CATALOG_MUTATING_ACTIONS,
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
    PACKAGE_ROOT_OVERRIDE_ENV,
    activate_deployment_candidate,
    active_deployment_candidate,
    app_deployment_package_dir,
    deployment_candidate_dir,
    deployment_target_for_env,
    deployment_target_path,
    deployment_work_root,
    env_observability_run_dir,
    env_runs_root,
    legal_static_deployment_package_dir,
    output_root,
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
        # 推荐 policy 单轨：gamma 只绑定 canonical 内容摘要，不允许环境变体。
        ["python3", "quwoquan_ops/gate/verify_canonical_recommendation_policy.py"],
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
DISCOVERY_FEED_UAT_TEST_TARGET = (
    "test/user_acceptance/patrol/discovery/"
    "feed_load__user_acceptance_test.dart"
)
CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET = (
    "test/user_acceptance/patrol/discovery/"
    "feed_controlled_edge_recovery__user_acceptance_test.dart"
)
APP_CORE_READBACK_UAT_TEST_TARGET = (
    "test/user_acceptance/patrol/environment/"
    "app_core_readback__user_acceptance_test.dart"
)
IOS_DIRECT_FLUTTER_RUN_UAT = (
    ROOT / "quwoquan_app/scripts/device/verify_ios_hot_restart.py"
)
STARTUP_FIRST_FRAME_UAT = (
    ROOT / "quwoquan_app/scripts/device/verify_startup_first_frame.py"
)
APP_CONTENT_UAT_ENVELOPE_ARGUMENTS = (
    ("releaseId", "--data-release-id"),
    ("releaseClass", "--data-release-class"),
    ("productLifecycleState", "--product-lifecycle-state"),
    ("homepageId", "--data-release-homepage-id"),
    ("homepageTitle", "--data-release-homepage-title"),
    ("articleWorkId", "--data-release-article-work-id"),
    ("articleTitle", "--data-release-article-title"),
    ("imageWorkId", "--data-release-image-work-id"),
    ("imageTitle", "--data-release-image-title"),
    ("creatorName", "--data-release-creator-name"),
    ("tagLabel", "--data-release-tag-label"),
    ("videoAttribution", "--data-release-video-attribution"),
)
RUNTIME_RECOVERY_UAT_TEST_TARGET = (
    "test/user_acceptance/patrol/environment/"
    "runtime_recovery_journey__user_acceptance_test.dart"
)
ACCOUNT_ENFORCEMENT_GAMMA_UAT_MANIFEST = (
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "product-ops-service/smoke/account_enforcement_gamma_uat_manifest.json"
)
ACCOUNT_ENFORCEMENT_GAMMA_UAT_VALIDATOR = (
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "product-ops-service/smoke/account_enforcement_gamma_uat.py"
)
ACCOUNT_ENFORCEMENT_GAMMA_DEVICE_RUNNER = (
    "quwoquan_ops/tests/acceptance/user_acceptance/service_ops/"
    "product-ops-service/smoke/run_account_enforcement_device_matrix.py"
)

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


def _provider_config():
    from quwoquan_ops.cli.lib import provider_config

    return provider_config


GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS: tuple[tuple[str, str], ...] = tuple(
    (service, local_release_image_environment_key(service))
    for service in first_party_service_names()
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
    return packaged_service_source_image_ref(env_name, service)


PACKAGE_OCI_IMAGES_SCHEMA = "stackctl-package-oci-images"


def _bind_gamma_build_service_image_refs(
    env_name: str,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Bind deterministic build tags only while materializing a candidate."""

    refs: dict[str, str] = {}
    for service, local_key in GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        ref = _packaged_service_source_image_ref(env_name, service)
        refs[service] = ref
        environment[local_key] = ref
        environment[compose_image_environment_key(service)] = ref
    composition_version = immutable_image_digest(refs)
    environment["LOCAL_GAMMA_IMAGE_VERSION"] = composition_version
    environment["QWQ_COMPOSE_IMAGE_VERSION"] = composition_version
    environment["QWQ_COMPOSE_IMAGE_TAG"] = composition_version.removeprefix("sha256:")
    composition: dict[str, Any] = {
        "imageVersion": composition_version,
        "images": {
            service: {"ref": ref}
            for service, ref in sorted(refs.items())
        },
    }
    _bind_gamma_packaged_configuration_digest(env_name, environment, composition)
    return composition


def _load_package_bound_local_image_composition(
    env_name: str,
    target_name: str,
) -> dict[str, Any]:
    """Load exact image IDs from the activated or staging package manifest."""

    manifest_path = (
        runtime_shared_deployment_package_dir(env_name, target=target_name)
        / "oci-images.json"
    )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"package OCI image manifest is unreadable: {exc}") from exc
    required = {
        "schema",
        "environment",
        "target",
        "configurationDigest",
        "buildInputDigest",
        "imageDigest",
        "images",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise ValueError("package OCI image manifest fields mismatch")
    if manifest.get("schema") != PACKAGE_OCI_IMAGES_SCHEMA:
        raise ValueError("package OCI image manifest schema mismatch")
    if manifest.get("environment") != env_name or manifest.get("target") != target_name:
        raise ValueError("package OCI image manifest target identity mismatch")
    for field in ("configurationDigest", "buildInputDigest", "imageDigest"):
        if re.fullmatch(r"sha256:[0-9a-f]{64}", str(manifest.get(field) or "")) is None:
            raise ValueError(f"package OCI image manifest {field} is invalid")
    images = manifest.get("images")
    expected_services = {
        service for service, _ in GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS
    }
    if not isinstance(images, dict) or set(images) != expected_services:
        raise ValueError("package OCI image manifest service set mismatch")
    runtime_refs: dict[str, str] = {}
    normalized_images: dict[str, dict[str, str]] = {}
    for service in sorted(expected_services):
        descriptor = images.get(service)
        if not isinstance(descriptor, dict) or set(descriptor) != {
            "ref",
            "imageDigest",
        }:
            raise ValueError(f"package OCI image descriptor fields mismatch: {service}")
        build_ref = str(descriptor.get("ref") or "")
        image_digest = str(descriptor.get("imageDigest") or "")
        if build_ref != _packaged_service_source_image_ref(env_name, service):
            raise ValueError(f"package OCI build ref mismatch: {service}")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None:
            raise ValueError(f"package OCI image digest is invalid: {service}")
        runtime_refs[service] = image_digest
        normalized_images[service] = {
            "ref": build_ref,
            "imageDigest": image_digest,
        }
    actual_set_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            normalized_images,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if actual_set_digest != manifest["imageDigest"]:
        raise ValueError("package OCI image set digest mismatch")
    configuration_digest = packaged_configuration_digest(
        env_name,
        target=target_name,
    )
    if configuration_digest != manifest["configurationDigest"]:
        raise ValueError("package OCI configuration digest mismatch")
    return {
        "imageVersion": immutable_image_digest(runtime_refs),
        "configurationDigest": configuration_digest,
        "buildInputDigest": manifest["buildInputDigest"],
        "imageDigest": manifest["imageDigest"],
        "images": {
            service: {"ref": image_digest, "digest": image_digest}
            for service, image_digest in sorted(runtime_refs.items())
        },
    }


def _bind_gamma_packaged_service_image_refs(
    env_name: str,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Bind only exact OCI image IDs attested by the immutable package."""

    target_name = str(environment.get("QWQ_LOCAL_RELEASE_TARGET") or "").strip()
    if not target_name:
        raise ValueError("package-bound runtime target is missing")
    composition = _load_package_bound_local_image_composition(
        env_name,
        target_name,
    )
    _apply_gamma_image_composition(composition, environment)
    return composition


def _bind_gamma_packaged_configuration_digest(
    env_name: str,
    environment: dict[str, str],
    composition: dict[str, Any] | None = None,
) -> str:
    target_name = str(environment.get("QWQ_LOCAL_RELEASE_TARGET") or "").strip()
    digest = packaged_configuration_digest(
        env_name,
        target=target_name,
    )
    environment["LOCAL_GAMMA_CONFIG_VERSION"] = digest
    if composition is not None:
        composition["configurationDigest"] = digest
    return digest


def _resolve_gamma_release_image_composition(
    manifest_path: Path,
) -> dict[str, Any]:
    """Resolve one validated candidate manifest without mutating or pulling."""

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"formal release manifest is unreadable: {error}") from error
    if not isinstance(manifest, dict):
        raise ValueError("formal release manifest must be an object")
    finalize_mainline_release_artifact.validate_manifest(
        manifest,
        allowed_statuses={"candidate-ready", "deployable", "released"},
    )
    finalize_mainline_release_artifact.validate_manifest_files(
        manifest_path.parent,
        manifest,
    )
    images = manifest.get("images")
    if not isinstance(images, dict):
        raise ValueError("formal release manifest has no images")
    bound: dict[str, dict[str, str]] = {}
    for service, _ in GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        descriptor = images.get(service)
        if not isinstance(descriptor, dict):
            raise ValueError(f"formal release image is missing: {service}")
        digest = str(descriptor.get("digest") or "")
        ref = str(descriptor.get("ref") or "")
        repository = str(descriptor.get("repository") or "")
        if (
            re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            or ref != f"{repository}@{digest}"
        ):
            raise ValueError(f"formal release image is not exact: {service}")
        bound[service] = {"ref": ref, "digest": digest}
    composition_version = immutable_image_digest(
        {service: descriptor["ref"] for service, descriptor in bound.items()}
    )
    return {
        "candidateId": str(manifest["candidateId"]),
        "artifactDigest": str(manifest["artifactDigest"]),
        "imageVersion": composition_version,
        "images": bound,
    }


def _apply_gamma_image_composition(
    composition: dict[str, Any],
    environment: dict[str, str],
) -> None:
    """Project one already-validated composition into both Compose aliases."""

    configuration_digest = str(composition.get("configurationDigest") or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", configuration_digest) is None:
        raise ValueError("immutable runtime composition has no configuration digest")
    environment["LOCAL_GAMMA_CONFIG_VERSION"] = configuration_digest
    images = composition.get("images")
    if not isinstance(images, dict) or not images:
        raise ValueError("immutable image composition has no images")
    refs: dict[str, str] = {}
    for service, local_key in GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        descriptor = images.get(service)
        if not isinstance(descriptor, dict):
            raise ValueError(f"immutable image composition is missing: {service}")
        ref = str(descriptor.get("ref") or "")
        refs[service] = ref
        environment[local_key] = ref
        environment[compose_image_environment_key(service)] = ref
    actual_version = immutable_image_digest(refs)
    expected_version = str(composition.get("imageVersion") or "")
    if actual_version != expected_version:
        raise ValueError("immutable image composition version mismatch")
    environment["LOCAL_GAMMA_IMAGE_VERSION"] = actual_version
    environment["QWQ_COMPOSE_IMAGE_VERSION"] = actual_version
    environment["QWQ_COMPOSE_IMAGE_TAG"] = actual_version.removeprefix("sha256:")
    candidate_id = str(composition.get("candidateId") or "")
    artifact_digest = str(composition.get("artifactDigest") or "")
    if candidate_id:
        environment["QWQ_RELEASE_CANDIDATE_DIGEST"] = candidate_id
    if artifact_digest:
        environment["QWQ_RELEASE_ARTIFACT_DIGEST"] = artifact_digest


def _bind_gamma_release_image_refs(
    manifest_path: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Pull and bind exact candidate OCI refs for a formal local release."""

    composition = _resolve_gamma_release_image_composition(manifest_path)
    planned: list[tuple[str, str, str, str]] = []
    for service, environment_key in GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        descriptor = composition["images"][service]
        digest = descriptor["digest"]
        ref = descriptor["ref"]
        planned.append((service, environment_key, ref, digest))

    def pull_exact_image(
        item: tuple[str, str, str, str],
    ) -> tuple[tuple[str, str, str, str], subprocess.CompletedProcess[str]]:
        return item, run(["docker", "pull", "--platform", "linux/amd64", item[2]])

    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, len(planned))
    ) as executor:
        futures = [executor.submit(pull_exact_image, item) for item in planned]
        for future in concurrent.futures.as_completed(futures):
            item, pull = future.result()
            if pull.returncode != 0:
                failures.append(
                    f"{item[0]}: "
                    + (pull.stderr.strip() or pull.stdout.strip() or "pull failed")
                )
    if failures:
        raise ValueError(
            "formal release exact OCI pull failed: " + "; ".join(sorted(failures))
        )

    _bind_gamma_packaged_configuration_digest(
        str(environment.get("QWQ_LOCAL_RELEASE_ENV") or ""),
        environment,
        composition,
    )
    _apply_gamma_image_composition(composition, environment)
    return composition


def _bind_gamma_release_teardown_image_refs(
    manifest_path: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    """Bind the exact candidate identity for teardown without pulling images."""

    composition = _resolve_gamma_release_image_composition(manifest_path)
    _bind_gamma_packaged_configuration_digest(
        str(environment.get("QWQ_LOCAL_RELEASE_ENV") or ""),
        environment,
        composition,
    )
    _apply_gamma_image_composition(composition, environment)
    return composition


def _inspect_gamma_release_runtime(
    release_composition: dict[str, Any],
    environment: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Prove that local containers actually run every exact candidate ref."""

    images = release_composition.get("images")
    if not isinstance(images, dict) or not images:
        raise ValueError("formal release composition has no images")
    project = str(
        environment.get("LOCAL_GAMMA_COMPOSE_PROJECT_NAME") or "quwoquan_service"
    ).strip()
    def inspect_service(item: tuple[str, Any]) -> tuple[str, dict[str, str]]:
        service, descriptor = item
        if not isinstance(descriptor, dict):
            raise ValueError(f"formal image descriptor is invalid: {service}")
        expected_ref = str(descriptor.get("ref") or "")
        expected_digest = str(descriptor.get("digest") or "")
        container_lookup = run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.project={project}",
                "--filter",
                f"label=com.docker.compose.service={service}",
            ],
            env=environment,
        )
        container_ids = [
            line.strip()
            for line in container_lookup.stdout.splitlines()
            if line.strip()
        ]
        if container_lookup.returncode != 0 or len(container_ids) != 1:
            raise ValueError(
                f"formal runtime must have exactly one {service} container; "
                f"found {len(container_ids)}"
            )
        container_id = container_ids[0]
        inspect_result = run(["docker", "inspect", container_id], env=environment)
        if inspect_result.returncode != 0:
            raise ValueError(f"formal runtime inspect failed: {service}")
        try:
            inspected = json.loads(inspect_result.stdout)
            container = inspected[0]
            actual_ref = str(container["Config"]["Image"])
            runtime_image_id = str(container["Image"])
            state = container["State"]
            status = str(state["Status"])
            health = str((state.get("Health") or {}).get("Status") or "not-declared")
        except (IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"formal runtime inspect is not canonical: {service}"
            ) from error
        if actual_ref != expected_ref:
            raise ValueError(
                f"formal runtime image differs from candidate: {service}"
            )
        if status != "running" or health not in {"healthy", "not-declared"}:
            raise ValueError(
                f"formal runtime is not ready: {service} status={status} health={health}"
            )
        image_result = run(["docker", "image", "inspect", expected_ref], env=environment)
        if image_result.returncode != 0:
            raise ValueError(f"formal local image inspect failed: {service}")
        try:
            local_images = json.loads(image_result.stdout)
            repo_digests = local_images[0].get("RepoDigests") or []
        except (IndexError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"formal local image inspect is not canonical: {service}"
            ) from error
        if expected_ref not in repo_digests:
            raise ValueError(
                f"formal local image has no exact pulled digest: {service}"
            )
        return service, {
            "ref": expected_ref,
            "digest": expected_digest,
            "containerId": container_id,
            "runtimeImageId": runtime_image_id,
            "status": status,
            "health": health,
        }

    items = sorted(images.items())
    runtime_images: dict[str, dict[str, str]] = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, len(items))
    ) as executor:
        futures = [executor.submit(inspect_service, item) for item in items]
        for future in concurrent.futures.as_completed(futures):
            service, runtime = future.result()
            runtime_images[service] = runtime
    return dict(sorted(runtime_images.items()))


def _bind_gamma_external_provider_environment(
    environment: dict[str, str],
) -> str | None:
    """Materialize Gamma-local Port-equivalent provider substitutes."""
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
    public_bases = (
        get_target(load_environment_topology(), "gamma-local").get("publicBases")
        or {}
    )
    media_delivery_origin = _public_url_origin(str(public_bases["mediaImage"]))
    environment.setdefault(
        "CONTENT_MEDIA_DELIVERY_BASE_URL",
        media_delivery_origin,
    )
    environment.setdefault(
        "CONTENT_MEDIA_UPLOAD_BASE_URL",
        str(public_bases["mediaUpload"]),
    )
    environment.setdefault(
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL",
        media_delivery_origin,
    )
    environment.setdefault(
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL",
        str(public_bases["mediaUpload"]),
    )
    _sync_object_storage_binding_aliases(environment, prefix="LOCAL_GAMMA")
    return None


def _bind_formal_local_release_provider_environment(
    environment: dict[str, str],
    *,
    environment_name: str,
    target_name: str,
    workload: str = "full",
    debug_sms_substitute: bool = False,
) -> str | None:
    """Bind target-isolated infrastructure and protected nonprod Providers."""

    try:
        auth = prepare_local_environment_auth(environment_name, target_name)
        storage = prepare_local_environment_object_storage(
            environment=environment_name,
            target_name=target_name,
            edge_port=profile_ports(
                load_port_manifest(),
                str(get_target(load_environment_topology(), target_name)["portProfile"]),
            )["object-storage-edge"],
            # The shared infrastructure Compose retains this private adapter
            # prefix. Service workloads consume only QWQ_COMPOSE_* aliases.
            environment_prefix="LOCAL_GAMMA",
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return f"{target_name} infrastructure materialization failed: {exc}"
    environment.update(auth.environment)
    environment.update(storage.environment)
    environment["QWQ_DEBUG_SMS_SUBSTITUTE_ENABLED"] = (
        "true" if debug_sms_substitute else "false"
    )
    environment["QWQ_DEBUG_PROVIDER_SUBSTITUTE_ENABLED"] = (
        "true" if debug_sms_substitute else "false"
    )
    public_bases = get_target(load_environment_topology(), target_name).get(
        "publicBases"
    ) or {}
    media_delivery_origin = _public_url_origin(str(public_bases["mediaImage"]))
    environment.setdefault("LOCAL_GAMMA_MEDIA_UPLOAD_BASE_URL", storage.host_endpoint)
    environment.setdefault("CONTENT_MEDIA_DELIVERY_BASE_URL", media_delivery_origin)
    environment.setdefault(
        "CONTENT_MEDIA_UPLOAD_BASE_URL", str(public_bases["mediaUpload"])
    )
    environment.setdefault(
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL", media_delivery_origin
    )
    environment.setdefault(
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL", str(public_bases["mediaUpload"])
    )
    _sync_object_storage_binding_aliases(environment, prefix="LOCAL_GAMMA")
    try:
        integration_mtls = prepare_local_integration_service_mtls(
            environment_name,
            target_name,
        )
    except (OSError, PublicDomainTlsError, RuntimeError, ValueError) as exc:
        return (
            f"{target_name} integration-service mTLS materialization failed: "
            f"{exc}"
        )
    environment.update(integration_mtls.environment)
    # Nonprod mesh OTP client requires the canonical internal HTTP URL; the
    # schema default remains HTTPS for packaged/prod-shaped configs.
    environment["INTEGRATION_EXTERNAL_INTERACTION_BASE_URL"] = (
        "http://integration-service:18086"
    )
    if workload == "full":
        try:
            skill_keys = prepare_local_assistant_skill_package_keys(
                environment_name,
                target_name,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return (
                f"{target_name} assistant Skill package key materialization "
                f"failed: {exc}"
            )
        environment.update(skill_keys.environment)
    if workload in {"content-release", "content-commercial"}:
        # Bounded content workloads own release import/public read and the
        # optional Product Ops premium command. External
        # login, embedding, assistant, integration and RTC capabilities are
        # not started by this workload; validating their protected material
        # here would incorrectly turn unrelated full-workload prerequisites
        # into a content activation or premium-command blocker.
        # user-service still mounts integration mTLS PEMs on every local up,
        # so empty /dev/null mounts must never reach Compose interpolation.
        return None
    if debug_sms_substitute:
        try:
            sms_substitute = prepare_local_sms_provider_substitute(
                environment_name,
                target_name,
                port=profile_ports(
                    load_port_manifest(),
                    str(
                        get_target(load_environment_topology(), target_name)[
                            "portProfile"
                        ]
                    ),
                )["sms-provider-substitute"],
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return f"{target_name} SMS substitute materialization failed: {exc}"
        environment.update(sms_substitute.environment)
        try:
            provider_substitute = prepare_local_provider_protocol_substitute(
                environment_name,
                target_name,
                port=profile_ports(
                    load_port_manifest(),
                    str(
                        get_target(load_environment_topology(), target_name)[
                            "portProfile"
                        ]
                    ),
                )["provider-protocol-substitute"],
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return (
                f"{target_name} Provider protocol substitute materialization "
                f"failed: {exc}"
            )
        environment.update(provider_substitute.environment)
    provider_error = _bind_local_external_provider_environment(
        environment,
        environment_name=environment_name,
        target_name=target_name,
        storage_prefix="LOCAL_GAMMA",
        debug_local=debug_sms_substitute,
    )
    if provider_error is not None:
        return provider_error
    try:
        provider_config = _provider_config()
        provider_config.project_provider_secret_bundles(
            environment=environment_name,
            target=target_name,
            source=environment,
        )
        provider_config_result = provider_config.compile_provider_config(
            action="render",
            environment=environment_name,
            target=target_name,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return f"{target_name} Provider configuration materialization failed: {exc}"
    if int(provider_config_result.get("exitCode", 2)) != 0:
        details = "; ".join(
            str(detail)
            for detail in provider_config_result.get("details", [])
            if str(detail).strip()
        )
        return (
            f"{target_name} Provider configuration materialization failed: "
            f"{details or 'required material is incomplete'}"
        )
    return None


def _bind_gamma_down_parse_environment(environment: dict[str, str]) -> None:
    """Satisfy non-identity Compose interpolation used only while tearing down."""

    storage_placeholders = {
        "ENDPOINT": "https://unused.invalid",
        "BUCKET": "unused",
        "REGION": "unused",
        "ACCESS_KEY_ID": "unused",
        "ACCESS_KEY_SECRET": "unused",
        "CDN_SIGN_KEY": "unused",
        "TLS_DIR": "/tmp",
        "CA_FILE": "/tmp/unused-local-managed-ca.crt",
    }
    for suffix, value in storage_placeholders.items():
        source_key = f"LOCAL_GAMMA_OBJECT_STORAGE_{suffix}"
        compose_key = f"QWQ_COMPOSE_OBJECT_STORAGE_{suffix}"
        environment.setdefault(source_key, value)
        environment.setdefault(compose_key, environment[source_key])
    environment.update(
        {
            "AUTH_JWT_SECRET": "down-not-used",
            "AUTH_JWT_ISSUER": "down-not-used",
            "AUTH_JWT_AUDIENCE": "down-not-used",
            "AUTH_JWT_TOKEN_VERSION": "down-not-used",
            "AUTH_DEVICE_TICKET_SECRET": "down-not-used",
            "AUTH_DEVICE_TICKET_ISSUER": "down-not-used",
            "AUTH_DEVICE_TICKET_AUDIENCE": "down-not-used",
            "AUTH_DEVICE_TICKET_TOKEN_VERSION": "down-not-used",
            "OTP_CODE_REF_ACTIVE_KEY_VERSION": "down-not-used",
            "OTP_CODE_REF_KEYS_JSON": '{"down-not-used":"down-not-used"}',
            "ASSISTANT_SKILL_PACKAGE_TRUSTED_PUBLIC_KEYS_JSON": (
                '{"down-not-used":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}'
            ),
            "QWQ_PUSH_TOKEN_ENCRYPTION_KEY": "down-not-used",
            "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET": "down-not-used",
            "RTC_MEDIA_API_KEY": "down-not-used",
            "RTC_MEDIA_API_SECRET": "down-not-used",
            "INTEGRATION_SERVICE_MTLS_CA_FILE": "/tmp/down-not-used",
            "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE": "/tmp/down-not-used",
            "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE": "/tmp/down-not-used",
            "INTEGRATION_PUSH_APNS_KEY_FILE": "/tmp/down-not-used",
            "INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE": "/tmp/down-not-used",
        }
    )


def _load_gamma_runtime_image_composition(
    target_name: str,
) -> tuple[dict[str, Any], str] | None:
    """Read the canonical current runtime binding; absence permits package derivation."""

    try:
        receipt = load_startup_attempt(target_name)
    except ValueError as exc:
        raise ValueError(f"runtime image composition receipt is unreadable: {exc}") from exc
    if receipt is None or receipt.get("status") == "stopped":
        return None
    if receipt.get("status") not in {"partial", "running"}:
        raise ValueError("runtime startup attempt has no resources to tear down")
    expected_environment = target_name.removesuffix("-local")
    if receipt.get("target") != target_name:
        raise ValueError("runtime image composition receipt target mismatch")
    receipt_environment = str(receipt.get("env") or "").strip()
    if receipt_environment != expected_environment:
        raise ValueError("runtime image composition receipt environment mismatch")
    compose_project = str(receipt.get("composeProject") or "").strip()
    if not compose_project:
        raise ValueError("runtime image composition receipt has no Compose project")
    expected_project_prefix = f"quwoquan_{expected_environment}_release"
    if (
        re.fullmatch(
            re.escape(expected_project_prefix) + r"(?:_[a-zA-Z0-9_-]+)?",
            compose_project,
        )
        is None
    ):
        raise ValueError("runtime image composition receipt Compose project mismatch")
    composition = receipt.get("imageComposition")
    if not isinstance(composition, dict):
        raise ValueError("runtime image composition receipt has no image composition")
    images = composition.get("images")
    if not isinstance(images, dict):
        raise ValueError("runtime image composition receipt has invalid images")
    refs: dict[str, str] = {}
    for service, _ in GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS:
        descriptor = images.get(service)
        if not isinstance(descriptor, dict):
            raise ValueError(f"runtime image composition is missing: {service}")
        refs[service] = str(descriptor.get("ref") or "")
    actual_version = immutable_image_digest(refs)
    expected_version = str(composition.get("imageVersion") or "")
    if actual_version != expected_version:
        raise ValueError("runtime image composition version mismatch")
    if str(receipt.get("imageTransportTag") or "") != actual_version:
        raise ValueError("runtime image composition receipt version mismatch")
    configuration_digest = str(receipt.get("configurationDigest") or "").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", configuration_digest) is None:
        raise ValueError("runtime image composition receipt has no configuration digest")
    composition = dict(composition)
    composition["configurationDigest"] = configuration_digest
    return composition, compose_project


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
    debug_local: bool = True,
) -> str | None:
    """Bind the canonical non-production Provider substitute topology."""

    try:
        values = load_nonprod_provider_environment(
            environment=environment_name,
            target_name=target_name,
            source=environment,
            debug_local=debug_local,
        )
    except (RuntimeError, ValueError) as exc:
        return f"{target_name} external Provider preflight failed: {exc}"
    environment.update(values)
    _sync_object_storage_binding_aliases(environment, prefix=storage_prefix)
    if values.get("CONTENT_EMBEDDING_ENDPOINT"):
        environment.setdefault(
            "QWQ_COMPOSE_EMBEDDING_ENDPOINT",
            values["CONTENT_EMBEDDING_ENDPOINT"],
        )
    if values.get("CONTENT_EMBEDDING_API_KEY"):
        environment.setdefault(
            "QWQ_COMPOSE_EMBEDDING_API_KEY",
            values["CONTENT_EMBEDDING_API_KEY"],
        )
    return None


def _bind_package_provider_reference_environment(
    environment: dict[str, str],
    *,
    environment_name: str,
) -> None:
    """Bind non-runtime interpolation values for an OCI-only build.

    The build-only script exits before any container starts.  These values are
    never Provider credentials, never validated as Provider readiness and may
    not be copied into a package or image.  Their sole purpose is to let the
    canonical Compose definition parse while building source-digest images.
    """

    endpoint_keys, secret_keys = provider_environment_reference_names(
        environment_name
    )
    # user-service Compose always mounts integration mTLS host files; package
    # interpolation must satisfy the required-file contract without runtime PEMs.
    package_keys = set(endpoint_keys) | set(secret_keys) | {
        "INTEGRATION_SERVICE_MTLS_CA_FILE",
        "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE",
        "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE",
    }
    for key in sorted(package_keys):
        if key.endswith("_FILE"):
            value = "/tmp/qwq-package-build-not-runtime"
        elif key.endswith("_JSON"):
            value = '{"package-build-not-runtime":"package-build-not-runtime"}'
        elif key.endswith("_URL") or key.endswith("_ENDPOINT"):
            value = "https://127.0.0.1"
        else:
            value = "package-build-not-runtime"
        environment[key] = value


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
        f"{prefix}_OBJECT_STORAGE_CDN_SIGN_KEY": "CONTENT_CDN_SIGN_KEY",
    }
    storage_to_compose = {
        f"{prefix}_OBJECT_STORAGE_ENDPOINT": "QWQ_COMPOSE_OBJECT_STORAGE_ENDPOINT",
        f"{prefix}_OBJECT_STORAGE_BUCKET": "QWQ_COMPOSE_OBJECT_STORAGE_BUCKET",
        f"{prefix}_OBJECT_STORAGE_REGION": "QWQ_COMPOSE_OBJECT_STORAGE_REGION",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_ID": "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_ID",
        f"{prefix}_OBJECT_STORAGE_ACCESS_KEY_SECRET": "QWQ_COMPOSE_OBJECT_STORAGE_ACCESS_KEY_SECRET",
        f"{prefix}_OBJECT_STORAGE_CDN_SIGN_KEY": "QWQ_COMPOSE_OBJECT_STORAGE_CDN_SIGN_KEY",
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
    if getattr(args, "formal_release", False):
        command.append("--formal-release")
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
        ROOT / "quwoquan_ops" / "environments" / "compose" / "object-storage-lifecycle.json",
        ROOT / "quwoquan_ops" / "external" / "livekit" / "base" / "livekit.yaml",
        ROOT / "quwoquan_ops" / "environments" / "gamma" / "local" / "Caddyfile",
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


def _build_package_bound_local_images(
    env_name: str,
    target_name: str,
    *,
    report_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """Build and attest the exact local OCI inputs during package, never during up."""
    topology = load_environment_topology()
    environment = _gamma_env_from_port_manifest(topology, target_name)
    _bind_gamma_down_parse_environment(environment)
    environment.update(
        {
            "QWQ_RUN_ROOT": str(report_dir.resolve()),
            "QWQ_OBSERVABILITY_RUN_ROOT": str(
                env_observability_run_dir(env_name, report_dir.name).resolve()
            ),
            "QWQ_WORKLOAD": "full",
            "QWQ_PRODUCT_TELEMETRY_AVAILABLE": "1",
            # Compose parses storage/provider variables while building, but no
            # build step may contact or persist them into an image.
            "LOCAL_GAMMA_OBJECT_STORAGE_ENDPOINT": "https://127.0.0.1",
            "LOCAL_GAMMA_OBJECT_STORAGE_BUCKET": "package-build-only",
            "LOCAL_GAMMA_OBJECT_STORAGE_REGION": "local",
            "LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_ID": "package-build-only",
            "LOCAL_GAMMA_OBJECT_STORAGE_ACCESS_KEY_SECRET": "package-build-only",
            "LOCAL_GAMMA_OBJECT_STORAGE_CDN_SIGN_KEY": "package-build-only",
            "LOCAL_GAMMA_OBJECT_STORAGE_TLS_DIR": str(
                (target_cache_dir(target_name) / "package" / "tls").resolve()
            ),
            "LOCAL_GAMMA_OBJECT_STORAGE_CA_FILE": str(
                (target_cache_dir(target_name) / "package" / "tls" / "root.crt").resolve()
            ),
        }
    )
    _sync_object_storage_binding_aliases(environment, prefix="LOCAL_GAMMA")
    _bind_package_provider_reference_environment(
        environment,
        environment_name=env_name,
    )
    composition = _bind_gamma_build_service_image_refs(env_name, environment)
    command = [
        "bash",
        "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
        "--build-only",
    ]

    def inspect_images() -> tuple[dict[str, dict[str, str]], list[str]]:
        inspected: dict[str, dict[str, str]] = {}
        missing: list[str] = []
        for service, descriptor in sorted(composition["images"].items()):
            image_ref = str(descriptor["ref"])
            inspect = run(
                ["docker", "image", "inspect", "--format", "{{.Id}}", image_ref]
            )
            image_digest = inspect.stdout.strip()
            if (
                inspect.returncode != 0
                or re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest) is None
            ):
                missing.append(service)
                continue
            inspected[service] = {
                "ref": image_ref,
                "imageDigest": image_digest,
            }
        return inspected, missing

    # Source-digest tags are common build artifacts.  Rebuilding the same tag
    # for every target produces non-deterministic OCI config timestamps and
    # lets the later target overwrite the earlier target's attested image ID.
    # Build exactly once when any source image is absent; otherwise attest the
    # already materialized immutable source set for every target package.
    images, missing_images = inspect_images()
    if missing_images:
        result = run(command, env=environment)
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip()
                or result.stdout.strip()
                or f"package-bound OCI build failed with exit={result.returncode}"
            )
        images, missing_images = inspect_images()
    if missing_images:
        raise RuntimeError(
            "package-bound OCI digest is unavailable: " + ", ".join(missing_images)
        )
    image_set_digest = "sha256:" + hashlib.sha256(
        json.dumps(
            images,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    manifest = {
        "schema": PACKAGE_OCI_IMAGES_SCHEMA,
        "environment": env_name,
        "target": target_name,
        "configurationDigest": composition["configurationDigest"],
        "buildInputDigest": composition["imageVersion"],
        "imageDigest": image_set_digest,
        "images": images,
    }
    manifest_path = (
        runtime_shared_deployment_package_dir(env_name, target=target_name)
        / "oci-images.json"
    )
    write_json(manifest_path, manifest)
    return manifest_path, manifest


def _materialize_release_evidence_configuration(
    env_name: str,
    *,
    target: str = "",
) -> dict[str, str]:
    """校验 CI release evidence 与环境自治服务包一致，并记录供应链证据。

    Release evidence 是可删除的回读副本，不再成为第二份运行配置。运行时始终只消费
    服务包中的 config/config.yaml，其 CONFIG_VERSION 为内容摘要。
    """
    artifact_root_value = os.environ.get("QWQ_PROD_RELEASE_ARTIFACT_ROOT", "").strip()
    if not artifact_root_value:
        return {}
    artifact_root = Path(artifact_root_value).expanduser()
    if not artifact_root.is_absolute():
        artifact_root = ROOT / artifact_root
    manifest_path = artifact_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"prod release artifact manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError(f"invalid release evidence manifest: {manifest_path}")
    allowed_statuses = (
        {"deployable", "released"}
        if env_name == "prod"
        else {"candidate-ready", "deployable", "released"}
    )
    finalize_mainline_release_artifact.validate_manifest(
        manifest, allowed_statuses=allowed_statuses
    )
    finalize_mainline_release_artifact.validate_manifest_files(
        artifact_root,
        manifest,
    )
    candidate_id = str(manifest["candidateId"])
    configuration_packages = manifest["configurationPackages"][env_name]
    package_root = deployment_target_path(
        deployment_target_for_env(env_name, target=target),
        "packages",
        "services",
    )
    archive_digest = _sha256_file(manifest_path)
    for service, descriptor in configuration_packages.items():
        relative_path = str(descriptor["path"])
        source = artifact_root / relative_path
        if not source.is_file():
            raise FileNotFoundError(
                f"{env_name} release evidence file missing: {source}"
            )
        destination_dir = package_root / str(service)
        report_path = destination_dir / "provenance.json"
        effective_config = destination_dir / "config/config.yaml"
        if not report_path.is_file() or not effective_config.is_file():
            raise FileNotFoundError(f"prod service package missing: {destination_dir}")
        source_digest = _sha256_file(source)
        effective_digest = _sha256_file(effective_config)
        if source_digest != effective_digest:
            raise ValueError(
                "release evidence config differs from autonomous package: "
                f"{env_name}/{service}"
            )
        provenance = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(provenance, dict):
            raise ValueError(f"service package provenance missing: {report_path}")
        if (provenance.get("digests") or {}).get("config") != effective_digest:
            raise ValueError(f"service package config provenance invalid: {report_path}")
        provenance["releaseEvidence"] = {
            "manifest": relpath(manifest_path),
            "evidenceFileDigest": archive_digest,
            "artifactDigest": manifest["artifactDigest"],
            "candidateId": candidate_id,
            "verifiedConfigDigest": effective_digest,
        }
        write_json(report_path, provenance)
    source = manifest["source"]
    return {
        "candidateId": candidate_id,
        "artifactDigest": str(manifest["artifactDigest"]),
        "sourceGitSha": str(source["gitSha"]),
        "sourceTreeDigest": str(source["treeDigest"]),
    }


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
    package_parser.add_argument(
        "--release-attestation",
        default="",
        help="Canonical candidate Data release attestation bound into a full package.",
    )
    package_parser.add_argument(
        "--rollback-release-attestation",
        default="",
        help="Canonical rollback Data release attestation bound into a full package.",
    )
    package_parser.add_argument("--target", choices=TARGETS, default="")
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
    package_parser.add_argument("--application-packages-dir", default="")
    package_parser.add_argument("--application-package-payloads-dir", default="")
    package_parser.add_argument("--application-evidence-ref", default="")
    package_parser.add_argument("--public-web-manifest", default="")
    package_parser.add_argument("--android-release-manifest", default="")
    package_parser.add_argument("--ops-portal-provenance", default="")
    package_parser.add_argument("--contract-graph", default="")
    package_parser.add_argument("--provider-evidence", default="")
    package_parser.add_argument("--provider-raw-dir", default="")
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
    verify_parser.add_argument("--data-release-id", default="")
    verify_parser.add_argument("--data-verify-run-id", default="")
    verify_parser.add_argument("--data-manifest-digest", default="")
    verify_parser.add_argument(
        "--nonprod-data-evidence",
        default="",
        help=(
            "Alpha/Beta/Gamma integration profile 的 Provider/share/fault gate "
            "evidence；只接受 QWQ_OUTPUT_ROOT 下的候选绑定 JSON"
        ),
    )
    verify_parser.add_argument(
        "--data-lifecycle-exit-ref",
        default="",
        help="release profile 绑定的 canonical rollback/replay lifecycle Exit ref",
    )
    verify_parser.add_argument(
        "--backup-recovery-receipt",
        default="",
        help="prod release 的 hosted 灾备隔离恢复 receipt；缺失即阻断",
    )
    verify_parser.add_argument("--distribution-root", default="")
    verify_parser.add_argument("--verify-hosted", action="store_true")

    matrix_parser = subparsers.add_parser(
        "matrix",
        help="串行 Alpha/Beta/Gamma 本地门禁矩阵（local-env-gate）",
    )
    matrix_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    matrix_parser.add_argument(
        "--profile",
        choices=(PROFILE_LOCAL_ENV_GATE,),
        default=PROFILE_LOCAL_ENV_GATE,
    )
    matrix_parser.add_argument(
        "--targets",
        required=True,
        help="必须为 alpha-local,beta-local,gamma-local",
    )
    matrix_parser.add_argument(
        "--skip-l0",
        action="store_true",
        help="跳过 make commit-gate（仅编排环境段）",
    )
    matrix_parser.add_argument("--release-attestation", required=True)
    matrix_parser.add_argument("--rollback-release-attestation", required=True)
    matrix_parser.add_argument(
        "--nonprod-data-evidence",
        action="append",
        metavar="TARGET=PATH",
        required=True,
        help=(
            "full integration 必须消费的 Provider/share/reliability evidence；"
            "Alpha/Beta/Gamma 各显式传入一次"
        ),
    )
    matrix_parser.add_argument("--ios-simulator-device", required=True)
    matrix_parser.add_argument("--android-emulator-device", required=True)
    matrix_parser.add_argument("--android-physical-device", required=True)

    tls_parser = subparsers.add_parser(
        "tls",
        help="local-managed 与公共 DNS-01 TLS 的统一预检、签发和验证门面",
    )
    tls_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    tls_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local", "prod-sim"),
        required=True,
    )
    tls_parser.add_argument(
        "--action",
        choices=("prevalidate", "verify", "issue"),
        required=True,
    )
    tls_parser.add_argument(
        "--confirm-protected-apply",
        action="store_true",
        help="明确确认 DNS-01 challenge 与 ACME 外部状态变更；local-managed 不需要",
    )

    device_trust_parser = subparsers.add_parser(
        "device-trust",
        help="安装并验证受管 Simulator/Emulator 的 local-managed 系统信任",
    )
    device_trust_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    device_trust_parser.add_argument(
        "--platform",
        choices=("ios-simulator", "android-emulator"),
        required=True,
    )
    device_trust_parser.add_argument(
        "--action",
        choices=("install", "verify", "release"),
        required=True,
    )
    device_trust_parser.add_argument("--device", default="")
    device_trust_parser.add_argument("--lease-id", default="")
    device_trust_parser.add_argument(
        "--defer-endpoint-probe",
        action="store_true",
        help=(
            "仅安装 Simulator 系统根证书，不探测受管端点；"
            "只允许 App 启动入口，环境/UAT verify 仍须端点成功"
        ),
    )
    device_trust_parser.add_argument(
        "--allow-unprovisioned-system-trust",
        action="store_true",
        help=(
            "只允许 Android 直接 App 启动在不可写系统 CA 的 Emulator 上进入降级 Shell；"
            "不会产生 system-trust/UAT 通过证据"
        ),
    )
    device_trust_parser.add_argument("--report-dir", default=argparse.SUPPRESS)

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
    provider_conformance_parser.add_argument(
        "--environment-matrix",
        action="store_true",
        help=(
            "按 generated ContractGraph/Binding 动态执行指定环境全部 capability "
            "的 local_contract/api_integration/user_acceptance 三层单元"
        ),
    )
    provider_conformance_parser.add_argument("--execute", action="store_true")
    provider_conformance_parser.add_argument("--image-digest", default="")
    provider_conformance_parser.add_argument("--data-digest", default="")

    provider_config_parser = subparsers.add_parser(
        "provider-config",
        help="校验、物化或比对 Binding/topology/Secret Bundle 编译结果",
    )
    provider_config_parser.add_argument(
        "provider_config_action",
        choices=("validate", "render", "diff"),
    )
    provider_config_parser.add_argument(
        "--env",
        choices=("alpha", "beta", "gamma", "prod"),
        required=True,
    )
    provider_config_parser.add_argument(
        "--target",
        choices=(
            "alpha-local",
            "beta-local",
            "gamma-local",
            "prod-hosted",
        ),
        required=True,
    )

    nonprod_data_evidence_parser = subparsers.add_parser(
        "nonprod-data-evidence",
        help="从显式真实回执装配候选绑定的非生产数据门禁 evidence",
    )
    nonprod_data_evidence_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    nonprod_data_evidence_parser.add_argument(
        "--target",
        choices=tuple(NONPROD_TARGETS),
        required=True,
    )
    nonprod_data_evidence_parser.add_argument(
        "--share-receipt",
        action="append",
        required=True,
        help="真实端侧分享 delivery CaseResult；必须显式传入三次",
    )
    nonprod_data_evidence_parser.add_argument(
        "--provider-receipt",
        action="append",
        required=True,
        metavar="ROLE=PATH",
        help=(
            "Provider Conformance user_acceptance receipt；ROLE 为 "
            + "|".join(NONPROD_PROVIDER_CAPABILITIES)
        ),
    )
    nonprod_data_evidence_parser.add_argument(
        "--reliability-receipt",
        action="append",
        required=True,
        metavar="CASE=PATH",
        help=(
            "候选绑定的可靠性 CaseResult；CASE 为 "
            + "|".join(NONPROD_RELIABILITY_CASE_IDS)
        ),
    )

    up_parser = subparsers.add_parser("up")
    up_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    up_parser.add_argument("--target", choices=TARGETS, default="")
    up_parser.add_argument("--env", choices=DEV_UP_ENVS, default="")
    up_parser.add_argument("--device-id", default="")
    up_parser.add_argument("--skip-app", action="store_true")
    up_parser.add_argument("--skip-build", action="store_true")
    up_parser.add_argument(
        "--formal-release",
        action="store_true",
        help="Fail-closed release mode: exact candidate images, no automatic repair or cleanup.",
    )
    up_parser.add_argument(
        "--release-manifest",
        default="",
        help="Canonical ReleaseEvidenceManifest required by --formal-release.",
    )
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
        choices=["content-release", "content-commercial", "full"],
        default="full",
    )
    up_parser.add_argument(
        "--data-release-readiness",
        default="",
        help=(
            "prod-sim 媒体演练必须消费的 canonical Data "
            "release-readiness.json；也可由 DATA_RELEASE_READINESS_RECEIPT 提供"
        ),
    )
    up_parser.add_argument("--rollout-mode", choices=["gray-initial", "carry-on", "full"], default="")

    dev_session_parser = subparsers.add_parser(
        "dev-session",
        help="幂等编排本地候选、full runtime、健康检查与可选 App handoff。",
    )
    dev_session_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    dev_session_parser.add_argument(
        "--env",
        choices=("alpha", "beta", "gamma"),
        default="",
    )
    dev_session_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        default="",
    )
    dev_session_parser.add_argument("--all-nonprod", action="store_true")
    dev_session_parser.add_argument("--release-attestation", required=True)
    dev_session_parser.add_argument("--rollback-release-attestation", required=True)
    dev_session_parser.add_argument("--device-id", default="")
    dev_session_parser.add_argument("--launch-app", action="store_true")

    log_sink_control_parser = subparsers.add_parser(
        "product-telemetry-log-sink",
        help="在 alpha/beta/gamma 本地目标受控执行 Elasticsearch 产品遥测日志端口验证。",
    )
    log_sink_control_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    log_sink_control_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
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
    down_parser.add_argument(
        "--workload",
        choices=["content-release", "content-commercial", "full"],
        default="",
        help="只停止匹配的 active workload；bounded workload 复用 full 时为无损 no-op。",
    )
    down_parser.add_argument(
        "--formal-release",
        action="store_true",
        help="Stop only the candidate-scoped immutable Compose project.",
    )
    down_parser.add_argument(
        "--release-manifest",
        default="",
        help="Canonical ReleaseEvidenceManifest required by formal teardown.",
    )
    down_parser.add_argument(
        "--purge-rebuildable-state",
        action="store_true",
        help=(
            "Delete only the runtime-receipt-bound Alpha/Beta/Gamma Compose "
            "volumes and target cache after stopping the target."
        ),
    )

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
        "--platform",
        choices=("android", "ios-simulator"),
        default="android",
    )
    consumer_lease_parser.add_argument(
        "--package-name",
        default="com.quwoquan.quwoquan_app",
    )
    consumer_lease_parser.add_argument("--bundle-id", default="")
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
    consumer_lease_parser.add_argument("--handoff-digest", default="")
    consumer_lease_parser.add_argument("--release-id", default="")
    consumer_lease_parser.add_argument("--manifest-digest", default="")
    consumer_lease_parser.add_argument("--readiness-receipt-digest", default="")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    status_parser.add_argument("--target", choices=TARGETS, required=True)

    health_parser = subparsers.add_parser("health")
    health_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    health_parser.add_argument("--target", choices=TARGETS, required=True)
    health_parser.add_argument(
        "--scope",
        choices=[
            "edge",
            "media",
            "service",
            "content-import",
            "content-consumer",
            "content-commercial",
            "full",
        ],
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
        "--host-id",
        default="",
        help="Select one logical prod-hosted host from access-isolation.yaml.",
    )
    inspect_parser.add_argument(
        "--deployment-instance",
        choices=("prevalidate", "gray", "prod"),
        default="prod",
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
    doctor_parser.add_argument("--host-id", default="")
    doctor_parser.add_argument(
        "--deployment-instance",
        choices=("prevalidate", "gray", "prod"),
        default="prod",
    )

    hosted_plan_parser = subparsers.add_parser(
        "prod-hosted-plan",
        help="render the read-only prod-hosted host/instance/replica execution plan",
    )
    hosted_plan_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    hosted_plan_parser.add_argument(
        "--deployment-instance",
        choices=("prevalidate", "gray", "prod"),
        required=True,
    )
    hosted_plan_parser.add_argument(
        "--plane",
        action="append",
        choices=("service", "edge"),
    )
    hosted_plan_parser.add_argument("--host-id", action="append", default=[])
    hosted_plan_parser.add_argument("--ssh-host", default="")

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
    content_readiness_parser.add_argument(
        "--release-id",
        default="",
        help="consumer/commercial readiness 绑定的 canonical Data releaseId",
    )
    content_readiness_parser.add_argument(
        "--verify-run-id",
        default="",
        help="canonical Data environment verify runId；禁止隐式选择 latest",
    )
    content_readiness_parser.add_argument(
        "--manifest-digest",
        default="",
        help="预期 immutable Data payload digest（sha256:...）",
    )
    content_readiness_parser.add_argument(
        "--lifecycle-exit-ref",
        default="",
        help="commercial phase 必需的 canonical rollback/replay lifecycle Exit ref",
    )

    app_content_preflight_parser = subparsers.add_parser(
        "app-content-preflight",
        help="在本地 Flutter 安装前验证 active candidate、商业内容回执与 live readback",
    )
    app_content_preflight_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    app_content_preflight_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    app_debug_preflight_parser = subparsers.add_parser(
        "app-debug-preflight",
        help="在 Flutter Debug 启动前只读验证目标 runtime、TLS 与 SMS substitute",
    )
    app_debug_preflight_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    app_debug_preflight_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    provider_debug_parser = subparsers.add_parser(
        "provider-debug",
        help="受保护的 Debug-local Provider 控制面；不会写入 OTP 报告",
    )
    provider_debug_parser.add_argument("action", choices=("otp-read",))
    provider_debug_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    app_content_uat_parser = subparsers.add_parser(
        "app-content-uat",
        help="顺序执行 Alpha/Beta/Gamma release-bound App 内容自动验收",
    )
    app_content_uat_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    app_content_uat_parser.add_argument(
        "--targets",
        default="alpha-local,beta-local,gamma-local",
    )
    app_content_uat_parser.add_argument(
        "--platform",
        choices=("ios-simulator", "android"),
        default="ios-simulator",
    )
    app_content_uat_parser.add_argument("--device-id", required=True)
    app_content_uat_parser.add_argument("--dry-run", action="store_true")

    data_fleet_parser = subparsers.add_parser(
        "data-execution-fleet",
        help="解析或管理 Data ReliableTask 专属的本地 Mongo+Redis fleet。",
    )
    data_fleet_parser.add_argument(
        "--action",
        choices=FLEET_ACTIONS,
        default="resolve",
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
        "--data-verify-run-id",
        required=True,
        help="与案例 import run 配对的 canonical Data verify runId；禁止选择 latest",
    )
    content_uat_parser.add_argument(
        "--acceptance-lease-id",
        required=True,
        help="本次真实设备 UAT 的 create-once acceptance lease id",
    )
    content_uat_parser.add_argument(
        "--platform",
        choices=("android", "ios", "all"),
        default="all",
    )
    content_uat_parser.add_argument("--device-id", action="append", default=[])

    account_enforcement_uat_parser = subparsers.add_parser(
        "account-enforcement-uat",
        help=(
            "在统一 Gamma 环境树中执行 account-enforcement 真机阶段，或聚合 "
            "GWT-003 的 fail-closed CaseResult"
        ),
    )
    account_enforcement_uat_parser.add_argument(
        "--report-dir", default=argparse.SUPPRESS
    )
    account_enforcement_uat_parser.add_argument(
        "--target",
        choices=("gamma-local",),
        default="gamma-local",
    )
    account_enforcement_uat_parser.add_argument(
        "--action",
        choices=("device-suspended", "device-restored", "verify"),
        required=True,
    )
    account_enforcement_uat_parser.add_argument(
        "--manifest",
        default=ACCOUNT_ENFORCEMENT_GAMMA_UAT_MANIFEST,
    )
    account_enforcement_uat_parser.add_argument(
        "--run-id",
        default=os.environ.get("QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RUN_ID", ""),
    )
    account_enforcement_uat_parser.add_argument(
        "--candidate-digest",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST", ""
        ),
    )
    account_enforcement_uat_parser.add_argument(
        "--journey-receipt",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_JOURNEY_RECEIPT", ""
        ),
    )
    account_enforcement_uat_parser.add_argument(
        "--suspended-device-report",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_SUSPENDED_DEVICE_REPORT", ""
        ),
    )
    account_enforcement_uat_parser.add_argument(
        "--restored-device-report",
        default=os.environ.get(
            "QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RESTORED_DEVICE_REPORT", ""
        ),
    )
    account_enforcement_uat_parser.add_argument(
        "--device-id", action="append", default=[]
    )

    filter_catalog_parser = subparsers.add_parser(
        "filter-catalog",
        help="按环境绑定的受信发布身份发布或复核 FilterCatalogRelease",
    )
    filter_catalog_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local", "prod-hosted"),
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

    premium_pool_parser = subparsers.add_parser(
        "premium-pool",
        help="以候选绑定 operator command/event 验证非生产精品池闭环",
    )
    premium_pool_parser.add_argument(
        "--target",
        choices=("alpha-local", "beta-local", "gamma-local"),
        required=True,
    )
    premium_pool_parser.add_argument(
        "--action",
        choices=("upsert-and-verify", "verify-readback"),
        default="upsert-and-verify",
    )
    premium_pool_parser.add_argument("--readiness-receipt", required=True)
    premium_pool_parser.add_argument("--content-id", required=True)
    premium_pool_parser.add_argument("--quality-score", type=float)
    premium_pool_parser.add_argument("--expires-at")
    premium_pool_parser.add_argument(
        "--projection-deadline-seconds",
        type=float,
        default=30.0,
    )
    premium_pool_parser.add_argument("--report-dir", default=argparse.SUPPRESS)

    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument("--report-dir", default=argparse.SUPPRESS)
    repair_parser.add_argument("--target", choices=TARGETS, required=True)
    repair_parser.add_argument(
        "--fix",
        choices=[
            "rebuild-packages",
            "reclaim-build-cache",
            "reclaim-orphaned-processes",
            "restart-stack",
            "reclaim-ports",
            "reconcile-nonprod-data",
        ],
        required=True,
    )
    repair_parser.add_argument(
        "--confirm-orphaned-process-reclaim",
        action="store_true",
        help=(
            "Confirm termination of ledger-less Alpha process groups only after "
            "their target-scoped wrapper and canonical port signatures match."
        ),
    )
    repair_parser.add_argument(
        "--confirm-nonprod-data-reconcile",
        action="store_true",
        help=(
            "Confirm public-API cleanup of stale, expired, or incomplete "
            "receipt-owned Alpha/Beta/Gamma acceptance datasets."
        ),
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
    deploy_parser.add_argument("--service", default="")
    deploy_parser.add_argument(
        "--from-candidate-digest",
        default="",
        help="hosted ledger 当前稳定候选的 sha256 摘要；只用于发布 CAS",
    )
    deploy_parser.add_argument(
        "--to-candidate-digest",
        default="",
        help="ReleaseEvidenceManifest candidateId；只用于发布 CAS",
    )
    deploy_parser.add_argument(
        "--release-evidence-ref",
        default="",
        help="Prod apply/resume 使用的精确 ReleaseEvidenceManifest OCI 引用",
    )
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
        "--promotion-deadline-epoch",
        type=int,
        default=0,
        help="停止 Prod 晋级并切入回滚的绝对 UTC epoch；正式发布必须提供",
    )
    deploy_parser.add_argument(
        "--hard-deadline-epoch",
        type=int,
        default=0,
        help="Prod 发布或回滚必须完成的绝对 UTC epoch；正式发布必须提供",
    )
    deploy_parser.add_argument(
        "--rollback-budget-seconds",
        type=int,
        default=300,
        help="Prod 自动回滚与 ready 恢复的硬预算",
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
        "--host-id",
        action="append",
        default=[],
        help="选择 access-isolation.yaml 中的一个或多个 prod-hosted 主机",
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


class _SloSamplesInsufficient(RuntimeError):
    """A deterministic pause condition, never an automatic rollback signal."""


def _remaining_deadline_seconds(deadline_epoch: int, label: str) -> float:
    remaining = float(deadline_epoch) - time.time()
    if remaining <= 0:
        raise RuntimeError(f"{label} deadline has been reached")
    return remaining


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
    host_id: str = "",
    replica_id: str = "",
) -> dict[str, Any]:
    argv = ["python3", "quwoquan_ops/cli/prod/inspect_prod_plane_runtime.py", "--plane", plane]
    argv.extend(["--instance", instance])
    if host:
        argv.extend(["--host", host])
    if host_id:
        argv.extend(["--host-id", host_id])
    if replica_id:
        argv.extend(["--replica-id", replica_id])
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


def _prod_instance_runtime_reports(
    report_dir: Path,
    *,
    instance: str,
    host: str = "",
    host_id: str = "",
) -> list[dict[str, Any]]:
    plan_argv = [
        "python3",
        "quwoquan_ops/cli/prod/prod_hosted_topology.py",
        "--instance",
        instance,
    ]
    if host:
        plan_argv.extend(["--ssh-host", host])
    if host_id:
        plan_argv.extend(["--host-id", host_id])
    plan_result = run(plan_argv)
    if plan_result.returncode != 0:
        return [
            {
                "error": "deployment plan resolution failed",
                "stdout": plan_result.stdout,
                "stderr": plan_result.stderr,
                "exitCode": plan_result.returncode,
            }
        ]
    try:
        placements = json.loads(plan_result.stdout).get("placements") or []
    except json.JSONDecodeError:
        return [
            {
                "error": "deployment plan output is not valid json",
                "stdout": plan_result.stdout,
                "stderr": plan_result.stderr,
                "exitCode": 2,
            }
        ]
    reports: list[dict[str, Any]] = []
    for placement in placements:
        plane = str(placement.get("plane") or "")
        placement_host_id = str(placement.get("hostId") or "")
        replica_id = str(placement.get("replicaId") or "")
        report_path = (
            report_dir
            / f"prod_rootless_{plane}_{instance}_{placement_host_id}_{replica_id}.json"
        )
        reports.append(
            _prod_plane_runtime_report(
                plane,
                report_path,
                instance=instance,
                host=host,
                host_id=placement_host_id,
                replica_id=replica_id,
            )
        )
    return reports


def _prod_hosted_placement_coverage_checks(
    report_dir: Path,
    *,
    stage: str,
    host: str = "",
    host_id: str = "",
) -> list[dict[str, Any]]:
    """Build one digest-bound postCheck per host/plane/replica placement."""

    try:
        instance = prod_hosted_instance_for_stage(stage)
        plan = resolve_prod_hosted_plan(
            load_prod_hosted_access_manifest(),
            instance=instance,
            host_ids=[host_id] if host_id else None,
            ssh_host_override=host,
        )
    except ProdHostedTopologyError as error:
        return [
            {
                "command": "prod-hosted-placement-coverage",
                "exitCode": 2,
                "summary": f"prod-hosted placement plan resolution failed: {error}",
                "details": [str(error)],
            }
        ]
    runtimes = _prod_instance_runtime_reports(
        report_dir / "placement-coverage",
        instance=instance,
        host=host,
        host_id=host_id,
    )
    runtime_by_key = {
        (
            str(item.get("plane") or ""),
            str(item.get("hostId") or ""),
            str(item.get("replicaId") or ""),
        ): item
        for item in runtimes
        if isinstance(item, dict)
    }
    checks: list[dict[str, Any]] = []
    for placement in plan:
        key = (placement.plane, placement.host_id, placement.replica_id)
        runtime = runtime_by_key.get(key)
        if runtime is None:
            # Fall back to plane-only match for older inspect payloads.
            runtime = next(
                (
                    item
                    for item in runtimes
                    if isinstance(item, dict)
                    and item.get("plane") == placement.plane
                    and (
                        not item.get("hostId")
                        or item.get("hostId") == placement.host_id
                    )
                    and (
                        not item.get("replicaId")
                        or item.get("replicaId") == placement.replica_id
                    )
                ),
                None,
            )
        findings = (
            _prod_plane_runtime_findings(runtime, plane=placement.plane)
            if isinstance(runtime, dict)
            else [f"missing runtime inspect for {placement.plane}/{placement.replica_id}"]
        )
        if runtime is None:
            findings = [
                f"missing runtime inspect for {placement.plane}/{placement.replica_id}"
            ]
        receipt = {
            "schema": "prod-hosted-placement-receipt",
            "target": "prod-hosted",
            "stage": stage,
            "instance": placement.instance,
            "plane": placement.plane,
            "hostId": placement.host_id,
            "replicaId": placement.replica_id,
            "sshHost": placement.ssh_host,
            "remoteRoot": placement.remote_root,
            "project": placement.project,
            "systemdUnit": placement.systemd_unit,
            "findings": findings,
            "runtime": runtime or {},
        }
        receipt_path = (
            report_dir
            / "placement-receipts"
            / f"{placement.host_id}_{placement.plane}_{placement.replica_id}.json"
        )
        write_json(receipt_path, receipt)
        checks.append(
            {
                "command": "prod-hosted-placement-coverage",
                "name": prod_hosted_placement_check_name(placement),
                "exitCode": 0 if not findings else 1,
                "summary": (
                    f"placement {placement.host_id}/{placement.plane}/{placement.replica_id} ready"
                    if not findings
                    else f"placement {placement.host_id}/{placement.plane}/{placement.replica_id} blocked"
                ),
                "details": findings,
                "placementReceiptPath": relpath(receipt_path),
                "placementReceipt": receipt,
            }
        )
    coverage_issues = validate_prod_hosted_host_coverage(
        [
            {
                "name": item["name"],
                "status": "passed" if item["exitCode"] == 0 else "failed",
                "receiptDigest": "sha256:" + ("0" * 64),
            }
            for item in checks
            if item.get("name")
        ],
        plan,
    )
    if coverage_issues:
        checks.append(
            {
                "command": "prod-hosted-placement-coverage",
                "exitCode": 2,
                "summary": "prod-hosted host coverage aggregate CAS blocked",
                "details": coverage_issues,
            }
        )
    return checks


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
    state_name = "content-release.json" if target == "alpha-local" else "local_run.json"
    state_path = target_process_dir(target) / state_name
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
        and set(parsed)
        == {
            "schema",
            "evidenceCount",
            "executableSourceCount",
            "sourceCoverageIssues",
            "readiness",
            "issues",
        }
        and parsed.get("schema") == "provider-conformance-readiness"
        and isinstance(issues, list)
        and all(isinstance(issue, str) for issue in issues)
        and isinstance(parsed.get("sourceCoverageIssues"), list)
        and all(
            isinstance(issue, str) for issue in parsed["sourceCoverageIssues"]
        )
        and isinstance(parsed.get("executableSourceCount"), int)
        and parsed["executableSourceCount"] >= 0
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
        and parsed is not None
        and parsed["evidenceCount"] > 0
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
        result = run(
            command,
            # Provider readiness is environment-scoped. Neutralize any shell
            # target instead of incorrectly selecting one of prod's targets.
            env=_verify_child_environment(""),
        )
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


def _verify_child_environment(
    target_name: str,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Bind every verify child to its selected target, never the parent shell."""

    environment = dict(extra or {})
    if target_name in TARGETS:
        target = get_target(load_environment_topology(), target_name)
        runtime_environment = str(target.get("env") or "").strip()
        environment["QWQ_DEPLOY_TARGET"] = target_name
        environment["QWQ_APP_RUNTIME_ENV"] = runtime_environment
    else:
        environment["QWQ_DEPLOY_TARGET"] = ""
        environment["QWQ_APP_RUNTIME_ENV"] = ""
    return environment


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


def _selected_profile_commands(
    env_name: str,
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None = None,
    service: str = "",
    data_readiness_path: Path | None = None,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    if profile.requires_environment and target_name in {
        "alpha-local",
        "beta-local",
        "gamma-local",
        "prod-sim",
    }:
        # verify is read-only with respect to package/build/deployment selection.
        # A missing or unhealthy runtime must block instead of triggering nested up.
        # Follow the active workload health scope: content-release must not be
        # forced through full commercial service probes.
        health_scope = _current_runtime_health_scope(target_name)
        commands.append(
            {
                "name": f"{target_name}-health-preflight",
                "argv": [
                    "python3",
                    "quwoquan_ops/cli/stackctl.py",
                    "--output-format",
                    "json",
                    "health",
                    "--target",
                    target_name,
                    "--scope",
                    health_scope,
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
        and _current_runtime_health_scope(target_name)
        not in {"content-consumer", "content-commercial"}
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
        and _current_runtime_health_scope(target_name)
        not in {"content-consumer", "content-commercial"}
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
        data_readiness_path=data_readiness_path,
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
            data_readiness_path=data_readiness_path,
        )
        if media_preflight_command is not None:
            commands.append(media_preflight_command)
        smoke_command = _environment_page_smoke_profile_command(
            env_name,
            target_name,
            report_dir,
            data_readiness_path=data_readiness_path,
        )
        if smoke_command is not None:
            commands.append(smoke_command)
        if env_name in {"beta", "gamma"} and target_name in {
            "beta-local",
            "gamma-local",
        }:
            runtime_recovery_command = _environment_page_smoke_profile_command(
                env_name,
                target_name,
                report_dir,
                suite_name="runtime-recovery-patrol",
                patrol_target=RUNTIME_RECOVERY_UAT_TEST_TARGET,
                persisted_device_session=True,
            )
            if runtime_recovery_command is not None:
                commands.append(runtime_recovery_command)
        if env_name == "gamma" and target_name == "gamma-local":
            account_enforcement_command = (
                _account_enforcement_gamma_uat_profile_command(
                    target_name,
                    profile,
                    report_dir,
                )
            )
            if account_enforcement_command is not None:
                commands.append(account_enforcement_command)
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
    *,
    data_readiness_path: Path | None = None,
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
            "DATA_RELEASE_READINESS_RECEIPT": (
                str(data_readiness_path) if data_readiness_path is not None else ""
            ),
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
    *,
    data_readiness_path: Path | None = None,
) -> dict[str, Any] | None:
    """在设备 Patrol 之前验证 canonical media 的 Range/MIME。"""

    if target_name not in {
        "alpha-local",
        "beta-local",
        "gamma-local",
        "prod-sim",
        "prod-hosted",
    }:
        return None
    health_report_path = (
        report_dir / "video-range-mime-preflight" / "report.json"
        if report_dir is not None
        else env_runs_root(
            str(get_target(load_environment_topology(), target_name)["env"]),
        )
        / "device-matrix"
        / "video-range-mime-preflight"
        / target_name
        / "report.json"
    )
    return {
        "name": f"{target_name}-release-video-canary-preflight",
        "argv": [
            "python3",
            "quwoquan_ops/cli/smoke/verify_video_playback_canary.py",
            "--target",
            target_name,
            "--release-readiness",
            str(data_readiness_path) if data_readiness_path is not None else "",
            "--report",
            str(health_report_path),
        ],
        "stopOnFailure": True,
        "reportPath": relpath(health_report_path),
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


def _profile_step(steps: list[dict[str, Any]], name_fragment: str) -> dict[str, Any]:
    for step in steps:
        if name_fragment in str(step.get("name") or ""):
            return step
    return {}


def _release_video_preflight_from_steps(
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Load the one typed release canary report from this T4 execution."""

    step = _profile_step(steps, "release-video-canary-preflight")
    report = _read_json_object(str(step.get("reportPath") or ""))
    if not report:
        try:
            parsed_stdout = json.loads(str(step.get("stdout") or ""))
        except json.JSONDecodeError:
            parsed_stdout = {}
        report = parsed_stdout if isinstance(parsed_stdout, dict) else {}
    if report:
        report["_reportPath"] = str(step.get("reportPath") or "")
        return report
    return {}


def _video_range_evidence_from_preflight(
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project Range/MIME only from the typed release canary report."""

    report = _release_video_preflight_from_steps(steps)
    delivery = report.get("delivery") if isinstance(report, dict) else None
    delivery = delivery if isinstance(delivery, dict) else {}
    return {
        "statusCode": delivery.get("rangeStatus"),
        "mimeType": delivery.get("mimeType"),
        "reportPath": str(report.get("_reportPath") or ""),
    }


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
        "iosPerformanceTracePath": os.environ.get(
            "VIDEO_PLAYBACK_IOS_PERFORMANCE_TRACE_PATH",
            "",
        ).strip(),
        "iosPerformanceSummaryPath": os.environ.get(
            "VIDEO_PLAYBACK_IOS_PERFORMANCE_SUMMARY_PATH",
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
    preflight = _release_video_preflight_from_steps(steps)
    release_identity = (
        dict(preflight.get("release"))
        if isinstance(preflight.get("release"), dict)
        else {}
    )
    video_identity = (
        dict(preflight.get("video"))
        if isinstance(preflight.get("video"), dict)
        else {}
    )
    service_evidence = {
        "videoRange": _video_range_evidence_from_preflight(steps),
    }
    ui_evidence = _video_ui_evidence_from_smoke(steps)
    media_identity = {
        "assetId": str(video_identity.get("assetId") or ""),
        "assetVersion": video_identity.get("assetVersion"),
        "probeHash": str(video_identity.get("expectedHash") or ""),
    }
    public_slice_key = str(video_identity.get("publicSliceKey") or "")
    post_id = str(video_identity.get("postId") or "")
    video_range = service_evidence["videoRange"]
    dry_run = os.environ.get("STACKCTL_PAGE_SMOKE_DRY_RUN", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    is_passed = (
        bool(public_slice_key)
        and bool(post_id)
        and preflight.get("schema")
        == "quwoquan_ops.release_video_delivery_evidence"
        and preflight.get("status") == "passed"
        and preflight.get("target") == target_name
        and release_identity.get("sourceOwner") == "qwq_data"
        and bool(release_identity.get("releaseId"))
        and bool(release_identity.get("importRunId"))
        and bool(release_identity.get("verifyRunId"))
        and bool(release_identity.get("readinessReceiptRef"))
        and _DATA_READINESS_DIGEST_RE.fullmatch(
            str(release_identity.get("manifestDigest") or "")
        )
        is not None
        and _DATA_READINESS_DIGEST_RE.fullmatch(
            str(release_identity.get("mediaManifestDigest") or "")
        )
        is not None
        and bool(media_identity.get("assetId"))
        and isinstance(media_identity.get("assetVersion"), int)
        and not isinstance(media_identity.get("assetVersion"), bool)
        and media_identity["assetVersion"] > 0
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
        and bool(ui_evidence["iosPerformanceTracePath"])
        and bool(ui_evidence["iosPerformanceSummaryPath"])
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
        "release": release_identity,
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


def _environment_page_smoke_profile_command(
    env_name: str,
    target_name: str,
    report_dir: Path | None,
    *,
    suite_name: str = "environment-page-smoke",
    patrol_target: str = VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
    remote_api_evidence_report: Path | None = None,
    data_readiness_path: Path | None = None,
    persisted_device_session: bool = False,
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
    if data_readiness_path is not None:
        try:
            release_binding = load_release_video_binding(
                data_readiness_path,
                expected_environment=runtime_env,
            )
        except ReleaseVideoDeliveryError:
            # The preceding release-video-canary preflight owns the typed
            # GATE_BLOCK. Never fall back to an environment identity here.
            video_playback_canary_work_id = ""
        else:
            video_playback_canary_work_id = str(release_binding["workId"])
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
    if persisted_device_session:
        if patrol_target != RUNTIME_RECOVERY_UAT_TEST_TARGET:
            raise ValueError(
                "persisted device session is only valid for runtime recovery UAT"
            )
        argv.append("--persisted-device-session")
    platform = os.environ.get("STACKCTL_PAGE_SMOKE_PLATFORM", "").strip()
    if platform:
        argv.extend(["--platform", platform])
    device_id = os.environ.get("STACKCTL_PAGE_SMOKE_DEVICE_ID", "").strip()
    if device_id:
        argv.extend(["--device-id", device_id])
    if os.environ.get("STACKCTL_PAGE_SMOKE_DRY_RUN", "").strip() in {"1", "true", "yes"}:
        argv.append("--dry-run")
    command_env: dict[str, str] = {}
    if target_name != "gamma-local" and not persisted_device_session:
        if token:
            command_env["TEST_AUTH_TOKEN"] = token
        for key in (
            "TEST_REFRESH_TOKEN",
            "APP_CURRENT_OWNER_ID",
            "APP_CURRENT_PERSONA_ID",
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


def _account_enforcement_gamma_uat_profile_command(
    target_name: str,
    profile: VerificationProfile,
    report_dir: Path | None,
) -> dict[str, Any] | None:
    """Bind the immutable GWT-003 CaseResult to Gamma release verification."""

    if (
        target_name != "gamma-local"
        or profile is not VerificationProfile.RELEASE
    ):
        return None
    evidence_root = (
        report_dir / "account-enforcement-gamma-uat"
        if report_dir is not None
        else env_runs_root("gamma")
        / "account-enforcement-gamma-uat"
        / target_name
    )
    report_path = evidence_root / "case-result.json"
    return {
        "name": "gamma-local-account-enforcement-uat",
        "argv": [
            "python3",
            ACCOUNT_ENFORCEMENT_GAMMA_UAT_VALIDATOR,
            "--manifest",
            ACCOUNT_ENFORCEMENT_GAMMA_UAT_MANIFEST,
            "--report",
            str(report_path),
        ],
        "cwd": ROOT,
        "stopOnFailure": True,
        "reportPath": relpath(report_path),
    }


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
    ca_file: str = "",
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
            parsed = urllib.parse.urlsplit(url)
            local_target = target_for_hostname(parsed.hostname or "")
            if parsed.scheme == "https" and local_target is not None:
                return _fetch_local_managed_url(
                    parsed,
                    local_target,
                    timeout=timeout,
                    headers=headers,
                )
            request = urllib.request.Request(url, headers=headers or {})
            context = (
                ssl.create_default_context(cafile=ca_file)
                if parsed.scheme == "https" and ca_file
                else None
            )
            response = urllib.request.urlopen(
                request,
                timeout=timeout,
                context=context,
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


class _CanonicalLocalHTTPSConnection(http.client.HTTPSConnection):
    """Connect to loopback while preserving canonical Host and TLS SNI."""

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (LOOPBACK_ADDRESS, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()
        server_hostname = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=server_hostname,
        )


def _fetch_local_managed_url(
    parsed: urllib.parse.SplitResult,
    target: str,
    *,
    timeout: float,
    headers: dict[str, str] | None,
) -> tuple[bool, int | None, str, str]:
    from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

    root = root_certificate_path(target)
    context = ssl.create_default_context(cafile=str(root))
    connection = _CanonicalLocalHTTPSConnection(
        parsed.hostname or "",
        port=parsed.port or 443,
        timeout=timeout,
        context=context,
    )
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    try:
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        content_type = str(response.headers.get("Content-Type") or "")
        status = int(response.status)
        return status < 400, status, body[:500], content_type
    finally:
        connection.close()


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
    timeout_seconds: float | None = None,
) -> tuple[dict[str, Any], str, list[str]]:
    result = run(argv, env=env, timeout_seconds=timeout_seconds)
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
    *,
    require_non_empty_content_feed: bool = False,
    release_post_expectations: dict[str, set[str]] | None = None,
    release_readiness_path: Path | None = None,
    only_checks: tuple[str, ...] = (),
    probe_name: str = "integration-readonly",
    timeout_seconds: float | None = None,
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
    if require_non_empty_content_feed:
        argv.append("--require-non-empty-content-feed")
    for check_name in only_checks:
        argv.extend(["--only-check", check_name])
    expectation_flags = {
        "content_feed": "--expected-discovery-post-id",
        "video_book_feed": "--expected-video-post-id",
        "premium_feed": "--expected-premium-video-post-id",
    }
    for check_name, post_ids in (release_post_expectations or {}).items():
        flag = expectation_flags.get(check_name)
        if flag is None:
            raise ValueError(f"unsupported release feed expectation: {check_name}")
        for post_id in sorted(post_ids):
            argv.extend([flag, post_id])
    if target_name == "prod-hosted":
        request_timeout = 20
        retry_attempts = 3
        retry_sleep_seconds = 3
        if timeout_seconds is not None:
            request_timeout = max(1, min(request_timeout, int(timeout_seconds)))
            retry_attempts = 1
            retry_sleep_seconds = 0
        argv.extend(
            [
                "--mode",
                "post-deploy",
                "--request-timeout-seconds",
                str(request_timeout),
                "--retry-attempts",
                str(retry_attempts),
                "--retry-sleep-seconds",
                str(retry_sleep_seconds),
            ]
        )
    product_ops = str(public_bases.get("productOps") or "").strip()
    if product_ops:
        argv.extend(["--product-ops-base-url", product_ops])
    media_image = str(public_bases.get("mediaImage") or "").strip()
    if media_image and release_readiness_path is not None:
        argv.extend(
            [
                "--media-image-base-url",
                media_image,
                "--release-readiness",
                str(release_readiness_path),
            ]
        )
    token = _resolve_test_auth_token(env_name)
    public_release_checks = {
        "content_feed",
        "video_book_feed",
        "premium_feed",
        "media_sample",
    }
    requires_reference_identity = not only_checks or any(
        check_name not in public_release_checks for check_name in only_checks
    )
    if env_name in {"beta", "gamma"} and not token and requires_reference_identity:
        # Self-signed local edge requires the managed CA before OTP/login;
        # probe_env SSL_CERT_FILE only covers the child probe process.
        # Use try/finally (not @contextmanager): LocalEnvironmentHTTPError is a
        # frozen dataclass and contextlib.throw cannot attach __traceback__.
        previous_ssl_cert_file = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = str(root_certificate_path(target_name))
        try:
            token = open_reference_acceptance_session(
                str(public_bases["api"]),
                environment=env_name,
                target_name=target_name,
            ).access_token
        except (OSError, RuntimeError, ValueError) as exc:
            finding = f"{target_name} integration auth failed: {exc}"
            return (
                {
                    "name": probe_name,
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
        finally:
            if previous_ssl_cert_file is None:
                os.environ.pop("SSL_CERT_FILE", None)
            else:
                os.environ["SSL_CERT_FILE"] = previous_ssl_cert_file
    probe_env: dict[str, str] = {}
    if target_name in {"alpha-local", "beta-local", "gamma-local"}:
        probe_env["SSL_CERT_FILE"] = str(root_certificate_path(target_name))
    if token:
        probe_env["TEST_AUTH_TOKEN"] = token
        if env_name == "gamma":
            probe_env["GAMMA_TEST_AUTH_TOKEN"] = token
        elif env_name == "beta":
            probe_env["BETA_TEST_AUTH_TOKEN"] = token
        elif env_name == "prod":
            probe_env["PROD_TEST_AUTH_TOKEN"] = token
    return _run_script_probe(
        name=probe_name,
        scope="full",
        argv=argv,
        report_file=report_file,
        env=probe_env or None,
        timeout_seconds=timeout_seconds,
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
    *,
    require_non_empty_content_feed: bool = False,
    deadline_epoch: int = 0,
) -> tuple[list[dict[str, Any]], list[tuple[str, str]], list[str]]:
    if scope != "full" and not require_non_empty_content_feed:
        return [], [], []
    statuses: list[dict[str, Any]] = []
    stdout_sections: list[tuple[str, str]] = []
    findings: list[str] = []

    if target_name in {"alpha-local", "beta-local", "gamma-local", "prod-sim", "prod-hosted"}:
        probe_timeout = (
            _remaining_deadline_seconds(deadline_epoch, "health verification")
            if deadline_epoch > 0
            else None
        )
        # content-consumer / content-release must not require search or other
        # full-stack commercial probes; those belong to scope=full only.
        only_checks: tuple[str, ...] = ()
        if require_non_empty_content_feed and scope != "full":
            only_checks = (
                "content_feed",
                "video_book_feed",
            )
        status, output, probe_findings = _run_environment_integration_probe(
            topology,
            target_name,
            report_dir,
            require_non_empty_content_feed=require_non_empty_content_feed,
            only_checks=only_checks,
            timeout_seconds=probe_timeout,
        )
        if require_non_empty_content_feed and scope != "full":
            status["scope"] = scope
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
    from_candidate_digest: str,
    to_candidate_digest: str,
    stage: str,
) -> tuple[str, int]:
    if not state:
        if stage != "gray-initial":
            raise RuntimeError("release ledger must start at gray-initial")
        return "advance", 0

    generation = int(state.get("generation") or 0)
    current_stage = _release_stage_from_state(state)
    same_target = (
        state.get("from_candidate_digest") == from_candidate_digest
        and state.get("to_candidate_digest") == to_candidate_digest
    )
    if same_target:
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
    if state.get("to_candidate_digest") != from_candidate_digest:
        raise RuntimeError(
            "release ledger base CAS conflict: requested source candidate does not "
            "match the current stable candidate"
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


@contextlib.contextmanager
def _target_package_lock(target_name: str) -> Any:
    """Serialize package materialization per target without blocking other envs."""
    target = str(target_name).strip()
    if target not in TARGETS:
        raise ValueError(f"package lock does not support {target!r}")
    lock_path = deployment_target_path(target, "locks", "package.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} target={target} startedAt={utc_now()}\n")
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


def _archive_release_artifact(manifest_path: Path, artifact_digest: str) -> Path:
    archive_root = _release_state_dir() / "artifacts"
    archive_root.mkdir(parents=True, exist_ok=True)
    digest_id = artifact_digest.removeprefix("sha256:")
    if re.fullmatch(r"[0-9a-f]{64}", digest_id) is None:
        raise RuntimeError("release artifact digest is invalid")
    target = archive_root / digest_id
    source = manifest_path.parent
    if target.exists():
        archived_manifest = target / "manifest.json"
        if not archived_manifest.is_file():
            raise RuntimeError(f"release artifact archive is incomplete: {target}")
        archived = json.loads(archived_manifest.read_text(encoding="utf-8"))
        declared = str(archived.get("artifactDigest") or "") if isinstance(archived, dict) else ""
        if declared != artifact_digest:
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
    deadline_epoch: int = 0,
) -> tuple[dict[str, str], Path | None]:
    """Fetch a digest-verified state/receipt pair from the hosted authority."""
    readback = _run_hosted_release_ledger(
        service=service,
        action="fetch",
        deadline_epoch=deadline_epoch,
    )
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
    *,
    deadline_epoch: int = 0,
) -> Path:
    """Read back an already committed hosted receipt; never publish local state."""
    hosted_state, hosted_receipt_path = _fetch_hosted_release_ledger_projection(
        service,
        allow_uninitialized=False,
        deadline_epoch=deadline_epoch,
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
    if (
        set(state) != hosted_release_ledger.STATE_FIELDS
        or set(receipt) != hosted_release_ledger.RECEIPT_FIELDS
    ):
        raise RuntimeError(
            "hosted release ledger state or receipt shape is not canonical"
        )
    receipt_id = str(receipt.get("receiptId") or "")
    for field in hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.values():
        history_receipt_id = state.get(field)
        if not isinstance(history_receipt_id, str) or (
            history_receipt_id
            and hosted_release_ledger.RECEIPT_ID_RE.fullmatch(history_receipt_id)
            is None
        ):
            raise RuntimeError(
                "hosted release ledger stage receipt history is invalid"
            )
    active_history_field = hosted_release_ledger.STAGE_RECEIPT_ID_FIELDS.get(
        state.get("trigger_stage", "")
    )
    if (
        active_history_field is None
        or state.get(active_history_field) != receipt_id
    ):
        raise RuntimeError(
            "hosted release ledger current receipt is not trigger-stage bound"
        )
    if (
        state.get("schema") != hosted_release_ledger.STATE_SCHEMA
        or state.get("authority") != hosted_release_ledger.AUTHORITY
        or state.get("service") != service
        or receipt.get("schema") != hosted_release_ledger.RECEIPT_SCHEMA
        or receipt.get("authority") != hosted_release_ledger.AUTHORITY
        or receipt.get("service") != service
        or re.fullmatch(r"[0-9a-f]{64}", receipt_id) is None
        or receipt_id != _hosted_receipt_id(receipt)
        or state.get("receipt_id") != receipt_id
        or payload.get("receiptRef") != f"receipt:hosted:{receipt_id}"
        or str(receipt.get("committedGeneration")) != state.get("generation")
        or receipt.get("artifactDigest") != state.get("artifact_digest")
        or receipt.get("fromCandidateDigest")
        != state.get("from_candidate_digest")
        or receipt.get("toCandidateDigest") != state.get("to_candidate_digest")
        or receipt.get("step") != state.get("step")
        or receipt.get("stage") != state.get("stage")
        or receipt.get("decision") != state.get("decision")
        or receipt.get("imageDigest") != state.get("image_digest")
        or receipt.get("configDigest") != state.get("config_digest")
        or receipt.get("contractGraphDigest") != state.get("contract_graph_digest")
        or receipt.get("adapterDigest") != state.get("adapter_digest")
        or receipt.get("rollbackOutcome") != state.get("rollback_outcome")
        or receipt.get("triggerStage") != state.get("trigger_stage")
        or receipt.get("fromReleaseEvidenceRef")
        != state.get("from_release_evidence_ref")
        or receipt.get("toReleaseEvidenceRef")
        != state.get("to_release_evidence_ref")
        or receipt.get("fromImageTransportTag")
        != state.get("from_image_transport_tag")
        or receipt.get("toImageTransportTag")
        != state.get("to_image_transport_tag")
        or receipt.get("lastGoodCandidateDigest")
        != state.get("last_good_candidate_digest")
        or receipt.get("verifiedAt") != state.get("updated_at")
    ):
        raise RuntimeError("hosted release ledger receipt digest or state binding is invalid")
    return payload


def _run_hosted_release_ledger(
    *,
    service: str,
    action: str,
    request: dict[str, Any] | None = None,
    receipt_id: str = "",
    deadline_epoch: int = 0,
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
        timeout_seconds = (
            _remaining_deadline_seconds(
                deadline_epoch,
                "hosted release ledger authority I/O",
            )
            if deadline_epoch > 0
            else None
        )
        result = run(command, timeout_seconds=timeout_seconds)
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
    receipt_id = str(receipt.get("receiptId") or "")
    validated = _validate_hosted_release_readback(
        {
            "schema": hosted_release_ledger.READBACK_SCHEMA,
            "authority": hosted_release_ledger.AUTHORITY,
            "state": state,
            "receipt": receipt,
            "receiptRef": f"receipt:hosted:{receipt_id}",
        },
        service=service,
    )
    state = dict(validated["state"])
    receipt = dict(validated["receipt"])
    cache_dir = _release_state_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_path = cache_dir / f"{service}.state"
    state_path.write_text(
        "\n".join(f"{key}={value}" for key, value in state.items()) + "\n",
        encoding="utf-8",
    )
    receipt_path = cache_dir / "receipts" / f"{receipt_id}.json"
    write_json(receipt_path, receipt)
    return state, receipt_path


def _check_exit_passed(item: dict[str, Any]) -> bool:
    exit_code = item.get("exitCode")
    return (
        isinstance(exit_code, int)
        and not isinstance(exit_code, bool)
        and exit_code == 0
    )


def _release_check_receipts(
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for index, item in enumerate(checks, start=1):
        explicit_name = str(item.get("name") or "").strip()
        if explicit_name.startswith("host:") and hosted_release_ledger.SAFE_VALUE_RE.fullmatch(
            explicit_name
        ):
            name = explicit_name
        else:
            name = f"post-check-{index}"
        receipts.append(
            {
                "name": name,
                "status": "passed" if _check_exit_passed(item) else "failed",
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
        )
    return receipts


def _commit_hosted_release_transition(
    *,
    service: str,
    from_candidate_digest: str,
    to_candidate_digest: str,
    step: str,
    stage: str,
    decision: str,
    artifact_digest: str,
    expected_generation: int,
    receipt_id: str,
    slo_readback: dict[str, Any] | None,
    candidate_digests: dict[str, str],
    last_good_candidate_digest: str,
    post_deploy_checks: list[dict[str, Any]],
    rollback_outcome: str,
    rollback_evidence: dict[str, Any],
    from_release_evidence_ref: str,
    to_release_evidence_ref: str,
    from_image_transport_tag: str,
    to_image_transport_tag: str,
    deadline_epoch: int = 0,
    trigger_stage: str = "",
) -> tuple[dict[str, str], Path]:
    del receipt_id
    request = {
        "schema": "prod-hosted-release-transition-request",
        "service": service,
        "fromCandidateDigest": from_candidate_digest,
        "toCandidateDigest": to_candidate_digest,
        "step": step,
        "stage": stage,
        "triggerStage": trigger_stage or stage,
        "fromReleaseEvidenceRef": from_release_evidence_ref,
        "toReleaseEvidenceRef": to_release_evidence_ref,
        "fromImageTransportTag": from_image_transport_tag,
        "toImageTransportTag": to_image_transport_tag,
        "decision": decision,
        "rollbackOutcome": rollback_outcome,
        "rollbackEvidence": rollback_evidence,
        "artifactDigest": artifact_digest,
        "imageDigest": candidate_digests["imageDigest"],
        "configDigest": candidate_digests["configDigest"],
        "contractGraphDigest": candidate_digests["contractGraphDigest"],
        "adapterDigest": candidate_digests["adapterDigest"],
        "expectedGeneration": expected_generation,
        "sloReadback": slo_readback or {},
        "postChecks": _release_check_receipts(post_deploy_checks),
        "lastGoodCandidateDigest": last_good_candidate_digest,
        "verifiedAt": utc_now(),
    }
    committed = _run_hosted_release_ledger(
        service=service,
        action="commit",
        request=request,
        deadline_epoch=deadline_epoch,
    )
    # The hosted commit action fsyncs state/receipt and returns its own validated
    # readback. A second network fetch adds no authority and extends the Prod path.
    return _cache_hosted_release_readback(
        service,
        committed["state"],
        committed["receipt"],
    )


def socket_probe(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait_for_network_ports_released(
    target_name: str,
    *,
    timeout_seconds: float = 45.0,
    poll_interval_seconds: float = 0.5,
) -> list[dict[str, Any]]:
    """Wait for target-owned host forwards to converge after compose down.

    Docker Desktop/Colima can remove containers before its host forwarding
    process closes the corresponding listening sockets. A single immediate
    probe therefore creates a false cleanup failure. The bounded wait keeps
    the fail-closed resource-release contract without restarting or otherwise
    mutating the shared container runtime.
    """

    deadline = time.monotonic() + timeout_seconds
    while True:
        occupied = [
            item for item in _network_report(target_name)["ports"] if item["open"]
        ]
        if not occupied or time.monotonic() >= deadline:
            return occupied
        time.sleep(poll_interval_seconds)


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
    package_root = portal_deployment_package_dir(env_name, target=target_name)
    current_package = package_root / "current"
    package_dir = current_package.resolve()
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
                portal_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                package_digest = str(portal_manifest.get("packageDigest") or "")
                if (
                    not re.fullmatch(r"sha256:[0-9a-f]{64}", package_digest)
                    or package_dir.name != package_digest.removeprefix("sha256:")
                ):
                    result = subprocess.CompletedProcess(
                        command,
                        1,
                        stdout=result.stdout,
                        stderr="ops-portal builder produced invalid packageDigest identity",
                    )
                    package_digest = ""
                provenance = {
                    "schema": "qwq.ops_portal_package",
                    "packageKind": "ops-portal",
                    "environment": env_name,
                    "target": target_name,
                    "packageDigest": package_digest,
                    "gitRevision": revision,
                    "digests": {
                        "manifest": _sha256_file(manifest_path),
                        "distTree": _sha256_tree(dist_dir),
                    },
                }
                if result.returncode == 0:
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
    """Seal the canonical release evidence into the existing service manifest."""
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
        "providerEvidence": str(
            getattr(args, "provider_evidence", "") or ""
        ).strip(),
        "testEvidence": str(getattr(args, "test_evidence", "") or "").strip(),
    }
    application_packages_dir_value = str(
        getattr(args, "application_packages_dir", "") or ""
    ).strip()
    application_package_payloads_dir_value = str(
        getattr(args, "application_package_payloads_dir", "") or ""
    ).strip()
    application_evidence_ref = str(
        getattr(args, "application_evidence_ref", "") or ""
    ).strip()
    provider_raw_dir_value = str(
        getattr(args, "provider_raw_dir", "") or ""
    ).strip()
    if not artifact_dir_value:
        issues.append("release-manifest assembly requires --release-artifact-dir")
    if not application_packages_dir_value:
        issues.append("release-manifest assembly requires --application-packages-dir")
    if not application_package_payloads_dir_value:
        issues.append(
            "release-manifest assembly requires --application-package-payloads-dir"
        )
    if not application_evidence_ref:
        issues.append("release-manifest assembly requires --application-evidence-ref")
    if not provider_raw_dir_value:
        issues.append("release-manifest assembly requires --provider-raw-dir")
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
                application_package_sources=(
                    collect_release_artifact_descriptors.load_application_package_sources(
                        Path(application_packages_dir_value).expanduser().resolve()
                    )
                ),
                application_package_payloads=(
                    collect_release_artifact_descriptors.load_application_package_payloads(
                        Path(application_package_payloads_dir_value)
                        .expanduser()
                        .resolve()
                    )
                ),
                application_evidence_ref=application_evidence_ref,
                provider_raw_dir=Path(provider_raw_dir_value).expanduser().resolve(),
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
        f"candidateId={manifest.get('candidateId')}",
        f"artifactDigest={manifest.get('artifactDigest')}",
        "evidence="
        + ",".join(
            sorted(finalize_mainline_release_artifact.REQUIRED_RELEASE_EVIDENCE)
        ),
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
            "candidateId": manifest.get("candidateId"),
            "artifactDigest": manifest.get("artifactDigest"),
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


def _run_runtime_compile_preflight(
    *,
    package_environment: dict[str, str],
) -> tuple[list[dict[str, Any]], str]:
    """Compile every runtime entrypoint before any package/image materialization."""

    checks = [
        (
            "compile-entrypoints:go",
            [
                "go",
                "test",
                "-run",
                "^$",
                "./services/.../cmd/...",
                "./control-plane/.../cmd/...",
            ],
            ROOT / "quwoquan_service",
        ),
        (
            "compile-entrypoints:recommendation-python",
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "import ast,pathlib;"
                    "root=pathlib.Path('services/recommendation-service');"
                    "files=sorted(root.rglob('*.py'));"
                    "assert files, 'recommendation Python source set is empty';"
                    "[(ast.parse(path.read_text(encoding='utf-8'), filename=str(path))) "
                    "for path in files]"
                ),
            ],
            ROOT / "quwoquan_service",
        ),
    ]
    reports: list[dict[str, Any]] = []
    for name, argv, cwd in checks:
        result = run(argv, cwd=cwd, env=package_environment)
        reports.append(
            {
                "name": name,
                "argv": argv,
                "exitCode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode != 0:
            return (
                reports,
                result.stderr.strip()
                or result.stdout.strip()
                or f"{name} failed",
            )
    return reports, ""


def command_package(args: argparse.Namespace) -> dict[str, Any]:
    package_kind = str(getattr(args, "kind", "runtime") or "runtime")
    if package_kind != "runtime":
        if package_kind == "release-manifest":
            return _command_package_unlocked(args, package_snapshot=None)
        env_name = str(getattr(args, "env", "") or "").strip()
        target_name = str(getattr(args, "target", "") or "").strip()
        if not target_name and env_name in DEFAULT_TARGET_BY_ENV:
            target_name = DEFAULT_TARGET_BY_ENV[env_name]
        previous_override = os.environ.get(PACKAGE_ROOT_OVERRIDE_ENV)
        isolated_root = deployment_target_path(
            target_name,
            "standalone-packages",
            package_kind,
            "packages",
        )
        os.environ[PACKAGE_ROOT_OVERRIDE_ENV] = str(isolated_root)
        try:
            return _command_package_unlocked(args, package_snapshot=None)
        finally:
            if previous_override is None:
                os.environ.pop(PACKAGE_ROOT_OVERRIDE_ENV, None)
            else:
                os.environ[PACKAGE_ROOT_OVERRIDE_ENV] = previous_override
    env_name = str(getattr(args, "env", "") or "").strip()
    target_name = str(getattr(args, "target", "") or "").strip()
    if not target_name and env_name in DEFAULT_TARGET_BY_ENV:
        target_name = DEFAULT_TARGET_BY_ENV[env_name]
    if not target_name:
        return _command_package_unlocked(args)
    if str(getattr(args, "service", "") or "").strip():
        return {
            "exitCode": 2,
            "summary": f"stackctl runtime package blocked for {env_name}",
            "details": [
                "runtime candidates are full-only; --service cannot create or activate a runtime candidate"
            ],
        }
    args.include_services = True
    try:
        requested_release_bindings = validate_release_attestations(
            str(getattr(args, "release_attestation", "") or ""),
            str(getattr(args, "rollback_release_attestation", "") or ""),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        return {
            "exitCode": 2,
            "summary": f"stackctl runtime package inputs blocked for {env_name}",
            "details": [str(exc)],
        }
    with _target_package_lock(target_name):
        package_snapshot = (
            workspace_snapshot()
            if getattr(args, "kind", "runtime") == "runtime"
            else None
        )
        if package_snapshot is None:
            return _command_package_unlocked(args, package_snapshot=None)

        baseline_id = str(package_snapshot["baselineId"])
        candidate_dir = deployment_candidate_dir(target_name, baseline_id)
        previous_override = os.environ.get(PACKAGE_ROOT_OVERRIDE_ENV)
        if candidate_dir.exists():
            os.environ[PACKAGE_ROOT_OVERRIDE_ENV] = str(candidate_dir / "packages")
            try:
                reusable, detail = can_reuse_package(
                    env_name,
                    target_name,
                    include_services=bool(args.include_services or args.service),
                    required_services=[args.service] if args.service else None,
                )
            finally:
                if previous_override is None:
                    os.environ.pop(PACKAGE_ROOT_OVERRIDE_ENV, None)
                else:
                    os.environ[PACKAGE_ROOT_OVERRIDE_ENV] = previous_override
            if not reusable:
                return {
                    "exitCode": 2,
                    "summary": f"stackctl package candidate collision for {target_name}",
                    "details": [detail, f"candidateDir={candidate_dir}"],
                    "baselineId": baseline_id,
                }
            reused_manifest = load_candidate_manifest(
                env_name,
                target_name,
                baseline_id,
                require_full=True,
            )
            if reused_manifest.get("release") != requested_release_bindings:
                return {
                    "exitCode": 2,
                    "summary": f"stackctl package release binding collision for {target_name}",
                    "details": [
                        "immutable candidate exists with different candidate/rollback release attestations"
                    ],
                    "baselineId": baseline_id,
                }
            reused_fingerprint_path = (
                candidate_dir / "packages" / "app" / "package-fingerprint.json"
            )
            reused_fingerprint = json.loads(
                reused_fingerprint_path.read_text(encoding="utf-8")
            )
            pointer = activate_deployment_candidate(target_name, baseline_id)
            return {
                "exitCode": 0,
                "summary": f"stackctl package reused immutable candidate for {env_name}",
                "details": [detail, f"candidateDir={candidate_dir}"],
                "baselineId": baseline_id,
                "candidateDir": str(candidate_dir),
                "activeCandidateRef": str(pointer),
                "reportDir": str(reused_fingerprint.get("reportRef") or ""),
                "packageFingerprint": str(reused_fingerprint_path),
                "packageDigest": reused_manifest["packageDigest"],
                "buildInputDigest": reused_manifest["buildInputDigest"],
                "imageDigest": reused_manifest["imageDigest"],
                "runtimeConfigDigest": reused_manifest["runtimeConfigDigest"],
                "environmentRuntimeDigest": reused_manifest[
                    "environmentRuntimeDigest"
                ],
                "runtimeSchemaVersion": reused_manifest["runtimeSchemaVersion"],
                "observabilityLogSink": reused_manifest[
                    "observabilityLogSink"
                ],
            }

        candidate_parent = candidate_dir.parent
        candidate_parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{candidate_dir.name}.staging-",
                dir=str(candidate_parent),
            )
        )
        os.environ[PACKAGE_ROOT_OVERRIDE_ENV] = str(staging_dir / "packages")
        try:
            payload = _command_package_unlocked(
                args,
                package_snapshot=package_snapshot,
            )
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
        finally:
            if previous_override is None:
                os.environ.pop(PACKAGE_ROOT_OVERRIDE_ENV, None)
            else:
                os.environ[PACKAGE_ROOT_OVERRIDE_ENV] = previous_override
        if int(payload.get("exitCode") or 0) != 0:
            shutil.rmtree(staging_dir, ignore_errors=True)
            return payload
        if candidate_dir.exists():
            shutil.rmtree(staging_dir)
            return {
                "exitCode": 2,
                "summary": f"stackctl package candidate collision for {target_name}",
                "details": [f"candidate already exists: {candidate_dir}"],
                "baselineId": baseline_id,
            }
        staging_dir.replace(candidate_dir)
        pointer = activate_deployment_candidate(target_name, baseline_id)
        staging_text = str(staging_dir)
        candidate_text = str(candidate_dir)
        payload = json.loads(
            json.dumps(payload, ensure_ascii=False).replace(
                staging_text,
                candidate_text,
            )
        )
        report_ref = str(payload.get("reportDir") or "").strip()
        if report_ref:
            evidence_root = (ROOT / report_ref).resolve()
            if evidence_root.is_dir() and evidence_root.is_relative_to(ROOT):
                for evidence_path in evidence_root.rglob("*"):
                    if not evidence_path.is_file() or evidence_path.suffix not in {
                        ".json",
                        ".md",
                    }:
                        continue
                    evidence_text = evidence_path.read_text(encoding="utf-8")
                    if staging_text in evidence_text:
                        evidence_path.write_text(
                            evidence_text.replace(staging_text, candidate_text),
                            encoding="utf-8",
                        )
        payload["candidateDir"] = str(candidate_dir)
        payload["activeCandidateRef"] = str(pointer)
        candidate_manifest = load_candidate_manifest(
            env_name,
            target_name,
            baseline_id,
            require_full=True,
        )
        for field in (
            "packageDigest",
            "buildInputDigest",
            "imageDigest",
            "runtimeConfigDigest",
            "environmentRuntimeDigest",
            "runtimeSchemaVersion",
            "observabilityLogSink",
        ):
            payload[field] = candidate_manifest[field]
        return payload


def _command_package_unlocked(
    args: argparse.Namespace,
    *,
    package_snapshot: dict[str, object] | None = None,
) -> dict[str, Any]:
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
    packaged_services: list[str] = []
    package_cache = target_cache_dir(target_name) / "package"
    go_build_cache = package_cache / "go-build"
    go_tmp = package_cache / "go-tmp"
    go_build_cache.mkdir(parents=True, exist_ok=True)
    go_tmp.mkdir(parents=True, exist_ok=True)
    package_environment = {
        "QWQ_DEPLOY_TARGET": target_name,
        "GOCACHE": str(go_build_cache),
        "GOTMPDIR": str(go_tmp),
    }
    preflight_reports, preflight_error = _run_runtime_compile_preflight(
        package_environment=package_environment,
    )
    reports.extend(preflight_reports)
    if preflight_error:
        timing = _finish_timing(started_monotonic, started_at)
        write_json(
            report_dir / "report.json",
            {
                "status": "GATE_BLOCK",
                "command": "package",
                "env": env_name,
                "target": target_name,
                "details": [preflight_error],
                "steps": reports,
                **timing,
            },
        )
        _write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="GATE_BLOCK",
            summary=f"stackctl runtime compile preflight blocked for {env_name}",
            details=[preflight_error],
            extra={"env": env_name},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl runtime compile preflight blocked for {env_name}",
            "details": [preflight_error],
            "reportDir": relpath(report_dir),
            **timing,
        }

    if not args.service:
        legal_result, legal_payload = _legal_static_command(
            "package",
            env_name,
            target=target_name,
        )
        reports.append(
            {
                "name": "legal-static-package",
                "argv": legal_payload.get("argv", []),
                "exitCode": legal_result.returncode,
                "stdout": legal_result.stdout,
                "stderr": legal_result.stderr,
            }
        )
        if legal_result.returncode != 0:
            timing = _finish_timing(started_monotonic, started_at)
            detail = (
                legal_result.stderr.strip()
                or legal_result.stdout.strip()
                or "legal-static package failed"
            )
            write_json(
                report_dir / "report.json",
                {"status": "failed", "steps": reports, **timing},
            )
            return {
                "exitCode": legal_result.returncode,
                "summary": f"stackctl package failed for legal-static/{env_name}",
                "details": [detail],
                "reportDir": relpath(report_dir),
                **timing,
            }
        details.append(
            f"legal-static package ready: {legal_payload.get('packageDir', '')}"
        )

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
        packaged_services = list(services)
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

    materialized_release_evidence: dict[str, str] = {}
    if not args.service:
        try:
            materialized_release_evidence = _materialize_release_evidence_configuration(
                env_name,
                target=target_name,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            timing = _finish_timing(started_monotonic, started_at)
            write_json(report_dir / "report.json", {"status": "failed", "steps": reports, **timing})
            _write_summary_bundle(
                report_dir,
                command="package",
                target=target_name,
                status="failed",
                summary=(
                    "stackctl package failed while materializing release evidence "
                    f"for {env_name}"
                ),
                details=[str(exc)],
                extra={"env": env_name},
                timing=timing,
            )
            return {
                "exitCode": 1,
                "summary": (
                    "stackctl package failed while materializing release evidence "
                    f"for {env_name}"
                ),
                "details": [str(exc)],
                "reportDir": relpath(report_dir),
                **timing,
            }
        if materialized_release_evidence:
            details.append(
                f"{env_name} release evidence materialized: "
                f"candidateId={materialized_release_evidence['candidateId']}"
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

    if (
        bool(args.include_services)
        and not args.service
        and target_name in {"alpha-local", "beta-local", "gamma-local"}
    ):
        try:
            image_manifest_path, image_manifest = _build_package_bound_local_images(
                env_name,
                target_name,
                report_dir=report_dir,
            )
        except RuntimeError as exc:
            timing = _finish_timing(started_monotonic, started_at)
            detail = str(exc)
            write_json(
                report_dir / "report.json",
                {
                    "status": "GATE_BLOCK",
                    "command": "package",
                    "env": env_name,
                    "target": target_name,
                    "details": [detail],
                    "steps": reports,
                    **timing,
                },
            )
            return {
                "exitCode": 2,
                "summary": f"stackctl package OCI build blocked for {env_name}",
                "details": [detail],
                "reportDir": relpath(report_dir),
                **timing,
            }
        details.extend(
            [
                f"OCI image manifest ready: {relpath(image_manifest_path)}",
                f"buildInputDigest: {image_manifest['buildInputDigest']}",
                f"imageDigest: {image_manifest['imageDigest']}",
            ]
        )

    ending_snapshot = workspace_snapshot()
    if package_snapshot is None:
        package_snapshot = ending_snapshot
    if ending_snapshot != package_snapshot:
        timing = _finish_timing(started_monotonic, started_at)
        details = [
            "workspace changed while package was being materialized",
            f"startBaselineId={package_snapshot.get('baselineId', '')}",
            f"endBaselineId={ending_snapshot.get('baselineId', '')}",
        ]
        write_json(
            report_dir / "report.json",
            {
                "status": "GATE_BLOCK",
                "command": "package",
                "env": env_name,
                "target": target_name,
                "details": details,
                **timing,
            },
        )
        _write_summary_bundle(
            report_dir,
            command="package",
            target=target_name,
            status="GATE_BLOCK",
            summary=f"stackctl package blocked for {env_name}",
            details=details,
            extra={"env": env_name},
            timing=timing,
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl package blocked for {env_name}",
            "details": details,
            "reportDir": relpath(report_dir),
            **timing,
        }

    try:
        fingerprint = write_package_fingerprint(
            env_name,
            target_name,
            report_dir=relpath(report_dir),
            include_services=True,
            details=details,
            service_packages=packaged_services,
            expected_snapshot=package_snapshot,
        )
        candidate_manifest = write_candidate_manifest(
            env_name,
            target_name,
            package_snapshot=package_snapshot,
            release_attestation=str(
                getattr(args, "release_attestation", "") or ""
            ),
            rollback_release_attestation=str(
                getattr(args, "rollback_release_attestation", "") or ""
            ),
        )
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        timing = _finish_timing(started_monotonic, started_at)
        write_json(
            report_dir / "report.json",
            {
                "status": "GATE_BLOCK",
                "command": "package",
                "env": env_name,
                "target": target_name,
                "baselineId": package_snapshot["baselineId"],
                "details": [str(exc)],
                "steps": reports,
                **timing,
            },
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl package candidate manifest blocked for {env_name}",
            "details": [str(exc)],
            "reportDir": relpath(report_dir),
            "baselineId": package_snapshot["baselineId"],
            **timing,
        }
    details.append(f"package fingerprint: {relpath(fingerprint)}")
    details.append(f"candidate manifest: {candidate_manifest}")
    details.append(f"baselineId: {package_snapshot['baselineId']}")
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "status": "ok",
        "command": "package",
        "env": env_name,
        "target": target_name,
        "baselineId": package_snapshot["baselineId"],
        "sourceRevision": package_snapshot["sourceRevision"],
        "workspaceStatusDigest": package_snapshot["workspaceStatusDigest"],
        "timestamp": utc_now(),
        "reportDir": relpath(report_dir),
        "steps": reports,
        **timing,
    }
    payload.update(materialized_release_evidence)
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
    return {
        "exitCode": 0,
        "summary": f"stackctl package completed for {env_name}",
        "details": details,
        "reportDir": relpath(report_dir),
        "packageFingerprint": relpath(fingerprint),
        "baselineId": package_snapshot["baselineId"],
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
    blocked = bool(issues) and (
        profile is VerificationProfile.RELEASE
        or (
            profile is VerificationProfile.INTEGRATION
            and args.kind == "all"
            and target_name in NONPROD_TARGETS
        )
    )
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
            data_readiness_path=_data_readiness_path_from_verify_args(
                args,
                environment=env_name,
                profile=profile,
            ),
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


def _run_nonprod_business_data_profile(
    args: argparse.Namespace,
    *,
    environment: str,
    target_name: str,
    report_dir: Path,
    prerequisites_passed: bool,
) -> dict[str, Any]:
    result_dir = report_dir / "nonprod-business-data"
    if not prerequisites_passed:
        result = {
            "schema": "qwq.case_result",
            "caseId": "alpha-beta-gamma-nonprod-business-data",
            "status": "GATE_BLOCK",
            "executed": 0,
            "skipped": 0,
            "target": target_name,
            "environment": environment,
            "specRefs": [
                "specs/feature-tree/spec.md#uat-009",
                "specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001",
                "specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003",
            ],
            "issues": [
                "nonprod business data mutation was not started because prerequisite gates failed"
            ],
        }
        write_json(result_dir / "case-result.json", result)
        return result

    try:
        active = active_deployment_candidate(target_name)
        if active is None:
            raise ValueError("active immutable deployment candidate is required")
        manifest = load_candidate_manifest(
            environment,
            target_name,
            active["baselineId"],
            require_full=True,
        )
        readiness, _ = _load_data_release_readiness(
            environment=environment,
            release_id=str(getattr(args, "data_release_id", "") or ""),
            verify_run_id=str(getattr(args, "data_verify_run_id", "") or ""),
            manifest_digest=str(
                getattr(args, "data_manifest_digest", "") or ""
            ),
            readiness_phase=ReadinessPhase.COMMERCIAL,
        )
        raw_evidence_path = str(
            getattr(args, "nonprod_data_evidence", "") or ""
        ).strip()
        if not raw_evidence_path:
            raise ValueError("--nonprod-data-evidence is required")
        evidence_path = Path(raw_evidence_path).expanduser()
        if not evidence_path.is_absolute():
            evidence_path = ROOT / evidence_path
        evidence_path = evidence_path.resolve()
        evidence_root = output_root().expanduser().resolve()
        try:
            evidence_path.relative_to(evidence_root)
        except ValueError as exc:
            raise ValueError(
                "nonprod data evidence must be below QWQ_OUTPUT_ROOT"
            ) from exc
        topology = load_environment_topology()
        target = get_target(topology, target_name)
        base_url = str((target.get("publicBases") or {}).get("api") or "").rstrip(
            "/"
        )
        if not base_url.startswith("https://"):
            raise ValueError("nonprod business data requires canonical HTTPS API")
        return run_nonprod_business_data_verification(
            environment=environment,
            target=target_name,
            base_url=base_url,
            candidate_manifest=manifest,
            release_readiness=readiness,
            evidence_path=evidence_path,
            report_dir=result_dir,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        result = {
            "schema": "qwq.case_result",
            "caseId": "alpha-beta-gamma-nonprod-business-data",
            "status": "GATE_BLOCK",
            "executed": 0,
            "skipped": 0,
            "target": target_name,
            "environment": environment,
            "specRefs": [
                "specs/feature-tree/spec.md#uat-009",
                "specs/feature-tree/runtime/runtime-data-engineering/spec.md#sit-001",
                "specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003",
            ],
            "issues": [str(exc)],
        }
        write_json(result_dir / "case-result.json", result)
        return result


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
    force_deadline_rollback = False
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
            timing = _finish_timing(started_monotonic, started_at)
            payload = {
                "status": ProbeOutcome.GATE_BLOCK.value,
                "command": "verify",
                "timestamp": utc_now(),
                "kind": args.kind,
                "profile": profile.value,
                "environment": env_name,
                "target": target_name,
                "providerReadiness": provider_readiness,
                "steps": steps,
                **timing,
            }
            write_json(report_dir / "report.json", payload)
            write_json(report_dir / "findings.json", {"issues": issues})
            _write_summary_bundle(
                report_dir,
                command="verify",
                target=target_name,
                status="blocked",
                summary="stackctl verify is GATE_BLOCK by Provider readiness",
                details=issues,
                extra={"kind": args.kind, "profile": profile.value},
                timing=timing,
            )
            return {
                "exitCode": 2,
                "summary": "stackctl verify is GATE_BLOCK by Provider readiness",
                "details": issues,
                "reportDir": relpath(report_dir),
                **timing,
            }
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
            result = run(
                command,
                env=_verify_child_environment(target_name),
            )
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
    for package_env in package_envs:
        package_target = args.target or DEFAULT_TARGET_BY_ENV[package_env]
        ok, package_detail = can_reuse_package(
            package_env,
            package_target,
            include_services=True,
        )
        steps.append(
            {
                "kind": "package",
                "env": package_env,
                "exitCode": 0 if ok else 2,
                "consumed": ok,
                "details": [package_detail],
                "reportDir": "",
            }
        )
        if not ok:
            issues.append(
                f"fixed package is unavailable for {package_env}/{package_target}: "
                f"{package_detail}; run stackctl package explicitly"
            )
    stdout_sections: list[tuple[str, str]] = []
    commands = _selected_verify_commands(
        args.kind,
        env_name if env_name in ENVIRONMENTS else "",
        target_name=target_name,
        profile=profile,
    )
    for command in commands:
        result = run(
            command,
            env=_verify_child_environment(target_name),
        )
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
                release_id=getattr(args, "data_release_id", ""),
                verify_run_id=getattr(args, "data_verify_run_id", ""),
                manifest_digest=getattr(args, "data_manifest_digest", ""),
                lifecycle_exit_ref=getattr(
                    args,
                    "data_lifecycle_exit_ref",
                    "",
                ),
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
        data_readiness_path=_data_readiness_path_from_verify_args(
            args,
            environment=env_name,
            profile=profile,
        ),
    ):
        result = run(
            profile_command["argv"],
            cwd=profile_command.get("cwd"),
            env=_verify_child_environment(
                target_name,
                profile_command.get("env"),
            ),
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
    if (
        profile is VerificationProfile.INTEGRATION
        and args.kind == "all"
        and target_name in NONPROD_TARGETS
    ):
        runtime_workload = _current_runtime_workload(target_name)
        if runtime_workload in {"content-release", "content-commercial"}:
            # content-release proves import/API/media via data-release bindings;
            # Provider/share/fault nonprod mutations require the full commercial
            # plane and must not block this workload.
            steps.append(
                {
                    "kind": "nonprod-business-data",
                    "profile": profile.value,
                    "exitCode": 0,
                    "reportPath": "",
                    "details": [
                        f"skipped: active workload={runtime_workload}; "
                        "data-release ship verify is the content-plane evidence"
                    ],
                    "caseResult": {
                        "schema": "qwq.case_result",
                        "caseId": "alpha-beta-gamma-nonprod-business-data",
                        "status": "skipped",
                        "executed": 0,
                        "skipped": 1,
                        "target": target_name,
                        "environment": env_name,
                        "issues": [],
                    },
                }
            )
        else:
            nonprod_data_result = _run_nonprod_business_data_profile(
                args,
                environment=env_name,
                target_name=target_name,
                report_dir=report_dir,
                prerequisites_passed=not issues,
            )
            nonprod_data_passed = (
                nonprod_data_result.get("status") == "passed"
                and int(nonprod_data_result.get("executed") or 0) > 0
                and int(nonprod_data_result.get("skipped") or 0) == 0
            )
            steps.append(
                {
                    "kind": "nonprod-business-data",
                    "profile": profile.value,
                    "exitCode": 0 if nonprod_data_passed else 2,
                    "reportPath": relpath(
                        report_dir / "nonprod-business-data/case-result.json"
                    ),
                    "details": list(nonprod_data_result.get("issues") or []),
                    "caseResult": nonprod_data_result,
                }
            )
            if not nonprod_data_passed:
                details = list(nonprod_data_result.get("issues") or [])
                issues.append(
                    "nonprod business data verification failed: "
                    + ("; ".join(details) if details else "invalid CaseResult")
                )
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
        "adapterId": "ext.obs.elasticsearch",
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
    failure_reason: str = "",
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
            failure_reason
            or "commercial full workload requires product telemetry log-sink binding",
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
        "executed": len(action_statuses),
        "skipped": 0,
        "failureReason": failure_reason if gate_blocked else "",
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
        "executed": len(action_statuses),
        "skipped": 0,
        **timing,
    }


def _product_telemetry_log_sink_failure_reason(
    action: str,
    error: Exception,
) -> str:
    """Expose only operator-actionable, credential-free failure context."""

    if isinstance(error, LocalEnvironmentHTTPError):
        return f"{action}: product-ops request failed with HTTP {error.status}"
    message = str(error).strip()
    safe_messages = {
        "GATE_BLOCK: exactly one active candidate-bound identity receipt is required",
        "product telemetry query authorization is unavailable",
        "product-ops public base is unavailable",
        "cold-start failed",
        "health failed",
        "permission probe returned unexpected status",
        "permission probe unexpectedly succeeded",
    }
    if message in safe_messages:
        return message
    return f"{action}: failed; inspect redacted stackctl evidence"


def _log_sink_control_actions(action: str) -> tuple[str, ...]:
    if action == "all":
        return ("cold-start", "health", "send-query", "permission-failure")
    return (action,)


@contextlib.contextmanager
def _local_managed_ca_environment(target_name: str):
    """Scope canonical local CA trust to one in-process control action."""

    previous = os.environ.get("SSL_CERT_FILE")
    os.environ["SSL_CERT_FILE"] = str(root_certificate_path(target_name))
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SSL_CERT_FILE", None)
        else:
            os.environ["SSL_CERT_FILE"] = previous


def _log_sink_control_query_session(
    *,
    api_base: str,
    environment: str,
    target_name: str,
) -> LocalAcceptanceSession:
    """Resolve a query session without serializing a bearer token into evidence."""
    if environment in {"alpha", "beta", "gamma"}:
        token = mint_local_product_ops_operator_token(environment, target_name)
        return LocalAcceptanceSession(
            owner_id=f"operator:content-commercial:{environment}",
            persona_id="",
            access_token=token,
        )
    query_token = os.environ.get("PRODUCT_TELEMETRY_QUERY_TOKEN", "").strip()
    if query_token:
        return LocalAcceptanceSession(
            owner_id="log-sink-control",
            persona_id="log-sink-control",
            access_token=query_token,
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
        # When a full runtime receipt is already running, re-entering `up`
        # is rejected as leftover-attempt; treat that as an already-warmed
        # cold-start rather than forcing a destructive down/up cycle.
        try:
            active_attempt = load_startup_attempt(target_name)
        except (OSError, ValueError):
            active_attempt = None
        if (
            isinstance(active_attempt, dict)
            and active_attempt.get("status") == "running"
            and active_attempt.get("workload") == "full"
            and active_attempt.get("target") == target_name
            and active_attempt.get("env") == environment
        ):
            write_json(
                report_dir / "cold-start" / "already-running.json",
                {
                    "schema": "stackctl-product-telemetry-cold-start-reuse",
                    "target": target_name,
                    "environment": environment,
                    "startupAttemptId": active_attempt.get("attemptId"),
                    "workload": "full",
                    "status": "reused_running_full",
                },
            )
            return
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
        # Log-sink health proves product-ops + ES telemetry path.
        # Do not require scope=full commercial probes (e.g. global_search).
        result = command_health(
            argparse.Namespace(
                command="health",
                target=target_name,
                scope="content-commercial",
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
    session = open_reference_acceptance_session(
        api_base,
        environment=environment,
        target_name=target_name,
    )
    if action == "permission-failure":
        try:
            request_local_environment_json(
                product_ops_base,
                path="/ops/events/summary",
                session=session,
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
    )
    query_session = _log_sink_control_query_session(
        api_base=api_base,
        environment=environment,
        target_name=target_name,
    )
    request_local_environment_json(
        product_ops_base,
        path="/ops/events/summary",
        session=query_session,
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
    with _local_managed_ca_environment(args.target):
        for action in actions:
            try:
                _run_product_telemetry_log_sink_control_action(
                    action=action,
                    target_name=args.target,
                    environment=environment,
                    report_dir=report_dir,
                )
            except (RuntimeError, ValueError, LocalEnvironmentHTTPError) as exc:
                action_statuses.append({"action": action, "status": "failed"})
                timing = _finish_timing(started_monotonic, started_at)
                return _write_product_telemetry_log_sink_control_report(
                    report_dir=report_dir,
                    target_name=args.target,
                    action=args.action,
                    receipt=receipt,
                    action_statuses=action_statuses,
                    gate_blocked=True,
                    failure_reason=_product_telemetry_log_sink_failure_reason(
                        action,
                        exc,
                    ),
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


def _reuse_running_full_for_bounded_workload(
    args: argparse.Namespace,
    *,
    target_name: str,
    env_name: str,
    report_target: str,
    report_dir: Path,
    started_monotonic: float,
    started_at: str,
) -> dict[str, Any] | None:
    workload = str(getattr(args, "workload", "") or "").strip()
    if workload not in {"content-release", "content-commercial"}:
        return None
    try:
        active_attempt = load_startup_attempt(target_name)
    except (OSError, ValueError) as exc:
        timing = _finish_timing(started_monotonic, started_at)
        details = [f"active runtime receipt is unreadable: {exc}"]
        write_json(
            report_dir / "report.json",
            {
                "command": "up",
                "target": report_target,
                "resolvedTarget": target_name,
                "workload": workload,
                "status": "gate_block",
                "blockerKind": "runtime_receipt_unreadable",
                "details": details,
                **timing,
            },
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl up is GATE_BLOCK for {report_target}",
            "details": details,
            "reportDir": relpath(report_dir),
            "blockerKind": "runtime_receipt_unreadable",
            **timing,
        }
    if not (
        active_attempt
        and active_attempt.get("status") == "running"
        and active_attempt.get("workload") == "full"
    ):
        return None

    timing = _finish_timing(started_monotonic, started_at)
    details = [
        f"{workload} reuses the healthy full runtime without changing its startup receipt",
        f"full attemptId={active_attempt.get('attemptId')}",
    ]
    report = {
        "command": "up",
        "target": report_target,
        "resolvedTarget": target_name,
        "environment": env_name,
        "workload": workload,
        "status": "ok",
        "sessionKind": "hot",
        "runtimeReused": True,
        "baselineWorkload": "full",
        "startupAttempt": active_attempt,
        "details": details,
        **timing,
    }
    write_json(report_dir / "report.json", report)
    _write_summary_bundle(
        report_dir,
        command="up",
        target=report_target,
        status="ok",
        summary=f"stackctl up reused full runtime for {report_target}",
        details=details,
        extra={
            "workload": workload,
            "sessionKind": "hot",
            "runtimeReused": True,
            "baselineWorkload": "full",
        },
        timing=timing,
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl up reused full runtime for {report_target}",
        "details": details,
        "reportDir": relpath(report_dir),
        "sessionKind": "hot",
        "runtimeReused": True,
        **timing,
    }


def _command_up_impl(args: argparse.Namespace) -> dict[str, Any]:
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
    formal_release = bool(getattr(args, "formal_release", False))
    release_composition: dict[str, Any] = {}
    runtime_images: dict[str, dict[str, str]] = {}
    destructive_actions: list[str] = []
    if formal_release and (
        requested_target not in {"alpha-local", "beta-local", "gamma-local"}
        or not getattr(args, "skip_build", False)
        or not getattr(args, "skip_app", False)
        or args.workload != "full"
        or not str(getattr(args, "release_manifest", "") or "").strip()
    ):
        timing = _finish_timing(started_monotonic, started_at)
        return {
            "exitCode": 2,
            "summary": "stackctl up formal release is GATE_BLOCK",
            "details": [
                "formal release requires alpha/beta/gamma, --workload full, "
                "--skip-build, --skip-app and a canonical --release-manifest"
            ],
            **timing,
        }
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
    if requested_target in {"alpha-local", "beta-local", "gamma-local"}:
        if build_only:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl up build-only is retired",
                "details": [
                    "up only consumes a fixed candidate; run stackctl package explicitly"
                ],
                "reportDir": relpath(report_dir),
                **timing,
            }
        package_ok, package_detail = can_reuse_package(
            env_name,
            requested_target,
            include_services=True,
            require_workspace_match=False,
        )
        if not package_ok:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": f"stackctl up GATE_BLOCK: fixed package missing for {requested_target}",
                "details": [package_detail, "run stackctl package explicitly"],
                "reportDir": relpath(report_dir),
                **timing,
            }
        # Local start scripts must never compile or re-package the workspace.
        args.skip_build = True
    bounded_reuse = _reuse_running_full_for_bounded_workload(
        args,
        target_name=requested_target,
        env_name=env_name,
        report_target=report_target,
        report_dir=report_dir,
        started_monotonic=started_monotonic,
        started_at=started_at,
    )
    if bounded_reuse is not None:
        return bounded_reuse
    # Migration drift is diagnostic input only. Destructive repair is never implicit.
    if requested_target in {"alpha-local", "beta-local"} and not build_only:
        drift = probe_migration_drift(requested_target)
        if drift.has_drift:
            timing = _finish_timing(started_monotonic, started_at)
            details = [
                format_drift_gate_block(drift),
                "use an explicitly approved stackctl repair action; up never wipes data",
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
    # A content release starts only the import/consumer data plane. Device
    # selection belongs to a separate App UAT command, never to server startup.
    if args.workload in {"content-release", "content-commercial"}:
        args.skip_app = True
    commercial_claim = args.workload == "full"
    log_sink_receipt = {
        "source": "not-required",
        "status": "not-claimed",
        "redactedDigest": "",
    }
    log_sink_redaction_values: tuple[str, ...] = ()
    if args.workload == "full" and requested_target in {
        "alpha-local",
        "beta-local",
        "gamma-local",
    }:
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

    cmd = ["stackctl", "up", "--target", requested_target]
    if requested_target in {"alpha-local", "beta-local", "gamma-local"}:
        try:
            profile_name, profile_kind, _ = tls_profile(requested_target)
            if profile_kind != "local-managed":
                raise PublicDomainTlsError(
                    f"GATE_BLOCK: {requested_target} must use local-managed TLS"
                )
            try:
                tls_evidence = verify_certificate(requested_target)
            except PublicDomainTlsError:
                tls_evidence = issue_certificate(requested_target)
            resolver_handoff = materialize_handoff(requested_target)
            steps.extend(
                (
                    {
                        "name": "local-managed-tls",
                        "exitCode": 0,
                        "stdout": json.dumps(tls_evidence, ensure_ascii=False),
                        "stderr": "",
                    },
                    {
                        "name": "canonical-local-resolver-handoff",
                        "exitCode": 0,
                        "stdout": json.dumps(resolver_handoff, ensure_ascii=False),
                        "stderr": "",
                    },
                )
            )
        except (PublicDomainTlsError, LocalTargetHandoffError, OSError, ValueError) as exc:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr=str(exc),
            )
            steps.append(
                {
                    "name": "local-managed-tls-and-resolver",
                    "exitCode": 2,
                    "stdout": "",
                    "stderr": str(exc),
                }
            )
        else:
            result = None
    else:
        result = None

    if result is not None:
        pass
    elif formal_release:
        env = _gamma_env_from_port_manifest(topology, requested_target)
        env["QWQ_RUN_ROOT"] = str(report_dir.resolve())
        env["QWQ_OBSERVABILITY_RUN_ROOT"] = str(
            env_observability_run_dir(env_name, report_dir.name).resolve()
        )
        env["QWQ_WORKLOAD"] = "full"
        env["LOCAL_GAMMA_COMPOSE_UP_TIMEOUT_SECONDS"] = "420"
        telemetry_env, telemetry_advisory = _optional_product_telemetry_environment(
            env_name, requested_target
        )
        env.update(telemetry_env)
        if telemetry_advisory:
            steps.append(
                {
                    "kind": "observability-prerequisite",
                    "exitCode": 2,
                    "blocking": True,
                    "stdout": "",
                    "stderr": telemetry_advisory,
                }
            )
        cmd = _gamma_start_command(args)
        syntax_cmd = [
            "bash",
            "-n",
            "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
        ]
        syntax_result = run(syntax_cmd, env=env)
        provider_error = None
        if syntax_result.returncode == 0:
            provider_error = _bind_formal_local_release_provider_environment(
                env,
                environment_name=env_name,
                target_name=requested_target,
                workload=args.workload,
                debug_sms_substitute=True,
            )
        steps.append(
            {
                "name": "formal-local-release-script-syntax",
                "argv": syntax_cmd,
                "exitCode": syntax_result.returncode,
                "stdout": syntax_result.stdout,
                "stderr": syntax_result.stderr,
            }
        )
        if provider_error is not None or telemetry_advisory or syntax_result.returncode:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr=provider_error or telemetry_advisory or syntax_result.stderr,
            )
        else:
            try:
                release_composition = _bind_gamma_release_image_refs(
                    Path(str(args.release_manifest)).expanduser().resolve(),
                    env,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                result = subprocess.CompletedProcess(
                    cmd,
                    2,
                    stdout="",
                    stderr=str(exc),
                )
            else:
                result = run_stage(
                    requested_target,
                    cmd,
                    env=env,
                    live_prefix=f"[{requested_target}] ",
                )
                if result.returncode == 0:
                    try:
                        runtime_images = _inspect_gamma_release_runtime(
                            release_composition,
                            env,
                        )
                    except ValueError as exc:
                        result = subprocess.CompletedProcess(
                            cmd,
                            2,
                            stdout=result.stdout,
                            stderr=str(exc),
                        )
    elif requested_target in {"alpha-local", "beta-local", "gamma-local"}:
        # Every supported local workload consumes the same packaged OCI
        # composition.  content-release only narrows runtime probes; it never
        # selects the retired Alpha/Beta build-from-worktree implementations.
        env = _gamma_env_from_port_manifest(topology, requested_target)
        env["QWQ_RUN_ROOT"] = str(report_dir.resolve())
        env["QWQ_OBSERVABILITY_RUN_ROOT"] = str(
            env_observability_run_dir(env_name, report_dir.name).resolve()
        )
        env["QWQ_WORKLOAD"] = args.workload
        telemetry_advisory = ""
        if args.workload == "full":
            telemetry_env, telemetry_advisory = (
                _optional_product_telemetry_environment(
                    env_name,
                    requested_target,
                )
            )
            env.update(telemetry_env)
        elif args.workload == "content-commercial":
            # Product Ops must bind the local Elasticsearch endpoint to start,
            # but full commercial observability remains a separate workload gate.
            try:
                commercial_log_sink = load_product_telemetry_log_sink(
                    env_name,
                    requested_target,
                )
            except (RuntimeError, ValueError) as exc:
                telemetry_advisory = str(exc)
                env["QWQ_PRODUCT_TELEMETRY_AVAILABLE"] = "0"
            else:
                env.update(commercial_log_sink.environment)
                env["QWQ_PRODUCT_TELEMETRY_AVAILABLE"] = "0"
                log_sink_receipt = commercial_log_sink.redacted_receipt()
                log_sink_redaction_values = tuple(
                    commercial_log_sink.environment.values()
                )
        else:
            env["QWQ_PRODUCT_TELEMETRY_AVAILABLE"] = "0"
        cmd = _gamma_start_command(args)
        syntax_cmd = [
            "bash",
            "-n",
            "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
        ]
        syntax_result = run(syntax_cmd, env=env)
        provider_error = None
        if syntax_result.returncode == 0:
            provider_error = _bind_formal_local_release_provider_environment(
                env,
                environment_name=env_name,
                target_name=requested_target,
                workload=args.workload,
                debug_sms_substitute=True,
            )
        steps.append(
            {
                "name": "shared-local-runtime-script-syntax",
                "argv": syntax_cmd,
                "exitCode": syntax_result.returncode,
                "stdout": syntax_result.stdout,
                "stderr": syntax_result.stderr,
            }
        )
        if provider_error is not None or telemetry_advisory or syntax_result.returncode:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout="",
                stderr=provider_error or telemetry_advisory or syntax_result.stderr,
            )
        else:
            try:
                release_composition = _bind_gamma_packaged_service_image_refs(
                    env_name,
                    env,
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                result = subprocess.CompletedProcess(
                    cmd,
                    2,
                    stdout="",
                    stderr=str(exc),
                )
            else:
                steps.append(
                    {
                        "name": "package-bound-runtime-composition",
                        "exitCode": 0,
                        "stdout": release_composition["imageVersion"],
                        "stderr": "",
                    }
                )
                result = run_stage(
                    requested_target,
                    cmd,
                    env=env,
                    live_prefix=f"[{requested_target}] ",
                )
    elif requested_target == "prod-sim":
        cmd = ["bash", "quwoquan_ops/cli/prod_sim/start_prod_sim_stack.sh", "up"]
        readiness_value = str(
            getattr(args, "data_release_readiness", "")
            or os.environ.get("DATA_RELEASE_READINESS_RECEIPT", "")
        ).strip()
        result = run_stage(
            "prod-sim",
            cmd,
            env={"DATA_RELEASE_READINESS_RECEIPT": readiness_value},
            live_prefix="[prod-sim] ",
        )
        if result.returncode == 0:
            try:
                background_tail = tail_prod_sim_background_logs()
            except RuntimeError as exc:
                steps.append(
                    {
                        "kind": "prod-sim-background-tail",
                        "exitCode": 1,
                        "stdout": "",
                        "stderr": str(exc),
                    }
                )
                result = subprocess.CompletedProcess(
                    cmd, 1, stdout=result.stdout, stderr=str(exc)
                )
            else:
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

    if (
        result.returncode == 0
        and requested_target in {"alpha-local", "beta-local", "gamma-local"}
        and args.workload in {"full", "content-commercial"}
    ):
        product_ops_base_url = str(
            (get_target(topology, requested_target).get("publicBases") or {}).get(
                "productOps"
            )
            or ""
        ).strip()
        try:
            if not product_ops_base_url:
                raise ExperimentPolicyActivationError(
                    "target topology lacks Product Ops public base"
                )
            policy_receipt = activate_search_experiment_policy(
                environment=env_name,
                target=requested_target,
                product_ops_base_url=product_ops_base_url,
            )
            policy_receipt_path = report_dir / "experiment-policy-activation.json"
            write_json(policy_receipt_path, policy_receipt)
            steps.append(
                {
                    "name": "package-bound-experiment-policy-activation",
                    "exitCode": 0,
                    "stdout": relpath(policy_receipt_path),
                    "stderr": "",
                }
            )
        except (ExperimentPolicyActivationError, OSError, RuntimeError, ValueError) as exc:
            result = subprocess.CompletedProcess(
                cmd,
                2,
                stdout=str(result.stdout or ""),
                stderr=str(exc),
            )
            steps.append(
                {
                    "name": "package-bound-experiment-policy-activation",
                    "exitCode": 2,
                    "stdout": "",
                    "stderr": str(exc),
                }
            )

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
            "formalRelease": formal_release,
            "releaseComposition": release_composition,
            "runtimeMode": "immutable-oci" if formal_release else "",
            "runtimeCandidateDigest": (
                str(release_composition.get("candidateId") or "")
                if formal_release
                else ""
            ),
            "runtimeImages": runtime_images,
            "destructiveRepairPerformed": bool(destructive_actions),
            "destructiveActions": destructive_actions,
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
            "formalRelease": formal_release,
            "releaseComposition": release_composition,
            "runtimeMode": "immutable-oci" if formal_release else "",
            "runtimeCandidateDigest": (
                str(release_composition.get("candidateId") or "")
                if formal_release
                else ""
            ),
            "runtimeImages": runtime_images,
            "destructiveRepairPerformed": bool(destructive_actions),
            "destructiveActions": destructive_actions,
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
    return payload


def command_up(args: argparse.Namespace) -> dict[str, Any]:
    """Hold the target operation lock for every return and exception path."""

    requested_target = str(getattr(args, "target", "") or "").strip()
    requested_env = str(getattr(args, "env", "") or "").strip()
    if not requested_target and requested_env:
        requested_target = str(DEV_UP_STACK_TARGETS.get(requested_env) or "")
        if not requested_target:
            requested_target = app_target_for_env(requested_env)
    local_targets = {"alpha-local", "beta-local", "gamma-local", "prod-sim"}
    if requested_target not in local_targets:
        return _command_up_impl(args)
    operation_scope = contextlib.ExitStack()
    try:
        operation_scope.enter_context(_local_stack_operation_lock(requested_target))
        topology = load_environment_topology()
        active_attempt = load_startup_attempt(requested_target)
        bounded_reuses_full = (
            str(getattr(args, "workload", "") or "")
            in {"content-release", "content-commercial"}
            and active_attempt is not None
            and active_attempt.get("status") == "running"
            and active_attempt.get("workload") == "full"
        )
        if not bounded_reuses_full:
            assert_local_runtime_available(topology, requested_target)
    except (OSError, RuntimeError, ValueError) as exc:
        operation_scope.close()
        lock_error = exc
    else:
        with operation_scope:
            return _command_up_impl(args)
    topology = load_environment_topology()
    target = get_target(topology, requested_target)
    env_name = str(target["env"])
    report_target = requested_env or requested_target
    report_dir = resolve_report_dir(args, env_name, report_target)
    details = [
        str(lock_error),
        "wait for the active operation or stop the conflicting local runtime",
    ]
    write_json(
        report_dir / "report.json",
        {
            "command": "up",
            "target": report_target,
            "resolvedTarget": requested_target,
            "workload": str(getattr(args, "workload", "") or ""),
            "status": "gate_block",
            "details": details,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="up",
        target=report_target,
        status="gate_block",
        summary=f"stackctl up is blocked for {report_target}",
        details=details,
    )
    return {
        "exitCode": 2,
        "summary": f"stackctl up is GATE_BLOCK for {report_target}",
        "details": details,
        "reportDir": relpath(report_dir),
    }


def command_consumer_lease(args: argparse.Namespace) -> dict[str, Any]:
    action = str(args.action)
    target = str(args.target)
    device = str(getattr(args, "device", "") or "").strip()
    consumer = str(getattr(args, "consumer", "flutter-run") or "flutter-run").strip()
    platform = str(getattr(args, "platform", "android") or "android").strip()
    if action in {"acquire", "release"} and not device:
        return {
            "exitCode": 2,
            "summary": f"consumer-lease {action} requires --device",
            "details": ["select one connected Android device or booted iOS Simulator"],
        }
    try:
        if action == "acquire":
            ports = [
                int(value.strip())
                for value in str(args.ports).split(",")
                if value.strip()
            ]
            with _local_stack_operation_lock(target):
                application_id = str(args.package_name)
                if platform == "ios-simulator":
                    application_id = str(getattr(args, "bundle_id", "") or "").strip()
                    if not application_id:
                        raise ValueError("--bundle-id is required for ios-simulator")
                lease = acquire_consumer_lease(
                    target=target,
                    device=device,
                    consumer=consumer,
                    package_name=application_id,
                    ports=ports,
                    platform=platform,
                    handoff_digest=str(getattr(args, "handoff_digest", "") or ""),
                    release_id=str(getattr(args, "release_id", "") or ""),
                    manifest_digest=str(
                        getattr(args, "manifest_digest", "") or ""
                    ),
                    readiness_receipt_digest=str(
                        getattr(args, "readiness_receipt_digest", "") or ""
                    ),
                    build_grace_seconds=int(args.build_grace_seconds),
                )
            return {
                "exitCode": 0,
                "summary": f"consumer lease acquired for {target}",
                "details": [
                    f"device={device}",
                    f"platform={platform}",
                    f"consumer={consumer}",
                    f"ports={','.join(str(port) for port in ports) or 'none'}",
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
                    f"platform={lease.get('platform', 'android')} "
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


def _bounded_workload_down_decision(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    requested_workload = str(getattr(args, "workload", "") or "").strip()
    if requested_workload not in {"content-release", "content-commercial"}:
        return None
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    try:
        active_attempt = load_startup_attempt(args.target)
    except (OSError, ValueError) as exc:
        details = [f"active runtime receipt is unreadable: {exc}"]
        return {
            "exitCode": 2,
            "summary": f"stackctl down is GATE_BLOCK for {args.target}",
            "details": details,
            "reportDir": relpath(report_dir),
            "blockerKind": "runtime_receipt_unreadable",
        }

    active_status = str((active_attempt or {}).get("status") or "")
    active_workload = str((active_attempt or {}).get("workload") or "")
    if not active_attempt or active_status == "stopped":
        details = [f"no active {requested_workload} runtime requires teardown"]
    elif active_status == "running" and active_workload == "full":
        details = [
            f"{requested_workload} reused the full runtime; bounded teardown is a no-op",
            "the full startup receipt remains running",
        ]
    elif active_workload != requested_workload:
        details = [
            f"requested workload {requested_workload} does not own active runtime "
            + f"{active_workload or '<unknown>'}/{active_status or '<unknown>'}"
        ]
        write_json(
            report_dir / "report.json",
            {
                "command": "down",
                "target": args.target,
                "workload": requested_workload,
                "status": "gate_block",
                "blockerKind": "runtime_workload_mismatch",
                "startupAttempt": active_attempt,
                "details": details,
            },
        )
        return {
            "exitCode": 2,
            "summary": f"stackctl down is GATE_BLOCK for {args.target}",
            "details": details,
            "reportDir": relpath(report_dir),
            "blockerKind": "runtime_workload_mismatch",
        }
    else:
        return None

    write_json(
        report_dir / "report.json",
        {
            "command": "down",
            "target": args.target,
            "workload": requested_workload,
            "status": "ok",
            "runtimeReused": active_workload == "full",
            "startupAttempt": active_attempt,
            "details": details,
        },
    )
    _write_summary_bundle(
        report_dir,
        command="down",
        target=args.target,
        status="ok",
        summary=f"stackctl down completed for {args.target}",
        details=details,
        extra={
            "workload": requested_workload,
            "runtimeReused": active_workload == "full",
        },
    )
    return {
        "exitCode": 0,
        "summary": f"stackctl down completed for {args.target}",
        "details": details,
        "reportDir": relpath(report_dir),
        "runtimeReused": active_workload == "full",
    }


def command_down(args: argparse.Namespace) -> dict[str, Any]:
    bounded_decision = _bounded_workload_down_decision(args)
    if bounded_decision is not None:
        return bounded_decision
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
    formal_release = bool(getattr(args, "formal_release", False))
    purge_rebuildable_state = bool(
        getattr(args, "purge_rebuildable_state", False)
    )
    release_composition: dict[str, Any] = {}
    runtime_composition_source = ""
    runtime_compose_project = ""

    if purge_rebuildable_state and (
        formal_release
        or args.target not in {"alpha-local", "beta-local", "gamma-local"}
    ):
        return {
            "exitCode": 2,
            "summary": f"stackctl down is GATE_BLOCK for {args.target}",
            "details": [
                "rebuildable-state purge is only available for non-formal Alpha/Beta/Gamma local teardown"
            ],
        }

    if formal_release:
        manifest_value = str(getattr(args, "release_manifest", "") or "").strip()
        if args.target not in {"alpha-local", "beta-local", "gamma-local"}:
            return {
                "exitCode": 2,
                "summary": f"stackctl down is GATE_BLOCK for {args.target}",
                "details": ["formal teardown supports only Alpha/Beta/Gamma local targets"],
            }
        if not manifest_value:
            return {
                "exitCode": 2,
                "summary": f"stackctl down is GATE_BLOCK for {args.target}",
                "details": ["formal teardown requires --release-manifest"],
            }
        manifest_path = Path(manifest_value).expanduser().resolve()
        env = _gamma_env_from_port_manifest(topology, args.target)
        try:
            release_composition = _bind_gamma_release_teardown_image_refs(
                manifest_path,
                env,
            )
            runtime_composition_source = "release-manifest"
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "exitCode": 2,
                "summary": f"stackctl down is GATE_BLOCK for {args.target}",
                "details": [str(exc)],
            }
        cmd = [
            "bash",
            "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh",
            "--down",
            "--formal-release-teardown",
        ]
        _bind_gamma_down_parse_environment(env)
        result = run(cmd, env=env)
    elif args.target in {"alpha-local", "beta-local", "gamma-local"}:
        cmd = ["bash", "quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh", "--down"]
        env = _gamma_env_from_port_manifest(topology, args.target)
        try:
            runtime_receipt = _load_gamma_runtime_image_composition(args.target)
            if runtime_receipt is None:
                if purge_rebuildable_state:
                    raise ValueError(
                        "rebuildable-state purge requires an exact runtime receipt"
                    )
                release_composition = _bind_gamma_packaged_service_image_refs(
                    env_name,
                    env,
                )
                runtime_composition_source = "service-package-provenance"
            else:
                release_composition, compose_project = runtime_receipt
                runtime_compose_project = compose_project
                env["LOCAL_GAMMA_COMPOSE_PROJECT_NAME"] = compose_project
                _apply_gamma_image_composition(release_composition, env)
                runtime_composition_source = "runtime-receipt"
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "exitCode": 2,
                "summary": f"stackctl down is GATE_BLOCK for {args.target}",
                "details": [
                    f"{args.target} teardown requires a canonical runtime receipt or service-package provenance",
                    str(exc),
                ],
            }
        _bind_gamma_down_parse_environment(env)
        if purge_rebuildable_state:
            cmd.append("--purge-rebuildable-state")
        runtime_result = run(cmd, env=env)
        if runtime_result.returncode == 0 and purge_rebuildable_state:
            shutil.rmtree(target_cache_dir(args.target), ignore_errors=True)
        app_cmd = [
            "bash",
            "quwoquan_app/scripts/device/stop_app_instance.sh",
            "--env",
            env_name,
            "--quiet",
        ]
        app_result = run(app_cmd)
        cmd = [*cmd, "&&", *app_cmd]
        result = next(
            (
                candidate
                for candidate in (runtime_result, app_result)
                if candidate.returncode != 0
            ),
            runtime_result,
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

    resource_release_issues: list[str] = []
    startup_receipt: dict[str, Any] | None = None
    if result.returncode == 0:
        occupied = _wait_for_network_ports_released(args.target)
        resource_release_issues = [
            f"canonical port remains occupied after down: {item['name']}:{item['port']}"
            for item in occupied
        ]
        if resource_release_issues:
            result = subprocess.CompletedProcess(
                result.args,
                2,
                stdout=result.stdout,
                stderr="\n".join(resource_release_issues),
            )
    if result.returncode == 0 and args.target in {
        "alpha-local",
        "beta-local",
        "gamma-local",
    }:
        try:
            current_attempt = load_startup_attempt(args.target)
            if current_attempt and current_attempt.get("status") != "stopped":
                startup_receipt = transition_startup_attempt(
                    env=env_name,
                    target=args.target,
                    attempt_id=str(current_attempt.get("attemptId") or ""),
                    status="stopped",
                    failure="",
                    cleanup_failure="",
                )
            else:
                startup_receipt = current_attempt
        except ValueError as exc:
            resource_release_issues.append(
                f"startup attempt stopped receipt failed: {exc}"
            )
            result = subprocess.CompletedProcess(
                result.args,
                2,
                stdout=result.stdout,
                stderr="\n".join(resource_release_issues),
            )

    write_json(
        report_dir / "report.json",
        {
            "command": "down",
            "target": args.target,
            "argv": cmd,
            "exitCode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "formalRelease": formal_release,
            "releaseComposition": release_composition,
            "runtimeMode": "immutable-oci" if formal_release else (
                "immutable-local" if release_composition else ""
            ),
            "runtimeCompositionSource": runtime_composition_source,
            "destructiveRepairPerformed": (
                purge_rebuildable_state and result.returncode == 0
            ),
            "destructiveActions": (
                [
                    f"purge-compose-volumes:{runtime_compose_project}",
                    f"purge-target-cache:{args.target}",
                ]
                if purge_rebuildable_state and result.returncode == 0
                else []
            ),
            "resourceReleaseIssues": resource_release_issues,
            "startupAttempt": startup_receipt,
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
    """Return the health scope promised by the canonical current startup attempt.

    Bounded content stacks intentionally do not start the full Assistant and
    external Provider planes. The target-scoped transactional startup receipt
    is the sole authority; missing, stopped or drifted identity fails closed to
    full scope and never consults retired environment state.
    """
    if target_name not in {"alpha-local", "beta-local", "gamma-local"}:
        return "full"
    try:
        startup_attempt = load_startup_attempt(target_name)
    except ValueError:
        return "full"
    expected_environment = target_name.removesuffix("-local")
    if (
        not isinstance(startup_attempt, dict)
        or startup_attempt.get("status") != "running"
        or startup_attempt.get("target") != target_name
        or startup_attempt.get("env") != expected_environment
        or not str(startup_attempt.get("composeProject") or "").strip()
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(startup_attempt.get("configurationDigest") or ""),
        )
        is None
        or re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(startup_attempt.get("imageTransportTag") or ""),
        )
        is None
    ):
        return "full"
    workload = str(startup_attempt.get("workload") or "").strip()
    if workload == "content-release":
        return "content-consumer"
    if workload == "content-commercial":
        return "content-commercial"
    return "full"


def command_data_execution_fleet(args: argparse.Namespace) -> dict[str, Any]:
    endpoint = resolve_data_execution_fleet_endpoint()
    action = str(getattr(args, "action", "resolve") or "resolve")
    if action == "resolve":
        return {
            "exitCode": 0,
            "summary": "stackctl data execution fleet resolved",
            "details": [f"target={endpoint.target}"],
            "fleet": endpoint.document(),
        }
    report_dir = artifact_run_dir(
        "repo",
        f"data-execution-fleet-{action}",
        target=endpoint.target,
    )
    try:
        runtime = manage_data_execution_fleet(action, endpoint)
        exit_code = 0 if action == "down" or runtime.ready else 1
        evidence = runtime.document()
        details = list(runtime.details)
        if not details:
            details = [
                f"mongo={runtime.mongo} redis={runtime.redis} owned={runtime.owned}"
            ]
    except (OSError, RuntimeError, ValueError) as exc:
        exit_code = 2
        evidence = {"action": action, "target": endpoint.target, "ready": False}
        details = [str(exc)]
    write_json(
        report_dir / "report.json",
        {
            "command": "data-execution-fleet",
            "status": "passed" if exit_code == 0 else "gate_block",
            "fleet": endpoint.document(),
            "evidence": evidence,
            "details": details,
        },
    )
    return {
        "exitCode": exit_code,
        "summary": f"stackctl data execution fleet {action}",
        "details": details,
        "fleet": endpoint.document(),
        "evidence": evidence,
        "reportDir": relpath(report_dir),
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    scope = _current_runtime_health_scope(args.target)
    health_args = argparse.Namespace(
        command="health",
        target=args.target,
        scope=scope,
        read_only=True,
        output_format=getattr(args, "output_format", "text"),
        report_dir=str(resolve_report_dir(args, str(get_target(load_environment_topology(), args.target)["env"]), args.target)),
    )
    result = command_health(health_args)
    candidate_workspace = _candidate_workspace_report(args.target)
    report_path = Path(health_args.report_dir) / "report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if isinstance(report, dict):
            report["candidateWorkspace"] = candidate_workspace
            write_json(report_path, report)
    except (OSError, json.JSONDecodeError):
        # status 的健康结果仍由 command_health 拥有；候选漂移是只读附加信息，
        # 报告文件异常不能被包装成新的运行时健康结论。
        pass
    result["candidateWorkspace"] = candidate_workspace
    return result


def command_health(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _start_timing()
    if not hasattr(args, "scope"):
        args.scope = _current_runtime_health_scope(args.target)
    workload = str(getattr(args, "workload", "") or "").strip() or None
    checks = _health_checks_for_target(
        topology,
        args.target,
        args.scope,
        workload=workload,
    )
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
    read_only = bool(getattr(args, "read_only", False))
    deadline_epoch = int(getattr(args, "deadline_epoch", 0) or 0)
    if deadline_epoch > 0:
        retry_attempts = 1
        retry_sleep_seconds = 0.0

    def probe_http_check(item: dict[str, Any]) -> dict[str, Any]:
        if item.get("skip"):
            return {
                "name": item["name"],
                "scope": item["scope"],
                "url": item["url"],
                "ok": True,
                "statusCode": None,
                "bodyPreview": str(item.get("reason", "skipped")),
                "skipped": True,
            }
        try:
            effective_timeout = (
                min(
                    timeout_seconds,
                    _remaining_deadline_seconds(
                        deadline_epoch, "health verification"
                    ),
                )
                if deadline_epoch > 0
                else timeout_seconds
            )
        except RuntimeError as error:
            ok, status_code, body, content_type = False, None, str(error), ""
        else:
            ok, status_code, body, content_type = fetch_url(
                item["url"],
                timeout=max(0.05, effective_timeout),
                retry_attempts=retry_attempts,
                retry_sleep_seconds=retry_sleep_seconds,
                headers=item.get("headers"),
                ca_file=str(item.get("caFile") or ""),
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
        return {
            "name": item["name"],
            "scope": item["scope"],
            "url": item["url"],
            "ok": ok,
            "statusCode": status_code,
            "contentType": content_type,
            "bodyPreview": body,
            "skipped": False,
        }

    probe_concurrency = min(16, len(checks))
    if probe_concurrency:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=probe_concurrency,
            thread_name_prefix="stackctl-health",
        ) as executor:
            statuses = list(executor.map(probe_http_check, checks))
    for status in statuses:
        if not status["ok"]:
            findings.append(
                f"{status['scope']}/{status['name']} failed: "
                f"{status['statusCode'] or 'ERR'} {status['url']}"
            )
        if not status["skipped"]:
            stdout_sections.append(
                (
                    status["name"],
                    f"{status['statusCode'] or 'ERR'} {status['url']}\n"
                    f"{status['bodyPreview']}",
                )
            )
    api_prerequisite = next(
        (
            item
            for item in statuses
            if item.get("scope") == "edge" and item.get("name") == "api-health"
        ),
        None,
    )
    if not read_only and api_prerequisite is not None and not api_prerequisite["ok"]:
        blocked = "integration-readonly blocked by failed edge/api-health prerequisite"
        statuses.append(
            {
                "name": "integration-readonly",
                "scope": args.scope,
                "type": "script",
                "argv": [],
                "ok": False,
                "statusCode": None,
                "bodyPreview": blocked,
                "skipped": True,
                "reportPath": "",
            }
        )
        stdout_sections.append(("integration-readonly", blocked))
        findings.append(blocked)
    elif not read_only:
        try:
            script_statuses, script_stdout_sections, script_findings = _script_probes_for_target(
                topology,
                args.target,
                args.scope,
                report_dir,
                require_non_empty_content_feed=bool(
                    getattr(args, "require_non_empty_content_feed", False)
                ),
                deadline_epoch=deadline_epoch,
            )
        except RuntimeError as error:
            script_statuses = [
                {
                    "name": "integration-readonly",
                    "scope": args.scope,
                    "type": "script",
                    "argv": [],
                    "ok": False,
                    "statusCode": 124,
                    "bodyPreview": str(error),
                    "skipped": False,
                    "reportPath": "",
                }
            ]
            script_stdout_sections = [("integration-readonly", str(error))]
            script_findings = [str(error)]
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
        "httpProbeConcurrency": probe_concurrency,
        "checks": statuses,
        "findings": findings,
        "timestamp": utc_now(),
        "scriptProbes": _script_probe_plan_for_target(topology, args.target),
        "readOnly": read_only,
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


def command_prod_hosted_plan(args: argparse.Namespace) -> dict[str, Any]:
    started_monotonic, started_at = _start_timing()
    argv = [
        "python3",
        "quwoquan_ops/cli/prod/prod_hosted_topology.py",
        "--instance",
        args.deployment_instance,
    ]
    for plane in args.plane or []:
        argv.extend(["--plane", plane])
    for host_id in args.host_id or []:
        argv.extend(["--host-id", host_id])
    if args.ssh_host:
        argv.extend(["--ssh-host", args.ssh_host])
    result = run(argv)
    timing = _finish_timing(started_monotonic, started_at)
    if result.returncode != 0:
        return {
            "exitCode": result.returncode,
            "summary": "stackctl prod-hosted plan blocked",
            "details": [result.stderr.strip() or result.stdout.strip()],
            **timing,
        }
    try:
        plan = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "exitCode": 2,
            "summary": "stackctl prod-hosted plan returned invalid JSON",
            "details": [result.stdout],
            **timing,
        }
    return {
        "exitCode": 0,
        "summary": (
            "stackctl prod-hosted plan resolved "
            f"{plan.get('replicaCount', 0)} plane replicas"
        ),
        "details": [
            f"instance={plan.get('instance')}",
            f"hosts={','.join(plan.get('hosts') or [])}",
        ],
        "deploymentPlan": plan,
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
    candidate_workspace = (
        _candidate_workspace_report(args.target)
        if "config" in scopes or "data" in scopes
        else None
    )
    if "network" in scopes:
        inspection["network"] = _network_report(args.target)
    if "config" in scopes:
        inspection["config"] = {
            "target": target,
            "portProfile": target.get("portProfile"),
            "publicBases": target.get("publicBases", {}),
            "origins": target.get("origins", {}),
            "candidateWorkspace": candidate_workspace,
            "releaseState": (
                _load_release_state(PROD_RELEASE_UNIT)
                if args.target == "prod-hosted"
                else {}
            ),
        }
        if args.target == "prod-hosted":
            runtimes = _prod_instance_runtime_reports(
                report_dir,
                instance=str(getattr(args, "deployment_instance", "prod") or "prod"),
                host=str(getattr(args, "ssh_host", "") or ""),
                host_id=str(getattr(args, "host_id", "") or ""),
            )
            inspection["config"]["rootlessRuntimeReplicas"] = runtimes
            for runtime in runtimes:
                plane = str(runtime.get("plane") or "unknown")
                findings.extend(_prod_plane_runtime_findings(runtime, plane=plane))
            service_runtimes = [
                runtime for runtime in runtimes if runtime.get("plane") == "service"
            ]
            edge_runtimes = [
                runtime for runtime in runtimes if runtime.get("plane") == "edge"
            ]
            if len(service_runtimes) == 1:
                inspection["config"]["rootlessRuntime"] = service_runtimes[0]
            if len(edge_runtimes) == 1:
                inspection["config"]["edgeRootlessRuntime"] = edge_runtimes[0]
        if "data" not in scopes and candidate_workspace is not None:
            findings.extend(
                f"candidate workspace: {issue}"
                for issue in candidate_workspace.get("issues", [])
            )
    if "logs" in scopes:
        inspection["logs"] = _local_log_report(args.target)
    if "data" in scopes:
        inspection["data"] = _data_report(
            args.target,
            candidate_workspace=candidate_workspace,
        )
        findings.extend(
            f"data: {issue}" for issue in inspection["data"].get("issues", [])
        )
    if "metrics" in scopes:
        inspection["metrics"] = _metrics_report(topology, args.target)
    if "security" in scopes:
        security = _security_report(topology, args.target)
        if args.target in {"alpha-local", "beta-local", "gamma-local"}:
            try:
                tls = verify_certificate(args.target)
                security["publicTls"] = {
                    key: value
                    for key, value in tls.items()
                    if key not in {"certificate", "privateKey"}
                }
            except PublicDomainTlsError as error:
                detail = str(error)
                security["publicTls"] = {
                    "status": ProbeOutcome.GATE_BLOCK.value,
                    "issues": [detail],
                }
                findings.append(f"public TLS: {detail}")
        inspection["security"] = security
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
    if args.target in {"alpha-local", "beta-local", "gamma-local"}:
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
            elif not all(
                state.get(field)
                for field in (
                    "to_candidate_digest",
                    "to_release_evidence_ref",
                    "to_image_transport_tag",
                )
            ):
                findings.append(
                    "prod release-state missing canonical candidate authority metadata"
                )
            runtimes = _prod_instance_runtime_reports(
                report_dir,
                instance=str(getattr(args, "deployment_instance", "prod") or "prod"),
                host=str(getattr(args, "ssh_host", "") or ""),
                host_id=str(getattr(args, "host_id", "") or ""),
            )
            for runtime in runtimes:
                findings.extend(
                    _prod_plane_runtime_findings(
                        runtime,
                        plane=str(runtime.get("plane") or "unknown"),
                    )
                )
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
        token_value = ""
        ssl_cafile = ""
        if args.target in LOCAL_FILTER_CATALOG_TARGETS:
            from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

            ssl_cafile = str(root_certificate_path(args.target))
        if (
            args.target in LOCAL_FILTER_CATALOG_TARGETS
            and args.action in FILTER_CATALOG_MUTATING_ACTIONS
        ):
            token_value = mint_local_filter_catalog_service_token(
                environment,
                args.target,
            )
        execution = execute_filter_catalog_command(
            repo_root=ROOT,
            target_name=args.target,
            environment=environment,
            api_base_url=api_base_url,
            action=args.action,
            rollback_release_id=args.rollback_release_id,
            token_env=args.token_env,
            prod_gray_activation=bool(args.prod_gray_activation),
            token_value=token_value,
            ssl_cafile=ssl_cafile,
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


def command_premium_pool(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    environment = str(target["env"])
    public_bases = target.get("publicBases") or {}
    api_base_url = str(public_bases.get("api") or "").strip()
    product_ops_base_url = str(public_bases.get("productOps") or "").strip()
    report_dir = resolve_report_dir(args, environment, args.target)
    started_monotonic, started_at = _start_timing()
    receipt: dict[str, Any] = {}
    try:
        if not api_base_url:
            raise PremiumPoolReleaseError("target topology lacks API public base")
        binding = load_premium_pool_candidate_binding(
            environment=environment,
            target=args.target,
            readiness_receipt=args.readiness_receipt,
            content_id=args.content_id,
        )
        from quwoquan_ops.cli.lib.public_domain_tls import root_certificate_path

        ssl_cafile = str(root_certificate_path(args.target))
        if str(args.action) == "verify-readback":
            receipt = execute_premium_pool_readback(
                binding=binding,
                api_base_url=api_base_url,
                ssl_cafile=ssl_cafile,
                projection_deadline_seconds=float(
                    args.projection_deadline_seconds
                ),
            )
        elif str(args.action) == "upsert-and-verify":
            if not product_ops_base_url:
                raise PremiumPoolReleaseError(
                    "target topology lacks Product Ops public base"
                )
            if args.quality_score is None or not str(args.expires_at or "").strip():
                raise PremiumPoolReleaseError(
                    "upsert-and-verify requires qualityScore and expiresAt"
                )
            session, operator_kind = open_premium_pool_operator_session(
                environment=environment,
                target=args.target,
            )
            receipt = execute_premium_pool_upsert(
                binding=binding,
                product_ops_base_url=product_ops_base_url,
                api_base_url=api_base_url,
                session=session,
                operator_kind=operator_kind,
                quality_score=float(args.quality_score),
                expires_at=str(args.expires_at),
                ssl_cafile=ssl_cafile,
                projection_deadline_seconds=float(
                    args.projection_deadline_seconds
                ),
            )
        else:
            raise PremiumPoolReleaseError("unsupported premium pool action")
        status = "ok"
        exit_code = 0
        details = [
            f"release={binding.release_id}",
            f"importRunId={binding.import_run_id}",
            f"contentId={binding.content_id}",
            f"baselineId={binding.baseline_id}",
        ]
    except (OSError, ValueError, PremiumPoolReleaseError) as exc:
        status = "gate_block"
        exit_code = 2
        details = [str(exc)]
    timing = _finish_timing(started_monotonic, started_at)
    write_json(
        report_dir / "report.json",
        {
            "command": "premium-pool",
            "target": args.target,
            "action": args.action,
            "status": status,
            "receipt": receipt,
            "details": details,
            **timing,
        },
    )
    summary = (
        f"stackctl premium-pool passed for {args.target}"
        if exit_code == 0
        else f"stackctl premium-pool is GATE_BLOCK for {args.target}"
    )
    _write_summary_bundle(
        report_dir,
        command="premium-pool",
        target=args.target,
        status=status,
        summary=summary,
        details=details,
        timing=timing,
    )
    return {
        "exitCode": exit_code,
        "summary": summary,
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


_DATA_READINESS_SCHEMA = "quwoquan_data.environment_release_readiness"
_DATA_LIFECYCLE_EXIT_SCHEMA = "quwoquan_data.environment_release_lifecycle_exit"
_DATA_READINESS_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DATA_CONSUMER_READINESS_QUERY_NAMES = frozenset(
    {
        "discovery_work",
        "typed_article",
        "typed_image",
        "typed_video",
        "homepage_recommend",
    }
)
_DATA_COMMERCIAL_READINESS_QUERY_NAMES = frozenset(
    {*_DATA_CONSUMER_READINESS_QUERY_NAMES, "premium_stream"}
)


def _data_readiness_segment(value: str, *, label: str) -> str:
    segment = str(value or "").strip()
    candidate = Path(segment)
    if (
        not segment
        or segment in {".", ".."}
        or candidate.is_absolute()
        or len(candidate.parts) != 1
        or "/" in segment
        or "\\" in segment
    ):
        raise ValueError(f"{label} must be one non-empty path segment")
    return segment


def _data_release_readiness_path(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
) -> Path:
    release_segment = _data_readiness_segment(release_id, label="releaseId")
    verify_segment = _data_readiness_segment(verify_run_id, label="verifyRunId")
    return (
        env_runs_root(environment)
        / "data-release"
        / release_segment
        / verify_segment
        / "release-readiness.json"
    )


def _data_readiness_path_from_verify_args(
    args: argparse.Namespace,
    *,
    environment: str,
    profile: VerificationProfile,
) -> Path | None:
    if profile is not VerificationProfile.RELEASE:
        return None
    release_id = str(getattr(args, "data_release_id", "") or "").strip()
    verify_run_id = str(getattr(args, "data_verify_run_id", "") or "").strip()
    manifest_digest = str(
        getattr(args, "data_manifest_digest", "") or ""
    ).strip()
    if not release_id or not verify_run_id or not manifest_digest:
        return None
    return _data_release_readiness_path(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
    )


def _canonical_document_checksum(document: dict[str, Any]) -> str:
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _validate_data_operation_evidence(
    value: object,
    *,
    label: str,
    expected_path: str,
    expected_page_id: str,
    expected_status: int,
    issues: list[str],
) -> tuple[str, str]:
    required = {
        "path",
        "pageId",
        "status",
        "requestId",
        "traceId",
        "startedAt",
        "endedAt",
        "durationMs",
    }
    if not isinstance(value, dict):
        issues.append(f"Data readiness {label} must be an object")
        return "", ""
    if set(value) != required:
        issues.append(
            f"Data readiness {label} must contain only canonical operation evidence"
        )
    if value.get("path") != expected_path:
        issues.append(f"Data readiness {label}.path is not canonical")
    if value.get("pageId") != expected_page_id:
        issues.append(f"Data readiness {label}.pageId is not canonical")
    if value.get("status") != expected_status:
        issues.append(f"Data readiness {label}.status must be {expected_status}")
    request_id = str(value.get("requestId") or "").strip()
    trace_id = str(value.get("traceId") or "").strip()
    started_at = str(value.get("startedAt") or "").strip()
    ended_at = str(value.get("endedAt") or "").strip()
    duration_ms = value.get("durationMs")
    if not request_id or not trace_id:
        issues.append(f"Data readiness {label} lacks requestId/traceId")
    if not started_at or not ended_at or ended_at < started_at:
        issues.append(f"Data readiness {label} timing is invalid")
    if (
        not isinstance(duration_ms, int)
        or isinstance(duration_ms, bool)
        or duration_ms < 0
    ):
        issues.append(f"Data readiness {label}.durationMs is invalid")
    return request_id, trace_id


def _validated_string_set(
    value: object,
    *,
    label: str,
    issues: list[str],
) -> set[str]:
    if not isinstance(value, list):
        issues.append(f"Data readiness {label} must be an array")
        return set()
    items = [str(item).strip() for item in value]
    if not items or any(not item for item in items) or len(items) != len(set(items)):
        issues.append(
            f"Data readiness {label} must contain unique non-empty strings"
        )
        return set(items)
    return set(items)


def _load_data_release_readiness(
    *,
    environment: str,
    release_id: str,
    verify_run_id: str,
    manifest_digest: str,
    readiness_phase: ReadinessPhase,
) -> tuple[dict[str, Any], Path]:
    """Load and fail-closed validate the single Data-owned environment receipt."""

    if _DATA_READINESS_DIGEST_RE.fullmatch(str(manifest_digest or "").strip()) is None:
        raise ValueError("manifestDigest must use canonical sha256:<64 lowercase hex>")
    receipt_path = _data_release_readiness_path(
        environment=environment,
        release_id=release_id,
        verify_run_id=verify_run_id,
    )
    try:
        raw = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(
            f"canonical Data readiness receipt is missing: {relpath(receipt_path)}"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"canonical Data readiness receipt is unreadable: {relpath(receipt_path)}"
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError("canonical Data readiness receipt must be a JSON object")
    receipt = dict(raw)
    issues: list[str] = []
    expected_values = {
        "schema": _DATA_READINESS_SCHEMA,
        "environment": environment,
        "releaseId": release_id,
        "releaseKind": "content",
        "sourceOwner": "qwq_data",
        "readinessPhase": readiness_phase.value,
        "manifestDigest": manifest_digest,
        "verifyRunId": verify_run_id,
        "passed": True,
    }
    for key, expected in expected_values.items():
        if receipt.get(key) != expected:
            issues.append(
                f"Data readiness {key}={receipt.get(key)!r}, expected {expected!r}"
            )
    expected_release_class = (
        readiness_phase.value
        if readiness_phase in {ReadinessPhase.RESEARCH, ReadinessPhase.COMMERCIAL}
        else str(receipt.get("releaseClass") or "")
    )
    if (
        receipt.get("releaseClass") != expected_release_class
        or receipt.get("productLifecycleState") != expected_release_class
    ):
        issues.append(
            "Data readiness releaseClass/productLifecycleState drift from phase"
        )
    authorization_required_ids = receipt.get("authorizationRequiredAssetIds")
    contains_unverified = receipt.get("containsUnverifiedAssets")
    if (
        not isinstance(authorization_required_ids, list)
        or any(not str(item).strip() for item in authorization_required_ids)
        or len(authorization_required_ids) != len(set(authorization_required_ids))
        or not isinstance(contains_unverified, bool)
        or contains_unverified != bool(authorization_required_ids)
    ):
        issues.append("Data readiness authorization-required asset summary is invalid")
    rights_status_counts = receipt.get("rightsStatusCounts")
    if (
        not isinstance(rights_status_counts, dict)
        or set(rights_status_counts) != {"verified", "unverified", "restricted", "unknown"}
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in rights_status_counts.values()
        )
    ):
        issues.append("Data readiness rightsStatusCounts is invalid")
    if readiness_phase is ReadinessPhase.COMMERCIAL and (
        contains_unverified is not False or authorization_required_ids != []
    ):
        issues.append("commercial readiness contains authorization-required assets")
    for digest_key in ("manifestDigest", "mediaManifestDigest"):
        if _DATA_READINESS_DIGEST_RE.fullmatch(str(receipt.get(digest_key) or "")) is None:
            issues.append(f"Data readiness {digest_key} is not a canonical digest")
    if not str(receipt.get("importRunId") or "").strip():
        issues.append("Data readiness importRunId is missing")
    if _DATA_READINESS_DIGEST_RE.fullmatch(
        str(receipt.get("guestActorHash") or "")
    ) is None:
        issues.append("Data readiness guestActorHash is not a canonical digest")
    observed_request_ids: set[str] = set()
    observed_trace_ids: set[str] = set()
    request_id, trace_id = _validate_data_operation_evidence(
        receipt.get("guestLogin"),
        label="guestLogin",
        expected_path="/auth/login/anonymous",
        expected_page_id="user.login.anonymous",
        expected_status=200,
        issues=issues,
    )
    if request_id:
        observed_request_ids.add(request_id)
    if trace_id:
        observed_trace_ids.add(trace_id)

    declared_checksum = str(receipt.get("verificationChecksum") or "")
    checksum_document = dict(receipt)
    checksum_document.pop("verificationChecksum", None)
    actual_checksum = _canonical_document_checksum(checksum_document)
    if declared_checksum != actual_checksum:
        issues.append("Data readiness verificationChecksum does not match the receipt")

    collections = {
        "entities": _validated_string_set(
            receipt.get("entityRefs"), label="entityRefs", issues=issues
        ),
        "posts": _validated_string_set(
            receipt.get("postIds"), label="postIds", issues=issues
        ),
        "creators": _validated_string_set(
            receipt.get("creatorIds"), label="creatorIds", issues=issues
        ),
        "tags": _validated_string_set(
            receipt.get("tagRefs"), label="tagRefs", issues=issues
        ),
        "mediaAssets": _validated_string_set(
            receipt.get("mediaAssetIds"), label="mediaAssetIds", issues=issues
        ),
    }
    counts = receipt.get("counts")
    if not isinstance(counts, dict):
        issues.append("Data readiness counts must be an object")
        counts = {}
    for count_name, identifiers in collections.items():
        count = counts.get(count_name)
        if not isinstance(count, int) or isinstance(count, bool) or count != len(identifiers):
            issues.append(
                f"Data readiness counts.{count_name} must equal {len(identifiers)}"
            )
    avatar_count = counts.get("avatarAssets")
    if (
        not isinstance(avatar_count, int)
        or isinstance(avatar_count, bool)
        or avatar_count != len(collections["creators"])
    ):
        issues.append(
            "Data readiness counts.avatarAssets must equal release-bound creators"
        )
    image_count = counts.get("imageAssets")
    if (
        not isinstance(image_count, int)
        or isinstance(image_count, bool)
        or image_count < 1
        or image_count > len(collections["mediaAssets"])
    ):
        issues.append(
            "Data readiness counts.imageAssets must be non-zero and release-bound"
        )

    queries = receipt.get("feedQueries")
    queries_by_name: dict[str, dict[str, Any]] = {}
    if not isinstance(queries, list):
        issues.append("Data readiness feedQueries must be an array")
        queries = []
    for index, item in enumerate(queries):
        if not isinstance(item, dict):
            issues.append(f"Data readiness feedQueries[{index}] must be an object")
            continue
        name = str(item.get("name") or "")
        if not name or name in queries_by_name:
            issues.append(f"Data readiness feed query name is empty or duplicated: {name!r}")
            continue
        queries_by_name[name] = item
        matched = _validated_string_set(
            item.get("matchedPostIds"),
            label=f"feedQueries.{name}.matchedPostIds",
            issues=issues,
        )
        if not matched.issubset(collections["posts"]):
            issues.append(f"Data readiness feed query {name} is not release-bound")
        if (
            item.get("path") != "/content/feed"
            or item.get("status") != 200
            or item.get("releaseBound") is not True
        ):
            issues.append(f"Data readiness feed query {name} lacks canonical 200 binding")
        requests = item.get("requests")
        if not isinstance(requests, list) or not requests:
            issues.append(f"Data readiness feed query {name} lacks request evidence")
            continue
        for request_index, request_evidence in enumerate(requests):
            request_id, trace_id = _validate_data_operation_evidence(
                request_evidence,
                label=f"feedQueries.{name}.requests[{request_index}]",
                expected_path="/content/feed",
                expected_page_id="content.feed.list",
                expected_status=200,
                issues=issues,
            )
            if request_id in observed_request_ids:
                issues.append(
                    f"Data readiness feed query {name} reuses requestId {request_id!r}"
                )
            elif request_id:
                observed_request_ids.add(request_id)
            if trace_id in observed_trace_ids:
                issues.append(
                    f"Data readiness feed query {name} reuses traceId {trace_id!r}"
                )
            elif trace_id:
                observed_trace_ids.add(trace_id)
    expected_query_names = (
        _DATA_COMMERCIAL_READINESS_QUERY_NAMES
        if readiness_phase in {ReadinessPhase.RESEARCH, ReadinessPhase.COMMERCIAL}
        else _DATA_CONSUMER_READINESS_QUERY_NAMES
    )
    if set(queries_by_name) != expected_query_names:
        issues.append(
            "Data readiness feedQueries do not match the declared readiness phase"
        )
    expected_query_patterns = {
        "discovery_work": r"^identity=work&limit=[1-9][0-9]*$",
        "typed_video": r"^identity=work&type=video&limit=[1-9][0-9]*$",
        "homepage_recommend": (
            r"^sort=recommend&channelId=recommend&limit=[1-9][0-9]*$"
        ),
    }
    if readiness_phase in {ReadinessPhase.RESEARCH, ReadinessPhase.COMMERCIAL}:
        expected_query_patterns["premium_stream"] = (
            r"^sort=recommend&channelId=premium_stream&limit=[1-9][0-9]*$"
        )
    for name, pattern in expected_query_patterns.items():
        query = str(queries_by_name.get(name, {}).get("query") or "")
        if re.fullmatch(pattern, query) is None:
            issues.append(f"Data readiness {name} exact query is not canonical")
    discovery_ids = set(
        queries_by_name.get("discovery_work", {}).get("matchedPostIds") or []
    )
    video_ids = set(queries_by_name.get("typed_video", {}).get("matchedPostIds") or [])
    premium_ids = set(
        queries_by_name.get("premium_stream", {}).get("matchedPostIds") or []
    )
    premium_video_ids = premium_ids & video_ids
    if not discovery_ids:
        issues.append("Data readiness discovery exact query is empty")
    if not video_ids:
        issues.append("Data readiness video-book exact query is empty")
    if readiness_phase in {ReadinessPhase.RESEARCH, ReadinessPhase.COMMERCIAL} and not premium_video_ids:
        issues.append("Data readiness premium_stream has no release-bound playable video")
    for count_name, expected_count in (("discoveryPosts", len(discovery_ids)),):
        value = counts.get(count_name)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 1
            or value != expected_count
        ):
            issues.append(
                f"Data readiness counts.{count_name} must equal {expected_count} and be non-zero"
            )
    premium_count = counts.get("premiumPlayableVideos")
    if (
        not isinstance(premium_count, int)
        or isinstance(premium_count, bool)
        or premium_count != len(premium_video_ids)
        or (
            readiness_phase in {ReadinessPhase.RESEARCH, ReadinessPhase.COMMERCIAL}
            and premium_count < 1
        )
    ):
        issues.append(
            "Data readiness counts.premiumPlayableVideos must match its readiness phase"
        )

    evidence_root = output_root().expanduser().resolve()
    expected_media_ref = (
        Path("data") / "releases" / release_id / "payload" / "media_manifest.json"
    ).as_posix()
    if receipt.get("mediaManifestRef") != expected_media_ref:
        issues.append("Data readiness mediaManifestRef is not the canonical release payload")
    evidence_refs = (
        "contentImportReportRef",
        "creatorAttributionRef",
        "tagAttributionRef",
        "homepageApiVerificationRef",
        "postApiVerificationRef",
        "mediaManifestRef",
    )
    resolved_evidence: dict[str, Path] = {}
    for key in evidence_refs:
        ref = str(receipt.get(key) or "").strip()
        candidate = (evidence_root / ref).resolve()
        try:
            candidate.relative_to(evidence_root)
        except ValueError:
            issues.append(f"Data readiness {key} escapes QWQ_OUTPUT_ROOT")
            continue
        if not ref or not candidate.is_file():
            issues.append(f"Data readiness {key} evidence is missing: {ref or '<empty>'}")
            continue
        resolved_evidence[key] = candidate
    media_path = resolved_evidence.get("mediaManifestRef")
    if media_path is not None:
        actual_media_digest = f"sha256:{hashlib.sha256(media_path.read_bytes()).hexdigest()}"
        if actual_media_digest != receipt.get("mediaManifestDigest"):
            issues.append("Data readiness mediaManifestDigest does not match payload bytes")
    post_verification_path = resolved_evidence.get("postApiVerificationRef")
    if post_verification_path is not None:
        try:
            post_verification = json.loads(
                post_verification_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            issues.append("Data readiness postApiVerificationRef is unreadable")
        else:
            if not isinstance(post_verification, dict):
                issues.append("Data readiness post API verification must be an object")
            elif (
                post_verification.get("guestActorHash")
                != receipt.get("guestActorHash")
                or post_verification.get("guestLogin") != receipt.get("guestLogin")
                or post_verification.get("feedQueries") != receipt.get("feedQueries")
            ):
                issues.append(
                    "Data readiness guest/feed operation evidence drifts from post verification"
                )
            else:
                creator_evidence = [
                    row
                    for row in post_verification.get("creators") or []
                    if isinstance(row, dict)
                ]
                creator_refs = {
                    str(row.get("creatorRef") or "").strip()
                    for row in creator_evidence
                }
                avatar_asset_ids = {
                    str(row.get("avatarAssetId") or "").strip()
                    for row in creator_evidence
                }
                if (
                    creator_refs != collections["creators"]
                    or len(avatar_asset_ids) != len(collections["creators"])
                    or "" in avatar_asset_ids
                    or any(
                        row.get("profileStatus") != 200
                        or row.get("avatarMediaReady") is not True
                        or row.get("avatarProbeCount") != 1
                        or not isinstance(row.get("avatarProbe"), dict)
                        or row["avatarProbe"].get("publicUrl")
                        != row.get("avatarUrl")
                        or row["avatarProbe"].get("status") != 200
                        or not str(row["avatarProbe"].get("mimeType") or "").startswith(
                            "image/"
                        )
                        or not isinstance(row["avatarProbe"].get("bytes"), int)
                        or row["avatarProbe"].get("bytes", 0) <= 0
                        or _DATA_READINESS_DIGEST_RE.fullmatch(
                            str(row["avatarProbe"].get("sha256") or "")
                        )
                        is None
                        or row["avatarProbe"].get("hashVerified") is not True
                        for row in creator_evidence
                    )
                ):
                    issues.append(
                        "Data readiness creator avatar evidence is not release-bound"
                    )
                image_asset_ids = {
                    str(probe.get("assetId") or "").strip()
                    for row in post_verification.get("posts") or []
                    if isinstance(row, dict)
                    for probe in row.get("mediaProbes") or []
                    if isinstance(probe, dict)
                    and probe.get("kind") == "image"
                    and probe.get("status") == 200
                    and str(probe.get("mimeType") or "").startswith("image/")
                    and probe.get("bytes") == probe.get("expectedBytes")
                    and probe.get("sha256") == probe.get("expectedSha256")
                    and probe.get("hashVerified") is True
                }
                if (
                    "" in image_asset_ids
                    or len(image_asset_ids) != image_count
                    or not image_asset_ids.issubset(collections["mediaAssets"])
                ):
                    issues.append(
                        "Data readiness image delivery evidence is not hash-bound"
                    )
                if any(
                    not isinstance(row, dict)
                    or not isinstance(row.get("mediaProbes"), list)
                    or row.get("mediaProbeCount")
                    != len(row.get("mediaProbes") or [])
                    for row in post_verification.get("posts") or []
                ):
                    issues.append(
                        "Data readiness mediaProbeCount drifts from typed probes"
                    )
    attestation_path = (
        evidence_root / "data" / "releases" / release_id / "attestations" / "release.json"
    )
    try:
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        issues.append(
            f"Data release attestation is missing or unreadable: {relpath(attestation_path)}"
        )
    else:
        if not isinstance(attestation, dict) or any(
            (
                attestation.get("releaseId") != release_id,
                attestation.get("sourceOwner") != "qwq_data",
                attestation.get("payloadSha256") != manifest_digest,
            )
        ):
            issues.append("Data release attestation does not bind the expected payload digest")

    if issues:
        raise ValueError("; ".join(issues))
    return receipt, receipt_path


def _load_data_release_lifecycle_exit(
    *,
    environment: str,
    release_id: str,
    manifest_digest: str,
    readiness: dict[str, Any],
    lifecycle_exit_ref: str,
) -> tuple[dict[str, Any], Path]:
    """Load the commercial-only rollback/replay proof and recompute its bindings."""

    ref = str(lifecycle_exit_ref or "").strip()
    if not ref:
        raise ValueError(
            "commercial readiness requires canonical data lifecycleExitRef"
        )
    relative = Path(ref)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("data lifecycleExitRef must stay below QWQ_OUTPUT_ROOT")
    expected_prefix = (
        "env",
        environment,
        "runs",
        "release-lifecycle-exit",
        release_id,
    )
    if (
        len(relative.parts) != 7
        or tuple(relative.parts[:5]) != expected_prefix
        or relative.parts[-1] != "lifecycle-exit.json"
    ):
        raise ValueError(
            "data lifecycleExitRef must bind environment/release/exitRunId"
        )
    exit_run_id = _data_readiness_segment(
        relative.parts[5],
        label="lifecycle exitRunId",
    )
    evidence_root = output_root().expanduser().resolve()
    path = (evidence_root / relative).resolve()
    try:
        path.relative_to(evidence_root)
    except ValueError as exc:
        raise ValueError("data lifecycleExitRef escapes QWQ_OUTPUT_ROOT") from exc
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"data lifecycle Exit receipt is missing: {ref}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"data lifecycle Exit receipt is unreadable: {ref}") from exc
    if not isinstance(raw, dict):
        raise ValueError("data lifecycle Exit receipt must be a JSON object")
    receipt = dict(raw)
    expected_keys = {
        "schema",
        "environment",
        "sourceOwner",
        "exitRunId",
        "originalReleaseId",
        "originalManifestDigest",
        "originalImportRunId",
        "originalVerifyRunId",
        "originalImportResultRef",
        "originalVerifyResultRef",
        "rollbackToReleaseId",
        "rollbackToManifestDigest",
        "rollbackRunId",
        "rollbackVerifyRunId",
        "rollbackResultRef",
        "rollbackVerifyResultRef",
        "replayImportRunId",
        "replayVerifyRunId",
        "replayManifestDigest",
        "replayImportResultRef",
        "replayVerifyResultRef",
        "recordedAt",
        "verificationChecksum",
        "passed",
    }
    issues: list[str] = []
    if set(receipt) != expected_keys:
        issues.append("data lifecycle Exit receipt fields drift from canonical schema")
    # Commercial verify may run on the post-lifecycle replayed import surface.
    # In that sequencing, readiness.importRunId equals replayImportRunId while
    # readiness.verifyRunId is the later commercial verify — not the lifecycle
    # original consumer verify. Keep the classic original* equality for the
    # pre-lifecycle commercial path.
    readiness_import = str(readiness.get("importRunId") or "").strip()
    readiness_verify = str(readiness.get("verifyRunId") or "").strip()
    readiness_phase = str(readiness.get("readinessPhase") or "").strip()
    replay_import = str(receipt.get("replayImportRunId") or "").strip()
    commercial_on_replay = (
        readiness_phase == ReadinessPhase.COMMERCIAL.value
        and readiness_import
        and readiness_import == replay_import
    )
    expected_values = {
        "schema": _DATA_LIFECYCLE_EXIT_SCHEMA,
        "environment": environment,
        "sourceOwner": "qwq_data",
        "exitRunId": exit_run_id,
        "originalReleaseId": release_id,
        "originalManifestDigest": manifest_digest,
        "replayManifestDigest": manifest_digest,
        "passed": True,
    }
    if commercial_on_replay:
        if not readiness_verify:
            issues.append(
                "commercial readiness on replay import requires a non-empty verifyRunId"
            )
    else:
        expected_values["originalImportRunId"] = readiness_import
        expected_values["originalVerifyRunId"] = readiness_verify
    for field, expected in expected_values.items():
        if receipt.get(field) != expected:
            issues.append(
                f"data lifecycle Exit {field}={receipt.get(field)!r}, expected {expected!r}"
            )
    rollback_release_id = str(receipt.get("rollbackToReleaseId") or "").strip()
    if not rollback_release_id or rollback_release_id == release_id:
        issues.append(
            "data lifecycle Exit rollbackToReleaseId must name another release"
        )
    for field in (
        "originalManifestDigest",
        "rollbackToManifestDigest",
        "replayManifestDigest",
    ):
        if _DATA_READINESS_DIGEST_RE.fullmatch(str(receipt.get(field) or "")) is None:
            issues.append(f"data lifecycle Exit {field} is not a canonical digest")
    declared_checksum = str(receipt.get("verificationChecksum") or "")
    unsigned = dict(receipt)
    unsigned.pop("verificationChecksum", None)
    if declared_checksum != _canonical_document_checksum(unsigned):
        issues.append("data lifecycle Exit verificationChecksum drift")

    run_ids = [
        str(receipt.get(field) or "").strip()
        for field in (
            "originalImportRunId",
            "originalVerifyRunId",
            "rollbackRunId",
            "rollbackVerifyRunId",
            "replayImportRunId",
            "replayVerifyRunId",
        )
    ]
    if any(not value for value in run_ids) or len(set(run_ids)) != len(run_ids):
        issues.append("data lifecycle Exit run IDs must be non-empty and distinct")

    def result_ref(bound_release_id: str, run_id_field: str) -> str:
        return (
            Path("env")
            / environment
            / "runs"
            / "data-release"
            / bound_release_id
            / str(receipt.get(run_id_field) or "")
            / "result.json"
        ).as_posix()

    expected_refs = {
        "originalImportResultRef": result_ref(release_id, "originalImportRunId"),
        "originalVerifyResultRef": result_ref(release_id, "originalVerifyRunId"),
        "rollbackResultRef": result_ref(rollback_release_id, "rollbackRunId"),
        "rollbackVerifyResultRef": result_ref(
            rollback_release_id,
            "rollbackVerifyRunId",
        ),
        "replayImportResultRef": result_ref(release_id, "replayImportRunId"),
        "replayVerifyResultRef": result_ref(release_id, "replayVerifyRunId"),
    }
    for field, expected in expected_refs.items():
        if receipt.get(field) != expected:
            issues.append(f"data lifecycle Exit {field} is not canonical")
            continue
        if not (evidence_root / expected).is_file():
            issues.append(f"data lifecycle Exit evidence is missing: {expected}")

    for bound_release_id, digest in (
        (release_id, manifest_digest),
        (rollback_release_id, str(receipt.get("rollbackToManifestDigest") or "")),
    ):
        attestation_path = (
            evidence_root
            / "data"
            / "releases"
            / bound_release_id
            / "attestations"
            / "release.json"
        )
        try:
            attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            issues.append(
                "data lifecycle Exit release attestation is missing or unreadable: "
                + relpath(attestation_path)
            )
            continue
        if (
            not isinstance(attestation, dict)
            or attestation.get("releaseId") != bound_release_id
            or attestation.get("sourceOwner") != "qwq_data"
            or attestation.get("payloadSha256") != digest
        ):
            issues.append(
                f"data lifecycle Exit attestation drift for {bound_release_id}"
            )
    if issues:
        raise ValueError("; ".join(issues))
    return receipt, path


def _run_release_video_delivery_probe(
    *,
    target: str,
    readiness_path: Path,
    report_dir: Path,
) -> tuple[dict[str, Any], Path]:
    """Prove release-bound HTTPS bytes, Range 206, duration and first frame."""

    report_path = report_dir / "report.json"
    # Local gamma/alpha/beta serve media with the stackctl-managed root CA.
    # System trust alone fails self-signed chains; bind SSL_CERT_FILE so
    # urllib/ffprobe use the same public-domain trust as host probes.
    probe_env = dict(os.environ)
    if target in {"alpha-local", "beta-local", "gamma-local"}:
        try:
            probe_env["SSL_CERT_FILE"] = str(root_certificate_path(target))
            probe_env["REQUESTS_CA_BUNDLE"] = probe_env["SSL_CERT_FILE"]
            probe_env["CURL_CA_BUNDLE"] = probe_env["SSL_CERT_FILE"]
        except PublicDomainTlsError as exc:
            raise ValueError(
                f"release video delivery probe missing local root CA: {exc}"
            ) from exc
    result = run(
        [
            "python3",
            "quwoquan_ops/cli/smoke/verify_video_playback_canary.py",
            "--target",
            target,
            "--release-readiness",
            str(readiness_path),
            "--report",
            str(report_path),
        ],
        env=probe_env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(
            "release video delivery probe failed: "
            + (detail[:800] if detail else f"exit={result.returncode}")
        )
    evidence = _read_json_object(str(report_path))
    if (
        evidence.get("schema") != "quwoquan_ops.release_video_delivery_evidence"
        or evidence.get("status") != "passed"
    ):
        raise ValueError("release video delivery probe did not emit a passed typed report")
    return evidence, report_path


def _release_feed_post_expectations(
    receipt: dict[str, Any],
    *,
    readiness_phase: ReadinessPhase,
) -> dict[str, set[str]]:
    """Return the immutable-release post IDs each live exact query must expose."""

    queries = {
        str(item.get("name") or ""): item
        for item in receipt.get("feedQueries") or []
        if isinstance(item, dict)
    }
    discovery_ids = {
        str(item).strip()
        for item in queries.get("discovery_work", {}).get("matchedPostIds") or []
        if str(item).strip()
    }
    video_ids = {
        str(item).strip()
        for item in queries.get("typed_video", {}).get("matchedPostIds") or []
        if str(item).strip()
    }
    premium_ids = {
        str(item).strip()
        for item in queries.get("premium_stream", {}).get("matchedPostIds") or []
        if str(item).strip()
    }
    premium_video_ids = premium_ids.intersection(video_ids)
    expectations = {
        "content_feed": discovery_ids,
        "video_book_feed": video_ids,
    }
    if readiness_phase in {ReadinessPhase.RESEARCH, ReadinessPhase.COMMERCIAL}:
        expectations["premium_feed"] = premium_video_ids
    empty = sorted(name for name, post_ids in expectations.items() if not post_ids)
    if empty:
        raise ValueError(
            "canonical Data readiness has no release-bound expectation for: "
            + ", ".join(empty)
        )
    return expectations


def _run_release_feed_readback_probe(
    *,
    target: str,
    receipt: dict[str, Any],
    readiness_path: Path,
    report_dir: Path,
    readiness_phase: ReadinessPhase,
) -> tuple[dict[str, Any], Path]:
    """Re-read live discovery/video/premium and bind results to receipt post IDs."""

    report_file = report_dir / "integration-probe.json"
    try:
        check, _output, findings = _run_environment_integration_probe(
            load_environment_topology(),
            target,
            report_dir,
            require_non_empty_content_feed=True,
            release_post_expectations=_release_feed_post_expectations(
                receipt,
                readiness_phase=readiness_phase,
            ),
            release_readiness_path=readiness_path,
            only_checks=tuple(
                (
                    "content_feed",
                    "video_book_feed",
                    *(
                        ("premium_feed",)
                        if readiness_phase in {ReadinessPhase.RESEARCH, ReadinessPhase.COMMERCIAL}
                        else ()
                    ),
                    "media_sample",
                )
            ),
            probe_name="release-bound-feed-readback",
        )
    except RuntimeError as exc:
        raise ValueError(f"local TLS trust is unavailable: {exc}") from exc
    report = _read_json_object(str(report_file))
    if not bool(check.get("ok")) or findings or report.get("status") != "passed":
        details = findings or ["release-bound feed readback did not pass"]
        raise ValueError("; ".join(str(item) for item in details))
    return report, report_file


def _resolve_active_app_content_evidence(
    target: str,
) -> tuple[dict[str, Any], dict[str, Any], Path, str]:
    """Resolve one active candidate to its newest fully valid commercial evidence."""

    topology = load_environment_topology()
    environment = str(get_target(topology, target)["env"])
    active = active_deployment_candidate(target)
    if active is None:
        raise ValueError("active immutable runtime candidate is missing")
    manifest_path = Path(str(active["candidateDir"])) / "manifest.json"
    manifest = _read_json_object(str(manifest_path))
    release = manifest.get("release") if isinstance(manifest, dict) else None
    candidate = release.get("candidate") if isinstance(release, dict) else None
    if not isinstance(candidate, dict):
        raise ValueError("active candidate does not bind a Data candidate release")
    release_id = str(candidate.get("releaseId") or "").strip()
    manifest_digest = str(candidate.get("releaseDigest") or "").strip()
    attestation_ref = str(candidate.get("attestationRef") or "").strip()
    attestation_digest = str(candidate.get("attestationDigest") or "").strip()
    if not release_id or _DATA_READINESS_DIGEST_RE.fullmatch(manifest_digest) is None:
        raise ValueError("active candidate Data release identity is incomplete")
    if not attestation_ref or _DATA_READINESS_DIGEST_RE.fullmatch(attestation_digest) is None:
        raise ValueError("active candidate Data release attestation identity is incomplete")
    attestation_path = Path(attestation_ref).expanduser().resolve()
    if not attestation_path.is_file():
        raise ValueError("active candidate Data release attestation is missing")
    actual_attestation_digest = "sha256:" + hashlib.sha256(
        attestation_path.read_bytes()
    ).hexdigest()
    if actual_attestation_digest != attestation_digest:
        raise ValueError("active candidate Data release attestation digest drifted")

    readiness_root = env_runs_root(environment) / "data-release" / release_id
    lifecycle_root = (
        env_runs_root(environment)
        / "release-lifecycle-exit"
        / release_id
    )
    readiness_errors: list[str] = []
    lifecycle_errors: list[str] = []
    commercial_receipts: list[tuple[dict[str, Any], Path]] = []
    for readiness_path in sorted(
        readiness_root.glob("*/release-readiness.json"), reverse=True
    ):
        try:
            receipt, canonical_path = _load_data_release_readiness(
                environment=environment,
                release_id=release_id,
                verify_run_id=readiness_path.parent.name,
                manifest_digest=manifest_digest,
                readiness_phase=ReadinessPhase.COMMERCIAL,
            )
        except ValueError as exc:
            readiness_errors.append(str(exc))
            continue
        commercial_receipts.append((receipt, canonical_path))
    if not commercial_receipts:
        detail = readiness_errors[0] if readiness_errors else "no receipt exists"
        raise ValueError(
            "active release has no valid commercial readiness receipt: " + detail
        )

    # Prefer any commercial readiness that binds a lifecycle Exit. Post-lifecycle
    # commercial verifies sit on the replay import; lexicographic "latest" alone
    # can otherwise pick a pre-lifecycle sibling commercial receipt first.
    for selected_readiness, selected_readiness_path in commercial_receipts:
        for lifecycle_path in sorted(
            lifecycle_root.glob("*/lifecycle-exit.json"), reverse=True
        ):
            try:
                candidate_ref = lifecycle_path.resolve().relative_to(
                    output_root().expanduser().resolve()
                ).as_posix()
            except ValueError:
                lifecycle_errors.append("lifecycle receipt escapes QWQ_OUTPUT_ROOT")
                continue
            try:
                _load_data_release_lifecycle_exit(
                    environment=environment,
                    release_id=release_id,
                    manifest_digest=manifest_digest,
                    readiness=selected_readiness,
                    lifecycle_exit_ref=candidate_ref,
                )
            except ValueError as exc:
                lifecycle_errors.append(str(exc))
                continue
            return manifest, selected_readiness, selected_readiness_path, candidate_ref

    detail = lifecycle_errors[0] if lifecycle_errors else "no receipt exists"
    raise ValueError(
        "active release has no valid rollback/replay lifecycle receipt: " + detail
    )


def _app_content_uat_envelope(readiness: dict[str, Any]) -> dict[str, str]:
    raw = readiness.get("appUatEnvelope")
    if not isinstance(raw, dict):
        raise ValueError("release readiness is missing canonical appUatEnvelope")
    required_fields = {
        key for key, _argument in APP_CONTENT_UAT_ENVELOPE_ARGUMENTS
    } | {"videoWorkId"}
    envelope = {key: str(raw.get(key) or "").strip() for key in required_fields}
    missing = sorted(key for key, value in envelope.items() if not value)
    if missing:
        raise ValueError(
            "release readiness appUatEnvelope is incomplete: "
            + ", ".join(missing)
        )
    if envelope["releaseId"] != str(readiness.get("releaseId") or "").strip():
        raise ValueError("release readiness appUatEnvelope releaseId mismatch")
    for key in ("releaseClass", "productLifecycleState"):
        if envelope[key] != str(readiness.get(key) or "").strip():
            raise ValueError(f"release readiness appUatEnvelope {key} mismatch")

    query_matches: dict[str, set[str]] = {}
    for query in readiness.get("feedQueries") or []:
        if not isinstance(query, dict):
            continue
        name = str(query.get("name") or "").strip()
        matches = query.get("matchedPostIds")
        if name and isinstance(matches, list):
            query_matches[name] = {
                str(item).strip() for item in matches if str(item).strip()
            }
    expected_queries = {
        "typed_article": envelope["articleWorkId"],
        "typed_image": envelope["imageWorkId"],
        "typed_video": envelope["videoWorkId"],
    }
    for query_name, work_id in expected_queries.items():
        if work_id not in query_matches.get(query_name, set()):
            raise ValueError(
                f"release readiness appUatEnvelope {query_name} is not exact-query bound"
            )
    if not query_matches.get("homepage_recommend"):
        raise ValueError("release readiness homepage recommendation is empty")
    if envelope["videoWorkId"] not in query_matches.get("premium_stream", set()):
        raise ValueError(
            "release readiness appUatEnvelope video is not Premium-query bound"
        )
    return envelope


def _app_content_readback_summary(readiness: dict[str, Any]) -> dict[str, Any]:
    queries: list[dict[str, Any]] = []
    for query in readiness.get("feedQueries") or []:
        if not isinstance(query, dict):
            continue
        requests = []
        for request in query.get("requests") or []:
            if not isinstance(request, dict):
                continue
            requests.append(
                {
                    key: request.get(key)
                    for key in (
                        "requestId",
                        "traceId",
                        "status",
                        "durationMs",
                    )
                }
            )
        queries.append(
            {
                "name": str(query.get("name") or ""),
                "status": query.get("status"),
                "matchedPostIds": list(query.get("matchedPostIds") or []),
                "requests": requests,
            }
        )
    return {
        "counts": readiness.get("counts", {}),
        "postIds": list(readiness.get("postIds") or []),
        "creatorIds": list(readiness.get("creatorIds") or []),
        "feedQueries": queries,
    }


def command_app_content_preflight(args: argparse.Namespace) -> dict[str, Any]:
    target = str(args.target)
    environment = str(get_target(load_environment_topology(), target)["env"])
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else repo_run_dir("app-content-preflight", target=target)
    )
    try:
        candidate, readiness, readiness_path, lifecycle_ref = (
            _resolve_active_app_content_evidence(target)
        )
        app_uat_envelope = _app_content_uat_envelope(readiness)
    except (OSError, ValueError) as exc:
        details = [str(exc)]
        payload = {
            "schema": "quwoquan_ops.app_content_preflight",
            "target": target,
            "environment": environment,
            "status": "gate_block",
            "details": details,
        }
        write_json(report_dir / "report.json", payload)
        write_json(report_dir / "findings.json", {"issues": details})
        return {
            **payload,
            "exitCode": 2,
            "summary": f"App content preflight is GATE_BLOCK for {target}",
            "reportDir": relpath(report_dir),
        }

    readiness_result = command_content_readiness(
        argparse.Namespace(
            command="content-readiness",
            phase=ReadinessPhase.COMMERCIAL.value,
            env=environment,
            release_id=str(readiness["releaseId"]),
            verify_run_id=str(readiness["verifyRunId"]),
            manifest_digest=str(readiness["manifestDigest"]),
            lifecycle_exit_ref=lifecycle_ref,
            output_format="json",
            report_dir=str(report_dir / "content-readiness"),
        )
    )
    passed = int(readiness_result.get("exitCode", 2)) == 0
    receipt_digest = _canonical_document_checksum(readiness)
    payload = {
        "schema": "quwoquan_ops.app_content_preflight",
        "target": target,
        "environment": environment,
        "status": "passed" if passed else "gate_block",
        "packageBaseline": candidate.get("baselineId", ""),
        "sourceRevision": candidate.get("sourceRevision", ""),
        "releaseId": readiness["releaseId"],
        "manifestDigest": readiness["manifestDigest"],
        "readinessReceiptRef": relpath(readiness_path),
        "readinessReceiptDigest": receipt_digest,
        "lifecycleExitRef": lifecycle_ref,
        "appUatEnvelope": app_uat_envelope,
        "contentReadback": _app_content_readback_summary(readiness),
        "contentReadinessReportRef": relpath(
            report_dir / "content-readiness" / "report.json"
        ),
        "details": list(readiness_result.get("details", [])),
    }
    write_json(report_dir / "report.json", payload)
    write_json(
        report_dir / "findings.json",
        {"issues": [] if passed else payload["details"]},
    )
    return {
        **payload,
        "exitCode": 0 if passed else 2,
        "summary": (
            f"App content preflight passed for {target}"
            if passed
            else f"App content preflight is GATE_BLOCK for {target}"
        ),
        "reportDir": relpath(report_dir),
    }


def _app_content_patrol_evidence(report_ref: str) -> dict[str, Any]:
    report_path = Path(report_ref)
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    report = _read_json_object(str(report_path))
    report_runs = report.get("runs")
    if not isinstance(report_runs, list):
        report_runs = []
    selected = next(
        (
            item
            for item in report_runs
            if isinstance(item, dict) and int(item.get("exitCode", 1)) == 0
        ),
        {},
    )
    evidence = selected.get("evidence") if isinstance(selected, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    screenshot = evidence.get("afterScreenshot")
    screenshot = screenshot if isinstance(screenshot, dict) else {}
    screenshot_ref = str(screenshot.get("path") or "").strip()
    screenshot_path = Path(screenshot_ref)
    if screenshot_ref and not screenshot_path.is_absolute():
        screenshot_path = ROOT / screenshot_path
    screenshot_digest = (
        "sha256:" + hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
        if screenshot_ref and screenshot_path.is_file()
        else ""
    )
    return {
        "status": str(report.get("status") or ""),
        "device": selected.get("device", {}) if isinstance(selected, dict) else {},
        "testExecution": (
            selected.get("testExecution", {}) if isinstance(selected, dict) else {}
        ),
        "consumerLease": evidence.get("consumerLease", {}),
        "feedContent": evidence.get("feedContent", {}),
        "controlledEdgeFault": evidence.get("controlledEdgeFault", {}),
        "controlledEdgeFaultReceipt": evidence.get(
            "controlledEdgeFaultReceipt", {}
        ),
        "screenshotRef": screenshot_ref,
        "screenshotDigest": screenshot_digest,
        "remoteApi": report.get("remoteApiEvidence", {}),
    }


def command_app_debug_preflight(args: argparse.Namespace) -> dict[str, Any]:
    """Fail closed before Debug launch without mutating environment lifecycle."""

    target_name = str(args.target)
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    environment = str(target["env"])
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else repo_run_dir("app-debug-preflight", target=target_name)
    )
    details: list[str] = []
    startup: dict[str, Any] = {}
    try:
        startup = load_startup_attempt(target_name) or {}
    except (OSError, ValueError) as exc:
        details.append(f"startup receipt unreadable: {exc}")
    if not startup:
        details.append("target has no startup receipt")
    else:
        if startup.get("status") != "running":
            details.append(
                "target startup status is not running: "
                + str(startup.get("status") or "missing")
            )
        if startup.get("env") != environment or startup.get("target") != target_name:
            details.append("startup receipt target/environment mismatch")
        if startup.get("workload") != "full":
            details.append("Debug login requires a full workload runtime")
        if re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            str(startup.get("configurationDigest") or ""),
        ) is None:
            details.append("startup receipt has no canonical configuration digest")

    try:
        tls_evidence = verify_certificate(target_name)
    except (OSError, PublicDomainTlsError, ValueError) as exc:
        tls_evidence = {"status": "gate_block"}
        details.append(f"target TLS is not ready: {exc}")

    profile_name = str(target.get("portProfile") or "")
    ports = profile_ports(load_port_manifest(), profile_name) if profile_name else {}
    public_bases = target.get("publicBases") or {}
    checks = [
        ("api-edge", f"{str(public_bases.get('api') or '').rstrip('/')}/healthz", ""),
        ("user-service", f"http://127.0.0.1:{ports.get('user-service', 0)}/healthz", ""),
        ("integration-service", f"http://127.0.0.1:{ports.get('integration-service', 0)}/healthz", ""),
        (
            "sms-provider-substitute",
            f"https://127.0.0.1:{ports.get('sms-provider-substitute', 0)}/healthz",
            str(root_certificate_path(target_name, require_ready=False)),
        ),
        (
            "provider-protocol-substitute",
            f"https://127.0.0.1:{ports.get('provider-protocol-substitute', 0)}/healthz",
            str(root_certificate_path(target_name, require_ready=False)),
        ),
    ]
    provider_readback: dict[str, Any] = {}
    check_receipts: list[dict[str, Any]] = []
    for name, url, ca_file in checks:
        if url.endswith(":0/healthz") or url == "/healthz":
            details.append(f"{name} topology is incomplete")
            continue
        ok, status_code, body, _ = fetch_url(
            url,
            timeout=2.0,
            retry_attempts=1,
            retry_sleep_seconds=0,
            ca_file=ca_file,
        )
        check_receipts.append(
            {"name": name, "ready": ok, "statusCode": status_code}
        )
        if not ok:
            details.append(f"{name} is not ready: {status_code or 'network_error'}")
            continue
        if name == "sms-provider-substitute":
            try:
                decoded = json.loads(body)
            except json.JSONDecodeError:
                details.append("SMS substitute health readback is not JSON")
                continue
            if not isinstance(decoded, dict):
                details.append("SMS substitute health readback is invalid")
                continue
            provider_readback = {
                "adapterId": str(decoded.get("adapterId") or ""),
                "environment": str(decoded.get("environment") or ""),
                "configurationDigest": str(
                    decoded.get("configurationDigest") or ""
                ),
                "profile": str(decoded.get("profile") or ""),
                "nonPromotable": decoded.get("nonPromotable") is True,
                "ready": decoded.get("status") == "ready",
            }
            if provider_readback != {
                "adapterId": "ext.sms.local_capture",
                "environment": environment,
                "configurationDigest": str(
                    startup.get("configurationDigest") or ""
                ),
                "profile": provider_readback["profile"],
                "nonPromotable": True,
                "ready": True,
            } or provider_readback["profile"] not in {
                "success",
                "rate_limit",
                "failure",
                "timeout",
            }:
                details.append("SMS substitute adapter/environment/readiness mismatch")

    content_result = command_app_content_preflight(
        argparse.Namespace(
            target=target_name,
            report_dir=str(report_dir / "content"),
        )
    )
    if int(content_result.get("exitCode", 2)) != 0:
        details.append(
            "content preflight failed: "
            + str((content_result.get("details") or ["unknown"])[0])
        )

    passed = not details
    payload = {
        "schema": "quwoquan_ops.app_debug_preflight",
        "target": target_name,
        "environment": environment,
        "status": "passed" if passed else "gate_block",
        "configurationDigest": str(startup.get("configurationDigest") or ""),
        "runtimeChecks": check_receipts,
        "tls": {
            "profile": str(tls_evidence.get("profile") or ""),
            "status": str(tls_evidence.get("status") or ""),
        },
        "provider": provider_readback,
        "details": details,
        "packageBaseline": content_result.get("packageBaseline", ""),
        "sourceRevision": content_result.get("sourceRevision", ""),
        "releaseId": content_result.get("releaseId", ""),
        "manifestDigest": content_result.get("manifestDigest", ""),
        "readinessReceiptRef": content_result.get("readinessReceiptRef", ""),
        "readinessReceiptDigest": content_result.get(
            "readinessReceiptDigest", ""
        ),
        "lifecycleExitRef": content_result.get("lifecycleExitRef", ""),
        "appUatEnvelope": content_result.get("appUatEnvelope", {}),
        "contentReadback": content_result.get("contentReadback", {}),
        "contentReadinessReportRef": content_result.get(
            "contentReadinessReportRef", ""
        ),
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": details})
    return {
        **payload,
        "exitCode": 0 if passed else 2,
        "summary": (
            f"App Debug preflight passed for {target_name}"
            if passed
            else f"App Debug preflight is GATE_BLOCK for {target_name}"
        ),
        "reportDir": relpath(report_dir),
    }


def command_provider_debug(args: argparse.Namespace) -> dict[str, Any]:
    """Read one random OTP through the protected local control plane."""

    target_name = str(args.target)
    target = get_target(load_environment_topology(), target_name)
    environment = str(target["env"])
    if args.action != "otp-read":
        return {
            "exitCode": 2,
            "summary": "provider-debug is GATE_BLOCK",
            "details": ["unsupported provider-debug action"],
        }
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return {
            "exitCode": 2,
            "summary": "provider-debug otp-read is GATE_BLOCK",
            "details": ["otp-read requires an interactive TTY"],
        }
    try:
        phone = _normalize_debug_phone(
            getpass.getpass("Phone (input is hidden): ")
        )
        protected_otp = read_latest_debug_otp(
            environment=environment,
            target_name=target_name,
            recipient=phone,
        )
        with open("/dev/tty", "w", encoding="utf-8") as tty:
            tty.write(f"OTP: {protected_otp.code}\n")
            tty.flush()
        protected_otp = None
    except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
        return {
            "exitCode": 2,
            "summary": "provider-debug otp-read is GATE_BLOCK",
            "details": [str(exc)],
        }
    return {
        "exitCode": 0,
        "summary": "protected OTP was displayed on the current TTY",
        "details": [
            f"target={target_name}",
            "OTP was not written to argv, reports, logs, or command output",
        ],
        "provider": {
            "adapterId": "ext.sms.local_capture",
            "environment": environment,
            "nonPromotable": True,
        },
    }


def _normalize_debug_phone(raw: str) -> str:
    normalized = re.sub(r"[\s\-()]", "", str(raw or "").strip())
    if re.fullmatch(r"1[0-9]{10}", normalized):
        normalized = "+86" + normalized
    if re.fullmatch(r"\+[1-9][0-9]{7,14}", normalized) is None:
        raise ValueError("phone must be an E.164 number or an 11-digit mainland number")
    return normalized


def _command_app_content_uat(
    args: argparse.Namespace,
    *,
    initial_issues: Sequence[str] = (),
) -> dict[str, Any]:
    allowed_targets = {"alpha-local", "beta-local", "gamma-local"}
    targets = [
        item.strip()
        for item in str(getattr(args, "targets", "")).split(",")
        if item.strip()
    ]
    report_dir = (
        Path(args.report_dir)
        if getattr(args, "report_dir", "")
        else repo_run_dir("app-content-uat", target="nonprod-local")
    )
    issues = list(initial_issues)
    if not targets or len(targets) != len(set(targets)):
        issues.append("--targets must contain unique non-empty targets")
    unsupported = sorted(set(targets) - allowed_targets)
    if unsupported:
        issues.append("unsupported App content UAT targets: " + ", ".join(unsupported))
    device_id = str(getattr(args, "device_id", "") or "").strip()
    if not device_id:
        issues.append("--device-id is required")

    preflights: list[dict[str, Any]] = []
    if not issues:
        for target in targets:
            result = command_app_debug_preflight(
                argparse.Namespace(
                    target=target,
                    report_dir=str(report_dir / target / "preflight"),
                )
            )
            preflights.append(result)
            if int(result.get("exitCode", 2)) != 0:
                issues.append(
                    f"{target}: "
                    + str((result.get("details") or [result.get("summary")])[0])
                )
                break
    if not issues and preflights:
        baselines = {str(item.get("packageBaseline") or "") for item in preflights}
        releases = {str(item.get("releaseId") or "") for item in preflights}
        digests = {str(item.get("manifestDigest") or "") for item in preflights}
        app_uat_envelopes = {
            json.dumps(
                item.get("appUatEnvelope") or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for item in preflights
        }
        if len(baselines) != 1 or "" in baselines:
            issues.append("Alpha/Beta/Gamma package baseline is not identical")
        elif len(releases) != 1 or "" in releases:
            issues.append("Alpha/Beta/Gamma active releaseId is not identical")
        elif len(digests) != 1 or "" in digests:
            issues.append("Alpha/Beta/Gamma manifest digest is not identical")
        elif len(app_uat_envelopes) != 1 or "{}" in app_uat_envelopes:
            issues.append("Alpha/Beta/Gamma appUatEnvelope is not identical")

    runs: list[dict[str, Any]] = []
    if not issues:
        for preflight in preflights:
            target = str(preflight["target"])
            environment = str(preflight["environment"])
            readiness_path = ROOT / str(preflight["readinessReceiptRef"])
            if args.platform == "ios-simulator":
                direct_command = [
                    sys.executable,
                    str(IOS_DIRECT_FLUTTER_RUN_UAT),
                    "--env",
                    environment,
                    "--device-id",
                    device_id,
                    "--launch-surface",
                    "direct_flutter_run",
                    "--output-dir",
                    str(report_dir / target / "direct-flutter-run"),
                ]
                if bool(getattr(args, "dry_run", False)):
                    direct_command.append("--preflight-only")
                direct_result = run(direct_command, cwd=ROOT / "quwoquan_app")
                try:
                    direct_evidence = json.loads(direct_result.stdout)
                except json.JSONDecodeError:
                    direct_evidence = {}
                direct_passed = (
                    direct_result.returncode == 0
                    and isinstance(direct_evidence, dict)
                    and direct_evidence.get("status") == "passed"
                    and direct_evidence.get("launchMode") == "direct_flutter_run"
                    and _DATA_READINESS_DIGEST_RE.fullmatch(
                        str(direct_evidence.get("consumerLeaseId") or "")
                    )
                    is not None
                )
                runs.append(
                    {
                        "target": target,
                        "suite": "direct-flutter-run",
                        "exitCode": direct_result.returncode,
                        "reportRef": str(direct_evidence.get("reportPath") or ""),
                        "launchMode": direct_evidence.get("launchMode"),
                        "consumerLeaseId": direct_evidence.get("consumerLeaseId"),
                        "attempts": direct_evidence.get("attempts", []),
                    }
                )
                if not direct_passed:
                    detail = (direct_result.stderr or direct_result.stdout).strip()
                    issues.append(
                        f"{target}: literal flutter run failed: "
                        + (detail[:800] if detail else "typed report is incomplete")
                    )
                    break
            for suite_name, patrol_target, bind_release in (
                ("homepage-feed", DISCOVERY_FEED_UAT_TEST_TARGET, False),
                ("app-core-readback", APP_CORE_READBACK_UAT_TEST_TARGET, True),
                ("video-playback", VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET, True),
                (
                    "controlled-edge-recovery",
                    CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
                    False,
                ),
            ):
                command = _environment_page_smoke_profile_command(
                    environment,
                    target,
                    report_dir / target,
                    suite_name=f"app-content-{suite_name}",
                    patrol_target=patrol_target,
                    data_readiness_path=(readiness_path if bind_release else None),
                )
                if command is None:
                    issues.append(f"{target}: {suite_name} topology is incomplete")
                    break
                argv = list(command["argv"])
                if patrol_target == APP_CORE_READBACK_UAT_TEST_TARGET:
                    envelope = preflight.get("appUatEnvelope")
                    if not isinstance(envelope, dict):
                        issues.append(
                            f"{target}: app-core-readback has no canonical App UAT envelope"
                        )
                        break
                    for field, flag in APP_CONTENT_UAT_ENVELOPE_ARGUMENTS:
                        argv.extend((flag, str(envelope.get(field) or "")))
                if patrol_target == CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET:
                    argv.append("--stackctl-controlled-edge-fault")
                argv.extend(
                    [
                        "--platform",
                        "ios" if args.platform == "ios-simulator" else "android",
                        "--device-id",
                        device_id,
                    ]
                )
                if bool(getattr(args, "dry_run", False)):
                    argv.append("--dry-run")
                result = run(argv, cwd=command["cwd"], env=command.get("env"))
                run_payload = {
                    "target": target,
                    "suite": suite_name,
                    "exitCode": result.returncode,
                    "reportRef": str(command["reportPath"]),
                    "evidence": _app_content_patrol_evidence(
                        str(command["reportPath"])
                    ),
                }
                runs.append(run_payload)
                if result.returncode != 0:
                    detail = (result.stderr or result.stdout).strip()
                    issues.append(
                        f"{target}: {suite_name} failed: "
                        + (detail[:800] if detail else f"exit={result.returncode}")
                    )
                    break
            if not issues and args.platform == "android":
                startup_command = [
                    sys.executable,
                    str(STARTUP_FIRST_FRAME_UAT),
                    "--android-device",
                    device_id,
                    "--runtime-env",
                    environment,
                    "--runtime-target",
                    target,
                    "--matrix-evidence-root",
                    str(report_dir / target / "startup-runtime"),
                    "--output-dir",
                    str(report_dir / target / "startup-first-frame"),
                    "--require-startup-sequence-events",
                    "--require-branded-visible",
                    "--require-no-native-recovery",
                    "--require-telemetry-ack",
                ]
                if bool(getattr(args, "dry_run", False)):
                    issues.append(
                        f"{target}: Android startup evidence cannot be dry-run"
                    )
                    break
                startup_result = run(startup_command, cwd=ROOT)
                try:
                    startup_evidence = json.loads(startup_result.stdout)
                except json.JSONDecodeError:
                    startup_evidence = {}
                startup_passed = (
                    startup_result.returncode == 0
                    and isinstance(startup_evidence, dict)
                    and startup_evidence.get("passed") is True
                    and any(
                        isinstance(item, dict)
                        and str(item.get("attemptId") or "").strip()
                        not in {"", "unknown"}
                        and item.get("telemetryAcknowledged") is True
                        and str(
                            item.get("effectiveLaunchManifestDigest") or ""
                        ).startswith("sha256:")
                        for item in startup_evidence.get("results") or []
                    )
                )
                runs.append(
                    {
                        "target": target,
                        "suite": "startup-first-frame",
                        "exitCode": startup_result.returncode,
                        "reportRef": str(
                            startup_evidence.get("outputDir") or ""
                        ),
                        "evidence": startup_evidence,
                    }
                )
                if not startup_passed:
                    detail = (
                        startup_result.stderr or startup_result.stdout
                    ).strip()
                    issues.append(
                        f"{target}: Android startup evidence failed: "
                        + (detail[:800] if detail else "typed report is incomplete")
                    )
            if issues:
                break

    dry_run = bool(getattr(args, "dry_run", False))
    status = "gate_block" if issues else ("planned" if dry_run else "passed")
    payload = {
        "schema": "quwoquan_ops.app_content_uat_receipt",
        "status": status,
        "targets": targets,
        "platform": str(args.platform),
        "deviceId": device_id,
        "packageBaseline": (
            str(preflights[0].get("packageBaseline") or "")
            if preflights
            else ""
        ),
        "releaseId": (
            str(preflights[0].get("releaseId") or "") if preflights else ""
        ),
        "manifestDigest": (
            str(preflights[0].get("manifestDigest") or "") if preflights else ""
        ),
        "appUatEnvelope": (
            preflights[0].get("appUatEnvelope", {}) if preflights else {}
        ),
        "appUatEnvelopeDigest": (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    preflights[0].get("appUatEnvelope") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if preflights and preflights[0].get("appUatEnvelope")
            else ""
        ),
        "configurationDigests": sorted(
            {
                str(item.get("configurationDigest") or "")
                for item in preflights
                if str(item.get("configurationDigest") or "")
            }
        ),
        "readinessReceiptDigests": sorted(
            {
                str(item.get("readinessReceiptDigest") or "")
                for item in preflights
                if str(item.get("readinessReceiptDigest") or "")
            }
        ),
        "consumerLeaseIds": sorted(
            {
                str(item.get("consumerLeaseId") or "")
                for item in runs
                if str(item.get("consumerLeaseId") or "")
            }
        ),
        "screenshotDigests": sorted(
            {
                str((item.get("evidence") or {}).get("screenshotDigest") or "")
                for item in runs
                if isinstance(item.get("evidence"), dict)
                and str((item.get("evidence") or {}).get("screenshotDigest") or "")
            }
        ),
        "visibleCardCounts": {
            str(item.get("target") or ""): int(
                ((item.get("evidence") or {}).get("feedContent") or {}).get(
                    "visibleCardCount", 0
                )
            )
            for item in runs
            if item.get("suite") == "homepage-feed"
            and isinstance(item.get("evidence"), dict)
        },
        "controlledEdgeRecoveries": {
            str(item.get("target") or ""): (
                (item.get("evidence") or {}).get("controlledEdgeFault") or {}
            )
            for item in runs
            if item.get("suite") == "controlled-edge-recovery"
            and isinstance(item.get("evidence"), dict)
        },
        "preflights": preflights,
        "runs": runs,
        "executed": 0 if dry_run else len(runs),
        "skipped": 0,
        "details": issues
        or [
            (
                "dry-run planned all App content UAT suites; no runtime evidence was claimed"
                if dry_run
                else "all requested App content UAT suites passed"
            )
        ],
    }
    write_json(report_dir / "report.json", payload)
    write_json(report_dir / "findings.json", {"issues": issues})
    return {
        **payload,
        "exitCode": 0 if not issues else 2,
        "summary": (
            "App content UAT dry-run planned"
            if not issues and dry_run
            else "App content UAT passed"
            if not issues
            else "App content UAT is GATE_BLOCK"
        ),
        "reportDir": relpath(report_dir),
    }


def command_app_content_uat(args: argparse.Namespace) -> dict[str, Any]:
    targets = [
        item.strip()
        for item in str(getattr(args, "targets", "")).split(",")
        if item.strip()
    ]
    device_id = str(getattr(args, "device_id", "") or "").strip()
    dry_run = bool(getattr(args, "dry_run", False))
    if dry_run or not targets or not device_id:
        return _command_app_content_uat(args)
    try:
        runtime_use_lock = acquire_local_runtime_use_lock(
            target=",".join(targets),
            purpose=f"app-content-uat:{args.platform}:{device_id}",
        )
    except RuntimeError as error:
        return _command_app_content_uat(args, initial_issues=(str(error),))
    try:
        return _command_app_content_uat(args)
    finally:
        runtime_use_lock.close()


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
            workload=requirement.workload,
            require_non_empty_content_feed=phase in {
                ReadinessPhase.CONSUMER,
                ReadinessPhase.COMMERCIAL,
            } or (
                phase is ReadinessPhase.RESEARCH
                and bool(str(getattr(args, "verify_run_id", "") or "").strip())
            ),
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
    data_readiness_receipt: dict[str, Any] | None = None
    data_readiness_path: Path | None = None
    feed_readback_evidence: dict[str, Any] | None = None
    feed_readback_path: Path | None = None
    video_delivery_evidence: dict[str, Any] | None = None
    video_delivery_path: Path | None = None
    lifecycle_exit_receipt: dict[str, Any] | None = None
    lifecycle_exit_path: Path | None = None
    research_isolation: dict[str, Any] | None = None
    has_research_verify_receipt = (
        phase is ReadinessPhase.RESEARCH
        and bool(str(getattr(args, "verify_run_id", "") or "").strip())
    )
    if phase in {ReadinessPhase.CONSUMER, ReadinessPhase.COMMERCIAL} or has_research_verify_receipt:
        try:
            data_readiness_receipt, data_readiness_path = _load_data_release_readiness(
                environment=args.env,
                release_id=getattr(args, "release_id", ""),
                verify_run_id=getattr(args, "verify_run_id", ""),
                manifest_digest=getattr(args, "manifest_digest", ""),
                readiness_phase=phase,
            )
            probes.append("canonical-data-release-readiness")
        except ValueError as exc:
            details.append(str(exc))
        if data_readiness_path is not None and data_readiness_receipt is not None:
            if phase is ReadinessPhase.COMMERCIAL:
                try:
                    lifecycle_exit_receipt, lifecycle_exit_path = (
                        _load_data_release_lifecycle_exit(
                            environment=args.env,
                            release_id=getattr(args, "release_id", ""),
                            manifest_digest=getattr(args, "manifest_digest", ""),
                            readiness=data_readiness_receipt,
                            lifecycle_exit_ref=getattr(
                                args,
                                "lifecycle_exit_ref",
                                "",
                            ),
                        )
                    )
                    probes.append("canonical-data-release-lifecycle-exit")
                except ValueError as exc:
                    details.append(str(exc))
            try:
                feed_readback_evidence, feed_readback_path = (
                    _run_release_feed_readback_probe(
                        target=requirement.target,
                        receipt=data_readiness_receipt,
                        readiness_path=data_readiness_path,
                        report_dir=report_dir / "release-feed-readback",
                        readiness_phase=phase,
                    )
                )
                probes.append("release-bound-feed-readback")
            except ValueError as exc:
                details.append(f"release-bound feed readback failed: {exc}")
            if phase in {ReadinessPhase.RESEARCH, ReadinessPhase.COMMERCIAL}:
                try:
                    video_delivery_evidence, video_delivery_path = (
                        _run_release_video_delivery_probe(
                            target=requirement.target,
                            readiness_path=data_readiness_path,
                            report_dir=report_dir / "release-video-delivery",
                        )
                    )
                    probes.append("release-video-delivery")
                except ValueError as exc:
                    details.append(str(exc))
    for capability in requirement.capabilities:
        binding = policy.probe_binding_for(capability)
        if binding.source is ProbeSource.HEALTH_SCOPE and binding.health_scope not in executed_scopes:
            details.append(
                f"capability {capability.value} declares probe scope "
                f"{binding.health_scope} but no probe executed for {requirement.target}"
            )
        if binding.source is ProbeSource.RESEARCH_ISOLATION:
            try:
                research_isolation = verify_research_content_isolation(args.env)
                probes.append("governed-research-content-isolation")
            except ValueError as exc:
                details.append(str(exc))
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
        "dataRelease": {
            "releaseId": getattr(args, "release_id", ""),
            "verifyRunId": getattr(args, "verify_run_id", ""),
            "manifestDigest": getattr(args, "manifest_digest", ""),
            "receiptRef": relpath(data_readiness_path) if data_readiness_path else "",
            "receipt": data_readiness_receipt,
            "lifecycleExitRef": (
                str(getattr(args, "lifecycle_exit_ref", "")).strip()
                if lifecycle_exit_path
                else ""
            ),
            "lifecycleExit": lifecycle_exit_receipt,
            "feedReadbackEvidenceRef": (
                relpath(feed_readback_path) if feed_readback_path else ""
            ),
            "feedReadback": feed_readback_evidence,
            "videoDeliveryEvidenceRef": (
                relpath(video_delivery_path) if video_delivery_path else ""
            ),
            "videoDelivery": video_delivery_evidence,
        },
        "researchContentIsolation": research_isolation,
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
        extra={
            "policyId": policy.policy_id,
            "phase": phase.value,
            "outcome": outcome.value,
            "dataRelease": payload["dataRelease"],
        },
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
    release_id = ""
    import_run_id = ""
    lease_acquire: dict[str, Any] | None = None
    try:
        resolved_cases = cases_path.resolve(strict=True)
        case_ref = resolved_cases.relative_to(allowed_root.resolve(strict=True))
        if (
            len(case_ref.parts) != 3
            or case_ref.parts[2] != "homepage_verification_cases.json"
        ):
            raise ValueError(
                "release UAT cases must be exactly "
                "<releaseId>/<importRunId>/homepage_verification_cases.json"
            )
        release_id, import_run_id, _filename = case_ref.parts
        verify_run_id = _data_readiness_segment(
            str(getattr(args, "data_verify_run_id", "")),
            label="dataVerifyRunId",
        )
        lease_id = _data_readiness_segment(
            str(getattr(args, "acceptance_lease_id", "")),
            label="acceptanceLeaseId",
        )
        command = _content_release_uat_command(
            target_name=args.target,
            release_uat_cases=resolved_cases,
            platform=args.platform,
            device_ids=list(args.device_id),
            report_dir=report_dir,
        )
        lease_acquire = _run_data_acceptance_lease(
            action="acquire",
            environment="gamma",
            release_id=release_id,
            import_run_id=import_run_id,
            verify_run_id=verify_run_id,
            lease_id=lease_id,
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

    result = run(command["argv"], cwd=command["cwd"], env=command.get("env"))
    runner_report = _read_json_object(str(ROOT / str(command["reportPath"])))
    runner_status = str(runner_report.get("status") or "failed")
    lease_revoke: dict[str, Any] | None = None
    lease_revoke_error = ""
    try:
        lease_revoke = _run_data_acceptance_lease(
            action="revoke",
            environment="gamma",
            release_id=release_id,
            lease_id=str(lease_acquire["leaseId"]),
            acquire_event_ref=str(lease_acquire["eventRef"]),
        )
    except ValueError as exc:
        lease_revoke_error = str(exc)
    status = "ok" if result.returncode == 0 and runner_status == "passed" else (
        "gate_block" if result.returncode == 2 or runner_status == "gate_block" else "failed"
    )
    details = _command_details(result)
    if lease_revoke_error:
        status = "gate_block"
        details.append(
            "acceptance lease revoke failed; release remains protected: "
            + lease_revoke_error
        )
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "command": "content-uat",
        "target": args.target,
        "status": status,
        "releaseUatCases": relpath(resolved_cases),
        "runnerReport": command["reportPath"],
        "runnerStatus": runner_status,
        "acceptanceLease": {
            "acquireEventRef": str((lease_acquire or {}).get("eventRef") or ""),
            "revokeEventRef": str((lease_revoke or {}).get("eventRef") or ""),
            "closed": lease_revoke is not None,
        },
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
            "acceptanceLease": payload["acceptanceLease"],
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


def command_account_enforcement_uat(args: argparse.Namespace) -> dict[str, Any]:
    """Run one controlled App phase or aggregate the immutable Gamma CaseResult."""

    report_dir = resolve_report_dir(args, "gamma", args.target)
    started_monotonic, started_at = _start_timing()
    action = str(args.action)
    if action == "verify":
        child_report = report_dir / "case-result.json"
        journey_receipt = str(args.journey_receipt).strip() or str(
            report_dir / "journey-receipt.json"
        )
        suspended_device_report = str(args.suspended_device_report).strip() or str(
            report_dir / "suspended-device-report.json"
        )
        restored_device_report = str(args.restored_device_report).strip() or str(
            report_dir / "restored-device-report.json"
        )
        command = [
            "python3",
            ACCOUNT_ENFORCEMENT_GAMMA_UAT_VALIDATOR,
            "--manifest",
            str(args.manifest),
            "--run-id",
            str(args.run_id),
            "--candidate-digest",
            str(args.candidate_digest),
            "--journey-receipt",
            journey_receipt,
            "--suspended-device-report",
            suspended_device_report,
            "--restored-device-report",
            restored_device_report,
            "--report",
            str(child_report),
        ]
    else:
        phase = action.removeprefix("device-")
        child_report = report_dir / f"{phase}-device-report.json"
        command = [
            "python3",
            ACCOUNT_ENFORCEMENT_GAMMA_DEVICE_RUNNER,
            "--manifest",
            str(args.manifest),
            "--phase",
            phase,
            "--candidate-digest",
            str(args.candidate_digest),
            "--report",
            str(child_report),
        ]
        for device_id in list(args.device_id):
            normalized = str(device_id).strip()
            if normalized:
                command.extend(("--device-id", normalized))

    result = run(command, cwd=ROOT)
    child_payload = _read_json_object(str(child_report))
    child_status = str(child_payload.get("status") or "failed")
    status = (
        "ok"
        if result.returncode == 0 and child_status == "passed"
        else "gate_block"
        if result.returncode == 2 or child_status == "gate_block"
        else "failed"
    )
    details = _command_details(result)
    if not child_payload:
        details.append("account-enforcement child report is missing or unreadable")
    timing = _finish_timing(started_monotonic, started_at)
    payload = {
        "command": "account-enforcement-uat",
        "target": args.target,
        "action": action,
        "status": status,
        "candidateDigest": str(args.candidate_digest),
        "childReport": relpath(child_report),
        "childStatus": child_status,
        "details": details,
        **timing,
    }
    write_json(report_dir / "report.json", payload)
    write_json(
        report_dir / "findings.json",
        {"issues": details if status != "ok" else []},
    )
    summary = (
        f"account-enforcement UAT {action} passed"
        if status == "ok"
        else f"account-enforcement UAT {action} is GATE_BLOCK"
        if status == "gate_block"
        else f"account-enforcement UAT {action} failed"
    )
    _write_summary_bundle(
        report_dir,
        command="account-enforcement-uat",
        target=args.target,
        status=status,
        summary=summary,
        details=details,
        extra={
            "action": action,
            "candidateDigest": str(args.candidate_digest),
            "childReport": relpath(child_report),
            "childStatus": child_status,
        },
        timing=timing,
    )
    return {
        "exitCode": 0 if status == "ok" else 2 if status == "gate_block" else 1,
        "summary": summary,
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def _run_data_acceptance_lease(
    *,
    action: str,
    environment: str,
    release_id: str,
    lease_id: str,
    import_run_id: str = "",
    verify_run_id: str = "",
    acquire_event_ref: str = "",
) -> dict[str, Any]:
    """Invoke the Data-owned lease writer; stackctl never writes its schema."""

    argv = [
        "python3",
        "-B",
        "quwoquan_data/scripts/cli.py",
        "release",
        "acceptance-lease",
        action,
        "--env",
        environment,
        "--release-id",
        release_id,
        "--lease-id",
        lease_id,
    ]
    if action == "acquire":
        argv.extend(
            (
                "--import-run-id",
                import_run_id,
                "--verify-run-id",
                verify_run_id,
            )
        )
    elif action == "revoke":
        argv.extend(("--acquire-event-ref", acquire_event_ref))
    else:
        raise ValueError("acceptance lease action must be acquire or revoke")
    result = run(argv, cwd=ROOT)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(
            "Data acceptance lease command failed: "
            + (detail[:800] if detail else f"exit={result.returncode}")
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Data acceptance lease command returned invalid JSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "quwoquan_data.release_acceptance_lease_event"
        or payload.get("action") != action
        or payload.get("environment") != environment
        or payload.get("releaseId") != release_id
        or payload.get("leaseId") != lease_id
        or not str(payload.get("eventRef") or "")
    ):
        raise ValueError("Data acceptance lease command returned identity-drifted evidence")
    return payload


def _reconcile_nonprod_data(
    args: argparse.Namespace,
    *,
    environment: str,
    target_name: str,
    report_dir: Path,
) -> dict[str, Any]:
    if environment not in {"alpha", "beta", "gamma"} or target_name not in NONPROD_TARGETS:
        summary = "reconcile-nonprod-data is forbidden outside Alpha/Beta/Gamma"
        return {
            "exitCode": 2,
            "summary": summary,
            "details": [summary, "Prod REAL_DATA_ONLY is fail-closed"],
            "reportDir": relpath(report_dir),
        }
    if not bool(getattr(args, "confirm_nonprod_data_reconcile", False)):
        summary = f"stackctl repair nonprod data is GATE_BLOCK for {target_name}"
        details = [
            "--confirm-nonprod-data-reconcile is required",
            "only stale, expired, failed, or incomplete receipt-owned datasets are eligible",
        ]
        write_json(
            report_dir / "report.json",
            {
                "command": "repair",
                "target": target_name,
                "fix": "reconcile-nonprod-data",
                "status": "GATE_BLOCK",
                "destructiveRepairPerformed": False,
                "details": details,
            },
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=target_name,
            status="failed",
            summary=summary,
            details=details,
        )
        return {
            "exitCode": 2,
            "summary": summary,
            "details": details,
            "reportDir": relpath(report_dir),
        }

    active_binding: dict[str, Any] | None = None
    active = active_deployment_candidate(target_name)
    if isinstance(active, dict):
        baseline_id = str(active.get("baselineId") or "").strip()
        try:
            manifest = load_candidate_manifest(
                environment,
                target_name,
                baseline_id,
                require_full=True,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            summary = f"stackctl repair nonprod data is GATE_BLOCK for {target_name}"
            details = ["active candidate manifest is invalid: " + str(exc)]
            _write_summary_bundle(
                report_dir,
                command="repair",
                target=target_name,
                status="failed",
                summary=summary,
                details=details,
            )
            return {
                "exitCode": 2,
                "summary": summary,
                "details": details,
                "reportDir": relpath(report_dir),
            }
        active_binding = {
            "baselineId": manifest.get("baselineId"),
            "packageDigest": manifest.get("packageDigest"),
            "runtimeConfigDigest": manifest.get("runtimeConfigDigest"),
            "releaseDigest": (
                ((manifest.get("release") or {}).get("candidate") or {}).get(
                    "releaseDigest"
                )
            ),
        }

    receipt_root = env_runs_root(environment) / "nonprod-data"
    groups: dict[tuple[str, ...], dict[str, dict[str, Any]]] = {}
    scan_issues: list[str] = []
    if receipt_root.is_dir():
        for epoch_dir in sorted(receipt_root.iterdir()):
            if (
                not epoch_dir.is_dir()
                or epoch_dir.name.startswith("history")
                or re.fullmatch(r"[0-9a-f]{64}", epoch_dir.name) is None
            ):
                continue
            for path in sorted(epoch_dir.glob("*.json")):
                try:
                    receipt = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    scan_issues.append(
                        f"unreadable receipt {relpath(path)}: {type(exc).__name__}"
                    )
                    continue
                if (
                    not isinstance(receipt, dict)
                    or receipt.get("schema")
                    != "qwq.nonprod_acceptance_dataset_receipt"
                    or receipt.get("target") != target_name
                    or receipt.get("environment") != environment
                    or receipt.get("retentionClass") != "candidate_bound"
                ):
                    scan_issues.append(
                        f"ineligible receipt identity: {relpath(path)}"
                    )
                    continue
                key = tuple(
                    str(receipt.get(name) or "").strip()
                    for name in (
                        "baselineId",
                        "sourceRevision",
                        "packageDigest",
                        "runtimeConfigDigest",
                        "releaseId",
                        "releaseDigest",
                        "importRunId",
                    )
                )
                if any(not value for value in key):
                    scan_issues.append(
                        f"receipt candidate binding is incomplete: {relpath(path)}"
                    )
                    continue
                dataset_id = str(receipt.get("datasetId") or "").strip()
                group = groups.setdefault(key, {})
                if not dataset_id or dataset_id in group:
                    scan_issues.append(
                        f"duplicate or empty dataset identity: {relpath(path)}"
                    )
                    continue
                group[dataset_id] = receipt

    eligible: list[tuple[tuple[str, ...], dict[str, dict[str, Any]], list[str]]] = []
    now = datetime.now(timezone.utc)
    for key, group in groups.items():
        reasons: list[str] = []
        binding = {
            "baselineId": key[0],
            "packageDigest": key[2],
            "runtimeConfigDigest": key[3],
            "releaseDigest": key[5],
        }
        if active_binding is not None and binding != active_binding:
            reasons.append("stale_candidate_binding")
        for receipt in group.values():
            if receipt.get("cleanupState") in {"pending", "failed"} or receipt.get(
                "status"
            ) != "passed":
                reasons.append("incomplete_or_failed")
            raw_expires_at = str(receipt.get("expiresAt") or "").strip()
            try:
                expires_at = datetime.fromisoformat(raw_expires_at.replace("Z", "+00:00"))
            except ValueError:
                reasons.append("invalid_expiry")
            else:
                if expires_at.tzinfo is None or expires_at <= now:
                    reasons.append("expired")
        if reasons:
            eligible.append((key, group, sorted(set(reasons))))

    results: list[dict[str, Any]] = []
    failures = list(scan_issues)
    topology = load_environment_topology()
    target = get_target(topology, target_name)
    base_url = str((target.get("publicBases") or {}).get("api") or "").rstrip("/")
    if not base_url.startswith("https://"):
        failures.append("canonical HTTPS API is required for reconciliation")
    if not failures:
        for key, group, reasons in eligible:
            identity = group.get("nonprod_reference_identity")
            if identity is None:
                failures.append(
                    f"candidate {key[0]} has no receipt-owned identity closure"
                )
                continue
            post_ids = identity.get("releasePostIds")
            if not isinstance(post_ids, list) or len(post_ids) != 3:
                content = group.get("nonprod_reference_content_interaction") or {}
                post_ids = (content.get("createdObjectIdsOrHashes") or {}).get(
                    "releasePostIds"
                )
            if (
                not isinstance(post_ids, list)
                or len(post_ids) != 3
                or len({str(value).strip() for value in post_ids}) != 3
            ):
                failures.append(
                    f"candidate {key[0]} has no exact release post closure"
                )
                continue
            try:
                candidate = NonprodCandidateIdentity(
                    environment=environment,
                    target=target_name,
                    baseline_id=key[0],
                    source_revision=key[1],
                    package_digest=key[2],
                    runtime_config_digest=key[3],
                    release_id=key[4],
                    release_digest=key[5],
                    import_run_id=key[6],
                    release_post_ids=tuple(str(value).strip() for value in post_ids),
                )
                result = NonprodDataProvisioner(
                    base_url=base_url,
                    candidate=candidate,
                ).cleanup_candidate_bound_data()
            except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
                failures.append(f"candidate {key[0]} cleanup failed: {exc}")
                continue
            results.append(
                {
                    "baselineId": result["baselineId"],
                    "packageDigest": result["packageDigest"],
                    "releaseDigest": result["releaseDigest"],
                    "datasetIds": result["datasetIds"],
                    "closedActorCount": len(result["closedActorRoles"]),
                    "cleanupState": result["cleanupState"],
                    "eligibilityReasons": reasons,
                }
            )

    succeeded = not failures
    summary = (
        f"stackctl repair reconciled {len(results)} nonprod dataset candidate(s) for {target_name}"
        if succeeded
        else f"stackctl repair nonprod data is GATE_BLOCK for {target_name}"
    )
    details = failures or (
        ["no stale, expired, failed, or incomplete dataset is eligible"]
        if not results
        else [
            f"cleaned receipt-bound candidate {item['baselineId']}"
            for item in results
        ]
    )
    write_json(
        report_dir / "report.json",
        {
            "command": "repair",
            "target": target_name,
            "fix": "reconcile-nonprod-data",
            "status": "passed" if succeeded else "GATE_BLOCK",
            "destructiveRepairPerformed": bool(results),
            "results": results,
            "issues": failures,
        },
    )
    write_json(
        report_dir / "repair_plan.json",
        {
            "target": target_name,
            "fix": "reconcile-nonprod-data",
            "actions": [
                "use only receipt-owned identifiers and managed nonprod identities",
                "reverse domain objects through ContractGraph public APIs",
                "close acceptance accounts only after domain cleanup succeeds",
                "never wipe a database or mutate Prod",
            ],
        },
    )
    _write_summary_bundle(
        report_dir,
        command="repair",
        target=target_name,
        status="ok" if succeeded else "failed",
        summary=summary,
        details=details,
    )
    return {
        "exitCode": 0 if succeeded else 2,
        "summary": summary,
        "details": details,
        "reportDir": relpath(report_dir),
    }


def command_repair(args: argparse.Namespace) -> dict[str, Any]:
    topology = load_environment_topology()
    target = get_target(topology, args.target)
    env_name = str(target["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    steps: list[dict[str, Any]] = []
    if args.fix == "reconcile-nonprod-data":
        return _reconcile_nonprod_data(
            args,
            environment=env_name,
            target_name=args.target,
            report_dir=report_dir,
        )
    if args.fix == "reclaim-orphaned-processes":
        if args.target != "alpha-local":
            summary = "reclaim-orphaned-processes is only available for alpha-local"
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
            reclaimed = alpha_content_release_runtime.reclaim_orphaned_managed_processes(
                confirm=bool(
                    getattr(args, "confirm_orphaned_process_reclaim", False)
                )
            )
            occupied = [
                item
                for item in _network_report(args.target)["ports"]
                if item["open"]
            ]
            if occupied:
                raise RuntimeError(
                    "canonical Alpha ports remain occupied after orphan repair: "
                    + ", ".join(
                        f"{item['name']}:{item['port']}" for item in occupied
                    )
                )
            preserved_observability: list[str] = []
            observability_root = output_root() / "env/alpha/observability"
            if observability_root.is_dir():
                incomplete_runs = [
                    entry
                    for entry in sorted(observability_root.iterdir())
                    if entry.is_dir() and not (entry / "manifest.json").is_file()
                ]
                if incomplete_runs:
                    preservation_root = (
                        report_dir / "attachments/incomplete-observability"
                    )
                    preservation_root.mkdir(parents=True, exist_ok=True)
                    for incomplete_run in incomplete_runs:
                        destination = preservation_root / incomplete_run.name
                        if destination.exists():
                            raise RuntimeError(
                                "incomplete observability preservation target already exists: "
                                + str(destination)
                            )
                        shutil.move(str(incomplete_run), str(destination))
                        preserved_observability.append(relpath(destination))
        except RuntimeError as exc:
            summary = f"stackctl repair orphan reclaim is GATE_BLOCK for {args.target}"
            details = [str(exc)]
            write_json(
                report_dir / "report.json",
                {
                    "command": "repair",
                    "target": args.target,
                    "fix": args.fix,
                    "status": "gate_block",
                    "destructiveRepairPerformed": False,
                    "details": details,
                },
            )
            _write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=details,
            )
            return {
                "exitCode": 2,
                "summary": summary,
                "details": details,
                "reportDir": relpath(report_dir),
            }
        details = [
            f"reclaimed managed role={name} pid={record['pid']} pgid={record['pgid']}"
            for name, record in sorted(reclaimed.items())
        ] or ["no orphaned Alpha managed process matched"]
        details.extend(
            f"preserved incomplete observability as repair attachment: {path}"
            for path in preserved_observability
        )
        summary = f"stackctl repair reclaimed orphaned Alpha processes for {args.target}"
        write_json(
            report_dir / "report.json",
            {
                "command": "repair",
                "target": args.target,
                "fix": args.fix,
                "status": "passed",
                "destructiveRepairPerformed": bool(reclaimed),
                "destructiveActions": details if reclaimed else [],
                "preservedIncompleteObservability": preserved_observability,
            },
        )
        write_json(
            report_dir / "repair_plan.json",
            {
                "target": args.target,
                "fix": args.fix,
                "actions": [
                    "terminate only ledger-less Alpha wrappers matching the repository path and canonical port signatures"
                ],
            },
        )
        _write_summary_bundle(
            report_dir,
            command="repair",
            target=args.target,
            status="ok",
            summary=summary,
            details=details,
        )
        return {
            "exitCode": 0,
            "summary": summary,
            "details": details,
            "reportDir": relpath(report_dir),
        }
    if args.fix == "reclaim-build-cache":
        local_targets = {"alpha-local", "beta-local", "gamma-local"}
        if args.target not in local_targets:
            summary = (
                "reclaim-build-cache is only available for "
                "alpha-local, beta-local, or gamma-local"
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
        # A completely full BuildKit store can make the read-only `system df`
        # pre-snapshot fail because BuildKit cannot update snapshots.db.  The
        # repair has still succeeded when the allow-listed cache prune and the
        # post-repair inventory both succeed; keep the failed pre-snapshot in
        # `steps` as diagnostic evidence instead of turning a recovered host
        # into a false failure.
        succeeded = reclaim.returncode == 0 and after.returncode == 0
        summary = (
            f"{args.target} unused Docker build cache reclaimed"
            if succeeded
            else f"{args.target} Docker build cache reclaim failed"
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
    if args.fix == "restart-stack":
        # Restart is destructive for local state. Validate every external
        # deployment prerequisite before stopping a currently running stack;
        # otherwise a failed `up` would turn a partial outage into a full one.
        if args.target in {"alpha-local", "beta-local", "gamma-local"}:
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
        if int(down_payload.get("exitCode") or 0) != 0:
            steps = [down_payload]
            summary = (
                f"stackctl repair restart-stack stopped after down failure for "
                f"{args.target}"
            )
            write_json(
                report_dir / "report.json",
                {
                    "command": "repair",
                    "target": args.target,
                    "fix": args.fix,
                    "status": "failed",
                    "steps": steps,
                },
            )
            write_json(
                report_dir / "repair_plan.json",
                {
                    "target": args.target,
                    "fix": args.fix,
                    "actions": [
                        "resolve the recorded down failure",
                        "rerun restart-stack only after resources are stopped",
                    ],
                },
            )
            _write_summary_bundle(
                report_dir,
                command="repair",
                target=args.target,
                status="failed",
                summary=summary,
                details=[str(down_payload.get("summary") or "down failed")],
            )
            return {
                "exitCode": int(down_payload.get("exitCode") or 1),
                "summary": summary,
                "details": [str(down_payload.get("summary") or "down failed")],
                "reportDir": relpath(report_dir),
            }
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


_REQUIRED_RELEASE_EVIDENCE = {
    "contractGraph",
    "providerEvidence",
    "testEvidence",
}


def _validate_release_artifacts(
    manifest: dict[str, Any],
    *,
    artifact_root: Path,
) -> None:
    if set(finalize_mainline_release_artifact.REQUIRED_RELEASE_EVIDENCE) != (
        _REQUIRED_RELEASE_EVIDENCE
    ):
        raise RuntimeError("release evidence set differs from the canonical contract")
    try:
        finalize_mainline_release_artifact.validate_manifest_files(
            artifact_root,
            manifest,
        )
    except ValueError as error:
        raise RuntimeError(f"release evidence files are invalid: {error}") from error


def _release_transport_tag(manifest: dict[str, Any]) -> str:
    tags: set[str] = set()
    for service, descriptor in manifest["images"].items():
        repository = str(descriptor["repository"])
        transport_ref = str(descriptor["transportRef"])
        prefix = repository + ":"
        if not transport_ref.startswith(prefix):
            raise RuntimeError(
                f"release evidence image transport reference is invalid: {service}"
            )
        tags.add(transport_ref.removeprefix(prefix))
    if len(tags) != 1:
        raise RuntimeError("release evidence images must share one transport tag")
    return next(iter(tags))


def _deployable_release_manifest(
    path_value: str,
    *,
    candidate_digest: str,
) -> tuple[Path, str, dict[str, Any]]:
    path = Path(path_value).expanduser().resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"release manifest unreadable: {error}") from error
    if not isinstance(manifest, dict):
        raise RuntimeError("release manifest must be an object")
    try:
        finalize_mainline_release_artifact.validate_manifest(
            manifest,
            allowed_statuses={"deployable"},
        )
    except ValueError as error:
        raise RuntimeError(f"release evidence manifest is not deployable: {error}") from error
    declared_digest = str(manifest["artifactDigest"])
    if candidate_digest != str(manifest["candidateId"]):
        raise RuntimeError("release candidate digest does not match reviewed evidence")
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
        or governance.get("artifactDigest") != declared_digest
        or not governance.get("approvers")
        or len(set(governance.get("distinctPrincipals") or [])) < 2
    ):
        raise RuntimeError("release governance receipt does not bind this reviewed artifact")
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
    try:
        finalize_mainline_release_artifact.validate_manifest(
            manifest,
            allowed_statuses={"deployable"},
        )
        finalize_mainline_release_artifact.validate_manifest_files(
            path.parent,
            manifest,
        )
    except ValueError as error:
        raise RuntimeError(
            f"prevalidation requires canonical deployable release evidence: {error}"
        ) from error
    declared_digest = str(manifest["artifactDigest"])
    source = manifest.get("source")
    source_sha = str(source.get("gitSha") or "") if isinstance(source, dict) else ""
    repository = str(source.get("repository") or "") if isinstance(source, dict) else ""
    workflow_run_id = (
        str(source.get("workflowRunId") or "") if isinstance(source, dict) else ""
    )
    if (
        re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_sha) is None
        or not repository
        or not workflow_run_id
    ):
        raise RuntimeError("release manifest source is not a Service Pipeline commit")
    image_transport_tag = _release_transport_tag(manifest)
    candidate_digest = str(manifest["candidateId"])
    required_images = manifest["requiredEvidence"]["images"]
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
    head = run(["git", "rev-parse", "HEAD"])
    if head.returncode != 0 or head.stdout.strip() != source_sha:
        raise RuntimeError("release manifest source SHA does not match checked-out code")
    dirty = run(["git", "status", "--porcelain", "--untracked-files=normal"])
    if dirty.returncode != 0 or dirty.stdout.strip():
        raise RuntimeError("prod-hosted prevalidation refuses an uncommitted worktree")
    reviewed_main = run(["git", "merge-base", "--is-ancestor", source_sha, "origin/main"])
    if reviewed_main.returncode != 0:
        raise RuntimeError("release manifest source is not present on reviewed origin/main")
    return path, declared_digest, manifest, image_transport_tag, candidate_digest


def _verify_release_registry_attestations(
    manifest: dict[str, Any], *, deadline_epoch: int
) -> None:
    images = manifest.get("images")
    if not isinstance(images, dict):
        raise RuntimeError("release manifest images are missing")
    source = manifest.get("source")
    repository = str(source.get("repository") or "") if isinstance(source, dict) else ""
    signer_workflow = f"{repository}/.github/workflows/service_pipeline.yml"
    verification_inputs: list[tuple[str, str]] = []
    for service, image in images.items():
        if not isinstance(image, dict):
            raise RuntimeError(f"release manifest image is invalid: {service}")
        verification_inputs.append((str(service), str(image.get("ref") or "")))

    def verify_one(service: str, ref: str) -> None:
        try:
            oci_supply_chain.verify_oci_supply_chain(
                ref,
                repository=repository,
                signer_workflow=signer_workflow,
                timeout_seconds=_remaining_deadline_seconds(
                    deadline_epoch, "Prod registry signed-attestation verification"
                ),
            )
        except (
            OSError,
            ValueError,
            RuntimeError,
            subprocess.TimeoutExpired,
        ) as error:
            raise RuntimeError(
                f"OCI signed SBOM/provenance verification failed for {service}: {error}"
            ) from error

    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(8, max(1, len(verification_inputs))),
        thread_name_prefix="prod-oci-attestation",
    ) as executor:
        futures = {
            executor.submit(verify_one, service, ref): service
            for service, ref in verification_inputs
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except RuntimeError as error:
                failures.append(str(error))
    if failures:
        raise RuntimeError("; ".join(sorted(failures)))


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


def _emit_prod_gray_canary_traffic(
    canary: dict[str, Any], *, deadline_epoch: int
) -> dict[str, Any]:
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
        request_timeout = min(
            5.0,
            _remaining_deadline_seconds(deadline_epoch, "Prod canary traffic"),
        )
        request = urllib.request.Request(
            f"{api_base}{path}",
            headers={**headers, "User-Agent": "quwoquan-release-canary/1"},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=max(0.05, request_timeout)
            ) as response:
                if response.status < 200 or response.status >= 300:
                    raise RuntimeError(
                        f"synthetic canary request {index + 1} returned {response.status}"
                    )
        except OSError as error:
            raise RuntimeError(
                f"synthetic canary request {index + 1}/{requests} failed: {error}"
            ) from error
        if interval_ms > 0 and index + 1 < requests:
            sleep_seconds = interval_ms / 1000
            remaining = _remaining_deadline_seconds(
                deadline_epoch, "Prod canary traffic"
            )
            if sleep_seconds >= remaining:
                raise RuntimeError("Prod canary interval would cross promotion cutoff")
            time.sleep(sleep_seconds)
    return {
        "source": "prod-public-api",
        "path": path,
        "requests": requests,
        "headers": sorted(headers),
        "durationMs": int((time.monotonic() - started) * 1000),
    }


def _prometheus_query_value(
    base_url: str, expression: str, *, deadline_epoch: int
) -> float:
    request_url = f"{base_url.rstrip('/')}/api/v1/query?{urllib.parse.urlencode({'query': expression})}"
    request = urllib.request.Request(request_url, headers={"Accept": "application/json"})
    try:
        timeout = min(
            5.0,
            _remaining_deadline_seconds(deadline_epoch, "Prometheus SLO readback"),
        )
        with urllib.request.urlopen(request, timeout=max(0.05, timeout)) as response:
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


def _read_prometheus_slo(
    base_url: str, service: str, *, deadline_epoch: int
) -> dict[str, Any]:
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
    values = {
        name: _prometheus_query_value(
            base_url, expression, deadline_epoch=deadline_epoch
        )
        for name, expression in queries.items()
    }
    if values["sampleCount"] < minimum_samples:
        raise _SloSamplesInsufficient(
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
        base_url,
        service,
        window,
        readback_policy.get("recommendation"),
        deadline_epoch=deadline_epoch,
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
    *,
    deadline_epoch: int,
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
        name: _prometheus_query_value(
            base_url, expression, deadline_epoch=deadline_epoch
        )
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
    if "decision=pause reason=insufficient_samples" in output:
        return "pause", "SLO sample evidence is insufficient; promotion remains paused"
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
    rollback_started_at = ""
    rollback_ended_at = ""
    rollback_duration_ms = 0
    rollback_deadline_epoch = 0
    rollback_reason = ""
    rollback_state: dict[str, str] | None = None
    rollout_decision = "continue"
    rollout_stage = ""
    dry_run_requested = str(getattr(args, "dry_run", "false")).strip().lower() == "true"
    slo_readback: dict[str, Any] | None = None
    prometheus_url = ""
    release_manifest_path: Path | None = None
    release_artifact_digest = ""
    release_manifest_payload: dict[str, Any] = {}
    expected_generation = 0
    transition_action = "advance"
    release_receipt_id = ""
    committed_release_state: dict[str, str] | None = None
    release_receipt_path: Path | None = None
    release_state_snapshot: dict[str, str] = {}
    release_candidate_digests: dict[str, str] = {}
    from_release_evidence_ref = ""
    to_release_evidence_ref = ""
    from_image_transport_tag = ""
    to_image_transport_tag = ""
    last_good_candidate_digest = ""
    gray_canary_contract: dict[str, Any] | None = None
    gray_canary_traffic: dict[str, Any] | None = None
    provider_readiness: dict[str, Any] = {}
    promotion_deadline_epoch = int(
        getattr(args, "promotion_deadline_epoch", 0) or 0
    )
    hard_deadline_epoch = int(getattr(args, "hard_deadline_epoch", 0) or 0)
    rollback_budget_seconds = int(
        getattr(args, "rollback_budget_seconds", 300) or 0
    )
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
        if not dry_run_requested and (
            promotion_deadline_epoch <= 0
            or hard_deadline_epoch <= promotion_deadline_epoch
            or rollback_budget_seconds <= 0
            or hard_deadline_epoch - promotion_deadline_epoch
            < rollback_budget_seconds
        ):
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: canonical Prod deadlines are required",
                "details": [],
                **timing,
            }
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
            args.from_candidate_digest,
            args.to_candidate_digest,
            args.release_evidence_ref,
            args.step,
        ]
        if not all(required):
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy prod-hosted requires candidate digests, exact release evidence and step",
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
                release_artifact_digest,
                release_manifest_payload,
            ) = _deployable_release_manifest(
                manifest_value,
                candidate_digest=args.to_candidate_digest,
            )
            for label, value in (
                ("from candidate", args.from_candidate_digest),
                ("to candidate", args.to_candidate_digest),
            ):
                if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                    raise RuntimeError(f"{label} digest is invalid")
            if not dry_run_requested:
                release_candidate_digests = _required_release_candidate_digests(
                    args,
                    release_manifest_payload,
                )
            release_state_snapshot, _ = _fetch_hosted_release_ledger_projection(
                args.service,
                allow_uninitialized=False,
                deadline_epoch=promotion_deadline_epoch,
            )
            to_release_evidence_ref = str(args.release_evidence_ref).strip()
            if re.fullmatch(
                r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}",
                to_release_evidence_ref,
            ) is None:
                raise RuntimeError("target release evidence ref is not exact OCI")
            to_image_transport_tag = _release_transport_tag(
                release_manifest_payload
            )
            if release_state_snapshot.get("to_candidate_digest") == args.to_candidate_digest:
                restored_candidate_noop = (
                    release_state_snapshot.get("decision") == "rolled_back"
                    and args.from_candidate_digest == args.to_candidate_digest
                )
                from_release_evidence_ref = release_state_snapshot.get(
                    (
                        "to_release_evidence_ref"
                        if restored_candidate_noop
                        else "from_release_evidence_ref"
                    ),
                    "",
                )
                from_image_transport_tag = release_state_snapshot.get(
                    (
                        "to_image_transport_tag"
                        if restored_candidate_noop
                        else "from_image_transport_tag"
                    ),
                    "",
                )
                if (
                    release_state_snapshot.get("to_release_evidence_ref")
                    != to_release_evidence_ref
                    or release_state_snapshot.get("to_image_transport_tag")
                    != to_image_transport_tag
                ):
                    raise RuntimeError(
                        "hosted ledger target transport does not match resume candidate"
                    )
            else:
                from_release_evidence_ref = release_state_snapshot.get(
                    "to_release_evidence_ref", ""
                )
                from_image_transport_tag = release_state_snapshot.get(
                    "to_image_transport_tag", ""
                )
            if (
                re.fullmatch(
                    r"ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}",
                    from_release_evidence_ref,
                )
                is None
                or not from_image_transport_tag
            ):
                raise RuntimeError(
                    "hosted ledger lacks canonical source transport metadata; historical cutover is required"
                )
            # The deployment adapter still needs transport coordinates, but
            # callers can no longer supply them as release identity. They are
            # derived exclusively from the two candidate authorities.
            last_good_candidate_digest = release_state_snapshot.get(
                "last_good_candidate_digest",
                args.from_candidate_digest,
            )
            transition_action, expected_generation = _validate_release_transition(
                release_state_snapshot,
                from_candidate_digest=args.from_candidate_digest,
                to_candidate_digest=args.to_candidate_digest,
                stage=rollout_stage,
            )
            if not dry_run_requested:
                _verify_release_registry_attestations(
                    release_manifest_payload,
                    deadline_epoch=promotion_deadline_epoch,
                )
                _archive_release_artifact(
                    release_manifest_path,
                    release_artifact_digest,
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
                f"{args.service}\0{release_artifact_digest}\0{rollout_stage}\0"
                f"{expected_generation + (0 if transition_action == 'replay' else 1)}"
            ).encode("utf-8")
        ).hexdigest()
        if transition_action == "replay" and not dry_run_requested:
            release_receipt_id = release_state_snapshot.get("receipt_id", "")
            if not release_receipt_id:
                timing = _finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy blocked: hosted ledger receipt identity is missing",
                    "details": [],
                    **timing,
                }
            try:
                # Recovery must be reconstructable from the hosted authority.
                # A disposable local receipt from an earlier runner is never a
                # prerequisite for replay.
                release_receipt_path = _sync_release_ledger_projection(
                    args.service,
                    release_receipt_id,
                    deadline_epoch=promotion_deadline_epoch,
                )
            except RuntimeError as error:
                timing = _finish_timing(started_monotonic, started_at)
                return {
                    "exitCode": 2,
                    "summary": "stackctl deploy replay could not sync release projection",
                    "details": [str(error)],
                    **timing,
                }
            hosted_receipt = _read_json_object(str(release_receipt_path))
            timing = _finish_timing(started_monotonic, started_at)
            replay_payload = {
                "command": "deploy",
                "target": args.target,
                "argv": [],
                "exitCode": 0,
                "stdout": "hosted release ledger replay matched",
                "stderr": "",
                "rolloutStage": rollout_stage,
                "rolloutDecision": hosted_receipt.get("decision"),
                "artifactDigest": release_artifact_digest,
                "candidateId": release_manifest_payload.get("candidateId"),
                "releaseReceiptId": release_receipt_id,
                "releaseReceiptRef": f"receipt:hosted:{release_receipt_id}",
                "releaseReceiptAuthority": "prod-hosted-service-plane",
                "releaseReceiptPath": str(release_receipt_path),
                "releaseState": release_state_snapshot,
                "wiredWorkloads": _prod_rollout_workloads(),
                "providerReadiness": provider_readiness,
                "postDeployChecks": [],
                "postDeployFailures": [],
                "rollbackPostChecks": [],
                "sloReadback": hosted_receipt.get("sloReadback") or {},
                "dryRun": False,
                "replayed": True,
                "rollback": {"triggered": False, "reason": "", "result": {}, "releaseState": {}},
                **timing,
            }
            write_json(report_dir / "report.json", replay_payload)
            return {
                "exitCode": 0,
                "summary": "stackctl deploy replay matched committed release ledger",
                "details": [f"receipt: {release_receipt_id}"],
                "releaseReceiptId": release_receipt_id,
                **timing,
            }
        if not dry_run_requested:
            try:
                _remaining_deadline_seconds(
                    promotion_deadline_epoch, "Prod promotion cutoff"
                )
            except RuntimeError as error:
                active_candidate = (
                    release_state_snapshot.get("to_candidate_digest")
                    == args.to_candidate_digest
                    and release_state_snapshot.get("last_good_candidate_digest")
                    == args.from_candidate_digest
                    and release_state_snapshot.get("stage")
                    in {"gray-initial", "carry-on"}
                )
                if active_candidate:
                    force_deadline_rollback = True
                else:
                    timing = _finish_timing(started_monotonic, started_at)
                    return {
                        "exitCode": 2,
                        "summary": "stackctl deploy blocked: promotion cutoff reached before mutation",
                        "details": [str(error)],
                        **timing,
                    }
        try:
            package_binding = _materialize_release_evidence_configuration(
                "prod", target=args.target
            )
            if package_binding.get("candidateId") != args.to_candidate_digest:
                raise ValueError(
                    "fixed prod package does not bind the rollout candidate"
                )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl deploy blocked: fixed prod package is invalid",
                "details": [str(error)],
                **timing,
            }
        cmd: list[str] = []
        if force_deadline_rollback:
            deploy_result = subprocess.CompletedProcess(
                ["prod-apply"],
                0,
                stdout="promotion cutoff reached while a candidate stage is active",
                stderr="",
            )
            result = subprocess.CompletedProcess(
                ["promotion-deadline"],
                12,
                stdout="decision=rollback",
                stderr="promotion cutoff reached; reserved time is now rollback-only",
            )
        elif transition_action == "reevaluate" and not dry_run_requested:
            deploy_result = subprocess.CompletedProcess(
                ["prod-apply"],
                0,
                stdout="paused hosted stage re-evaluation reused the existing apply",
                stderr="",
            )
        else:
            try:
                apply_timeout = (
                    _remaining_deadline_seconds(
                        promotion_deadline_epoch, "Prod promotion cutoff"
                    )
                    if not dry_run_requested
                    else None
                )
            except RuntimeError as error:
                apply_timeout = 0.001
            deploy_result = run(
                ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
                env={
                    "CLOUD_PROVIDER": args.cloud_provider,
                    "SERVICE": args.service,
                    "IMAGE_TRANSPORT_TAG": to_image_transport_tag,
                    "CANDIDATE_DIGEST": args.to_candidate_digest,
                    "PREVIOUS_IMAGE_TRANSPORT_TAG": from_image_transport_tag,
                    "ROLLOUT_STAGE": rollout_stage,
                    "DRY_RUN": args.dry_run,
                    "RELEASE_MANIFEST": str(release_manifest_path),
                    "RELEASE_EVIDENCE_DIGEST": release_artifact_digest,
                },
                timeout_seconds=apply_timeout,
            )
        if force_deadline_rollback:
            pass
        elif deploy_result.returncode != 0:
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
                    gray_canary_contract,
                    deadline_epoch=promotion_deadline_epoch,
                )
                settle_seconds = _slo_settle_seconds(rollout_stage)
                if settle_seconds:
                    remaining = _remaining_deadline_seconds(
                        promotion_deadline_epoch, "Prod promotion cutoff"
                    )
                    if settle_seconds >= remaining:
                        raise RuntimeError(
                            "SLO settle interval would cross the Prod promotion cutoff"
                        )
                    time.sleep(settle_seconds)
                slo_service = (
                    "content-service"
                    if args.service == PROD_RELEASE_UNIT
                    else args.service
                )
                slo_readback = _read_prometheus_slo(
                    prometheus_url,
                    slo_service,
                    deadline_epoch=promotion_deadline_epoch,
                )
                slo_readback["canaryTraffic"] = gray_canary_traffic
            except _SloSamplesInsufficient as error:
                slo_readback = {
                    "canaryTraffic": gray_canary_traffic or {},
                    "status": "insufficient_samples",
                    "error": str(error),
                }
                result = subprocess.CompletedProcess(
                    ["prometheus-slo-readback"],
                    10,
                    stdout="decision=pause reason=insufficient_samples",
                    stderr=str(error),
                )
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
                    "--step",
                    args.step,
                    "--error-rate",
                    args.error_rate,
                    "--p95-ms",
                    args.p95_ms,
                    "--redis-error-rate",
                    args.redis_error_rate,
                ]
                try:
                    gate_timeout = _remaining_deadline_seconds(
                        promotion_deadline_epoch, "Prod promotion cutoff"
                    )
                except RuntimeError as error:
                    result = subprocess.CompletedProcess(
                        cmd,
                        12,
                        stdout="decision=rollback",
                        stderr=str(error),
                    )
                else:
                    gate_result = run(cmd, timeout_seconds=gate_timeout)
                    result = (
                        gate_result
                        if gate_result.returncode == 0
                        else subprocess.CompletedProcess(
                            gate_result.args,
                            gate_result.returncode,
                            stdout="decision=rollback\n" + gate_result.stdout,
                            stderr=gate_result.stderr,
                        )
                    )
    run_post_deploy_checks = result.returncode == 0 and not (
        args.target == "prod-hosted" and dry_run_requested
    )
    if run_post_deploy_checks:
        def _deploy_health_args(
            target_name: str,
            scope_name: str,
            out_dir: Path,
            *,
            deadline_epoch: int,
        ) -> argparse.Namespace:
            return argparse.Namespace(
                command="health",
                target=target_name,
                scope=scope_name,
                output_format="json",
                report_dir=str(out_dir),
                request_timeout_seconds=0,
                retry_attempts=0,
                retry_sleep_seconds=-1.0,
                deadline_epoch=deadline_epoch,
            )

        for nested_command, nested_scope in (("health", "full"),):
            nested_dir = report_dir / nested_command
            if nested_command == "health":
                nested_args = _deploy_health_args(
                    args.target,
                    nested_scope,
                    nested_dir,
                    deadline_epoch=promotion_deadline_epoch,
                )
                post_deploy_checks.append(command_health(nested_args))
        if args.target == "prod-hosted" and rollout_stage == "gray-initial":
            nested_dir = report_dir / "environment-page-smoke"
            verify_command = [
                "python3",
                "quwoquan_ops/cli/stackctl.py",
                "verify",
                "--target",
                args.target,
                "--kind",
                "topology",
                "--profile",
                "release",
                "--report-dir",
                str(nested_dir),
                "--output-format",
                "json",
            ]
            verify_result = run(
                verify_command,
                timeout_seconds=_remaining_deadline_seconds(
                    promotion_deadline_epoch,
                    "Prod release environment verification",
                ),
            )
            try:
                verify_payload = json.loads(verify_result.stdout)
            except json.JSONDecodeError:
                verify_payload = {
                    "exitCode": verify_result.returncode,
                    "summary": "bounded Prod release environment verification failed",
                    "details": _command_details(verify_result),
                }
            post_deploy_checks.append(verify_payload)
        if args.target == "prod-hosted":
            post_deploy_checks.extend(
                _prod_hosted_placement_coverage_checks(
                    report_dir,
                    stage=rollout_stage,
                    host=str(getattr(args, "ssh_host", "") or ""),
                    host_id=(
                        str((getattr(args, "host_id", None) or [""])[0])
                        if isinstance(getattr(args, "host_id", None), list)
                        else str(getattr(args, "host_id", "") or "")
                    ),
                )
            )
    post_deploy_failures = [
        item["summary"]
        for item in post_deploy_checks
        if not _check_exit_passed(item)
    ]
    final_exit_code = result.returncode
    findings = list(post_deploy_failures)
    if final_exit_code == 0 and post_deploy_failures:
        final_exit_code = 1
    if (
        args.target == "prod-hosted"
        and not dry_run_requested
        and final_exit_code == 0
    ):
        try:
            _remaining_deadline_seconds(
                promotion_deadline_epoch, "Prod promotion cutoff"
            )
        except RuntimeError as error:
            result = subprocess.CompletedProcess(
                result.args,
                12,
                stdout="decision=rollback\n" + (result.stdout or ""),
                stderr="\n".join(filter(None, [result.stderr, str(error)])),
            )
            final_exit_code = 12
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
            rollback_started_at = utc_now()
            rollback_started_monotonic = time.monotonic()
            rollback_deadline_epoch = min(
                hard_deadline_epoch,
                int(time.time()) + rollback_budget_seconds,
            )
            rollback_env = {
                "CLOUD_PROVIDER": args.cloud_provider,
                "SERVICE": args.service,
                "IMAGE_TRANSPORT_TAG": from_image_transport_tag,
                "CANDIDATE_DIGEST": args.from_candidate_digest,
                "PREVIOUS_IMAGE_TRANSPORT_TAG": to_image_transport_tag,
                "ROLLOUT_STAGE": "full",
                "DRY_RUN": "false",
                "PROD_IMAGE_DELIVERY_MODE": "skip",
            }
            try:
                rollback_timeout = min(
                    float(rollback_budget_seconds),
                    _remaining_deadline_seconds(
                        rollback_deadline_epoch, "Prod rollback recovery"
                    ),
                )
            except RuntimeError as error:
                rollback_result = subprocess.CompletedProcess(
                    ["prod-rollback"], 124, stdout="", stderr=str(error)
                )
            else:
                rollback_result = run(
                    ["bash", "quwoquan_ops/cli/prod/deploy_to_prod.sh"],
                    env=rollback_env,
                    timeout_seconds=rollback_timeout,
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
                            request_timeout_seconds=0,
                            retry_attempts=0,
                            retry_sleep_seconds=-1.0,
                            deadline_epoch=rollback_deadline_epoch,
                        )
                        rollback_post_checks.append(command_health(nested_args))
                rollback_failures = [
                    item["summary"]
                    for item in rollback_post_checks
                    if not _check_exit_passed(item)
                ]
                findings.extend(f"rollback {item}" for item in rollback_failures)
                if rollback_failures and final_exit_code == 0:
                    final_exit_code = 1
                rollback_duration_ms = int(
                    (time.monotonic() - rollback_started_monotonic) * 1000
                )
                rollback_ended_at = utc_now()
                rollback_evidence = {
                    "triggered": True,
                    "startedAt": rollback_started_at,
                    "endedAt": rollback_ended_at,
                    "durationMs": rollback_duration_ms,
                    "postChecks": _release_check_receipts(rollback_post_checks),
                }
                rollback_decision = (
                    "rollback_failed" if rollback_failures else "rolled_back"
                )
                rollback_succeeded = rollback_decision == "rolled_back"
                rollback_state, release_receipt_path = _commit_hosted_release_transition(
                    service=args.service,
                    from_candidate_digest=(
                        args.to_candidate_digest
                        if rollback_succeeded
                        else args.from_candidate_digest
                    ),
                    to_candidate_digest=(
                        args.from_candidate_digest
                        if rollback_succeeded
                        else args.to_candidate_digest
                    ),
                    step="100" if rollback_succeeded else args.step,
                    stage="full" if rollback_succeeded else rollout_stage,
                    decision=rollback_decision,
                    artifact_digest=release_artifact_digest,
                    expected_generation=expected_generation,
                    receipt_id=release_receipt_id,
                    slo_readback=slo_readback,
                    candidate_digests=release_candidate_digests,
                    last_good_candidate_digest=args.from_candidate_digest,
                    post_deploy_checks=post_deploy_checks + rollback_post_checks,
                    rollback_outcome=rollback_decision,
                    rollback_evidence=rollback_evidence,
                    from_release_evidence_ref=(
                        to_release_evidence_ref
                        if rollback_succeeded
                        else from_release_evidence_ref
                    ),
                    to_release_evidence_ref=(
                        from_release_evidence_ref
                        if rollback_succeeded
                        else to_release_evidence_ref
                    ),
                    from_image_transport_tag=(
                        to_image_transport_tag
                        if rollback_succeeded
                        else from_image_transport_tag
                    ),
                    to_image_transport_tag=(
                        from_image_transport_tag
                        if rollback_succeeded
                        else to_image_transport_tag
                    ),
                    deadline_epoch=rollback_deadline_epoch,
                    trigger_stage=rollout_stage,
                )
                committed_release_state = rollback_state
                # The execution/readiness interval is sealed before commit;
                # hosted verifiedAt separately proves durable authority writeback.
                if rollback_duration_ms > rollback_budget_seconds * 1000:
                    findings.append(
                        "rollback exceeded the deterministic recovery budget"
                    )
                    final_exit_code = 1
                if time.time() > hard_deadline_epoch:
                    findings.append(
                        "rollback authority readback completed after the hard release deadline"
                    )
                    final_exit_code = 1
            else:
                findings.append("live rollback apply failed")
                final_exit_code = rollback_result.returncode
                rollback_duration_ms = int(
                    (time.monotonic() - rollback_started_monotonic) * 1000
                )
                rollback_ended_at = utc_now()
                committed_release_state, release_receipt_path = _commit_hosted_release_transition(
                    service=args.service,
                    from_candidate_digest=args.from_candidate_digest,
                    to_candidate_digest=args.to_candidate_digest,
                    step=args.step,
                    stage=rollout_stage,
                    decision="rollback_failed",
                    artifact_digest=release_artifact_digest,
                    expected_generation=expected_generation,
                    receipt_id=release_receipt_id,
                    slo_readback=slo_readback,
                    candidate_digests=release_candidate_digests,
                    last_good_candidate_digest=last_good_candidate_digest,
                    post_deploy_checks=post_deploy_checks + rollback_post_checks,
                    rollback_outcome="rollback_failed",
                    rollback_evidence={
                        "triggered": True,
                        "startedAt": rollback_started_at,
                        "endedAt": rollback_ended_at,
                        "durationMs": rollback_duration_ms,
                        "postChecks": _release_check_receipts(rollback_post_checks),
                    },
                    from_release_evidence_ref=from_release_evidence_ref,
                    to_release_evidence_ref=to_release_evidence_ref,
                    from_image_transport_tag=from_image_transport_tag,
                    to_image_transport_tag=to_image_transport_tag,
                    deadline_epoch=rollback_deadline_epoch,
                    trigger_stage=rollout_stage,
                )
        elif rollout_decision == "pause" and final_exit_code == 10:
            final_exit_code = 10
            if not dry_run_requested:
                committed_release_state, release_receipt_path = _commit_hosted_release_transition(
                    service=args.service,
                    from_candidate_digest=args.from_candidate_digest,
                    to_candidate_digest=args.to_candidate_digest,
                    step=args.step,
                    stage=rollout_stage,
                    decision="pause",
                    artifact_digest=release_artifact_digest,
                    expected_generation=expected_generation,
                    receipt_id=release_receipt_id,
                    slo_readback=slo_readback,
                    candidate_digests=release_candidate_digests,
                    last_good_candidate_digest=last_good_candidate_digest,
                    post_deploy_checks=post_deploy_checks,
                    rollback_outcome="not_triggered",
                    rollback_evidence={"triggered": False},
                    from_release_evidence_ref=from_release_evidence_ref,
                    to_release_evidence_ref=to_release_evidence_ref,
                    from_image_transport_tag=from_image_transport_tag,
                    to_image_transport_tag=to_image_transport_tag,
                    deadline_epoch=promotion_deadline_epoch,
                )
        elif final_exit_code == 0 and not dry_run_requested:
            committed_last_good_candidate_digest = (
                args.to_candidate_digest
                if rollout_stage == "full"
                else last_good_candidate_digest
            )
            committed_release_state, release_receipt_path = _commit_hosted_release_transition(
                service=args.service,
                from_candidate_digest=args.from_candidate_digest,
                to_candidate_digest=args.to_candidate_digest,
                step=args.step,
                stage=rollout_stage,
                decision="continue",
                artifact_digest=release_artifact_digest,
                expected_generation=expected_generation,
                receipt_id=release_receipt_id,
                slo_readback=slo_readback,
                candidate_digests=release_candidate_digests,
                last_good_candidate_digest=committed_last_good_candidate_digest,
                post_deploy_checks=post_deploy_checks,
                rollback_outcome="not_triggered",
                rollback_evidence={"triggered": False},
                from_release_evidence_ref=from_release_evidence_ref,
                to_release_evidence_ref=to_release_evidence_ref,
                from_image_transport_tag=from_image_transport_tag,
                to_image_transport_tag=to_image_transport_tag,
                deadline_epoch=promotion_deadline_epoch,
            )
        if committed_release_state is not None:
            release_receipt_id = committed_release_state["receipt_id"]
            if release_receipt_path is None:
                release_receipt_path = _sync_release_ledger_projection(
                    args.service,
                    release_receipt_id,
                    deadline_epoch=(
                        rollback_deadline_epoch
                        if rollback_reason
                        else promotion_deadline_epoch
                    ),
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
            "triggerStage": (
                (committed_release_state or {}).get("trigger_stage")
                or rollout_stage
            ),
            "terminalStage": (
                (committed_release_state or {}).get("stage")
                or rollout_stage
            ),
            "rolloutDecision": rollout_decision,
            "artifactDigest": release_artifact_digest,
            "releaseEvidenceRef": to_release_evidence_ref,
            "candidateId": (
                release_manifest_payload.get("candidateId")
                if release_manifest_payload
                else ""
            ),
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
                "startedAt": rollback_started_at,
                "endedAt": rollback_ended_at,
                "durationMs": rollback_duration_ms,
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
    image_transport_tag: str,
    candidate_digest: str,
    dry_run: bool,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    argv = [
        "python3",
        "quwoquan_ops/cli/prod/prevalidate_prod_hosted.py",
        "--release-manifest",
        str(manifest_path),
        "--image-transport-tag",
        image_transport_tag,
        "--candidate-digest",
        candidate_digest,
        "--data-mode",
        str(args.data_mode),
        "--scope",
        str(args.prevalidate_scope),
    ]
    if args.ssh_host:
        argv.extend(["--host", str(args.ssh_host)])
    for host_id in getattr(args, "host_id", []) or []:
        argv.extend(["--host-id", str(host_id)])
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
            "from_candidate_digest",
            "to_candidate_digest",
            "release_evidence_ref",
            "step",
            "prometheus_url",
            "release_image_digest",
            "release_config_digest",
            "contract_graph_digest",
            "adapter_digest",
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
    if ssh_host and (
        "://" in ssh_host
        or re.fullmatch(r"[A-Za-z0-9.-]+", ssh_host) is None
    ):
        request_issues.append("prevalidate --ssh-host must be a valid SSH-only host")
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
    artifact_digest = ""
    manifest_payload: dict[str, Any] = {}
    image_transport_tag = "unresolved"
    candidate_digest = "unresolved"
    if not manifest_value:
        request_issues.append("immutable Service Pipeline --release-manifest is required")
    else:
        try:
            (
                manifest_path,
                artifact_digest,
                manifest_payload,
                image_transport_tag,
                candidate_digest,
            ) = _prevalidation_release_manifest(manifest_value)
        except RuntimeError as error:
            request_issues.append(str(error))

    host_payload: dict[str, Any] = {}
    host_result: subprocess.CompletedProcess[str] | None = None
    if args.data_mode and args.prevalidate_scope:
        host_result, host_payload = _prod_prevalidation_executor(
            args,
            manifest_path=manifest_path,
            image_transport_tag=image_transport_tag,
            candidate_digest=candidate_digest,
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
                image_transport_tag=image_transport_tag,
                candidate_digest=candidate_digest,
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
        "releaseEvidence": {
            "path": str(manifest_path) if manifest_value else "",
            "artifactDigest": artifact_digest,
            "candidateId": manifest_payload.get("candidateId") or "",
            "source": manifest_payload.get("source") or {},
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
            candidate_digest = (
                str(release_payload.get("candidateId") or "")
                if isinstance(release_payload, dict)
                else ""
            )
            _deployable_release_manifest(
                release_manifest,
                candidate_digest=candidate_digest,
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
            f"artifactDigest={receipt.get('artifactDigest')}",
            f"candidateId={receipt.get('candidateId')}",
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
            and receipt.get("lastGoodCandidateDigest")
            == receipt.get("toCandidateDigest")
        ):
            raise RuntimeError("hosted receipt is not a stable full last-good release")
        if purpose == "rollback" and not (
            receipt.get("decision") == "rolled_back"
            and receipt.get("rollbackOutcome") == "rolled_back"
            and receipt.get("lastGoodCandidateDigest")
            == receipt.get("toCandidateDigest")
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


def _public_url_origin(raw_url: str) -> str:
    parsed = urllib.parse.urlsplit(raw_url)
    if parsed.scheme not in {"https", "wss"} or not parsed.netloc:
        raise RuntimeError(f"GATE_BLOCK: invalid public URL projection: {raw_url!r}")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


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
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL": _public_url_origin(
            str(public_bases["mediaImage"])
        ),
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
    }


def _formal_release_compose_project_name(target_name: str) -> str:
    run_id = re.sub(r"[^a-zA-Z0-9_-]", "", os.environ.get("GITHUB_RUN_ID", ""))
    attempt = re.sub(
        r"[^a-zA-Z0-9_-]", "", os.environ.get("GITHUB_RUN_ATTEMPT", "")
    )
    environment_name = target_name.removesuffix("-local")
    suffix = f"_{run_id}_{attempt}" if run_id and attempt else ""
    return f"quwoquan_{environment_name}_release{suffix}"


def _gamma_env_from_port_manifest(topology: dict[str, Any], target_name: str) -> dict[str, str]:
    """Project any Alpha/Beta/Gamma local target into the shared OCI runtime."""

    manifest = load_port_manifest()
    profile_name = str(get_target(topology, target_name).get("portProfile"))
    ports = profile_ports(manifest, profile_name)
    target = get_target(topology, target_name)
    environment_name = str(target["env"])
    if environment_name not in {"alpha", "beta", "gamma"}:
        raise RuntimeError(
            f"GATE_BLOCK: shared local release runtime does not support {target_name}"
        )
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
        "CONTENT_MEDIA_DELIVERY_BASE_URL": _public_url_origin(
            str(public_bases["mediaImage"])
        ),
        "CONTENT_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
        "QWQ_COMPOSE_MEDIA_DELIVERY_BASE_URL": _public_url_origin(
            str(public_bases["mediaImage"])
        ),
        "QWQ_COMPOSE_MEDIA_UPLOAD_BASE_URL": str(public_bases["mediaUpload"]),
        "LOCAL_GAMMA_RTC_MEDIA_CONNECTION_URL": str(public_bases["rtc"]),
        "LOCAL_GAMMA_CONTENT_PORT": str(ports["content-service"]),
        "LOCAL_GAMMA_CHAT_PORT": str(ports["chat-service"]),
        "LOCAL_GAMMA_USER_PORT": str(ports["user-service"]),
        "LOCAL_GAMMA_ASSISTANT_PORT": str(ports["assistant-service"]),
        "LOCAL_GAMMA_ENTITY_PORT": str(ports["entity-service"]),
        "LOCAL_GAMMA_CIRCLE_PORT": str(ports["circle-service"]),
        "LOCAL_GAMMA_INTEGRATION_PORT": str(ports["integration-service"]),
        "LOCAL_GAMMA_SMS_SUBSTITUTE_PORT": str(
            ports["sms-provider-substitute"]
        ),
        "QWQ_COMPOSE_PROVIDER_SUBSTITUTE_PORT": str(
            ports["provider-protocol-substitute"]
        ),
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
        "QWQ_COMPOSE_ELASTICSEARCH_PORT": str(ports["elasticsearch"]),
        "LOCAL_GAMMA_OBJECT_STORAGE_EDGE_PORT": str(ports["object-storage-edge"]),
        "LOCAL_GAMMA_MEDIA_ORIGIN_PORT": str(ports["media-origin"]),
        "LOCAL_GAMMA_LIVEKIT_HTTP_PORT": str(ports["livekit-http"]),
        "LOCAL_GAMMA_LIVEKIT_RTC_TCP_PORT": str(ports["livekit-rtc-tcp"]),
        "LOCAL_GAMMA_LIVEKIT_RTC_UDP_PORT": str(ports["livekit-rtc-udp"]),
        "LOCAL_GAMMA_LIVEKIT_METRICS_PORT": str(ports["livekit-metrics"]),
        "LOCAL_GAMMA_TURN_TCP_PORT": str(ports["coturn"]),
        "LOCAL_GAMMA_TURN_UDP_PORT": str(ports["coturn"]),
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
        "QWQ_LOCAL_RELEASE_ENV": environment_name,
        "QWQ_LOCAL_RELEASE_TARGET": target_name,
        "LOCAL_GAMMA_COMPOSE_PROJECT_NAME": _formal_release_compose_project_name(
            target_name
        ),
    }
    return environment


def _current_runtime_workload(target_name: str) -> str:
    """Map the active local runtime slice to an expected-role workload."""

    scope = _current_runtime_health_scope(target_name)
    if scope in {
        "content-import",
        "content-consumer",
    }:
        return "content-release"
    if scope == "content-commercial":
        return "content-commercial"
    return "full"


def _media_edge_health_url(public_bases: dict[str, Any]) -> str:
    """Probe media-edge root /healthz; never append carrier pathBase (/media/image)."""

    return f"{_public_url_origin(str(public_bases['mediaImage'])).rstrip('/')}/healthz"


def _health_checks_for_target(
    topology: dict[str, Any],
    target_name: str,
    scope: str,
    *,
    workload: str | None = None,
) -> list[dict[str, Any]]:
    target = get_target(topology, target_name)
    env_name = str(target["env"])
    env_cfg = topology["environments"][env_name]
    public_bases = target.get("publicBases") or {}
    checks: list[dict[str, Any]] = []
    if scope in {
        "edge",
        "full",
        "content-import",
        "content-consumer",
        "content-commercial",
    }:
        checks.append(
            {
                "name": "api-health",
                "scope": "edge",
                "url": f"{str(public_bases['api']).rstrip('/')}/healthz",
            }
        )
    if scope in {"edge", "full", "content-commercial"}:
        checks.append(
            {
                "name": "product-ops-health",
                "scope": "edge",
                "url": f"{str(public_bases['productOps']).rstrip('/')}/healthz",
            }
        )
    if scope in {
        "media",
        "full",
        "content-import",
        "content-consumer",
        "content-commercial",
    } and "mediaImage" in public_bases:
        checks.append(
            {
                "name": "media-edge-health",
                "scope": "media",
                "url": _media_edge_health_url(public_bases),
            }
        )
    if scope in {"service", "full"}:
        checks.extend(_service_health_checks_for_target(target_name))
    if scope in {"content-import", "content-consumer", "content-commercial", "full"}:
        plane_workload = (
            "full"
            if scope == "full"
            else (workload or _current_runtime_workload(target_name))
        )
        checks.extend(
            _content_data_plane_health_checks(
                target_name,
                workload=plane_workload,
            )
        )
    if scope in {"content-consumer", "content-commercial", "full"}:
        checks.extend(_content_consumer_health_checks(target_name, public_bases))
    if scope == "content-commercial":
        checks.extend(_content_commercial_health_checks(target_name))
    if scope == "full":
        checks.extend(_full_scope_health_checks(target_name, public_bases, env_cfg))
    return checks


_CONTENT_DATA_PLANE_ROLES = frozenset(
    {"content-service", "entity-service", "tag-service", "search-service"}
)


def _content_data_plane_health_checks(
    target_name: str,
    *,
    workload: str = "full",
) -> list[dict[str, Any]]:
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
        for role_name in _expected_local_roles(target_name, workload=workload)
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
    # Ranked /channel recommend feeds require a session id; bare ?limit=1 is 400.
    feed_url = (
        f"{api_base}/content/feed?limit=1"
        "&sessionId=stackctl-content-consumer-health"
    )
    return [
        {"name": "app-config", "scope": "content-consumer", "url": f"{api_base}/config/app"},
        {"name": "content-feed", "scope": "content-consumer", "url": feed_url},
    ]


def _content_commercial_health_checks(target_name: str) -> list[dict[str, Any]]:
    if target_name not in {"alpha-local", "beta-local", "gamma-local"}:
        return []
    target = get_target(load_environment_topology(), target_name)
    profile_name = str(target.get("portProfile") or "")
    if not profile_name:
        return []
    port = canonical_port(load_port_manifest(), profile_name, "product-ops-service")
    return [
        {
            "name": "product-ops-service",
            "scope": "content-commercial",
            "url": f"http://127.0.0.1:{port}/healthz",
        }
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
        "sms-provider-substitute": "/healthz",
        "provider-protocol-substitute": "/healthz",
    }
    for role_name in _expected_local_roles(target_name):
        if not role_name.endswith("-service") and role_name not in non_service_paths:
            continue
        port = canonical_port(manifest, str(profile_name), role_name)
        path = non_service_paths.get(role_name, "/healthz")
        if role_name == "recommendation-service":
            path = "/health"
        check = {
            "name": role_name,
            "scope": "service",
            "url": f"http://127.0.0.1:{port}{path}",
        }
        if role_name in {
            "sms-provider-substitute",
            "provider-protocol-substitute",
        }:
            check["url"] = f"https://127.0.0.1:{port}{path}"
            try:
                check["caFile"] = str(root_certificate_path(target_name))
            except PublicDomainTlsError:
                check["caFile"] = ""
        checks.append(check)
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
        # Ranked feeds require sessionId; bare ?limit=1 is CONTENT.USER.invalid_argument.
        gamma_feed_smoke = (
            f"{str(public_bases['api']).rstrip('/')}/content/feed?limit=1"
            "&sessionId=stackctl-gamma-route-smoke"
        )
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
                    "url": gamma_feed_smoke,
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
        # Keep sessionId parity with content-consumer / gamma full probes.
        prod_sim_feed_smoke = (
            f"{str(public_bases['api']).rstrip('/')}/content/feed?limit=1"
            "&sessionId=stackctl-prod-sim-route-smoke"
        )
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
                    "url": prod_sim_feed_smoke,
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
    if workload in {"content-release", "content-commercial"} and target_name in {
        "alpha-local",
        "beta-local",
        "gamma-local",
    }:
        # content-release 启动的就是这条 consumer data plane；不能要求
        # assistant/chat/Ops 等 full workload 才会启动的端口，否则集成验证
        # 会错误重启已经健康的发布环境。
        roles = [
            "api-edge",
            "media-edge",
            "media-origin",
            "content-service",
            "user-service",
            "entity-service",
        ]
        if workload == "content-commercial":
            roles.extend(
                [
                    "product-ops-edge",
                    "product-ops-service",
                    "recommendation-service",
                ]
            )
        return roles
    # Alpha/Beta/Gamma share one packaged Remote composition.  A target must
    # never look healthy merely because its historical, smaller role subset is
    # listening; the full gate is identical across all three physical stacks.
    full_local_roles = [
            "api-edge",
            "product-ops-edge",
            "media-edge",
            "object-storage-edge",
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
            "sms-provider-substitute",
            "provider-protocol-substitute",
            "notification-service",
            "realtime-gateway",
            "rtc-service",
            "livekit-http",
            "livekit-rtc-tcp",
            "livekit-metrics",
            "coturn",
            "postgres",
            "mongodb",
            "redis",
            "elasticsearch",
    ]
    role_map = {
        "alpha-local": full_local_roles,
        "beta-local": full_local_roles,
        "gamma-local": full_local_roles,
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


def _candidate_workspace_report(target_name: str) -> dict[str, Any]:
    """Compare the active immutable candidate with current managed inputs.

    This is deliberately read-only.  It never packages, activates, repairs or
    selects another candidate; status/inspect can therefore expose stale
    evidence without changing the environment being observed.
    """

    report: dict[str, Any] = {
        "status": "unavailable",
        "drifted": None,
        "candidate": None,
        "current": None,
        "mismatchedFields": [],
        "issues": [],
    }
    try:
        topology = load_environment_topology()
        environment = str(get_target(topology, target_name).get("env") or "")
        active = active_deployment_candidate(target_name)
        if active is None:
            report.update(
                {
                    "status": "no_active_candidate",
                    "drifted": True,
                    "issues": [f"no active immutable candidate for {target_name}"],
                }
            )
            return report
        candidate = load_candidate_manifest(
            environment,
            target_name,
            str(active["baselineId"]),
            require_full=True,
        )
        current = workspace_snapshot()
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        report["issues"] = [
            "candidate/workspace identity is unavailable: " + str(exc)
        ]
        return report

    candidate_identity = {
        "baselineId": candidate.get("baselineId"),
        "sourceRevision": candidate.get("sourceRevision"),
        "workspaceStatusDigest": candidate.get("workspaceStatusDigest"),
        "deploymentInputDigest": candidate.get("workspaceDigest"),
    }
    current_identity = {
        "baselineId": current.get("baselineId"),
        "sourceRevision": current.get("sourceRevision"),
        "workspaceStatusDigest": current.get("workspaceStatusDigest"),
        "deploymentInputDigest": current.get("deploymentInputDigest"),
        "deploymentInputFileCount": current.get("deploymentInputFileCount"),
    }
    mismatched = [
        field
        for field, expected in candidate_identity.items()
        if expected != current_identity.get(field)
    ]
    drifted = bool(mismatched)
    report.update(
        {
            "status": "drifted" if drifted else "current",
            "drifted": drifted,
            "candidate": candidate_identity,
            "current": current_identity,
            "mismatchedFields": mismatched,
            "issues": (
                [
                    "active immutable candidate differs from current managed "
                    "workspace fields: " + ",".join(mismatched)
                ]
                if drifted
                else []
            ),
        }
    )
    return report


def _data_report(
    target_name: str,
    *,
    candidate_workspace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def summarized_digest(value: dict[str, Any]) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    topology = load_environment_topology()
    target = get_target(topology, target_name)
    profile_name = target.get("portProfile")
    if not profile_name:
        return {"ports": []}
    manifest = load_port_manifest()
    report: dict[str, Any] = {
        "ports": {
            "postgres": canonical_port(manifest, profile_name, "postgres"),
            "mongodb": canonical_port(manifest, profile_name, "mongodb"),
            "redis": canonical_port(manifest, profile_name, "redis"),
        },
        "realDataOnly": str(target.get("env")) == "prod",
        "nonprodAcceptanceDatasets": [],
        "issues": [],
    }
    workspace_binding = candidate_workspace or _candidate_workspace_report(target_name)
    report["candidateWorkspace"] = workspace_binding
    report["issues"].extend(
        f"candidate workspace: {issue}"
        for issue in workspace_binding.get("issues", [])
    )
    environment = str(target.get("env") or "")
    active_manifest: dict[str, Any] | None = None
    active = active_deployment_candidate(target_name)
    if isinstance(active, dict):
        baseline_id = str(active.get("baselineId") or "").strip()
        try:
            active_manifest = load_candidate_manifest(
                environment,
                target_name,
                baseline_id,
                require_full=True,
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            report["issues"].append(
                "active candidate manifest is invalid: " + type(exc).__name__
            )
    report["activeCandidateBinding"] = (
        {
            "baselineId": active_manifest.get("baselineId"),
            "packageDigest": active_manifest.get("packageDigest"),
            "releaseDigest": (
                ((active_manifest.get("release") or {}).get("candidate") or {}).get(
                    "releaseDigest"
                )
            ),
        }
        if active_manifest is not None
        else None
    )
    receipt_root = env_runs_root(environment) / "nonprod-data"
    if not receipt_root.is_dir():
        return report
    if environment == "prod":
        report["issues"].append(
            "Prod run root contains forbidden nonprod acceptance dataset receipts"
        )
        return report
    for path in sorted(receipt_root.glob("*/*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            report["issues"].append(
                f"invalid nonprod dataset receipt {relpath(path)}: {type(exc).__name__}"
            )
            continue
        if not isinstance(payload, dict) or payload.get("schema") != (
            "qwq.nonprod_acceptance_dataset_receipt"
        ):
            report["issues"].append(
                f"invalid nonprod dataset receipt schema: {relpath(path)}"
            )
            continue
        receipt_issues: list[str] = []
        if payload.get("target") != target_name or payload.get("environment") != environment:
            receipt_issues.append("target/environment mismatch")
        if str(payload.get("datasetEpoch") or "") != path.parent.name:
            receipt_issues.append("datasetEpoch/path mismatch")
        raw_expires_at = str(payload.get("expiresAt") or "").strip()
        try:
            expires_at = datetime.fromisoformat(raw_expires_at.replace("Z", "+00:00"))
        except ValueError:
            receipt_issues.append("expiresAt invalid")
        else:
            if expires_at.tzinfo is None:
                receipt_issues.append("expiresAt timezone missing")
            elif expires_at <= datetime.now(timezone.utc):
                receipt_issues.append("receipt expired")
        candidate_binding = "unbound"
        if active_manifest is not None:
            expected_release_digest = (
                ((active_manifest.get("release") or {}).get("candidate") or {}).get(
                    "releaseDigest"
                )
            )
            binding_fields = {
                "baselineId": active_manifest.get("baselineId"),
                "packageDigest": active_manifest.get("packageDigest"),
                "runtimeConfigDigest": active_manifest.get("runtimeConfigDigest"),
                "releaseDigest": expected_release_digest,
            }
            drifted = [
                name
                for name, expected in binding_fields.items()
                if payload.get(name) != expected
            ]
            candidate_binding = "stale" if drifted else "active"
            if drifted:
                receipt_issues.append(
                    "candidate binding drift: " + ",".join(sorted(drifted))
                )
        if receipt_issues:
            report["issues"].append(
                f"nonprod dataset {payload.get('datasetId') or path.name}: "
                + "; ".join(receipt_issues)
            )
        objects = payload.get("createdObjectIdsOrHashes")
        projection = payload.get("projectionWatermarks")
        report["nonprodAcceptanceDatasets"].append(
            {
                "datasetId": payload.get("datasetId"),
                "datasetEpoch": payload.get("datasetEpoch"),
                "baselineId": payload.get("baselineId"),
                "packageDigest": payload.get("packageDigest"),
                "releaseDigest": payload.get("releaseDigest"),
                "retentionClass": payload.get("retentionClass"),
                "status": payload.get("status"),
                "cleanupState": payload.get("cleanupState"),
                "expiresAt": payload.get("expiresAt"),
                "candidateBinding": candidate_binding,
                "driftIssues": receipt_issues,
                "objectClosureHash": (
                    summarized_digest(objects) if isinstance(objects, dict) else ""
                ),
                "projectionWatermarkHash": (
                    summarized_digest(projection)
                    if isinstance(projection, dict)
                    else ""
                ),
                "receiptRef": relpath(path),
            }
        )
    return report


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
    environment_matrix = bool(getattr(args, "environment_matrix", False))
    if bool(args.matrix) and environment_matrix:
        return {
            "exitCode": 2,
            "summary": "stackctl provider-conformance is GATE_BLOCK",
            "details": ["--matrix and --environment-matrix are mutually exclusive"],
        }
    if environment_matrix:
        environment = str(args.env or "").strip()
        target_name = DEFAULT_TARGET_BY_ENV.get(environment, "")
        report_dir = resolve_report_dir(args, environment or "repo", target_name or "repo")
        governance = _external_provider_governance()
        conformance = _provider_conformance()
        issues: list[str] = []
        cells: list[dict[str, Any]] = []
        binding_capability_count = 0
        capability_count = 0
        try:
            if environment not in {"alpha", "beta", "gamma"}:
                raise ValueError(
                    "--environment-matrix requires --env alpha, beta, or gamma"
                )
            if not bool(args.execute):
                raise ValueError(
                    "--environment-matrix requires --execute; dry-run is not evidence"
                )
            if any(
                str(value or "").strip()
                for value in (args.adapter_id, args.capability_id, args.layer)
            ):
                raise ValueError(
                    "environment matrix derives adapter/capability/layer from generated Bindings"
                )
            compiled, governance_issues = governance.load_and_compile()
            if governance_issues:
                raise ValueError(
                    "; ".join(issue.render() for issue in governance_issues)
                )
            selected = (compiled.get("selectedBindings") or {}).get(environment)
            if not isinstance(selected, dict) or not selected:
                raise ValueError(
                    f"generated Binding has no capabilities for {environment}"
                )
            binding_capability_count = len(selected)
            capability_count = sum(
                1
                for binding in selected.values()
                if isinstance(binding, dict)
                and governance.requires_provider_conformance(binding)
            )
            sources, source_issues = conformance.discover_test_sources()
            if source_issues:
                raise ValueError("; ".join(source_issues))
            runner = _provider_conformance_runner()
            runner.preflight_environment_matrix(
                environment=environment,
                registry=governance.load_registry(),
                compiled=compiled,
                sources=sources,
            )
            for capability_id, binding in sorted(selected.items()):
                if not isinstance(binding, dict):
                    raise ValueError(
                        f"{environment}/{capability_id} selected Binding is invalid"
                    )
                if not governance.requires_provider_conformance(binding):
                    continue
                adapter_id = str(binding.get("adapter_id") or "")
                if not adapter_id or binding.get("state") != "enabled":
                    raise ValueError(
                        f"{environment}/{capability_id} has no enabled selected adapter"
                    )
                for layer in PROVIDER_CONFORMANCE_LAYERS:
                    runner_args = [
                        "--adapter-id",
                        adapter_id,
                        "--capability-id",
                        capability_id,
                        "--environment",
                        environment,
                        "--layer",
                        layer,
                        "--execute",
                    ]
                    exit_code = runner.main(runner_args)
                    cells.append(
                        {
                            "capabilityId": capability_id,
                            "adapterId": adapter_id,
                            "layer": layer,
                            "exitCode": exit_code,
                        }
                    )
                    if exit_code != 0:
                        raise ValueError(
                            f"{environment}/{capability_id}/{layer} failed"
                        )
            readiness, readiness_load_issues = conformance.load_validate_and_derive()
            readiness_issues = conformance.readiness_issues(
                readiness,
                environment=environment,
            )
            issues.extend(str(item) for item in readiness_load_issues)
            issues.extend(str(item) for item in readiness_issues)
        except (OSError, RuntimeError, ValueError) as exc:
            issues.append(str(exc))
        expected_cells = capability_count * len(PROVIDER_CONFORMANCE_LAYERS)
        passed = (
            not issues
            and capability_count > 0
            and len(cells) == expected_cells
            and all(int(cell.get("exitCode") or 0) == 0 for cell in cells)
        )
        payload = {
            "schema": "stackctl-provider-conformance-environment-matrix",
            "status": "passed" if passed else "gate_block",
            "environment": environment,
            "target": target_name,
            "bindingCapabilityCount": binding_capability_count,
            "capabilityCount": capability_count,
            "expectedCells": expected_cells,
            "executed": len(cells),
            "skipped": 0,
            "cells": cells,
            "issues": issues,
        }
        write_json(report_dir / "report.json", payload)
        write_json(report_dir / "findings.json", {"issues": issues})
        return {
            **payload,
            "exitCode": 0 if passed else 2,
            "summary": (
                f"stackctl provider-conformance passed {len(cells)} cells for {environment}"
                if passed
                else f"stackctl provider-conformance is GATE_BLOCK for {environment}"
            ),
            "details": issues or [
                f"capabilities={capability_count}",
                f"executed={len(cells)}",
                "skipped=0",
            ],
            "reportDir": relpath(report_dir),
        }

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


def _explicit_evidence_mappings(
    values: list[str],
    *,
    allowed: set[str],
    option: str,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        name, separator, path = str(raw).partition("=")
        name = name.strip()
        path = path.strip()
        if not separator or name not in allowed or not path:
            raise ValueError(
                f"{option} must use one of {','.join(sorted(allowed))}=PATH"
            )
        if name in result:
            raise ValueError(f"{option} duplicates role/case: {name}")
        result[name] = path
    if set(result) != allowed:
        raise ValueError(
            f"{option} must bind exactly {','.join(sorted(allowed))}"
        )
    return result


def command_provider_config(args: argparse.Namespace) -> dict[str, Any]:
    try:
        return _provider_config().compile_provider_config(
            action=str(args.provider_config_action),
            environment=str(args.env),
            target=str(args.target),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "exitCode": 2,
            "summary": "stackctl provider-config is GATE_BLOCK",
            "details": [str(exc)],
        }


def command_nonprod_data_evidence(args: argparse.Namespace) -> dict[str, Any]:
    target_name = str(args.target)
    environment = str(NONPROD_TARGETS[target_name])
    report_dir = resolve_report_dir(args, environment, target_name)
    started_monotonic, started_at = _start_timing()
    issues: list[str] = []
    output_path = report_dir / "gate-evidence.json"
    try:
        active = active_deployment_candidate(target_name)
        if active is None:
            raise ValueError("active immutable deployment candidate is required")
        manifest = load_candidate_manifest(
            environment,
            target_name,
            str(active["baselineId"]),
            require_full=True,
        )
        provider_refs = _explicit_evidence_mappings(
            list(args.provider_receipt),
            allowed=set(NONPROD_PROVIDER_CAPABILITIES),
            option="--provider-receipt",
        )
        reliability_refs = _explicit_evidence_mappings(
            list(args.reliability_receipt),
            allowed=set(NONPROD_RELIABILITY_CASE_IDS),
            option="--reliability-receipt",
        )
        assemble_nonprod_gate_evidence(
            target=target_name,
            environment=environment,
            candidate_manifest=manifest,
            share_receipt_refs=list(args.share_receipt),
            provider_receipt_refs=provider_refs,
            reliability_receipt_refs=reliability_refs,
            evidence_root=output_root(),
            output_path=output_path,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    timing = _finish_timing(started_monotonic, started_at)
    status = "passed" if not issues else ProbeOutcome.GATE_BLOCK.value
    report = {
        "command": "nonprod-data-evidence",
        "target": target_name,
        "environment": environment,
        "status": status,
        "evidenceRef": relpath(output_path) if not issues else "",
        "issues": issues,
        **timing,
    }
    write_json(report_dir / "report.json", report)
    write_json(report_dir / "findings.json", {"issues": issues})
    return {
        "exitCode": 0 if not issues else 2,
        "summary": (
            f"nonprod data evidence assembled for {target_name}"
            if not issues
            else f"nonprod data evidence is GATE_BLOCK for {target_name}"
        ),
        "details": issues or [f"evidence={relpath(output_path)}"],
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_tls(args: argparse.Namespace) -> dict[str, Any]:
    """Expose canonical TLS through stackctl without duplicating certificate logic."""
    env_name = str(get_target(load_environment_topology(), args.target)["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _start_timing()
    details: list[str] = []
    evidence: dict[str, Any] = {}
    exit_code = 0
    try:
        if args.action == "prevalidate":
            policy = load_public_domain_policy()
            profile_name, profile_kind, profile = tls_profile(args.target)
            if profile_kind == "local-managed":
                client = "openssl"
                client_available = shutil.which(client) is not None
                if not client_available:
                    details.append("required local-managed TLS client is unavailable: openssl")
                    exit_code = 2
                evidence = {
                    "target": args.target,
                    "action": "prevalidate",
                    "profile": profile_name,
                    "kind": profile_kind,
                    "clientAvailable": client_available,
                    "protectedInputsReady": True,
                    "status": "passed" if exit_code == 0 else ProbeOutcome.GATE_BLOCK.value,
                }
                if exit_code == 0:
                    details.append("local-managed TLS inputs and openssl are ready")
            else:
                acme = policy.get("acme") or {}
                authority = policy.get("acmeChallengeAuthority") or {}
                required_envs = (
                    str(acme.get("accountEmailEnv") or ""),
                    str(authority.get("apiTokenEnv") or ""),
                )
                missing_envs = [
                    name for name in required_envs if not name or not os.environ.get(name, "").strip()
                ]
                client = str(acme.get("client") or "lego")
                if shutil.which(client) is None:
                    details.append(f"required ACME client is unavailable: {client}")
                if missing_envs:
                    details.append("missing protected environment inputs: " + ", ".join(missing_envs))
                if details:
                    exit_code = 2
                evidence = {
                    "target": args.target,
                    "action": "prevalidate",
                    "profile": profile_name,
                    "kind": profile_kind,
                    "apex": str(profile.get("apex") or ""),
                    "wildcard": str(profile.get("wildcard") or ""),
                    "clientAvailable": shutil.which(client) is not None,
                    "protectedInputsReady": not missing_envs,
                    "status": "passed" if exit_code == 0 else ProbeOutcome.GATE_BLOCK.value,
                }
                if exit_code == 0:
                    details.append("DNS-01 TLS protected inputs and client are ready")
        elif args.action == "verify":
            verified = verify_certificate(args.target)
            evidence = {
                key: value
                for key, value in verified.items()
                if key not in {"certificate", "privateKey"}
            }
            details.append("public certificate, private-key match and SAN verified")
        else:
            _, profile_kind, _ = tls_profile(args.target)
            if profile_kind != "local-managed" and not args.confirm_protected_apply:
                raise PublicDomainTlsError(
                    "GATE_BLOCK: issue requires --confirm-protected-apply after prevalidate"
                )
            issued = issue_certificate(args.target)
            evidence = {
                key: value
                for key, value in issued.items()
                if key not in {"certificate", "privateKey"}
            }
            details.append(f"{profile_kind} certificate issued and verified")
    except PublicDomainTlsError as error:
        exit_code = 2
        details = [str(error)]
        evidence = {
            "target": args.target,
            "action": args.action,
            "status": ProbeOutcome.GATE_BLOCK.value,
        }
    timing = _finish_timing(started_monotonic, started_at)
    status = "passed" if exit_code == 0 else "gate_block"
    write_json(
        report_dir / "report.json",
        {
            "command": "tls",
            "target": args.target,
            "action": args.action,
            "status": status,
            "evidence": evidence,
            "details": details,
            **timing,
        },
    )
    write_json(
        report_dir / "findings.json",
        {"issues": [] if exit_code == 0 else details},
    )
    return {
        "exitCode": exit_code,
        "summary": f"stackctl tls {args.action} {status} for {args.target}",
        "details": details,
        "reportDir": relpath(report_dir),
        **timing,
    }


def command_device_trust(args: argparse.Namespace) -> dict[str, Any]:
    env_name = str(get_target(load_environment_topology(), args.target)["env"])
    report_dir = resolve_report_dir(args, env_name, args.target)
    started_monotonic, started_at = _start_timing()
    defer_endpoint_probe = bool(getattr(args, "defer_endpoint_probe", False))
    allow_unprovisioned_system_trust = bool(
        getattr(args, "allow_unprovisioned_system_trust", False)
    )
    try:
        if args.action == "install":
            evidence = install_device_trust(
                target=args.target,
                platform_name=args.platform,
                device=args.device,
                lease_id=args.lease_id,
                endpoint_probe=not defer_endpoint_probe,
                allow_unprovisioned_system_trust=allow_unprovisioned_system_trust,
            )
        elif args.action == "verify":
            if defer_endpoint_probe or allow_unprovisioned_system_trust:
                raise LocalDeviceTrustError(
                    "startup-only trust flags are valid only for device-trust install"
                )
            if not str(args.device or "").strip():
                raise LocalDeviceTrustError("device-trust verify requires --device")
            evidence = verify_device_trust(
                target=args.target,
                platform_name=args.platform,
                device=args.device,
            )
        else:
            if defer_endpoint_probe or allow_unprovisioned_system_trust:
                raise LocalDeviceTrustError(
                    "startup-only trust flags are valid only for device-trust install"
                )
            if not str(args.device or "").strip() or not str(args.lease_id or "").strip():
                raise LocalDeviceTrustError(
                    "device-trust release requires --device and --lease-id"
                )
            evidence = release_device_trust(
                target=args.target,
                platform_name=args.platform,
                device=args.device,
                lease_id=args.lease_id,
            )
        exit_code = 0
        details = [
            f"device={evidence['device']}",
            f"rootFingerprintSha256={evidence['rootFingerprintSha256']}",
            f"receipt={evidence['receipt']}",
        ]
    except (LocalDeviceTrustError, PublicDomainTlsError, OSError, ValueError) as exc:
        evidence = {}
        exit_code = 2
        details = [str(exc)]
    timing = _finish_timing(started_monotonic, started_at)
    status = (
        "launch_degraded"
        if exit_code == 0 and evidence.get("systemTrustStore") is False
        else "passed"
        if exit_code == 0
        else "gate_block"
    )
    write_json(
        report_dir / "report.json",
        {
            "command": "device-trust",
            "target": args.target,
            "platform": args.platform,
            "action": args.action,
            "status": status,
            "evidence": evidence,
            "details": details,
            **timing,
        },
    )
    return {
        "exitCode": exit_code,
        "summary": (
            f"stackctl device-trust {args.action} {status} for {args.target}"
        ),
        "details": details,
        "reportDir": relpath(report_dir),
        "evidence": evidence,
        **timing,
    }


def _dev_session_child_args(
    command: str,
    *,
    report_dir: Path,
    argv: list[str],
) -> argparse.Namespace:
    return build_parser().parse_args(
        [
            "--output-format",
            "json",
            "--report-dir",
            str(report_dir),
            command,
            *argv,
        ]
    )


def _dev_session_phase(
    name: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "exitCode": int(payload.get("exitCode", 1)),
        "summary": str(payload.get("summary") or ""),
        "details": list(payload.get("details") or []),
        "reportDir": str(payload.get("reportDir") or ""),
    }


def _run_dev_session_target(
    *,
    environment: str,
    target: str,
    release_attestation: str,
    rollback_release_attestation: str,
    device_id: str,
    launch_app_requested: bool,
    report_dir: Path,
) -> dict[str, Any]:
    phases: list[dict[str, Any]] = []
    package_payload = command_package(
        _dev_session_child_args(
            "package",
            report_dir=report_dir / "package",
            argv=[
                "--env",
                environment,
                "--target",
                target,
                "--include-services",
                "--release-attestation",
                release_attestation,
                "--rollback-release-attestation",
                rollback_release_attestation,
            ],
        )
    )
    phases.append(_dev_session_phase("package", package_payload))
    if int(package_payload.get("exitCode", 1)) != 0:
        return {
            "exitCode": int(package_payload.get("exitCode", 1)),
            "sessionKind": "cold",
            "blockerKind": "package_failed",
            "details": list(package_payload.get("details") or []),
            "phases": phases,
        }

    try:
        active_attempt = load_startup_attempt(target)
    except (OSError, ValueError) as exc:
        return {
            "exitCode": 2,
            "sessionKind": "cold",
            "blockerKind": "runtime_receipt_unreadable",
            "details": [str(exc)],
            "phases": phases,
        }
    session_kind = (
        "hot"
        if active_attempt
        and active_attempt.get("status") == "running"
        and active_attempt.get("workload") == "full"
        else "cold"
    )

    if session_kind == "cold":
        up_argv = [
            "--env",
            environment,
            "--workload",
            "full",
        ]
        if device_id:
            up_argv.extend(("--device-id", device_id))
        if not launch_app_requested:
            up_argv.append("--skip-app")
        up_payload = command_up(
            _dev_session_child_args(
                "up",
                report_dir=report_dir / "up",
                argv=up_argv,
            )
        )
        phases.append(_dev_session_phase("up", up_payload))
        if int(up_payload.get("exitCode", 1)) != 0:
            return {
                "exitCode": int(up_payload.get("exitCode", 1)),
                "sessionKind": session_kind,
                "blockerKind": "runtime_up_failed",
                "details": list(up_payload.get("details") or []),
                "phases": phases,
            }
    else:
        phases.append(
            {
                "name": "up",
                "exitCode": 0,
                "summary": "healthy full runtime reused",
                "details": [
                    f"attemptId={active_attempt.get('attemptId')}",
                    "compose up was not repeated",
                ],
                "reportDir": "",
            }
        )
        if launch_app_requested:
            selected_device = device_id or resolve_device_id(
                include_mobile=True,
                include_web=False,
                include_desktop=False,
                label="[stackctl dev-session]",
            )
            try:
                process = launch_app(
                    environment,
                    selected_device,
                    topology=load_environment_topology(),
                    rollout_mode="",
                    log_path=report_dir / f"app-launch-{selected_device.replace('/', '_')}.log",
                )
            except RuntimeError as exc:
                return {
                    "exitCode": 1,
                    "sessionKind": session_kind,
                    "blockerKind": "app_launch_failed",
                    "details": [str(exc)],
                    "phases": phases,
                }
            phases.append(
                {
                    "name": "app-launch",
                    "exitCode": 0,
                    "summary": f"App launch started with pid={process.pid}",
                    "details": [f"device={selected_device}"],
                    "reportDir": relpath(report_dir),
                }
            )

    health_payload = command_health(
        _dev_session_child_args(
            "health",
            report_dir=report_dir / "health",
            argv=["--target", target, "--scope", "full"],
        )
    )
    phases.append(_dev_session_phase("health", health_payload))
    if int(health_payload.get("exitCode", 1)) != 0:
        return {
            "exitCode": int(health_payload.get("exitCode", 1)),
            "sessionKind": session_kind,
            "blockerKind": "runtime_health_failed",
            "details": list(health_payload.get("details") or []),
            "phases": phases,
        }

    handoff = ["./run.sh", "--env", environment]
    if device_id:
        handoff.extend(("-d", device_id))
    return {
        "exitCode": 0,
        "sessionKind": session_kind,
        "blockerKind": "",
        "details": [
            "App handoff: cd quwoquan_app && "
            + " ".join(shlex.quote(item) for item in handoff)
        ],
        "phases": phases,
    }


def command_dev_session(args: argparse.Namespace) -> dict[str, Any]:
    started_monotonic, started_at = _start_timing()
    topology = load_environment_topology()
    all_nonprod = bool(getattr(args, "all_nonprod", False))
    requested_env = str(getattr(args, "env", "") or "").strip()
    requested_target = str(getattr(args, "target", "") or "").strip()
    if all_nonprod:
        if requested_env or requested_target or bool(getattr(args, "launch_app", False)):
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl dev-session is GATE_BLOCK",
                "details": [
                    "--all-nonprod cannot be combined with --env, --target or --launch-app"
                ],
                "blockerKind": "invalid_session_selection",
                **timing,
            }
        selections = [
            (environment, DEV_UP_STACK_TARGETS[environment])
            for environment in ("alpha", "beta", "gamma")
        ]
        report_env = "repo"
        report_target = "all-nonprod"
    else:
        if bool(requested_env) == bool(requested_target):
            timing = _finish_timing(started_monotonic, started_at)
            return {
                "exitCode": 2,
                "summary": "stackctl dev-session is GATE_BLOCK",
                "details": ["provide exactly one of --env, --target or use --all-nonprod"],
                "blockerKind": "environment_missing",
                **timing,
            }
        if requested_env:
            requested_target = DEV_UP_STACK_TARGETS[requested_env]
        else:
            requested_env = str(get_target(topology, requested_target)["env"])
        selections = [(requested_env, requested_target)]
        report_env = requested_env
        report_target = requested_target

    report_dir = resolve_report_dir(args, report_env, report_target)
    release_attestation = str(args.release_attestation)
    rollback_release_attestation = str(args.rollback_release_attestation)
    sessions: list[dict[str, Any]] = []
    terminal_exit = 0
    blocker_kind = ""
    details: list[str] = []

    if all_nonprod:
        for target in CANONICAL_LOCAL_GATE_TARGETS:
            try:
                attempt = load_startup_attempt(target)
            except (OSError, ValueError) as exc:
                terminal_exit = 2
                blocker_kind = "runtime_receipt_unreadable"
                details = [f"{target}: {exc}"]
                break
            if attempt and attempt.get("status") != "stopped":
                down_payload = command_down(
                    _dev_session_child_args(
                        "down",
                        report_dir=report_dir / "pre-down" / target,
                        argv=["--target", target],
                    )
                )
                if int(down_payload.get("exitCode", 1)) != 0:
                    terminal_exit = int(down_payload.get("exitCode", 1))
                    blocker_kind = "pre_down_failed"
                    details = list(down_payload.get("details") or [])
                    break

    if terminal_exit == 0:
        for environment, target in selections:
            session = _run_dev_session_target(
                environment=environment,
                target=target,
                release_attestation=release_attestation,
                rollback_release_attestation=rollback_release_attestation,
                device_id=str(getattr(args, "device_id", "") or ""),
                launch_app_requested=bool(getattr(args, "launch_app", False)),
                report_dir=report_dir / target,
            )
            sessions.append(
                {
                    "environment": environment,
                    "target": target,
                    **session,
                }
            )
            terminal_exit = int(session["exitCode"])
            if terminal_exit != 0:
                blocker_kind = str(session.get("blockerKind") or "session_failed")
                details = list(session.get("details") or [])
            if all_nonprod:
                down_payload = command_down(
                    _dev_session_child_args(
                        "down",
                        report_dir=report_dir / target / "down",
                        argv=["--target", target, "--workload", "full"],
                    )
                )
                sessions[-1]["down"] = _dev_session_phase("down", down_payload)
                if terminal_exit == 0 and int(down_payload.get("exitCode", 1)) != 0:
                    terminal_exit = int(down_payload.get("exitCode", 1))
                    blocker_kind = "post_down_failed"
                    details = list(down_payload.get("details") or [])
            if terminal_exit != 0:
                break

    timing = _finish_timing(started_monotonic, started_at)
    status = "ok" if terminal_exit == 0 else "gate_block" if terminal_exit == 2 else "failed"
    summary = (
        f"stackctl dev-session completed for {report_target}"
        if terminal_exit == 0
        else f"stackctl dev-session is {status.upper()} for {report_target}"
    )
    if terminal_exit == 0 and not details:
        details = [
            item
            for session in sessions
            for item in list(session.get("details") or [])
        ]
    report = {
        "command": "dev-session",
        "target": report_target,
        "status": status,
        "allNonprod": all_nonprod,
        "blockerKind": blocker_kind,
        "sessions": sessions,
        "details": details,
        **timing,
    }
    write_json(report_dir / "report.json", report)
    _write_summary_bundle(
        report_dir,
        command="dev-session",
        target=report_target,
        status=status,
        summary=summary,
        details=details,
        extra={
            "allNonprod": all_nonprod,
            "blockerKind": blocker_kind,
            "sessions": sessions,
        },
        timing=timing,
    )
    return {
        "exitCode": terminal_exit,
        "summary": summary,
        "details": details,
        "reportDir": relpath(report_dir),
        "blockerKind": blocker_kind,
        "sessions": sessions,
        **timing,
    }


def command_matrix(args: argparse.Namespace) -> dict[str, Any]:
    profile = str(getattr(args, "profile", PROFILE_LOCAL_ENV_GATE) or PROFILE_LOCAL_ENV_GATE)
    if profile != PROFILE_LOCAL_ENV_GATE:
        return {
            "exitCode": 2,
            "summary": f"unsupported matrix profile: {profile}",
            "details": [f"supported: {PROFILE_LOCAL_ENV_GATE}"],
        }
    targets = tuple(
        item.strip()
        for item in str(getattr(args, "targets", "") or "").split(",")
        if item.strip()
    )
    evidence_by_target: dict[str, str] = {}
    evidence_issues: list[str] = []
    for raw in list(getattr(args, "nonprod_data_evidence", []) or []):
        target, separator, path = str(raw).partition("=")
        target = target.strip()
        path = path.strip()
        if not separator or target not in CANONICAL_LOCAL_GATE_TARGETS or not path:
            evidence_issues.append(
                "--nonprod-data-evidence must use alpha-local|beta-local|gamma-local=PATH"
            )
            continue
        if target in evidence_by_target:
            evidence_issues.append(f"duplicate nonprod data evidence target: {target}")
            continue
        evidence_by_target[target] = path
    if evidence_issues:
        return {
            "exitCode": 2,
            "summary": "stackctl matrix nonprod data evidence is GATE_BLOCK",
            "details": evidence_issues,
        }
    return run_local_env_gate_matrix(
        package_fn=command_package,
        up_fn=command_up,
        health_fn=command_health,
        verify_fn=command_verify,
        down_fn=command_down,
        telemetry_fn=command_product_telemetry_log_sink,
        provider_fn=command_provider_conformance,
        app_uat_fn=command_app_content_uat,
        filter_catalog_fn=command_filter_catalog,
        targets=targets,
        include_l0=not bool(getattr(args, "skip_l0", False)),
        release_attestation=str(
            getattr(args, "release_attestation", "") or ""
        ),
        rollback_release_attestation=str(
            getattr(args, "rollback_release_attestation", "") or ""
        ),
        nonprod_data_evidence=evidence_by_target,
        ios_simulator_device=str(
            getattr(args, "ios_simulator_device", "") or ""
        ),
        android_emulator_device=str(
            getattr(args, "android_emulator_device", "") or ""
        ),
        android_physical_device=str(
            getattr(args, "android_physical_device", "") or ""
        ),
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "package": command_package,
        "verify": command_verify,
        "matrix": command_matrix,
        "tls": command_tls,
        "device-trust": command_device_trust,
        "provider-conformance": command_provider_conformance,
        "provider-config": command_provider_config,
        "nonprod-data-evidence": command_nonprod_data_evidence,
        "dev-session": command_dev_session,
        "up": command_up,
        "product-telemetry-log-sink": command_product_telemetry_log_sink,
        "down": command_down,
        "consumer-lease": command_consumer_lease,
        "status": command_status,
        "health": command_health,
        "prod-hosted-plan": command_prod_hosted_plan,
        "inspect": command_inspect,
        "doctor": command_doctor,
        "content-readiness": command_content_readiness,
        "app-content-preflight": command_app_content_preflight,
        "app-debug-preflight": command_app_debug_preflight,
        "provider-debug": command_provider_debug,
        "app-content-uat": command_app_content_uat,
        "data-execution-fleet": command_data_execution_fleet,
        "content-uat": command_content_uat,
        "account-enforcement-uat": command_account_enforcement_uat,
        "filter-catalog": command_filter_catalog,
        "premium-pool": command_premium_pool,
        "repair": command_repair,
        "roll": command_roll,
        "deploy": command_deploy,
        "hosted-release-receipt": command_hosted_release_receipt,
    }
    payload = dispatch[args.command](args)
    return print_result(args, payload)


if __name__ == "__main__":
    raise SystemExit(main())
