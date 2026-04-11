import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';

/// 当结构化 `processTimeline` 与快照均缺失时，从 [AssistantJourney] 合成可展示的流程帧（读侧恢复 / 写侧补齐）。
List<ProcessTimelineFrame> buildProcessTimelineFramesFromJourneyFallback(
  AssistantJourney journey,
) {
  if (journey.isEmpty) {
    return const <ProcessTimelineFrame>[];
  }
  final hasVerify = _journeyHasVerifySignal(journey);
  final sortedEntries = List<AssistantJourneyEntry>.from(journey.entries)
    ..sort((a, b) => a.order.compareTo(b.order));

  final understandingEntries = <AssistantJourneyEntry>[];
  final designSearchEntries = <AssistantJourneyEntry>[];
  final processingSearchEntries = <AssistantJourneyEntry>[];
  final verifyEntries = <AssistantJourneyEntry>[];
  final answerEntries = <AssistantJourneyEntry>[];

  for (final e in sortedEntries) {
    switch (e.stageId) {
      case JourneyStageId.analyze:
        understandingEntries.add(e);
        break;
      case JourneyStageId.search:
        if (hasVerify) {
          designSearchEntries.add(e);
        } else if (_searchEntryLooksLikeVerification(e)) {
          processingSearchEntries.add(e);
        } else {
          designSearchEntries.add(e);
        }
        break;
      case JourneyStageId.verify:
        verifyEntries.add(e);
        break;
      case JourneyStageId.answer:
        answerEntries.add(e);
        break;
      default:
        break;
    }
  }

  final analyzeStage = journey.stageFor(JourneyStageId.analyze);
  final searchStage = journey.stageFor(JourneyStageId.search);
  final verifyStage = journey.stageFor(JourneyStageId.verify);
  final answerStage = journey.stageFor(JourneyStageId.answer);

  final frames = <ProcessTimelineFrame>[];

  final uHeadline = _pickJourneyHeadline(
    stage: analyzeStage,
    entries: understandingEntries,
  );
  final uDetail = _mergeJourneyEntryLines(
    stage: analyzeStage,
    entries: understandingEntries,
    understandingStage: true,
  );
  if (uHeadline.isNotEmpty || uDetail.isNotEmpty) {
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.understanding,
        status: _mergeBucketStatus(
          stage: analyzeStage,
          entries: understandingEntries,
        ),
        headline: uHeadline,
        detail: uDetail,
        understandingSnapshot: uHeadline.isNotEmpty
            ? RunArtifactsUnderstandingSnapshot(
                intentSummary: uHeadline,
                userFacingSummary: uHeadline,
              )
            : const RunArtifactsUnderstandingSnapshot(),
      ),
    );
  }

  final designHeadline = _pickJourneyHeadline(
    stage: searchStage,
    entries: designSearchEntries,
  );
  final designDetail = _mergeJourneyEntryLines(
    stage: searchStage,
    entries: designSearchEntries,
    understandingStage: false,
  );
  if (designHeadline.isNotEmpty || designDetail.isNotEmpty) {
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.retrievalDesign,
        status: _mergeBucketStatus(
          stage: searchStage,
          entries: designSearchEntries,
        ),
        headline: designHeadline,
        detail: designDetail,
        understandingSnapshot: designHeadline.isNotEmpty
            ? RunArtifactsUnderstandingSnapshot(
                queryDesignSummary: designHeadline,
              )
            : const RunArtifactsUnderstandingSnapshot(),
      ),
    );
  }

  final processingEntries = <AssistantJourneyEntry>[
    ...verifyEntries,
    ...processingSearchEntries,
  ];
  final processingHeadline = _pickJourneyHeadline(
    stage: verifyStage,
    entries: processingEntries,
  );
  final processingDetail = _mergeJourneyEntryLines(
    stage: verifyStage,
    entries: processingEntries,
    understandingStage: false,
  );
  final processingRefs = _collectRetrievalReferences(
    entries: processingEntries,
    journey: journey,
  );
  if (processingHeadline.isNotEmpty ||
      processingDetail.isNotEmpty ||
      processingRefs.isNotEmpty) {
    // 不在帧快照里重复 headline：否则 _resolveRetrievalProcessing 会优先采用帧内
    // processingSummary，与 headline 相同后触发去重把整条 headline 剥空（读侧 journey 恢复）。
    final rpSnapshot = RetrievalProcessingSnapshot(
      processedDocumentCount: processingRefs.isNotEmpty
          ? processingRefs.length
          : 0,
      acceptedDocumentCount: processingRefs.isNotEmpty
          ? processingRefs.length
          : 0,
      processingSummary: '',
      selectedKeyPoints: _detailToKeyPoints(processingDetail),
      acceptedReferences: processingRefs,
    );
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.retrievalProcessing,
        status: _mergeBucketStatus(
          stage: verifyStage,
          entries: processingEntries,
        ),
        headline: processingHeadline,
        detail: processingDetail,
        references: processingRefs,
        retrievalProcessing: rpSnapshot,
      ),
    );
  }

  if (_shouldEmitAnswerOrganizationFrame(journey, answerStage, answerEntries)) {
    final answerHeadline = _pickJourneyHeadline(
      stage: answerStage,
      entries: answerEntries,
    );
    final answerDetail = _mergeJourneyEntryLines(
      stage: answerStage,
      entries: answerEntries,
      understandingStage: false,
    );
    if (answerHeadline.isNotEmpty || answerDetail.isNotEmpty) {
      final apSnapshot = answerHeadline.isNotEmpty
          ? RunArtifactsAnswerProcessing(readinessSummary: answerHeadline)
          : const RunArtifactsAnswerProcessing();
      frames.add(
        buildProcessTimelineFrame(
          stepId: ProcessStepId.answerOrganization,
          status: _mergeBucketStatus(
            stage: answerStage,
            entries: answerEntries,
          ),
          headline: answerHeadline,
          detail: answerDetail,
          answerProcessing: apSnapshot,
        ),
      );
    }
  }

  return normalizeProcessTimeline(frames);
}

