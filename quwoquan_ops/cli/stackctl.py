#!/usr/bin/env python3
from __future__ import annotations

# Path anchors keep shared shell/python helpers classified as lib by governance
# derivation. Do not execute these strings; they document managed ownership only.
OPS_SCRIPT_LIB_ANCHORS = (
    "quwoquan_ops/cli/lib/beta_manual_lifecycle.sh",
    "quwoquan_ops/cli/lib/local_beta_object_storage.py",
)

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
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import urllib.parse
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def _bootstrap_command(argv: Sequence[str]) -> str:
    """Resolve the command without importing the full argparse command graph."""

    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in {"--output-format", "--report-dir"}:
            index += 2
            continue
        if argument.startswith("--output-format=") or argument.startswith("--report-dir="):
            index += 1
            continue
        return "" if argument.startswith("-") else argument
    return ""


# status/health/inspect must produce diagnostics before mutating, packaging,
# Data, App UAT, Objective, release, and migration domains are imported.
if __name__ == "__main__" and _bootstrap_command(sys.argv[1:]) in {
    "status",
    "health",
    "inspect",
    "doctor",
}:
    from quwoquan_ops.cli.read_only_entry import main as _read_only_main

    raise SystemExit(_read_only_main())

from quwoquan_ops.cli.lib.common import (
    artifact_run_dir, ensure_list, load_json_yaml, relpath, run, utc_now, write_json,
    write_markdown,
)
from quwoquan_ops.cli.lib.android_official_release import (
    AndroidOfficialReleaseError, package_android_official_release,
)
from quwoquan_ops.cli.lib.app_identity import (
    application_id_for, resolve_app_identity,
)
from quwoquan_ops.cli.lib.web_official_release import (
    WebOfficialReleaseError, package_web_official_release,
)
from quwoquan_ops.cli.lib.official_distribution_release import (
    OfficialDistributionReleaseError, deploy_official_distribution, inspect_official_distribution,
)
from quwoquan_ops.cli.prod import collect_release_artifact_descriptors
from quwoquan_ops.cli.prod import hosted_release_ledger
from quwoquan_ops.cli.prod import oci_supply_chain
from quwoquan_ops.cli.prod import rollout_stage_promotion_evidence
from quwoquan_ops.cli.prod.prod_hosted_topology import (
    ProdHostedTopologyError, instance_for_stage as prod_hosted_instance_for_stage,
    load_access_manifest as load_prod_hosted_access_manifest,
    placement_check_name as prod_hosted_placement_check_name,
    require_release_redundancy as require_prod_hosted_release_redundancy,
    resolve_plan as resolve_prod_hosted_plan,
    validate_host_coverage as validate_prod_hosted_host_coverage,
)
from quwoquan_ops.cli.alpha import content_release_runtime as alpha_content_release_runtime
from quwoquan_ops.cli.lib import active_content_release_outbox_repair
from quwoquan_ops.cli.lib.acceptance_surface_identity import (
    ACCOUNT_ENFORCEMENT_GAMMA_DEVICE_RUNNER, ACCOUNT_ENFORCEMENT_GAMMA_UAT_MANIFEST,
    ACCOUNT_ENFORCEMENT_GAMMA_UAT_VALIDATOR, GAMMA_CONTENT_UAT_TARGET,
    ProfileActorCaseId, RELEASE_HOMEPAGE_UAT_TEST_TARGET,
    RUNTIME_RECOVERY_UAT_TEST_TARGET,
)
from quwoquan_ops.cli.lib.compose_layout import compose_file_args, gamma_compose_files
from quwoquan_ops.cli.lib.fault_drill_orchestration import FAULT_PROFILES, run_drill
from quwoquan_ops.cli.lib.local_runtime_capacity import (
    CAPACITY_BLOCKER, is_disk_exhausted, local_runtime_capacity_evidence,
)
from quwoquan_ops.cli.lib.loadtest_orchestration import run_loadtest
from quwoquan_ops.cli.lib.patrol_execution_lock import acquire_patrol_execution_lock
from quwoquan_ops.cli.lib.environment_topology import (
    ENVIRONMENTS, TARGETS, formal_release_compose_project_name, get_environment,
    get_target, load_environment_topology, require_formal_release_compose_project,
    resolve_environment_target_base,
)
from quwoquan_ops.cli.lib.experiment_policy_activation import (
    ExperimentPolicyActivationError, activate_search_experiment_policy,
    activate_test_live_experiment_policies,
)
from quwoquan_ops.cli.lib.local_environment_auth import (
    LocalAcceptanceSession, LocalEnvironmentHTTPError, close_test_data_acceptance_actor,
    load_local_environment_auth, mint_local_filter_catalog_service_token,
    mint_local_product_ops_operator_token, open_local_phone_acceptance_session,
    open_test_data_acceptance_session, prepare_local_environment_auth,
    request_local_environment_json,
)
from quwoquan_ops.cli.lib.premium_pool_release import (
    PremiumPoolReleaseError, execute_premium_pool_readback, execute_premium_pool_upsert,
    load_premium_pool_bootstrap_binding, load_premium_pool_candidate_binding,
    load_premium_pool_test_live_binding, open_premium_pool_operator_session,
    premium_pool_is_empty,
)
from quwoquan_ops.cli.lib.local_gamma_object_storage import prepare_local_gamma_object_storage
from quwoquan_ops.cli.lib.local_environment_object_storage import (
    prepare_local_environment_object_storage,
)
from quwoquan_ops.cli.lib.product_telemetry_log_sink import load_product_telemetry_log_sink
from quwoquan_ops.cli.lib.public_domain_tls import (
    PublicDomainTlsError, issue_certificate, load_policy as load_public_domain_policy,
    root_certificate_path, tls_profile, verify_certificate,
)
from quwoquan_ops.cli.lib.local_target_handoff import (
    LOOPBACK_ADDRESS, LocalTargetHandoffError, materialize_handoff, target_for_hostname,
)
from quwoquan_ops.cli.lib.local_device_trust import (
    LocalDeviceTrustError, _read_receipt as read_device_trust_receipt,
    _receipt_path as device_trust_receipt_path, install_device_trust,
    release_device_trust, verify_device_trust,
)
from quwoquan_ops.cli.lib.local_provider_credentials import load_nonprod_provider_environment
from quwoquan_ops.cli.lib.local_sms_provider_substitute import prepare_local_sms_provider_substitute
from quwoquan_ops.cli.lib.local_integration_service_mtls import (
    prepare_local_integration_service_mtls,
)
from quwoquan_ops.cli.lib.local_assistant_skill_package_keys import (
    prepare_local_assistant_skill_package_keys,
)
from quwoquan_ops.cli.lib.local_assistant_skill_package_publication import (
    load_packaged_assistant_skill_package_trust,
    publish_alpha_test_live,
)
from quwoquan_ops.cli.lib.local_provider_protocol_substitute import (
    prepare_local_provider_protocol_substitute,
)
from quwoquan_ops.cli.lib.local_sms_provider_debug import read_latest_debug_otp
from quwoquan_ops.cli.lib.video_playback_evidence import read_native_video_playback_evidence
from quwoquan_ops.cli.lib.release_video_delivery import (
    ReleaseVideoDeliveryError, load_release_video_binding,
)
from quwoquan_ops.cli.lib.content_release_readiness import (
    ProbeOutcome, ProbeSource, ReadinessPhase, ShipReadinessReceipt, VerificationProfile,
    load_content_release_readiness_policy,
)
from quwoquan_ops.cli.lib.app_content_uat_plan import build_app_content_uat_plan
from quwoquan_ops.cli.lib.app_content_uat_release_samples import (
    resolve_release_sample_requests,
    validate_release_sample_probe,
    validate_release_strict_probe,
)
from quwoquan_ops.cli.lib.content_delivery_verification import verify_content_delivery
from quwoquan_ops.cli.lib.research_content_isolation import verify_research_content_isolation
from quwoquan_ops.cli.lib.research_isolation_runtime_probe import (
    ResearchIsolationProbeError, run_research_isolation_runtime_probe,
)
from quwoquan_ops.cli.lib.research_consumer_credential import (
    ResearchConsumerCredentialError, issue_research_consumer_credential,
)
from quwoquan_ops.cli.lib.content_api_consumer import run_content_api_consumer
from quwoquan_ops.cli.lib.runtime_port_ownership import (
    project_canonical_runtime_owned_ports,
    project_compose_published_endpoints,
    project_runtime_owned_ports,
    require_published_endpoint_port,
)
from quwoquan_ops.cli.lib.domain_remote_api_integration import (
    GOVERNED_DOMAINS as REMOTE_API_INTEGRATION_DOMAINS,
    discover_cases as discover_domain_remote_api_cases,
    discover_selected_cases as discover_selected_remote_api_cases,
    managed_readiness_case_ids as managed_remote_api_readiness_case_ids,
    run_flutter_with_private_defines as run_remote_api_with_private_defines,
    validate_cases as validate_domain_remote_api_cases,
)
from quwoquan_ops.cli.lib.local_runtime_reservation import (
    LocalOperationLockBusyError,
    acquire_local_runtime_use_lock, active_conflicting_local_targets, assert_local_runtime_available,
    assert_no_running_mutable_runtime,
    global_local_operation_lock as _reservation_global_local_operation_lock,
    local_runtime_lock_holders,
    local_runtime_peer_targets,
    local_runtime_operation_lock_path,
    local_stack_operation_lock as _reservation_local_stack_operation_lock,
)
from quwoquan_ops.cli.lib.local_runtime_consumer_lease import (
    DEFAULT_BUILD_GRACE_SECONDS, OCCUPANCY_FREE_STATES, acquire_consumer_lease,
    active_consumer_leases, bind_consumer_lease, consumer_lease_dir,
    inspect_consumer_leases, release_consumer_lease,
)
from quwoquan_ops.cli.lib import orphan_compose_teardown
from quwoquan_ops.cli.lib.orphan_compose_runtime_gate import (
    orphan_compose_runtime_gate as _orphan_compose_runtime_gate,
)
from quwoquan_ops.cli.lib import output_layout_reconciliation
from quwoquan_ops.cli.lib import service_core_cutover
from quwoquan_ops.cli.lib import startup_health_failure_evidence
from quwoquan_ops.cli.lib.startup_attempt_receipt import (
    image_composition_from_candidate_oci, load_startup_attempt, load_workload_startup_attempt,
    read_startup_attempt, startup_attempt_path, startup_attempt_path_for_workload,
    transition_startup_attempt,
)
from quwoquan_ops.cli.lib.test_live_startup_attempt_receipt import (
    UnsafeTestLiveStartupReceiptPath,
    bounded_replace_stale_test_live_startup_attempt, load_test_live_startup_attempt,
    read_stale_test_live_startup_attempt, reclaim_stale_test_live_startup_attempt,
    require_bounded_stale_test_live_startup_attempt,
    test_live_startup_attempt_path, transition_test_live_startup_attempt,
)
from quwoquan_ops.cli.lib.test_live_content_binding import (
    create_test_live_content_binding, load_test_live_content_binding,
)
from quwoquan_ops.cli.lib.local_env_gate_matrix import (
    CANONICAL_TARGETS as CANONICAL_LOCAL_GATE_TARGETS,
    DEVICE_PROFILES as LOCAL_GATE_DEVICE_PROFILES,
    DEVICE_PROFILE_FULL as LOCAL_GATE_DEVICE_PROFILE_FULL, PROFILE_LOCAL_ENV_GATE,
    run_local_env_gate_matrix,
)
from quwoquan_ops.cli.lib.immutable_image_composition import (
    bind_packaged_image_composition, compose_image_environment_key, first_party_service_names,
    immutable_image_digest, local_release_image_environment_key, packaged_runtime_source_image_ref,
    runtime_image_owner_names,
)
from quwoquan_ops.cli.lib.immutable_configuration_composition import packaged_configuration_digest
from quwoquan_ops.cli.lib.local_postgres_migration_drift import (
    format_drift_gate_block, probe_migration_drift,
)
from quwoquan_ops.cli.lib.package_reuse import (
    PACKAGE_INPUT_CAPSULE_DIRECTORY, can_reuse_package, deployment_input_roots,
    materialize_package_input_capsule, verify_package_input_capsule, write_package_fingerprint,
)
from quwoquan_ops.cli.lib.graphql_read_registry_package import (
    materialize_graphql_read_runtime_config, materialize_graphql_read_registry_package,
    resolve_signing_material as resolve_graphql_read_signing_material,
)
from quwoquan_ops.cli.lib.graphql_read_registry_signing import (
    SIGNING_KEY_ID_ENV as GRAPHQL_READ_SIGNING_KEY_ID_ENV,
    SIGNING_PRIVATE_KEY_FILE_ENV as GRAPHQL_READ_SIGNING_PRIVATE_KEY_FILE_ENV,
    TRUSTED_PUBLIC_KEYS_FILE_ENV as GRAPHQL_READ_TRUSTED_PUBLIC_KEYS_FILE_ENV,
)
from quwoquan_ops.cli.lib.local_graphql_read_registry_keys import (
    prepare_local_graphql_read_registry_signing,
)
from quwoquan_ops.cli.lib.runtime_topology_package import (
    CONTENT_COMMERCIAL_COMPOSE_PROFILES, FULL_WORKLOAD_COMPOSE_PROFILES,
    load_runtime_topology_package, materialize_runtime_topology_package,
)
from quwoquan_ops.cli.lib.service_core_composition import (
    SERVICE_CORE_IMAGE_ENV, SERVICE_CORE_MODULE_SET, SERVICE_CORE_WORKLOAD,
    project_compose_document,
)
from quwoquan_ops.cli.lib.deployment_candidate_manifest import (
    RELEASE_INPUT_CLASSIFICATIONS, canonical_contract_graph_digest,
    canonical_local_observability_log_sink_composition, load_candidate_manifest,
    load_provider_binding_overlay, materialize_mutable_provider_binding_overlay,
    materialize_observability_log_sink_package,
    materialize_provider_binding_overlay, materialize_provider_runtime_package,
    observability_log_sink_composition_digest, provider_binding_overlay_build_inputs,
    provider_runtime_image_environment_key,
    release_input_classification as classify_release_inputs, seal_provider_runtime_package_images,
    validate_observability_log_sink_package, validate_release_attestations,
    write_candidate_manifest,
)
from quwoquan_ops.cli.lib.provider_runtime_composition import (
    compile_provider_runtime_composition, validate_provider_runtime_composition,
)
from quwoquan_ops.cli.lib.test_data_verification import (
    build_provider_evidence_document, build_candidate_binding, build_test_data_handoff,
    load_provider_evidence, run_test_data_verification,
)
from quwoquan_ops.cli.lib.test_data.api import TestDataSession
from quwoquan_ops.cli.lib.test_data.capabilities.circle_service import CircleGatheringPlanResult
from quwoquan_ops.cli.lib.test_data.capabilities.common import ActorRole
from quwoquan_ops.cli.lib.test_data.capabilities.user_service import (
    AUTHENTICATED_ACTORS, AuthenticatedActorsParams,
)
from quwoquan_ops.cli.lib.test_data.cases import (
    AcceptanceCaseId, canonical_acceptance_suite, circle_gathering_plan_case,
)
from quwoquan_ops.cli.lib.test_data.model import TestDataContext
from quwoquan_ops.cli.lib.test_data.operations import TestDataRuntime
from quwoquan_ops.cli.lib.test_data.serialization import case_request_document, load_case_requests
from quwoquan_ops.cli.lib.dev_up import (
    DEV_UP_ENVS, DEV_UP_STACK_TARGETS, app_target_for_env, build_start_app_command,
    detect_device_kind, enable_android_adb_reverse, find_device, launch_app,
    pick_dev_up_env, resolve_device_id,
)
from quwoquan_ops.cli.lib.managed_preparation import (
    MANAGED_PREPARATION_SCHEMA, ManagedPreparationBlocked,
    _managed_active_release_readback, _managed_android_adb_reverse_ports, _managed_content_binding, _managed_device_identity,
    _managed_device_trust, _managed_inspect_running_full_runtime,
    _managed_research_readiness_candidates, _managed_runtime_ready,
    _managed_strict_preflight, _write_managed_preparation_receipt, run_managed_preparation,
)
from quwoquan_ops.cli.lib.filter_catalog_release import (
    LOCAL_FILTER_CATALOG_TARGETS, MUTATING_ACTIONS as FILTER_CATALOG_MUTATING_ACTIONS,
    PUBLISH_TOKEN_ENV_DEFAULT, execute_filter_catalog_command,
)
from quwoquan_ops.cli.lib.port_manifest import (
    canonical_port,
    compose_published_endpoint_roles,
    compose_publisher_container_role_closure,
    load_port_manifest,
    profile_ports,
)
from quwoquan_ops.cli.lib.observability import (
    append_log_line, env_from_report_dir, parse_log_records, run_dir as observability_run_dir,
    run_id_from_report_dir, write_run_manifest, write_stackctl_links,
)
from quwoquan_ops.cli.lib.output_paths import (
    PACKAGE_ROOT_OVERRIDE_ENV, activate_deployment_candidate, active_deployment_candidate,
    active_deployment_candidate_snapshot, app_deployment_package_dir,
    assert_active_deployment_candidate_snapshot, deployment_candidate_dir,
    deployment_target_for_env, deployment_target_path, deployment_work_root,
    env_for_target, env_observability_run_dir, env_runs_root,
    legal_static_deployment_package_dir, output_root, portal_deployment_package_dir,
    repo_local_dir, repo_run_dir, repo_runs_root, remove_deployment_tree,
    runtime_shared_deployment_package_dir, service_deployment_package_dir,
    target_cache_dir, target_local_dir, target_process_dir,
    validate_env_run_evidence_dir, web_deployment_package_dir,
)
from quwoquan_ops.migrations.travel_to_gathering import (
    control_plane as travel_to_gathering_migration,
)


