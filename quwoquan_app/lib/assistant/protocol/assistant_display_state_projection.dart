import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

const String assistantDisplayStateField = 'displayState';

class _ProcessNarrativeParts {
  const _ProcessNarrativeParts({this.title = '', this.body = ''});

  final String title;
  final String body;

  bool get hasVisibleText => title.trim().isNotEmpty || body.trim().isNotEmpty;
}

bool hasAssistantDisplayState(AssistantDisplayState state) {
  return state.process.blocks.isNotEmpty ||
      state.answer.blocks.isNotEmpty ||
      state.process.summary.trim().isNotEmpty ||
      state.answer.summary.trim().isNotEmpty;
}

AssistantDisplayState buildAssistantDisplayState({
  AssistantDisplayState explicitState = const AssistantDisplayState(),
  List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
  RunArtifactsUnderstandingSnapshot understandingSnapshot =
      const RunArtifactsUnderstandingSnapshot(),
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
  RunArtifactsAnswerProcessing answerProcessing =
      const RunArtifactsAnswerProcessing(),
  String answerMarkdown = '',
  String answerPlainText = '',
  bool finalAnswerReady = false,
}) {
  final normalizedTimeline = normalizeProcessTimeline(processTimeline);
  final process = _resolveProcessDisplayState(
    explicit: explicitState.process,
    processTimeline: normalizedTimeline,
    understandingSnapshot: understandingSnapshot,
    retrievalProcessing: retrievalProcessing,
    answerProcessing: answerProcessing,
    finalAnswerReady: finalAnswerReady,
  );
  final answer = _resolveAnswerDisplayState(
    explicit: explicitState.answer,
    answerMarkdown: answerMarkdown,
    answerPlainText: answerPlainText,
    answerSummary: answerProcessing.readinessSummary,
  );
  return AssistantDisplayState(process: process, answer: answer);
}

AssistantDisplayState resolveAssistantDisplayStateFromRunArtifacts(
  RunArtifacts runArtifacts,
) {
  return buildAssistantDisplayState(
    explicitState: runArtifacts.displayState,
    processTimeline: runArtifacts.processTimeline,
    understandingSnapshot: runArtifacts.understandingSnapshot,
    retrievalProcessing: runArtifacts.retrievalProcessing,
    answerProcessing: runArtifacts.answerProcessing,
    answerMarkdown: runArtifacts.displayMarkdown,
    answerPlainText: runArtifacts.displayPlainText,
    finalAnswerReady: runArtifacts.displayState.process.finalAnswerReady,
  );
}

AssistantDisplayState parseAssistantDisplayStateFromMap(
  Map<String, dynamic>? raw,
) {
  if (raw == null || raw.isEmpty) {
    return const AssistantDisplayState();
  }
  return AssistantDisplayState.fromJson(raw);
}

String renderAnswerBlocksToMarkdown(List<AssistantAnswerDisplayBlock> blocks) {
  final out = <String>[];
  for (final block in blocks) {
    final rendered = _renderAnswerBlockToMarkdown(block);
    if (rendered.isNotEmpty) {
      out.add(rendered);
    }
  }
  return _normalizeMarkdownLeaf(out.join('\n\n'));
}

String renderAnswerBlocksToPlainText(List<AssistantAnswerDisplayBlock> blocks) {
  final out = <String>[];
  for (final block in blocks) {
    final rendered = _renderAnswerBlockToPlainText(block);
    if (rendered.isNotEmpty) {
      out.add(rendered);
    }
  }
  return _normalizePlainText(out.join('\n\n'));
}

