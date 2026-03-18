import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';

const String assistantJourneyField = 'journey';
const String assistantUiProcessTimelineV2Field = 'uiProcessTimelineV2';
const String assistantDisplayMarkdownField = 'displayMarkdown';
const String assistantDisplayPlainTextField = 'displayPlainText';
const String assistantFollowupPromptField = 'followupPrompt';
const String assistantActionHintsField = 'actionHints';
const String assistantTurnSchemaVersionField = 'assistantTurnSchemaVersion';
const String assistantHistoryStorageVersion = 'assistant_history_v3';
const String assistantTurnSchemaVersion = 'assistant_turn_v3';

const List<JourneyStageId> assistantPrimaryJourneyStages = <JourneyStageId>[
  JourneyStageId.analyze,
  JourneyStageId.search,
  JourneyStageId.verify,
  JourneyStageId.answer,
];

AssistantJourney resolvePersistedAssistantJourney(Map<String, dynamic> message) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const AssistantJourney();
  }
  final raw = (message[assistantJourneyField] as Map?)?.cast<String, dynamic>();
  if (raw == null || raw.isEmpty) {
    return const AssistantJourney();
  }
  final parsed = AssistantJourney.fromJson(raw);
  return parsed.isEmpty ? const AssistantJourney() : parsed;
}