def _local_stack_operation_lock(target_name: str) -> Any:
    return _reservation_local_stack_operation_lock(
        target_name,
        lock_path=local_runtime_operation_lock_path(),
    )


def _global_local_operation_lock(
    *,
    scope: str,
    affected_targets: Sequence[str],
) -> Any:
    return _reservation_global_local_operation_lock(
        scope=scope,
        affected_targets=affected_targets,
        lock_path=local_runtime_operation_lock_path(),
    )


# 子命令域外挂模块：argparse 表面与编排胶水迁往 quwoquan_ops/cli/commands/**，
# stackctl 保持唯一入口；此处 import + 再导出保证 dispatch 与测试
# monkeypatch（mock.patch.object(stackctl, ...)）语义零漂移。
from quwoquan_ops.cli.commands import stackctl_dispatch
from quwoquan_ops.cli.commands import app_managed_prepare as app_managed_prepare_commands
from quwoquan_ops.cli.commands import app_preflight as app_preflight_commands
from quwoquan_ops.cli.commands import app_uat_evidence as app_uat_evidence_commands
from quwoquan_ops.cli.commands import app_preflight_shared as app_preflight_shared_commands
from quwoquan_ops.cli.commands import app_preflight_uat as app_preflight_uat_commands
from quwoquan_ops.cli.commands import app_dependency_sync as app_dependency_sync_commands
from quwoquan_ops.cli.commands import assistant_skill_package as assistant_skill_package_commands
from quwoquan_ops.cli.commands import consumer_lease as consumer_lease_commands
from quwoquan_ops.cli.commands import content_acceptance as content_acceptance_commands
from quwoquan_ops.cli.commands import deploy_domain as deploy_domain_commands
from quwoquan_ops.cli.commands import dev_session_domain as dev_session_domain_commands
from quwoquan_ops.cli.commands import device_trust as device_trust_commands
from quwoquan_ops.cli.commands import matrix_domain as matrix_domain_commands
from quwoquan_ops.cli.commands import (
    provider_conformance_domain as provider_conformance_domain_commands,
)
from quwoquan_ops.cli.commands import repair_domain as repair_domain_commands
from quwoquan_ops.cli.commands import doctor as doctor_commands
from quwoquan_ops.cli.commands import down_domain as down_domain_commands
from quwoquan_ops.cli.commands import down_shared as down_shared_commands
from quwoquan_ops.cli.commands import drill as drill_commands
from quwoquan_ops.cli.commands import filter_catalog as filter_catalog_commands
from quwoquan_ops.cli.commands import health as health_commands
from quwoquan_ops.cli.commands import hosted_release_receipt as hosted_release_receipt_commands
from quwoquan_ops.cli.commands import hosted_read_only as hosted_read_only_commands
from quwoquan_ops.cli.commands import inspect_surface as inspect_surface_commands
from quwoquan_ops.cli.commands import loadtest as loadtest_commands
from quwoquan_ops.cli.commands import package_domain as package_domain_commands
from quwoquan_ops.cli.commands import premium_pool as premium_pool_commands
from quwoquan_ops.cli.commands import prod_hosted_plan as prod_hosted_plan_commands
from quwoquan_ops.cli.commands import (
    product_telemetry_log_sink as product_telemetry_log_sink_commands,
)
from quwoquan_ops.cli.commands import provider_config as provider_config_commands
from quwoquan_ops.cli.commands import provider_debug as provider_debug_commands
from quwoquan_ops.cli.commands import research_isolation_probe as research_isolation_probe_commands
from quwoquan_ops.cli.commands import research_consumer_credential as research_consumer_credential_commands
from quwoquan_ops.cli.commands import roll as roll_commands
from quwoquan_ops.cli.commands import status as status_commands
from quwoquan_ops.cli.commands import store_channels as store_channels_commands
from quwoquan_ops.cli.commands import store_distribution as store_distribution_commands
from quwoquan_ops.cli.commands import test_data_surface as test_data_surface_commands
from quwoquan_ops.cli.commands import tls as tls_commands
from quwoquan_ops.cli.commands import up_domain as up_domain_commands
from quwoquan_ops.cli.commands import verify_domain as verify_domain_commands
from quwoquan_ops.cli.commands import verify_kinds as verify_kinds_commands
from quwoquan_ops.cli.commands import verify_profiles as verify_profiles_commands
from quwoquan_ops.cli.commands import verify_shared as verify_shared_commands
from quwoquan_ops.cli.commands.app_preflight import (
    _app_content_readback_summary, _app_content_uat_sample_plan, _execute_otp_login_journey,
    _load_active_release_uat_contract, _resolve_active_app_content_evidence,
    _resolve_test_live_app_content_evidence, _run_app_content_release_probe,
    command_app_content_preflight, command_app_debug_preflight,
    command_app_domain_api_integration,
)
from quwoquan_ops.cli.commands.app_preflight_shared import (
    _DATA_ACTIVATION_SCHEMA, _DATA_COMMERCIAL_READINESS_QUERY_NAMES,
    _DATA_CONSUMER_READINESS_QUERY_NAMES, _DATA_LIFECYCLE_EXIT_SCHEMA, _DATA_READINESS_DIGEST_RE,
    _DATA_READINESS_SCHEMA, _canonical_document_checksum, _data_readiness_segment,
    _data_release_readiness_path, _load_data_release_lifecycle_exit, _load_data_release_readiness,
    _load_test_data_release_readiness, _validate_data_activation_envelope,
    _validate_data_operation_evidence, _validated_string_set,
)
from quwoquan_ops.cli.commands.app_preflight_uat import (
    _ALPHA_APP_CONTENT_TYPED_ACTOR_TARGETS, _APP_CONTENT_TEST_LIVE_STARTUP_IDENTITY_FIELDS,
    _BETA_GAMMA_APP_CONTENT_TYPED_ACTOR_TARGETS, _app_content_patrol_evidence,
    _app_content_experience_screenshot_digests,
    _app_content_test_live_actor_context, _app_content_test_live_runtime_binding,
    _app_content_uat_requires_typed_actor, _command_app_content_uat,
    _ios_direct_flutter_log_reader_retryable,
    _run_app_content_message_home_command, command_app_content_uat,
    APP_CORE_READBACK_UAT_TEST_TARGET, CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET,
    DISCOVERY_FEED_UAT_TEST_TARGET, HOME_VIDEO_PLAYBACK_UAT_TEST_TARGET,
    IOS_DIRECT_FLUTTER_RUN_UAT, MESSAGE_HOME_UAT_TEST_TARGET,
    PROFILE_JOURNEY_UAT_TEST_TARGET, STARTUP_FIRST_FRAME_UAT,
    VIDEO_PLAYBACK_CANARY_UAT_TEST_TARGET,
)
from quwoquan_ops.cli.commands.app_dependency_sync import command_app_dependency_sync
from quwoquan_ops.cli.commands.assistant_skill_package import command_assistant_skill_package
from quwoquan_ops.cli.commands.consumer_lease import command_consumer_lease
from quwoquan_ops.cli.commands.content_acceptance import (
    _content_release_uat_command, _release_feed_post_expectations, _run_data_acceptance_lease,
    _run_release_feed_readback_probe, _run_release_video_delivery_probe,
    command_account_enforcement_uat, command_content_api_consumer,
    command_content_readiness, command_content_uat,
)
from quwoquan_ops.cli.commands.device_trust import command_device_trust
from quwoquan_ops.cli.commands.diagnostics_shared import (
    _CONTENT_DATA_PLANE_ROLES, _candidate_workspace_report, _content_commercial_health_checks,
    _content_consumer_health_checks, _content_data_plane_health_checks, _full_scope_health_checks,
    _health_checks_for_target, _media_edge_health_url, _read_only_user_availability_report,
    _script_probe_plan_for_target, _service_health_checks_for_target,
    validate_read_only_user_availability_report,
)
from quwoquan_ops.cli.commands.doctor import command_doctor
from quwoquan_ops.cli.commands.down_domain import (
    _bind_local_teardown_runtime, _bounded_workload_down_decision, _command_down_unlocked,
    _consumer_lease_down_gate, _receipt_bound_local_compose_model, command_down,
)
from quwoquan_ops.cli.commands.down_shared import (
    _command_mutable_test_live_down, _mutable_test_live_container_ids,
    _mutable_test_live_resource_names, _mutable_test_live_runtime_plan_from_receipt,
    _mutable_test_live_teardown_manifest, _reclaim_orphaned_project_networks,
)
from quwoquan_ops.cli.commands.drill import command_drill
from quwoquan_ops.cli.commands.filter_catalog import (
    _filter_catalog_failure_detail, _write_filter_catalog_command_report, command_filter_catalog,
)
from quwoquan_ops.cli.commands.health import (
    _health_body_evidence, _health_request_policy, _script_probes_for_target, command_health,
)
from quwoquan_ops.cli.commands.hosted_release_receipt import command_hosted_release_receipt
from quwoquan_ops.cli.commands.inspect_surface import (
    _data_report, _local_log_report, _metrics_report, _prometheus_scrape_inspection,
    _runtime_log_evidence_report, _security_report, command_inspect,
)
from quwoquan_ops.cli.commands.loadtest import command_loadtest
from quwoquan_ops.cli.commands.package_domain import _target_package_lock, command_package
from quwoquan_ops.cli.commands.package_runtime import (
    _command_package_unlocked, _run_runtime_compile_preflight, _runtime_package_report_path,
    _validate_runtime_package_identity_readback,
)
from quwoquan_ops.cli.commands.package_shared import (
    _build_package_bound_local_images, _build_runtime_shared_package,
    _command_package_legal_static, _command_package_ops_portal,
)
from quwoquan_ops.cli.commands.premium_pool import command_premium_pool
from quwoquan_ops.cli.commands.prod_hosted_plan import command_prod_hosted_plan
from quwoquan_ops.cli.commands.product_telemetry_log_sink import (
    _load_active_product_telemetry_log_sink, _local_managed_ca_environment,
    _log_sink_control_actions, _log_sink_control_query_session, _log_sink_gate_block_receipt,
    _optional_product_telemetry_environment, _product_telemetry_log_sink_failure_reason,
    _run_product_telemetry_log_sink_control_action, _write_full_workload_log_sink_gate_block,
    _write_product_telemetry_log_sink_control_report, command_product_telemetry_log_sink,
)
from quwoquan_ops.cli.commands.provider_config import command_provider_config
from quwoquan_ops.cli.commands.provider_debug import _normalize_debug_phone, command_provider_debug
from quwoquan_ops.cli.commands.research_isolation_probe import command_research_isolation_probe
from quwoquan_ops.cli.commands.research_consumer_credential import command_research_consumer_credential
from quwoquan_ops.cli.commands.repair_build_cache import (
    _builder_prune_reclaimed_evidence, _canonical_output_layout_plan_ref, _command_result_evidence,
    _consumer_lease_receipt_audit, _finish_build_cache_reclaim,
    _finish_output_layout_reconciliation, _local_build_cache_runtime_audit,
    _output_layout_canonical_truth, _parse_docker_size_bytes, _repair_output_layout,
    _repair_reclaim_build_cache, _run_build_cache_command, _startup_receipt_cache_audit,
)
from quwoquan_ops.cli.commands.deploy_domain import (
    _command_deploy_distribution, _command_deploy_service_environment,
    _command_environment_assembly, _command_prod_prevalidate, _prod_prevalidation_executor,
    _validate_prod_prevalidation_public_bases, command_deploy,
)
from quwoquan_ops.cli.commands.environment_probe import (
    _content_release_public_ready_attempts, _fetch_local_managed_url, _is_retryable_fetch_error,
    _provider_readiness_failure_categories, _read_json_object, _read_json_payload,
    _resolve_test_auth_token, _run_environment_integration_probe,
    _run_provider_readiness_preflight, _run_script_probe, _sanitized_provider_readiness_report,
    _startup_health_failure_for_report, _verify_child_environment, fetch_url,
)
from quwoquan_ops.cli.commands.gamma_release_binding import (
    _bind_beta_external_provider_environment,
    _bind_formal_local_release_provider_environment, _bind_gamma_down_parse_environment,
    _bind_gamma_external_provider_environment, _bind_gamma_object_storage_environment,
    _bind_local_external_provider_environment, _bind_package_provider_reference_environment,
    _gamma_start_command, _inspect_gamma_release_runtime,
    _materialize_release_evidence_configuration,
    _sync_object_storage_binding_aliases,
)
from quwoquan_ops.cli.commands.local_topology_manifest import (
    _all_services, _beta_env_from_port_manifest, _canonical_port_occupancy_report,
    _current_runtime_workload, _expected_local_roles, _formal_release_compose_project_name,
    _gamma_env_from_port_manifest, _network_report, _other_local_target_port_blocks,
    _project_target_runtime_owned_ports, _public_url_origin,
    _published_endpoint_is_occupied, _runtime_owned_port_occupancy_report,
    _scoped_process_environment, _wait_for_network_ports_released,
    _wait_for_published_endpoints_released, socket_probe,
)
from quwoquan_ops.cli.commands.prod_plane_reports import (
    _prod_hosted_placement_coverage_checks, _prod_instance_runtime_reports,
    _prod_plane_runtime_findings, _prod_plane_runtime_report,
)
from quwoquan_ops.cli.commands.provider_runtime_binding import (
    _active_observability_log_sink, _active_provider_runtime, _candidate_bindings_from_snapshot,
    _candidate_observability_log_sink, _candidate_provider_runtime, _external_provider_governance,
    _fixed_candidate_identity, _observability_log_sink_launch_environment, _provider_config,
    _provider_runtime_launch_environment,
)
from quwoquan_ops.cli.commands.runtime_artifact_identity_mount import (
    _bind_artifact_identity_mount_material,
)
from quwoquan_ops.cli.commands.runtime_image_composition import (
    _apply_gamma_image_composition,
    _bind_gamma_build_service_image_refs, _bind_gamma_packaged_configuration_digest,
    _bind_gamma_packaged_service_image_refs,
    _build_missing_runtime_images,
    _build_provider_runtime_images, _load_gamma_runtime_image_composition,
    _load_package_bound_local_image_composition,
    _packaged_service_source_image_ref, _provider_runtime_build_specs,
    _runtime_image_build_spec,
    _sha256_file, _sha256_tree,
)
from quwoquan_ops.cli.commands.runtime_progress_output import (
    _app_launch_failure_detail, _finish_timing, _format_duration_ms, _format_stage_header,
    _is_interactive_terminal, _local_runtime_log_root, _progress_print, _redact_controlled_payload,
    _redact_controlled_values, _remaining_deadline_seconds, _run_with_live_output, _start_timing,
    _tail_file_for_startup, _tail_gamma_container_logs, _tail_multiple_logs_for_startup,
    _write_stdout_markdown, _write_summary_bundle,
)
from quwoquan_ops.cli.commands.dev_session_content_binding import (
    _command_dev_session_bind_content, _dev_session_content_binding_request,
    _dev_session_test_live_content_binding_readiness_issues,
)
from quwoquan_ops.cli.commands.dev_session_domain import (
    _dev_session_launcher_handoff, _run_dev_session_target, command_dev_session,
)
from quwoquan_ops.cli.commands.dev_session_live import (
    _dev_session_regular_json, _dev_session_resume_running_mutable_runtime,
    _start_mutable_test_live_runtime,
)
from quwoquan_ops.cli.commands.dev_session_compose import (
    _dev_session_materialize_compose_files, _dev_session_source_compose_files,
)
from quwoquan_ops.cli.commands.dev_session_runtime import (
    InadmissibleCurrentTestLiveReceipt,
    _bounded_replace_stale_managed_receipt, _dev_session_active_receipts,
    _dev_session_child_args, _dev_session_compose_project,
    _dev_session_finalize_runtime_plan, _dev_session_phase,
    _dev_session_render_runtime_inputs, _dev_session_runtime_preflight,
    _dev_session_target_media_root, _dev_session_workload_conflict,
    _mutable_observability_log_sink_launch_environment,
    _mutable_test_live_operation_identity_environment, _mutable_workspace_snapshot,
)
from quwoquan_ops.cli.lib.local_portal_materialization import (
    materialize_local_portal_root as _materialize_local_portal_root,
)
from quwoquan_ops.cli.commands.dev_session_public_web import (
    _load_dev_session_public_web_package, _resolve_dev_session_public_web_package,
)
from quwoquan_ops.cli.commands.matrix_domain import command_matrix
from quwoquan_ops.cli.commands.provider_conformance_domain import (
    _command_provider_conformance_unlocked, _provider_conformance, _provider_conformance_runner,
    _provider_conformance_runtime_environment, command_provider_conformance,
)
from quwoquan_ops.cli.commands.deploy_prod_finalize import _deploy_prod_hosted_finalize
from quwoquan_ops.cli.commands.deploy_release_inputs import (
    _decision_from_slo_output, _emit_prod_rollout_canary_traffic,
    _load_prod_activation_admission, _materialize_frozen_diagnostic_snapshot,
    _frozen_diagnostic_snapshot,
    _prod_rollout_contract, _prod_rollout_workloads, _prometheus_query_value, _read_prometheus_slo,
    _read_recommendation_slo, _release_transport_tag, _resolve_prod_rollout_stage,
    _slo_settle_seconds, _verify_release_registry_attestations,
)
from quwoquan_ops.cli.commands.deploy_rollout import _command_deploy_with_lock
from quwoquan_ops.cli.commands.deploy_release_state import (
    PROD_RELEASE_UNIT, _archive_release_artifact, _cache_hosted_release_readback,
    _check_exit_passed, _commit_hosted_release_transition, _fetch_hosted_release_ledger_projection,
    _hosted_receipt_id, _load_release_state, _load_release_state_path, _release_check_receipts,
    _release_stage_from_state, _release_state_dir, _required_release_candidate_digests,
    _run_hosted_release_ledger, _sync_release_ledger_projection, _validate_hosted_release_readback,
    _validate_release_transition,
)
from quwoquan_ops.cli.commands.repair_content_recovery import (
    _repair_active_content_release_outbox, _repair_media_processing_dead_letter_indexes,
)
from quwoquan_ops.cli.commands.repair_domain import (
    _finish_orphan_repair_gate_block, _publish_orphan_terminal_success,
    command_repair,
)
from quwoquan_ops.cli.commands.repair_runtime_recovery import (
    _close_orphan_reclaimed_startup_receipt, _commit_orphan_compose_terminal_consumption,
    _complete_orphan_compose_audit_convergence, _current_runtime_health_scope,
    _global_local_build_cache_lock, _global_output_layout_reconciliation_lock,
    _normal_down_structurally_impossible,
    _prod_release_lock, _repair_orphaned_compose,
    _wait_for_attested_orphan_compose_ports_released,
)
from quwoquan_ops.cli.commands.repair_stale_test_live_receipt import (
    repair_stale_test_live_receipt as _repair_stale_test_live_receipt,
)
from quwoquan_ops.cli.commands.repair_undownable_startup_receipt import (
    repair_undownable_startup_receipt as _repair_undownable_startup_receipt,
)
from quwoquan_ops.cli.commands.roll import command_roll
from quwoquan_ops.cli.commands.status import command_status
from quwoquan_ops.cli.commands.store_channels import command_store_channels
from quwoquan_ops.cli.commands.store_distribution import command_store_distribution
from quwoquan_ops.cli.commands.test_data_surface import (
    command_test_data_evidence, command_test_data_request,
)
from quwoquan_ops.cli.commands.tls import command_tls
from quwoquan_ops.cli.commands.up_domain import (
    _command_up_impl, _fixed_candidate_runtime_identity, _reuse_running_full_for_bounded_workload,
    _runtime_identity_mismatches, command_up,
)
from quwoquan_ops.cli.commands.verify_domain import command_verify
from quwoquan_ops.cli.commands.verify_selection import (
    _selected_profile_commands, _selected_verify_commands,
)
from quwoquan_ops.cli.commands.verify_kinds import (
    _command_verify_config_slo, _command_verify_content_delivery, _command_verify_distribution,
    _command_verify_legal_static, _command_verify_service_environment,
    _inspect_distribution_for_target, _legal_static_command, _official_distribution_root,
    _service_verify_report_action,
)
from quwoquan_ops.cli.commands.verify_profiles import (
    _account_enforcement_gamma_uat_profile_command,
    _app_domain_remote_api_integration_profile_command,
    _assistant_learning_gamma_api_integration_profile_command,
    _chat_group_lifecycle_profile_command, _environment_page_smoke_profile_command,
    _media_publication_lifecycle_profile_command,
    _onboarding_author_impact_gamma_api_integration_profile_command,
    _profile_proposal_gamma_api_integration_profile_command,
    _report_feedback_lifecycle_profile_command, _search_remote_api_integration_profile_command,
    _target_media_preflight_profile_command,
)
from quwoquan_ops.cli.commands.verify_shared import (
    _current_commit_sha, _data_readiness_path_from_verify_args, _is_patrol_profile_command,
    _link_profile_preparation_to_page_report, _profile_step,
    _release_video_preflight_from_steps, _run_profile_command,
    _run_profile_commands_parallel, _run_static_verify_wave, _run_test_data_profile,
    _runtime_media_config_hash, _runtime_media_playback_evidence, _typed_profile_actor_context,
    _validate_test_data_request_for_profile, _video_range_evidence_from_preflight,
    _video_ui_evidence_from_smoke,
)