bool _journeyHasVerifySignal(AssistantJourney journey) {
  return journey.stages.any((s) => s.stageId == JourneyStageId.verify) ||
      journey.entries.any((e) => e.stageId == JourneyStageId.verify);
}

bool _searchEntryLooksLikeVerification(AssistantJourneyEntry entry) {
  if (entry.kind == JourneyEntryKind.referenceBundle) {
    return true;
  }
  if (entry.references.isNotEmpty) {
    return true;
  }
  final text = '${entry.headline}${entry.detail}'.toLowerCase();
  return text.contains('核对') ||
      text.contains('核实') ||
      text.contains('交叉') ||
      text.contains('验证');
}

bool _shouldEmitAnswerOrganizationFrame(
  AssistantJourney journey,
  AssistantJourneyStage? answerStage,
  List<AssistantJourneyEntry> answerEntries,
) {
  if (!journey.readiness.finalAnswerReady &&
      (answerStage == null ||
          answerStage.status == JourneyStageStatus.pending)) {
    return false;
  }
  return (answerStage != null && answerStage.summary.trim().isNotEmpty) ||
      answerEntries.any(
        (e) => e.headline.trim().isNotEmpty || e.detail.trim().isNotEmpty,
      );
}

String _pickJourneyHeadline({
  required AssistantJourneyStage? stage,
  required List<AssistantJourneyEntry> entries,
}) {
  if (entries.length > 1 && stage != null && stage.summary.trim().isNotEmpty) {
    return stage.summary.trim();
  }
  for (final e in entries) {
    if (e.headline.trim().isNotEmpty) {
      return e.headline.trim();
    }
  }
  return stage?.summary.trim() ?? '';
}

String _mergeJourneyEntryLines({
  required AssistantJourneyStage? stage,
  required List<AssistantJourneyEntry> entries,
  required bool understandingStage,
}) {
  final stageSummary = stage?.summary.trim() ?? '';
  final entryLines = <String>[];
  if (understandingStage) {
    for (final e in entries) {
      if (e.headline.trim().isNotEmpty) {
        entryLines.add(e.headline.trim());
      }
      if (e.detail.trim().isNotEmpty) {
        entryLines.add(e.detail.trim());
      }
    }
  } else {
    for (final e in entries) {
      final line = e.detail.trim().isNotEmpty
          ? e.detail.trim()
          : e.headline.trim();
      if (line.isNotEmpty) {
        entryLines.add(line);
      }
    }
  }
  final merged = entryLines.join('\n');
  if (understandingStage) {
    if (stageSummary.isNotEmpty && !merged.contains(stageSummary)) {
      return merged.isEmpty ? stageSummary : '$stageSummary\n$merged';
    }
    return merged;
  }
  final skipStagePreamble = entries.length > 1 && stageSummary.isNotEmpty;
  if (stageSummary.isNotEmpty && !skipStagePreamble) {
    if (merged.isEmpty) {
      return stageSummary;
    }
    if (!merged.contains(stageSummary)) {
      return '$stageSummary\n$merged';
    }
  }
  return merged;
}

