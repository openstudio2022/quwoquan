"""Lightweight stackctl entry for read-only diagnostics.

The canonical ``stackctl.py`` script delegates status/health/inspect here before
loading mutating package, release, Data, App UAT, Objective, and migration
domains.  Command implementations remain in ``commands/**``; this module only
provides a lazy compatibility facade for their historical stackctl namespace.
"""
from __future__ import annotations

import argparse
import http.client
import importlib
import json
import socket
import sys
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
READ_ONLY_COMMANDS = frozenset({"status", "health", "inspect", "doctor"})

_BINDINGS: dict[str, tuple[str, str]] = {
    # Canonical command implementations and diagnostic helpers.
    "command_status": ("quwoquan_ops.cli.commands.status", "command_status"),
    "command_health": ("quwoquan_ops.cli.commands.health", "command_health"),
    "command_inspect": ("quwoquan_ops.cli.commands.inspect_surface", "command_inspect"),
    "command_doctor": ("quwoquan_ops.cli.commands.doctor", "command_doctor"),
    "_health_body_evidence": ("quwoquan_ops.cli.commands.health", "_health_body_evidence"),
    "_health_request_policy": ("quwoquan_ops.cli.commands.health", "_health_request_policy"),
    "_script_probes_for_target": ("quwoquan_ops.cli.commands.health", "_script_probes_for_target"),
    "_candidate_workspace_report": ("quwoquan_ops.cli.commands.diagnostics_shared", "_candidate_workspace_report"),
    "_CONTENT_DATA_PLANE_ROLES": ("quwoquan_ops.cli.commands.diagnostics_shared", "_CONTENT_DATA_PLANE_ROLES"),
    "_content_commercial_health_checks": ("quwoquan_ops.cli.commands.diagnostics_shared", "_content_commercial_health_checks"),
    "_content_consumer_health_checks": ("quwoquan_ops.cli.commands.diagnostics_shared", "_content_consumer_health_checks"),
    "_content_data_plane_health_checks": ("quwoquan_ops.cli.commands.diagnostics_shared", "_content_data_plane_health_checks"),
    "_full_scope_health_checks": ("quwoquan_ops.cli.commands.diagnostics_shared", "_full_scope_health_checks"),
    "_health_checks_for_target": ("quwoquan_ops.cli.commands.diagnostics_shared", "_health_checks_for_target"),
    "_media_edge_health_url": ("quwoquan_ops.cli.commands.diagnostics_shared", "_media_edge_health_url"),
    "_read_only_user_availability_report": ("quwoquan_ops.cli.commands.diagnostics_shared", "_read_only_user_availability_report"),
    "_script_probe_plan_for_target": ("quwoquan_ops.cli.commands.diagnostics_shared", "_script_probe_plan_for_target"),
    "_service_health_checks_for_target": ("quwoquan_ops.cli.commands.diagnostics_shared", "_service_health_checks_for_target"),
    "_local_log_report": ("quwoquan_ops.cli.commands.inspect_surface", "_local_log_report"),
    "_runtime_log_evidence_report": ("quwoquan_ops.cli.commands.inspect_surface", "_runtime_log_evidence_report"),
    "_data_report": ("quwoquan_ops.cli.commands.inspect_surface", "_data_report"),
    "_metrics_report": ("quwoquan_ops.cli.commands.inspect_surface", "_metrics_report"),
    "_prometheus_scrape_inspection": ("quwoquan_ops.cli.commands.inspect_surface", "_prometheus_scrape_inspection"),
    "_security_report": ("quwoquan_ops.cli.commands.inspect_surface", "_security_report"),
    # Lightweight topology, output, and immutable-candidate identity.
    "TARGETS": ("quwoquan_ops.cli.lib.environment_topology", "TARGETS"),
    "get_target": ("quwoquan_ops.cli.lib.environment_topology", "get_target"),
    "load_environment_topology": ("quwoquan_ops.cli.lib.environment_topology", "load_environment_topology"),
    "artifact_run_dir": ("quwoquan_ops.cli.lib.common", "artifact_run_dir"),
    "ensure_list": ("quwoquan_ops.cli.lib.common", "ensure_list"),
    "load_json_yaml": ("quwoquan_ops.cli.lib.common", "load_json_yaml"),
    "relpath": ("quwoquan_ops.cli.lib.common", "relpath"),
    "run": ("quwoquan_ops.cli.lib.common", "run"),
    "utc_now": ("quwoquan_ops.cli.lib.common", "utc_now"),
    "write_json": ("quwoquan_ops.cli.lib.common", "write_json"),
    "app_deployment_package_dir": ("quwoquan_ops.cli.lib.output_paths", "app_deployment_package_dir"),
    "active_deployment_candidate": ("quwoquan_ops.cli.lib.output_paths", "active_deployment_candidate"),
    "active_deployment_candidate_snapshot": ("quwoquan_ops.cli.lib.output_paths", "active_deployment_candidate_snapshot"),
    "deployment_candidate_dir": ("quwoquan_ops.cli.lib.output_paths", "deployment_candidate_dir"),
    "env_runs_root": ("quwoquan_ops.cli.lib.output_paths", "env_runs_root"),
    "repo_local_dir": ("quwoquan_ops.cli.lib.output_paths", "repo_local_dir"),
    "repo_runs_root": ("quwoquan_ops.cli.lib.output_paths", "repo_runs_root"),
    "target_process_dir": ("quwoquan_ops.cli.lib.output_paths", "target_process_dir"),
    "load_candidate_manifest": ("quwoquan_ops.cli.lib.deployment_candidate_manifest", "load_candidate_manifest"),
    "package_content_digest": ("quwoquan_ops.cli.lib.package_reuse", "package_content_digest"),
    "can_reuse_package": ("quwoquan_ops.cli.lib.package_reuse", "can_reuse_package"),
    # Runtime topology and health execution.
    "_current_runtime_health_scope": ("quwoquan_ops.cli.commands.repair_runtime_recovery", "_current_runtime_health_scope"),
    "_current_runtime_workload": ("quwoquan_ops.cli.commands.local_topology_manifest", "_current_runtime_workload"),
    "_expected_local_roles": ("quwoquan_ops.cli.commands.local_topology_manifest", "_expected_local_roles"),
    "_network_report": ("quwoquan_ops.cli.commands.local_topology_manifest", "_network_report"),
    "socket_probe": ("quwoquan_ops.cli.commands.local_topology_manifest", "socket_probe"),
    "_public_url_origin": ("quwoquan_ops.cli.commands.local_topology_manifest", "_public_url_origin"),
    "_active_provider_runtime": ("quwoquan_ops.cli.commands.provider_runtime_binding", "_active_provider_runtime"),
    "_active_observability_log_sink": ("quwoquan_ops.cli.commands.provider_runtime_binding", "_active_observability_log_sink"),
    "_candidate_provider_runtime": ("quwoquan_ops.cli.commands.provider_runtime_binding", "_candidate_provider_runtime"),
    "_candidate_observability_log_sink": ("quwoquan_ops.cli.commands.provider_runtime_binding", "_candidate_observability_log_sink"),
    "_fixed_candidate_identity": ("quwoquan_ops.cli.commands.provider_runtime_binding", "_fixed_candidate_identity"),
    "canonical_port": ("quwoquan_ops.cli.lib.port_manifest", "canonical_port"),
    "load_port_manifest": ("quwoquan_ops.cli.lib.port_manifest", "load_port_manifest"),
    "profile_ports": ("quwoquan_ops.cli.lib.port_manifest", "profile_ports"),
    "local_runtime_capacity_evidence": ("quwoquan_ops.cli.lib.local_runtime_capacity", "local_runtime_capacity_evidence"),
    "target_for_hostname": ("quwoquan_ops.cli.lib.local_target_handoff", "target_for_hostname"),
    "root_certificate_path": ("quwoquan_ops.cli.lib.public_domain_tls", "root_certificate_path"),
    "verify_certificate": ("quwoquan_ops.cli.lib.public_domain_tls", "verify_certificate"),
    "PublicDomainTlsError": ("quwoquan_ops.cli.lib.public_domain_tls", "PublicDomainTlsError"),
    "fetch_url": ("quwoquan_ops.cli.commands.environment_probe", "fetch_url"),
    "_fetch_local_managed_url": ("quwoquan_ops.cli.commands.environment_probe", "_fetch_local_managed_url"),
    "_is_retryable_fetch_error": ("quwoquan_ops.cli.commands.environment_probe", "_is_retryable_fetch_error"),
    "_read_json_object": ("quwoquan_ops.cli.commands.environment_probe", "_read_json_object"),
    "_read_json_payload": ("quwoquan_ops.cli.commands.environment_probe", "_read_json_payload"),
    "PROVIDER_CONFORMANCE_SCRIPT": ("quwoquan_ops.cli.commands.stackctl_contract", "PROVIDER_CONFORMANCE_SCRIPT"),
    "RUNTIME_CANDIDATE_ROOT_ENV": ("quwoquan_ops.cli.commands.stackctl_contract", "RUNTIME_CANDIDATE_ROOT_ENV"),
    "PACKAGE_ROOT_OVERRIDE_ENV": ("quwoquan_ops.cli.lib.output_paths", "PACKAGE_ROOT_OVERRIDE_ENV"),
    "_run_environment_integration_probe": ("quwoquan_ops.cli.commands.environment_probe", "_run_environment_integration_probe"),
    "_run_script_probe": ("quwoquan_ops.cli.commands.environment_probe", "_run_script_probe"),
    "_resolve_test_auth_token": ("quwoquan_ops.cli.commands.environment_probe", "_resolve_test_auth_token"),
    "open_test_data_acceptance_session": ("quwoquan_ops.cli.lib.local_environment_auth", "open_test_data_acceptance_session"),
    "close_test_data_acceptance_actor": ("quwoquan_ops.cli.lib.local_environment_auth", "close_test_data_acceptance_actor"),
    "_load_active_product_telemetry_log_sink": ("quwoquan_ops.cli.commands.product_telemetry_log_sink", "_load_active_product_telemetry_log_sink"),
    "load_product_telemetry_log_sink": ("quwoquan_ops.cli.lib.product_telemetry_log_sink", "load_product_telemetry_log_sink"),
    "_legal_static_command": ("quwoquan_ops.cli.commands.verify_kinds", "_legal_static_command"),
    # Timing and report projection.
    "_finish_timing": ("quwoquan_ops.cli.commands.runtime_progress_output", "_finish_timing"),
    "_local_runtime_log_root": ("quwoquan_ops.cli.commands.runtime_progress_output", "_local_runtime_log_root"),
    "_remaining_deadline_seconds": ("quwoquan_ops.cli.commands.runtime_progress_output", "_remaining_deadline_seconds"),
    "_start_timing": ("quwoquan_ops.cli.commands.runtime_progress_output", "_start_timing"),
    "_write_stdout_markdown": ("quwoquan_ops.cli.commands.runtime_progress_output", "_write_stdout_markdown"),
    "_write_summary_bundle": ("quwoquan_ops.cli.commands.runtime_progress_output", "_write_summary_bundle"),
    "parse_log_records": ("quwoquan_ops.cli.lib.observability", "parse_log_records"),
    "append_log_line": ("quwoquan_ops.cli.lib.observability", "append_log_line"),
    "env_from_report_dir": ("quwoquan_ops.cli.lib.observability", "env_from_report_dir"),
    "observability_run_dir": ("quwoquan_ops.cli.lib.observability", "run_dir"),
    "run_id_from_report_dir": ("quwoquan_ops.cli.lib.observability", "run_id_from_report_dir"),
    "write_run_manifest": ("quwoquan_ops.cli.lib.observability", "write_run_manifest"),
    "write_stackctl_links": ("quwoquan_ops.cli.lib.observability", "write_stackctl_links"),
    "write_markdown": ("quwoquan_ops.cli.lib.common", "write_markdown"),
    "_format_duration_ms": ("quwoquan_ops.cli.commands.runtime_progress_output", "_format_duration_ms"),
    "_is_interactive_terminal": ("quwoquan_ops.cli.commands.runtime_progress_output", "_is_interactive_terminal"),
    "_redact_controlled_values": ("quwoquan_ops.cli.commands.runtime_progress_output", "_redact_controlled_values"),
    "_tail_multiple_logs_for_startup": ("quwoquan_ops.cli.commands.runtime_progress_output", "_tail_multiple_logs_for_startup"),
    "compose_file_args": ("quwoquan_ops.cli.lib.compose_layout", "compose_file_args"),
    "gamma_compose_files": ("quwoquan_ops.cli.lib.compose_layout", "gamma_compose_files"),
    # Read-only availability evidence dependencies. They remain lazy and load
    # only when the corresponding evidence layer is actually present.
    "load_startup_attempt": ("quwoquan_ops.cli.lib.startup_attempt_receipt", "load_startup_attempt"),
    "read_startup_attempt": ("quwoquan_ops.cli.lib.startup_attempt_receipt", "read_startup_attempt"),
    "load_test_live_startup_attempt": ("quwoquan_ops.cli.lib.test_live_startup_attempt_receipt", "load_test_live_startup_attempt"),
    "load_test_live_content_binding": ("quwoquan_ops.cli.lib.test_live_content_binding", "load_test_live_content_binding"),
    "inspect_consumer_leases": ("quwoquan_ops.cli.lib.local_runtime_consumer_lease", "inspect_consumer_leases"),
    "device_trust_receipt_path": ("quwoquan_ops.cli.lib.local_device_trust", "_receipt_path"),
    "read_device_trust_receipt": ("quwoquan_ops.cli.lib.local_device_trust", "_read_receipt"),
    "validate_provider_runtime_composition": ("quwoquan_ops.cli.lib.provider_runtime_composition", "validate_provider_runtime_composition"),
    "compile_provider_runtime_composition": ("quwoquan_ops.cli.lib.provider_runtime_composition", "compile_provider_runtime_composition"),
    "_resolve_active_app_content_evidence": ("quwoquan_ops.cli.commands.app_preflight", "_resolve_active_app_content_evidence"),
    "_resolve_test_live_app_content_evidence": ("quwoquan_ops.cli.commands.app_preflight", "_resolve_test_live_app_content_evidence"),
    "_load_active_release_uat_contract": ("quwoquan_ops.cli.commands.app_preflight", "_load_active_release_uat_contract"),
    "_app_content_uat_sample_plan": ("quwoquan_ops.cli.commands.app_preflight", "_app_content_uat_sample_plan"),
    "_DATA_READINESS_DIGEST_RE": ("quwoquan_ops.cli.commands.app_preflight_shared", "_DATA_READINESS_DIGEST_RE"),
    "_DATA_READINESS_SCHEMA": ("quwoquan_ops.cli.commands.app_preflight_shared", "_DATA_READINESS_SCHEMA"),
    "_DATA_ACTIVATION_SCHEMA": ("quwoquan_ops.cli.commands.app_preflight_shared", "_DATA_ACTIVATION_SCHEMA"),
    "_DATA_LIFECYCLE_EXIT_SCHEMA": ("quwoquan_ops.cli.commands.app_preflight_shared", "_DATA_LIFECYCLE_EXIT_SCHEMA"),
    "_DATA_CONSUMER_READINESS_QUERY_NAMES": ("quwoquan_ops.cli.commands.app_preflight_shared", "_DATA_CONSUMER_READINESS_QUERY_NAMES"),
    "_DATA_COMMERCIAL_READINESS_QUERY_NAMES": ("quwoquan_ops.cli.commands.app_preflight_shared", "_DATA_COMMERCIAL_READINESS_QUERY_NAMES"),
    "_data_readiness_segment": ("quwoquan_ops.cli.commands.app_preflight_shared", "_data_readiness_segment"),
    "_data_release_readiness_path": ("quwoquan_ops.cli.commands.app_preflight_shared", "_data_release_readiness_path"),
    "_canonical_document_checksum": ("quwoquan_ops.cli.commands.app_preflight_shared", "_canonical_document_checksum"),
    "_validate_data_activation_envelope": ("quwoquan_ops.cli.commands.app_preflight_shared", "_validate_data_activation_envelope"),
    "_validate_data_operation_evidence": ("quwoquan_ops.cli.commands.app_preflight_shared", "_validate_data_operation_evidence"),
    "_validated_string_set": ("quwoquan_ops.cli.commands.app_preflight_shared", "_validated_string_set"),
    "_load_data_release_readiness": ("quwoquan_ops.cli.commands.app_preflight_readiness", "_load_data_release_readiness"),
    "_load_test_data_release_readiness": ("quwoquan_ops.cli.commands.app_preflight_readiness", "_load_test_data_release_readiness"),
    "_load_data_release_lifecycle_exit": ("quwoquan_ops.cli.commands.app_preflight_readiness", "_load_data_release_lifecycle_exit"),
    "output_root": ("quwoquan_ops.cli.lib.output_paths", "output_root"),
    "build_app_content_uat_plan": ("quwoquan_ops.cli.lib.app_content_uat_plan", "build_app_content_uat_plan"),
    "_inspect_distribution_for_target": ("quwoquan_ops.cli.commands.verify_kinds", "_inspect_distribution_for_target"),
    "_official_distribution_root": ("quwoquan_ops.cli.commands.verify_kinds", "_official_distribution_root"),
    "deployment_target_path": ("quwoquan_ops.cli.lib.output_paths", "deployment_target_path"),
    "inspect_official_distribution": ("quwoquan_ops.cli.lib.official_distribution_release", "inspect_official_distribution"),
    "_sha256_file": ("quwoquan_ops.cli.lib.deployment_candidate_manifest", "_sha256_file"),
    "provider_runtime_image_environment_key": ("quwoquan_ops.cli.lib.deployment_candidate_manifest", "provider_runtime_image_environment_key"),
    "validate_observability_log_sink_package": ("quwoquan_ops.cli.lib.deployment_candidate_manifest", "validate_observability_log_sink_package"),
    "OfficialDistributionReleaseError": ("quwoquan_ops.cli.lib.official_distribution_release", "OfficialDistributionReleaseError"),
    # Inspect-only prod and release surfaces remain dormant for local targets.
    "PROD_RELEASE_UNIT": ("quwoquan_ops.cli.commands.deploy_release_state", "PROD_RELEASE_UNIT"),
    "_load_release_state": ("quwoquan_ops.cli.commands.deploy_release_state", "_load_release_state"),
    "_load_release_state_path": ("quwoquan_ops.cli.commands.deploy_release_state", "_load_release_state_path"),
    "_release_state_dir": ("quwoquan_ops.cli.commands.deploy_release_state", "_release_state_dir"),
    "_prod_instance_runtime_reports": ("quwoquan_ops.cli.commands.prod_plane_reports", "_prod_instance_runtime_reports"),
    "_prod_plane_runtime_findings": ("quwoquan_ops.cli.commands.prod_plane_reports", "_prod_plane_runtime_findings"),
    "_prod_plane_runtime_report": ("quwoquan_ops.cli.commands.prod_plane_reports", "_prod_plane_runtime_report"),
    "ProdHostedTopologyError": ("quwoquan_ops.cli.prod.prod_hosted_topology", "ProdHostedTopologyError"),
    "load_prod_hosted_access_manifest": ("quwoquan_ops.cli.prod.prod_hosted_topology", "load_access_manifest"),
    "prod_hosted_instance_for_stage": ("quwoquan_ops.cli.prod.prod_hosted_topology", "instance_for_stage"),
    "prod_hosted_placement_check_name": ("quwoquan_ops.cli.prod.prod_hosted_topology", "placement_check_name"),
    "resolve_prod_hosted_plan": ("quwoquan_ops.cli.prod.prod_hosted_topology", "resolve_plan"),
    "validate_prod_hosted_host_coverage": ("quwoquan_ops.cli.prod.prod_hosted_topology", "validate_host_coverage"),
    "hosted_release_ledger": ("quwoquan_ops.cli.prod", "hosted_release_ledger"),
    "rollout_stage_promotion_evidence": ("quwoquan_ops.cli.prod", "rollout_stage_promotion_evidence"),
    "ProbeOutcome": ("quwoquan_ops.cli.lib.content_release_readiness", "ProbeOutcome"),
}


