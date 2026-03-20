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
  bool allowAnswerStage = true,
  Map<String, dynamic> usageStats = const <String, dynamic>{},
  int elapsedMs = 0,
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
}) {
  final effectiveJourney = _maskPrematureAnswerJourney(
    journey,
    isRunning: isRunning,
    allowAnswerStage: allowAnswerStage,
  );
  final timelineJourney = buildAssistantUiProcessTimeline(effectiveJourney);
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

AssistantJourney _maskPrematureAnswerJourney(
  AssistantJourney journey, {
  required bool isRunning,
  required bool allowAnswerStage,
}) {
  if (!isRunning ||
      allowAnswerStage ||
      journey.isEmpty ||
      journey.readiness.finalAnswerReady) {
    return journey;
  }
  var changed = false;
  final stages = <AssistantJourneyStage>[
    for (final stage in journey.stages)
      if (stage.stageId == JourneyStageId.answer)
        () {
          changed = true;
          return AssistantJourneyStage(
            stageId: stage.stageId,
            status: JourneyStageStatus.pending,
            order: stage.order,
            summary: '',
            referenceCount: stage.referenceCount,
          );
        }()
      else
        stage,
  ];
  final entries = journey.entries
      .where((entry) => entry.stageId != JourneyStageId.answer)
      .toList(growable: false);
  if (entries.length != journey.entries.length) {
    changed = true;
  }
  if (!changed) {
    return journey;
  }
  return AssistantJourney(
    stages: stages,
    entries: entries,
    summary: '',
    referenceSummary: journey.referenceSummary,
    readiness: journey.readiness,
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
  final blocks = <AssistantJourneyBlockViewModel>[];
  final analyzeLines = <String>[];
  final searchLines = <String>[];
  final answerLines = <String>[];
  final fallbackSearchReferences = <AssistantJourneyReferenceViewModel>[];
  final fallbackSearchReferenceKeys = <String>{};
  final orderedEntries = List<AssistantJourneyEntry>.of(journey.entries)
    ..sort((a, b) => a.order.compareTo(b.order));
  for (final entry in orderedEntries) {
    final displayStageId = _displayStageId(entry.stageId);
    final lines = _narrativeLinesForEntry(entry, stageId: displayStageId);
    final references = _referenceViewModels(entry.references);
    switch (displayStageId) {
      case JourneyStageId.analyze:
        _appendDistinctLines(analyzeLines, lines);
        break;
      case JourneyStageId.search:
        _appendDistinctLines(searchLines, lines);
        _appendDistinctReferences(
          fallbackSearchReferences,
          fallbackSearchReferenceKeys,
          references,
        );
        break;
      case JourneyStageId.answer:
        _appendDistinctLines(answerLines, lines);
        break;
      default:
        break;
    }
  }
  final stageById = <JourneyStageId, AssistantJourneyStageViewModel>{
    for (final stage in stages) stage.stageId: stage,
  };
  if (analyzeLines.isEmpty) {
    _appendFallbackStageSummary(
      analyzeLines,
      stageById[JourneyStageId.analyze]?.summary ?? '',
      stageId: JourneyStageId.analyze,
    );
  }
  if (searchLines.isEmpty) {
    _appendFallbackStageSummary(
      searchLines,
      stageById[JourneyStageId.search]?.summary ?? '',
      stageId: JourneyStageId.search,
      skipLowSignal: true,
    );
    _appendFallbackStageSummary(
      searchLines,
      retrievalProcessing.processingSummary,
      stageId: JourneyStageId.search,
      skipLowSignal: true,
    );
  }
  if (answerLines.isEmpty) {
    _appendFallbackStageSummary(
      answerLines,
      stageById[JourneyStageId.answer]?.summary ?? '',
      stageId: JourneyStageId.answer,
    );
  }
  _appendFallbackStageSummary(
    searchLines,
    retrievalProcessing.expansionReason,
    stageId: JourneyStageId.search,
    skipLowSignal: true,
  );

  final analyzeBlock = _buildNarrativeStageBlock(
    stageId: JourneyStageId.analyze,
    lines: analyzeLines,
  );
  if (analyzeBlock != null) {
    blocks.add(analyzeBlock);
  }
  final searchNarrativeBlock = _buildNarrativeStageBlock(
    stageId: JourneyStageId.search,
    lines: searchLines,
  );
  if (searchNarrativeBlock != null) {
    blocks.add(searchNarrativeBlock);
  }
  final retrievalReferenceBlock = _buildRetrievalReferenceBlock(
    retrievalProcessing,
    fallbackReferences: fallbackSearchReferences,
  );
  if (retrievalReferenceBlock != null) {
    blocks.add(retrievalReferenceBlock);
  }
  final answerBlock = _buildNarrativeStageBlock(
    stageId: JourneyStageId.answer,
    lines: answerLines,
  );
  if (answerBlock != null) {
    blocks.add(answerBlock);
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

List<String> _narrativeLinesForEntry(
  AssistantJourneyEntry entry, {
  required JourneyStageId stageId,
}) {
  final headline = _sanitizeStageNarrative(entry.headline, stageId: stageId);
  final detail = _sanitizeStageNarrative(entry.detail, stageId: stageId);
  if (headline.isEmpty && detail.isEmpty) {
    return const <String>[];
  }
  return _distinctNonEmpty(<String>[
    headline,
    if (detail.isNotEmpty && detail != headline) detail,
  ]);
}

List<AssistantJourneyReferenceViewModel> _referenceViewModels(
  List<AssistantJourneyReference> references,
) {
  return references
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
}

void _appendDistinctLines(List<String> target, Iterable<String> candidates) {
  for (final candidate in candidates) {
    final trimmed = candidate.trim();
    if (trimmed.isEmpty || target.contains(trimmed)) {
      continue;
    }
    target.add(trimmed);
  }
}

void _appendDistinctReferences(
  List<AssistantJourneyReferenceViewModel> target,
  Set<String> seenKeys,
  Iterable<AssistantJourneyReferenceViewModel> candidates,
) {
  for (final candidate in candidates) {
    final key = '${candidate.url}::${candidate.title}';
    if (!seenKeys.add(key)) {
      continue;
    }
    target.add(candidate);
  }
}

void _appendFallbackStageSummary(
  List<String> target,
  String candidate, {
  required JourneyStageId stageId,
  bool skipLowSignal = false,
}) {
  final sanitized = _sanitizeStageNarrative(candidate, stageId: stageId);
  if (sanitized.isEmpty) {
    return;
  }
  if (skipLowSignal && _isLowSignalStageNarrative(stageId, sanitized)) {
    return;
  }
  if (target.contains(sanitized)) {
    return;
  }
  target.add(sanitized);
}

AssistantJourneyBlockViewModel? _buildNarrativeStageBlock({
  required JourneyStageId stageId,
  required List<String> lines,
}) {
  final visibleLines = _filterStageNarrativeLines(stageId, lines);
  if (visibleLines.isEmpty) {
    return null;
  }
  return AssistantJourneyBlockViewModel(
    kind: AssistantJourneyBlockKind.narrative,
    stageId: stageId,
    headline: visibleLines.first,
    detail: visibleLines.skip(1).join('\n'),
  );
}

AssistantJourneyBlockViewModel? _buildRetrievalReferenceBlock(
  RetrievalProcessingSnapshot retrievalProcessing, {
  required List<AssistantJourneyReferenceViewModel> fallbackReferences,
}) {
  final references = retrievalProcessing.acceptedReferences.isNotEmpty
      ? retrievalProcessing.acceptedReferences
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
            .toList(growable: false)
      : fallbackReferences;
  final acceptedCount = retrievalProcessing.acceptedDocumentCount > 0
      ? retrievalProcessing.acceptedDocumentCount
      : references.length;
  final processedCount = retrievalProcessing.processedDocumentCount > 0
      ? retrievalProcessing.processedDocumentCount
      : acceptedCount;
  if (processedCount <= 0 && acceptedCount <= 0 && references.isEmpty) {
    return null;
  }
  return AssistantJourneyBlockViewModel(
    kind: AssistantJourneyBlockKind.searchSummary,
    stageId: JourneyStageId.search,
    headline: _retrievalBlockHeadline(
      processedCount: processedCount,
      acceptedCount: acceptedCount,
    ),
    references: references,
  );
}

bool _isLowSignalRetrievalNarrative(String text) {
  final normalized = text.trim();
  return normalized == '已完成资料筛选并进入成答' || normalized == '已完成当前轮资料筛选';
}

String _sanitizeStageNarrative(
  String raw, {
  required JourneyStageId stageId,
}) {
  final sanitized = _stripLowSignalStagePrefix(
    _sanitizeJourneyText(raw),
    stageId: stageId,
  );
  if (sanitized.isEmpty || _isLowSignalStageNarrative(stageId, sanitized)) {
    return '';
  }
  return sanitized;
}

String _stripLowSignalStagePrefix(
  String text, {
  required JourneyStageId stageId,
}) {
  var normalized = text.trim();
  if (normalized.isEmpty) {
    return '';
  }
  switch (stageId) {
    case JourneyStageId.analyze:
      normalized = normalized.replaceFirst(
        RegExp(r'^正在获取[^\n。！？!?]*[。！？!?]?\s*'),
        '',
      );
      break;
    case JourneyStageId.search:
      normalized = normalized
          .replaceFirst(
            RegExp(r'^正在(?:交叉核对|搜索|查询|检索)[^\n。！？!?]*[。！？!?]?\s*'),
            '',
          )
          .replaceFirst(RegExp(r'^已找到\s*\d+\s*篇相关资料[。！？!?]?\s*'), '')
          .replaceFirst(
            RegExp(r'^已经有一批能支撑判断的信息了[^\n。！？!?]*[。！？!?]?\s*'),
            '',
          );
      break;
    case JourneyStageId.answer:
      normalized = normalized.replaceFirst(
        RegExp(r'^我开始整理[^\n。！？!?]*[。！？!?]\s*'),
        '',
      );
      break;
    default:
      break;
  }
  return normalized.trim();
}

List<String> _filterStageNarrativeLines(
  JourneyStageId stageId,
  Iterable<String> lines,
) {
  return _distinctNonEmpty(
    lines.where(
      (line) => !_isLowSignalStageNarrative(stageId, line.trim()),
    ),
  );
}

bool _isLowSignalStageNarrative(JourneyStageId stageId, String text) {
  final normalized = text.trim();
  switch (stageId) {
    case JourneyStageId.analyze:
      return RegExp(r'^正在获取.+位置').hasMatch(normalized);
    case JourneyStageId.search:
      return _isLowSignalRetrievalNarrative(normalized) ||
          RegExp(r'^正在(?:交叉核对|搜索|查询|检索).+').hasMatch(normalized) ||
          RegExp(r'^已找到\s*\d+\s*篇相关资料$').hasMatch(normalized) ||
          RegExp(r'^已经有一批能支撑判断的信息了.+').hasMatch(normalized);
    case JourneyStageId.answer:
      return normalized == '已满足成答条件' ||
          RegExp(r'^我开始整理.+关键信息').hasMatch(normalized);
    default:
      return false;
  }
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
  final processingSummary =
      retrievalProcessing.processingSummary.trim().isNotEmpty
      ? retrievalProcessing.processingSummary
      : _fallbackRetrievalProcessingSummary(journey);
  return RetrievalProcessingSnapshot(
    processedDocumentCount: processedDocumentCount,
    acceptedDocumentCount: acceptedDocumentCount,
    processingSummary: _sanitizeJourneyText(processingSummary),
    expansionReason: _sanitizeJourneyText(retrievalProcessing.expansionReason),
    acceptedReferences: acceptedReferences,
  );
}

String _fallbackRetrievalProcessingSummary(AssistantJourney journey) {
  for (final entry in journey.entries.reversed) {
    if (entry.stageId != JourneyStageId.search &&
        entry.stageId != JourneyStageId.verify) {
      continue;
    }
    final detail = _sanitizeJourneyText(entry.detail);
    if (detail.isNotEmpty) {
      return detail;
    }
    final headline = _sanitizeJourneyText(entry.headline);
    if (headline.isNotEmpty) {
      return headline;
    }
  }
  for (final stage in journey.stages.reversed) {
    if (stage.stageId != JourneyStageId.search &&
        stage.stageId != JourneyStageId.verify) {
      continue;
    }
    final summary = _sanitizeJourneyText(stage.summary);
    if (summary.isNotEmpty) {
      return summary;
    }
  }
  return '';
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
      AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
        AssistantDisplayTextResolver.stripRomanizedQueryLeakSentences(raw),
      );
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