AssistantJourney resolvePersistedAssistantTimeline(Map<String, dynamic> message) {
  if (!_hasCurrentAssistantTurnSchemaVersion(message)) {
    return const AssistantJourney();
  }
  final raw =
      (message[assistantUiProcessTimelineV2Field] as Map?)
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

AssistantJourney resolveAssistantJourneyFromRunResponse(AssistantRunResponse response) {
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

String resolvePersistedAssistantDisplayMarkdown(Map<String, dynamic> message) {
  return AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
    (message[assistantDisplayMarkdownField] as String?) ?? '',
    allowJsonExtraction: false,
  );
}

String resolvePersistedAssistantDisplayPlainText(Map<String, dynamic> message) {
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

List<String> resolveAssistantActionHintsFromMessage(Map<String, dynamic> message) {
  return ((message[assistantActionHintsField] as List?) ?? const <dynamic>[])
      .whereType<String>()
      .map(_sanitizeUserFacingTimelineText)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

String resolveAssistantFollowupPromptFromResponse(AssistantRunResponse response) {
  return _sanitizeUserFacingTimelineText(
    (response.structuredResponse[assistantFollowupPromptField] as String?) ?? '',
  );
}

List<String> resolveAssistantActionHintsFromResponse(AssistantRunResponse response) {
  return ((response.structuredResponse[assistantActionHintsField] as List?) ??
          const <dynamic>[])
      .whereType<String>()
      .map(_sanitizeUserFacingTimelineText)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

AssistantJourney buildAssistantUiProcessTimelineV2(AssistantJourney journey) {
  if (journey.isEmpty) {
    return const AssistantJourney();
  }
  final stagesById = <JourneyStageId, AssistantJourneyStage>{
    for (final stage in journey.stages) stage.stageId: stage,
  };
  final normalizedStages = <AssistantJourneyStage>[
    for (var index = 0; index < assistantPrimaryJourneyStages.length; index++)
      _normalizeStageForTimeline(
        stageId: assistantPrimaryJourneyStages[index],
        order: index,
        rawStage: stagesById[assistantPrimaryJourneyStages[index]],
        readiness: journey.readiness,
        journeySummary: journey.summary,
      ),
  ];
  final normalizedEntries = journey.entries
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

Map<String, dynamic> buildPersistedAssistantTurnFields({
  required AssistantJourney journey,
  required String displayMarkdown,
  required String displayPlainText,
  required String followupPrompt,
  required List<String> actionHints,
  required int elapsedMs,
}) {
  final persistedJourney = buildAssistantUiProcessTimelineV2(journey);
  return <String, dynamic>{
    assistantTurnSchemaVersionField: assistantTurnSchemaVersion,
    assistantJourneyField: journey.toJson(),
    assistantUiProcessTimelineV2Field: persistedJourney.toJson(),
    assistantDisplayMarkdownField: AssistantDisplayTextResolver
        .normalizeCompletedDisplayCandidate(
          displayMarkdown,
          allowJsonExtraction: false,
        ),
    assistantDisplayPlainTextField: AssistantDisplayTextResolver
        .normalizeCompletedPlainTextCandidate(
          displayPlainText,
          allowJsonExtraction: false,
        ),
    assistantFollowupPromptField: _sanitizeUserFacingTimelineText(followupPrompt),
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
  final journey = resolvePersistedAssistantJourney(message);
  final timeline = resolvePersistedAssistantTimeline(message);
  if (journey.isEmpty || timeline.isEmpty) {
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
  return answerSignals.any((item) => item.trim().isNotEmpty);
}

Map<String, dynamic>? normalizeCanonicalPersistedAssistantTurnMessage(
  Map<String, dynamic> message,
) {
  if (!isCanonicalPersistedAssistantTurnMessage(message)) {
    return null;
  }
  final journey = resolvePersistedAssistantJourney(message);
  final timeline = resolvePersistedAssistantTimeline(message);
  final displayMarkdown = resolvePersistedAssistantDisplayMarkdown(message);
  final displayPlainText = resolvePersistedAssistantDisplayPlainText(message);
  final normalized = <String, dynamic>{
    ...message,
    assistantTurnSchemaVersionField: assistantTurnSchemaVersion,
    assistantJourneyField: journey.toJson(),
    assistantUiProcessTimelineV2Field: timeline.toJson(),
    assistantDisplayMarkdownField: displayMarkdown,
    assistantDisplayPlainTextField: displayPlainText,
    assistantFollowupPromptField:
        resolveAssistantFollowupPromptFromMessage(message),
    assistantActionHintsField:
        resolveAssistantActionHintsFromMessage(message),
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
  final runArtifacts = (normalized['runArtifacts'] as Map?)?.cast<String, dynamic>();
  if (runArtifacts != null && runArtifacts.isNotEmpty) {
    normalized['runArtifacts'] = Map<String, dynamic>.from(runArtifacts)
      ..remove('machineEnvelope');
  }
  return normalized;
}

AssistantJourneyStage _normalizeStageForTimeline({
  required JourneyStageId stageId,
  required int order,
  required AssistantJourneyStage? rawStage,
  required AssistantJourneyReadiness readiness,
  required String journeySummary,
}) {
  final rawStatus = rawStage?.status ?? JourneyStageStatus.pending;
  final summary = _sanitizeUserFacingTimelineText(rawStage?.summary ?? '');
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
      summary: _sanitizeUserFacingTimelineText(journeySummary),
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
  final detail = _sanitizeUserFacingTimelineText(entry.detail);
  return AssistantJourneyEntry(
    entryId: entry.entryId,
    stageId: entry.stageId,
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
      .where((reference) => reference.title.isNotEmpty || reference.url.isNotEmpty)
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
  final headline = _sanitizeUserFacingTimelineText(entry.headline);
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

String _sanitizeUserFacingTimelineText(String raw) {
  final text = raw.trim();
  if (text.isEmpty) {
    return '';
  }
  if (RegExp(r'\{\{[^{}]+\}\}').hasMatch(text)) {
    return '';
  }
  final normalized = AssistantDisplayTextResolver.normalizePlainText(text);
  if (normalized.isEmpty) {
    return '';
  }
  if (AssistantDisplayTextResolver.containsInternalProcessFragment(normalized) ||
      AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
        normalized,
      ) ||
      AssistantContentFilters.isJsonEnvelope(normalized) ||
      AssistantContentFilters.isDegradedText(normalized)) {
    return '';
  }
  final lower = normalized.toLowerCase();
  if (lower.contains('token') ||
      lower.contains('model calls') ||
      normalized.contains('模型调用')) {
    return '';
  }
  return normalized;
}

bool _hasCurrentAssistantTurnSchemaVersion(Map<String, dynamic> message) {
  return (message[assistantTurnSchemaVersionField] as String?)?.trim() ==
      assistantTurnSchemaVersion;
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
