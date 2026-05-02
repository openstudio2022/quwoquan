import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:quwoquan_app/assistant/context/assembly/recall_coordinator.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_plan_view.dart';
import 'package:quwoquan_app/assistant/contracts/context_assembly_result.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/contracts/system_context_envelope.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/reasoning/routing/domain_router.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/capability_catalog.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_context_scope_hint_view.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_state_keys.dart';

/// Bootstrap: session resolution, context assembly, catalog loading.
class BootstrapPhase implements Phase {
  const BootstrapPhase({
    required this.runtime,
    required this.sessionManager,
    required this.memoryRepository,
    required this.contextOrchestrator,
    required this.templateCatalogRuntime,
    required this.domainRouter,
    required this.recallCoordinator,
    this.toolMetadataRegistry,
  });

  final ReactRuntime runtime;
  final AssistantSessionManager sessionManager;
  final AssistantMemoryRepository memoryRepository;
  final PersonalAssistantContextOrchestrator contextOrchestrator;
  final TemplateCatalogRuntime templateCatalogRuntime;
  final AssistantDomainRouter domainRouter;
  final RecallCoordinator recallCoordinator;
  final ToolMetadataRegistry? toolMetadataRegistry;

  @override
  String get phaseId => 'bootstrap';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    final request = coerceAssistantRunRequest(input.request);
    final latestUserQuery = request.messages.isNotEmpty
        ? request.messages.last.content
        : '';
    final contextScopeHintView = AssistantPipelineContextScopeHintView(
      request.contextScopeHint,
    );
    final forceRefreshCatalog = contextScopeHintView.forceRefreshCatalog;
    await sessionManager.load();
    final requestedSessionId = request.sessionId ?? 'default';
    final sessionId = requestedSessionId == 'assistant'
        ? sessionManager.resolveAssistantSessionForQuery(latestUserQuery)
        : requestedSessionId;
    final priorSessionHistory = sessionManager
        .getOrCreateSession(sessionId)
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
    await templateCatalogRuntime.ensureLoaded(
      forceRefresh: forceRefreshCatalog,
    );
    final previousRunArtifacts = _recoverPreviousRunArtifacts(
      contextScopeHintView,
    );
    final latestAssistant = _latestAssistantMessage(priorSessionHistory);
    final previousSystemContextEnvelope = latestAssistant == null
        ? const SystemContextEnvelope()
        : resolvePersistedAssistantSystemContextEnvelope(latestAssistant);
    final previousUnderstandingResult = latestAssistant == null
        ? const UnderstandingResult()
        : resolvePersistedAssistantUnderstandingResult(latestAssistant);
    final previousTaskGraph = latestAssistant == null
        ? const TaskGraph()
        : resolvePersistedAssistantTaskGraph(latestAssistant);
    final previousPlanView = _parsePreviousPlanView(latestAssistant);
    final effectivePreviousUnderstandingResult =
        previousUnderstandingResult.intents.isNotEmpty
        ? previousUnderstandingResult
        : _typedUnderstandingFromPlanView(previousPlanView);
    final effectivePreviousTaskGraph = previousTaskGraph.tasks.isNotEmpty
        ? previousTaskGraph
        : _taskGraphFromPlanView(
            previousPlanView,
            effectivePreviousUnderstandingResult,
          );
    final previousAnswerSummary = _resolvePreviousAnswerSummary(
      latestAssistant,
    );
    final recentRoundsLimit = resolveRecentDialogueRoundsLimit(
      request.contextScopeHint,
    );
    final olderRecentRoundsLimit = resolveOlderRecentDialogueRoundsLimit(
      request.contextScopeHint,
    );
    final recentDialogueRounds = sessionManager.recentDialogueRounds(
      sessionId,
      limit: recentRoundsLimit,
      olderLimit: olderRecentRoundsLimit,
    );
    final previousProviderReasoningContinuation =
        _resolveProviderReasoningContinuation(latestAssistant);
    final sessionHistoryState = sessionManager.historyStateOf(sessionId);
    final previousUnderstandingSnapshot = _parsePreviousUnderstandingSnapshot(
      latestAssistant,
      previousRunArtifacts,
    );
    final previousAnswerProcessing = _parsePreviousAnswerProcessing(
      latestAssistant,
      previousRunArtifacts,
    );
    final historicalThinkingSnapshot = _parseHistoricalThinkingSnapshot(
      latestAssistant,
      previousRunArtifacts,
    );
    final continuityPolicy = _fallbackContinuityPolicy(
      query: latestUserQuery,
      sessionHistory: priorSessionHistory,
      previousPlanView: previousPlanView,
      previousAnswerSummary: previousAnswerSummary,
      recentRoundsLimit: recentRoundsLimit,
      olderRecentRoundsLimit: olderRecentRoundsLimit,
    );
    final continuityOverrideSlots = contextScopeHintView.mapValue(
      AssistantPipelineStateKeys.continuityOverrideSlots,
    );
    final carryPreviousTurn = _shouldCarryPreviousTurn(continuityPolicy);
    final carriedPreviousRunArtifacts = carryPreviousTurn
        ? previousRunArtifacts
        : null;
    final carriedPreviousAnswerSummary = carryPreviousTurn
        ? previousAnswerSummary
        : '';
    final carriedPreviousUnderstandingSnapshot = carryPreviousTurn
        ? previousUnderstandingSnapshot
        : const RunArtifactsUnderstandingSnapshot();
    final carriedPreviousAnswerProcessing = carryPreviousTurn
        ? previousAnswerProcessing
        : const RunArtifactsAnswerProcessing();
    final carriedHistoricalThinkingSnapshot = carryPreviousTurn
        ? historicalThinkingSnapshot
        : const RunArtifactsHistoricalThinkingSnapshot();
    final carriedProviderReasoningContinuation = carryPreviousTurn
        ? previousProviderReasoningContinuation
        : '';
    if (latestUserQuery.isNotEmpty) {
      sessionManager.appendMessage(
        sessionId: sessionId,
        role: 'user',
        content: latestUserQuery,
      );
    }