AssistantProcessDisplayState _resolveProcessDisplayState({
  required AssistantProcessDisplayState explicit,
  required List<ProcessTimelineFrame> processTimeline,
  required RunArtifactsUnderstandingSnapshot understandingSnapshot,
  required RetrievalProcessingSnapshot retrievalProcessing,
  required RunArtifactsAnswerProcessing answerProcessing,
  required bool finalAnswerReady,
}) {
  final explicitBlocks = explicit.blocks
      .where(_hasVisibleProcessBlock)
      .toList(growable: false);
  final explicitSummary = explicit.summary.trim();
  final activeStepId = explicit.activeStepId != ProcessStepId.unknown
      ? explicit.activeStepId
      : _resolveActiveStepId(processTimeline);
  final derivedBlocks = <AssistantProcessDisplayBlock>[
    ..._buildUnderstandingBlocks(processTimeline, understandingSnapshot),
    ..._buildRetrievalBlocks(
      processTimeline,
      retrievalProcessing,
      answerProcessing,
    ),
  ];
  final mergedBlocks = _mergeProcessBlocks(
    preferred: explicitBlocks,
    fallback: derivedBlocks,
  );
  return AssistantProcessDisplayState(
    activeStepId: activeStepId,
    summary: _resolveProcessSummary(
      explicitBlocks: mergedBlocks,
      processTimeline: processTimeline,
      fallbackSummary: explicitSummary,
    ),
    blocks: mergedBlocks,
    finalAnswerReady: explicit.finalAnswerReady || finalAnswerReady,
  );
}

AssistantAnswerDisplayState _resolveAnswerDisplayState({
  required AssistantAnswerDisplayState explicit,
  required String answerMarkdown,
  required String answerPlainText,
  required String answerSummary,
}) {
  final explicitBlocks = explicit.blocks
      .where(_hasVisibleAnswerBlock)
      .toList(growable: false);
  final markdown = _normalizeMarkdownLeaf(answerMarkdown);
  if (explicitBlocks.isNotEmpty ||
      (explicit.summary.trim().isNotEmpty &&
          markdown.isEmpty &&
          _normalizePlainText(answerPlainText).isEmpty)) {
    return AssistantAnswerDisplayState(
      summary: explicit.summary.trim().isNotEmpty
          ? explicit.summary.trim()
          : answerSummary.trim(),
      blocks: explicitBlocks,
    );
  }
  if (markdown.isNotEmpty) {
    return AssistantAnswerDisplayState(
      summary: answerSummary.trim(),
      blocks: <AssistantAnswerDisplayBlock>[
        AssistantAnswerDisplayBlock(
          blockId: 'answer_markdown',
          kind: DisplayBlockKind.markdown,
          body: markdown,
        ),
      ],
    );
  }
  final plainText = _normalizePlainText(answerPlainText);
  if (plainText.isEmpty) {
    return AssistantAnswerDisplayState(summary: answerSummary.trim());
  }
  return AssistantAnswerDisplayState(
    summary: answerSummary.trim(),
    blocks: <AssistantAnswerDisplayBlock>[
      AssistantAnswerDisplayBlock(
        blockId: 'answer_paragraph',
        kind: DisplayBlockKind.paragraph,
        body: plainText,
      ),
    ],
  );
}

List<AssistantProcessDisplayBlock> _buildUnderstandingBlocks(
  List<ProcessTimelineFrame> processTimeline,
  RunArtifactsUnderstandingSnapshot snapshot,
) {
  final frame = _frameForStep(processTimeline, ProcessStepId.understanding);
  final designFrame = _frameForStep(processTimeline, ProcessStepId.retrievalDesign);
  final status = frame?.status ?? JourneyStageStatus.pending;
  final summary = snapshot.userFacingSummary.trim();
  final resolutionItems = snapshot.resolutionItems
      .where(
        (item) =>
            item.visibleInUnderstanding &&
            (item.detail.trim().isNotEmpty ||
                item.resolvedValue.trim().isNotEmpty),
      )
      .toList(growable: false);
  final enriched = _enrichSummaryWithResolutions(summary, resolutionItems);
  final designSummary = designFrame?.headline.trim() ?? '';
  final designDetail = designFrame?.detail.trim() ?? '';
  if (summary.isEmpty &&
      resolutionItems.isEmpty &&
      designSummary.isEmpty &&
      designDetail.isEmpty) {
    return const <AssistantProcessDisplayBlock>[];
  }
  final narrative = _buildNarrativeParts(
    primary: enriched.isNotEmpty ? enriched : designSummary,
    secondary: _composeNarrativeSegments(<String>[
      if (enriched.isNotEmpty) designSummary,
      designDetail,
    ]),
  );
  if (!narrative.hasVisibleText) {
    return const <AssistantProcessDisplayBlock>[];
  }
  return <AssistantProcessDisplayBlock>[
    AssistantProcessDisplayBlock(
      blockId: 'understanding_narrative',
      stepId: ProcessStepId.understanding,
      status: status,
      kind: ProcessDisplayBlockKind.summary,
      title: narrative.title,
      body: narrative.body,
    ),
  ];
}