class _ReadOnlyStackctlFacade(types.ModuleType):
    """Resolve only the symbol demanded by the selected read-only path."""

    def __getattr__(self, name: str) -> Any:
        binding = _BINDINGS.get(name)
        if binding is None:
            raise AttributeError(f"read-only stackctl facade has no binding for {name}")
        module_name, attribute_name = binding
        value = getattr(importlib.import_module(module_name), attribute_name)
        setattr(self, name, value)
        return value


class _CanonicalLocalHTTPSConnection(http.client.HTTPSConnection):
    def connect(self) -> None:
        from quwoquan_ops.cli.lib.local_target_handoff import LOOPBACK_ADDRESS

        self.sock = socket.create_connection(
            (LOOPBACK_ADDRESS, self.port),
            self.timeout,
            self.source_address,
        )
        if self._tunnel_host:
            self._tunnel()
        server_hostname = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)


def resolve_report_dir(args: argparse.Namespace, env_name: str, target: str) -> Path:
    report_dir = getattr(args, "report_dir", "") or ""
    if report_dir:
        return Path(report_dir)
    from quwoquan_ops.cli.lib.common import artifact_run_dir

    return artifact_run_dir(env_name, args.command, target=target or "local")


def install_facade() -> _ReadOnlyStackctlFacade:
    facade = _ReadOnlyStackctlFacade("quwoquan_ops.cli.stackctl")
    facade.__file__ = str(ROOT / "quwoquan_ops/cli/stackctl.py")
    facade.ROOT = ROOT
    facade.resolve_report_dir = resolve_report_dir
    facade._CanonicalLocalHTTPSConnection = _CanonicalLocalHTTPSConnection
    sys.modules[facade.__name__] = facade
    return facade


def build_parser() -> argparse.ArgumentParser:
    install_facade()
    from quwoquan_ops.cli.commands import doctor, health, inspect_surface, status

    parser = argparse.ArgumentParser(
        description="Unified environment packaging, startup, verification, inspection, and rollout control.",
    )
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    parser.add_argument("--report-dir", default="")
    subparsers = parser.add_subparsers(dest="command", required=True)
    status.register_parser(subparsers)
    health.register_parser(subparsers)
    inspect_surface.register_parser(subparsers)
    doctor.register_parser(subparsers)
    return parser


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    facade = sys.modules["quwoquan_ops.cli.stackctl"]
    payload = getattr(facade, f"command_{args.command}")(args)
    return print_result(args, payload)
