import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:quwoquan_app/assistant/context/assembly/recall_coordinator.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
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
    final forceRefreshCatalog =
        request.contextScopeHint['forceRefreshCatalog'] == true;
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
      request.contextScopeHint,
    );
    final latestAssistant = _latestAssistantMessage(priorSessionHistory);
    final previousIntentGraph = _parsePreviousIntentGraph(latestAssistant);
    final previousAnswerSummary = _resolvePreviousAnswerSummary(
      latestAssistant,
    );
    final recentRoundsLimit = resolveRecentDialogueRoundsLimit(
      request.contextScopeHint,
    );
    final recentDialogueRounds = sessionManager.recentDialogueRounds(
      sessionId,
      limit: recentRoundsLimit,
    );
    final previousProviderReasoningContinuation =
        _resolveProviderReasoningContinuation(latestAssistant);
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
      previousIntentGraph: previousIntentGraph,
      previousAnswerSummary: previousAnswerSummary,
    );
    final continuityOverrideSlots =
        (request.contextScopeHint['continuityOverrideSlots'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final carryPreviousTurn = _shouldCarryPreviousTurn(continuityPolicy);
    final carriedPreviousRunArtifacts = carryPreviousTurn
        ? previousRunArtifacts
        : null;
    final carriedPreviousIntentGraph = carryPreviousTurn
        ? previousIntentGraph
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
          recentDialogueRounds: recentDialogueRounds,
          recentDialogueRoundsLimit: recentRoundsLimit,
          recalledTexts: recalledTexts,
          previousIntentGraph: carriedPreviousIntentGraph,
          previousAnswerSummary: carriedPreviousAnswerSummary,
          previousUnderstandingSnapshot: carriedPreviousUnderstandingSnapshot,
          previousAnswerProcessing: carriedPreviousAnswerProcessing,
          historicalThinkingSnapshot: carriedHistoricalThinkingSnapshot,
          providerReasoningContinuation: carriedProviderReasoningContinuation,
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
      ),
    );
  }

  bool _hasCapability(List<String> capabilityCatalog, String capabilityId) {
    return capabilityCatalog.any((item) => item.trim() == capabilityId);
  }

  RunArtifacts? _recoverPreviousRunArtifacts(
    Map<String, dynamic> contextScopeHint,
  ) {
    final raw = (contextScopeHint['runArtifacts'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) return null;
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
      goal: '压缩以上对话历史为简洁摘要',
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

  IntentGraph? _parsePreviousIntentGraph(
    Map<String, dynamic>? latestAssistant,
  ) {
    final raw = (latestAssistant?['intentGraph'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) return null;
    try {
      return IntentGraph.fromJson(raw);
    } catch (_) {
      return null;
    }
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
    required IntentGraph? previousIntentGraph,
    required String previousAnswerSummary,
  }) {
    final seeded = contextOrchestrator.buildContinuityPolicy(
      query: query,
      sessionHistory: sessionHistory,
    );
    if (_shouldCarryPreviousTurn(seeded)) return seeded;
    final hasPriorTurn =
        previousIntentGraph != null ||
        previousAnswerSummary.trim().isNotEmpty ||
        _latestAssistantMessage(sessionHistory) != null;
    final referenceQueries = _recentUserQueries(sessionHistory);
    final implicitFollowUp =
        _looksLikeFollowUpQuery(query) ||
        _looksLikeImplicitSameTopicFollowUp(
          query,
          previousIntentGraph: previousIntentGraph,
          referenceQueries: referenceQueries,
        );
    if (!hasPriorTurn || !implicitFollowUp) {
      return seeded;
    }
    return ContextContinuityPolicy(
      queryIntent: seeded.queryIntent,
      problemClass:
          previousIntentGraph?.problemClass.wireName ?? seeded.problemClass,
      continuityMode: ContextContinuityMode.explicitFollowUp,
      explicitContinuation: true,
      topicOverlap: seeded.topicOverlap > 0 ? seeded.topicOverlap : 0.6,
      allowHistorySummary: true,
      allowLongtermMemory: seeded.allowLongtermMemory,
      allowLocationHints: _shouldCarryLocationHints(
        previousIntentGraph,
        previousAnswerSummary,
      ),
      referenceQueries: referenceQueries,
      carryForwardFacts: <String>[
        if ((previousIntentGraph?.userGoal.trim() ?? '').isNotEmpty)
          previousIntentGraph!.userGoal.trim(),
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
    final explicitAnchor = RegExp(
      r'([A-Za-z]{3,}|[\u4e00-\u9fff]{2,}(?:市|区|县|镇|乡|村|街道|公园|景区|机场|车站|大厦|广场|口岸|山|湖|河|沟|湾|岛|草原))',
    ).hasMatch(compact);
    return (referentialCue || refinementCue) && !explicitAnchor;
  }

  bool _looksLikeImplicitSameTopicFollowUp(
    String query, {
    required IntentGraph? previousIntentGraph,
    required List<String> referenceQueries,
  }) {
    final normalizedQuery = _normalizeImplicitFollowUpTopic(query);
    if (normalizedQuery.isEmpty || normalizedQuery.length > 12) {
      return false;
    }
    final candidates = <String>[
      previousIntentGraph?.userGoal ?? '',
      previousIntentGraph?.targetObject ?? '',
      ...?previousIntentGraph?.entityAnchors,
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
        .replaceAll(RegExp(r'[Aa]股'), '股票')
        .replaceAll('中国股市', '股票')
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

  bool _shouldCarryLocationHints(
    IntentGraph? previousIntentGraph,
    String previousAnswerSummary,
  ) {
    final contextSlots =
        previousIntentGraph?.contextSlots ?? const <String, dynamic>{};
    for (final key in const <String>[
      'city',
      'destination',
      'location',
      'place',
    ]) {
      if (contextSlots[key] != null) return true;
    }
    if (previousIntentGraph?.entityAnchors.isNotEmpty == true) {
      return RegExp(
        r'(市|区|县|镇|乡|村|街道|公园|景区|机场|车站|大厦|广场|口岸|山|湖|河|沟|湾|岛|草原)',
      ).hasMatch(previousAnswerSummary);
    }
    return false;
  }

  bool _shouldCarryPreviousTurn(ContextContinuityPolicy policy) {
    return policy.continuityMode != ContextContinuityMode.unknown &&
        policy.continuityMode != ContextContinuityMode.freshTopic;
  }
}
