import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
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
    this.referenceLabel = '',
    this.references = const <AssistantJourneyReferenceViewModel>[],
  });

  final AssistantJourneyBlockKind kind;
  final JourneyStageId stageId;
  final String headline;
  final String detail;
  final String referenceLabel;
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
  final summary = _sanitizeStageNarrative(
    stage?.summary ?? '',
    stageId: stageId,
  );
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
      _sanitizeStageNarrative(secondaryStage?.summary ?? '', stageId: stageId),
      _sanitizeStageNarrative(primaryStage?.summary ?? '', stageId: stageId),
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
  final orderedEntries = List<AssistantJourneyEntry>.of(journey.entries)
    ..sort((a, b) => a.order.compareTo(b.order));
  for (final entry in orderedEntries) {
    final block = _buildBlockFromEntry(entry);
    if (block == null) {
      continue;
    }
    _appendOrMergeSequentialBlock(blocks, block);
  }
  final stageById = <JourneyStageId, AssistantJourneyStageViewModel>{
    for (final stage in stages) stage.stageId: stage,
  };
  _appendFallbackStageBlock(
    blocks,
    stageId: JourneyStageId.analyze,
    candidate: stageById[JourneyStageId.analyze]?.summary ?? '',
  );
  _appendFallbackStageBlock(
    blocks,
    stageId: JourneyStageId.search,
    candidate: stageById[JourneyStageId.search]?.summary ?? '',
    skipLowSignal: true,
  );
  _appendFallbackStageBlock(
    blocks,
    stageId: JourneyStageId.search,
    candidate: retrievalProcessing.processingSummary,
    skipLowSignal: true,
  );
  _appendFallbackStageBlock(
    blocks,
    stageId: JourneyStageId.search,
    candidate: retrievalProcessing.expansionReason,
    skipLowSignal: true,
  );
  _appendFallbackStageBlock(
    blocks,
    stageId: JourneyStageId.answer,
    candidate: stageById[JourneyStageId.answer]?.summary ?? '',
  );
  _mergeRetrievalProcessingIntoBlocks(blocks, retrievalProcessing);
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

AssistantJourneyBlockViewModel? _buildBlockFromEntry(AssistantJourneyEntry entry) {
  final stageId = _displayStageId(entry.stageId);
  final visibleLines = _filterStageNarrativeLines(
    stageId,
    _narrativeLinesForEntry(entry, stageId: stageId),
  );
  final references = _referenceViewModels(entry.references);
  if (visibleLines.isEmpty && references.isEmpty) {
    return null;
  }
  return AssistantJourneyBlockViewModel(
    kind: references.isNotEmpty
        ? AssistantJourneyBlockKind.searchSummary
        : AssistantJourneyBlockKind.narrative,
    stageId: stageId,
    headline: visibleLines.isNotEmpty ? visibleLines.first : '',
    detail: visibleLines.skip(1).join('\n'),
    referenceLabel: references.isNotEmpty
        ? _retrievalBlockHeadline(
            processedCount: 0,
            acceptedCount: references.length,
          )
        : '',
    references: references,
  );
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
    if (headline.isNotEmpty) headline,
    if (detail.isNotEmpty && detail != headline)
      ...detail
          .split('\n')
          .map((line) => line.trim())
          .where((line) => line.isNotEmpty),
  ]);
}

void _appendOrMergeSequentialBlock(
  List<AssistantJourneyBlockViewModel> blocks,
  AssistantJourneyBlockViewModel incoming,
) {
  if (blocks.isEmpty) {
    blocks.add(incoming);
    return;
  }
  final last = blocks.last;
  if (last.stageId != incoming.stageId) {
    blocks.add(incoming);
    return;
  }
  blocks[blocks.length - 1] = _mergeJourneyBlocks(last, incoming);
}