from quwoquan_ops.cli.commands.stackctl_contract import (
    DEFAULT_TARGET_BY_ENV,
    PROVIDER_CONFORMANCE_EVIDENCE_ENVIRONMENTS,
    PROVIDER_CONFORMANCE_LAYERS,
    PROVIDER_CONFORMANCE_RUNTIME_IDENTITY_ENV,
    PROVIDER_CONFORMANCE_SCRIPT,
    RUNTIME_CANDIDATE_ROOT_ENV,
    TEST_DATA_TARGETS,
    VERIFY_COMMAND_GROUPS,
)

# PROD_RELEASE_UNIT 常量已随 release state 迁往 commands/deploy_release_state.py，
# 经下方 re-export 段回填本命名空间。

# CLI summaries should retain every concise prerequisite failure while keeping
# the terminal surface bounded.
COMMAND_SUMMARY_DETAIL_LIMIT = 400
# A cold iOS simulator build can legitimately take several minutes.
ALPHA_APP_FIRST_BUILD_TIMEOUT_SECONDS = 300.0
_PROVIDER_CAPABILITY_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]+)+$"
)


GAMMA_PACKAGED_SERVICE_IMAGE_ENVIRONMENTS: tuple[tuple[str, str], ...] = tuple(
    (service, local_release_image_environment_key(service))
    for service in runtime_image_owner_names()
)


