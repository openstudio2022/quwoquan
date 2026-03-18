import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

enum AssistantJourneyBlockKind { narrative, searchSummary, verificationSummary }

class AssistantJourneyReferenceViewModel {
  const AssistantJourneyReferenceViewModel({
    required this.title,
    required this.url,
    this.source = '',
  });

  final String title;
  final String url;
  final String source;
}

class AssistantJourneyStageViewModel {
  const AssistantJourneyStageViewModel({
    required this.stageId,
    required this.order,
    required this.label,
    this.status = JourneyStageStatus.pending,
    this.summary = '',
    this.referenceCount = 0,
  });

  final JourneyStageId stageId;
  final int order;
  final String label;
  final JourneyStageStatus status;
  final String summary;
  final int referenceCount;

  bool get isResolved =>
      status == JourneyStageStatus.completed ||
      status == JourneyStageStatus.blocked ||
      status == JourneyStageStatus.skipped;

  bool get isActive => status == JourneyStageStatus.active;

  bool get isBlocked => status == JourneyStageStatus.blocked;
}

class AssistantJourneyBlockViewModel {
  const AssistantJourneyBlockViewModel({
    required this.kind,
    required this.stageId,
    this.headline = '',
    this.detail = '',
    this.references = const <AssistantJourneyReferenceViewModel>[],
  });

  final AssistantJourneyBlockKind kind;
  final JourneyStageId stageId;
  final String headline;
  final String detail;
  final List<AssistantJourneyReferenceViewModel> references;

  bool get hasReferences => references.isNotEmpty;
}

class AssistantJourneyViewModel {
  const AssistantJourneyViewModel({
    this.journey = const AssistantJourney(),
    this.stages = const <AssistantJourneyStageViewModel>[],
    this.blocks = const <AssistantJourneyBlockViewModel>[],
    this.summary = '',
    this.activeStageId = JourneyStageId.unknown,
    this.activeStageLabel = '',
    this.referenceCount = 0,
    this.isRunning = false,
    this.usageStats = const <String, dynamic>{},
    this.elapsedMs = 0,
    this.finalAnswerReady = false,
    this.clarificationNeeded = false,
    this.needExpansion = false,
  });

  final AssistantJourney journey;
  final List<AssistantJourneyStageViewModel> stages;
  final List<AssistantJourneyBlockViewModel> blocks;
  final String summary;
  final JourneyStageId activeStageId;
  final String activeStageLabel;
  final int referenceCount;
  final bool isRunning;
  final Map<String, dynamic> usageStats;
  final int elapsedMs;
  final bool finalAnswerReady;
  final bool clarificationNeeded;
  final bool needExpansion;

  bool get hasVisibleContent =>
      stages.isNotEmpty || blocks.isNotEmpty || summary.isNotEmpty;

  bool get isInitialWait =>
      isRunning &&
      blocks.isEmpty &&
      stages.isNotEmpty &&
      activeStageId == JourneyStageId.analyze;
}

AssistantJourneyViewModel buildAssistantJourneyViewModel({
  required AssistantJourney journey,
  required bool isRunning,
  Map<String, dynamic> usageStats = const <String, dynamic>{},
  int elapsedMs = 0,
}) {
  final timelineJourney = buildAssistantUiProcessTimelineV2(journey);
  final stages = _buildStages(journey: timelineJourney, isRunning: isRunning);
  final blocks = _buildBlocks(timelineJourney, stages: stages);
  final activeStage = _resolveActiveStage(stages);
  final summary = _resolveSummary(timelineJourney, stages: stages, blocks: blocks);
  return AssistantJourneyViewModel(
    journey: timelineJourney,
    stages: stages,
    blocks: blocks,
    summary: summary,
    activeStageId: activeStage.stageId,
    activeStageLabel: activeStage.label,
    referenceCount: timelineJourney.referenceSummary.count > 0
        ? timelineJourney.referenceSummary.count
        : <String>{
            for (final block in blocks)
              for (final reference in block.references)
                if (reference.url.trim().isNotEmpty) reference.url.trim(),
          }.length,
    isRunning: isRunning,
    usageStats: usageStats,
    elapsedMs: elapsedMs,
    finalAnswerReady: timelineJourney.readiness.finalAnswerReady,
    clarificationNeeded: timelineJourney.readiness.clarificationNeeded,
    needExpansion: timelineJourney.readiness.needExpansion,
  );
}

List<AssistantJourneyStageViewModel> _buildStages({
  required AssistantJourney journey,
  required bool isRunning,
}) {
  if (journey.isEmpty) {
    return const <AssistantJourneyStageViewModel>[];
  }
  final rawByStageId = <JourneyStageId, AssistantJourneyStage>{
    for (final stage in journey.stages) stage.stageId: stage,
  };
  return <AssistantJourneyStageViewModel>[
    _stageViewModel(
      stageId: JourneyStageId.analyze,
      order: 0,
      label: UITextConstants.assistantProcessStageUnderstand,
      stage: rawByStageId[JourneyStageId.analyze],
    ),
    _stageViewModel(
      stageId: JourneyStageId.search,
      order: 1,
      label: UITextConstants.assistantProcessStageSearch,
      stage: rawByStageId[JourneyStageId.search],
    ),
    _stageViewModel(
      stageId: JourneyStageId.verify,
      order: 2,
      label: UITextConstants.assistantProcessStageAnalyze,
      stage: rawByStageId[JourneyStageId.verify],
    ),
    _stageViewModel(
      stageId: JourneyStageId.answer,
      order: 3,
      label: UITextConstants.assistantProcessStageAnswer,
      stage: rawByStageId[JourneyStageId.answer],
    ),
  ];
}

