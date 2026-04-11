// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — 会话持久化消息 Map；子树用 codegen/Codec/assistantJsonAsStringKeyedMap 收窄。

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';

const String assistantJourneyField = 'journey';
const String assistantProcessTimelineField = 'processTimeline';
const String assistantUiProcessTimelineField = 'uiProcessTimeline';
const String assistantDisplayMarkdownField = 'displayMarkdown';
const String assistantDisplayPlainTextField = 'displayPlainText';
const String assistantFollowupPromptField = 'followupPrompt';
const String assistantActionHintsField = 'actionHints';
const String assistantUnderstandingSnapshotField = 'understandingSnapshot';
const String assistantAnswerProcessingField = 'answerProcessing';
const String assistantHistoricalThinkingSnapshotField =
    'historicalThinkingSnapshot';
const String assistantRetrievalProcessingField = 'retrievalProcessing';
const String assistantProviderReasoningContinuationField =
    'providerReasoningContinuation';
const String assistantTurnSchemaVersionField = 'assistantTurnSchemaVersion';
const String assistantHistoryStorageVersion = 'assistant_history_v1';
const String assistantTurnSchemaVersion = 'assistant_turn_v1';

/// `jsonDecode` 根或嵌套 JSON 对象 → `Map<String, dynamic>`（会话持久化加载等）。
Map<String, dynamic>? assistantJsonAsStringKeyedMap(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return value.map((k, v) => MapEntry(k.toString(), v));
  }
  return null;
}

const List<JourneyStageId> assistantPrimaryJourneyStages = <JourneyStageId>[
  JourneyStageId.analyze,
  JourneyStageId.search,
  JourneyStageId.answer,
];

AssistantJourney resolvePersistedAssistantJourney(
  Map<String, dynamic> message,
) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const AssistantJourney();
  }
  final raw = (message[assistantJourneyField] as Map?)?.cast<String, dynamic>();
  if (raw != null && raw.isNotEmpty) {
    final parsed = AssistantJourney.fromJson(raw);
    return parsed.isEmpty ? const AssistantJourney() : parsed;
  }
  final runArtifacts = (message['runArtifacts'] as Map?)
      ?.cast<String, dynamic>();
  final nested = (runArtifacts?[assistantJourneyField] as Map?)
      ?.cast<String, dynamic>();
  if (nested != null && nested.isNotEmpty) {
    final parsed = AssistantJourney.fromJson(nested);
    return parsed.isEmpty ? const AssistantJourney() : parsed;
  }
  return const AssistantJourney();
}

/// 只使用当前持久化 schema 产出的规范化 UI 时间轴。
AssistantJourney resolvePersistedAssistantJourneyForDisplay(
  Map<String, dynamic> message,
) {
  final timeline = resolvePersistedAssistantTimeline(message);
  if (!timeline.isEmpty) {
    return timeline;
  }
  return const AssistantJourney();
}

AssistantJourney resolvePersistedAssistantTimeline(
  Map<String, dynamic> message,
) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const AssistantJourney();
  }
  final raw = (message[assistantUiProcessTimelineField] as Map?)
      ?.cast<String, dynamic>();
  if (raw == null || raw.isEmpty) {
    return const AssistantJourney();
  }
  final parsed = AssistantJourney.fromJson(raw);
  if (parsed.isEmpty || !_hasCanonicalPrimaryTimeline(parsed)) {
    return const AssistantJourney();
  }
  return parsed;
}

List<ProcessTimelineFrame> resolvePersistedAssistantProcessTimeline(
  Map<String, dynamic> message,
) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const <ProcessTimelineFrame>[];
  }
  final direct = _parseProcessTimelineList(
    message[assistantProcessTimelineField],
  );
  if (hasStructuredProcessTimeline(direct)) {
    return direct;
  }
  final runArtifacts = (message['runArtifacts'] as Map?)
      ?.cast<String, dynamic>();
  final nested = _parseProcessTimelineList(
    runArtifacts?[assistantProcessTimelineField],
  );
  if (hasStructuredProcessTimeline(nested)) {
    return nested;
  }
  return const <ProcessTimelineFrame>[];
}

List<ProcessTimelineFrame> resolvePersistedAssistantVisibleProcessTimeline(
  Map<String, dynamic> message,
) {
  return buildVisibleProcessTimeline(
    resolvePersistedAssistantProcessTimeline(message),
  );
}