List<String> _detailToKeyPoints(String detail) {
  return detail
      .split('\n')
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .take(8)
      .toList(growable: false);
}

List<RetrievalProcessingReference> _collectRetrievalReferences({
  required List<AssistantJourneyEntry> entries,
  required AssistantJourney journey,
}) {
  final out = <RetrievalProcessingReference>[];
  final seen = <String>{};
  void addFromJourneyRef(AssistantJourneyReference r) {
    final key = r.url.trim().isNotEmpty
        ? r.url.trim()
        : '${r.source.trim()}:${r.title.trim()}';
    if (key.trim().isEmpty || seen.contains(key)) {
      return;
    }
    seen.add(key);
    out.add(
      RetrievalProcessingReference(
        title: r.title.trim(),
        url: r.url.trim(),
        source: r.source.trim(),
      ),
    );
  }

  for (final e in entries) {
    for (final r in e.references) {
      addFromJourneyRef(r);
    }
  }
  for (final r in journey.referenceSummary.references) {
    addFromJourneyRef(r);
  }
  return out;
}

JourneyStageStatus _mergeBucketStatus({
  required AssistantJourneyStage? stage,
  required List<AssistantJourneyEntry> entries,
}) {
  final statuses = <JourneyStageStatus>[
    if (stage != null) stage.status,
    ...entries.map((e) => e.status),
  ];
  if (statuses.any(
    (s) => s == JourneyStageStatus.active || s == JourneyStageStatus.blocked,
  )) {
    return JourneyStageStatus.active;
  }
  if (statuses.any((s) => s == JourneyStageStatus.completed)) {
    return JourneyStageStatus.completed;
  }
  if (statuses.any((s) => s == JourneyStageStatus.skipped)) {
    return JourneyStageStatus.skipped;
  }
  return stage?.status ?? JourneyStageStatus.pending;
}

const List<ProcessStepId> assistantPrimaryProcessSteps = <ProcessStepId>[
  ProcessStepId.understanding,
  ProcessStepId.retrievalDesign,
  ProcessStepId.retrievalProcessing,
  ProcessStepId.answerOrganization,
];

const List<ProcessStepId> assistantVisibleProcessSteps = <ProcessStepId>[
  ProcessStepId.understanding,
  ProcessStepId.retrievalProcessing,
  ProcessStepId.answerOrganization,
];

JourneyStageId assistantJourneyStageForProcessStep(ProcessStepId stepId) {
  switch (stepId) {
    case ProcessStepId.understanding:
      return JourneyStageId.analyze;
    case ProcessStepId.retrievalDesign:
    case ProcessStepId.retrievalProcessing:
      return JourneyStageId.search;
    case ProcessStepId.answerOrganization:
      return JourneyStageId.answer;
    case ProcessStepId.unknown:
      return JourneyStageId.unknown;
  }
}

int assistantProcessStepOrder(ProcessStepId stepId) {
  switch (stepId) {
    case ProcessStepId.understanding:
      return 0;
    case ProcessStepId.retrievalDesign:
      return 1;
    case ProcessStepId.retrievalProcessing:
      return 2;
    case ProcessStepId.answerOrganization:
      return 3;
    case ProcessStepId.unknown:
      return 999;
  }
}

String assistantProcessFrameId(ProcessStepId stepId) {
  final wire = stepId.wireName.trim();
  return wire.isNotEmpty ? 'process.$wire' : 'process.unknown';
}

bool hasStructuredProcessTimeline(List<ProcessTimelineFrame> frames) {
  return frames.any((frame) => frame.hasVisibleContent);
}

