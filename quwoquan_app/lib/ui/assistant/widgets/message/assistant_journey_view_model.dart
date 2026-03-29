import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
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

  final ProcessStepId stageId;
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
    this.items = const <String>[],
    this.referenceLabel = '',
    this.references = const <AssistantJourneyReferenceViewModel>[],
  });

  final AssistantJourneyBlockKind kind;
  final ProcessStepId stageId;
  final String headline;
  final String detail;
  final List<String> items;
  final String referenceLabel;
  final List<AssistantJourneyReferenceViewModel> references;

  bool get hasReferences => references.isNotEmpty;
}

class AssistantJourneyViewModel {
  const AssistantJourneyViewModel({
    this.journey = const AssistantJourney(),
    this.displayState = const AssistantDisplayState(),
    this.processTimeline = const <ProcessTimelineFrame>[],
    this.retrievalProcessing = const RetrievalProcessingSnapshot(),
    this.stages = const <AssistantJourneyStageViewModel>[],
    this.blocks = const <AssistantJourneyBlockViewModel>[],
    this.summary = '',
    this.activeStageId = ProcessStepId.unknown,
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
  final AssistantDisplayState displayState;
  final List<ProcessTimelineFrame> processTimeline;
  final RetrievalProcessingSnapshot retrievalProcessing;
  final List<AssistantJourneyStageViewModel> stages;
  final List<AssistantJourneyBlockViewModel> blocks;
  final String summary;
  final ProcessStepId activeStageId;
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
      activeStageId == ProcessStepId.understanding;
}

AssistantJourneyViewModel buildAssistantJourneyViewModel({
  required AssistantJourney journey,
  required List<ProcessTimelineFrame> processTimeline,
  required bool isRunning,
  bool allowAnswerStage = true,
  Map<String, dynamic> usageStats = const <String, dynamic>{},
  int elapsedMs = 0,
  AssistantDisplayState displayState = const AssistantDisplayState(),
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
}) {
  final timelineInput = processTimeline.isNotEmpty
      ? buildVisibleProcessTimeline(processTimeline)
      : const <ProcessTimelineFrame>[];
  final effectiveTimeline = _maskPrematureAnswerTimeline(
    normalizeProcessTimeline(timelineInput),
    isRunning: isRunning,
    allowAnswerStage: allowAnswerStage,
    finalAnswerReady: journey.readiness.finalAnswerReady,
  );
  final effectiveRetrievalProcessing = _resolveRetrievalProcessing(
    effectiveTimeline,
    retrievalProcessing,
  );
  final effectiveDisplayState = buildAssistantDisplayState(
    explicitState: displayState,
    processTimeline: effectiveTimeline,
    retrievalProcessing: effectiveRetrievalProcessing,
    finalAnswerReady: displayState.process.finalAnswerReady,
  );
  final fallbackStages = _buildStages(
    processTimeline: effectiveTimeline,
    retrievalProcessing: effectiveRetrievalProcessing,
  );
  final fallbackBlocks = _buildBlocks(
    processTimeline: effectiveTimeline,
    retrievalProcessing: effectiveRetrievalProcessing,
  );
  final displayStages = effectiveDisplayState.process.blocks.isNotEmpty
      ? _buildStagesFromDisplayState(
          process: effectiveDisplayState.process,
          retrievalProcessing: effectiveRetrievalProcessing,
        )
      : const <AssistantJourneyStageViewModel>[];
  final displayBlocks = effectiveDisplayState.process.blocks.isNotEmpty
      ? _buildBlocksFromDisplayState(
          process: effectiveDisplayState.process,
          retrievalProcessing: effectiveRetrievalProcessing,
        )
      : const <AssistantJourneyBlockViewModel>[];
  final stages = _mergeStages(
    preferred: displayStages,
    fallback: fallbackStages,
  );
  final blocks = _mergeBlocks(
    preferred: displayBlocks,
    fallback: fallbackBlocks,
  );
  final activeStage = _resolveActiveStage(stages, isRunning: isRunning);
  final summary = _resolveSummary(
    stages: stages,
    blocks: blocks,
    isRunning: isRunning,
  );
  final referenceCount = <String>{
    for (final block in blocks)
      for (final reference in block.references)
        if (reference.url.trim().isNotEmpty) reference.url.trim(),
  }.length;
  return AssistantJourneyViewModel(
    journey: journey,
    displayState: effectiveDisplayState,
    processTimeline: effectiveTimeline,
    retrievalProcessing: effectiveRetrievalProcessing,
    stages: stages,
    blocks: blocks,
    summary: summary,
    activeStageId: activeStage.stageId,
    activeStageLabel: activeStage.label,
    processedDocumentCount:
        effectiveRetrievalProcessing.processedDocumentCount > 0
        ? effectiveRetrievalProcessing.processedDocumentCount
        : effectiveRetrievalProcessing.acceptedDocumentCount,
    acceptedDocumentCount: effectiveRetrievalProcessing.acceptedDocumentCount,
    referenceCount: referenceCount,
    isRunning: isRunning,
    usageStats: usageStats,
    elapsedMs: elapsedMs,
    finalAnswerReady: journey.readiness.finalAnswerReady,
    clarificationNeeded: journey.readiness.clarificationNeeded,
    needExpansion: journey.readiness.needExpansion,
  );
}

List<ProcessTimelineFrame> _maskPrematureAnswerTimeline(
  List<ProcessTimelineFrame> processTimeline, {
  required bool isRunning,
  required bool allowAnswerStage,
  required bool finalAnswerReady,
}) {
  if (!isRunning || allowAnswerStage || finalAnswerReady) {
    return processTimeline;
  }
  return processTimeline
      .where((frame) => frame.stepId != ProcessStepId.answerOrganization)
      .toList(growable: false);
}

List<AssistantJourneyStageViewModel> _buildStages({
  required List<ProcessTimelineFrame> processTimeline,
  required RetrievalProcessingSnapshot retrievalProcessing,
}) {
  if (processTimeline.isEmpty) {
    return const <AssistantJourneyStageViewModel>[];
  }
  return processTimeline
      .map((frame) {
        return AssistantJourneyStageViewModel(
          stageId: frame.stepId,
          order: assistantProcessStepOrder(frame.stepId),
          label: _processStepLabel(frame.stepId),
          status: frame.status,
          summary: _headlineForFrame(frame),
          referenceCount: frame.stepId == ProcessStepId.retrievalProcessing
              ? (retrievalProcessing.acceptedDocumentCount > 0
                    ? retrievalProcessing.acceptedDocumentCount
                    : retrievalProcessing.acceptedReferences.length)
              : 0,
        );
      })
      .toList(growable: false);
}

List<AssistantJourneyStageViewModel> _buildStagesFromDisplayState({
  required AssistantProcessDisplayState process,
  required RetrievalProcessingSnapshot retrievalProcessing,
}) {
  final grouped = <ProcessStepId, List<AssistantProcessDisplayBlock>>{};
  for (final block in process.blocks) {
    grouped
        .putIfAbsent(block.stepId, () => <AssistantProcessDisplayBlock>[])
        .add(block);
  }
  final orderedSteps = grouped.keys.toList(growable: false)
    ..sort(
      (a, b) =>
          assistantProcessStepOrder(a).compareTo(assistantProcessStepOrder(b)),
    );
  return orderedSteps
      .map((stepId) {
        final stepBlocks =
            grouped[stepId] ?? const <AssistantProcessDisplayBlock>[];
        final summary = _summaryForProcessBlocks(stepBlocks);
        return AssistantJourneyStageViewModel(
          stageId: stepId,
          order: assistantProcessStepOrder(stepId),
          label: _processStepLabel(stepId),
          status: _statusForProcessBlocks(stepBlocks),
          summary: summary,
          referenceCount: stepId == ProcessStepId.retrievalProcessing
              ? _referenceCountForStep(stepBlocks, retrievalProcessing)
              : 0,
        );
      })
      .toList(growable: false);
}

List<AssistantJourneyBlockViewModel> _buildBlocks({
  required List<ProcessTimelineFrame> processTimeline,
  required RetrievalProcessingSnapshot retrievalProcessing,
}) {
  return processTimeline
      .where((frame) => frame.hasVisibleContent)
      .map(
        (frame) => AssistantJourneyBlockViewModel(
          kind: frame.stepId == ProcessStepId.retrievalProcessing
              ? AssistantJourneyBlockKind.searchSummary
              : AssistantJourneyBlockKind.narrative,
          stageId: frame.stepId,
          headline: _headlineForFrame(frame),
          detail: _detailForFrame(
            frame,
            fallbackRetrievalProcessing: retrievalProcessing,
          ),
          referenceLabel: _referenceLabelForFrame(
            frame,
            fallbackRetrievalProcessing: retrievalProcessing,
          ),
          references: frame.references
              .map(
                (reference) => AssistantJourneyReferenceViewModel(
                  title: reference.title.trim(),
                  url: reference.url.trim(),
                  source: reference.source.trim(),
                ),
              )
              .where(
                (reference) =>
                    reference.title.isNotEmpty || reference.url.isNotEmpty,
              )
              .toList(growable: false),
        ),
      )
      .toList(growable: false);
}

List<AssistantJourneyBlockViewModel> _buildBlocksFromDisplayState({
  required AssistantProcessDisplayState process,
  required RetrievalProcessingSnapshot retrievalProcessing,
}) {
  final grouped = <ProcessStepId, List<AssistantProcessDisplayBlock>>{};
  for (final block in process.blocks.where(_hasVisibleProcessBlockForUi)) {
    grouped
        .putIfAbsent(block.stepId, () => <AssistantProcessDisplayBlock>[])
        .add(block);
  }
  final orderedSteps = grouped.keys.toList(growable: false)
    ..sort(
      (a, b) =>
          assistantProcessStepOrder(a).compareTo(assistantProcessStepOrder(b)),
    );
  return orderedSteps
      .map((stepId) {
        final stepBlocks =
            grouped[stepId] ?? const <AssistantProcessDisplayBlock>[];
        var headline = '';
        var detail = '';
        final items = <String>[];
        final references = <AssistantJourneyReferenceViewModel>[];
        for (final block in stepBlocks) {
          final title = _sanitizeProcessText(
            block.title.trim(),
            stepId: stepId,
          );
          final body = _sanitizeProcessText(block.body.trim(), stepId: stepId);
          if (headline.isEmpty) {
            if (title.isNotEmpty) {
              headline = title;
            } else if (body.isNotEmpty) {
              headline = body;
            }
          } else if (detail.isEmpty && body.isNotEmpty && body != headline) {
            detail = body;
          }
          items.addAll(
            block.items
                .map(
                  (item) => _sanitizeProcessText(
                    _displayItemText(item),
                    stepId: stepId,
                  ),
                )
                .where((item) => item.isNotEmpty),
          );
          references.addAll(
            block.references
                .map(
                  (reference) => AssistantJourneyReferenceViewModel(
                    title: reference.title.trim(),
                    url: reference.url.trim(),
                    source: reference.source.trim(),
                  ),
                )
                .where(
                  (reference) =>
                      reference.title.isNotEmpty || reference.url.isNotEmpty,
                ),
          );
        }
        final acceptedCount = retrievalProcessing.acceptedDocumentCount > 0
            ? retrievalProcessing.acceptedDocumentCount
            : references.length;
        final processedCount = retrievalProcessing.processedDocumentCount > 0
            ? retrievalProcessing.processedDocumentCount
            : acceptedCount;
        return AssistantJourneyBlockViewModel(
          kind: stepId == ProcessStepId.retrievalProcessing
              ? AssistantJourneyBlockKind.searchSummary
              : AssistantJourneyBlockKind.narrative,
          stageId: stepId,
          headline: headline,
          detail: detail,
          items: items,
          referenceLabel: references.isNotEmpty
              ? UITextConstants.assistantProcessReferenceDigestTemplate
                    .replaceFirst('%s', processedCount.toString())
                    .replaceFirst('%s', acceptedCount.toString())
              : '',
          references: references,
        );
      })
      .toList(growable: false);
}

List<AssistantJourneyStageViewModel> _mergeStages({
  required List<AssistantJourneyStageViewModel> preferred,
  required List<AssistantJourneyStageViewModel> fallback,
}) {
  final merged = <ProcessStepId, AssistantJourneyStageViewModel>{
    for (final stage in fallback) stage.stageId: stage,
  };
  for (final stage in preferred) {
    merged[stage.stageId] = stage;
  }
  final ordered = merged.values.toList(growable: false)
    ..sort((a, b) => a.order.compareTo(b.order));
  return ordered;
}

List<AssistantJourneyBlockViewModel> _mergeBlocks({
  required List<AssistantJourneyBlockViewModel> preferred,
  required List<AssistantJourneyBlockViewModel> fallback,
}) {
  final preferredByStep =
      <ProcessStepId, List<AssistantJourneyBlockViewModel>>{};
  for (final block in preferred) {
    preferredByStep
        .putIfAbsent(block.stageId, () => <AssistantJourneyBlockViewModel>[])
        .add(block);
  }
  final fallbackByStep =
      <ProcessStepId, List<AssistantJourneyBlockViewModel>>{};
  for (final block in fallback) {
    fallbackByStep
        .putIfAbsent(block.stageId, () => <AssistantJourneyBlockViewModel>[])
        .add(block);
  }
  final orderedStepIds =
      <ProcessStepId>{
        ...fallbackByStep.keys,
        ...preferredByStep.keys,
      }.toList(growable: false)..sort(
        (a, b) => assistantProcessStepOrder(
          a,
        ).compareTo(assistantProcessStepOrder(b)),
      );
  final merged = <AssistantJourneyBlockViewModel>[];
  for (final stepId in orderedStepIds) {
    final preferredBlocks = preferredByStep[stepId];
    if (preferredBlocks != null && preferredBlocks.isNotEmpty) {
      merged.addAll(preferredBlocks);
      continue;
    }
    merged.addAll(
      fallbackByStep[stepId] ?? const <AssistantJourneyBlockViewModel>[],
    );
  }
  return merged;
}

AssistantJourneyStageViewModel _resolveActiveStage(
  List<AssistantJourneyStageViewModel> stages, {
  required bool isRunning,
}) {
  for (final stage in stages) {
    if (stage.status == JourneyStageStatus.active) {
      return stage;
    }
  }
  if (isRunning) {
    for (final stage in stages) {
      if (!stage.isResolved) {
        return stage;
      }
    }
  }
  for (final stage in stages.reversed) {
    if (stage.summary.trim().isNotEmpty || stage.referenceCount > 0) {
      return stage;
    }
  }
  return const AssistantJourneyStageViewModel(
    stageId: ProcessStepId.unknown,
    order: -1,
    label: '',
  );
}

String _resolveSummary({
  required List<AssistantJourneyStageViewModel> stages,
  required List<AssistantJourneyBlockViewModel> blocks,
  required bool isRunning,
}) {
  if (isRunning) {
    final active = _resolveActiveStage(stages, isRunning: true);
    if (active.label.isNotEmpty) {
      return active.label;
    }
  }
  for (final block in blocks.reversed) {
    if (block.headline.trim().isNotEmpty) {
      return block.headline.trim();
    }
  }
  for (final stage in stages.reversed) {
    if (stage.summary.trim().isNotEmpty) {
      return stage.summary.trim();
    }
  }
  return '';
}

String _summaryForProcessBlocks(List<AssistantProcessDisplayBlock> blocks) {
  for (final block in blocks) {
    if (block.title.trim().isNotEmpty) {
      return block.title.trim();
    }
    if (block.body.trim().isNotEmpty) {
      return block.body.trim();
    }
  }
  return '';
}

JourneyStageStatus _statusForProcessBlocks(
  List<AssistantProcessDisplayBlock> blocks,
) {
  for (final block in blocks) {
    if (block.status == JourneyStageStatus.active) {
      return JourneyStageStatus.active;
    }
  }
  for (final block in blocks) {
    if (block.status != JourneyStageStatus.unknown) {
      return block.status;
    }
  }
  return JourneyStageStatus.pending;
}

int _referenceCountForStep(
  List<AssistantProcessDisplayBlock> blocks,
  RetrievalProcessingSnapshot retrievalProcessing,
) {
  final direct = retrievalProcessing.acceptedDocumentCount > 0
      ? retrievalProcessing.acceptedDocumentCount
      : retrievalProcessing.acceptedReferences.length;
  if (direct > 0) {
    return direct;
  }
  return <String>{
    for (final block in blocks)
      for (final reference in block.references)
        if (reference.url.trim().isNotEmpty) reference.url.trim(),
  }.length;
}

String _displayItemText(AssistantDisplayItem item) {
  final title = item.title.trim();
  final body = item.body.trim();
  if (title.isNotEmpty && body.isNotEmpty) {
    return '$title：$body';
  }
  return title.isNotEmpty ? title : body;
}

bool _hasVisibleProcessBlockForUi(AssistantProcessDisplayBlock block) {
  return block.title.trim().isNotEmpty ||
      block.body.trim().isNotEmpty ||
      block.items.any(
        (item) => item.title.trim().isNotEmpty || item.body.trim().isNotEmpty,
      ) ||
      block.references.any(
        (reference) =>
            reference.title.trim().isNotEmpty ||
            reference.url.trim().isNotEmpty,
      );
}

RetrievalProcessingSnapshot _resolveRetrievalProcessing(
  List<ProcessTimelineFrame> processTimeline,
  RetrievalProcessingSnapshot fallback,
) {
  ProcessTimelineFrame? summaryFrame;
  ProcessTimelineFrame? refsFallbackFrame;
  for (final frame in processTimeline) {
    if (frame.stepId != ProcessStepId.retrievalProcessing) {
      continue;
    }
    final rp = frame.retrievalProcessing;
    if (rp.processingSummary.trim().isNotEmpty) {
      summaryFrame = frame;
    }
    if (_retrievalFrameHasSnapshotFallbackSignals(frame)) {
      refsFallbackFrame = frame;
    }
  }
  if (summaryFrame != null) {
    return _mergeRetrievalSnapshotWithFrameReferences(
      summaryFrame,
      summaryFrame.retrievalProcessing,
    );
  }
  if (refsFallbackFrame != null) {
    return _mergeRetrievalSnapshotWithFrameReferences(
      refsFallbackFrame,
      refsFallbackFrame.retrievalProcessing,
    );
  }
  return fallback;
}

bool _retrievalFrameHasSnapshotFallbackSignals(ProcessTimelineFrame frame) {
  if (frame.stepId != ProcessStepId.retrievalProcessing) {
    return false;
  }
  final rp = frame.retrievalProcessing;
  return frame.references.isNotEmpty ||
      rp.acceptedReferences.isNotEmpty ||
      rp.selectedKeyPoints.isNotEmpty ||
      rp.processedDocumentCount > 0 ||
      rp.acceptedDocumentCount > 0;
}

/// 将 timeline 帧上的 [ProcessTimelineFrame.references] 并入快照，并补齐计数，避免仅有引用时摘要丢失。
RetrievalProcessingSnapshot _mergeRetrievalSnapshotWithFrameReferences(
  ProcessTimelineFrame frame,
  RetrievalProcessingSnapshot snapshot,
) {
  final refs = snapshot.acceptedReferences.isNotEmpty
      ? snapshot.acceptedReferences
      : frame.references;
  final acceptedCount = snapshot.acceptedDocumentCount > 0
      ? snapshot.acceptedDocumentCount
      : (refs.isNotEmpty ? refs.length : 0);
  final processedCount = snapshot.processedDocumentCount > 0
      ? snapshot.processedDocumentCount
      : acceptedCount;
  return RetrievalProcessingSnapshot(
    processedDocumentCount: processedCount,
    acceptedDocumentCount: acceptedCount,
    processingSummary: snapshot.processingSummary,
    selectedKeyPoints: snapshot.selectedKeyPoints,
    expansionReason: snapshot.expansionReason,
    acceptedReferences: refs,
  );
}

String _headlineForFrame(ProcessTimelineFrame? frame) {
  if (frame == null) return '';
  final lines = _sanitizeProcessLines(frame.headline, stepId: frame.stepId);
  if (lines.isNotEmpty) {
    return lines.first;
  }
  final detailLines = _sanitizeProcessLines(frame.detail, stepId: frame.stepId);
  return detailLines.isNotEmpty ? detailLines.first : '';
}

String _detailForFrame(
  ProcessTimelineFrame frame, {
  required RetrievalProcessingSnapshot fallbackRetrievalProcessing,
}) {
  if (frame.stepId == ProcessStepId.understanding) {
    return '';
  }
  if (frame.stepId == ProcessStepId.retrievalProcessing &&
      !_retrievalFrameHasSnapshotFallbackSignals(frame)) {
    return '';
  }
  final detailLines = _sanitizeProcessLines(frame.detail, stepId: frame.stepId);
  if (detailLines.isEmpty) {
    return '';
  }
  final headline = _headlineForFrame(frame);
  final remaining = headline.isNotEmpty && detailLines.first == headline
      ? detailLines.skip(1).toList(growable: false)
      : detailLines;
  return remaining.join('\n');
}

String _referenceLabelForFrame(
  ProcessTimelineFrame frame, {
  required RetrievalProcessingSnapshot fallbackRetrievalProcessing,
}) {
  if (frame.stepId != ProcessStepId.retrievalProcessing) {
    return '';
  }
  final snapshot = frame.retrievalProcessing.processingSummary.trim().isNotEmpty
      ? frame.retrievalProcessing
      : fallbackRetrievalProcessing;
  var acceptedCount = snapshot.acceptedDocumentCount > 0
      ? snapshot.acceptedDocumentCount
      : snapshot.acceptedReferences.length;
  var processedCount = snapshot.processedDocumentCount > 0
      ? snapshot.processedDocumentCount
      : acceptedCount;
  if (processedCount <= 0 && acceptedCount <= 0) {
    final refCount = frame.references
        .where((r) => r.title.trim().isNotEmpty || r.url.trim().isNotEmpty)
        .length;
    if (refCount > 0) {
      acceptedCount = refCount;
      processedCount = refCount;
    }
  }
  if (processedCount <= 0 && acceptedCount <= 0) {
    return '';
  }
  return UITextConstants.assistantProcessReferenceDigestTemplate
      .replaceFirst('%s', processedCount.toString())
      .replaceFirst('%s', acceptedCount.toString());
}

String _processStepLabel(ProcessStepId stepId) {
  switch (stepId) {
    case ProcessStepId.understanding:
      return UITextConstants.assistantProcessStageUnderstand;
    case ProcessStepId.retrievalDesign:
      return UITextConstants.assistantProcessStageUnderstand;
    case ProcessStepId.retrievalProcessing:
      return UITextConstants.assistantProcessStageRetrievalProcessing;
    case ProcessStepId.answerOrganization:
      return UITextConstants.assistantProcessStageAnswer;
    case ProcessStepId.unknown:
      return UITextConstants.assistantProcessStageUnderstand;
  }
}

String _sanitizeProcessMultiline(String raw, {required ProcessStepId stepId}) {
  return _sanitizeProcessLines(raw, stepId: stepId).join('\n');
}

List<String> _sanitizeProcessLines(
  String raw, {
  required ProcessStepId stepId,
}) {
  return raw
      .split('\n')
      .map((line) => _sanitizeProcessSingleLine(line, stepId: stepId))
      .where((line) => line.isNotEmpty)
      .toList(growable: false);
}

String _sanitizeProcessText(String raw, {required ProcessStepId stepId}) {
  if (raw.contains('\n')) {
    return _sanitizeProcessMultiline(raw, stepId: stepId);
  }
  return _sanitizeProcessSingleLine(raw, stepId: stepId);
}

String _sanitizeProcessSingleLine(String raw, {required ProcessStepId stepId}) {
  final normalized =
      AssistantDisplayTextResolver.normalizeUserFacingProcessNarration(raw);
  if (normalized.isEmpty) {
    return '';
  }
  return normalized;
}