AssistantDisplayState resolvePersistedAssistantDisplayState(
  Map<String, dynamic> message,
) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const AssistantDisplayState();
  }
  final direct = parseAssistantDisplayStateFromMap(
    (message[assistantDisplayStateField] as Map?)?.cast<String, dynamic>(),
  );
  if (hasAssistantDisplayState(direct)) {
    return direct;
  }
  final runArtifacts = (message['runArtifacts'] as Map?)
      ?.cast<String, dynamic>();
  if (runArtifacts == null || runArtifacts.isEmpty) {
    return const AssistantDisplayState();
  }
  try {
    return resolveAssistantDisplayStateFromRunArtifacts(
      RunArtifacts.fromJson(runArtifacts),
    );
  } catch (_) {
    return const AssistantDisplayState();
  }
}

RunArtifactsUnderstandingSnapshot resolvePersistedAssistantUnderstandingSnapshot(
  Map<String, dynamic> message,
) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const RunArtifactsUnderstandingSnapshot();
  }
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantUnderstandingSnapshotField,
  );
  if (raw.isEmpty) {
    return const RunArtifactsUnderstandingSnapshot();
  }
  return parseRunArtifactsUnderstandingSnapshotFromMap(raw);
}

RunArtifactsAnswerProcessing resolvePersistedAssistantAnswerProcessing(
  Map<String, dynamic> message,
) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const RunArtifactsAnswerProcessing();
  }
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantAnswerProcessingField,
  );
  if (raw.isEmpty) {
    return const RunArtifactsAnswerProcessing();
  }
  return RunArtifactsAnswerProcessing.fromJson(raw);
}

RunArtifactsHistoricalThinkingSnapshot
resolvePersistedAssistantHistoricalThinkingSnapshot(
  Map<String, dynamic> message,
) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const RunArtifactsHistoricalThinkingSnapshot();
  }
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantHistoricalThinkingSnapshotField,
  );
  if (raw.isEmpty) {
    return const RunArtifactsHistoricalThinkingSnapshot();
  }
  return RunArtifactsHistoricalThinkingSnapshot.fromJson(raw);
}

RetrievalProcessingSnapshot resolvePersistedAssistantRetrievalProcessing(
  Map<String, dynamic> message,
) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const RetrievalProcessingSnapshot();
  }
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantRetrievalProcessingField,
  );
  if (raw.isEmpty) {
    return const RetrievalProcessingSnapshot();
  }
  return RetrievalProcessingSnapshot.fromJson(raw);
}

IntentGraph? resolvePersistedAssistantIntentGraph(Map<String, dynamic> message) {
  final direct = (message['intentGraph'] as Map?)?.cast<String, dynamic>();
  if (direct != null && direct.isNotEmpty) {
    try {
      return IntentGraph.fromJson(direct);
    } catch (_) {}
  }
  final runArtifacts = (message['runArtifacts'] as Map?)?.cast<String, dynamic>();
  final nested = (runArtifacts?['intentGraph'] as Map?)?.cast<String, dynamic>();
  if (nested != null && nested.isNotEmpty) {
    try {
      return IntentGraph.fromJson(nested);
    } catch (_) {}
  }
  return null;
}

AssistantJourney resolveAssistantJourneyFromRunResponse(
  AssistantRunResponse response,
) {
  final runArtifactsJourney = response.runArtifacts?.journey;
  if (runArtifactsJourney != null && !runArtifactsJourney.isEmpty) {
    return runArtifactsJourney;
  }
  final topLevel = response.structuredResponse[assistantJourneyField];
  if (topLevel is Map) {
    final parsed = AssistantJourney.fromJson(topLevel.cast<String, dynamic>());
    if (!parsed.isEmpty) {
      return parsed;
    }
  }
  return const AssistantJourney();
}

List<ProcessTimelineFrame> resolveAssistantProcessTimelineFromRunResponse(
  AssistantRunResponse response,
) {
  final runArtifactsTimeline = response.runArtifacts?.processTimeline;
  if (runArtifactsTimeline != null &&
      hasStructuredProcessTimeline(runArtifactsTimeline)) {
    return normalizeProcessTimeline(runArtifactsTimeline);
  }
  final topLevel = response.structuredResponse[assistantProcessTimelineField];
  final direct = _parseProcessTimelineList(topLevel);
  if (hasStructuredProcessTimeline(direct)) {
    return direct;
  }
  return const <ProcessTimelineFrame>[];
}

List<ProcessTimelineFrame>
resolveAssistantVisibleProcessTimelineFromRunResponse(
  AssistantRunResponse response,
) {
  return buildVisibleProcessTimeline(
    resolveAssistantProcessTimelineFromRunResponse(response),
  );
}

