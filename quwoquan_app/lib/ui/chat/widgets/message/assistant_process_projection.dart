import 'package:quwoquan_app/assistant/contracts/explainable_flow_event.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/orchestration/process_journal_bus.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';

List<ExplainableFlowEvent> buildExplainableFlowFromMessage(
  Map<String, dynamic> message,
) {
  final rawFlow =
      (message['uiExplainableFlow'] as List?)
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false) ??
      const <Map<String, dynamic>>[];
  if (rawFlow.isNotEmpty) {
    final forceCompleted = message['streaming'] != true;
    return _sanitizeExplainableFlowEvents(
      rawFlow.map(ExplainableFlowEvent.fromJson).toList(growable: false),
      forceCompleted: forceCompleted,
    );
  }

  final rawJournal =
      ((((message['runArtifacts'] as Map?)?['processJournal'] as List?) ??
              (message['processJournalV1'] as List?))
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false)) ??
      const <Map<String, dynamic>>[];
  if (rawJournal.isNotEmpty) {
    final journal = rawJournal
        .map(ProcessJournalEvent.fromJson)
        .toList(growable: false);
    return projectExplainableFlowFromJournal(journal);
  }

  final rawTimeline =
      (((message['uiProcessTimeline'] as List?) ??
              (message['uiProcessTimelineV2'] as List?))
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false)) ??
      const <Map<String, dynamic>>[];
  if (rawTimeline.isNotEmpty) {
    return projectExplainableFlowFromTimeline(rawTimeline);
  }
  return const <ExplainableFlowEvent>[];
}

List<ExplainableFlowEvent> projectExplainableFlowFromJournal(
  List<ProcessJournalEvent> journal,
) {
  if (journal.isEmpty) return const <ExplainableFlowEvent>[];
  final snapshot = ProcessJournalBus.toDisplaySnapshot(journal);
  final projected = <ExplainableFlowEvent>[];
  final indexByPhase = <String, int>{};
  for (final event in snapshot) {
    if (event.type == ProcessJournalEventType.stageSet ||
        event.type == ProcessJournalEventType.answerDelta ||
        event.type == ProcessJournalEventType.completed) {
      continue;
    }
    final phaseId = _normalizePhaseId(event.phaseId, stage: event.stage);
    final headline = _sanitizeProcessUiText(
      event.message.isNotEmpty ? event.message : event.reasonShort,
    );
    final detail = _detailFromPayload(event.payload);
    final references = _flowReferencesFromProcessReferences(event.references);
    if (headline.isEmpty && detail.isEmpty && references.isEmpty) {
      continue;
    }
    final existingIndex = indexByPhase[phaseId];
    final nextStatus = event.type == ProcessJournalEventType.liveCursor
        ? ExplainablePhaseStatus.active
        : ExplainablePhaseStatus.completed;
    if (existingIndex == null) {
      indexByPhase[phaseId] = projected.length;
      projected.add(
        ExplainableFlowEvent(
          phaseId: phaseId,
          phaseOrder: projected.length,
          phaseStatus: nextStatus,
          headline: headline,
          detail: detail,
          references: references,
        ),
      );
      continue;
    }
    final previous = projected[existingIndex];
    projected[existingIndex] = previous.copyWith(
      phaseStatus: nextStatus,
      headline: headline.isNotEmpty ? headline : previous.headline,
      detail: detail.isNotEmpty ? detail : previous.detail,
      references: _mergeFlowReferences(previous.references, references),
    );
  }
  return _sanitizeExplainableFlowEvents(projected, forceCompleted: true);
}