AssistantJourneyStageViewModel _stageViewModel({
  required JourneyStageId stageId,
  required int order,
  required String label,
  required AssistantJourneyStage? stage,
}) {
  final summary = _sanitizeJourneyText(stage?.summary ?? '');
  return AssistantJourneyStageViewModel(
    stageId: stageId,
    order: order,
    label: label,
    status: stage?.status ?? JourneyStageStatus.pending,
    summary: summary,
    referenceCount: stage?.referenceCount ?? 0,
  );
}

AssistantJourneyStageViewModel _resolveActiveStage(
  List<AssistantJourneyStageViewModel> stages,
) {
  if (stages.isEmpty) {
    return const AssistantJourneyStageViewModel(
      stageId: JourneyStageId.unknown,
      order: -1,
      label: '',
    );
  }
  return stages.firstWhere(
    (stage) =>
        stage.status == JourneyStageStatus.active ||
        stage.status == JourneyStageStatus.blocked,
    orElse: () => stages.lastWhere(
      (stage) => stage.status == JourneyStageStatus.completed,
      orElse: () => stages.first,
    ),
  );
}

List<AssistantJourneyBlockViewModel> _buildBlocks(
  AssistantJourney journey, {
  required List<AssistantJourneyStageViewModel> stages,
}) {
  final labelByStageId = <JourneyStageId, String>{
    for (final stage in stages) stage.stageId: stage.label,
  };
  final blocks = <AssistantJourneyBlockViewModel>[];
  final signatures = <String>{};
  final orderedEntries = List<AssistantJourneyEntry>.of(journey.entries)
    ..sort((a, b) => a.order.compareTo(b.order));
  for (final entry in orderedEntries) {
    final headline = _sanitizeJourneyText(entry.headline);
    final detail = _sanitizeJourneyText(entry.detail);
    final references = entry.references
        .map(
          (reference) => AssistantJourneyReferenceViewModel(
            title: reference.title.trim(),
            url: reference.url.trim(),
            source: reference.source.trim(),
          ),
        )
        .where(
          (reference) =>
              reference.title.isNotEmpty && reference.url.isNotEmpty,
        )
        .toList(growable: false);
    if (headline.isEmpty && detail.isEmpty && references.isEmpty) {
      continue;
    }
    final kind = references.isEmpty
        ? AssistantJourneyBlockKind.narrative
        : entry.stageId == JourneyStageId.search
        ? AssistantJourneyBlockKind.searchSummary
        : AssistantJourneyBlockKind.verificationSummary;
    final resolvedHeadline = headline.isNotEmpty
        ? headline
        : (labelByStageId[entry.stageId] ?? '');
    final signature = <String>[
      kind.name,
      entry.stageId.name,
      resolvedHeadline,
      detail,
      references.map((item) => item.url).join('|'),
    ].join('::');
    if (!signatures.add(signature)) {
      continue;
    }
    blocks.add(
      AssistantJourneyBlockViewModel(
        kind: kind,
        stageId: entry.stageId,
        headline: resolvedHeadline,
        detail: detail,
        references: references,
      ),
    );
  }
  if (blocks.isEmpty) {
    final summary = _resolveSummary(journey, stages: stages, blocks: blocks);
    if (summary.isNotEmpty) {
      blocks.add(
        AssistantJourneyBlockViewModel(
          kind: AssistantJourneyBlockKind.narrative,
          stageId: journey.activeStageId,
          headline: summary,
        ),
      );
    }
  }
  return blocks;
}

String _resolveSummary(
  AssistantJourney journey, {
  required List<AssistantJourneyStageViewModel> stages,
  required List<AssistantJourneyBlockViewModel> blocks,
}) {
  final summary = _sanitizeJourneyText(journey.summary);
  if (summary.isNotEmpty) return summary;
  for (final stage in stages.reversed) {
    if (stage.summary.isNotEmpty) return stage.summary;
  }
  for (final block in blocks.reversed) {
    if (block.headline.isNotEmpty) return block.headline;
  }
  return '';
}

String _sanitizeJourneyText(String raw) {
  final normalized =
      AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(raw);
  if (normalized.isEmpty) return '';
  if (RegExp(r'\{\{[^{}]+\}\}').hasMatch(normalized)) return '';
  if (AssistantContentFilters.isJsonEnvelope(normalized) ||
      AssistantContentFilters.isDegradedText(normalized) ||
      AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
        normalized,
      ) ||
      AssistantDisplayTextResolver.containsInternalProcessFragment(normalized) ||
      normalized.contains('模型调用') ||
      normalized.toLowerCase().contains('token')) {
    return '';
  }
  if (normalized.startsWith('{') || normalized.startsWith('[')) return '';
  return normalized.trim();
}