AssistantDisplayState resolveAssistantDisplayStateFromRunResponse(
  AssistantRunResponse response,
) {
  final direct = parseAssistantDisplayStateFromMap(
    (response.structuredResponse[assistantDisplayStateField] as Map?)
        ?.cast<String, dynamic>(),
  );
  if (hasAssistantDisplayState(direct)) {
    return direct;
  }
  final runArtifacts = response.runArtifacts;
  if (runArtifacts == null) {
    return const AssistantDisplayState();
  }
  return resolveAssistantDisplayStateFromRunArtifacts(runArtifacts);
}

String resolvePersistedAssistantDisplayMarkdown(Map<String, dynamic> message) {
  final displayState = resolvePersistedAssistantDisplayState(message);
  if (displayState.answer.blocks.isNotEmpty) {
    return renderAnswerBlocksToMarkdown(displayState.answer.blocks);
  }
  return AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
    (message[assistantDisplayMarkdownField] as String?) ?? '',
    allowJsonExtraction: false,
  );
}

String resolvePersistedAssistantDisplayPlainText(Map<String, dynamic> message) {
  final displayState = resolvePersistedAssistantDisplayState(message);
  if (displayState.answer.blocks.isNotEmpty) {
    return renderAnswerBlocksToPlainText(displayState.answer.blocks);
  }
  return AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
    (message[assistantDisplayPlainTextField] as String?) ?? '',
    allowJsonExtraction: false,
  );
}

String resolveAssistantFollowupPromptFromMessage(Map<String, dynamic> message) {
  return _sanitizeUserFacingTimelineText(
    (message[assistantFollowupPromptField] as String?) ?? '',
  );
}