String _enrichSummaryWithResolutions(
  String summary,
  List<RunArtifactsUnderstandingResolutionItem> resolutionItems,
) {
  if (resolutionItems.isEmpty) return summary;
  final details = resolutionItems
      .map(
        (item) => item.detail.trim().isNotEmpty
            ? item.detail.trim()
            : item.resolvedValue.trim(),
      )
      .where((d) => d.isNotEmpty)
      .toList(growable: false);
  if (details.isEmpty) return summary;
  if (summary.isEmpty) {
    return details.join('；');
  }
  final uncovered = details
      .where((d) => !_summaryCoversDetail(summary, d))
      .toList(growable: false);
  if (uncovered.isEmpty) return summary;
  final base =
      summary.endsWith('。') || summary.endsWith('.')
          ? summary.substring(0, summary.length - 1)
          : summary;
  return '$base。${uncovered.join('；')}。';
}

bool _summaryCoversDetail(String summary, String detail) {
  final s = _stripSpacesAndPunctuation(summary);
  final d = _stripSpacesAndPunctuation(detail);
  if (d.length <= 6) return s.contains(d);
  final segments = _splitDetailSegments(d);
  for (final seg in segments) {
    if (seg.length >= 2 && seg.length <= 6 && s.contains(seg)) return true;
  }
  return false;
}

List<AssistantProcessDisplayBlock> _buildRetrievalBlocks(
  List<ProcessTimelineFrame> processTimeline,
  RetrievalProcessingSnapshot snapshot,
  RunArtifactsAnswerProcessing answerProcessing,
) {
  final frame = _frameForStep(
    processTimeline,
    ProcessStepId.retrievalProcessing,
  );
  final status = frame?.status ?? JourneyStageStatus.pending;
  final refs = snapshot.acceptedReferences
      .where(
        (item) =>
            item.title.trim().isNotEmpty ||
            item.url.trim().isNotEmpty ||
            item.source.trim().isNotEmpty,
      )
      .toList(growable: false);
  final summary = _resolveRetrievalSummary(frame: frame, snapshot: snapshot);
  final readinessNarrative = answerProcessing.readinessSummary.trim().isNotEmpty
      ? answerProcessing.readinessSummary.trim()
      : _fallbackRetrievalReadinessNarrative(
          snapshot: snapshot,
          answerProcessing: answerProcessing,
        );
  final continuationNarrative = _buildRetrievalContinuationNarrative(
    snapshot: snapshot,
    answerProcessing: answerProcessing,
    existingTexts: <String>[summary, readinessNarrative],
  );
  final narrative = _buildNarrativeParts(
    primary: summary.isNotEmpty ? summary : readinessNarrative,
    secondary: _composeNarrativeSegments(<String>[
      if (summary.isNotEmpty) readinessNarrative,
      continuationNarrative,
    ]),
  );
  final acceptedCount = snapshot.acceptedDocumentCount > 0
      ? snapshot.acceptedDocumentCount
      : refs.length;
  final processedCount = snapshot.processedDocumentCount > 0
      ? snapshot.processedDocumentCount
      : acceptedCount;
  final statsLabel = (processedCount > 0 || acceptedCount > 0)
      ? UITextConstants.assistantProcessReferenceDigestTemplate
            .replaceFirst('%s', processedCount.toString())
            .replaceFirst('%s', acceptedCount.toString())
      : '';
  final blocks = <AssistantProcessDisplayBlock>[];
  if (statsLabel.isNotEmpty || refs.isNotEmpty) {
    blocks.add(
      AssistantProcessDisplayBlock(
        blockId: 'retrieval_reference_stats',
        stepId: ProcessStepId.retrievalProcessing,
        status: status,
        kind: ProcessDisplayBlockKind.references,
        title: statsLabel,
        references: refs,
      ),
    );
  }
  if (narrative.hasVisibleText) {
    blocks.add(
      AssistantProcessDisplayBlock(
        blockId: 'retrieval_narrative',
        stepId: ProcessStepId.retrievalProcessing,
        status: status,
        kind: ProcessDisplayBlockKind.summary,
        title: narrative.title,
        body: narrative.body,
      ),
    );
  }
  return blocks;
}