    final enableChatRecent = _hasCapability(
      request.capabilityCatalog,
      AssistantCapabilityCatalog.chatRecent,
    );
    final enableChatLongterm = _hasCapability(
      request.capabilityCatalog,
      AssistantCapabilityCatalog.chatLongterm,
    );
    final historySummary =
        enableChatRecent && continuityPolicy.allowHistorySummary
        ? await sessionManager.summarizeRecentAsync(
            sessionId,
            roundsLimit: recentRoundsLimit,
            roundsOlderLimit: olderRecentRoundsLimit,
            summarizer: (transcript) => _summarizeWithLlm(
              transcript: transcript,
              sessionId: sessionId,
              runId: input.runId,
              traceId: input.traceId,
              onTraceEvent: input.onTraceEvent,
            ),
          )
        : '';
    final recall = enableChatLongterm && continuityPolicy.allowLongtermMemory
        ? await memoryRepository.recallByText(query: latestUserQuery, limit: 3)
        : const [];
    final recalledTexts = recall
        .map((item) => item.text.toString())
        .toList(growable: false);
    final contextScopeHint = <String, dynamic>{
      ..._sanitizeForwardedContextScopeHint(
        request.contextScopeHint,
        carryPreviousTurn: carryPreviousTurn,
        previousRunArtifacts: carriedPreviousRunArtifacts,
      ),
      if (continuityOverrideSlots.isNotEmpty)
        'continuityOverrideSlots': continuityOverrideSlots,
      if (_hasStructuredContent(carriedPreviousUnderstandingSnapshot.toJson()))
        'previousUnderstandingSnapshot': carriedPreviousUnderstandingSnapshot
            .toJson(),
      if (_hasStructuredContent(carriedPreviousAnswerProcessing.toJson()))
        'previousAnswerProcessing': carriedPreviousAnswerProcessing.toJson(),
      if (_hasStructuredContent(carriedHistoricalThinkingSnapshot.toJson()))
        'historicalThinkingSnapshot': carriedHistoricalThinkingSnapshot
            .toJson(),
      if (recentDialogueRounds.isNotEmpty)
        'recentDialogueRounds': recentDialogueRounds,
      'recentDialogueRoundsLimit': recentRoundsLimit,
      if (carriedProviderReasoningContinuation.isNotEmpty)
        'providerReasoningContinuation': carriedProviderReasoningContinuation,
    };
    final contextAssembly = contextOrchestrator.assemble(
      query: latestUserQuery,
      historySummary: historySummary,
      recalledTexts: recalledTexts,
      deviceProfile: request.deviceProfile,
      deviceModel: request.deviceModel,
      deviceOs: request.deviceOs,
      gpsLocation: request.gpsLocation,
      contextScopeHint: contextScopeHint,
      continuityPolicy: continuityPolicy,
    );
    final systemContextEnvelope = _resolveSystemContextEnvelope(
      request: request,
      contextScopeHintView: contextScopeHintView,
      contextAssembly: contextAssembly,
      fallback: previousSystemContextEnvelope,
    );
    await toolMetadataRegistry?.ensureLoaded();
    await AssistantContentFilters.ensureLoaded();
    final domainCatalog = await domainRouter.availableDomains(
      forceRefresh: forceRefreshCatalog,
      contextScopeHint: request.contextScopeHint,
    );
    final domainCatalogVersion = await domainRouter.catalogVersion(
      forceRefresh: false,
      contextScopeHint: request.contextScopeHint,
    );
    final fullSkillCatalog = await domainRouter.buildSkillCatalogPrompt(
      contextScopeHint: request.contextScopeHint,
    );
    final allManifests = await domainRouter.availableSkillManifests(
      contextScopeHint: request.contextScopeHint,
    );
    final recallResult = recallCoordinator.recall(
      latestUserQuery,
      allManifests,
    );
    final skillCatalog = recallResult.toPlannerSkillCatalog(
      fullCatalog: fullSkillCatalog,
      fallbackDomainId: domainRouter.fallbackDomainId,
    );