ProcessTimelineFrame buildProcessTimelineFrame({
  required ProcessStepId stepId,
  JourneyStageStatus status = JourneyStageStatus.completed,
  String headline = '',
  String detail = '',
  List<RetrievalProcessingReference> references =
      const <RetrievalProcessingReference>[],
  RunArtifactsUnderstandingSnapshot understandingSnapshot =
      const RunArtifactsUnderstandingSnapshot(),
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
  RunArtifactsAnswerProcessing answerProcessing =
      const RunArtifactsAnswerProcessing(),
}) {
  return ProcessTimelineFrame(
    frameId: assistantProcessFrameId(stepId),
    stepId: stepId,
    status: status,
    order: assistantProcessStepOrder(stepId),
    headline: headline.trim(),
    detail: detail.trim(),
    references: references,
    understandingSnapshot: understandingSnapshot,
    retrievalProcessing: retrievalProcessing,
    answerProcessing: answerProcessing,
  );
}

List<ProcessTimelineFrame> normalizeProcessTimeline(
  List<ProcessTimelineFrame> frames,
) {
  final byStep = <ProcessStepId, ProcessTimelineFrame>{};
  for (final frame in frames) {
    final stepId = frame.stepId;
    if (stepId == ProcessStepId.unknown) continue;
    final normalized = frame.copyWith(
      frameId: frame.frameId.trim().isNotEmpty
          ? frame.frameId.trim()
          : assistantProcessFrameId(stepId),
      order: frame.order > 0 ? frame.order : assistantProcessStepOrder(stepId),
    );
    byStep[stepId] = normalized;
  }
  final ordered = byStep.values.toList(growable: false)
    ..sort((a, b) => a.order.compareTo(b.order));
  return List<ProcessTimelineFrame>.unmodifiable(ordered);
}

List<ProcessTimelineFrame> buildProcessTimelineFromSnapshots({
  List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
  RunArtifactsUnderstandingSnapshot understandingSnapshot =
      const RunArtifactsUnderstandingSnapshot(),
  RetrievalProcessingSnapshot retrievalProcessing =
      const RetrievalProcessingSnapshot(),
  RunArtifactsAnswerProcessing answerProcessing =
      const RunArtifactsAnswerProcessing(),
}) {
  final frames = <ProcessTimelineFrame>[];
  if (understandingSnapshot.userFacingSummary.trim().isNotEmpty ||
      understandingSnapshot.resolutionItems.any(
        (item) =>
            item.visibleInUnderstanding &&
            (item.detail.trim().isNotEmpty ||
                item.resolvedValue.trim().isNotEmpty),
      )) {
    final understandingDetail = understandingSnapshot.resolutionItems
        .where((item) => item.visibleInUnderstanding)
        .map((item) => item.detail.trim())
        .where((item) => item.isNotEmpty)
        .take(2)
        .join('\n');
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.understanding,
        headline: understandingSnapshot.userFacingSummary.trim(),
        detail: understandingDetail,
        understandingSnapshot: understandingSnapshot,
      ),
    );
  }

  if (understandingSnapshot.queryDesignSummary.trim().isNotEmpty ||
      understandingSnapshot.queryGroups.isNotEmpty) {
    final retrievalDesignDetail = understandingSnapshot.queryGroups
        .expand(
          (group) => group.queries
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .take(2),
        )
        .take(3)
        .join('\n');
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.retrievalDesign,
        headline: understandingSnapshot.queryDesignSummary.trim(),
        detail: retrievalDesignDetail,
        understandingSnapshot: understandingSnapshot,
      ),
    );
  }

  if (retrievalProcessing.processingSummary.trim().isNotEmpty ||
      retrievalProcessing.expansionReason.trim().isNotEmpty ||
      retrievalProcessing.acceptedReferences.isNotEmpty) {
    final retrievalDetail = retrievalProcessing.expansionReason.trim();
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.retrievalProcessing,
        headline: retrievalProcessing.processingSummary.trim(),
        detail: retrievalDetail,
        references: retrievalProcessing.acceptedReferences,
        retrievalProcessing: retrievalProcessing,
      ),
    );
  }

  if (answerProcessing.readinessSummary.trim().isNotEmpty ||
      answerProcessing.retrieveMoreReason.trim().isNotEmpty) {
    final answerDetail = answerProcessing.retrieveMoreReason.trim();
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.answerOrganization,
        headline: answerProcessing.readinessSummary.trim(),
        detail: answerDetail,
        answerProcessing: answerProcessing,
      ),
    );
  }
  final snapshotTimeline = normalizeProcessTimeline(frames);
  if (!hasStructuredProcessTimeline(processTimeline)) {
    return snapshotTimeline;
  }
  final mergedByStep = <ProcessStepId, ProcessTimelineFrame>{
    for (final frame in snapshotTimeline) frame.stepId: frame,
  };
  for (final frame in normalizeProcessTimeline(processTimeline)) {
    final fallback = mergedByStep[frame.stepId];
    if (fallback == null) {
      mergedByStep[frame.stepId] = frame;
      continue;
    }
    mergedByStep[frame.stepId] = fallback.copyWith(
      status: frame.status != JourneyStageStatus.pending
          ? frame.status
          : fallback.status,
      headline: frame.headline.trim().isNotEmpty
          ? frame.headline
          : fallback.headline,
      detail: frame.detail.trim().isNotEmpty ? frame.detail : fallback.detail,
      references: frame.references.isNotEmpty
          ? frame.references
          : fallback.references,
      understandingSnapshot: _firstStructuredUnderstandingSnapshot(
        <RunArtifactsUnderstandingSnapshot>[
          fallback.understandingSnapshot,
          frame.understandingSnapshot,
        ],
      ),
      retrievalProcessing: _hasStructuredMap(frame.retrievalProcessing.toJson())
          ? frame.retrievalProcessing
          : fallback.retrievalProcessing,
      answerProcessing: _hasStructuredMap(frame.answerProcessing.toJson())
          ? frame.answerProcessing
          : fallback.answerProcessing,
    );
  }
  return normalizeProcessTimeline(mergedByStep.values.toList(growable: false));
}