String _buildRetrievalContinuationNarrative({
  required RetrievalProcessingSnapshot snapshot,
  required RunArtifactsAnswerProcessing answerProcessing,
  required Iterable<String> existingTexts,
}) {
  final segments = <String>[];
  final visibleKeyPoints = snapshot.selectedKeyPoints
      .map((item) => item.trim())
      .where(
        (item) => item.isNotEmpty &&
            !_isDuplicateNarrativeText(item, existing: existingTexts),
      )
      .toList(growable: false);
  if (visibleKeyPoints.isNotEmpty) {
    segments.add('我先把${visibleKeyPoints.join('、')}这些能直接支撑回答的点拎出来。');
  }
  final visibleKeyFacts = answerProcessing.keyFacts
      .map((item) => item.trim())
      .where(
        (item) => item.isNotEmpty &&
            !_isDuplicateNarrativeText(item, existing: existingTexts),
      )
      .toList(growable: false);
  if (visibleKeyFacts.isNotEmpty) {
    if (visibleKeyFacts.length == 1) {
      segments.add('回答会先围绕${visibleKeyFacts.first}展开。');
    } else {
      segments.add('回答会按${visibleKeyFacts.join('、')}的顺序展开。');
    }
  }
  return segments.join('\n');
}

String _fallbackRetrievalReadinessNarrative({
  required RetrievalProcessingSnapshot snapshot,
  required RunArtifactsAnswerProcessing answerProcessing,
}) {
  if (answerProcessing.keyFacts.isNotEmpty) {
    return '我会先把关键点排好顺序，再把回答写清楚。';
  }
  if (snapshot.selectedKeyPoints.isNotEmpty) {
    return '我先把能直接回答你的关键信息收拢起来。';
  }
  return '';
}

String _composeNarrativeSegments(Iterable<String> segments) {
  return segments
      .map((segment) => segment.trim())
      .where((segment) => segment.isNotEmpty)
      .join('\n');
}

_ProcessNarrativeParts _buildNarrativeParts({
  required String primary,
  String secondary = '',
}) {
  final normalizedPrimary = primary.trim();
  final normalizedSecondary = secondary.trim();
  if (normalizedPrimary.isEmpty && normalizedSecondary.isEmpty) {
    return const _ProcessNarrativeParts();
  }
  if (normalizedPrimary.isEmpty) {
    return _ProcessNarrativeParts(title: normalizedSecondary);
  }
  if (normalizedSecondary.isEmpty ||
      _isDuplicateNarrativeText(
        normalizedSecondary,
        existing: <String>[normalizedPrimary],
      )) {
    return _ProcessNarrativeParts(title: normalizedPrimary);
  }
  return _ProcessNarrativeParts(
    title: normalizedPrimary,
    body: normalizedSecondary,
  );
}

