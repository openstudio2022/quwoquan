// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — finalize 消费持久化/响应 Map；与 RunArtifacts 对齐。

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_run_structured_bundle.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_session_history_state.dart';
import 'package:quwoquan_app/assistant/contracts/preference_fact.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/skill_synthesis_contract.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/debug/agent_loop_dev_logger.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_perf_probe.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';

typedef ObservabilityPayloadBuilderFn =
    Map<String, dynamic> Function({
      required AssistantRunResponse response,
      required AssistantRunRequest request,
    });

class FinalizeRunner {
  const FinalizeRunner({
    required this.sessionManager,
    required this.memoryRepository,
    required this.buildObservabilityPayload,
  });

  final AssistantSessionManager sessionManager;
  final AssistantMemoryRepository memoryRepository;
  final ObservabilityPayloadBuilderFn buildObservabilityPayload;

  Future<AssistantRunResponse> finalize(
    AssistantRunRequest request, {
    required ExecutionPhaseSnapshot executionSnapshot,
    required AssistantRunResponse response,
  }) async {
    final successSnapshot = executionSnapshot is ExecutionPhaseSuccess
        ? executionSnapshot
        : null;
    final sessionId =
        successSnapshot?.sessionId ?? (request.sessionId ?? 'default');
    final latestUserQuery = successSnapshot?.latestUserQuery.trim() ?? '';
    final runStartAt = successSnapshot?.runStartAt;
    final runId =
        response.runId ??
        successSnapshot?.runId ??
        '${DateTime.now().millisecondsSinceEpoch}_${request.sessionId ?? 'default'}';
    final traceId =
        response.traceId ??
        successSnapshot?.traceId ??
        request.traceId ??
        runId;
    final completedArtifact = response.runArtifacts;
    final structuredResponse = response.structuredResponse;
    final structuredBundle =
        AssistantRunStructuredBundle.fromStructuredResponseRoot(
          structuredResponse,
        );
    final skillSynthesisSection =
        (structuredResponse['skillSynthesis'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final skillSynthesisInput = skillSynthesisSection['input'] is Map
        ? SkillSynthesisInput.fromJson(
            (skillSynthesisSection['input'] as Map).cast<String, dynamic>(),
          )
        : null;
    final skillSynthesisOutput = skillSynthesisSection['output'] is Map
        ? SkillSynthesisOutput.fromJson(
            (skillSynthesisSection['output'] as Map).cast<String, dynamic>(),
          )
        : null;
    final structuredRunArtifacts =
        structuredBundle.runArtifacts?.toJson() ?? const <String, dynamic>{};
    final canonicalDisplayState = resolveAssistantDisplayStateFromRunResponse(
      response,
    );
    final canonicalProcessTimeline =
        resolveAssistantProcessTimelineFromRunResponse(response);
    final persistedJourney = resolveAssistantJourneyFromRunResponse(response);
    final understandingSnapshot = _resolvedUnderstandingSnapshotMap(
      structuredResponse[assistantUnderstandingSnapshotField],
      _resolvedUnderstandingSnapshotMap(
        structuredRunArtifacts[assistantUnderstandingSnapshotField],
        completedArtifact?.understandingSnapshot.toJson() ??
            const <String, dynamic>{},
      ),
    );
    final answerProcessing = _resolvedStructuredMap(
      structuredResponse[assistantAnswerProcessingField],
      _resolvedStructuredMap(
        structuredRunArtifacts[assistantAnswerProcessingField],
        completedArtifact?.answerProcessing.toJson() ??
            const <String, dynamic>{},
      ),
    );
    final historicalThinkingSnapshot = _resolvedStructuredMap(
      structuredResponse[assistantHistoricalThinkingSnapshotField],
      _resolvedStructuredMap(
        structuredRunArtifacts[assistantHistoricalThinkingSnapshotField],
        completedArtifact?.historicalThinkingSnapshot.toJson() ??
            const <String, dynamic>{},
      ),
    );
    final retrievalProcessing = _resolvedStructuredMap(
      structuredResponse[assistantRetrievalProcessingField],
      _resolvedStructuredMap(
        structuredRunArtifacts[assistantRetrievalProcessingField],
        completedArtifact?.retrievalProcessing.toJson() ??
            const <String, dynamic>{},
      ),
    );
    final systemContextEnvelope = _resolvedStructuredMap(
      structuredResponse[assistantSystemContextEnvelopeField],
      const <String, dynamic>{},
    );
    final understandingResult = _resolvedStructuredMap(
      structuredResponse[assistantUnderstandingResultField],
      const <String, dynamic>{},
    );
    final taskGraph = _resolvedStructuredMap(
      structuredResponse[assistantTaskGraphField],
      const <String, dynamic>{},
    );
    final orchestratorState = _resolvedStructuredMap(
      structuredResponse[assistantOrchestratorStateField],
      const <String, dynamic>{},
    );
    final turnSynthesisState = _resolvedStructuredMap(
      structuredResponse[assistantTurnSynthesisStateField],
      const <String, dynamic>{},
    );
    final displayMarkdown = canonicalDisplayState.answer.blocks.isNotEmpty
        ? renderAnswerBlocksToMarkdown(
            canonicalDisplayState.answer.blocks,
          ).trim()
        : _resolvedStructuredText(
            structuredResponse[assistantDisplayMarkdownField],
            _resolvedStructuredText(
              structuredRunArtifacts[assistantDisplayMarkdownField],
              _resolvedStructuredText(
                structuredResponse['userMarkdown'],
                completedArtifact?.displayMarkdown ?? response.finalText,
              ),
            ),
          );
    final displayPlainText = canonicalDisplayState.answer.blocks.isNotEmpty
        ? renderAnswerBlocksToPlainText(
            canonicalDisplayState.answer.blocks,
          ).trim()
        : _resolvedStructuredText(
            structuredResponse[assistantDisplayPlainTextField],
            _resolvedStructuredText(
              structuredRunArtifacts[assistantDisplayPlainTextField],
              _resolvedStructuredText(
                structuredResponse['result'] is Map
                    ? ((structuredResponse['result'] as Map)['text'] as String?)
                    : null,
                completedArtifact?.displayPlainText ?? displayMarkdown,
              ),
            ),
          );
    final displayTextForSession = displayMarkdown.isNotEmpty
        ? displayMarkdown
        : displayPlainText;
    final persistedTurnFields = buildPersistedAssistantTurnFields(
      journey: persistedJourney,
      displayMarkdown: displayMarkdown,
      displayPlainText: displayPlainText,
      followupPrompt: response.followupPrompt,
      actionHints: response.actionHints,
      elapsedMs: runStartAt == null
          ? 0
          : DateTime.now().difference(runStartAt).inMilliseconds,
      displayState: canonicalDisplayState.toJson(),
      processTimeline: canonicalProcessTimeline,
      understandingSnapshot: understandingSnapshot,
      answerProcessing: answerProcessing,
      historicalThinkingSnapshot: historicalThinkingSnapshot,
      retrievalProcessing: retrievalProcessing,
      systemContextEnvelope: systemContextEnvelope,
      understandingResult: understandingResult,
      taskGraph: taskGraph,
      orchestratorState: orchestratorState,
      turnSynthesisState: turnSynthesisState,
      providerReasoningContinuation:
          (structuredResponse[assistantProviderReasoningContinuationField]
                  as String?)
              ?.trim() ??
          '',
    );
    sessionManager.updateSessionTopicSummary(
      sessionId: sessionId,
      latestUserQuery: latestUserQuery,
      latestAssistantReply: displayPlainText.isNotEmpty
          ? displayPlainText
          : displayTextForSession,
    );
    if (displayPlainText.isNotEmpty) {
      await memoryRepository.rememberText(
        id: '${sessionId}_${DateTime.now().millisecondsSinceEpoch}',
        text: displayPlainText,
        metadata: <String, dynamic>{
          'sessionId': sessionId,
          'userId': request.userId ?? '',
          'deviceProfile': request.deviceProfile,
          'deviceModel': request.deviceModel,
          'deviceOs': request.deviceOs,
        },
      );
    }
    if (displayTextForSession.isNotEmpty ||
        !persistedJourney.isEmpty ||
        canonicalProcessTimeline.isNotEmpty ||
        hasAssistantDisplayState(canonicalDisplayState)) {
      sessionManager.appendMessage(
        sessionId: sessionId,
        role: 'assistant',
        content: displayTextForSession,
        metadata: <String, dynamic>{
          ...persistedTurnFields,
          'runArtifacts': _buildPersistedRunArtifactsPayload(
            response: response,
            journey: persistedJourney,
            displayMarkdown: displayMarkdown,
            displayPlainText: displayPlainText,
            displayState: canonicalDisplayState,
            processTimeline: canonicalProcessTimeline,
            understandingSnapshot: understandingSnapshot,
            answerProcessing: answerProcessing,
            historicalThinkingSnapshot: historicalThinkingSnapshot,
            retrievalProcessing: retrievalProcessing,
          ),
          'uiUsageStats':
              (structuredResponse['uiUsageStats'] as Map?) ??
              const <String, dynamic>{},
          if (systemContextEnvelope.isNotEmpty)
            assistantSystemContextEnvelopeField: systemContextEnvelope,
          if (understandingResult.isNotEmpty)
            assistantUnderstandingResultField: understandingResult,
          if (taskGraph.isNotEmpty) assistantTaskGraphField: taskGraph,
          if (orchestratorState.isNotEmpty)
            assistantOrchestratorStateField: orchestratorState,
          if (turnSynthesisState.isNotEmpty)
            assistantTurnSynthesisStateField: turnSynthesisState,
        },
      );
    }
    final historyState = _buildHistoryState(
      sessionId: sessionId,
      currentSessionSummary: structuredResponse['sessionSummary'] is String
          ? (structuredResponse['sessionSummary'] as String)
          : '',
      skillSynthesisInput: skillSynthesisInput,
      skillSynthesisOutput: skillSynthesisOutput,
      structuredResponse: structuredResponse,
      sessionManager: sessionManager,
    );
    if (!historyState.isEmpty) {
      final mergedHistoryState = sessionManager
          .historyStateOf(sessionId)
          .mergeWith(historyState);
      sessionManager.updateSessionHistoryState(
        sessionId: sessionId,
        historyState: mergedHistoryState,
      );
    }
    await sessionManager.save();
    await _persistLearningTags(
      response: response,
      sessionId: sessionId,
      userId: request.userId ?? '',
    );
    await AssistantAgentLoopDevLogger.instance.writeRun(
      request: request,
      response: response,
      sessionId: sessionId,
      runId: runId,
    );
    await _safeWriteLogEvent(
      logType: AppLogType.agentRun,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      ),
      payload: buildObservabilityPayload(response: response, request: request),
      summaryPayload: <String, dynamic>{
        'kind': 'agent_run',
        'runId': runId,
        'traceId': traceId,
        'degraded': response.degraded,
      },
      hasError: response.degraded,
    );
    final runLatencyMs = runStartAt == null
        ? 0
        : DateTime.now().difference(runStartAt).inMilliseconds;
    await _safeWriteLogEvent(
      logType: AppLogType.perf,
      level: AppLogLevel.info,
      context: AppLogContext(
        sessionId: sessionId,
        runId: runId,
        traceId: traceId,
      ),
      payload: AppPerfProbe.snapshot(
        event: 'operation',
        route: '/assistant/run',
        operation: 'agent_run_end',
        latencyMs: runLatencyMs,
      ),
      summaryPayload: <String, dynamic>{
        'event': 'operation',
        'operation': 'agent_run_end',
        'latencyMs': runLatencyMs,
      },
    );
    return response;
  }

  Map<String, dynamic> _buildPersistedRunArtifactsPayload({
    required AssistantRunResponse response,
    required AssistantJourney journey,
    required String displayMarkdown,
    required String displayPlainText,
    required AssistantDisplayState displayState,
    required List<ProcessTimelineFrame> processTimeline,
    required Map<String, dynamic> understandingSnapshot,
    required Map<String, dynamic> answerProcessing,
    required Map<String, dynamic> historicalThinkingSnapshot,
    required Map<String, dynamic> retrievalProcessing,
  }) {
    final runArtifacts = response.runArtifacts?.toJson() ?? <String, dynamic>{};
    return <String, dynamic>{
      ...runArtifacts,
      assistantDisplayMarkdownField: displayMarkdown,
      assistantDisplayPlainTextField: displayPlainText,
      if (!journey.isEmpty) assistantJourneyField: journey.toJson(),
      if (processTimeline.isNotEmpty)
        assistantProcessTimelineField: processTimeline
            .map((item) => item.toJson())
            .toList(growable: false),
      if (understandingSnapshot.isNotEmpty)
        assistantUnderstandingSnapshotField: understandingSnapshot,
      if (answerProcessing.isNotEmpty)
        assistantAnswerProcessingField: answerProcessing,
      if (historicalThinkingSnapshot.isNotEmpty)
        assistantHistoricalThinkingSnapshotField: historicalThinkingSnapshot,
      if (retrievalProcessing.isNotEmpty)
        assistantRetrievalProcessingField: retrievalProcessing,
      if (hasAssistantDisplayState(displayState))
        assistantDisplayStateField: displayState.toJson(),
    };
  }

  Map<String, dynamic> _resolvedStructuredMap(
    Object? raw,
    Map<String, dynamic> fallback,
  ) {
    if (raw is Map) {
      final direct = raw.cast<String, dynamic>();
      if (direct.isNotEmpty) {
        return direct;
      }
    }
    return fallback;
  }

  Map<String, dynamic> _resolvedUnderstandingSnapshotMap(
    Object? raw,
    Map<String, dynamic> fallback,
  ) {
    if (raw is Map) {
      final normalized = normalizeRunArtifactsUnderstandingSnapshotJson(
        raw.cast<String, dynamic>(),
      );
      if (_hasUnderstandingSnapshotContent(normalized)) {
        return normalized;
      }
    }
    return fallback;
  }

  bool _hasUnderstandingSnapshotContent(Map<String, dynamic> raw) {
    if (raw.isEmpty) return false;
    final parsed = RunArtifactsUnderstandingSnapshot.fromJson(raw);
    return parsed.intentSummary.trim().isNotEmpty ||
        parsed.userFacingSummary.trim().isNotEmpty ||
        parsed.retrievalDesignNarrative.trim().isNotEmpty ||
        parsed.concernPoints.isNotEmpty ||
        parsed.resolutionItems.isNotEmpty ||
        parsed.assumptions.isNotEmpty ||
        parsed.mismatchSignal.trim().isNotEmpty ||
        parsed.carryForwardFacts.isNotEmpty ||
        parsed.discardedAssumptions.isNotEmpty;
  }

  String _resolvedStructuredText(Object? raw, String fallback) {
    if (raw is String && raw.trim().isNotEmpty) {
      return raw.trim();
    }
    return fallback.trim();
  }

  Future<void> _persistLearningTags({
    required AssistantRunResponse response,
    required String sessionId,
    required String userId,
  }) async {
    try {
      final structured = response.structuredResponse;
      final learningTrack =
          (structured['learningTrack'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final tags =
          (learningTrack['profileTagDelta'] as List?)
              ?.whereType<Map>()
              .map((t) => t.cast<String, dynamic>())
              .where((t) => (t['tag'] ?? '').toString().isNotEmpty)
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      if (tags.isEmpty) return;

      final tagSummary = tags
          .map((t) => '${t['tag']}: ${t['value'] ?? t['confidence'] ?? ''}')
          .join('; ');
      await memoryRepository.rememberText(
        id: 'learning_${sessionId}_${DateTime.now().millisecondsSinceEpoch}',
        text: '用户画像标签: $tagSummary',
        metadata: <String, dynamic>{
          'type': 'learning_tag',
          'sessionId': sessionId,
          'userId': userId,
          'tags': tags,
          'timestamp': DateTime.now().toIso8601String(),
        },
      );
    } catch (_) {
      // Non-critical: silently ignore persistence failures.
    }
  }

  AssistantSessionHistoryState _buildHistoryState({
    required String sessionId,
    required String currentSessionSummary,
    required SkillSynthesisInput? skillSynthesisInput,
    required SkillSynthesisOutput? skillSynthesisOutput,
    required Map<String, dynamic> structuredResponse,
    required AssistantSessionManager sessionManager,
  }) {
    final sessionPreferences = <PreferenceFact>[
      ..._preferenceFactsFromRaw(structuredResponse['sessionPreferenceFacts']),
      ..._preferenceFactsFromRaw(structuredResponse['longTermPreferenceFacts']),
    ];
    final effectivePreferences = sessionPreferences.isNotEmpty
        ? sessionPreferences
        : <PreferenceFact>[
            ...sessionManager.sessionPreferenceFactsOf(sessionId),
            ...sessionManager.longTermPreferenceFactsOf(sessionId),
          ];
    if (skillSynthesisInput == null || skillSynthesisOutput == null) {
      return AssistantSessionHistoryState(
        sessionSummary: currentSessionSummary.trim(),
        userPreferences: effectivePreferences,
      );
    }
    return AssistantSessionHistoryState.fromSkillSynthesis(
      input: skillSynthesisInput,
      output: skillSynthesisOutput,
      userPreferences: effectivePreferences,
    );
  }

  List<PreferenceFact> _preferenceFactsFromRaw(Object? raw) {
    final items = raw is List ? raw : const <dynamic>[];
    return items
        .whereType<Map>()
        .map((item) => PreferenceFact.fromJson(item.cast<String, dynamic>()))
        .where(
          (fact) => fact.key.trim().isNotEmpty && fact.value.trim().isNotEmpty,
        )
        .toList(growable: false);
  }

  Future<void> _safeWriteLogEvent({
    required AppLogType logType,
    required AppLogLevel level,
    required AppLogContext context,
    required dynamic payload,
    required Map<String, dynamic> summaryPayload,
    bool hasError = false,
  }) async {
    try {
      await AppLogService.instance.writeEvent(
        logType: logType,
        level: level,
        context: context,
        payload: payload,
        summaryPayload: summaryPayload,
        hasError: hasError,
      );
    } catch (error) {
      if (kDebugMode) {
        debugPrint('[FinalizeRunner] log write skipped: $error');
      }
    }
  }
}