PACKAGE_OCI_IMAGES_SCHEMA = "stackctl-package-oci-images"


# `_build_runtime_shared_package` / `_build_package_bound_local_images` 已迁往
# quwoquan_ops/cli/commands/package_shared.py（仅 package 域消费），
# 顶部 import 再导出保持 stackctl 命名空间与测试 patch 语义。
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified environment packaging, startup, verification, inspection, and rollout control.",
    )
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    parser.add_argument("--report-dir", default="")
    subparsers = parser.add_subparsers(dest="command", required=True)
    travel_to_gathering_migration.register_parser(subparsers)
    package_domain_commands.register_parser(subparsers)

    verify_domain_commands.register_parser(subparsers)

    test_data_surface_commands.register_parser(subparsers)

    matrix_domain_commands.register_parser(subparsers)
    tls_commands.register_parser(subparsers)

    device_trust_commands.register_parser(subparsers)

    store_channels_commands.register_parser(subparsers)

    store_distribution_commands.register_parser(subparsers)

    provider_conformance_domain_commands.register_parser(subparsers)
    provider_config_commands.register_parser(subparsers)

    assistant_skill_package_commands.register_parser(subparsers)

    up_domain_commands.register_parser(subparsers)

    dev_session_domain_commands.register_parser(subparsers)
    product_telemetry_log_sink_commands.register_parser(subparsers)

    down_domain_commands.register_parser(subparsers)

    consumer_lease_commands.register_parser(subparsers)

    status_commands.register_parser(subparsers)

    health_commands.register_parser(subparsers)

    inspect_surface_commands.register_parser(subparsers)

    loadtest_commands.register_parser(subparsers)

    drill_commands.register_parser(subparsers)

    doctor_commands.register_parser(subparsers)

    prod_hosted_plan_commands.register_parser(subparsers)

    content_acceptance_commands.register_content_readiness_parser(subparsers)
    content_acceptance_commands.register_content_api_consumer_parser(subparsers)

    app_managed_prepare_commands.register_parser(subparsers)
    app_preflight_commands.register_parser(subparsers)
    app_dependency_sync_commands.register_parser(subparsers)
    provider_debug_commands.register_parser(subparsers)
    app_preflight_uat_commands.register_parser(subparsers)
    app_uat_evidence_commands.register_parser(subparsers)

    content_acceptance_commands.register_uat_parsers(subparsers)

    filter_catalog_commands.register_parser(subparsers)

    premium_pool_commands.register_parser(subparsers)

    research_isolation_probe_commands.register_parser(subparsers)
    research_consumer_credential_commands.register_parser(subparsers)

    repair_domain_commands.register_parser(subparsers)
    roll_commands.register_parser(subparsers)

    deploy_domain_commands.register_parser(subparsers)
    hosted_release_receipt_commands.register_parser(subparsers)
    hosted_read_only_commands.register_parser(subparsers)
    return parser


