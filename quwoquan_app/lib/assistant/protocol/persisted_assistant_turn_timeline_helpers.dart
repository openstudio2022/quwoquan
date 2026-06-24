part of 'persisted_assistant_turn.dart';

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
  final detail = _sanitizeUserFacingTimelineText(
    entry.detail,
    stageId: entry.stageId,
  );
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
  final headline = _sanitizeUserFacingTimelineText(
    entry.headline,
    stageId: entry.stageId,
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
