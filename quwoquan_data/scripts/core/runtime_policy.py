"""Strict loader for the single data runtime-policy truth source."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

from core.paths import CONTROL_PLANE_SHARED_ROOT
from core.control_types import RuntimeEnvironment


DEFAULT_RUNTIME_PROFILE_ID = "cursor_local_calibrated"
RUNTIME_PROFILE_ENV = "QWQ_RUNTIME_PROFILE"


@dataclass(frozen=True, slots=True)
class ProviderTimeouts:
    mediawiki_seconds: int
    qunar_seconds: int
    openverse_seconds: int
    overpass_seconds: int


@dataclass(frozen=True, slots=True)
class CoverageDiscoveryPolicy:
    saturation_threshold: float
    saturation_rounds: int
    max_pages_per_cell: int
    max_candidates_per_city_source: int
    max_new_per_cell: int
    request_budget: int
    max_total_candidates: int
    required_empty_pages: int
    request_timeout_seconds: int
    rate_limit_per_second: float
    wiki_category_depth: int
    retry_backoff_multiplier: float
    overpass_result_limit: int


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    profile_id: str
    cursor_model: str
    cursor_runtime: RuntimeEnvironment
    author_workers: int
    reviewer_workers: int
    research_workers: int
    research_wave_size: int
    research_max_waves_per_run: int
    download_concurrency: int
    startup_timeout_seconds: int
    preflight_network_timeout_seconds: int
    agent_timeout_seconds: int
    auth_retry_limit: int
    auth_retry_delay_seconds: int
    no_progress_round_limit: int
    cold_start_max_workers: int
    worker_stagger_seconds: float
    managed_future_grace_seconds: int
    scheduler_stale_seconds: int
    download_fetch_retry_limit: int
    bridge_launch_cooldown_seconds: float
    bridge_ready_delay_seconds: float
    codex_cli_workers: int
    react_rewind_limit: int
    preflight_startup_attempts: int
    preflight_retry_delay_seconds: float
    cursor_warm_attempts: int
    cursor_bridge_max_retries: int
    managed_checkpoint_ref_limit: int
    cursor_bridge_handshake_timeout_seconds: int
    page_image_fetch_max_attempts: int
    page_image_fetch_retry_backoff_seconds: float
    page_image_download_timeout_seconds: int
    download_text_timeout_seconds: int
    download_bytes_timeout_seconds: int
    stage_no_progress_timeout_seconds: int
    research_wave_budget_seconds: int
    network_breaker_threshold: int
    local_process_probe_timeout_seconds: int
    process_termination_timeout_seconds: int
    agent_future_poll_timeout_seconds: int
    api_request_timeout_seconds: int
    entity_reload_timeout_seconds: int
    direct_fetch_timeout_seconds: int
    source_fetch_timeout_seconds: int
    source_fetch_max_retries: int
    ocr_timeout_seconds: int
    mediawiki_fallback_retries: int
    mediawiki_wikitext_max_retries: int
    queue_lease_ttl_seconds: int
    queue_heartbeat_seconds: int
    queue_max_attempts: int
    queue_max_startup_failures: int
    queue_max_wall_clock_seconds: int
    queue_backoff_base_seconds: int
    queue_backoff_cap_seconds: int
    queue_stuck_threshold: int
    startup_probe_suite_attempts: int
    cursor_true_5xx_rate_limit: float
    cursor_startup_timeout_rate_limit: float
    coverage_wiki_retry_limit: int
    coverage_wiki_retry_backoff_seconds: float
    coverage_wiki_inter_request_delay_seconds: float
    coverage_overpass_retry_limit: int
    coverage_overpass_retry_backoff_seconds: float
    coverage_overpass_inter_request_delay_seconds: float
    coverage_overpass_query_timeout_seconds: int
    curl_retries: int
    curl_retry_delay_seconds: int
    provider_timeouts: ProviderTimeouts
    coverage_discovery: CoverageDiscoveryPolicy

    def process_environment(self) -> dict[str, str]:
        """Translate typed policy to SDK/process variables at the process boundary."""
        return {
            RUNTIME_PROFILE_ENV: self.profile_id,
            "QWQ_CURSOR_AGENT_MODEL": self.cursor_model,
            "QWQ_MANAGED_LOCAL_CURSOR_MAX_WORKERS": str(self.author_workers),
            "QWQ_MANAGED_AGENT_TIMEOUT_SECONDS": str(self.agent_timeout_seconds),
            "QWQ_ORCHESTRATE_AGENT_TIMEOUT_SECONDS": str(self.agent_timeout_seconds),
            "QWQ_FANOUT_COLD_START_MAX_WORKERS": str(self.cold_start_max_workers),
            "QWQ_FANOUT_WORKER_STAGGER_SECONDS": str(self.worker_stagger_seconds),
            "QWQ_AUTO_RESEARCH_CURL_RETRIES": str(self.curl_retries),
            "QWQ_AUTO_RESEARCH_CURL_RETRY_DELAY_SECONDS": str(self.curl_retry_delay_seconds),
            "QWQ_MANAGED_AGENT_FUTURE_GRACE_SECONDS": str(self.managed_future_grace_seconds),
            "QWQ_MANAGED_SCHEDULER_STALE_SECONDS": str(self.scheduler_stale_seconds),
            "QWQ_DOWNLOAD_FETCH_ONLY_RETRY_LIMIT": str(self.download_fetch_retry_limit),
            "QWQ_CURSOR_BRIDGE_LAUNCH_COOLDOWN_SECONDS": str(self.bridge_launch_cooldown_seconds),
            "QWQ_CURSOR_BRIDGE_READY_DELAY_SECONDS": str(self.bridge_ready_delay_seconds),
            "QWQ_MANAGED_CODEX_CLI_MAX_WORKERS": str(self.codex_cli_workers),
            "QWQ_MANAGED_PREFLIGHT_STARTUP_ATTEMPTS": str(self.preflight_startup_attempts),
            "QWQ_MANAGED_PREFLIGHT_RETRY_DELAY_SECONDS": str(self.preflight_retry_delay_seconds),
            "QWQ_CURSOR_WARM_ATTEMPTS": str(self.cursor_warm_attempts),
            "QWQ_MANAGED_CHECKPOINT_REF_LIMIT": str(self.managed_checkpoint_ref_limit),
            "QWQ_CURSOR_BRIDGE_TIMEOUT": str(self.cursor_bridge_handshake_timeout_seconds),
        }


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"runtime policy {label} must be a positive integer")
    return value


def _positive_float(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"runtime policy {label} must be positive")
    return float(value)


def _non_negative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"runtime policy {label} must be a non-negative integer")
    return value


def _non_negative_float(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"runtime policy {label} must be non-negative")
    return float(value)


def _mapping(value: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"runtime policy {label} must be an object")
    return value


def _non_empty_string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"runtime policy {label} must be a non-empty string")
    return value.strip()


def runtime_profile_path(profile_id: str) -> Path:
    normalized = str(profile_id or "").strip()
    if not normalized or not normalized.replace("_", "").isalnum():
        raise ValueError("runtime profile id is invalid")
    return CONTROL_PLANE_SHARED_ROOT / f"{normalized}.runtime.yaml"


def load_runtime_policy(profile_id: str) -> RuntimePolicy:
    path = runtime_profile_path(profile_id)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"runtime policy unreadable: {path}: {exc}") from exc
    doc = _mapping(raw, label="document")
    from core.schema import assert_valid

    assert_valid(dict(doc), "execution", "runtime_policy", label=path.as_posix())
    if doc.get("profileId") != profile_id:
        raise ValueError("runtime policy profileId does not match its file name")
    policy = _mapping(doc.get("policy"), label="policy")
    cursor = _mapping(policy.get("cursor"), label="policy.cursor")
    workers = _mapping(policy.get("workers"), label="policy.workers")
    budgets = _mapping(policy.get("budgets"), label="policy.budgets")
    network = _mapping(policy.get("network"), label="policy.network")
    coverage = _mapping(policy.get("coverageDiscovery"), label="policy.coverageDiscovery")
    timeouts = _mapping(network.get("providerTimeoutSeconds"), label="policy.network.providerTimeoutSeconds")
    expected_top = {"cursor", "workers", "budgets", "network", "coverageDiscovery"}
    if set(policy) != expected_top:
        raise ValueError("runtime policy contains unknown or missing policy sections")
    return RuntimePolicy(
        profile_id=profile_id,
        cursor_model=_non_empty_string(cursor.get("model"), label="cursor.model"),
        cursor_runtime=RuntimeEnvironment(
            _non_empty_string(cursor.get("runtime"), label="cursor.runtime")
        ),
        author_workers=_positive_int(workers.get("author"), label="workers.author"),
        reviewer_workers=_positive_int(workers.get("reviewer"), label="workers.reviewer"),
        research_workers=_positive_int(workers.get("research"), label="workers.research"),
        research_wave_size=_positive_int(budgets.get("researchWaveSize"), label="budgets.researchWaveSize"),
        research_max_waves_per_run=_non_negative_int(
            budgets.get("researchMaxWavesPerRun"),
            label="budgets.researchMaxWavesPerRun",
        ),
        download_concurrency=_positive_int(workers.get("download"), label="workers.download"),
        startup_timeout_seconds=_positive_int(budgets.get("startupTimeoutSeconds"), label="budgets.startupTimeoutSeconds"),
        preflight_network_timeout_seconds=_positive_int(
            budgets.get("preflightNetworkTimeoutSeconds"),
            label="budgets.preflightNetworkTimeoutSeconds",
        ),
        agent_timeout_seconds=_positive_int(budgets.get("agentTimeoutSeconds"), label="budgets.agentTimeoutSeconds"),
        auth_retry_limit=_positive_int(budgets.get("authRetryLimit"), label="budgets.authRetryLimit"),
        auth_retry_delay_seconds=_positive_int(budgets.get("authRetryDelaySeconds"), label="budgets.authRetryDelaySeconds"),
        no_progress_round_limit=_positive_int(budgets.get("noProgressRoundLimit"), label="budgets.noProgressRoundLimit"),
        cold_start_max_workers=_positive_int(budgets.get("coldStartMaxWorkers"), label="budgets.coldStartMaxWorkers"),
        worker_stagger_seconds=_positive_float(budgets.get("workerStaggerSeconds"), label="budgets.workerStaggerSeconds"),
        managed_future_grace_seconds=_positive_int(budgets.get("managedFutureGraceSeconds"), label="budgets.managedFutureGraceSeconds"),
        scheduler_stale_seconds=_positive_int(budgets.get("schedulerStaleSeconds"), label="budgets.schedulerStaleSeconds"),
        download_fetch_retry_limit=_non_negative_int(budgets.get("downloadFetchRetryLimit"), label="budgets.downloadFetchRetryLimit"),
        bridge_launch_cooldown_seconds=_non_negative_float(budgets.get("bridgeLaunchCooldownSeconds"), label="budgets.bridgeLaunchCooldownSeconds"),
        bridge_ready_delay_seconds=_non_negative_float(budgets.get("bridgeReadyDelaySeconds"), label="budgets.bridgeReadyDelaySeconds"),
        codex_cli_workers=_positive_int(workers.get("codexCli"), label="workers.codexCli"),
        react_rewind_limit=_positive_int(budgets.get("reactRewindLimit"), label="budgets.reactRewindLimit"),
        preflight_startup_attempts=_positive_int(budgets.get("preflightStartupAttempts"), label="budgets.preflightStartupAttempts"),
        preflight_retry_delay_seconds=_positive_float(budgets.get("preflightRetryDelaySeconds"), label="budgets.preflightRetryDelaySeconds"),
        cursor_warm_attempts=_positive_int(budgets.get("cursorWarmAttempts"), label="budgets.cursorWarmAttempts"),
        cursor_bridge_max_retries=_positive_int(budgets.get("cursorBridgeMaxRetries"), label="budgets.cursorBridgeMaxRetries"),
        managed_checkpoint_ref_limit=_non_negative_int(budgets.get("managedCheckpointRefLimit"), label="budgets.managedCheckpointRefLimit"),
        cursor_bridge_handshake_timeout_seconds=_positive_int(budgets.get("cursorBridgeHandshakeTimeoutSeconds"), label="budgets.cursorBridgeHandshakeTimeoutSeconds"),
        page_image_fetch_max_attempts=_positive_int(budgets.get("pageImageFetchMaxAttempts"), label="budgets.pageImageFetchMaxAttempts"),
        page_image_fetch_retry_backoff_seconds=_positive_float(budgets.get("pageImageFetchRetryBackoffSeconds"), label="budgets.pageImageFetchRetryBackoffSeconds"),
        page_image_download_timeout_seconds=_positive_int(budgets.get("pageImageDownloadTimeoutSeconds"), label="budgets.pageImageDownloadTimeoutSeconds"),
        download_text_timeout_seconds=_positive_int(budgets.get("downloadTextTimeoutSeconds"), label="budgets.downloadTextTimeoutSeconds"),
        download_bytes_timeout_seconds=_positive_int(budgets.get("downloadBytesTimeoutSeconds"), label="budgets.downloadBytesTimeoutSeconds"),
        stage_no_progress_timeout_seconds=_positive_int(budgets.get("stageNoProgressTimeoutSeconds"), label="budgets.stageNoProgressTimeoutSeconds"),
        research_wave_budget_seconds=_positive_int(budgets.get("researchWaveBudgetSeconds"), label="budgets.researchWaveBudgetSeconds"),
        network_breaker_threshold=_positive_int(budgets.get("networkBreakerThreshold"), label="budgets.networkBreakerThreshold"),
        local_process_probe_timeout_seconds=_positive_int(budgets.get("localProcessProbeTimeoutSeconds"), label="budgets.localProcessProbeTimeoutSeconds"),
        process_termination_timeout_seconds=_positive_int(budgets.get("processTerminationTimeoutSeconds"), label="budgets.processTerminationTimeoutSeconds"),
        agent_future_poll_timeout_seconds=_positive_int(budgets.get("agentFuturePollTimeoutSeconds"), label="budgets.agentFuturePollTimeoutSeconds"),
        api_request_timeout_seconds=_positive_int(budgets.get("apiRequestTimeoutSeconds"), label="budgets.apiRequestTimeoutSeconds"),
        entity_reload_timeout_seconds=_positive_int(budgets.get("entityReloadTimeoutSeconds"), label="budgets.entityReloadTimeoutSeconds"),
        direct_fetch_timeout_seconds=_positive_int(budgets.get("directFetchTimeoutSeconds"), label="budgets.directFetchTimeoutSeconds"),
        source_fetch_timeout_seconds=_positive_int(budgets.get("sourceFetchTimeoutSeconds"), label="budgets.sourceFetchTimeoutSeconds"),
        source_fetch_max_retries=_positive_int(budgets.get("sourceFetchMaxRetries"), label="budgets.sourceFetchMaxRetries"),
        ocr_timeout_seconds=_positive_int(budgets.get("ocrTimeoutSeconds"), label="budgets.ocrTimeoutSeconds"),
        mediawiki_fallback_retries=_positive_int(budgets.get("mediawikiFallbackRetries"), label="budgets.mediawikiFallbackRetries"),
        mediawiki_wikitext_max_retries=_positive_int(budgets.get("mediawikiWikitextMaxRetries"), label="budgets.mediawikiWikitextMaxRetries"),
        queue_lease_ttl_seconds=_positive_int(budgets.get("queueLeaseTtlSeconds"), label="budgets.queueLeaseTtlSeconds"),
        queue_heartbeat_seconds=_positive_int(budgets.get("queueHeartbeatSeconds"), label="budgets.queueHeartbeatSeconds"),
        queue_max_attempts=_positive_int(budgets.get("queueMaxAttempts"), label="budgets.queueMaxAttempts"),
        queue_max_startup_failures=_positive_int(budgets.get("queueMaxStartupFailures"), label="budgets.queueMaxStartupFailures"),
        queue_max_wall_clock_seconds=_positive_int(budgets.get("queueMaxWallClockSeconds"), label="budgets.queueMaxWallClockSeconds"),
        queue_backoff_base_seconds=_positive_int(budgets.get("queueBackoffBaseSeconds"), label="budgets.queueBackoffBaseSeconds"),
        queue_backoff_cap_seconds=_positive_int(budgets.get("queueBackoffCapSeconds"), label="budgets.queueBackoffCapSeconds"),
        queue_stuck_threshold=_positive_int(budgets.get("queueStuckThreshold"), label="budgets.queueStuckThreshold"),
        startup_probe_suite_attempts=_positive_int(budgets.get("startupProbeSuiteAttempts"), label="budgets.startupProbeSuiteAttempts"),
        cursor_true_5xx_rate_limit=_positive_float(budgets.get("cursorTrue5xxRateLimit"), label="budgets.cursorTrue5xxRateLimit"),
        cursor_startup_timeout_rate_limit=_positive_float(budgets.get("cursorStartupTimeoutRateLimit"), label="budgets.cursorStartupTimeoutRateLimit"),
        coverage_wiki_retry_limit=_positive_int(budgets.get("coverageWikiRetryLimit"), label="budgets.coverageWikiRetryLimit"),
        coverage_wiki_retry_backoff_seconds=_positive_float(budgets.get("coverageWikiRetryBackoffSeconds"), label="budgets.coverageWikiRetryBackoffSeconds"),
        coverage_wiki_inter_request_delay_seconds=_non_negative_float(budgets.get("coverageWikiInterRequestDelaySeconds"), label="budgets.coverageWikiInterRequestDelaySeconds"),
        coverage_overpass_retry_limit=_positive_int(budgets.get("coverageOverpassRetryLimit"), label="budgets.coverageOverpassRetryLimit"),
        coverage_overpass_retry_backoff_seconds=_positive_float(budgets.get("coverageOverpassRetryBackoffSeconds"), label="budgets.coverageOverpassRetryBackoffSeconds"),
        coverage_overpass_inter_request_delay_seconds=_non_negative_float(budgets.get("coverageOverpassInterRequestDelaySeconds"), label="budgets.coverageOverpassInterRequestDelaySeconds"),
        coverage_overpass_query_timeout_seconds=_positive_int(budgets.get("coverageOverpassQueryTimeoutSeconds"), label="budgets.coverageOverpassQueryTimeoutSeconds"),
        curl_retries=_positive_int(network.get("curlRetries"), label="network.curlRetries"),
        curl_retry_delay_seconds=_positive_int(network.get("curlRetryDelaySeconds"), label="network.curlRetryDelaySeconds"),
        provider_timeouts=ProviderTimeouts(
            mediawiki_seconds=_positive_int(timeouts.get("mediawiki"), label="providerTimeoutSeconds.mediawiki"),
            qunar_seconds=_positive_int(timeouts.get("qunar"), label="providerTimeoutSeconds.qunar"),
            openverse_seconds=_positive_int(timeouts.get("openverse"), label="providerTimeoutSeconds.openverse"),
            overpass_seconds=_positive_int(timeouts.get("overpass"), label="providerTimeoutSeconds.overpass"),
        ),
        coverage_discovery=CoverageDiscoveryPolicy(
            saturation_threshold=_positive_float(
                coverage.get("saturationThreshold"),
                label="coverageDiscovery.saturationThreshold",
            ),
            saturation_rounds=_positive_int(
                coverage.get("saturationRounds"),
                label="coverageDiscovery.saturationRounds",
            ),
            max_pages_per_cell=_positive_int(
                coverage.get("maxPagesPerCell"),
                label="coverageDiscovery.maxPagesPerCell",
            ),
            max_candidates_per_city_source=_positive_int(
                coverage.get("maxCandidatesPerCitySource"),
                label="coverageDiscovery.maxCandidatesPerCitySource",
            ),
            max_new_per_cell=_positive_int(
                coverage.get("maxNewPerCell"),
                label="coverageDiscovery.maxNewPerCell",
            ),
            request_budget=_positive_int(
                coverage.get("requestBudget"),
                label="coverageDiscovery.requestBudget",
            ),
            max_total_candidates=_non_negative_int(
                coverage.get("maxTotalCandidates"),
                label="coverageDiscovery.maxTotalCandidates",
            ),
            required_empty_pages=_positive_int(
                coverage.get("requiredEmptyPages"),
                label="coverageDiscovery.requiredEmptyPages",
            ),
            request_timeout_seconds=_positive_int(
                coverage.get("requestTimeoutSeconds"),
                label="coverageDiscovery.requestTimeoutSeconds",
            ),
            rate_limit_per_second=_positive_float(
                coverage.get("rateLimitPerSecond"),
                label="coverageDiscovery.rateLimitPerSecond",
            ),
            wiki_category_depth=_non_negative_int(
                coverage.get("wikiCategoryDepth"),
                label="coverageDiscovery.wikiCategoryDepth",
            ),
            retry_backoff_multiplier=_positive_float(
                coverage.get("retryBackoffMultiplier"),
                label="coverageDiscovery.retryBackoffMultiplier",
            ),
            overpass_result_limit=_positive_int(
                coverage.get("overpassResultLimit"),
                label="coverageDiscovery.overpassResultLimit",
            ),
        ),
    )


def active_runtime_policy() -> RuntimePolicy:
    return load_runtime_policy(os.environ.get(RUNTIME_PROFILE_ENV, DEFAULT_RUNTIME_PROFILE_ID))


def apply_runtime_policy(policy: RuntimePolicy) -> None:
    for key, value in policy.process_environment().items():
        os.environ[key] = value


__all__ = [
    "DEFAULT_RUNTIME_PROFILE_ID",
    "RUNTIME_PROFILE_ENV",
    "ProviderTimeouts",
    "CoverageDiscoveryPolicy",
    "RuntimePolicy",
    "active_runtime_policy",
    "apply_runtime_policy",
    "load_runtime_policy",
    "runtime_profile_path",
]