def resolve_report_dir(args: argparse.Namespace, env_name: str, target: str) -> Path:
    report_dir = getattr(args, "report_dir", "") or ""
    if report_dir:
        return Path(report_dir)
    return artifact_run_dir(env_name, args.command, target=target or "local")


def validate_up_report_dir(report_dir: str | Path, *, env_name: str) -> Path:
    """Accept `up` evidence writes only inside the selected env runs subtree."""

    return validate_env_run_evidence_dir(report_dir, env_name=env_name)


class _SloSamplesInsufficient(RuntimeError):
    """A deterministic pause condition, never an automatic rollback signal."""


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


LOCAL_BUILD_CACHE_TARGETS: tuple[str, ...] = (
    "alpha-local",
    "beta-local",
    "gamma-local",
)


# `_target_package_lock` / `command_package` 已迁往
# quwoquan_ops/cli/commands/package_domain.py（仅 package 域消费），
# 顶部 import 再导出保持 stackctl 命名空间与测试 patch 语义。
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


# `_command_package_legal_static` / `_command_package_ops_portal` 已迁往
# quwoquan_ops/cli/commands/package_shared.py（仅 package 域消费），
# 顶部 import 再导出保持 stackctl 命名空间与测试 patch 语义;
# verify_ci_cd_evidence_contracts.py 的 SCOPED_FUNCTIONS 已随定义位置同步。
# `_validate_runtime_package_identity_readback` / `_runtime_package_report_path` /
# `_run_runtime_compile_preflight` / `_command_package_unlocked` 已迁往
# quwoquan_ops/cli/commands/package_runtime.py（仅 package 域消费），
# 顶部 import 再导出保持 stackctl 命名空间与测试 patch 语义。
def _resolve_graphql_read_signing_for_local_target(
    environment: str,
    target: str,
):
    try:
        return resolve_graphql_read_signing_material(ROOT)
    except ValueError:
        explicit = (
            GRAPHQL_READ_SIGNING_KEY_ID_ENV,
            GRAPHQL_READ_SIGNING_PRIVATE_KEY_FILE_ENV,
            GRAPHQL_READ_TRUSTED_PUBLIC_KEYS_FILE_ENV,
        )
        if any(str(os.environ.get(name) or "").strip() for name in explicit):
            raise
        if environment == "prod":
            raise ValueError(
                "Prod GraphQL registry package requires explicit signing material"
            )
        return prepare_local_graphql_read_registry_signing(
            ROOT, environment, target
        )