bool _isDuplicateNarrativeText(
  String candidate, {
  required Iterable<String> existing,
}) {
  final normalizedCandidate = _normalizeProcessTextKey(candidate);
  if (normalizedCandidate.isEmpty) {
    return true;
  }
  for (final text in existing) {
    final normalizedExisting = _normalizeProcessTextKey(text);
    if (normalizedExisting.isEmpty) {
      continue;
    }
    if (normalizedCandidate == normalizedExisting ||
        normalizedCandidate.contains(normalizedExisting) ||
        normalizedExisting.contains(normalizedCandidate)) {
      return true;
    }
  }
  return false;
}

String _normalizeProcessTextKey(String raw) {
  final trimmed = raw.trimLeft();
  final prefixes = <String>['我会先', '我先', '先'];
  var start = 0;
  for (final prefix in prefixes) {
    if (trimmed.startsWith(prefix)) {
      start = prefix.length;
      break;
    }
  }
  final buffer = StringBuffer();
  for (final rune in trimmed.substring(start).runes) {
    if (_isIgnorableNormalizationRune(rune)) {
      continue;
    }
    buffer.writeCharCode(rune);
  }
  return buffer.toString().trim().toLowerCase();
}

String _resolveRetrievalSummary({
  required ProcessTimelineFrame? frame,
  required RetrievalProcessingSnapshot snapshot,
}) {
  final frameHeadline = _firstProcessLine(frame?.headline ?? '');
  if (frameHeadline.isNotEmpty) {
    return frameHeadline;
  }
  final frameDetail = _firstProcessLine(frame?.detail ?? '');
  if (frameDetail.isNotEmpty) {
    return frameDetail;
  }
  return snapshot.processingSummary.trim();
}

ProcessTimelineFrame? _frameForStep(
  List<ProcessTimelineFrame> processTimeline,
  ProcessStepId stepId,
) {
  for (final frame in processTimeline) {
    if (frame.stepId == stepId) {
      return frame;
    }
  }
  return null;
}

String _firstProcessLine(String raw) {
  for (final line in raw.split('\n')) {
    final trimmed = line.trim();
    if (trimmed.isNotEmpty) {
      return trimmed;
    }
  }
  return '';
}

ProcessStepId _resolveActiveStepId(List<ProcessTimelineFrame> processTimeline) {
  for (final frame in processTimeline) {
    if (frame.status == JourneyStageStatus.active) {
      return frame.stepId;
    }
  }
  for (final frame in processTimeline) {
    if (frame.status == JourneyStageStatus.pending) {
      return frame.stepId;
    }
  }
  for (final frame in processTimeline.reversed) {
    if (frame.status != JourneyStageStatus.unknown) {
      return frame.stepId;
    }
  }
  return ProcessStepId.unknown;
}

String _resolveProcessSummary({
  required List<AssistantProcessDisplayBlock> explicitBlocks,
  required List<ProcessTimelineFrame> processTimeline,
  String fallbackSummary = '',
}) {
  if (fallbackSummary.trim().isNotEmpty) {
    return fallbackSummary.trim();
  }
  for (final block in explicitBlocks) {
    if (block.title.trim().isNotEmpty) {
      return block.title.trim();
    }
  }
  for (final frame in processTimeline) {
    final snapshotSummary = switch (frame.stepId) {
      ProcessStepId.understanding =>
        frame.understandingSnapshot.userFacingSummary,
      ProcessStepId.retrievalProcessing =>
        frame.retrievalProcessing.processingSummary,
      _ => '',
    }.trim();
    if (snapshotSummary.isNotEmpty) {
      return snapshotSummary;
    }
  }
  return '';
}

