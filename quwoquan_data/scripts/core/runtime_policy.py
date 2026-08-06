"""Strict loader for the single data runtime-policy truth source."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from core.control_types import AgentProvider, RuntimeEnvironment
from core.cursor_model import CursorModelParameter, CursorModelSelection
from core.paths import CONTROL_PLANE_SHARED_ROOT
from core.runtime_policy_types import (
    CoverageDiscoveryPolicy,
    ExplicitSemanticSelection,
    ProviderTimeouts,
    RuntimeEvidencePolicy,
    SemanticAgentBinding,
    SemanticCalibrationPolicy,
    SemanticCapacityPolicy,
)
from core.runtime_policy_types import (
    explicit_semantic_selections as _explicit_semantic_selections,
)
from core.runtime_policy_types import (
    mapping as _mapping,
)
from core.runtime_policy_types import (
    non_empty_string as _non_empty_string,
)
from core.runtime_policy_types import (
    non_empty_string_tuple as _non_empty_string_tuple,
)
from core.runtime_policy_types import (
    semantic_binding as _semantic_binding,
)

DEFAULT_RUNTIME_PROFILE_ID = "semantic_agent_local_calibrated"


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    profile_id: str
    semantic_author: SemanticAgentBinding
    semantic_reviewer: SemanticAgentBinding
    semantic_calibration: SemanticCalibrationPolicy
    semantic_capacity: SemanticCapacityPolicy
    runtime_evidence: RuntimeEvidencePolicy
    explicit_semantic_selections: tuple[ExplicitSemanticSelection, ...]
    semantic_fallback_policy: str
    semantic_agent_runtime: RuntimeEnvironment
    author_workers: int
    reviewer_workers: int
    research_workers: int
    research_wave_size: int
    campaign_lane_workers: int
    research_max_waves_per_run: int
    source_plan_recovery_passes: int
    source_plan_recovery_workers: int
    download_concurrency: int
    cursor_bridge_instances: int
    oversample_factor: float
    startup_timeout_seconds: int
    campaign_submission_timeout_seconds: int
    campaign_lane_timeout_seconds: int
    preflight_network_timeout_seconds: int
    agent_timeout_seconds: int
    auth_retry_limit: int
    auth_retry_delay_seconds: int
    no_progress_round_limit: int
    cold_start_max_workers: int
    worker_stagger_seconds: float
    managed_future_grace_seconds: int
    scheduler_stale_seconds: int
    controller_lease_stale_seconds: int
    assignment_deadline_seconds: int
    download_fetch_retry_limit: int
    bridge_launch_cooldown_seconds: float
    bridge_ready_delay_seconds: float
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
    direct_fetch_timeout_seconds: int
    source_fetch_timeout_seconds: int
    source_video_read_timeout_seconds: int
    source_fetch_max_retries: int
    ocr_timeout_seconds: int
    video_probe_timeout_seconds: int
    video_transcode_timeout_seconds: int
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
    cursor_startup_probe_cache_ttl_seconds: int
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

    @property
    def semantic_agent_provider(self) -> AgentProvider:
        """Primary author provider used by legacy-neutral orchestration call sites."""
        return self.semantic_author.provider

    @property
    def semantic_agent_model(self) -> str:
        return self.semantic_author.model

    @property
    def semantic_agent_model_parameters(self) -> tuple[CursorModelParameter, ...]:
        return self.semantic_author.model_parameters

    @property
    def semantic_agent_model_selection(self) -> CursorModelSelection:
        return self.semantic_author.selection

    def explicit_semantic_selection(
        self,
        selection_id: str,
    ) -> ExplicitSemanticSelection:
        normalized = str(selection_id or "").strip()
        matches = [
            selection
            for selection in self.explicit_semantic_selections
            if selection.selection_id == normalized
        ]
        if len(matches) != 1:
            raise ValueError(f"unknown explicit semantic selection: {normalized}")
        return matches[0]

    def process_environment(self) -> dict[str, str]:
        """Translate typed policy to SDK/process variables at the process boundary."""
        return {
            "QWQ_SEMANTIC_AGENT_PROVIDER": self.semantic_agent_provider.value,
            "QWQ_SEMANTIC_AGENT_MODEL": self.semantic_agent_model,
            "QWQ_SEMANTIC_REVIEWER_PROVIDER": self.semantic_reviewer.provider.value,
            "QWQ_SEMANTIC_REVIEWER_MODEL": self.semantic_reviewer.model,
            "QWQ_SEMANTIC_CALIBRATION_PROVIDER": self.semantic_calibration.binding.provider.value,
            "QWQ_SEMANTIC_CALIBRATION_MODEL": self.semantic_calibration.binding.model,
            "QWQ_MANAGED_LOCAL_SEMANTIC_AGENT_MAX_WORKERS": str(self.author_workers),
            "QWQ_CURSOR_BRIDGE_INSTANCES": str(self.cursor_bridge_instances),
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


def _oversample_factor(value: object, *, label: str) -> float:
    """候选池相对准出配额的过采系数；小于 1 会让候选池永远无法覆盖配额。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 1:
        raise ValueError(f"runtime policy {label} must be a number >= 1")
    return float(value)