List<String> resolveAssistantActionHintsFromMessage(
  Map<String, dynamic> message,
) {
  return ((message[assistantActionHintsField] as List?) ?? const <dynamic>[])
      .whereType<String>()
      .map(_sanitizeUserFacingTimelineText)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

String resolveAssistantFollowupPromptFromResponse(
  AssistantRunResponse response,
) {
  return _sanitizeUserFacingTimelineText(
    (response.structuredResponse[assistantFollowupPromptField] as String?) ??
        '',
  );
}

List<String> resolveAssistantActionHintsFromResponse(
  AssistantRunResponse response,
) {
  return ((response.structuredResponse[assistantActionHintsField] as List?) ??
          const <dynamic>[])
      .whereType<String>()
      .map(_sanitizeUserFacingTimelineText)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

AssistantJourney buildAssistantUiProcessTimeline(AssistantJourney journey) {
  if (journey.isEmpty) {
    return const AssistantJourney();
  }
  final stagesById = <JourneyStageId, AssistantJourneyStage>{
    for (final stage in journey.stages) stage.stageId: stage,
  };
  final normalizedStages = <AssistantJourneyStage>[
    _normalizeStageForTimeline(
      stageId: JourneyStageId.analyze,
      order: 0,
      rawStage: stagesById[JourneyStageId.analyze],
      readiness: journey.readiness,
      journeySummary: journey.summary,
    ),
    _mergeStageForTimeline(
      stageId: JourneyStageId.search,
      order: 1,
      primaryStage: stagesById[JourneyStageId.search],
      secondaryStage: stagesById[JourneyStageId.verify],
    ),
    _normalizeStageForTimeline(
      stageId: JourneyStageId.answer,
      order: 2,
      rawStage: stagesById[JourneyStageId.answer],
      readiness: journey.readiness,
      journeySummary: journey.summary,
    ),
  ];
  final normalizedEntries =
      journey.entries
          .map(_normalizeEntryForTimeline)
          .where(_timelineEntryHasVisibleSignal)
          .toList(growable: false)
        ..sort((a, b) => a.order.compareTo(b.order));
  final referenceSummary = _normalizeReferenceSummary(
    journey.referenceSummary,
    fallbackEntries: normalizedEntries,
  );
  final summary = _sanitizeUserFacingTimelineText(journey.summary);
  return AssistantJourney(
    stages: normalizedStages,
    entries: normalizedEntries,
    summary: summary,
    referenceSummary: referenceSummary,
    readiness: journey.readiness,
  );
}

AssistantJourney buildAssistantUiProcessTimelineFromProcessTimeline(
  List<ProcessTimelineFrame> processTimeline, {
  AssistantJourney fallbackJourney = const AssistantJourney(),
}) {
  final visibleTimeline = buildVisibleProcessTimeline(processTimeline);
  if (visibleTimeline.isEmpty) {
    return fallbackJourney.isEmpty
        ? const AssistantJourney()
        : buildAssistantUiProcessTimeline(fallbackJourney);
  }
  final references = <AssistantJourneyReference>[];
  final seenReferenceKeys = <String>{};
  void collectReference(RetrievalProcessingReference reference) {
    final key = reference.url.trim().isNotEmpty
        ? reference.url.trim()
        : '${reference.source.trim()}:${reference.title.trim()}';
    if (key.trim().isEmpty || !seenReferenceKeys.add(key)) {
      return;
    }
    references.add(
      AssistantJourneyReference(
        title: reference.title.trim(),
        url: reference.url.trim(),
        source: reference.source.trim(),
      ),
    );
  }

  final stages = <AssistantJourneyStage>[];
  final entries = <AssistantJourneyEntry>[];
  for (final frame in visibleTimeline) {
    final stageId = assistantJourneyStageForProcessStep(frame.stepId);
    if (stageId == JourneyStageId.unknown) {
      continue;
    }
    final summary = _sanitizeUserFacingTimelineText(
      frame.headline,
      stageId: stageId,
    );
    final detail = _sanitizeUserFacingTimelineText(
      frame.detail,
      stageId: stageId,
    );
    for (final reference in frame.references) {
      collectReference(reference);
    }
    stages.add(
      AssistantJourneyStage(
        stageId: stageId,
        status: frame.status,
        order: stages.length,
        summary: summary,
        referenceCount: stageId == JourneyStageId.search
            ? _maxInt(<int>[
                frame.references.length,
                frame.retrievalProcessing.acceptedDocumentCount,
                frame.retrievalProcessing.acceptedReferences.length,
              ])
            : 0,
      ),
    );
    if (summary.isEmpty && detail.isEmpty && frame.references.isEmpty) {
      continue;
    }
    entries.add(
      AssistantJourneyEntry(
        entryId: assistantProcessFrameId(frame.stepId),
        stageId: stageId,
        kind: frame.references.isNotEmpty
            ? JourneyEntryKind.referenceBundle
            : JourneyEntryKind.narrative,
        status: frame.status,
        order: entries.length,
        headline: summary,
        detail: detail,
        references: frame.references
            .map(
              (reference) => AssistantJourneyReference(
                title: reference.title.trim(),
                url: reference.url.trim(),
                source: reference.source.trim(),
              ),
            )
            .toList(growable: false),
      ),
    );
  }
  final finalAnswerReady = visibleTimeline.any(
    (frame) =>
        frame.stepId == ProcessStepId.answerOrganization &&
        frame.status == JourneyStageStatus.completed,
  );
  final summary = _firstNonEmpty(<String>[
    if (finalAnswerReady)
      ...visibleTimeline.reversed.map((frame) => frame.headline.trim()),
    fallbackJourney.summary,
    visibleTimeline.last.headline.trim(),
  ]);
  return AssistantJourney(
    stages: stages,
    entries: entries,
    summary: summary,
    referenceSummary: AssistantJourneyReferenceSummary(
      count: references.length,
      references: references,
    ),
    readiness: AssistantJourneyReadiness(
      nextAction: finalAnswerReady
          ? AssistantNextAction.answer
          : fallbackJourney.readiness.nextAction,
      finalAnswerMode: finalAnswerReady
          ? FinalAnswerMode.full
          : fallbackJourney.readiness.finalAnswerMode,
      answerEligibility: finalAnswerReady
          ? AnswerEligibility.eligible
          : fallbackJourney.readiness.answerEligibility,
      finalAnswerReady:
          finalAnswerReady || fallbackJourney.readiness.finalAnswerReady,
      clarificationNeeded: fallbackJourney.readiness.clarificationNeeded,
      needExpansion: fallbackJourney.readiness.needExpansion,
    ),
  );
}

Map<String, dynamic> buildPersistedAssistantTurnFields({
  required AssistantJourney journey,
  required String displayMarkdown,
  required String displayPlainText,
  required String followupPrompt,
  required List<String> actionHints,
  required int elapsedMs,
  Map<String, dynamic> displayState = const <String, dynamic>{},
  List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
  Map<String, dynamic> understandingSnapshot = const <String, dynamic>{},
  Map<String, dynamic> answerProcessing = const <String, dynamic>{},
  Map<String, dynamic> historicalThinkingSnapshot = const <String, dynamic>{},
  Map<String, dynamic> retrievalProcessing = const <String, dynamic>{},
  String providerReasoningContinuation = '',
}) {
  final persistedProcessTimeline = hasStructuredProcessTimeline(processTimeline)
      ? normalizeProcessTimeline(processTimeline)
      : buildProcessTimelineFromSnapshots(
          understandingSnapshot: parseRunArtifactsUnderstandingSnapshotFromMap(
            understandingSnapshot,
          ),
          retrievalProcessing: RetrievalProcessingSnapshot.fromJson(
            retrievalProcessing,
          ),
          answerProcessing: RunArtifactsAnswerProcessing.fromJson(
            answerProcessing,
          ),
        );
  final persistedUiTimeline =
      buildAssistantUiProcessTimelineFromProcessTimeline(
        persistedProcessTimeline,
        fallbackJourney: journey,
      );
  return <String, dynamic>{
    assistantTurnSchemaVersionField: assistantTurnSchemaVersion,
    assistantJourneyField: journey.toJson(),
    if (!persistedUiTimeline.isEmpty)
      assistantUiProcessTimelineField: persistedUiTimeline.toJson(),
    if (persistedProcessTimeline.isNotEmpty)
      assistantProcessTimelineField: persistedProcessTimeline
          .map((item) => item.toJson())
          .toList(growable: false),
    if (_hasStructuredContent(understandingSnapshot))
      assistantUnderstandingSnapshotField: _copyStructuredMap(
        understandingSnapshot,
      ),
    if (_hasStructuredContent(answerProcessing))
      assistantAnswerProcessingField: _copyStructuredMap(answerProcessing),
    if (_hasStructuredContent(historicalThinkingSnapshot))
      assistantHistoricalThinkingSnapshotField: _copyStructuredMap(
        historicalThinkingSnapshot,
      ),
    if (_hasStructuredContent(retrievalProcessing))
      assistantRetrievalProcessingField: _copyStructuredMap(
        retrievalProcessing,
      ),
    if (providerReasoningContinuation.trim().isNotEmpty)
      assistantProviderReasoningContinuationField: providerReasoningContinuation
          .trim(),
    if (_hasStructuredContent(displayState))
      assistantDisplayStateField: _copyStructuredMap(displayState),
    assistantDisplayMarkdownField:
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          displayMarkdown,
          allowJsonExtraction: false,
        ),
    assistantDisplayPlainTextField:
        AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
          displayPlainText,
          allowJsonExtraction: false,
        ),
    assistantFollowupPromptField: _sanitizeUserFacingTimelineText(
      followupPrompt,
    ),
    assistantActionHintsField: actionHints
        .map(_sanitizeUserFacingTimelineText)
        .where((item) => item.isNotEmpty)
        .toList(growable: false),
    'assistantElapsedMs': elapsedMs,
  };
}

