import 'dart:convert';

import 'package:quwoquan_app/assistant/context/assembly/context_orchestrator.dart';
import 'package:quwoquan_app/assistant/context/assembly/recall_coordinator.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
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
    final request = input.request is AssistantRunRequest
        ? input.request as AssistantRunRequest
        : AssistantRunRequest.fromJson((input.request as dynamic).toJson());
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
    final continuityDecision = await _resolveContinuityWithModel(
      request: request,
      latestUserQuery: latestUserQuery,
      sessionId: sessionId,
      runId: input.runId,
      traceId: input.traceId,
      sessionHistory: priorSessionHistory,
      previousRunArtifacts: previousRunArtifacts,
      onTraceEvent: input.onTraceEvent,
    );
    final continuityPolicy =
        continuityDecision?.policy ??
        contextOrchestrator.buildContinuityPolicy(
          query: latestUserQuery,
          sessionHistory: priorSessionHistory,
        );
    final continuityOverrideSlots =
        continuityDecision?.overrideSlots ?? const <String, dynamic>{};
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
      ...request.contextScopeHint,
      if (continuityOverrideSlots.isNotEmpty)
        'continuityOverrideSlots': continuityOverrideSlots,
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
          recalledTexts: recalledTexts,
          previousIntentGraph: previousIntentGraph,
          previousAnswerSummary: previousAnswerSummary,
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
        previousRunArtifacts: previousRunArtifacts,
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

  Future<String> _summarizeWithLlm({
    required String transcript,
    required String sessionId,
    required String runId,
    required String traceId,
    void Function(dynamic event)? onTraceEvent,
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

  Future<_ModelContinuityDecision?> _resolveContinuityWithModel({
    required AssistantRunRequest request,
    required String latestUserQuery,
    required String sessionId,
    required String runId,
    required String traceId,
    required List<Map<String, dynamic>> sessionHistory,
    required RunArtifacts? previousRunArtifacts,
    void Function(dynamic event)? onTraceEvent,
  }) async {
    if (latestUserQuery.trim().isEmpty) return null;
    final templateVersion = templateCatalogRuntime.latestVersionFor(
      'planner.continuity_resolution',
      fallback: '',
    );
    final recentQueries = _recentUserQueries(sessionHistory);
    final latestAssistant = _latestAssistantMessage(sessionHistory);
    final previousIntentGraph =
        (latestAssistant?['intentGraph'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final previousSlotState =
        previousRunArtifacts?.slotState.toJson() ??
        ((latestAssistant?['runArtifacts'] as Map?)
                    ?.cast<String, dynamic>()?['slotState']
                as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final previousAnswerSummary =
        (latestAssistant?['displayPlainText'] as String?)?.trim().isNotEmpty ==
            true
        ? (latestAssistant!['displayPlainText'] as String).trim()
        : (latestAssistant?['content'] as String?)?.trim() ?? '';
    final result = await runtime.run(
      messages: <Map<String, dynamic>>[
        <String, dynamic>{'role': 'user', 'content': latestUserQuery},
      ],
      maxIterations: 1,
      goal: '判断当前问题是否需要承接上一轮上下文',
      availableToolNamesOverride: const <String>[],
      templateId: 'planner.continuity_resolution',
      templateVersion: templateVersion,
      templateVariables: <String, dynamic>{
        'currentQuery': latestUserQuery,
        'referenceQueries': jsonEncode(recentQueries),
        'historySummary': _recentAssistantHistorySummary(sessionHistory),
        'previousIntentGraph': jsonEncode(previousIntentGraph),
        'previousSlotState': jsonEncode(previousSlotState),
        'previousAnswerSummary': previousAnswerSummary,
      },
      templateContext: request.contextScopeHint,
      sessionId: sessionId,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent == null
          ? null
          : (event) => onTraceEvent(
              event.copyWith(visibility: TraceVisibility.internal),
            ),
      callOptions: const LlmCallOptions(
        temperature: 0.1,
        maxTokens: 700,
        forceJsonObject: true,
        timeoutSeconds: 15,
      ),
    );
    final parsed =
        LlmResponseParser.parse(result.finalText).json ?? <String, dynamic>{};
    if (parsed.isEmpty) return null;
    final continuityMode = parseContextContinuityMode(
      (parsed['continuityMode'] as String?)?.trim() ?? '',
    );
    if (continuityMode == ContextContinuityMode.unknown) {
      return null;
    }
    final policy = ContextContinuityPolicy(
      queryIntent: (parsed['queryIntent'] as String?)?.trim() ?? '',
      problemClass: (parsed['problemClass'] as String?)?.trim() ?? '',
      continuityMode: continuityMode,
      explicitContinuation: parsed['explicitContinuation'] == true,
      topicOverlap: ((parsed['topicOverlap'] as num?) ?? 0).toDouble(),
      allowHistorySummary: parsed['allowHistorySummary'] == true,
      allowLongtermMemory: parsed['allowLongtermMemory'] == true,
      allowLocationHints: parsed['allowLocationHints'] == true,
      referenceQueries:
          (parsed['referenceQueries'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          recentQueries,
    );
    return _ModelContinuityDecision(
      policy: policy,
      overrideSlots:
          (parsed['overrideSlots'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
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

  String _resolvePreviousAnswerSummary(Map<String, dynamic>? latestAssistant) {
    if (latestAssistant == null) return '';
    final displayPlainText =
        (latestAssistant['displayPlainText'] as String?)?.trim() ?? '';
    if (displayPlainText.isNotEmpty) return displayPlainText;
    final content = (latestAssistant['content'] as String?)?.trim() ?? '';
    if (content.isNotEmpty) return content;
    return '';
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

  String _recentAssistantHistorySummary(
    List<Map<String, dynamic>> sessionHistory,
  ) {
    final assistant = _latestAssistantMessage(sessionHistory);
    if (assistant == null) return '';
    final displayPlainText =
        (assistant['displayPlainText'] as String?)?.trim() ?? '';
    if (displayPlainText.isNotEmpty) return displayPlainText;
    return (assistant['content'] as String?)?.trim() ?? '';
  }
}

class _ModelContinuityDecision {
  const _ModelContinuityDecision({
    required this.policy,
    required this.overrideSlots,
  });

  final ContextContinuityPolicy policy;
  final Map<String, dynamic> overrideSlots;
}
