import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
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
    this.retrievalProcessing = const RetrievalProcessingSnapshot(),
    this.stages = const <AssistantJourneyStageViewModel>[],
    this.blocks = const <AssistantJourneyBlockViewModel>[],
    this.summary = '',
    this.activeStageId = JourneyStageId.unknown,
    this.activeStageLabel = '',
    this.processedDocumentCount = 0,
    this.acceptedDocumentCount = 0,
    this.referenceCount = 0,
    this.isRunning = false,
    this.usageStats = const <String, dynamic>{},
    this.elapsedMs = 0,
    this.finalAnswerReady = false,
    this.clarificationNeeded = false,
    this.needExpansion = false,
  });

  final AssistantJourney journey;
  final RetrievalProcessingSnapshot retrievalProcessing;
  final List<AssistantJourneyStageViewModel> stages;
  final List<AssistantJourneyBlockViewModel> blocks;
  final String summary;
  final JourneyStageId activeStageId;
  final String activeStageLabel;
  final int processedDocumentCount;
  final int acceptedDocumentCount;
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
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
}) {
  final timelineJourney = buildAssistantUiProcessTimeline(journey);
  final effectiveRetrievalProcessing = _normalizeRetrievalProcessing(
    retrievalProcessing,
    timelineJourney,
  );
  final stages = _buildStages(
    journey: timelineJourney,
    isRunning: isRunning,
    retrievalProcessing: effectiveRetrievalProcessing,
  );
  final blocks = _buildBlocks(
    timelineJourney,
    stages: stages,
    retrievalProcessing: effectiveRetrievalProcessing,
  );
  final activeStage = _resolveActiveStage(stages);
  final summary = _resolveSummary(
    timelineJourney,
    stages: stages,
    blocks: blocks,
  );
  final acceptedDocumentCount =
      effectiveRetrievalProcessing.acceptedDocumentCount;
  final processedDocumentCount =
      effectiveRetrievalProcessing.processedDocumentCount;
  final referenceCount = acceptedDocumentCount > 0
      ? acceptedDocumentCount
      : timelineJourney.referenceSummary.count > 0
      ? timelineJourney.referenceSummary.count
      : <String>{
          for (final block in blocks)
            for (final reference in block.references)
              if (reference.url.trim().isNotEmpty) reference.url.trim(),
        }.length;
  return AssistantJourneyViewModel(
    journey: timelineJourney,
    retrievalProcessing: effectiveRetrievalProcessing,
    stages: stages,
    blocks: blocks,
    summary: summary,
    activeStageId: activeStage.stageId,
    activeStageLabel: activeStage.label,
    processedDocumentCount: processedDocumentCount,
    acceptedDocumentCount: acceptedDocumentCount,
    referenceCount: referenceCount,
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
  required RetrievalProcessingSnapshot retrievalProcessing,
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
    _mergedStageViewModel(
      stageId: JourneyStageId.search,
      order: 1,
      label: UITextConstants.assistantProcessStageSearch,
      primaryStage: rawByStageId[JourneyStageId.search],
      secondaryStage: rawByStageId[JourneyStageId.verify],
      referenceCount: retrievalProcessing.acceptedDocumentCount,
    ),
    _stageViewModel(
      stageId: JourneyStageId.answer,
      order: 2,
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

AssistantJourneyStageViewModel _mergedStageViewModel({
  required JourneyStageId stageId,
  required int order,
  required String label,
  required AssistantJourneyStage? primaryStage,
  required AssistantJourneyStage? secondaryStage,
  int referenceCount = 0,
}) {
  return AssistantJourneyStageViewModel(
    stageId: stageId,
    order: order,
    label: label,
    status: _mergeStageStatus(primaryStage?.status, secondaryStage?.status),
    summary: _firstNonEmpty(<String>[
      _sanitizeJourneyText(secondaryStage?.summary ?? ''),
      _sanitizeJourneyText(primaryStage?.summary ?? ''),
    ]),
    referenceCount: _maxInt(<int>[
      referenceCount,
      primaryStage?.referenceCount ?? 0,
      secondaryStage?.referenceCount ?? 0,
    ]),
  );
}

JourneyStageStatus _mergeStageStatus(
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
  required RetrievalProcessingSnapshot retrievalProcessing,
}) {
  final labelByStageId = <JourneyStageId, String>{
    for (final stage in stages) stage.stageId: stage.label,
  };
  final blocks = <AssistantJourneyBlockViewModel>[];
  final signatures = <String>{};
  final retrievalNarratives = <String>[];
  final orderedEntries = List<AssistantJourneyEntry>.of(journey.entries)
    ..sort((a, b) => a.order.compareTo(b.order));
  for (final entry in orderedEntries) {
    final displayStageId = _displayStageId(entry.stageId);
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
          (reference) => reference.title.isNotEmpty && reference.url.isNotEmpty,
        )
        .toList(growable: false);
    if (headline.isEmpty && detail.isEmpty && references.isEmpty) {
      continue;
    }
    final shouldMergeIntoRetrievalBlock =
        _hasRetrievalProcessingSignal(retrievalProcessing) &&
        (entry.stageId == JourneyStageId.search ||
            entry.stageId == JourneyStageId.verify);
    if (shouldMergeIntoRetrievalBlock) {
      if (detail.isNotEmpty) {
        retrievalNarratives.add(detail);
      } else if (headline.isNotEmpty) {
        retrievalNarratives.add(headline);
      }
      continue;
    }
    final kind = references.isEmpty
        ? AssistantJourneyBlockKind.narrative
        : displayStageId == JourneyStageId.search
        ? AssistantJourneyBlockKind.searchSummary
        : AssistantJourneyBlockKind.verificationSummary;
    final resolvedHeadline = headline.isNotEmpty
        ? headline
        : (labelByStageId[displayStageId] ?? '');
    final signature = <String>[
      kind.name,
      displayStageId.name,
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
        stageId: displayStageId,
        headline: resolvedHeadline,
        detail: detail,
        references: references,
      ),
    );
  }
  final retrievalBlock = _buildRetrievalProcessingBlock(
    retrievalProcessing,
    fallbackNarratives: retrievalNarratives,
  );
  if (retrievalBlock != null) {
    final answerIndex = blocks.indexWhere(
      (block) => block.stageId == JourneyStageId.answer,
    );
    if (answerIndex >= 0) {
      blocks.insert(answerIndex, retrievalBlock);
    } else {
      blocks.add(retrievalBlock);
    }
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

RetrievalProcessingSnapshot _normalizeRetrievalProcessing(
  RetrievalProcessingSnapshot retrievalProcessing,
  AssistantJourney journey,
) {
  final acceptedReferences = retrievalProcessing.acceptedReferences.isNotEmpty
      ? retrievalProcessing.acceptedReferences
      : _fallbackAcceptedReferences(journey);
  final acceptedDocumentCount = retrievalProcessing.acceptedDocumentCount > 0
      ? retrievalProcessing.acceptedDocumentCount
      : acceptedReferences.length;
  final processedDocumentCount = retrievalProcessing.processedDocumentCount > 0
      ? retrievalProcessing.processedDocumentCount
      : acceptedDocumentCount;
  return RetrievalProcessingSnapshot(
    processedDocumentCount: processedDocumentCount,
    acceptedDocumentCount: acceptedDocumentCount,
    processingSummary: _sanitizeJourneyText(
      retrievalProcessing.processingSummary,
    ),
    expansionReason: _sanitizeJourneyText(retrievalProcessing.expansionReason),
    acceptedReferences: acceptedReferences,
  );
}

List<RetrievalProcessingReference> _fallbackAcceptedReferences(
  AssistantJourney journey,
) {
  final byUrl = <String, RetrievalProcessingReference>{};
  for (final reference in journey.referenceSummary.references) {
    final url = reference.url.trim();
    final title = reference.title.trim();
    if (url.isEmpty || title.isEmpty) continue;
    byUrl[url] = RetrievalProcessingReference(
      title: title,
      url: url,
      source: reference.source.trim(),
    );
  }
  if (byUrl.isNotEmpty) {
    return byUrl.values.toList(growable: false);
  }
  for (final entry in journey.entries) {
    if (entry.stageId != JourneyStageId.search &&
        entry.stageId != JourneyStageId.verify) {
      continue;
    }
    for (final reference in entry.references) {
      final url = reference.url.trim();
      final title = reference.title.trim();
      if (url.isEmpty || title.isEmpty) continue;
      byUrl[url] = RetrievalProcessingReference(
        title: title,
        url: url,
        source: reference.source.trim(),
      );
    }
  }
  return byUrl.values.toList(growable: false);
}

AssistantJourneyBlockViewModel? _buildRetrievalProcessingBlock(
  RetrievalProcessingSnapshot retrievalProcessing, {
  Iterable<String> fallbackNarratives = const <String>[],
}) {
  final references = retrievalProcessing.acceptedReferences
      .map(
        (reference) => AssistantJourneyReferenceViewModel(
          title: reference.title.trim(),
          url: reference.url.trim(),
          source: reference.source.trim(),
        ),
      )
      .where(
        (reference) => reference.title.isNotEmpty && reference.url.isNotEmpty,
      )
      .toList(growable: false);
  final processedCount = retrievalProcessing.processedDocumentCount;
  final acceptedCount = retrievalProcessing.acceptedDocumentCount > 0
      ? retrievalProcessing.acceptedDocumentCount
      : references.length;
  final detailParts = _distinctNonEmpty(<String>[
    retrievalProcessing.processingSummary,
    retrievalProcessing.expansionReason,
    ...fallbackNarratives,
  ]);
  if (!_hasRetrievalProcessingSignal(retrievalProcessing) &&
      references.isEmpty &&
      detailParts.isEmpty) {
    return null;
  }
  final effectiveProcessedCount = processedCount > 0
      ? processedCount
      : acceptedCount;
  return AssistantJourneyBlockViewModel(
    kind: AssistantJourneyBlockKind.searchSummary,
    stageId: JourneyStageId.search,
    headline: _retrievalBlockHeadline(
      processedCount: effectiveProcessedCount,
      acceptedCount: acceptedCount,
    ),
    detail: detailParts.join('\n'),
    references: references,
  );
}

String _retrievalBlockHeadline({
  required int processedCount,
  required int acceptedCount,
}) {
  if (processedCount > 0 && acceptedCount > 0) {
    return '处理$processedCount篇文档，接纳$acceptedCount篇如下';
  }
  if (acceptedCount > 0) {
    return '接纳$acceptedCount篇资料如下';
  }
  if (processedCount > 0) {
    return '处理$processedCount篇文档';
  }
  return '';
}

bool _hasRetrievalProcessingSignal(
  RetrievalProcessingSnapshot retrievalProcessing,
) {
  return retrievalProcessing.processedDocumentCount > 0 ||
      retrievalProcessing.acceptedDocumentCount > 0 ||
      retrievalProcessing.processingSummary.isNotEmpty ||
      retrievalProcessing.expansionReason.isNotEmpty ||
      retrievalProcessing.acceptedReferences.isNotEmpty;
}

JourneyStageId _displayStageId(JourneyStageId stageId) {
  switch (stageId) {
    case JourneyStageId.verify:
      return JourneyStageId.search;
    default:
      return stageId;
  }
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
  if (_looksLikeRomanizedQueryFragment(normalized)) return '';
  if (RegExp(r'\{\{[^{}]+\}\}').hasMatch(normalized)) return '';
  if (AssistantContentFilters.isJsonEnvelope(normalized) ||
      AssistantContentFilters.isDegradedText(normalized) ||
      AssistantDisplayTextResolver.containsInternalPlannerNarrationFragment(
        normalized,
      ) ||
      AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
        normalized,
      ) ||
      AssistantDisplayTextResolver.containsTechnicalFailureFragment(
        normalized,
      ) ||
      AssistantDisplayTextResolver.containsInternalProcessFragment(
        normalized,
      ) ||
      normalized.contains('模型调用') ||
      normalized.toLowerCase().contains('token')) {
    return '';
  }
  if (normalized.startsWith('{') || normalized.startsWith('[')) return '';
  return normalized.trim();
}

bool _looksLikeRomanizedQueryFragment(String text) {
  return RegExp(
    r'^[a-z]+(?:\s+[a-z]+){1,7}$',
    caseSensitive: false,
  ).hasMatch(text.trim());
}

String _firstNonEmpty(Iterable<String> values) {
  for (final value in values) {
    if (value.trim().isNotEmpty) {
      return value.trim();
    }
  }
  return '';
}

int _maxInt(Iterable<int> values) {
  var current = 0;
  for (final value in values) {
    if (value > current) {
      current = value;
    }
  }
  return current;
}

List<String> _distinctNonEmpty(Iterable<String> values) {
  final seen = <String>{};
  final result = <String>[];
  for (final value in values) {
    final trimmed = value.trim();
    if (trimmed.isEmpty || !seen.add(trimmed)) {
      continue;
    }
    result.add(trimmed);
  }
  return result;
}