bool isCanonicalPersistedAssistantTurnMessage(Map<String, dynamic> message) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return false;
  }
  final hasCanonicalEnvelope =
      message.containsKey(assistantJourneyField) ||
      message.containsKey(assistantDisplayStateField) ||
      message.containsKey(assistantUiProcessTimelineField) ||
      message.containsKey(assistantProcessTimelineField) ||
      message.containsKey(assistantDisplayMarkdownField) ||
      message.containsKey(assistantDisplayPlainTextField) ||
      message.containsKey(assistantUnderstandingSnapshotField) ||
      message.containsKey(assistantAnswerProcessingField) ||
      message.containsKey(assistantRetrievalProcessingField);
  if (!hasCanonicalEnvelope) {
    return false;
  }
  final answerSignals = <String>[
    resolvePersistedAssistantDisplayMarkdown(message),
    resolvePersistedAssistantDisplayPlainText(message),
    AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
      (message['content'] as String?) ?? '',
      allowJsonExtraction: false,
    ),
  ];
  return answerSignals.any((item) => item.trim().isNotEmpty) ||
      _hasReplayableAssistantTurnState(message);
}

Map<String, dynamic>? normalizeCanonicalPersistedAssistantTurnMessage(
  Map<String, dynamic> message,
) {
  if (!isCanonicalPersistedAssistantTurnMessage(message)) {
    return null;
  }
  final journey = resolvePersistedAssistantJourney(message);
  final processTimeline = resolvePersistedAssistantProcessTimeline(message);
  final displayState = resolvePersistedAssistantDisplayState(message);
  final displayMarkdown = resolvePersistedAssistantDisplayMarkdown(message);
  final displayPlainText = resolvePersistedAssistantDisplayPlainText(message);
  final understandingSnapshot = _resolvePersistedStructuredMap(
    message,
    assistantUnderstandingSnapshotField,
  );
  final answerProcessing = _resolvePersistedStructuredMap(
    message,
    assistantAnswerProcessingField,
  );
  final historicalThinkingSnapshot = _resolvePersistedStructuredMap(
    message,
    assistantHistoricalThinkingSnapshotField,
  );
  final retrievalProcessing = _resolvePersistedStructuredMap(
    message,
    assistantRetrievalProcessingField,
  );
  final providerReasoningContinuation =
      (message[assistantProviderReasoningContinuationField] as String?)
          ?.trim() ??
      '';
  final normalized = <String, dynamic>{
    ...message,
    assistantTurnSchemaVersionField: assistantTurnSchemaVersion,
    assistantJourneyField: journey.toJson(),
    if (hasAssistantDisplayState(displayState))
      assistantDisplayStateField: displayState.toJson(),
    if (processTimeline.isNotEmpty)
      assistantProcessTimelineField: processTimeline
          .map((item) => item.toJson())
          .toList(growable: false),
    if (_hasStructuredContent(understandingSnapshot))
      assistantUnderstandingSnapshotField: understandingSnapshot,
    if (_hasStructuredContent(answerProcessing))
      assistantAnswerProcessingField: answerProcessing,
    if (_hasStructuredContent(historicalThinkingSnapshot))
      assistantHistoricalThinkingSnapshotField: historicalThinkingSnapshot,
    if (_hasStructuredContent(retrievalProcessing))
      assistantRetrievalProcessingField: retrievalProcessing,
    if (providerReasoningContinuation.isNotEmpty)
      assistantProviderReasoningContinuationField:
          providerReasoningContinuation,
    assistantDisplayMarkdownField: displayMarkdown,
    assistantDisplayPlainTextField: displayPlainText,
    assistantFollowupPromptField: resolveAssistantFollowupPromptFromMessage(
      message,
    ),
    assistantActionHintsField: resolveAssistantActionHintsFromMessage(message),
    'assistantElapsedMs': (message['assistantElapsedMs'] as num?)?.toInt() ?? 0,
  };
  final bestContent = displayPlainText.isNotEmpty
      ? displayPlainText
      : (displayMarkdown.isNotEmpty
            ? AssistantDisplayTextResolver.stripMarkdown(displayMarkdown)
            : AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
                (message['content'] as String?) ?? '',
                allowJsonExtraction: false,
              ));
  normalized['content'] = bestContent;
  normalized.remove('machineEnvelope');
  normalized.remove('streamFinalAnswer');
  normalized.remove('decisionJson');
  final runArtifacts = (normalized['runArtifacts'] as Map?)
      ?.cast<String, dynamic>();
  if (runArtifacts != null && runArtifacts.isNotEmpty) {
    normalized['runArtifacts'] = Map<String, dynamic>.from(runArtifacts)
      ..remove('machineEnvelope');
  }
  return normalized;
}