List<AssistantProcessDisplayBlock> _mergeProcessBlocks({
  required List<AssistantProcessDisplayBlock> preferred,
  required List<AssistantProcessDisplayBlock> fallback,
}) {
  final merged = <AssistantProcessDisplayBlock>[];
  final indexByKey = <String, int>{};

  String blockKey(AssistantProcessDisplayBlock block) {
    final blockId = _canonicalProcessBlockId(block.blockId);
    if (blockId.isNotEmpty) {
      return blockId;
    }
    return '${block.stepId.name}:${block.kind.name}:${block.title.trim()}';
  }

  for (final block in preferred) {
    final key = blockKey(block);
    if (_hasVisibleProcessBlock(block)) {
      indexByKey[key] = merged.length;
      merged.add(block);
    }
  }
  for (final block in fallback) {
    final key = blockKey(block);
    if (!_hasVisibleProcessBlock(block)) {
      continue;
    }
    final existingIndex = indexByKey[key];
    if (existingIndex == null) {
      indexByKey[key] = merged.length;
      merged.add(block);
      continue;
    }
    merged[existingIndex] = _mergeProcessBlock(
      existing: merged[existingIndex],
      incoming: block,
    );
  }
  return merged;
}

AssistantProcessDisplayBlock _mergeProcessBlock({
  required AssistantProcessDisplayBlock existing,
  required AssistantProcessDisplayBlock incoming,
}) {
  return AssistantProcessDisplayBlock(
    blockId: existing.blockId.trim().isNotEmpty
        ? existing.blockId
        : incoming.blockId,
    stepId: existing.stepId != ProcessStepId.unknown
        ? existing.stepId
        : incoming.stepId,
    status: _mergeProcessBlockStatus(existing.status, incoming.status),
    kind: existing.kind != ProcessDisplayBlockKind.unknown
        ? existing.kind
        : incoming.kind,
    title: _preferRicherProcessText(existing.title, incoming.title),
    body: _preferRicherProcessText(existing.body, incoming.body),
    items: _mergeProcessDisplayItems(existing.items, incoming.items),
    references: _mergeRetrievalReferences(existing.references, incoming.references),
  );
}

JourneyStageStatus _mergeProcessBlockStatus(
  JourneyStageStatus existing,
  JourneyStageStatus incoming,
) {
  if (incoming == JourneyStageStatus.blocked ||
      incoming == JourneyStageStatus.completed) {
    return incoming;
  }
  if (existing == JourneyStageStatus.blocked ||
      existing == JourneyStageStatus.completed) {
    return existing;
  }
  if (incoming == JourneyStageStatus.active) {
    return JourneyStageStatus.active;
  }
  if (existing == JourneyStageStatus.active) {
    return JourneyStageStatus.active;
  }
  if (incoming != JourneyStageStatus.unknown &&
      incoming != JourneyStageStatus.pending) {
    return incoming;
  }
  return existing;
}

String _preferRicherProcessText(String existing, String incoming) {
  final current = existing.trim();
  final next = incoming.trim();
  if (current.isEmpty) {
    return next;
  }
  if (next.isEmpty) {
    return current;
  }
  if (next.length > current.length) {
    return next;
  }
  return current;
}

List<AssistantDisplayItem> _mergeProcessDisplayItems(
  List<AssistantDisplayItem> existing,
  List<AssistantDisplayItem> incoming,
) {
  final merged = <String, AssistantDisplayItem>{};
  String itemKey(AssistantDisplayItem item) {
    final itemId = item.itemId.trim();
    if (itemId.isNotEmpty) {
      return itemId;
    }
    return '${item.title.trim()}:${item.body.trim()}';
  }

  for (final item in <AssistantDisplayItem>[...existing, ...incoming]) {
    final key = itemKey(item);
    final current = merged[key];
    if (current == null) {
      merged[key] = item;
      continue;
    }
    merged[key] = AssistantDisplayItem(
      itemId: current.itemId.trim().isNotEmpty ? current.itemId : item.itemId,
      title: _preferRicherProcessText(current.title, item.title),
      body: _preferRicherProcessText(current.body, item.body),
      referenceIds: <String>{
        ...current.referenceIds,
        ...item.referenceIds,
      }.where((id) => id.trim().isNotEmpty).toList(growable: false),
    );
  }
  return merged.values.toList(growable: false);
}

