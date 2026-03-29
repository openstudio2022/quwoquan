import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';

const String assistantDisplayStateField = 'displayState';

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
  if (explicitBlocks.isNotEmpty || explicitSummary.isNotEmpty) {
    return AssistantProcessDisplayState(
      activeStepId: activeStepId,
      summary: explicitSummary.isNotEmpty
          ? explicitSummary
          : _resolveProcessSummary(
              explicitBlocks: explicitBlocks,
              processTimeline: processTimeline,
            ),
      blocks: explicitBlocks,
      finalAnswerReady: explicit.finalAnswerReady || finalAnswerReady,
    );
  }
  final derivedBlocks = <AssistantProcessDisplayBlock>[
    ..._buildUnderstandingBlocks(processTimeline, understandingSnapshot),
    ..._buildRetrievalBlocks(processTimeline, retrievalProcessing),
    ..._buildAnswerOrganizationBlocks(processTimeline, answerProcessing),
  ];
  return AssistantProcessDisplayState(
    activeStepId: activeStepId,
    summary: _resolveProcessSummary(
      explicitBlocks: derivedBlocks,
      processTimeline: processTimeline,
    ),
    blocks: derivedBlocks,
    finalAnswerReady: finalAnswerReady,
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
  if (explicitBlocks.isNotEmpty || explicit.summary.trim().isNotEmpty) {
    return AssistantAnswerDisplayState(
      summary: explicit.summary.trim(),
      blocks: explicitBlocks,
    );
  }
  final markdown = _normalizeMarkdownLeaf(answerMarkdown);
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
  final status = frame?.status ?? JourneyStageStatus.pending;
  final summary = snapshot.userFacingSummary.trim();
  if (summary.isEmpty) {
    return const <AssistantProcessDisplayBlock>[];
  }
  return <AssistantProcessDisplayBlock>[
    AssistantProcessDisplayBlock(
      blockId: 'understanding_summary',
      stepId: ProcessStepId.understanding,
      status: status,
      kind: ProcessDisplayBlockKind.summary,
      title: summary,
    ),
  ];
}

List<AssistantProcessDisplayBlock> _buildRetrievalBlocks(
  List<ProcessTimelineFrame> processTimeline,
  RetrievalProcessingSnapshot snapshot,
) {
  final frame = _frameForStep(
    processTimeline,
    ProcessStepId.retrievalProcessing,
  );
  final status = frame?.status ?? JourneyStageStatus.pending;
  final keyPoints = snapshot.selectedKeyPoints
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  final refs = snapshot.acceptedReferences
      .where(
        (item) =>
            item.title.trim().isNotEmpty ||
            item.url.trim().isNotEmpty ||
            item.source.trim().isNotEmpty,
      )
      .toList(growable: false);
  final summary = _resolveRetrievalSummary(
    frame: frame,
    snapshot: snapshot,
    hasKeyPoints: keyPoints.isNotEmpty,
    hasReferences: refs.isNotEmpty,
  );
  final blocks = <AssistantProcessDisplayBlock>[];
  if (summary.isNotEmpty) {
    blocks.add(
      AssistantProcessDisplayBlock(
        blockId: 'retrieval_summary',
        stepId: ProcessStepId.retrievalProcessing,
        status: status,
        kind: ProcessDisplayBlockKind.summary,
        title: summary,
      ),
    );
  }
  if (keyPoints.isNotEmpty) {
    blocks.add(
      AssistantProcessDisplayBlock(
        blockId: 'retrieval_points',
        stepId: ProcessStepId.retrievalProcessing,
        status: status,
        kind: ProcessDisplayBlockKind.points,
        items: _buildItems(keyPoints),
      ),
    );
  }
  if (refs.isNotEmpty) {
    blocks.add(
      AssistantProcessDisplayBlock(
        blockId: 'retrieval_references',
        stepId: ProcessStepId.retrievalProcessing,
        status: status,
        kind: ProcessDisplayBlockKind.references,
        references: refs,
      ),
    );
  }
  return blocks;
}

String _resolveRetrievalSummary({
  required ProcessTimelineFrame? frame,
  required RetrievalProcessingSnapshot snapshot,
  required bool hasKeyPoints,
  required bool hasReferences,
}) {
  final frameHeadline = _firstProcessLine(frame?.headline ?? '');
  if (frameHeadline.isNotEmpty) {
    final hasLegacySnapshotOnlySummary =
        frame != null &&
        frame.detail.trim().isEmpty &&
        frameHeadline == snapshot.processingSummary.trim() &&
        (hasKeyPoints ||
            hasReferences ||
            snapshot.processedDocumentCount > 0 ||
            snapshot.acceptedDocumentCount > 0);
    if (!hasLegacySnapshotOnlySummary) {
      return frameHeadline;
    }
  }
  final frameDetail = _firstProcessLine(frame?.detail ?? '');
  if (frameDetail.isNotEmpty) {
    return frameDetail;
  }
  if (hasKeyPoints ||
      hasReferences ||
      snapshot.processedDocumentCount > 0 ||
      snapshot.acceptedDocumentCount > 0) {
    return '';
  }
  return snapshot.processingSummary.trim();
}

List<AssistantProcessDisplayBlock> _buildAnswerOrganizationBlocks(
  List<ProcessTimelineFrame> processTimeline,
  RunArtifactsAnswerProcessing snapshot,
) {
  final frame = _frameForStep(
    processTimeline,
    ProcessStepId.answerOrganization,
  );
  final status = frame?.status ?? JourneyStageStatus.pending;
  final summary = snapshot.readinessSummary.trim();
  final keyFacts = snapshot.keyFacts
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  final blocks = <AssistantProcessDisplayBlock>[];
  if (summary.isNotEmpty) {
    blocks.add(
      AssistantProcessDisplayBlock(
        blockId: 'answer_summary',
        stepId: ProcessStepId.answerOrganization,
        status: status,
        kind: ProcessDisplayBlockKind.summary,
        title: summary,
      ),
    );
  }
  if (keyFacts.isNotEmpty) {
    blocks.add(
      AssistantProcessDisplayBlock(
        blockId: 'answer_points',
        stepId: ProcessStepId.answerOrganization,
        status: status,
        kind: ProcessDisplayBlockKind.points,
        items: _buildItems(keyFacts),
      ),
    );
  }
  return blocks;
}

List<AssistantDisplayItem> _buildItems(List<String> lines) {
  return lines
      .asMap()
      .entries
      .map(
        (entry) => AssistantDisplayItem(
          itemId: 'item_${entry.key}',
          body: entry.value,
        ),
      )
      .toList(growable: false);
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
}) {
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
      ProcessStepId.answerOrganization =>
        frame.answerProcessing.readinessSummary,
      _ => '',
    }.trim();
    if (snapshotSummary.isNotEmpty) {
      return snapshotSummary;
    }
  }
  return '';
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