bool _hasReplayableAssistantTurnState(Map<String, dynamic> message) {
  final journey = resolvePersistedAssistantJourney(message);
  if (!journey.isEmpty) {
    return true;
  }
  if (resolvePersistedAssistantProcessTimeline(message).isNotEmpty) {
    return true;
  }
  if (hasAssistantDisplayState(
    resolvePersistedAssistantDisplayState(message),
  )) {
    return true;
  }
  return _hasStructuredContent(
        _resolvePersistedStructuredMap(
          message,
          assistantUnderstandingSnapshotField,
        ),
      ) ||
      _hasStructuredContent(
        _resolvePersistedStructuredMap(message, assistantAnswerProcessingField),
      ) ||
      _hasStructuredContent(
        _resolvePersistedStructuredMap(
          message,
          assistantRetrievalProcessingField,
        ),
      );
}

AssistantJourneyStage _normalizeStageForTimeline({
  required JourneyStageId stageId,
  required int order,
  required AssistantJourneyStage? rawStage,
  required AssistantJourneyReadiness readiness,
  required String journeySummary,
}) {
  final rawStatus = rawStage?.status ?? JourneyStageStatus.pending;
  final summary = _sanitizeUserFacingTimelineText(
    rawStage?.summary ?? '',
    stageId: stageId,
  );
  if (rawStage != null) {
    return AssistantJourneyStage(
      stageId: stageId,
      status: rawStatus,
      order: order,
      summary: summary,
      referenceCount: rawStage.referenceCount,
    );
  }
  if (stageId == JourneyStageId.answer && readiness.finalAnswerReady) {
    return AssistantJourneyStage(
      stageId: stageId,
      status: JourneyStageStatus.completed,
      order: order,
      summary: _sanitizeUserFacingTimelineText(
        journeySummary,
        stageId: stageId,
      ),
      referenceCount: 0,
    );
  }
  return AssistantJourneyStage(
    stageId: stageId,
    status: JourneyStageStatus.pending,
    order: order,
    summary: '',
    referenceCount: 0,
  );
}