extension ProcessTimelineFrameCompat on ProcessTimelineFrame {
  bool get hasVisibleContent {
    return headline.trim().isNotEmpty ||
        detail.trim().isNotEmpty ||
        references.isNotEmpty ||
        _hasStructuredMap(understandingSnapshot.toJson()) ||
        _hasStructuredMap(retrievalProcessing.toJson()) ||
        _hasStructuredMap(answerProcessing.toJson());
  }

  ProcessTimelineFrame copyWith({
    String? frameId,
    ProcessStepId? stepId,
    JourneyStageStatus? status,
    int? order,
    String? headline,
    String? detail,
    List<RetrievalProcessingReference>? references,
    RunArtifactsUnderstandingSnapshot? understandingSnapshot,
    RetrievalProcessingSnapshot? retrievalProcessing,
    RunArtifactsAnswerProcessing? answerProcessing,
  }) {
    return ProcessTimelineFrame(
      frameId: frameId ?? this.frameId,
      stepId: stepId ?? this.stepId,
      status: status ?? this.status,
      order: order ?? this.order,
      headline: headline ?? this.headline,
      detail: detail ?? this.detail,
      references: references ?? this.references,
      understandingSnapshot:
          understandingSnapshot ?? this.understandingSnapshot,
      retrievalProcessing: retrievalProcessing ?? this.retrievalProcessing,
      answerProcessing: answerProcessing ?? this.answerProcessing,
    );
  }
}

List<ProcessTimelineFrame> buildVisibleProcessTimeline(
  List<ProcessTimelineFrame> canonical,
) {
  final normalized = normalizeProcessTimeline(canonical);
  if (normalized.isEmpty) {
    return const <ProcessTimelineFrame>[];
  }
  final byStep = <ProcessStepId, ProcessTimelineFrame>{
    for (final frame in normalized) frame.stepId: frame,
  };
  final understanding = _mergeVisibleUnderstandingFrame(
    understanding: byStep[ProcessStepId.understanding],
    retrievalDesign: byStep[ProcessStepId.retrievalDesign],
  );
  final visible = <ProcessTimelineFrame>[
    if (understanding != null && understanding.hasVisibleContent) understanding,
    ?byStep[ProcessStepId.retrievalProcessing],
    ?byStep[ProcessStepId.answerOrganization],
  ];
  return normalizeProcessTimeline(
    visible
        .asMap()
        .entries
        .map(
          (entry) => entry.value.copyWith(
            order: entry.key,
            frameId: assistantProcessFrameId(entry.value.stepId),
          ),
        )
        .toList(growable: false),
  );
}

