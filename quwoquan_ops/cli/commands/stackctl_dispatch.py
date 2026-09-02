"""Top-level stackctl command dispatch.

Handlers are resolved from the caller namespace at dispatch time.  This keeps
``quwoquan_ops.cli.stackctl`` as the stable monkeypatch/API surface while the
command-to-handler responsibility lives outside the canonical entry module.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from typing import Any, Callable


CommandHandler = Callable[[argparse.Namespace], dict[str, Any]]

_STACKCTL_HANDLER_NAMES = {
    "package": "command_package",
    "verify": "command_verify",
    "test-data-request": "command_test_data_request",
    "test-data-evidence": "command_test_data_evidence",
    "matrix": "command_matrix",
    "tls": "command_tls",
    "device-trust": "command_device_trust",
    "store-channels": "command_store_channels",
    "store-distribution": "command_store_distribution",
    "provider-conformance": "command_provider_conformance",
    "provider-config": "command_provider_config",
    "assistant-skill-package": "command_assistant_skill_package",
    "dev-session": "command_dev_session",
    "up": "command_up",
    "product-telemetry-log-sink": "command_product_telemetry_log_sink",
    "down": "command_down",
    "consumer-lease": "command_consumer_lease",
    "status": "command_status",
    "health": "command_health",
    "loadtest": "command_loadtest",
    "drill": "command_drill",
    "prod-hosted-plan": "command_prod_hosted_plan",
    "inspect": "command_inspect",
    "doctor": "command_doctor",
    "content-readiness": "command_content_readiness",
    "research-isolation-probe": "command_research_isolation_probe",
    "research-consumer-credential": "command_research_consumer_credential",
    "app-content-preflight": "command_app_content_preflight",
    "app-debug-preflight": "command_app_debug_preflight",
    "app-domain-api-integration": "command_app_domain_api_integration",
    "app-dependency-sync": "command_app_dependency_sync",
    "provider-debug": "command_provider_debug",
    "app-content-uat": "command_app_content_uat",
    "content-uat": "command_content_uat",
    "account-enforcement-uat": "command_account_enforcement_uat",
    "filter-catalog": "command_filter_catalog",
    "premium-pool": "command_premium_pool",
    "repair": "command_repair",
    "roll": "command_roll",
    "deploy": "command_deploy",
    "hosted-release-receipt": "command_hosted_release_receipt",
}


def command_handlers(namespace: Mapping[str, Any]) -> dict[str, CommandHandler]:
    """Build the handler table from the live stackctl namespace."""

    handlers = {
        command: namespace[handler_name]
        for command, handler_name in _STACKCTL_HANDLER_NAMES.items()
    }
    handlers["app-managed-prepare"] = namespace[
        "app_managed_prepare_commands"
    ].command_app_managed_prepare
    handlers.update(namespace["app_uat_evidence_commands"].COMMAND_HANDLERS)
    handlers["hosted-read-only"] = namespace[
        "hosted_read_only_commands"
    ].command_hosted_read_only
    handlers["migration"] = namespace[
        "travel_to_gathering_migration"
    ].command
    return handlers


def dispatch(
    args: argparse.Namespace,
    namespace: Mapping[str, Any],
) -> dict[str, Any]:
    """Dispatch parsed arguments through the caller's live handler surface."""

    return command_handlers(namespace)[args.command](args)