    return PhaseOutput(
      state: input.state.copyWith(
        bootstrapContext: AssistantBootstrapContext(
          sessionId: sessionId,
          latestUserQuery: latestUserQuery,
          historySummary: historySummary,
          systemContextEnvelope: systemContextEnvelope,
          recentDialogueRounds: recentDialogueRounds,
          recentDialogueRoundsLimit: recentRoundsLimit,
          recalledTexts: recalledTexts,
          previousAnswerSummary: carriedPreviousAnswerSummary,
          previousUnderstandingResult: carryPreviousTurn
              ? effectivePreviousUnderstandingResult
              : const UnderstandingResult(),
          previousTaskGraph: carryPreviousTurn
              ? effectivePreviousTaskGraph
              : const TaskGraph(),
          previousUnderstandingSnapshot: carriedPreviousUnderstandingSnapshot,
          previousAnswerProcessing: carriedPreviousAnswerProcessing,
          historicalThinkingSnapshot: carriedHistoricalThinkingSnapshot,
          providerReasoningContinuation: carriedProviderReasoningContinuation,
          sessionHistoryState: sessionHistoryState,
          contextContinuityPolicy: continuityPolicy,
          continuityOverrideSlots: continuityOverrideSlots,
          recallResult: recallResult,
          forceRefreshCatalog: forceRefreshCatalog,
          domainCatalog: domainCatalog,
          domainCatalogVersion: domainCatalogVersion,
          fullSkillCatalog: fullSkillCatalog,
          skillCatalog: skillCatalog,
        ),
        contextAssembly: contextAssembly,
        previousRunArtifacts: carriedPreviousRunArtifacts,
        systemContextEnvelope: systemContextEnvelope,
      ),
    );
  }

  bool _hasCapability(List<String> capabilityCatalog, String capabilityId) {
    return capabilityCatalog.any((item) => item.trim() == capabilityId);
  }

  RunArtifacts? _recoverPreviousRunArtifacts(
    AssistantPipelineContextScopeHintView contextScopeHint,
  ) {
    final raw = contextScopeHint.mapValue(
      AssistantPipelineStateKeys.runArtifacts,
    );
    if (raw.isEmpty) return null;
    try {
      return parseRunArtifacts(raw);
    } catch (_) {
      return null;
    }
  }

  Map<String, dynamic> _sanitizeForwardedContextScopeHint(
    Map<String, dynamic> contextScopeHint, {
    required bool carryPreviousTurn,
    RunArtifacts? previousRunArtifacts,
  }) {
    if (contextScopeHint.isEmpty) {
      return carryPreviousTurn && previousRunArtifacts != null
          ? <String, dynamic>{'runArtifacts': previousRunArtifacts.toJson()}
          : const <String, dynamic>{};
    }
    final sanitized = Map<String, dynamic>.from(contextScopeHint);
    for (final key in const <String>[
      'runArtifacts',
      'previousRunArtifacts',
      'machineEnvelope',
      'displayMarkdown',
      'displayPlainText',
      'journey',
      'uiProcessTimeline',
      'assistantResponse',
      'previousUnderstandingSnapshot',
      'previousAnswerProcessing',
      'historicalThinkingSnapshot',
      'providerReasoningContinuation',
      'continuityOverrideSlots',
    ]) {
      sanitized.remove(key);
    }
    if (!carryPreviousTurn) {
      sanitized.remove('dialogueState');
      sanitized.remove('currentStateId');
      return sanitized;
    }
    if (previousRunArtifacts != null) {
      sanitized['runArtifacts'] = previousRunArtifacts.toJson();
    }
    return sanitized;
  }

  Future<String> _summarizeWithLlm({
    required String transcript,
    required String sessionId,
    required String runId,
    required String traceId,
    AssistantTraceEventSink? onTraceEvent,
  }) async {
    final result = await runtime.run(
      messages: <Map<String, dynamic>>[
        <String, dynamic>{'role': 'user', 'content': transcript},
      ],
      maxIterations: 1,
      goal: '压缩以上对话记录为简洁摘要',
      templateId: 'summarize_session',
      templateVersion: '',
      templateContext: const <String, dynamic>{},
      templateVariables: <String, dynamic>{'sessionTranscript': transcript},
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent == null
          ? null
          : (event) => onTraceEvent(
              event.copyWith(visibility: TraceVisibility.internal),
            ),
    );
    return result.finalText.trim();
  }

  AssistantPlanView? _parsePreviousPlanView(
    Map<String, dynamic>? latestAssistant,
  ) {
    if (latestAssistant == null || latestAssistant.isEmpty) {
      return null;
    }
    final understandingResult = resolvePersistedAssistantUnderstandingResult(
      latestAssistant,
    );
    final taskGraph = resolvePersistedAssistantTaskGraph(latestAssistant);
    return assistantPlanViewFromTypedMainline(
      understandingResult: understandingResult,
      taskGraph: taskGraph,
    );
  }

  RunArtifactsUnderstandingSnapshot _parsePreviousUnderstandingSnapshot(
    Map<String, dynamic>? latestAssistant,
    RunArtifacts? previousRunArtifacts,
  ) {
    final raw = _assistantStructuredMap(
      latestAssistant,
      'understandingSnapshot',
      previousRunArtifacts?.understandingSnapshot.toJson(),
    );
    if (raw.isEmpty) return const RunArtifactsUnderstandingSnapshot();
    try {
      return parseRunArtifactsUnderstandingSnapshotFromMap(raw);
    } catch (_) {
      return const RunArtifactsUnderstandingSnapshot();
    }
  }

  RunArtifactsAnswerProcessing _parsePreviousAnswerProcessing(
    Map<String, dynamic>? latestAssistant,
    RunArtifacts? previousRunArtifacts,
  ) {
    final raw = _assistantStructuredMap(
      latestAssistant,
      'answerProcessing',
      previousRunArtifacts?.answerProcessing.toJson(),
    );
    if (raw.isEmpty) return const RunArtifactsAnswerProcessing();
    try {
      return RunArtifactsAnswerProcessing.fromJson(raw);
    } catch (_) {
      return const RunArtifactsAnswerProcessing();
    }
  }

  RunArtifactsHistoricalThinkingSnapshot _parseHistoricalThinkingSnapshot(
    Map<String, dynamic>? latestAssistant,
    RunArtifacts? previousRunArtifacts,
  ) {
    final raw = _assistantStructuredMap(
      latestAssistant,
      'historicalThinkingSnapshot',
      previousRunArtifacts?.historicalThinkingSnapshot.toJson(),
    );
    if (raw.isEmpty) return const RunArtifactsHistoricalThinkingSnapshot();
    try {
      return RunArtifactsHistoricalThinkingSnapshot.fromJson(raw);
    } catch (_) {
      return const RunArtifactsHistoricalThinkingSnapshot();
    }
  }

  Map<String, dynamic> _assistantStructuredMap(
    Map<String, dynamic>? latestAssistant,
    String key, [
    Map<String, dynamic>? fallback,
  ]) {
    final direct = (latestAssistant?[key] as Map?)?.cast<String, dynamic>();
    if (direct != null && _hasStructuredContent(direct)) return direct;
    final runArtifacts =
        (latestAssistant?['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final nested = (runArtifacts[key] as Map?)?.cast<String, dynamic>();
    if (nested != null && _hasStructuredContent(nested)) return nested;
    if (fallback != null && _hasStructuredContent(fallback)) return fallback;
    return const <String, dynamic>{};
  }

  SystemContextEnvelope _resolveSystemContextEnvelope({
    required AssistantRunRequest request,
    required AssistantPipelineContextScopeHintView contextScopeHintView,
    required ContextAssemblyResult? contextAssembly,
    required SystemContextEnvelope fallback,
  }) {
    final geo = contextAssembly?.availableGeoContext;
    final gps = request.gpsLocation;
    final fallbackTime = fallback.time;
    final fallbackLocation = fallback.location;
    final timezone = _firstNonEmptyString(<Object?>[
      contextScopeHintView.stringValue('timezone'),
      gps['timezone'],
      geo?.timezone,
      fallbackTime.timezone,
      fallbackLocation.timezone,
    ]);
    final locale = _firstNonEmptyString(<Object?>[
      contextScopeHintView.stringValue('locale'),
      gps['locale'],
      fallbackTime.locale,
    ]);
    final referenceNowIso = _firstNonEmptyString(<Object?>[
      contextScopeHintView.stringValue('referenceNowIso'),
      fallbackTime.referenceNowIso,
    ]);
    final countryCode = _firstNonEmptyString(<Object?>[
      geo?.countryCode,
      gps['countryCode'],
      fallbackLocation.countryCode,
    ]);
    final countryName = _firstNonEmptyString(<Object?>[
      geo?.countryLabel,
      gps['countryLabel'],
      fallbackLocation.countryName,
    ]);
    final adminAreaLevel1 = _firstNonEmptyString(<Object?>[
      geo?.regionLabel,
      gps['region'],
      gps['regionLabel'],
      fallbackLocation.adminAreaLevel1,
    ]);
    final adminAreaLevel2 = _firstNonEmptyString(<Object?>[
      geo?.cityLabel,
      gps['city'],
      gps['cityLabel'],
      fallbackLocation.adminAreaLevel2,
    ]);
    final adminAreaLevel3 = _firstNonEmptyString(<Object?>[
      geo?.districtLabel,
      gps['district'],
      gps['districtLabel'],
      fallbackLocation.adminAreaLevel3,
    ]);
    final formattedAddress = <String>[
      countryName,
      adminAreaLevel1,
      adminAreaLevel2,
      adminAreaLevel3,
    ].where((item) => item.trim().isNotEmpty).join(' ').trim();
    final locationGranularity = adminAreaLevel2.isNotEmpty
        ? LocationGranularity.city
        : adminAreaLevel1.isNotEmpty
        ? LocationGranularity.region
        : countryCode.isNotEmpty || countryName.isNotEmpty
        ? LocationGranularity.region
        : LocationGranularity.none;
    return SystemContextEnvelope(
      time: SystemTimeContext(
        referenceNowIso: referenceNowIso,
        timezone: timezone,
        locale: locale,
        granularity:
            referenceNowIso.isNotEmpty ||
                timezone.isNotEmpty ||
                locale.isNotEmpty
            ? ContextGranularity.coarse
            : fallbackTime.granularity,
      ),
      device: DeviceSummary(
        os: request.deviceOs.trim().isNotEmpty
            ? request.deviceOs.trim()
            : fallback.device.os,
        model: request.deviceModel.trim().isNotEmpty
            ? request.deviceModel.trim()
            : fallback.device.model,
        appVersion: fallback.device.appVersion,
        granularity:
            request.deviceOs.trim().isNotEmpty ||
                request.deviceModel.trim().isNotEmpty
            ? ContextGranularity.coarse
            : fallback.device.granularity,
      ),
      permissions: fallback.permissions,
      location: SystemLocationContext(
        countryCode: countryCode,
        countryName: countryName,
        adminAreaLevel1: adminAreaLevel1,
        adminAreaLevel2: adminAreaLevel2,
        adminAreaLevel3: adminAreaLevel3,
        adminAreaLevel4: fallbackLocation.adminAreaLevel4,
        formattedAddress: formattedAddress,
        timezone: timezone,
        granularity: locationGranularity,
      ),
    );
  }

  String _firstNonEmptyString(Iterable<Object?> values) {
    for (final value in values) {
      final text = value?.toString().trim() ?? '';
      if (text.isNotEmpty) {
        return text;
      }
    }
    return '';
  }

  bool _hasStructuredContent(Map<String, dynamic> value) {
    for (final item in value.values) {
      if (item is String && item.trim().isNotEmpty) return true;
      if (item is num && item != 0) return true;
      if (item is bool && item) return true;
      if (item is List && item.isNotEmpty) return true;
      if (item is Map && item.isNotEmpty) return true;
    }
    return false;
  }

  String _resolvePreviousAnswerSummary(Map<String, dynamic>? latestAssistant) {
    if (latestAssistant == null) return '';
    final displayPlainText =
        (latestAssistant['displayPlainText'] as String?)?.trim() ?? '';
    if (displayPlainText.isNotEmpty) return displayPlainText;
    final content = (latestAssistant['content'] as String?)?.trim() ?? '';
    if (content.isNotEmpty) return content;
    return '';
  }

  String _resolveProviderReasoningContinuation(
    Map<String, dynamic>? latestAssistant,
  ) {
    return (latestAssistant?[assistantProviderReasoningContinuationField]
                as String?)
            ?.trim() ??
        '';
  }

  UnderstandingResult _typedUnderstandingFromPlanView(
    AssistantPlanView? previousPlanView,
  ) {
    if (previousPlanView == null || previousPlanView.userGoal.trim().isEmpty) {
      return const UnderstandingResult();
    }
    final intentType = previousPlanView.primarySkill.trim().isNotEmpty
        ? '${previousPlanView.primarySkill.trim()}.retrieve'
        : 'general.retrieve';
    return UnderstandingResult(
      intents: <IntentNode>[
        IntentNode(
          intentId: 'intent_previous',
          intentType: intentType,
          goal: previousPlanView.userGoal.trim(),
          entityRefs: previousPlanView.entityRefs
              .map(
                (item) => IntentEntityRef(
                  entityType: 'entity',
                  canonicalKey: item.trim(),
                  displayText: item.trim(),
                ),
              )
              .where((item) => item.canonicalKey.isNotEmpty)
              .toList(growable: false),
          constraints: previousPlanView.constraints
              .map((item) => IntentConstraint(key: 'constraint', value: item))
              .toList(growable: false),
          requiresEvidence:
              previousPlanView.requiresExternalEvidence ||
              previousPlanView.mustVerifyClaims ||
              previousPlanView.searchPlans.isNotEmpty,
        ),
      ],
      dialogueTransitionDecision: DialogueTransitionDecision(
        nextTurnMode:
            previousPlanView.requiresExternalEvidence ||
                previousPlanView.searchPlans.isNotEmpty
            ? NextTurnMode.continueExecution
            : NextTurnMode.answer,
        needsClarification: previousPlanView.clarificationNeeded,
      ),
    );
  }

  TaskGraph _taskGraphFromPlanView(
    AssistantPlanView? previousPlanView,
    UnderstandingResult understandingResult,
  ) {
    if (understandingResult.intents.isEmpty) {
      return const TaskGraph();
    }
    final primaryIntentId = understandingResult.intents.first.intentId;
    final plans = previousPlanView?.searchPlans ?? const <SearchPlanItem>[];
    if (plans.isEmpty) {
      if (!understandingResult.intents.first.requiresEvidence) {
        return const TaskGraph();
      }
      return TaskGraph(
        tasks: <TaskNode>[
          TaskNode(
            taskId: 'task_previous',
            intentId: primaryIntentId,
            toolName: 'web_search',
            toolArgs: TaskToolArgs(<String, Object?>{
              'query': understandingResult.intents.first.goal,
            }),
          ),
        ],
      );
    }
    return TaskGraph(
      tasks: plans
          .map(
            (plan) => TaskNode(
              taskId: plan.id.trim().isNotEmpty
                  ? plan.id.trim()
                  : 'task_previous',
              intentId: primaryIntentId,
              toolName: 'web_search',
              toolArgs: TaskToolArgs(<String, Object?>{
                'query': plan.query.trim().isNotEmpty
                    ? plan.query.trim()
                    : understandingResult.intents.first.goal,
                'searchPlans': <Map<String, dynamic>>[plan.toJson()],
              }),
            ),
          )
          .toList(growable: false),
    );
  }

  List<String> _recentUserQueries(List<Map<String, dynamic>> sessionHistory) {
    final result = <String>[];
    for (final item in sessionHistory.reversed) {
      if ((item['role'] as String?)?.trim() != 'user') continue;
      final content = (item['content'] as String?)?.trim() ?? '';
      if (content.isEmpty) continue;
      result.add(content);
      if (result.length >= 3) break;
    }
    return result;
  }

  Map<String, dynamic>? _latestAssistantMessage(
    List<Map<String, dynamic>> sessionHistory,
  ) {
    for (final item in sessionHistory.reversed) {
      if ((item['role'] as String?)?.trim() == 'assistant') {
        return item;
      }
    }
    return null;
  }

  ContextContinuityPolicy _fallbackContinuityPolicy({
    required String query,
    required List<Map<String, dynamic>> sessionHistory,
    required AssistantPlanView? previousPlanView,
    required String previousAnswerSummary,
    required int recentRoundsLimit,
    required int olderRecentRoundsLimit,
  }) {
    final seeded = contextOrchestrator.buildContinuityPolicy(
      query: query,
      sessionHistory: sessionHistory,
      recentRoundsLimit: recentRoundsLimit,
      recentOlderRoundsLimit: olderRecentRoundsLimit,
    );
    if (_shouldCarryPreviousTurn(seeded)) return seeded;
    final hasPriorTurn =
        previousPlanView != null ||
        previousAnswerSummary.trim().isNotEmpty ||
        _latestAssistantMessage(sessionHistory) != null;
    final referenceQueries = _recentUserQueries(sessionHistory);
    final implicitFollowUp =
        _looksLikeFollowUpQuery(query) ||
        _looksLikeImplicitSameTopicFollowUp(
          query,
          previousPlanView: previousPlanView,
          referenceQueries: referenceQueries,
        );
    if (!hasPriorTurn || !implicitFollowUp) {
      return seeded;
    }
    return ContextContinuityPolicy(
      queryIntent: seeded.queryIntent,
      problemClass:
          previousPlanView?.problemClass.wireName ?? seeded.problemClass,
      continuityMode: ContextContinuityMode.explicitFollowUp,
      explicitContinuation: true,
      topicOverlap: seeded.topicOverlap > 0 ? seeded.topicOverlap : 0.6,
      allowHistorySummary: true,
      allowLongtermMemory: seeded.allowLongtermMemory,
      allowLocationHints: _shouldCarryLocationHints(previousPlanView),
      referenceQueries: referenceQueries,
      carryForwardFacts: <String>[
        if ((previousPlanView?.userGoal.trim() ?? '').isNotEmpty)
          previousPlanView!.userGoal.trim(),
      ],
      needsRecheckFacts: const <String>[],
      discardedAssumptions: const <String>[],
      mismatchSignal: '',
    );
  }

  bool _looksLikeFollowUpQuery(String query) {
    final compact = query.trim().replaceAll(RegExp(r'\s+'), '');
    if (compact.isEmpty || compact.length > 32) return false;
    final referentialCue = RegExp(
      r'^(那|那如果|如果|如果我|改成|换成|继续|再|还有|这个|那个|这条|那条|上面|上述)',
    ).hasMatch(compact);
    final refinementCue = RegExp(
      r'(明天|后天|只有\d+天|优先|哪条|哪个更|怎么选|这样|这么|这种|这一版)',
    ).hasMatch(compact);
    return referentialCue || refinementCue;
  }

  bool _looksLikeImplicitSameTopicFollowUp(
    String query, {
    required AssistantPlanView? previousPlanView,
    required List<String> referenceQueries,
  }) {
    final normalizedQuery = _normalizeImplicitFollowUpTopic(query);
    if (normalizedQuery.isEmpty || normalizedQuery.length > 12) {
      return false;
    }
    final candidates =
        <String>[
              previousPlanView?.userGoal ?? '',
              ...?previousPlanView?.entityRefs,
              ...referenceQueries,
            ]
            .map(_normalizeImplicitFollowUpTopic)
            .where((item) => item.isNotEmpty)
            .toSet();
    for (final candidate in candidates) {
      if (candidate.contains(normalizedQuery) ||
          normalizedQuery.contains(candidate)) {
        return true;
      }
    }
    return false;
  }

  String _normalizeImplicitFollowUpTopic(String raw) {
    var normalized = raw.trim().toLowerCase();
    if (normalized.isEmpty) return '';
    normalized = normalized
        .replaceAll(RegExp(r'\s+'), '')
        .replaceAll(
          RegExp(
            r'(昨天|今天|明天|后天|周一|周二|周三|周四|周五|周六|周日|最近|请问|一下|一下子|是什么|为什么|怎么|如何|原因|呢|吗|呀|啊|吧)',
          ),
          '',
        )
        .replaceAll(RegExp(r'[^\p{L}\p{N}]', unicode: true), '');
    return normalized;
  }

  bool _shouldCarryLocationHints(AssistantPlanView? previousPlanView) {
    if (previousPlanView == null) {
      return false;
    }
    return previousPlanView.searchPlans.any(
      (plan) =>
          plan.entityRefs.isNotEmpty ||
          plan.timezone.trim().isNotEmpty ||
          plan.timeScope.trim().isNotEmpty,
    );
  }

  bool _shouldCarryPreviousTurn(ContextContinuityPolicy policy) {
    return policy.continuityMode != ContextContinuityMode.unknown &&
        policy.continuityMode != ContextContinuityMode.freshTopic;
  }
}