List<ProcessTimelineFrame> rebuildCanonicalProcessTimelineFromVisible({
  required List<ProcessTimelineFrame> visibleProcessTimeline,
  List<ProcessTimelineFrame> seedProcessTimeline =
      const <ProcessTimelineFrame>[],
}) {
  final normalizedVisible = buildVisibleProcessTimeline(visibleProcessTimeline);
  final normalizedSeed = normalizeProcessTimeline(seedProcessTimeline);
  if (normalizedVisible.isEmpty) {
    return normalizedSeed;
  }
  final visibleByStep = <ProcessStepId, ProcessTimelineFrame>{
    for (final frame in normalizedVisible) frame.stepId: frame,
  };
  final seedByStep = <ProcessStepId, ProcessTimelineFrame>{
    for (final frame in normalizedSeed) frame.stepId: frame,
  };
  final understandingSnapshot = _firstStructuredUnderstandingSnapshot(
    <RunArtifactsUnderstandingSnapshot>[
      if (visibleByStep[ProcessStepId.understanding] case final understanding?)
        understanding.understandingSnapshot,
      if (seedByStep[ProcessStepId.understanding] case final understanding?)
        understanding.understandingSnapshot,
      if (seedByStep[ProcessStepId.retrievalDesign] case final retrievalDesign?)
        retrievalDesign.understandingSnapshot,
    ],
  );
  final retrievalProcessing =
      _firstStructuredRetrievalProcessing(<RetrievalProcessingSnapshot>[
        if (visibleByStep[ProcessStepId.retrievalProcessing]
            case final retrieval?)
          retrieval.retrievalProcessing,
        if (seedByStep[ProcessStepId.retrievalProcessing] case final retrieval?)
          retrieval.retrievalProcessing,
      ]);
  final answerProcessing =
      _firstStructuredAnswerProcessing(<RunArtifactsAnswerProcessing>[
        if (visibleByStep[ProcessStepId.answerOrganization] case final answer?)
          answer.answerProcessing,
        if (seedByStep[ProcessStepId.answerOrganization] case final answer?)
          answer.answerProcessing,
      ]);
  final rebuilt = buildProcessTimelineFromSnapshots(
    processTimeline: <ProcessTimelineFrame>[
      ...normalizedSeed,
      ...normalizedVisible,
    ],
    understandingSnapshot: understandingSnapshot,
    retrievalProcessing: retrievalProcessing,
    answerProcessing: answerProcessing,
  );
  final byStep = <ProcessStepId, ProcessTimelineFrame>{
    for (final frame in rebuilt) frame.stepId: frame,
  };
  final visibleUnderstanding = visibleByStep[ProcessStepId.understanding];
  final rebuiltRetrievalDesign = byStep[ProcessStepId.retrievalDesign];
  if (visibleUnderstanding != null &&
      rebuiltRetrievalDesign != null &&
      seedByStep[ProcessStepId.retrievalDesign] == null &&
      rebuiltRetrievalDesign.status == JourneyStageStatus.completed &&
      visibleUnderstanding.status != JourneyStageStatus.completed) {
    byStep[ProcessStepId.retrievalDesign] = rebuiltRetrievalDesign.copyWith(
      status: visibleUnderstanding.status,
    );
  }
  return normalizeProcessTimeline(byStep.values.toList(growable: false));
}