List<RetrievalProcessingReference> _mergeRetrievalReferences(
  List<RetrievalProcessingReference> existing,
  List<RetrievalProcessingReference> incoming,
) {
  final merged = <String, RetrievalProcessingReference>{};
  for (final reference in <RetrievalProcessingReference>[
    ...existing,
    ...incoming,
  ]) {
    final key = reference.url.trim().isNotEmpty
        ? reference.url.trim()
        : '${reference.source.trim()}:${reference.title.trim()}';
    if (key.trim().isEmpty || merged.containsKey(key)) {
      continue;
    }
    merged[key] = reference;
  }
  return merged.values.toList(growable: false);
}

String _canonicalProcessBlockId(String raw) {
  switch (raw.trim()) {
    case 'understanding_summary':
      return 'understanding_narrative';
    case 'retrieval_summary':
      return 'retrieval_narrative';
    case 'retrieval_references':
      return 'retrieval_reference_stats';
    default:
      return raw.trim();
  }
}

bool _hasVisibleProcessBlock(AssistantProcessDisplayBlock block) {
  return block.title.trim().isNotEmpty ||
      block.body.trim().isNotEmpty ||
      block.items.any(
        (item) => item.title.trim().isNotEmpty || item.body.trim().isNotEmpty,
      ) ||
      block.references.any(
        (reference) =>
            reference.title.trim().isNotEmpty ||
            reference.url.trim().isNotEmpty ||
            reference.source.trim().isNotEmpty,
      );
}

bool _hasVisibleAnswerBlock(AssistantAnswerDisplayBlock block) {
  return block.title.trim().isNotEmpty ||
      block.body.trim().isNotEmpty ||
      block.items.any(
        (item) => item.title.trim().isNotEmpty || item.body.trim().isNotEmpty,
      );
}

String _stripSpacesAndPunctuation(String raw) {
  final buffer = StringBuffer();
  for (final rune in raw.runes) {
    if (_isIgnorableNormalizationRune(rune)) {
      continue;
    }
    buffer.writeCharCode(rune);
  }
  return buffer.toString();
}

String _removeWhitespace(String raw) {
  final buffer = StringBuffer();
  for (final rune in raw.runes) {
    if (rune == 0x20 || rune == 0x09 || rune == 0x0a || rune == 0x0d) {
      continue;
    }
    buffer.writeCharCode(rune);
  }
  return buffer.toString();
}

List<String> _splitDetailSegments(String text) {
  final segments = <String>[];
  final buffer = StringBuffer();
  for (final rune in text.runes) {
    if (_isDetailSegmentSeparatorRune(rune)) {
      final segment = buffer.toString().trim();
      if (segment.isNotEmpty) {
        segments.add(segment);
      }
      buffer.clear();
      continue;
    }
    buffer.writeCharCode(rune);
  }
  final tail = buffer.toString().trim();
  if (tail.isNotEmpty) {
    segments.add(tail);
  }
  return segments;
}

bool _isIgnorableNormalizationRune(int rune) {
  return rune == 0x20 ||
      rune == 0x09 ||
      rune == 0x0a ||
      rune == 0x0d ||
      rune == 0x3000 ||
      rune == 0x3001 ||
      rune == 0x3002 ||
      rune == 0xFF0C ||
      rune == 0xFF1B ||
      rune == 0x003B ||
      rune == 0x003A ||
      rune == 0xFF1A ||
      rune == 0x300A ||
      rune == 0x300B ||
      rune == 0x300C ||
      rune == 0x300D ||
      rune == 0x300E ||
      rune == 0x300F ||
      rune == 0x002F ||
      rune == 0x005C ||
      rune == 0x0028 ||
      rune == 0x0029 ||
      rune == 0x002D ||
      rune == 0x005F;
}

bool _isDetailSegmentSeparatorRune(int rune) {
  return rune == 0x20 ||
      rune == 0x09 ||
      rune == 0x0a ||
      rune == 0x0d ||
      rune == 0xFF0C ||
      rune == 0x3001 ||
      rune == 0x3002 ||
      rune == 0xFF1B ||
      rune == 0x003B;
}