AssistantJourneyBlockViewModel _mergeJourneyBlocks(
  AssistantJourneyBlockViewModel current,
  AssistantJourneyBlockViewModel incoming,
) {
  final mergedLines = _distinctNonEmpty(<String>[
    ..._blockLines(current),
    ..._blockLines(incoming),
  ]);
  final mergedReferences = _mergeBlockReferences(
    current.references,
    incoming.references,
  );
  final mergedReferenceLabel = incoming.referenceLabel.trim().isNotEmpty
      ? incoming.referenceLabel.trim()
      : (current.referenceLabel.trim().isNotEmpty
            ? current.referenceLabel.trim()
            : (mergedReferences.isNotEmpty
                  ? _retrievalBlockHeadline(
                      processedCount: 0,
                      acceptedCount: mergedReferences.length,
                    )
                  : ''));
  return AssistantJourneyBlockViewModel(
    kind: mergedReferences.isNotEmpty
        ? AssistantJourneyBlockKind.searchSummary
        : current.kind,
    stageId: current.stageId,
    headline: mergedLines.isNotEmpty ? mergedLines.first : '',
    detail: mergedLines.skip(1).join('\n'),
    referenceLabel: mergedReferenceLabel,
    references: mergedReferences,
  );
}

List<String> _blockLines(AssistantJourneyBlockViewModel block) {
  return _distinctNonEmpty(<String>[
    if (block.headline.trim().isNotEmpty) block.headline.trim(),
    ...block.detail
        .split('\n')
        .map((line) => line.trim())
        .where((line) => line.isNotEmpty),
  ]);
}

List<AssistantJourneyReferenceViewModel> _mergeBlockReferences(
  List<AssistantJourneyReferenceViewModel> first,
  List<AssistantJourneyReferenceViewModel> second,
) {
  final seen = <String>{};
  final merged = <AssistantJourneyReferenceViewModel>[];
  for (final candidate in <AssistantJourneyReferenceViewModel>[
    ...first,
    ...second,
  ]) {
    final key = '${candidate.url}::${candidate.title}';
    if (!seen.add(key)) {
      continue;
    }
    merged.add(candidate);
  }
  return merged;
}

void _appendFallbackStageBlock(
  List<AssistantJourneyBlockViewModel> blocks, {
  required JourneyStageId stageId,
  required String candidate,
  bool skipLowSignal = false,
}) {
  if (blocks.any((block) => block.stageId == stageId)) {
    return;
  }
  final sanitized = _sanitizeStageNarrative(candidate, stageId: stageId);
  if (sanitized.isEmpty) {
    return;
  }
  if (skipLowSignal && _isLowSignalStageNarrative(stageId, sanitized)) {
    return;
  }
  _insertBlockByStageOrder(
    blocks,
    AssistantJourneyBlockViewModel(
      kind: AssistantJourneyBlockKind.narrative,
      stageId: stageId,
      headline: sanitized,
    ),
  );
}

void _mergeRetrievalProcessingIntoBlocks(
  List<AssistantJourneyBlockViewModel> blocks,
  RetrievalProcessingSnapshot retrievalProcessing,
) {
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
  final acceptedCount = retrievalProcessing.acceptedDocumentCount > 0
      ? retrievalProcessing.acceptedDocumentCount
      : references.length;
  final processedCount = retrievalProcessing.processedDocumentCount > 0
      ? retrievalProcessing.processedDocumentCount
      : acceptedCount;
  final referenceLabel =
      (processedCount > 0 || acceptedCount > 0 || references.isNotEmpty)
      ? _retrievalBlockHeadline(
          processedCount: processedCount,
          acceptedCount: acceptedCount,
        )
      : '';
  if (referenceLabel.isEmpty && references.isEmpty) {
    return;
  }
  final searchIndex = blocks.lastIndexWhere(
    (block) => block.stageId == JourneyStageId.search,
  );
  final retrievalBlock = AssistantJourneyBlockViewModel(
    kind: AssistantJourneyBlockKind.searchSummary,
    stageId: JourneyStageId.search,
    referenceLabel: referenceLabel,
    references: references,
  );
  if (searchIndex < 0) {
    _insertBlockByStageOrder(blocks, retrievalBlock);
    return;
  }
  blocks[searchIndex] = _mergeJourneyBlocks(blocks[searchIndex], retrievalBlock);
}