List<ExplainableFlowEvent> projectExplainableFlowFromTimeline(
  List<Map<String, dynamic>> timeline,
) {
  if (timeline.isEmpty) return const <ExplainableFlowEvent>[];
  final projected = <ExplainableFlowEvent>[];
  final indexByPhase = <String, int>{};
  for (final item in timeline) {
    final payload =
        (item['payload'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final phaseId = _normalizePhaseId(
      (payload['phaseId'] as String?)?.trim() ?? '',
      stage: (payload['stage'] as String?)?.trim() ?? '',
      scope: (item['scope'] as String?)?.trim() ?? '',
    );
    final headline = _sanitizeProcessUiText(
      (item['summary'] as String?)?.trim() ?? '',
    );
    final detail = _timelineDetail(item, payload);
    final references = _flowReferencesFromTimeline(item['references'] as List?);
    if (headline.isEmpty && detail.isEmpty && references.isEmpty) {
      continue;
    }
    final nextStatus = payload['streaming'] == true
        ? ExplainablePhaseStatus.active
        : ExplainablePhaseStatus.completed;
    final existingIndex = indexByPhase[phaseId];
    if (existingIndex == null) {
      indexByPhase[phaseId] = projected.length;
      projected.add(
        ExplainableFlowEvent(
          phaseId: phaseId,
          phaseOrder: projected.length,
          phaseStatus: nextStatus,
          headline: headline,
          detail: detail,
          references: references,
        ),
      );
      continue;
    }
    final previous = projected[existingIndex];
    projected[existingIndex] = previous.copyWith(
      phaseStatus: nextStatus,
      headline: headline.isNotEmpty ? headline : previous.headline,
      detail: detail.isNotEmpty ? detail : previous.detail,
      references: _mergeFlowReferences(previous.references, references),
    );
  }
  return _sanitizeExplainableFlowEvents(projected, forceCompleted: true);
}

List<ExplainableFlowEvent> _sanitizeExplainableFlowEvents(
  List<ExplainableFlowEvent> events, {
  bool forceCompleted = false,
}) {
  final sanitized = <ExplainableFlowEvent>[];
  for (final event in events) {
    final headline = _sanitizeProcessUiText(event.headline);
    final detail = _sanitizeProcessUiText(event.detail);
    final references = _mergeFlowReferences(
      const <FlowReference>[],
      event.references
          .where(
            (ref) => ref.title.trim().isNotEmpty && ref.url.trim().isNotEmpty,
          )
          .toList(growable: false),
    );
    if (headline.isEmpty && detail.isEmpty && references.isEmpty) {
      continue;
    }
    sanitized.add(
      event.copyWith(
        headline: headline,
        detail: detail,
        references: references,
        phaseStatus:
            forceCompleted && event.phaseStatus == ExplainablePhaseStatus.active
            ? ExplainablePhaseStatus.completed
            : event.phaseStatus,
      ),
    );
  }
  sanitized.sort((a, b) => a.phaseOrder.compareTo(b.phaseOrder));
  return sanitized;
}

List<FlowReference> _flowReferencesFromProcessReferences(
  List<ProcessSourceReference> references,
) {
  return _mergeFlowReferences(
    const <FlowReference>[],
    references
        .where(
          (item) => item.title.trim().isNotEmpty && item.url.trim().isNotEmpty,
        )
        .map(
          (item) => FlowReference(
            title: item.title.trim(),
            url: item.url.trim(),
            source: item.source.trim(),
          ),
        )
        .toList(growable: false),
  );
}

List<FlowReference> _flowReferencesFromTimeline(List? rawReferences) {
  final references =
      rawReferences
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .map(
            (item) => FlowReference(
              title: (item['title'] as String?)?.trim() ?? '',
              url: (item['url'] as String?)?.trim() ?? '',
              source: (item['source'] as String?)?.trim() ?? '',
            ),
          )
          .where((item) => item.title.isNotEmpty && item.url.isNotEmpty)
          .toList(growable: false) ??
      const <FlowReference>[];
  return _mergeFlowReferences(const <FlowReference>[], references);
}

List<FlowReference> _mergeFlowReferences(
  List<FlowReference> existing,
  List<FlowReference> incoming,
) {
  final seen = <String>{for (final item in existing) item.url.trim()};
  final merged = <FlowReference>[...existing];
  for (final item in incoming) {
    final url = item.url.trim();
    if (url.isEmpty || !seen.add(url)) continue;
    merged.add(item);
  }
  return merged;
}

String _timelineDetail(
  Map<String, dynamic> item,
  Map<String, dynamic> payload,
) {
  final rawDetails = <String>[
    ...((item['details'] as List?) ?? const <dynamic>[]).map(
      (detail) => _sanitizeProcessUiText(detail.toString()),
    ),
    ...((payload['details'] as List?) ?? const <dynamic>[]).map(
      (detail) => _sanitizeProcessUiText(detail.toString()),
    ),
  ].where((detail) => detail.isNotEmpty).toList(growable: false);
  if (rawDetails.isEmpty) return '';
  return rawDetails.join('  ');
}

String _detailFromPayload(Map<String, dynamic> payload) {
  final rawDetails =
      (payload['details'] as List?)
          ?.map((detail) => _sanitizeProcessUiText(detail.toString()))
          .where((detail) => detail.isNotEmpty)
          .toList(growable: false) ??
      const <String>[];
  if (rawDetails.isEmpty) return '';
  return rawDetails.join('  ');
}

String _normalizePhaseId(String raw, {String stage = '', String scope = ''}) {
  final normalized = raw.trim().toLowerCase();
  switch (normalized) {
    case PhaseId.understand:
    case 'understanding':
      return PhaseId.understand;
    case PhaseId.classify:
      return PhaseId.classify;
    case PhaseId.plan:
    case 'planning':
      return PhaseId.plan;
    case PhaseId.execute:
    case 'searching':
    case 'executing':
      return PhaseId.execute;
    case PhaseId.aggregate:
    case 'analyzing':
      return PhaseId.aggregate;
    case PhaseId.answer:
    case 'answering':
    case 'completed':
      return PhaseId.answer;
    case PhaseId.dispatch:
    case PhaseId.subExecute:
    case PhaseId.merge:
    case PhaseId.expand:
    case PhaseId.recall:
    case PhaseId.clarify:
      return normalized;
  }

  final stageNormalized = stage.trim().toLowerCase();
  if (stageNormalized.isNotEmpty) {
    return _normalizePhaseId(stageNormalized);
  }
  final scopeNormalized = scope.trim().toLowerCase();
  switch (scopeNormalized) {
    case 'skill':
      return PhaseId.execute;
    case 'aggregation':
      return PhaseId.aggregate;
    default:
      return PhaseId.understand;
  }
}

String _sanitizeProcessUiText(String raw) {
  final normalized =
      AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(raw);
  if (normalized.isEmpty) return '';
  if (AssistantContentFilters.isProgressPlaceholder(normalized) ||
      AssistantContentFilters.isJsonEnvelope(normalized) ||
      AssistantContentFilters.isDegradedText(normalized)) {
    return '';
  }
  for (final fragment in _blockedFragments) {
    if (normalized.contains(fragment)) return '';
  }
  if (normalized.startsWith('{') || normalized.startsWith('[')) return '';
  return normalized.trim();
}

const List<String> _blockedFragments = <String>[
  'assistant_turn',
  'contractVersion',
  'tool_call',
  '<tool_call>',
  '</tool_call>',
  'queryTasks',
  'queryVariants',
  'machineEnvelope',
  'runArtifacts',
  'provider',
  'freshnessHoursMax',
  'timeScope',
];