def runtime_profile_path(profile_id: str) -> Path:
    normalized = str(profile_id or "").strip()
    if not normalized or not normalized.replace("_", "").isalnum():
        raise ValueError("runtime profile id is invalid")
    return CONTROL_PLANE_SHARED_ROOT / f"{normalized}.runtime.yaml"


def runtime_profile_digest(profile_id: str) -> str:
    return "sha256:" + hashlib.sha256(runtime_profile_path(profile_id).read_bytes()).hexdigest()


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
    semantic_agent = _mapping(
        policy.get("semanticAgent"),
        label="policy.semanticAgent",
    )
    semantic_author = _semantic_binding(
        semantic_agent.get("author"),
        label="policy.semanticAgent.author",
    )
    semantic_reviewer = _semantic_binding(
        semantic_agent.get("reviewer"),
        label="policy.semanticAgent.reviewer",
    )
    calibration = _mapping(
        semantic_agent.get("calibration"),
        label="policy.semanticAgent.calibration",
    )
    capacity = _mapping(
        semantic_agent.get("capacity"),
        label="policy.semanticAgent.capacity",
    )
    workers = _mapping(policy.get("workers"), label="policy.workers")
    selection = _mapping(policy.get("selection"), label="policy.selection")
    budgets = _mapping(policy.get("budgets"), label="policy.budgets")
    network = _mapping(policy.get("network"), label="policy.network")
    coverage = _mapping(policy.get("coverageDiscovery"), label="policy.coverageDiscovery")
    runtime_evidence = _mapping(
        policy.get("runtimeEvidence"), label="policy.runtimeEvidence"
    )
    timeouts = _mapping(network.get("providerTimeoutSeconds"), label="policy.network.providerTimeoutSeconds")
    expected_top = {
        "semanticAgent",
        "workers",
        "selection",
        "budgets",
        "network",
        "coverageDiscovery",
        "runtimeEvidence",
    }
    if set(policy) != expected_top:
        raise ValueError("runtime policy contains unknown or missing policy sections")
    return RuntimePolicy(
        profile_id=profile_id,
        semantic_author=semantic_author,
        semantic_reviewer=semantic_reviewer,
        semantic_calibration=SemanticCalibrationPolicy(
            binding=_semantic_binding(
                calibration,
                label="policy.semanticAgent.calibration",
            ),
            sample_rate=_positive_float(
                calibration.get("sampleRate"),
                label="semanticAgent.calibration.sampleRate",
            ),
            minimum_sample_count=_positive_int(
                calibration.get("minimumSampleCount"),
                label="semanticAgent.calibration.minimumSampleCount",
            ),
            small_batch_policy=_non_empty_string(
                calibration.get("smallBatchPolicy"),
                label="semanticAgent.calibration.smallBatchPolicy",
            ),
        ),
        semantic_capacity=SemanticCapacityPolicy(
            account_scope_id=_non_empty_string(
                capacity.get("accountScopeId"),
                label="semanticAgent.capacity.accountScopeId",
            ),
            host_scope_id=_non_empty_string(
                capacity.get("hostScopeId"),
                label="semanticAgent.capacity.hostScopeId",
            ),
            requests_per_minute=_positive_int(
                capacity.get("requestsPerMinute"),
                label="semanticAgent.capacity.requestsPerMinute",
            ),
            burst_limit=_positive_int(
                capacity.get("burstLimit"),
                label="semanticAgent.capacity.burstLimit",
            ),
            lane_concurrency_limit=_positive_int(
                capacity.get("laneConcurrencyLimit"),
                label="semanticAgent.capacity.laneConcurrencyLimit",
            ),
            receipt_ttl_seconds=_positive_int(
                capacity.get("receiptTtlSeconds"),
                label="semanticAgent.capacity.receiptTtlSeconds",
            ),
        ),
        runtime_evidence=RuntimeEvidencePolicy(
            process_inspection_timeout_seconds=_positive_float(
                runtime_evidence.get("processInspectionTimeoutSeconds"),
                label="runtimeEvidence.processInspectionTimeoutSeconds",
            ),
            queue_fault_event_timeout_seconds=_positive_float(
                runtime_evidence.get("queueFaultEventTimeoutSeconds"),
                label="runtimeEvidence.queueFaultEventTimeoutSeconds",
            ),
        ),
        explicit_semantic_selections=_explicit_semantic_selections(
            semantic_agent.get("explicitSelections"),
            label="policy.semanticAgent.explicitSelections",
        ),
        semantic_fallback_policy=_non_empty_string(
            semantic_agent.get("fallbackPolicy"),
            label="semanticAgent.fallbackPolicy",
        ),
        semantic_agent_runtime=RuntimeEnvironment(
            _non_empty_string(
                semantic_agent.get("runtime"),
                label="semanticAgent.runtime",
            )
        ),
        author_workers=_positive_int(workers.get("author"), label="workers.author"),
        reviewer_workers=_positive_int(workers.get("reviewer"), label="workers.reviewer"),
        research_workers=_positive_int(workers.get("research"), label="workers.research"),
        campaign_lane_workers=_positive_int(
            workers.get("campaignLaneWorkers"),
            label="workers.campaignLaneWorkers",
        ),
        research_wave_size=_positive_int(budgets.get("researchWaveSize"), label="budgets.researchWaveSize"),
        research_max_waves_per_run=_non_negative_int(
            budgets.get("researchMaxWavesPerRun"),
            label="budgets.researchMaxWavesPerRun",
        ),
        source_plan_recovery_passes=_non_negative_int(
            budgets.get("sourcePlanRecoveryPasses"),
            label="budgets.sourcePlanRecoveryPasses",
        ),
        source_plan_recovery_workers=_positive_int(
            budgets.get("sourcePlanRecoveryWorkers"),
            label="budgets.sourcePlanRecoveryWorkers",
        ),
        download_concurrency=_positive_int(workers.get("download"), label="workers.download"),
        cursor_bridge_instances=_positive_int(
            workers.get("cursorBridgeInstances"),
            label="workers.cursorBridgeInstances",
        ),
        oversample_factor=_oversample_factor(
            selection.get("oversampleFactor"),
            label="selection.oversampleFactor",
        ),
        startup_timeout_seconds=_positive_int(budgets.get("startupTimeoutSeconds"), label="budgets.startupTimeoutSeconds"),
        campaign_submission_timeout_seconds=_positive_int(
            budgets.get("campaignSubmissionTimeoutSeconds"),
            label="budgets.campaignSubmissionTimeoutSeconds",
        ),
        campaign_lane_timeout_seconds=_positive_int(
            budgets.get("campaignLaneTimeoutSeconds"),
            label="budgets.campaignLaneTimeoutSeconds",
        ),
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
        controller_lease_stale_seconds=_positive_int(
            budgets.get("controllerLeaseStaleSeconds"),
            label="budgets.controllerLeaseStaleSeconds",
        ),
        assignment_deadline_seconds=_positive_int(
            budgets.get("assignmentDeadlineSeconds"),
            label="budgets.assignmentDeadlineSeconds",
        ),
        download_fetch_retry_limit=_non_negative_int(budgets.get("downloadFetchRetryLimit"), label="budgets.downloadFetchRetryLimit"),
        bridge_launch_cooldown_seconds=_non_negative_float(budgets.get("bridgeLaunchCooldownSeconds"), label="budgets.bridgeLaunchCooldownSeconds"),
        bridge_ready_delay_seconds=_non_negative_float(budgets.get("bridgeReadyDelaySeconds"), label="budgets.bridgeReadyDelaySeconds"),
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
        direct_fetch_timeout_seconds=_positive_int(budgets.get("directFetchTimeoutSeconds"), label="budgets.directFetchTimeoutSeconds"),
        source_fetch_timeout_seconds=_positive_int(budgets.get("sourceFetchTimeoutSeconds"), label="budgets.sourceFetchTimeoutSeconds"),
        source_video_read_timeout_seconds=_positive_int(
            budgets.get("sourceVideoReadTimeoutSeconds"),
            label="budgets.sourceVideoReadTimeoutSeconds",
        ),
        source_fetch_max_retries=_positive_int(budgets.get("sourceFetchMaxRetries"), label="budgets.sourceFetchMaxRetries"),
        ocr_timeout_seconds=_positive_int(budgets.get("ocrTimeoutSeconds"), label="budgets.ocrTimeoutSeconds"),
        video_probe_timeout_seconds=_positive_int(
            budgets.get("videoProbeTimeoutSeconds"),
            label="budgets.videoProbeTimeoutSeconds",
        ),
        video_transcode_timeout_seconds=_positive_int(
            budgets.get("videoTranscodeTimeoutSeconds"),
            label="budgets.videoTranscodeTimeoutSeconds",
        ),
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
        cursor_startup_probe_cache_ttl_seconds=_non_negative_int(
            budgets.get("cursorStartupProbeCacheTtlSeconds"),
            label="budgets.cursorStartupProbeCacheTtlSeconds",
        ),
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
            encyclopedia_seconds=_positive_int(
                timeouts.get("encyclopedia"),
                label="providerTimeoutSeconds.encyclopedia",
            ),
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
            wikidata_sparql_endpoint=_non_empty_string(
                coverage.get("wikidataSparqlEndpoint"),
                label="coverageDiscovery.wikidataSparqlEndpoint",
            ),
            wikidata_result_limit=_positive_int(
                coverage.get("wikidataResultLimit"),
                label="coverageDiscovery.wikidataResultLimit",
            ),
            overpass_concurrency=_positive_int(
                coverage.get("overpassConcurrency"),
                label="coverageDiscovery.overpassConcurrency",
            ),
            overpass_result_limit=_positive_int(
                coverage.get("overpassResultLimit"),
                label="coverageDiscovery.overpassResultLimit",
            ),
            overpass_endpoints=_non_empty_string_tuple(
                coverage.get("overpassEndpoints"),
                label="coverageDiscovery.overpassEndpoints",
            ),
        ),
    )


def active_runtime_policy() -> RuntimePolicy:
    return load_runtime_policy(DEFAULT_RUNTIME_PROFILE_ID)


def apply_runtime_policy(policy: RuntimePolicy) -> None:
    for key, value in policy.process_environment().items():
        os.environ[key] = value


__all__ = [
    "DEFAULT_RUNTIME_PROFILE_ID",
    "CoverageDiscoveryPolicy",
    "ExplicitSemanticSelection",
    "ProviderTimeouts",
    "RuntimeEvidencePolicy",
    "RuntimePolicy",
    "SemanticAgentBinding",
    "SemanticCalibrationPolicy",
    "SemanticCapacityPolicy",
    "active_runtime_policy",
    "apply_runtime_policy",
    "load_runtime_policy",
    "runtime_profile_digest",
    "runtime_profile_path",
]