AssistantJourneyStage _mergeStageForTimeline({
  required JourneyStageId stageId,
  required int order,
  required AssistantJourneyStage? primaryStage,
  required AssistantJourneyStage? secondaryStage,
}) {
  final mergedSummary = _firstNonEmpty(<String>[
    _sanitizeUserFacingTimelineText(
      secondaryStage?.summary ?? '',
      stageId: stageId,
    ),
    _sanitizeUserFacingTimelineText(
      primaryStage?.summary ?? '',
      stageId: stageId,
    ),
  ]);
  if (primaryStage == null && secondaryStage == null) {
    return AssistantJourneyStage(
      stageId: stageId,
      status: JourneyStageStatus.pending,
      order: order,
      summary: '',
      referenceCount: 0,
    );
  }
  return AssistantJourneyStage(
    stageId: stageId,
    status: _mergeTimelineStageStatus(
      primaryStage?.status,
      secondaryStage?.status,
    ),
    order: order,
    summary: mergedSummary,
    referenceCount: _maxInt(<int>[
      primaryStage?.referenceCount ?? 0,
      secondaryStage?.referenceCount ?? 0,
    ]),
  );
}

JourneyStageStatus _mergeTimelineStageStatus(
  JourneyStageStatus? primary,
  JourneyStageStatus? secondary,
) {
  final statuses = <JourneyStageStatus>[?primary, ?secondary];
  if (statuses.contains(JourneyStageStatus.active)) {
    return JourneyStageStatus.active;
  }
  if (statuses.contains(JourneyStageStatus.blocked)) {
    return JourneyStageStatus.blocked;
  }
  if (statuses.contains(JourneyStageStatus.completed)) {
    return JourneyStageStatus.completed;
  }
  if (statuses.contains(JourneyStageStatus.skipped)) {
    return JourneyStageStatus.skipped;
  }
  if (statuses.contains(JourneyStageStatus.pending)) {
    return JourneyStageStatus.pending;
  }
  return JourneyStageStatus.unknown;
}

AssistantJourneyEntry _normalizeEntryForTimeline(AssistantJourneyEntry entry) {
  final normalizedReferences = entry.references
      .map(
        (reference) => AssistantJourneyReference(
          title: reference.title.trim(),
          url: reference.url.trim(),
          source: reference.source.trim(),
        ),
      )
      .where(
        (reference) =>
            reference.title.isNotEmpty ||
            reference.url.isNotEmpty ||
            reference.source.isNotEmpty,
      )
      .toList(growable: false);
  final headline = _normalizeTimelineHeadline(entry);
  final displayStageId = entry.stageId == JourneyStageId.verify
      ? JourneyStageId.search
      : entry.stageId;
  final detail = _sanitizeUserFacingTimelineText(
    entry.detail,
    stageId: displayStageId,
  );
  return AssistantJourneyEntry(
    entryId: entry.entryId,
    stageId: displayStageId,
    kind: entry.kind,
    status: entry.status,
    order: entry.order,
    headline: headline,
    detail: detail,
    references: normalizedReferences,
    provenance: entry.provenance,
  );
}

bool _timelineEntryHasVisibleSignal(AssistantJourneyEntry entry) {
  return entry.headline.isNotEmpty ||
      entry.detail.isNotEmpty ||
      entry.references.isNotEmpty;
}