String _renderAnswerBlockToMarkdown(AssistantAnswerDisplayBlock block) {
  final title = block.title.trim();
  final body = block.body.trim();
  switch (block.kind) {
    case DisplayBlockKind.markdown:
      return body;
    case DisplayBlockKind.paragraph:
      if (title.isNotEmpty && body.isNotEmpty) {
        return '**$title**\n$body';
      }
      return title.isNotEmpty ? title : body;
    case DisplayBlockKind.bulletList:
    case DisplayBlockKind.numberedList:
    case DisplayBlockKind.referenceList:
      final prefix = block.kind == DisplayBlockKind.numberedList ? '1.' : '-';
      final lines = <String>[
        if (title.isNotEmpty) title,
        ...block.items
            .map((item) {
              final itemText = _renderItemText(item);
              return itemText.isEmpty ? '' : '$prefix $itemText';
            })
            .where((item) => item.isNotEmpty),
      ];
      if (body.isNotEmpty) {
        lines.insert(title.isNotEmpty ? 1 : 0, body);
      }
      return lines.join('\n').trim();
    case DisplayBlockKind.callout:
      final lines = <String>[
        if (title.isNotEmpty) '> $title',
        if (body.isNotEmpty)
          ...body.split('\n').map((line) => '> $line.trim()'),
      ];
      return lines.join('\n').trim();
    case DisplayBlockKind.unknown:
      return body.isNotEmpty ? body : title;
  }
}

String _renderAnswerBlockToPlainText(AssistantAnswerDisplayBlock block) {
  final title = block.title.trim();
  final body = block.body.trim();
  switch (block.kind) {
    case DisplayBlockKind.markdown:
      return _normalizePlainText(_stripMarkdown(body));
    case DisplayBlockKind.paragraph:
    case DisplayBlockKind.callout:
    case DisplayBlockKind.unknown:
      if (title.isNotEmpty && body.isNotEmpty) {
        return '$title\n$body';
      }
      return title.isNotEmpty ? title : body;
    case DisplayBlockKind.bulletList:
    case DisplayBlockKind.numberedList:
    case DisplayBlockKind.referenceList:
      final lines = <String>[
        if (title.isNotEmpty) title,
        if (body.isNotEmpty) body,
        ...block.items.map(_renderItemText).where((item) => item.isNotEmpty),
      ];
      return lines.join('\n').trim();
  }
}

String _renderItemText(AssistantDisplayItem item) {
  final title = item.title.trim();
  final body = item.body.trim();
  if (title.isNotEmpty && body.isNotEmpty) {
    return '$title：$body';
  }
  return title.isNotEmpty ? title : body;
}

String _normalizeMarkdownLeaf(String raw) {
  var text = raw.trim().replaceAll('\r\n', '\n');
  if (text.isEmpty) {
    return '';
  }
  text = text.replaceAll(RegExp(r'\n{3,}'), '\n\n');
  return text.trim();
}

String _normalizePlainText(String raw) {
  final stripped = _stripMarkdown(raw);
  return stripped
      .replaceAll('\r\n', '\n')
      .replaceAll(RegExp(r'[ \t]+'), ' ')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
}

String _stripMarkdown(String raw) {
  return raw
      .replaceAll(RegExp(r'```[\s\S]*?```'), '')
      .replaceAll(RegExp(r'!\[[^\]]*\]\([^)]+\)'), '')
      .replaceAllMapped(
        RegExp(r'\[([^\]]+)\]\(([^)]+)\)'),
        (match) => match.group(1) ?? '',
      )
      .replaceAll(RegExp(r'(^|\n)\s*#{1,6}\s+', multiLine: true), '\n')
      .replaceAll(RegExp(r'(^|\n)\s*>\s?', multiLine: true), '\n')
      .replaceAll(RegExp(r'[*_`~]'), '')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
}