ProcessTimelineFrame? _mergeVisibleUnderstandingFrame({
  required ProcessTimelineFrame? understanding,
  required ProcessTimelineFrame? retrievalDesign,
}) {
  if (understanding == null && retrievalDesign == null) {
    return null;
  }
  final base = understanding ?? retrievalDesign!;
  final retrievalDesignSnapshot =
      retrievalDesign?.understandingSnapshot ??
      const RunArtifactsUnderstandingSnapshot();
  final mergedUnderstandingSnapshot = RunArtifactsUnderstandingSnapshot(
    intentSummary: _firstNonEmpty(<String>[
      base.understandingSnapshot.intentSummary,
      retrievalDesignSnapshot.intentSummary,
    ]),
    userFacingSummary: _firstNonEmpty(<String>[
      base.understandingSnapshot.userFacingSummary,
      base.headline.trim(),
    ]),
    concernPoints: base.understandingSnapshot.concernPoints.isNotEmpty
        ? base.understandingSnapshot.concernPoints
        : retrievalDesignSnapshot.concernPoints,
    emotionSignal: _firstNonEmpty(<String>[
      base.understandingSnapshot.emotionSignal,
      retrievalDesignSnapshot.emotionSignal,
    ]),
    queryDesignSummary: _firstNonEmpty(<String>[
      base.understandingSnapshot.queryDesignSummary,
      retrievalDesignSnapshot.queryDesignSummary,
    ]),
    queryGroups: base.understandingSnapshot.queryGroups.isNotEmpty
        ? base.understandingSnapshot.queryGroups
        : retrievalDesignSnapshot.queryGroups,
    resolutionItems: _mergeVisibleUnderstandingResolutionItems(
      base.understandingSnapshot.resolutionItems,
      retrievalDesignSnapshot.resolutionItems,
    ),
    assumptions: base.understandingSnapshot.assumptions.isNotEmpty
        ? base.understandingSnapshot.assumptions
        : retrievalDesignSnapshot.assumptions,
    mismatchSignal: _firstNonEmpty(<String>[
      base.understandingSnapshot.mismatchSignal,
      retrievalDesignSnapshot.mismatchSignal,
    ]),
    carryForwardFacts: base.understandingSnapshot.carryForwardFacts.isNotEmpty
        ? base.understandingSnapshot.carryForwardFacts
        : retrievalDesignSnapshot.carryForwardFacts,
    discardedAssumptions:
        base.understandingSnapshot.discardedAssumptions.isNotEmpty
        ? base.understandingSnapshot.discardedAssumptions
        : retrievalDesignSnapshot.discardedAssumptions,
  );
  return buildProcessTimelineFrame(
    stepId: ProcessStepId.understanding,
    status: _mergeVisibleStatus(<JourneyStageStatus>[
      base.status,
      if (retrievalDesign != null) retrievalDesign.status,
    ]),
    headline: mergedUnderstandingSnapshot.userFacingSummary.trim().isNotEmpty
        ? mergedUnderstandingSnapshot.userFacingSummary.trim()
        : base.headline.trim(),
    detail: base.detail.trim(),
    understandingSnapshot: mergedUnderstandingSnapshot,
  );
}

List<RunArtifactsUnderstandingResolutionItem>
_mergeVisibleUnderstandingResolutionItems(
  List<RunArtifactsUnderstandingResolutionItem> primary,
  List<RunArtifactsUnderstandingResolutionItem> fallback,
) {
  final merged = <RunArtifactsUnderstandingResolutionItem>[];
  final seen = <String>{};

  void absorb(List<RunArtifactsUnderstandingResolutionItem> items) {
    for (final item in items) {
      final key =
          '${item.kind.trim()}|${item.title.trim()}|${item.detail.trim()}|'
          '${item.resolvedValue.trim()}|${item.originalValue.trim()}|'
          '${item.source.trim()}|${item.defaultApplied}|'
          '${item.visibleInUnderstanding}';
      if (seen.add(key)) {
        merged.add(item);
      }
    }
  }

  absorb(primary);
  absorb(fallback);
  return merged;
}

JourneyStageStatus _mergeVisibleStatus(List<JourneyStageStatus> statuses) {
  if (statuses.any((status) => status == JourneyStageStatus.active)) {
    return JourneyStageStatus.active;
  }
  if (statuses.any((status) => status == JourneyStageStatus.blocked)) {
    return JourneyStageStatus.blocked;
  }
  if (statuses.every((status) => status == JourneyStageStatus.completed)) {
    return JourneyStageStatus.completed;
  }
  if (statuses.any((status) => status == JourneyStageStatus.completed)) {
    return JourneyStageStatus.active;
  }
  if (statuses.any((status) => status == JourneyStageStatus.skipped)) {
    return JourneyStageStatus.skipped;
  }
  return JourneyStageStatus.pending;
}

String _firstNonEmpty(List<String> values) {
  for (final value in values) {
    final trimmed = value.trim();
    if (trimmed.isNotEmpty) {
      return trimmed;
    }
  }
  return '';
}