void _insertBlockByStageOrder(
  List<AssistantJourneyBlockViewModel> blocks,
  AssistantJourneyBlockViewModel block,
) {
  final insertAt = blocks.indexWhere(
    (existing) => _stageDisplayOrder(existing.stageId) > _stageDisplayOrder(block.stageId),
  );
  if (insertAt < 0) {
    blocks.add(block);
    return;
  }
  blocks.insert(insertAt, block);
}

int _stageDisplayOrder(JourneyStageId stageId) {
  switch (stageId) {
    case JourneyStageId.analyze:
      return 0;
    case JourneyStageId.search:
    case JourneyStageId.verify:
      return 1;
    case JourneyStageId.answer:
      return 2;
    case JourneyStageId.unknown:
      return 3;
  }
}

bool _isLowSignalRetrievalNarrative(String text) {
  final normalized = text.trim();
  return normalized == '已完成资料筛选并进入成答' || normalized == '已完成当前轮资料筛选';
}

String _sanitizeStageNarrative(String raw, {required JourneyStageId stageId}) {
  final normalized = stageId == JourneyStageId.analyze
      ? _sanitizeAnalyzeJourneyText(raw)
      : _sanitizeJourneyText(raw, stageHint: stageId.name);
  final sanitized = _stripLowSignalStagePrefix(
    stageId == JourneyStageId.search
        ? _normalizeSearchNarrative(normalized)
        : normalized,
    stageId: stageId,
  );
  if (sanitized.isEmpty || _isLowSignalStageNarrative(stageId, sanitized)) {
    return '';
  }
  return sanitized;
}

String _sanitizeAnalyzeJourneyText(String raw) {
  final normalized = AssistantDisplayTextResolver
      .normalizeUserFacingProcessNarration(raw, stageHint: 'analyze');
  if (normalized.isEmpty) return '';
  if (_looksLikeRomanizedQueryFragment(normalized)) return '';
  return normalized.trim();
}

String _normalizeSearchNarrative(String raw) {
  if (raw.trim().isEmpty) {
    return '';
  }
  final lines = raw
      .replaceAll('\r\n', '\n')
      .split('\n')
      .map(_normalizeSearchNarrativeLine)
      .where((line) => line.isNotEmpty)
      .toList(growable: false);
  return lines.join('\n').trim();
}

String _normalizeSearchNarrativeLine(String rawLine) {
  final line = rawLine.trim();
  if (line.isEmpty) {
    return '';
  }
  if (line.startsWith('检索词：')) {
    final focus = _compactSearchFocusLabel(line.substring(4).trim());
    return focus.isEmpty ? '' : '我会先核对$focus。';
  }
  if (line.startsWith('- ')) {
    final focus = _compactSearchFocusLabel(line.substring(2).trim());
    return focus.isEmpty ? '' : '- $focus';
  }
  return line;
}

String _compactSearchFocusLabel(String raw) {
  final normalized = raw.trim();
  if (normalized.isEmpty) {
    return '';
  }
  final prefix = normalized.split('：').first.trim().replaceAll('｜', ' · ');
  if (prefix.isEmpty) {
    return '';
  }
  if (prefix == normalized && normalized.length > 24) {
    return '';
  }
  return prefix;
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
          .replaceFirst(RegExp(r'^已经有一批能支撑判断的信息了[^\n。！？!?]*[。！？!?]?\s*'), '');
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
    lines.where((line) => !_isLowSignalStageNarrative(stageId, line.trim())),
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

String _sanitizeJourneyText(String raw, {String stageHint = ''}) {
  final normalized = AssistantDisplayTextResolver
      .normalizeUserFacingProcessNarration(raw, stageHint: stageHint);
  if (normalized.isEmpty) return '';
  if (_looksLikeRomanizedQueryFragment(normalized)) return '';
  if (normalized.contains('模型调用') || normalized.toLowerCase().contains('token')) {
    return '';
  }
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