AssistantJourneyReferenceSummary _normalizeReferenceSummary(
  AssistantJourneyReferenceSummary summary, {
  required List<AssistantJourneyEntry> fallbackEntries,
}) {
  final references = summary.references
      .map(
        (reference) => AssistantJourneyReference(
          title: reference.title.trim(),
          url: reference.url.trim(),
          source: reference.source.trim(),
        ),
      )
      .where(
        (reference) => reference.title.isNotEmpty || reference.url.isNotEmpty,
      )
      .toList(growable: false);
  if (references.isNotEmpty || summary.count > 0) {
    return AssistantJourneyReferenceSummary(
      count: summary.count > 0 ? summary.count : references.length,
      references: references,
    );
  }
  final deduped = <String, AssistantJourneyReference>{};
  for (final entry in fallbackEntries) {
    for (final reference in entry.references) {
      final key = reference.url.trim().isNotEmpty
          ? reference.url.trim()
          : '${reference.source.trim()}:${reference.title.trim()}';
      if (key.trim().isEmpty || deduped.containsKey(key)) {
        continue;
      }
      deduped[key] = reference;
    }
  }
  return AssistantJourneyReferenceSummary(
    count: deduped.length,
    references: deduped.values.toList(growable: false),
  );
}

String _normalizeTimelineHeadline(AssistantJourneyEntry entry) {
  final displayStageId = entry.stageId == JourneyStageId.verify
      ? JourneyStageId.search
      : entry.stageId;
  final headline = _sanitizeUserFacingTimelineText(
    entry.headline,
    stageId: displayStageId,
  );
  if (headline.isNotEmpty) {
    return headline;
  }
  final provenance = entry.provenance;
  if (provenance.actionCode == PlannerActionCode.expandSearch ||
      provenance.reasonCode == PlannerReasonCode.needMoreSearch ||
      provenance.reasonCode == PlannerReasonCode.needMoreEvidence) {
    return '我在补充核对还不够稳的信息';
  }
  if (entry.references.isNotEmpty) {
    return '我已补充一批可供你查看的参考资料';
  }
  return '';
}

String _sanitizeUserFacingTimelineText(
  String raw, {
  JourneyStageId stageId = JourneyStageId.unknown,
}) {
  final normalized =
      AssistantDisplayTextResolver.normalizeUserFacingProcessNarration(raw);
  if (normalized.isEmpty) {
    return '';
  }
  if (AssistantDisplayTextResolver.containsInternalProcessFragment(
    normalized,
  )) {
    return '';
  }
  return normalized;
}

String _firstNonEmpty(Iterable<String> values) {
  for (final value in values) {
    final trimmed = value.trim();
    if (trimmed.isNotEmpty) {
      return trimmed;
    }
  }
  return '';
}

int _maxInt(Iterable<int> values) {
  var maxValue = 0;
  for (final value in values) {
    if (value > maxValue) {
      maxValue = value;
    }
  }
  return maxValue;
}

bool _hasCurrentAssistantTurnSchemaVersion(Map<String, dynamic> message) {
  return (message[assistantTurnSchemaVersionField] as String?)?.trim() ==
      assistantTurnSchemaVersion;
}

List<ProcessTimelineFrame> _parseProcessTimelineList(Object? raw) {
  if (raw is! List) {
    return const <ProcessTimelineFrame>[];
  }
  final frames = raw
      .whereType<Map>()
      .map(
        (item) => ProcessTimelineFrame.fromJson(item.cast<String, dynamic>()),
      )
      .toList(growable: false);
  return normalizeProcessTimeline(frames);
}

Map<String, dynamic> _resolvePersistedStructuredMap(
  Map<String, dynamic> message,
  String key,
) {
  final direct = (message[key] as Map?)?.cast<String, dynamic>();
  if (direct != null && _hasStructuredContent(direct)) {
    return _copyStructuredMap(direct);
  }
  final runArtifacts = (message['runArtifacts'] as Map?)
      ?.cast<String, dynamic>();
  final nested = (runArtifacts?[key] as Map?)?.cast<String, dynamic>();
  if (nested != null && _hasStructuredContent(nested)) {
    return _copyStructuredMap(nested);
  }
  return const <String, dynamic>{};
}

Map<String, dynamic> _copyStructuredMap(Map<String, dynamic> value) {
  return Map<String, dynamic>.from(value);
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

bool _hasCanonicalPrimaryTimeline(AssistantJourney journey) {
  final orderedStageIds = journey.stages
      .map((stage) => stage.stageId)
      .where((stageId) => stageId != JourneyStageId.unknown)
      .toList(growable: false);
  if (orderedStageIds.length < assistantPrimaryJourneyStages.length) {
    return false;
  }
  for (var index = 0; index < assistantPrimaryJourneyStages.length; index++) {
    if (orderedStageIds[index] != assistantPrimaryJourneyStages[index]) {
      return false;
    }
  }
  return true;
}