RunArtifactsUnderstandingSnapshot _firstStructuredUnderstandingSnapshot(
  List<RunArtifactsUnderstandingSnapshot> candidates,
) {
  var merged = const RunArtifactsUnderstandingSnapshot();
  for (final candidate in candidates) {
    if (!_hasStructuredMap(candidate.toJson())) {
      continue;
    }
    if (!_hasStructuredMap(merged.toJson())) {
      merged = candidate;
      continue;
    }
    merged = RunArtifactsUnderstandingSnapshot(
      intentSummary: _firstNonEmpty(<String>[
        merged.intentSummary,
        candidate.intentSummary,
      ]),
      userFacingSummary: _firstNonEmpty(<String>[
        merged.userFacingSummary,
        candidate.userFacingSummary,
      ]),
      concernPoints: _mergeUniqueStrings(
        merged.concernPoints,
        candidate.concernPoints,
      ),
      emotionSignal: _firstNonEmpty(<String>[
        merged.emotionSignal,
        candidate.emotionSignal,
      ]),
      queryDesignSummary: _firstNonEmpty(<String>[
        merged.queryDesignSummary,
        candidate.queryDesignSummary,
      ]),
      queryGroups: _mergeUnderstandingQueryGroups(
        merged.queryGroups,
        candidate.queryGroups,
      ),
      resolutionItems: _mergeVisibleUnderstandingResolutionItems(
        merged.resolutionItems,
        candidate.resolutionItems,
      ),
      assumptions: _mergeUniqueStrings(
        merged.assumptions,
        candidate.assumptions,
      ),
      mismatchSignal: _firstNonEmpty(<String>[
        merged.mismatchSignal,
        candidate.mismatchSignal,
      ]),
      carryForwardFacts: _mergeUniqueStrings(
        merged.carryForwardFacts,
        candidate.carryForwardFacts,
      ),
      discardedAssumptions: _mergeUniqueStrings(
        merged.discardedAssumptions,
        candidate.discardedAssumptions,
      ),
    );
  }
  return merged;
}

RetrievalProcessingSnapshot _firstStructuredRetrievalProcessing(
  List<RetrievalProcessingSnapshot> candidates,
) {
  for (final candidate in candidates) {
    if (_hasStructuredMap(candidate.toJson())) {
      return candidate;
    }
  }
  return const RetrievalProcessingSnapshot();
}

RunArtifactsAnswerProcessing _firstStructuredAnswerProcessing(
  List<RunArtifactsAnswerProcessing> candidates,
) {
  for (final candidate in candidates) {
    if (_hasStructuredMap(candidate.toJson())) {
      return candidate;
    }
  }
  return const RunArtifactsAnswerProcessing();
}

bool _hasStructuredMap(Map<String, dynamic> value) {
  for (final item in value.values) {
    if (item is String && item.trim().isNotEmpty) return true;
    if (item is num && item != 0) return true;
    if (item is bool && item) return true;
    if (item is List && item.isNotEmpty) return true;
    if (item is Map && item.isNotEmpty) return true;
  }
  return false;
}

List<String> _mergeUniqueStrings(List<String> primary, List<String> fallback) {
  final merged = <String>[];
  final seen = <String>{};
  for (final value in <String>[...primary, ...fallback]) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      continue;
    }
    if (seen.add(trimmed)) {
      merged.add(trimmed);
    }
  }
  return merged;
}

List<RunArtifactsUnderstandingQueryGroup> _mergeUnderstandingQueryGroups(
  List<RunArtifactsUnderstandingQueryGroup> primary,
  List<RunArtifactsUnderstandingQueryGroup> fallback,
) {
  final merged = <RunArtifactsUnderstandingQueryGroup>[];
  final seen = <String>{};

  void absorb(List<RunArtifactsUnderstandingQueryGroup> groups) {
    for (final group in groups) {
      final queries = group.queries
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
      final key =
          '${group.dimension.trim()}|${queries.join("||")}|${group.why.trim()}';
      if (seen.add(key)) {
        merged.add(
          RunArtifactsUnderstandingQueryGroup(
            dimension: group.dimension,
            queries: queries,
            why: group.why,
          ),
        );
      }
    }
  }

  absorb(primary);
  absorb(fallback);
  return merged;
}