_REQUIRED_RELEASE_EVIDENCE = {
    "contractGraph",
    "providerEvidence",
    "testEvidence",
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
    # Build tools normally print their actionable failure at the end of a
    # long progress stream.  Keeping only the prefix hid that failure and made
    # mutable test-live recovery loop on an untyped Compose error.  Preserve a
    # bounded prefix and suffix so the report contains both build context and
    # the first actionable terminal blocker.
    head_count = COMMAND_SUMMARY_DETAIL_LIMIT // 2
    tail_count = COMMAND_SUMMARY_DETAIL_LIMIT - head_count
    omitted = len(details) - head_count - tail_count
    return [
        *details[:head_count],
        f"... {omitted} command output line(s) omitted ...",
        *details[-tail_count:],
    ]


_DEV_SESSION_WORKLOADS = ("full", "content-release", "content-commercial")


_TEST_LIVE_CONTENT_BINDING_REQUIRED_SERVICES = frozenset(
    {
        SERVICE_CORE_WORKLOAD,
        "recommendation-service",
        # Mutable test-live exposes media through gamma-proxy and reads the
        # release-bound bytes from object-storage.  Both physical services are
        # required before binding Data consumer evidence to the App.
        "gamma-proxy",
        "object-storage",
    }
)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    payload = stackctl_dispatch.dispatch(args, globals())
    return print_result(args, payload)


if __name__ == "__main__":
    raise SystemExit(main())
