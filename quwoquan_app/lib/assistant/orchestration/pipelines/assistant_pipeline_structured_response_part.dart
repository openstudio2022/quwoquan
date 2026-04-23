part of 'assistant_pipeline_engine.dart';

bool _hasStructuredContent(Map<String, dynamic> value) {
  for (final entry in value.entries) {
    final item = entry.value;
    if (item == null) continue;
    if (item is String && item.trim().isEmpty) continue;
    if (item is List && item.isEmpty) continue;
    if (item is Map && item.isEmpty) continue;
    return true;
  }
  return false;
}

String _firstNonEmptyText(Iterable<String?> values) {
  for (final value in values) {
    final trimmed = (value ?? '').trim();
    if (trimmed.isNotEmpty) return trimmed;
  }
  return '';
}

String _canonicalizeUnderstandingSnapshotDateAnchors(String text) {
  return text.trim();
}

String _mergeStableNarrativeFinalText({
  required String streamed,
  required String finalized,
}) {
  final streamedText = streamed.trim();
  final finalizedText = finalized.trim();
  if (streamedText.isEmpty) return finalizedText;
  if (finalizedText.isEmpty ||
      streamedText == finalizedText ||
      streamedText.startsWith(finalizedText))
    return streamedText;
  final overlap = _suffixPrefixOverlap(streamedText, finalizedText);
  return overlap > 0 && overlap < finalizedText.length
      ? '$streamedText${finalizedText.substring(overlap)}'.trim()
      : streamedText;
}

int _suffixPrefixOverlap(String left, String right) {
  final maxOverlap = left.length < right.length ? left.length : right.length;
  for (var overlap = maxOverlap; overlap > 0; overlap--) {
    if (left.substring(left.length - overlap) == right.substring(0, overlap))
      return overlap;
  }
  return 0;
}

String _sanitizeAnswerKeyFact(String raw) =>
    SafeReferenceNormalizer.normalizeFact(raw);

String _composeDisplayMarkdown(
  String plainText,
  List<AssistantUiReferenceWireDto> uiReferences,
) {
  if (uiReferences.isEmpty) {
    return plainText.trim();
  }
  return plainText.trim();
}

String _journeyUnderstandingEntryDetail({
  required RunArtifactsUnderstandingSnapshot snapshot,
  required String reasonShort,
}) {
  final fromItems = snapshot.resolutionItems
      .where((item) => item.visibleInUnderstanding)
      .map((item) => item.detail.trim())
      .where((item) => item.isNotEmpty)
      .take(2)
      .join('\n');
  return _firstNonEmptyText(<String?>[fromItems, reasonShort]);
}

JourneyStageStatus _journeyStageStatusForPipelineStep({
  required ProcessStepId step,
  required ProcessStepId blockedProcessStepId,
  required bool finalAnswerReady,
}) {
  if (step == ProcessStepId.answerOrganization) {
    return finalAnswerReady
        ? JourneyStageStatus.completed
        : JourneyStageStatus.blocked;
  }
  if (blockedProcessStepId == ProcessStepId.unknown) {
    return JourneyStageStatus.completed;
  }
  if (blockedProcessStepId == step) {
    return JourneyStageStatus.blocked;
  }
  final blockedOrder = assistantProcessStepOrder(blockedProcessStepId);
  final stepOrder = assistantProcessStepOrder(step);
  if (stepOrder < blockedOrder) return JourneyStageStatus.completed;
  if (stepOrder > blockedOrder) return JourneyStageStatus.pending;
  return JourneyStageStatus.completed;
}

/// 固定管线阶段：理解 → 检索设计 → 检索处理 → 成答（与 [assistant_journey_projector] 默认四段一致）。
/// 摘要只来自模型快照，不遍历 [projectedProcessTimelineWithBlock]（避免把末尾注入的阻塞帧当成独立阶段）。
List<Map<String, dynamic>> _buildPipelineJourneyStages({
  required RunArtifactsUnderstandingSnapshot understanding,
  required IntentGraph intentGraph,
  required RetrievalProcessingSnapshot retrieval,
  required String retrievalSummary,
  required bool finalAnswerReady,
  required String answerPlainText,
  required int referenceCount,
  required ProcessStepId blockedProcessStepId,
}) {
  final understandingSummary = _firstNonEmptyText(<String?>[
    understanding.userFacingSummary.trim(),
    intentGraph.userGoal.trim(),
  ]);
  final designSummary = understanding.intentSummary.trim();
  final processingSummary = _firstNonEmptyText(<String?>[
    retrievalSummary,
    retrieval.processingSummary.trim(),
  ]);
  return <Map<String, dynamic>>[
    <String, dynamic>{
      'stageId': JourneyStageId.analyze.wireName,
      'status': _journeyStageStatusForPipelineStep(
        step: ProcessStepId.understanding,
        blockedProcessStepId: blockedProcessStepId,
        finalAnswerReady: finalAnswerReady,
      ).wireName,
      'order': assistantProcessStepOrder(ProcessStepId.understanding),
      'summary': understandingSummary,
      'referenceCount': 0,
    },
    <String, dynamic>{
      'stageId': JourneyStageId.search.wireName,
      'status': _journeyStageStatusForPipelineStep(
        step: ProcessStepId.retrievalDesign,
        blockedProcessStepId: blockedProcessStepId,
        finalAnswerReady: finalAnswerReady,
      ).wireName,
      'order': assistantProcessStepOrder(ProcessStepId.retrievalDesign),
      'summary': designSummary,
      'referenceCount': 0,
    },
    <String, dynamic>{
      'stageId': JourneyStageId.verify.wireName,
      'status': _journeyStageStatusForPipelineStep(
        step: ProcessStepId.retrievalProcessing,
        blockedProcessStepId: blockedProcessStepId,
        finalAnswerReady: finalAnswerReady,
      ).wireName,
      'order': assistantProcessStepOrder(ProcessStepId.retrievalProcessing),
      'summary': processingSummary,
      'referenceCount': referenceCount,
    },
    <String, dynamic>{
      'stageId': JourneyStageId.answer.wireName,
      'status': _journeyStageStatusForPipelineStep(
        step: ProcessStepId.answerOrganization,
        blockedProcessStepId: blockedProcessStepId,
        finalAnswerReady: finalAnswerReady,
      ).wireName,
      'order': assistantProcessStepOrder(ProcessStepId.answerOrganization),
      'summary': answerPlainText.trim(),
      'referenceCount': referenceCount,
    },
  ];
}

String _buildEvidenceBindingLabel({
  required String title,
  required String source,
  required String url,
}) {
  final candidate = _firstNonEmptyText(<String?>[title, source]);
  if (candidate.isNotEmpty) return candidate;
  return url.isNotEmpty ? url : 'evidence';
}

String _trimTrailingSlashes(String input) {
  var output = input.trim();
  while (output.endsWith('/')) {
    output = output.substring(0, output.length - 1).trimRight();
  }
  return output;
}

String _inferPrimaryCity(IntentGraph intentGraph) {
  final contextCity =
      (intentGraph.contextSlots['city'] as String?)?.trim() ?? '';
  if (contextCity.isNotEmpty) return contextCity;
  for (final task in intentGraph.queryTasks) {
    for (final anchor in task.entityAnchors) {
      final trimmed = anchor.trim();
      if (trimmed.isNotEmpty) return trimmed;
    }
  }
  for (final anchor in intentGraph.entityAnchors) {
    final trimmed = anchor.trim();
    if (trimmed.isNotEmpty) return trimmed;
  }
  final target = intentGraph.targetObject.trim();
  if (target.isNotEmpty) return target;
  return intentGraph.userGoal.trim();
}

String _buildRetrievalDesignDetail({
  required IntentGraph intentGraph,
  required Map<String, dynamic> answerPayload,
}) {
  final payloadIntentGraph = AssistantAnswerPayloadReadView(
    answerPayload,
  ).asTypedOutput.intentGraph;
  final queryTasks = payloadIntentGraph?.queryTasks.isNotEmpty == true
      ? payloadIntentGraph!.queryTasks
      : intentGraph.queryTasks;
  final lines = <String>[];
  final seen = <String>{};
  for (final task in queryTasks) {
    final line = _queryTaskDesignLine(task);
    if (line.isEmpty || !seen.add(line)) {
      continue;
    }
    lines.add(line);
    if (lines.length >= 2) {
      break;
    }
  }
  return lines.join('\n');
}

String _buildRetrievalDesignNarrativeFallback(Iterable<QueryTask> queryTasks) {
  final tokens = <String>[];
  final seen = <String>{};
  for (final task in queryTasks) {
    final token = _queryTaskNarrativeToken(task);
    final normalized = _normalizedCompactText(token);
    if (normalized.isEmpty || !seen.add(normalized)) {
      continue;
    }
    tokens.add(token);
    if (tokens.length >= 2) {
      break;
    }
  }
  if (tokens.isEmpty) {
    return '';
  }
  if (tokens.length == 1) {
    return '接下来先沿着${tokens.first}这条线继续核对。';
  }
  return '接下来先沿着${tokens.first}和${tokens[1]}两条线继续核对。';
}

String _queryTaskNarrativeToken(QueryTask task) {
  final dimension = task.dimensionLabel.trim();
  if (dimension.isNotEmpty) {
    return dimension;
  }
  final label = task.effectiveLabel.trim();
  if (label.isNotEmpty) {
    return label;
  }
  return task.query.trim();
}

String _queryTaskDesignLine(QueryTask task) {
  final query = task.query.trim();
  final label = task.effectiveLabel.trim();
  final anchors = task.entityAnchors
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toSet()
      .toList(growable: false);
  final prefixParts = <String>[
    if (anchors.isNotEmpty) anchors.join(' / '),
    if (label.isNotEmpty &&
        _normalizedCompactText(label) != _normalizedCompactText(query))
      label,
  ];
  final prefix = prefixParts.join('｜');
  if (query.isEmpty) {
    return prefix.isNotEmpty ? '- $prefix' : '';
  }
  if (prefix.isEmpty ||
      _normalizedCompactText(prefix) == _normalizedCompactText(query)) {
    return '- $query';
  }
  return '- $prefix｜$query';
}

String _normalizedCompactText(String raw) {
  return raw.trim().toLowerCase().replaceAll(
    RegExp(r'[\s:：|｜/、,，。！？!?._-]+'),
    '',
  );
}

class _JourneyNarrativeText {
  const _JourneyNarrativeText({this.headline = '', this.detail = ''});

  final String headline;
  final String detail;
}

_JourneyNarrativeText _resolveRetrievalJourneyNarrative(
  AssistantDisplayState displayState,
  RetrievalProcessingSnapshot retrievalProcessing,
) {
  final processBlocks = displayState.process.blocks;
  AssistantProcessDisplayBlock? block;
  for (final item in processBlocks) {
    if (item.stepId == ProcessStepId.retrievalProcessing &&
        item.kind == ProcessDisplayBlockKind.summary &&
        (item.title.trim().isNotEmpty || item.body.trim().isNotEmpty)) {
      block = item;
      break;
    }
  }
  block ??= processBlocks.firstWhere(
    (item) =>
        item.stepId == ProcessStepId.retrievalProcessing &&
        (item.title.trim().isNotEmpty || item.body.trim().isNotEmpty),
    orElse: () => const AssistantProcessDisplayBlock(blockId: ''),
  );
  return _JourneyNarrativeText(
    headline: _firstNonEmptyText(<String?>[
      block.title,
      retrievalProcessing.processingSummary,
    ]),
    detail: _firstNonEmptyText(<String?>[
      _sanitizeRetrievalJourneyDetail(block.body),
      _sanitizeRetrievalJourneyDetail(retrievalProcessing.expansionReason),
    ]),
  );
}

String _sanitizeRetrievalJourneyDetail(String raw) {
  final trimmed = raw.trim();
  if (trimmed == 'blocked_but_renderable' || trimmed == 'blocked_closed') {
    return '';
  }
  return trimmed;
}

Map<String, dynamic> _normalizedUnderstandingSnapshotMap({
  required Map<String, dynamic> raw,
  required IntentGraph intentGraph,
  required String latestUserQuery,
}) {
  if (!_hasStructuredContent(raw)) {
    return const <String, dynamic>{};
  }
  final parsed = RunArtifactsUnderstandingSnapshot.fromJson(raw);
  final concernPoints = parsed.concernPoints.isNotEmpty
      ? parsed.concernPoints
      : <String>[...intentGraph.hardConstraints, ...intentGraph.softConstraints]
            .where((item) => item.trim().isNotEmpty)
            .take(4)
            .toList(growable: false);
  final canonicalQuery = _firstNonEmptyText(<String?>[
    intentGraph.queryNormalization.rewrittenQuery,
    intentGraph.queryNormalization.normalizedQuery,
    intentGraph.queryTasks.isNotEmpty ? intentGraph.queryTasks.first.query : '',
  ]);
  final parsedIntentSummary = parsed.intentSummary.trim();
  final intentSummary = parsedIntentSummary.isNotEmpty
      ? parsedIntentSummary
      : _firstNonEmptyText(<String?>[
          intentGraph.userGoal,
          intentGraph.userJobToBeDone,
          intentGraph.targetObject,
          latestUserQuery,
          canonicalQuery,
        ]);
  final parsedUserFacingSummary = parsed.userFacingSummary.trim();
  final userFacingSummary = parsedUserFacingSummary.isNotEmpty
      ? parsedUserFacingSummary
      : _firstNonEmptyText(<String?>[
          parsedIntentSummary,
          intentSummary,
          intentGraph.userGoal,
          intentGraph.userJobToBeDone,
          intentGraph.targetObject,
          latestUserQuery,
          canonicalQuery,
        ]);
  return RunArtifactsUnderstandingSnapshot(
    intentSummary: _canonicalizeUnderstandingSnapshotDateAnchors(intentSummary),
    userFacingSummary: _canonicalizeUnderstandingSnapshotDateAnchors(
      userFacingSummary,
    ),
    concernPoints: concernPoints,
    emotionSignal: parsed.emotionSignal,
    resolutionItems: parsed.resolutionItems,
    assumptions: parsed.assumptions,
    mismatchSignal: parsed.mismatchSignal,
    carryForwardFacts: parsed.carryForwardFacts,
    discardedAssumptions: parsed.discardedAssumptions,
  ).toJson();
}

SlotStateSnapshot _buildSlotStateSnapshot({
  required String domainId,
  required SlotStateSnapshot previousSlotState,
  required IntentGraph intentGraph,
  required List<AnswerEvidenceBinding> groundingBindings,
}) {
  final mergedSlots = <String, dynamic>{
    ...previousSlotState.slots,
    ...intentGraph.contextSlots,
  };
  final mergedValues = <String, SlotValueSnapshot>{
    ...previousSlotState.slotValues,
  };
  final groundingEvidenceIds = groundingBindings
      .map((item) => item.evidenceId.isNotEmpty ? item.evidenceId : item.url)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  final inferredCity = _inferPrimaryCity(intentGraph);
  if (inferredCity.isNotEmpty) {
    mergedSlots['city'] = inferredCity;
    mergedValues['city'] = SlotValueSnapshot(
      slotId: 'city',
      value: inferredCity,
      source: 'intent_graph',
      confidence: 1.0,
      updatedAt: DateTime.now().toIso8601String(),
      evidenceIds: groundingEvidenceIds,
    );
  }
  for (final entry in intentGraph.contextSlots.entries) {
    final key = entry.key.toString().trim();
    if (key.isEmpty) continue;
    final value = entry.value;
    mergedValues[key] = SlotValueSnapshot(
      slotId: key,
      value: value,
      source: 'intent_graph',
      confidence: 1.0,
      updatedAt: DateTime.now().toIso8601String(),
    );
  }
  return SlotStateSnapshot(
    domainId: domainId,
    slots: mergedSlots,
    slotValues: mergedValues,
    missingSlots: previousSlotState.missingSlots,
    updatedAt: DateTime.now().toIso8601String(),
  );
}

List<RunArtifactsUnderstandingResolutionItem>
_deriveResolutionItemsFromIntentGraph(IntentGraph intentGraph) {
  final items = <RunArtifactsUnderstandingResolutionItem>[];
  final explicitDate = _firstUnderstandingSnapshotExplicitDate(intentGraph);
  if (explicitDate.isNotEmpty) {
    items.add(
      RunArtifactsUnderstandingResolutionItem(
        kind: 'temporal_anchor',
        title: explicitDate,
        detail: explicitDate,
        resolvedValue: explicitDate,
        visibleInUnderstanding: true,
      ),
    );
  }
  return items;
}

List<String> _buildAnswerKeyFacts({
  required Map<String, dynamic> answerPayload,
  required List<EvidenceLedgerEntry> evidenceLedger,
}) {
  final fromPayload = AssistantAnswerPayloadReadView(answerPayload).evidenceMaps
      .map((item) {
        final claim = (item['claim'] as String?)?.trim() ?? '';
        final text = (item['text'] as String?)?.trim() ?? '';
        return _sanitizeAnswerKeyFact(claim.isNotEmpty ? claim : text);
      })
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  if (fromPayload.isNotEmpty) return fromPayload;
  final fromLedger = evidenceLedger
      .map(
        (entry) => _sanitizeAnswerKeyFact(
          entry.snippet.isNotEmpty ? entry.snippet : entry.title,
        ),
      )
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  if (fromLedger.isNotEmpty) return fromLedger;
  final fallbackText = _sanitizeAnswerKeyFact(
    ((answerPayload['userMarkdown'] as String?)?.trim().isNotEmpty == true
            ? (answerPayload['userMarkdown'] as String).trim()
            : ((answerPayload['result'] as Map?)?['text'] as String?)
                  ?.trim()) ??
        '',
  );
  return fallbackText.isNotEmpty ? <String>[fallbackText] : const <String>[];
}

String _firstUnderstandingSnapshotExplicitDate(IntentGraph intentGraph) {
  final qn = intentGraph.queryNormalization;
  for (final candidate in <String>[
    qn.timePoint,
    qn.timeRangeStart,
    qn.timeRangeEnd,
  ]) {
    if (candidate.trim().isNotEmpty) {
      return _canonicalizeUnderstandingSnapshotDateAnchors(candidate.trim());
    }
  }
  for (final task in intentGraph.queryTasks) {
    if (task.timePoint.trim().isNotEmpty)
      return _canonicalizeUnderstandingSnapshotDateAnchors(
        task.timePoint.trim(),
      );
  }
  return '';
}

extension AssistantPipelineStructuredResponseAssemblyCore
    on LocalPhaseExecutionOwner {
  Future<Map<String, dynamic>> buildStructuredResponsePayload({
    required AssistantRunRequest request,
    required ContextAssemblyResult contextAssembly,
    required SynthesisReadinessResult synthesisReadiness,
    required dynamic result,
    required IntentGraph intentGraph,
    required List<SkillRun> skillRuns,
    required AggregationState aggregationState,
    required SkillRouteOutput skillRoute,
    required List<SubagentPlan> subagentPlan,
    required List<AssistantSubagentRunRecord> subagentRuns,
    required SkillSynthesisInput skillSynthesisInput,
    required SkillSynthesisOutput skillSynthesisOutput,
    required DialogueRoundScript dialogueRoundScript,
    required List<String> candidateDomains,
    required SkillExecutionShell skillExecutionShell,
    required String templateVersionUsed,
    required String domainCatalogVersion,
    required String sessionId,
    required Map<String, dynamic> retrievalPolicy,
    required AnswerBoundaryPolicy answerBoundaryPolicy,
    required SlotStateSnapshot previousSlotState,
    Map<String, dynamic> carriedUnderstandingSnapshot =
        const <String, dynamic>{},
    Map<String, dynamic> carriedRetrievalProcessing = const <String, dynamic>{},
    Map<String, dynamic> carriedHistoricalThinkingSnapshot =
        const <String, dynamic>{},
    String streamedRetrievalProcessingSummary = '',
    String streamedAnswerReadinessSummary = '',
    Map<String, dynamic> phaseOneRoutingDiagnostics = const <String, dynamic>{},
    DomainPolicyBundle? previousDomainPolicyBundle,
    ProcessStepId blockedProcessStepId = ProcessStepId.unknown,
    String blockedProcessMessage = '',
    void Function(AssistantTraceEvent event)? onTraceEvent,
    String? runId,
    String? traceId,
  }) async {
    final traces =
        (result.traces as List?)?.whereType<AssistantTraceEvent>().toList(
          growable: false,
        ) ??
        const <AssistantTraceEvent>[];
    final answerPayload = parseAnswerPayload(
      rawFinalText: result.finalText as String? ?? '',
      traces: traces,
    );
    final answerPayloadView = AssistantAnswerPayloadReadView(answerPayload);
    final structuredTurn = answerPayloadView.asTypedOutput;
    final toolResults = traces
        .where((event) => event.type == AssistantTraceEventType.toolResult)
        .map(AssistantToolResultRow.fromTraceEvent)
        .toList(growable: false);
    final evidenceLedger = _baselineKernel.buildEvidenceLedger(
      domainId: dialogueRoundScript.domainId,
      toolResults: _toolResultsForEvidenceLedger(toolResults),
      slotState: previousSlotState,
      retrievalPolicy: retrievalPolicy,
    );
    final uiReferences = _buildUiReferences(
      toolResults,
      isRealtimeLike: isRealtimeLikeRequest(
        fallbackProblemClass: intentGraph.problemClassWireName,
        answerPayload: answerPayload,
      ),
    );
    final fallbackUiReferences = uiReferences.isNotEmpty
        ? uiReferences
        : _buildUiReferencesFromLedger(
            evidenceLedger,
            toolResults: toolResults
                .map((item) => item.toJson())
                .toList(growable: false),
            isRealtimeLike: isRealtimeLikeRequest(
              fallbackProblemClass: intentGraph.problemClassWireName,
              answerPayload: answerPayload,
            ),
          );
    final effectiveUiReferences = fallbackUiReferences.isNotEmpty
        ? fallbackUiReferences
        : uiReferences;
    final answerText = _firstNonEmptyText(<String?>[
      (answerPayload['userMarkdown'] as String?)?.trim(),
      skillSynthesisOutput.answerMarkdown.trim(),
      ((answerPayload['result'] as Map?)?['text'] as String?)?.trim(),
      ((answerPayload['result'] as Map?)?['summary'] as String?)?.trim(),
      (result.finalText as String?)?.trim(),
    ]);
    final renderedText = answerText.isNotEmpty
        ? answerText
        : assistantPipelineDefaultFailureMessageForStep(
            blockedProcessStepId == ProcessStepId.answerOrganization
                ? ProcessStepId.answerOrganization
                : ProcessStepId.unknown,
          );
    final messageKind = _resolveMessageKind(
      answerPayload: answerPayload,
      resultText: renderedText,
    );
    final isFallbackOutput = messageKind == AssistantMessageKind.fallback;
    final inferredCity = _inferPrimaryCity(intentGraph);
    final reasonShort = (answerPayload['reasonShort'] as String?)?.trim() ?? '';
    final pendingClarifications = skillSynthesisInput.pendingClarifications
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    final syntheticUiReferences = !isFallbackOutput
        ? effectiveUiReferences
        : const <AssistantUiReferenceWireDto>[];
    final displayMarkdown = _composeDisplayMarkdown(
      renderedText,
      syntheticUiReferences,
    );
    final projectedUnderstandingSnapshot = _buildUnderstandingSnapshot(
      raw: <String, dynamic>{
        ...carriedUnderstandingSnapshot,
        ...?((answerPayload['understandingSnapshot'] as Map?)
            ?.cast<String, dynamic>()),
      },
      intentGraph: intentGraph,
      latestUserQuery: request.messages.isNotEmpty
          ? request.messages.last.content
          : '',
    );
    final retrievalDesignDetail = _buildRetrievalDesignDetail(
      intentGraph: intentGraph,
      answerPayload: answerPayload,
    );
    final mergedRetrievalProcessing = <String, dynamic>{
      ...carriedRetrievalProcessing,
      ...?((answerPayload['retrievalProcessing'] as Map?)
          ?.cast<String, dynamic>()),
    };
    final mergedAnswerProcessing = <String, dynamic>{
      ...?((answerPayload['answerProcessing'] as Map?)
          ?.cast<String, dynamic>()),
    };
    final projectedRetrievalProcessing = _buildRetrievalProcessingSnapshot(
      processing: mergedRetrievalProcessing,
      streamedProcessingSummary: streamedRetrievalProcessingSummary,
      uiReferences: effectiveUiReferences,
      toolResults: toolResults,
      evidenceLedger: evidenceLedger,
    );
    final structuredAnswerReadyCandidate = _hasRenderableAnswerPayload(
      payload: answerPayload,
      turn: structuredTurn,
      projectionRenderableContent: renderedText.trim().isNotEmpty,
    );
    final structuredAnswerMaterializedCandidate =
        structuredAnswerReadyCandidate &&
        (!answerBoundaryPolicy.evidenceRequired ||
            _hasEvidencePayloadCandidate(
              retrievalProcessing: projectedRetrievalProcessing,
              evidenceLedger: evidenceLedger,
              toolResults: toolResults,
            ));
    final structuredFinalAnswerModeCandidate = _resolveStructuredFinalAnswerMode(
      turn: structuredTurn,
      answerPayloadView: answerPayloadView,
      answerBoundaryPolicy: answerBoundaryPolicy,
      structuredAnswerMaterializedCandidate:
          structuredAnswerMaterializedCandidate,
    );
    final structuredAskUserCandidate =
        structuredTurn.decision.nextAction == AssistantNextAction.askUser ||
        structuredTurn.hasAskUser;
    final projectedStateCandidate = _buildProjectedConversationStateDecision(
      aggregationState: aggregationState,
      answerBoundaryPolicy: answerBoundaryPolicy,
      synthesisReadiness: synthesisReadiness,
      blockedProcessStepId: blockedProcessStepId,
      structuredAnswerMaterializedCandidate:
          structuredAnswerMaterializedCandidate,
      structuredFinalAnswerModeCandidate: structuredFinalAnswerModeCandidate,
      structuredAskUserCandidate: structuredAskUserCandidate,
    );
    final evidenceEvaluation = _baselineKernel.evaluateEvidence(
      ledger: evidenceLedger,
      evidenceRequired: answerBoundaryPolicy.evidenceRequired,
      authorityRequired: answerBoundaryPolicy.authorityRequired,
      freshnessHoursMax: answerBoundaryPolicy.freshnessHoursMax,
      requiredDimensions: answerBoundaryPolicy.requiredDimensions,
      blockingDimensions: answerBoundaryPolicy.blockingDimensions,
    );
    final resultDegraded = result is ReactRuntimeResult ? result.degraded : false;
    final retrievalOutcome = _retrievalOutcomeResolver.resolve(
      policy: answerBoundaryPolicy,
      retrievalProcessing: projectedRetrievalProcessing,
      evidenceEvaluation: evidenceEvaluation,
      synthesisReadiness: synthesisReadiness,
      queryTasks: intentGraph.queryTasks,
      toolResults: toolResults,
      terminalPayloadComplete: true,
      degraded: resultDegraded,
    );
    final projectedAnswerGateDecision = _answerGateResolver.resolve(
      retrievalOutcome: retrievalOutcome,
      conversationStateDecision: projectedStateCandidate,
      renderableAnswer: renderedText.trim().isNotEmpty,
      degraded: resultDegraded,
      terminalPayloadComplete: retrievalOutcome.terminalPayloadComplete,
    );
    final projectedConversationStateDecision =
        _reconcileConversationStateDecisionWithGate(
          base: projectedStateCandidate,
          gate: projectedAnswerGateDecision,
        );
    final journeyReadiness = AssistantJourneyReadiness(
      nextAction: projectedConversationStateDecision.nextActionType,
      finalAnswerMode: projectedConversationStateDecision.finalAnswerModeType,
      answerEligibility:
          projectedConversationStateDecision.answerEligibilityType,
      finalAnswerReady: projectedConversationStateDecision.finalAnswerReady,
      clarificationNeeded:
          aggregationState.clarificationNeeded ||
          projectedConversationStateDecision.nextActionType ==
              AssistantNextAction.askUser,
      needExpansion: aggregationState.needExpansion,
    );
    final evidenceSummary = _firstNonEmptyText(<String?>[
      retrievalOutcome.summary.trim(),
      projectedAnswerGateDecision.reason.trim(),
      evidenceEvaluation.summary.trim(),
      synthesisReadiness.reason.trim(),
    ]);
    final shouldPromptForClarification =
        pendingClarifications.isNotEmpty &&
        (skillSynthesisOutput.partialCompletionState.trim() ==
                'needs_clarification' ||
            projectedConversationStateDecision.nextActionWireName ==
                AssistantNextAction.askUser.wireName ||
            aggregationState.clarificationNeeded);
    final resolvedFollowupPrompt = _firstNonEmptyText(<String?>[
      (answerPayload['followupPrompt'] as String?)?.trim(),
      if (shouldPromptForClarification) '还需要你一次性补充这些信息：',
      skillSynthesisOutput.followUpSuggestions.join('\n').trim(),
    ]);
    final resolvedActionHints =
        skillSynthesisOutput.followUpSuggestions.isNotEmpty
        ? skillSynthesisOutput.followUpSuggestions
        : shouldPromptForClarification
        ? pendingClarifications
        : normalizeStringList(answerPayload['actionHints']);
    final projectedAnswerProcessing = _buildAnswerProcessingSnapshot(
      raw: mergedAnswerProcessing,
      streamedReadinessSummary: streamedAnswerReadinessSummary,
      synthesisReadiness: synthesisReadiness,
      stateDecision: projectedConversationStateDecision,
      evidenceEvaluation: evidenceEvaluation,
      evidenceLedger: evidenceLedger,
      answerPayload: answerPayload,
    );
    final projectedProcessTimeline = buildProcessTimelineFromSnapshots(
      processTimeline: <ProcessTimelineFrame>[
        if (projectedUnderstandingSnapshot.retrievalDesignNarrative.trim().isNotEmpty ||
            retrievalDesignDetail.isNotEmpty)
          buildProcessTimelineFrame(
            stepId: ProcessStepId.retrievalDesign,
            headline:
                projectedUnderstandingSnapshot.retrievalDesignNarrative.trim(),
            detail: retrievalDesignDetail,
            understandingSnapshot: projectedUnderstandingSnapshot,
          ),
      ],
      understandingSnapshot: projectedUnderstandingSnapshot,
      retrievalProcessing: projectedRetrievalProcessing,
      answerProcessing: projectedAnswerProcessing,
    );
    final projectedRetrievalFrameReferences = syntheticUiReferences
        .map(
          (item) => RetrievalProcessingReference(
            title: item.title.trim(),
            url: item.url.trim(),
            source: item.source.trim(),
            snippet: item.snippet.trim(),
          ),
        )
        .where(
          (item) =>
              item.title.isNotEmpty ||
              item.url.isNotEmpty ||
              item.source.isNotEmpty,
        )
        .toList(growable: false);
    final projectedProcessTimelineWithReferences = projectedProcessTimeline
        .map((frame) {
          if (frame.stepId != ProcessStepId.retrievalProcessing ||
              projectedRetrievalFrameReferences.isEmpty) {
            return frame;
          }
          return frame.copyWith(references: projectedRetrievalFrameReferences);
        })
        .toList(growable: false);
    final projectedProcessTimelineWithBlock =
        blockedProcessStepId == ProcessStepId.unknown
        ? projectedProcessTimelineWithReferences
        : <ProcessTimelineFrame>[
            ...projectedProcessTimelineWithReferences.where(
              (frame) => frame.stepId != blockedProcessStepId,
            ),
            buildProcessTimelineFrame(
              stepId: blockedProcessStepId,
              status: JourneyStageStatus.blocked,
              headline: blockedProcessMessage.isNotEmpty
                  ? blockedProcessMessage
                  : assistantPipelineDefaultFailureMessageForStep(
                      blockedProcessStepId,
                    ),
              detail: answerBoundaryPolicy.allowBoundedAnswer
                  ? 'blocked_but_renderable'
                  : 'blocked_closed',
              references:
                  blockedProcessStepId == ProcessStepId.retrievalProcessing
                  ? projectedRetrievalFrameReferences
                  : const <RetrievalProcessingReference>[],
              answerProcessing: _buildAnswerProcessingSnapshot(
                raw: mergedAnswerProcessing,
                streamedReadinessSummary: streamedAnswerReadinessSummary,
                synthesisReadiness: synthesisReadiness,
                stateDecision: projectedConversationStateDecision,
                evidenceEvaluation: evidenceEvaluation,
                evidenceLedger: evidenceLedger,
                answerPayload: answerPayload,
              ),
            ),
          ];
    final projectedDisplayState = buildAssistantDisplayState(
      processTimeline: projectedProcessTimelineWithBlock,
      understandingSnapshot: projectedUnderstandingSnapshot,
      retrievalProcessing: projectedRetrievalProcessing,
      answerProcessing: projectedAnswerProcessing,
      answerMarkdown: displayMarkdown,
      answerPlainText: renderedText,
      finalAnswerReady: journeyReadiness.finalAnswerReady,
    );
    final projectedRetrievalNarrative = _resolveRetrievalJourneyNarrative(
      projectedDisplayState,
      projectedRetrievalProcessing,
    );
    final retrievalJourneyDetail = projectedRetrievalNarrative.detail.trim();
    final journeyStages = _buildPipelineJourneyStages(
      understanding: projectedUnderstandingSnapshot,
      intentGraph: intentGraph,
      retrieval: projectedRetrievalProcessing,
      retrievalSummary: projectedRetrievalNarrative.headline,
      finalAnswerReady: journeyReadiness.finalAnswerReady,
      answerPlainText: renderedText,
      referenceCount: effectiveUiReferences.length,
      blockedProcessStepId: blockedProcessStepId,
    );
    final response = <String, dynamic>{
      ...answerPayload,
      'finalText': renderedText,
      'displayPlainText': renderedText,
      'displayMarkdown': displayMarkdown,
      'messageKind': messageKind.wireName,
      'intentGraph': intentGraph.toJson(),
      'primarySkill': intentGraph.primarySkill,
      'skillRoute': skillRoute.toJson(),
      'pendingClarifications': pendingClarifications,
      'understandingSnapshot': projectedUnderstandingSnapshot.toJson(),
      'finalAnswerMode':
          projectedConversationStateDecision.finalAnswerModeWireName,
      assistantRetrievalOutcomeField: retrievalOutcome.toJson(),
      assistantAnswerGateDecisionField: projectedAnswerGateDecision.toJson(),
      'displayState': projectedDisplayState.toJson(),
      'followupPrompt': resolvedFollowupPrompt,
      'actionHints': resolvedActionHints,
      'decision': <String, dynamic>{
        'nextAction': projectedConversationStateDecision.nextActionWireName,
        'messageKind': messageKind.wireName,
        'finalAnswerMode':
            projectedConversationStateDecision.finalAnswerModeWireName,
      },
      'conversationStateDecision': projectedConversationStateDecision.toJson(),
      'answerEligibility':
          projectedConversationStateDecision.answerEligibilityWireName,
      'journey': <String, dynamic>{
        'stages': journeyStages,
        'entries': <Map<String, dynamic>>[
          <String, dynamic>{
            'entryId': 'understanding_${dialogueRoundScript.domainId}',
            'stageId': JourneyStageId.analyze.wireName,
            'kind': JourneyEntryKind.narrative.wireName,
            'status': _journeyStageStatusForPipelineStep(
              step: ProcessStepId.understanding,
              blockedProcessStepId: blockedProcessStepId,
              finalAnswerReady: journeyReadiness.finalAnswerReady,
            ).wireName,
            'order': 0,
            'headline': projectedUnderstandingSnapshot.userFacingSummary.trim(),
            'detail': _journeyUnderstandingEntryDetail(
              snapshot: projectedUnderstandingSnapshot,
              reasonShort: reasonShort,
            ),
            'references': <Map<String, dynamic>>[],
            'provenance': <String, dynamic>{
              'phaseId': 'understanding',
              'actionCode': 'compose_answer',
              'reasonCode': 'answer_organization',
              'toolName': 'pipeline',
              'source': 'structured_response',
            },
          },
          <String, dynamic>{
            'entryId': 'retrieval_design_${dialogueRoundScript.domainId}',
            'stageId': JourneyStageId.search.wireName,
            'kind': JourneyEntryKind.narrative.wireName,
            'status': _journeyStageStatusForPipelineStep(
              step: ProcessStepId.retrievalDesign,
              blockedProcessStepId: blockedProcessStepId,
              finalAnswerReady: journeyReadiness.finalAnswerReady,
            ).wireName,
            'order': 1,
            'headline':
                projectedUnderstandingSnapshot.retrievalDesignNarrative.trim(),
            'detail': retrievalDesignDetail,
            'references': <Map<String, dynamic>>[],
            'provenance': <String, dynamic>{
              'phaseId': 'understanding',
              'actionCode': 'compose_answer',
              'reasonCode': 'prepare_delivery',
              'toolName': 'pipeline',
              'source': 'structured_response',
            },
          },
          <String, dynamic>{
            'entryId': 'retrieval_processing_${dialogueRoundScript.domainId}',
            'stageId': JourneyStageId.verify.wireName,
            'kind': JourneyEntryKind.narrative.wireName,
            'status': _journeyStageStatusForPipelineStep(
              step: ProcessStepId.retrievalProcessing,
              blockedProcessStepId: blockedProcessStepId,
              finalAnswerReady: journeyReadiness.finalAnswerReady,
            ).wireName,
            'order': 2,
            'headline': projectedRetrievalNarrative.headline,
            'detail': retrievalJourneyDetail,
            'references': syntheticUiReferences
                .map((item) => item.toJson())
                .toList(growable: false),
            'provenance': <String, dynamic>{
              'phaseId': 'analysis',
              'actionCode': 'frameProblem',
              'reasonCode': 'prepare_delivery',
              'toolName': 'pipeline',
              'source': 'structured_response',
            },
          },
          <String, dynamic>{
            'entryId': 'answer_${dialogueRoundScript.domainId}',
            'stageId': JourneyStageId.answer.wireName,
            'kind': JourneyEntryKind.narrative.wireName,
            'status': _journeyStageStatusForPipelineStep(
              step: ProcessStepId.answerOrganization,
              blockedProcessStepId: blockedProcessStepId,
              finalAnswerReady: journeyReadiness.finalAnswerReady,
            ).wireName,
            'order': 3,
            'headline': renderedText,
            'detail': _firstNonEmptyText(<String?>[
              reasonShort,
              projectedAnswerProcessing.readinessSummary.trim(),
            ]),
            'references': syntheticUiReferences
                .map((item) => item.toJson())
                .toList(growable: false),
            'provenance': <String, dynamic>{
              'phaseId': 'synthesis',
              'actionCode': 'compose_answer',
              'reasonCode': 'prepare_delivery',
              'toolName': 'pipeline',
              'source': 'structured_response',
            },
          },
        ],
        'summary': renderedText,
        'referenceSummary': <String, dynamic>{
          'count': isFallbackOutput ? 0 : syntheticUiReferences.length,
          'references': isFallbackOutput
              ? <Map<String, dynamic>>[]
              : syntheticUiReferences
                    .map((item) => item.toJson())
                    .toList(growable: false),
        },
        'readiness': journeyReadiness.toJson(),
      },
      'sessionId': sessionId,
      'domainId': dialogueRoundScript.domainId,
      'templateVersionUsed': templateVersionUsed,
      'domainCatalogVersion': domainCatalogVersion,
      'retrievalPolicy': retrievalPolicy,
      'answerBoundaryPolicy': answerBoundaryPolicy.toJson(),
      'previousSlotState': previousSlotState.toJson(),
      'carriedUnderstandingSnapshot': carriedUnderstandingSnapshot,
      'carriedRetrievalProcessing': carriedRetrievalProcessing,
      'carriedHistoricalThinkingSnapshot': carriedHistoricalThinkingSnapshot,
      'streamedRetrievalProcessingSummary': streamedRetrievalProcessingSummary,
      'streamedAnswerReadinessSummary': streamedAnswerReadinessSummary,
      'phaseOneRoutingDiagnostics': phaseOneRoutingDiagnostics,
      'previousDomainPolicyBundle': previousDomainPolicyBundle?.toJson(),
      'blockedProcessStepId': blockedProcessStepId.wireName,
      'blockedProcessMessage': blockedProcessMessage,
      'skillRuns': skillRuns
          .map((item) => item.toJson())
          .toList(growable: false),
      'subagentPlan': subagentPlan
          .map((item) => item.toJson())
          .toList(growable: false),
      'subagentRuns': subagentRuns
          .map((item) => item.toJson())
          .toList(growable: false),
      'skillSynthesis': <String, dynamic>{
        'input': skillSynthesisInput.toJson(),
        'output': skillSynthesisOutput.toJson(),
      },
      'uiTimeline': buildStructuredResponseUiTimeline(
        subagentRuns: subagentRuns,
      ),
      'aggregationState': aggregationState.toJson(),
      'uiReferences': _uiReferenceWireMaps(effectiveUiReferences),
      'evidenceLedger': evidenceLedger
          .map((item) => item.toJson())
          .toList(growable: false),
      'toolResults': toolResults
          .map((item) => item.toJson())
          .toList(growable: false),
      'uiUsageStats': usage_stats.buildUiUsageStats(
        traces: traces,
        request: request,
        subagentRuns: subagentRuns,
        outputText: renderedText,
      ),
      'answerEvidenceLinks': _buildInlineEvidenceLinks(
        answerPayload: answerPayload,
        uiReferences: syntheticUiReferences,
        evidenceLedger: evidenceLedger,
      ),
    };
    final answerEvidenceBindings = _buildAnswerEvidenceBindings(
      answerPayload: answerPayload,
      uiReferences: syntheticUiReferences,
      evidenceLedger: evidenceLedger,
    );
    final currentSlotState = _buildSlotStateSnapshot(
      domainId: dialogueRoundScript.domainId,
      previousSlotState: previousSlotState,
      intentGraph: intentGraph,
      groundingBindings: answerEvidenceBindings,
    );
    final runArtifacts = RunArtifacts(
      machineEnvelope: (result.finalText as String?)?.trim().isNotEmpty == true
          ? (result.finalText as String).trim()
          : renderedText,
      displayMarkdown: displayMarkdown,
      displayPlainText: renderedText,
      displayState: projectedDisplayState,
      processTimeline: projectedProcessTimelineWithBlock,
      journey: AssistantJourney(
        stages: journeyStages
            .map(
              (item) => AssistantJourneyStage(
                stageId: parseJourneyStageId(
                  (item['stageId'] as String?) ?? '',
                ),
                status: parseJourneyStageStatus(
                  (item['status'] as String?) ?? '',
                ),
                order: (item['order'] as num?)?.toInt() ?? 0,
                summary: (item['summary'] as String?)?.trim() ?? '',
                referenceCount: (item['referenceCount'] as num?)?.toInt() ?? 0,
              ),
            )
            .toList(growable: false),
        entries: <AssistantJourneyEntry>[
          AssistantJourneyEntry(
            entryId: 'understanding_${dialogueRoundScript.domainId}',
            stageId: JourneyStageId.analyze,
            kind: JourneyEntryKind.narrative,
            status: _journeyStageStatusForPipelineStep(
              step: ProcessStepId.understanding,
              blockedProcessStepId: blockedProcessStepId,
              finalAnswerReady: journeyReadiness.finalAnswerReady,
            ),
            order: 0,
            headline: projectedUnderstandingSnapshot.userFacingSummary.trim(),
            detail: _journeyUnderstandingEntryDetail(
              snapshot: projectedUnderstandingSnapshot,
              reasonShort: reasonShort,
            ),
            provenance: AssistantJourneyProvenance(
              phaseId: parsePlannerPhaseId('understanding'),
              actionCode: parsePlannerActionCode('compose_answer'),
              reasonCode: parsePlannerReasonCode('answer_organization'),
              toolName: 'pipeline',
              source: 'structured_response',
            ),
          ),
          AssistantJourneyEntry(
            entryId: 'retrieval_design_${dialogueRoundScript.domainId}',
            stageId: JourneyStageId.search,
            kind: JourneyEntryKind.narrative,
            status: _journeyStageStatusForPipelineStep(
              step: ProcessStepId.retrievalDesign,
              blockedProcessStepId: blockedProcessStepId,
              finalAnswerReady: journeyReadiness.finalAnswerReady,
            ),
            order: 1,
            headline:
                projectedUnderstandingSnapshot.retrievalDesignNarrative.trim(),
            detail: retrievalDesignDetail,
            provenance: AssistantJourneyProvenance(
              phaseId: parsePlannerPhaseId('understanding'),
              actionCode: parsePlannerActionCode('compose_answer'),
              reasonCode: parsePlannerReasonCode('prepare_delivery'),
              toolName: 'pipeline',
              source: 'structured_response',
            ),
          ),
          AssistantJourneyEntry(
            entryId: 'retrieval_processing_${dialogueRoundScript.domainId}',
            stageId: JourneyStageId.verify,
            kind: JourneyEntryKind.narrative,
            status: _journeyStageStatusForPipelineStep(
              step: ProcessStepId.retrievalProcessing,
              blockedProcessStepId: blockedProcessStepId,
              finalAnswerReady: journeyReadiness.finalAnswerReady,
            ),
            order: 2,
            headline: projectedRetrievalNarrative.headline,
            detail: retrievalJourneyDetail,
            provenance: AssistantJourneyProvenance(
              phaseId: parsePlannerPhaseId('analysis'),
              actionCode: parsePlannerActionCode('frameProblem'),
              reasonCode: parsePlannerReasonCode('prepare_delivery'),
              toolName: 'pipeline',
              source: 'structured_response',
            ),
            references: syntheticUiReferences
                .map(
                  (item) => AssistantJourneyReference(
                    title: item.title.trim(),
                    url: item.url.trim(),
                    source: item.source.trim(),
                  ),
                )
                .toList(growable: false),
          ),
          AssistantJourneyEntry(
            entryId: 'answer_${dialogueRoundScript.domainId}',
            stageId: JourneyStageId.answer,
            kind: JourneyEntryKind.narrative,
            status: _journeyStageStatusForPipelineStep(
              step: ProcessStepId.answerOrganization,
              blockedProcessStepId: blockedProcessStepId,
              finalAnswerReady: journeyReadiness.finalAnswerReady,
            ),
            order: 3,
            headline: renderedText,
            detail: _firstNonEmptyText(<String?>[
              reasonShort,
              projectedAnswerProcessing.readinessSummary.trim(),
            ]),
            provenance: AssistantJourneyProvenance(
              phaseId: parsePlannerPhaseId('synthesis'),
              actionCode: parsePlannerActionCode('compose_answer'),
              reasonCode: parsePlannerReasonCode('prepare_delivery'),
              toolName: 'pipeline',
              source: 'structured_response',
            ),
          ),
        ],
        summary: renderedText,
        referenceSummary: AssistantJourneyReferenceSummary(
          count: isFallbackOutput ? 0 : syntheticUiReferences.length,
          references: isFallbackOutput
              ? const <AssistantJourneyReference>[]
              : syntheticUiReferences
                    .map(
                      (item) => AssistantJourneyReference(
                        title: item.title.trim(),
                        url: item.url.trim(),
                        source: item.source.trim(),
                      ),
                    )
                    .toList(growable: false),
        ),
        readiness: journeyReadiness,
      ),
      understandingSnapshot: projectedUnderstandingSnapshot,
      answerProcessing: _buildAnswerProcessingSnapshot(
        raw: mergedAnswerProcessing,
        streamedReadinessSummary: streamedAnswerReadinessSummary,
        synthesisReadiness: synthesisReadiness,
        stateDecision: projectedConversationStateDecision,
        evidenceEvaluation: evidenceEvaluation,
        evidenceLedger: evidenceLedger,
        answerPayload: answerPayload,
      ),
      historicalThinkingSnapshot: _buildHistoricalThinkingSnapshot(
        raw: carriedHistoricalThinkingSnapshot,
        understandingSnapshot: _buildUnderstandingSnapshot(
          raw: carriedUnderstandingSnapshot,
          intentGraph: intentGraph,
          latestUserQuery: request.messages.isNotEmpty
              ? request.messages.last.content
              : '',
        ),
      ),
      retrievalProcessing: projectedRetrievalProcessing,
      evidenceLedger: evidenceLedger,
      answerEvidenceBindings: answerEvidenceBindings,
      slotState: currentSlotState,
      answerDecision: RunArtifactsAnswerDecisionPartitioned(
        core: RunArtifactsAnswerDecisionCore(
          nextAction: projectedConversationStateDecision.nextActionWireName,
          answerEligibility:
              projectedConversationStateDecision.answerEligibilityWireName,
          finalAnswerReady: projectedConversationStateDecision.finalAnswerReady,
          evidenceSummary: evidenceSummary,
          confidence: structuredTurn.confidence,
          reasoning: structuredTurn.decision.reasoning.trim(),
          synthesisReady: synthesisReadiness.ready,
          synthesisReason: synthesisReadiness.reason.trim(),
        ),
        extensions: <String, dynamic>{
          'finalAnswerMode':
              projectedConversationStateDecision.finalAnswerModeWireName,
          'reasonCode': projectedAnswerGateDecision.reasonCode,
          'reason': projectedAnswerGateDecision.reason,
          'eligible': projectedAnswerGateDecision.eligible,
          'renderable': projectedAnswerGateDecision.renderable,
          'retrievalReady': projectedAnswerGateDecision.retrievalReady,
          'terminalPayloadComplete':
              projectedAnswerGateDecision.terminalPayloadComplete,
          'degraded': projectedAnswerGateDecision.degraded,
        },
      ),
      diagnostics: RunArtifactsDiagnosticsPartitioned(
        core: RunArtifactsDiagnosticsCore(
          domainId: dialogueRoundScript.domainId,
          renderMode: messageKind.wireName,
          renderFallback: isFallbackOutput ? messageKind.wireName : '',
          answerEligibility:
              projectedConversationStateDecision.answerEligibilityWireName,
          qualityGates: projectedConversationStateDecision.qualityGatesData,
          evidenceEvaluation: evidenceEvaluation.toJson(),
          answerBoundaryPolicy: answerBoundaryPolicy.toJson(),
          evidenceSummary: evidenceSummary,
          evidencePassed: retrievalOutcome.evidencePassed,
          finalAnswerMode:
              projectedConversationStateDecision.finalAnswerModeWireName,
          synthesisReady: synthesisReadiness.ready,
          synthesisReason: synthesisReadiness.reason.trim(),
          heuristicFallbackUsed: false,
        ),
      ),
      domainPolicyBundle:
          previousDomainPolicyBundle ??
          DomainPolicyBundle(
            domainId: dialogueRoundScript.domainId,
            retrievalPolicy: retrievalPolicy,
            slotSchema: <String, dynamic>{...currentSlotState.toJson()},
          ),
    );
    response['runArtifacts'] = runArtifacts.toJson();
    return assembleStructuredResponseRoot(
      enrichedAnswerPayload: response,
      rootPayload: <String, dynamic>{
        'request': request.toJson(),
        'runId': runId ?? '',
        'traceId': traceId ?? '',
        'candidateDomains': candidateDomains,
      },
    );
  }

  Future<Map<String, dynamic>> _loadRetrievalPolicy(String domainId) async {
    final normalized = domainId.trim();
    if (normalized.isEmpty) {
      return const <String, dynamic>{};
    }
    final path =
        'assets/assistant/skills/$normalized/config/retrieval_policy.json';
    try {
      final content = await rootBundle.loadString(path);
      final decoded = jsonDecode(content);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      if (decoded is Map) {
        return decoded.cast<String, Object?>();
      }
    } catch (_) {
      final file = File(path);
      if (await file.exists()) {
        try {
          final decoded = jsonDecode(await file.readAsString());
          if (decoded is Map<String, dynamic>) {
            return decoded;
          }
          if (decoded is Map) {
            return decoded.cast<String, Object?>();
          }
        } catch (_) {
          return const <String, dynamic>{};
        }
      }
    }
    return const <String, dynamic>{};
  }

  Map<String, dynamic> _preferStructuredMap(
    Map<String, dynamic> primary,
    Map<String, dynamic> fallback,
  ) {
    return primary.isNotEmpty ? primary : fallback;
  }

  List<AssistantToolResultRow> _toolResultsForEvidenceLedger(
    List<AssistantToolResultRow> toolResults,
  ) {
    return toolResults;
  }

  List<String> _blockingEvidenceDimensions({
    required List<QueryTask> queryTasks,
    required List<AssistantToolResultRow> toolResults,
  }) {
    final dimensions = <String>{};
    for (final item in toolResults) {
      final raw =
          (item.dataPayload['blockingDimensions'] as List?)
              ?.whereType<String>()
              .toList(growable: false) ??
          const <String>[];
      dimensions.addAll(
        raw.map((value) => value.trim()).where((value) => value.isNotEmpty),
      );
    }
    return dimensions.toList(growable: false);
  }

  bool _hasRenderableAnswerPayload({
    required Map<String, dynamic> payload,
    required Object? turn,
    required bool projectionRenderableContent,
  }) {
    final payloadView = AssistantAnswerPayloadReadView(payload);
    final typedTurn = turn is AssistantTurnOutput
        ? turn
        : payloadView.asTypedOutput;
    final isAnswerLike =
        typedTurn.decision.nextAction == AssistantNextAction.answer &&
        typedTurn.messageKind != AssistantMessageKind.fallback &&
        typedTurn.messageKind != AssistantMessageKind.progress &&
        typedTurn.messageKind != AssistantMessageKind.unknown;
    if (!isAnswerLike) return false;
    final userMarkdown = payloadView.userMarkdownTrimmed;
    final resultText = payloadView.resultTextTrimmed;
    return projectionRenderableContent ||
        userMarkdown.isNotEmpty ||
        resultText.isNotEmpty;
  }

  bool _hasEvidencePayloadCandidate({
    required RetrievalProcessingSnapshot retrievalProcessing,
    required List<EvidenceLedgerEntry> evidenceLedger,
    required List<AssistantToolResultRow> toolResults,
  }) {
    return retrievalProcessing.acceptedDocumentCount > 0 ||
        retrievalProcessing.acceptedReferences.isNotEmpty ||
        evidenceLedger.isNotEmpty ||
        toolResults.isNotEmpty;
  }

  FinalAnswerMode? _resolveStructuredFinalAnswerMode({
    required AssistantTurnOutput turn,
    required AssistantAnswerPayloadReadView answerPayloadView,
    required AnswerBoundaryPolicy answerBoundaryPolicy,
    required bool structuredAnswerMaterializedCandidate,
  }) {
    if (!structuredAnswerMaterializedCandidate ||
        turn.decision.nextAction != AssistantNextAction.answer) {
      return null;
    }
    final decisionMap = answerPayloadView.decisionMap;
    final rawFinalAnswerMode =
        (decisionMap['finalAnswerMode'] as String?)?.trim() ?? '';
    if (rawFinalAnswerMode.isNotEmpty) {
      final parsed = parseFinalAnswerMode(rawFinalAnswerMode);
      if (parsed != FinalAnswerMode.blocked ||
          rawFinalAnswerMode == FinalAnswerMode.blocked.wireName) {
        return parsed;
      }
    }
    final interpretation = turn.result.interpretation.trim();
    if (interpretation == FinalAnswerMode.boundedAnswer.wireName) {
      return FinalAnswerMode.boundedAnswer;
    }
    if (interpretation == FinalAnswerMode.full.wireName) {
      return FinalAnswerMode.full;
    }
    return answerBoundaryPolicy.allowBoundedAnswer
        ? FinalAnswerMode.boundedAnswer
        : FinalAnswerMode.boundedAnswer;
  }

  List<AssistantUiReferenceWireDto> _buildUiReferences(
    List<AssistantToolResultRow> toolResults, {
    required bool isRealtimeLike,
  }) {
    final refs = <AssistantUiReferenceWireDto>[];
    final seen = <String>{};
    for (final item in toolResults) {
      final rawRefs =
          (item.dataPayload['references'] as List?)?.whereType<Map>().toList(
            growable: false,
          ) ??
          const <Map>[];
      for (final raw in rawRefs) {
        final map = raw.cast<String, dynamic>();
        final url = (map['url'] as String?)?.trim() ?? '';
        if (url.isEmpty) continue;
        final dedupeKey = url.isNotEmpty
            ? url
            : '${(map['title'] as String?)?.trim() ?? ''}::${(map['source'] as String?)?.trim() ?? ''}';
        if (dedupeKey.isEmpty || !seen.add(dedupeKey)) {
          continue;
        }
        refs.add(
          AssistantUiReferenceWireDto(
            title: (map['title'] as String?)?.trim() ?? '',
            url: url,
            source: (map['source'] as String?)?.trim() ?? '',
            snippet: (map['snippet'] as String?)?.trim() ?? '',
          ),
        );
      }
    }
    return refs;
  }

  ConversationStateDecision _buildProjectedConversationStateDecision({
    required AggregationState aggregationState,
    required AnswerBoundaryPolicy answerBoundaryPolicy,
    required SynthesisReadinessResult synthesisReadiness,
    required ProcessStepId blockedProcessStepId,
    required bool structuredAnswerMaterializedCandidate,
    required FinalAnswerMode? structuredFinalAnswerModeCandidate,
    required bool structuredAskUserCandidate,
  }) {
    final shouldReplanForRetrievalBlock =
        !structuredAnswerMaterializedCandidate &&
        !synthesisReadiness.ready &&
        synthesisReadiness.replanTask != null;
    if (shouldReplanForRetrievalBlock) {
      return ConversationStateDecision(
        nextAction: AssistantNextAction.toolCall,
        finalAnswerMode: FinalAnswerMode.replan,
        answerEligibility: AnswerEligibility.blocked,
        slotState: const SlotStateSnapshot(),
        missingCriticalSlots: const <String>[],
        askUser: const AssistantTurnAskUser(),
        qualityGates: const QualityGatesDto(),
        finalAnswerReady: false,
      );
    }
    final shouldDeliverAnswer =
        aggregationState.finalAnswerReady ||
        structuredAnswerMaterializedCandidate;
    final shouldClarify =
        !shouldDeliverAnswer &&
        (structuredAskUserCandidate || aggregationState.clarificationNeeded);
    return ConversationStateDecision(
      nextAction: shouldDeliverAnswer
          ? AssistantNextAction.answer
          : AssistantNextAction.askUser,
      finalAnswerMode: shouldDeliverAnswer
          ? (structuredFinalAnswerModeCandidate ??
                (aggregationState.finalAnswerReady
                ? FinalAnswerMode.full
                : structuredAnswerMaterializedCandidate ||
                      answerBoundaryPolicy.allowBoundedAnswer
                ? FinalAnswerMode.boundedAnswer
                : FinalAnswerMode.full))
          : shouldClarify
          ? FinalAnswerMode.clarify
          : FinalAnswerMode.blocked,
      answerEligibility: shouldDeliverAnswer
          ? AnswerEligibility.eligible
          : shouldClarify
          ? AnswerEligibility.clarify
          : AnswerEligibility.blocked,
      slotState: const SlotStateSnapshot(),
      missingCriticalSlots: const <String>[],
      askUser: const AssistantTurnAskUser(),
      qualityGates: const QualityGatesDto(),
      finalAnswerReady: shouldDeliverAnswer,
    );
  }

  ConversationStateDecision _reconcileConversationStateDecisionWithGate({
    required ConversationStateDecision base,
    required AnswerGateDecision gate,
  }) {
    final resolvedNextAction = gate.nextAction.trim().isNotEmpty
        ? parseAssistantNextAction(gate.nextAction)
        : base.nextActionType;
    final resolvedEligibility = gate.answerEligibility.trim().isNotEmpty
        ? parseAnswerEligibility(gate.answerEligibility)
        : base.answerEligibilityType;
    final shouldPreserveAnswerMode =
        resolvedNextAction == AssistantNextAction.answer;
    return ConversationStateDecision(
      nextAction: resolvedNextAction,
      finalAnswerMode: gate.finalAnswerReady || shouldPreserveAnswerMode
          ? base.finalAnswerModeType
          : _blockedFinalAnswerModeForNextAction(resolvedNextAction),
      answerEligibility: resolvedEligibility,
      slotState: base.slotState,
      missingCriticalSlots: base.missingCriticalSlots,
      askUser: base.askUser,
      qualityGates: base.qualityGates,
      finalAnswerReady: gate.finalAnswerReady,
    );
  }

  FinalAnswerMode _blockedFinalAnswerModeForNextAction(
    AssistantNextAction nextAction,
  ) {
    switch (nextAction) {
      case AssistantNextAction.toolCall:
      case AssistantNextAction.replan:
        return FinalAnswerMode.replan;
      case AssistantNextAction.retry:
        return FinalAnswerMode.retry;
      case AssistantNextAction.askUser:
        return FinalAnswerMode.clarify;
      case AssistantNextAction.answer:
      case AssistantNextAction.abort:
      case AssistantNextAction.unknown:
        return FinalAnswerMode.blocked;
    }
  }

  List<AssistantUiReferenceWireDto> _buildUiReferencesFromLedger(
    List<EvidenceLedgerEntry> ledger, {
    required List<Map<String, dynamic>> toolResults,
    required bool isRealtimeLike,
  }) {
    return ledger
        .map(
          (entry) => AssistantUiReferenceWireDto(
            title: entry.title.isNotEmpty ? entry.title : entry.source,
            url: entry.url,
            source: entry.source.isNotEmpty ? entry.source : entry.sourceHost,
            snippet: entry.snippet,
          ),
        )
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _uiReferenceWireMaps(
    List<AssistantUiReferenceWireDto> uiReferences,
  ) {
    return uiReferences.map((item) => item.toJson()).toList(growable: false);
  }

  SkillRun _buildPrimarySkillRun({
    required IntentGraph intentGraph,
    required String domainId,
    required Map<String, dynamic> answerPayload,
    required dynamic result,
    required SkillExecutionShell executionShell,
    required List<Map<String, dynamic>> references,
  }) {
    return SkillRun(
      runId: '${domainId}_${DateTime.now().microsecondsSinceEpoch}',
      domainId: domainId,
      goal: _firstNonEmptyText(<String?>[
        intentGraph.userGoal,
        intentGraph.userJobToBeDone,
        intentGraph.targetObject,
      ]),
      problemClass: executionShell.problemClass,
      shell: <String, dynamic>{
        'problemClass': executionShell.problemClass,
        'maxIterations': executionShell.maxIterations,
        'toolBudget': executionShell.toolBudget,
        'variantBudget': executionShell.variantBudget,
        'reflectionBudget': executionShell.reflectionBudget,
        'providerPolicy': executionShell.providerPolicy,
        'preferredProviders': executionShell.preferredProviders,
        'authorityDomains': executionShell.authorityDomains,
        'freshnessHoursMax': executionShell.freshnessHoursMax,
      },
      slotState: const <String, dynamic>{},
      answerReady: true,
      stopReason: '',
      references: references,
      resultSummary: result.finalText as String? ?? '',
    );
  }

  SkillRouteOutput _buildSkillRouteOutput({
    required String userQuery,
    required IntentGraph intentGraph,
    required String primaryDomainId,
    required SkillExecutionShell executionShell,
    required List<SubagentPlan> subagentPlans,
  }) {
    final secondarySkillIds = subagentPlans
        .map((item) => item.domainId.trim())
        .where((item) => item.isNotEmpty && item != primaryDomainId.trim())
        .toList(growable: false);
    final primaryRouteNarrative = secondarySkillIds.isEmpty
        ? 'primary=$primaryDomainId; query=${userQuery.trim()}'
        : 'primary=$primaryDomainId; secondary=${secondarySkillIds.join(',')}; '
              'query=${userQuery.trim()}';
    return SkillRouteOutput.fromPrimaryAndSupportingPlans(
      userQuery: userQuery,
      primaryTarget: SkillRouteTarget.primary(
        skillId: primaryDomainId,
        goal: _firstNonEmptyText(<String?>[
          intentGraph.userGoal,
          intentGraph.userJobToBeDone,
          intentGraph.targetObject,
          userQuery,
        ]),
        problemClass: _firstNonEmptyText(<String?>[
          executionShell.problemClass,
          intentGraph.problemClassWireName,
        ]),
        taskBrief: _firstNonEmptyText(<String?>[
          intentGraph.userJobToBeDone,
          intentGraph.targetObject,
          intentGraph.userGoal,
          userQuery,
        ]),
        routeNarrative: primaryRouteNarrative,
        localContextSeed: _buildPrimarySkillLocalContextSeed(
          intentGraph: intentGraph,
          userQuery: userQuery,
          primaryDomainId: primaryDomainId,
        ),
        needClarify: intentGraph.clarificationNeeded,
      ),
      supportingPlans: subagentPlans,
      routeNarrative: <String>[
        primaryRouteNarrative,
        ...subagentPlans
            .map((item) => item.routeNarrative.trim())
            .where((item) => item.isNotEmpty),
      ].join(' | '),
      needClarify: intentGraph.clarificationNeeded,
      pendingClarifications: subagentPlans
          .expand((item) => item.pendingClarifications)
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false),
    );
  }

  String _buildPrimarySkillLocalContextSeed({
    required IntentGraph intentGraph,
    required String userQuery,
    required String primaryDomainId,
  }) {
    final anchors = intentGraph.entityAnchors
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    final buffer = StringBuffer()
      ..write('query=')
      ..write(userQuery.trim())
      ..write('; primary=')
      ..write(primaryDomainId.trim())
      ..write('; class=')
      ..write(intentGraph.problemClassWireName);
    final job = intentGraph.userJobToBeDone.trim();
    if (job.isNotEmpty) {
      buffer
        ..write('; job=')
        ..write(job);
    }
    if (anchors.isNotEmpty) {
      buffer
        ..write('; anchors=')
        ..write(anchors.join('、'));
    }
    return buffer.toString();
  }

  SkillSynthesisSkillResult _buildPrimarySkillSynthesisResult({
    required String primaryDomainId,
    required Map<String, dynamic> answerPayload,
    required String fallbackSummary,
    required List<Map<String, dynamic>> acceptedEvidence,
    required bool answerReady,
  }) {
    return SkillSynthesisSkillResult(
      skillId: primaryDomainId,
      role: 'primary',
      status: answerReady ? 'success' : 'pending',
      summary: _firstNonEmptyText(<String?>[
        answerPayload['result'] is Map
            ? ((answerPayload['result'] as Map)['summary'] as String?)?.trim()
            : null,
        answerPayload['result'] is Map
            ? ((answerPayload['result'] as Map)['text'] as String?)?.trim()
            : null,
        (answerPayload['reasonShort'] as String?)?.trim(),
        fallbackSummary,
      ]),
      acceptedEvidence: acceptedEvidence,
      rejectedEvidence: const <Map<String, dynamic>>[],
      missingSlots: normalizeStringList(answerPayload['missingContextSlots']),
      failureReason: '',
      answerReady: answerReady,
    );
  }

  SkillRun Function(AssistantSubagentRunRecord)
  get _skillRunFromLegacySubagentRun {
    return (record) => SkillRun(
      runId: record.subagentId,
      domainId: record.domainId,
      goal: record.goal,
      problemClass: record.problemClass,
      shell: record.shell,
      slotState: const <String, dynamic>{},
      answerReady: record.answerReady,
      stopReason: record.failureReason.isNotEmpty
          ? record.failureReason
          : record.errorMessage,
      references: record.references,
      resultSummary: record.summary,
    );
  }

  AggregationState _buildAggregationState({
    required IntentGraph intentGraph,
    required List<SkillRun> skillRuns,
    required Map<String, dynamic> answerPayload,
  }) {
    final answerReady =
        ((answerPayload['result'] as Map?)?['text'] as String?)
            ?.trim()
            .isNotEmpty ==
        true;
    return AggregationState(
      allSkillsReady: skillRuns.isNotEmpty,
      blockingSkills: const <String>[],
      blockedBy: const <String, AggregationBlockingSkillStateDto>{},
      canGivePartialAnswer: answerReady,
      needExpansion: false,
      expansionPlan: const AggregationExpansionPlanDto(),
      finalAnswerReady: answerReady,
      answerOwner: intentGraph.primarySkill,
      clarificationSource: '',
      dependencies: const <String, AggregationDependencyChainDto>{},
    );
  }

  RetrievalProcessingSnapshot _licensedRetrievalProcessingForSynthesis(
    Map<String, dynamic> raw,
  ) {
    return _hasStructuredContent(raw)
        ? RetrievalProcessingSnapshot.fromJson(raw)
        : const RetrievalProcessingSnapshot();
  }

  AssistantMessageKind _resolveMessageKind({
    required Map<String, dynamic> answerPayload,
    required String resultText,
  }) {
    final parsed = parseMessageKind(
      (answerPayload['messageKind'] as String?)?.trim() ?? '',
    );
    if (parsed != AssistantMessageKind.unknown) return parsed;
    return resultText.trim().isNotEmpty
        ? AssistantMessageKind.answer
        : AssistantMessageKind.fallback;
  }

  RunArtifactsUnderstandingSnapshot _buildUnderstandingSnapshot({
    required Map<String, dynamic> raw,
    required IntentGraph intentGraph,
    required String latestUserQuery,
  }) {
    final parsed = _hasStructuredContent(raw)
        ? RunArtifactsUnderstandingSnapshot.fromJson(raw)
        : const RunArtifactsUnderstandingSnapshot();
    final concernPoints = parsed.concernPoints.isNotEmpty
        ? parsed.concernPoints
        : <String>[
                ...intentGraph.hardConstraints,
                ...intentGraph.softConstraints,
              ]
              .where((item) => item.trim().isNotEmpty)
              .take(4)
              .toList(growable: false);
    final canonicalQuery = _firstNonEmptyText(<String?>[
      intentGraph.queryNormalization.rewrittenQuery,
      intentGraph.queryNormalization.normalizedQuery,
      intentGraph.queryTasks.isNotEmpty
          ? intentGraph.queryTasks.first.query
          : '',
    ]);
    final parsedIntentSummary = parsed.intentSummary.trim();
    final intentSummary = parsedIntentSummary.isNotEmpty
        ? parsedIntentSummary
        : _firstNonEmptyText(<String?>[
            intentGraph.userGoal,
            intentGraph.userJobToBeDone,
            intentGraph.targetObject,
            latestUserQuery,
            canonicalQuery,
          ]);
    final parsedUserFacingSummary = parsed.userFacingSummary.trim();
    final userFacingSummary = parsedUserFacingSummary.isNotEmpty
        ? parsedUserFacingSummary
        : _firstNonEmptyText(<String?>[
            parsedIntentSummary,
            intentSummary,
            intentGraph.userGoal,
            intentGraph.userJobToBeDone,
            intentGraph.targetObject,
            latestUserQuery,
            canonicalQuery,
          ]);
    final parsedRetrievalDesignNarrative =
        parsed.retrievalDesignNarrative.trim();
    final retrievalDesignNarrative = parsedRetrievalDesignNarrative.isNotEmpty
        ? parsedRetrievalDesignNarrative
        : _firstNonEmptyText(<String?>[
            if (parsedIntentSummary.isNotEmpty &&
                parsedIntentSummary != parsedUserFacingSummary)
              parsedIntentSummary,
            _buildRetrievalDesignNarrativeFallback(intentGraph.queryTasks),
          ]);
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: _normalizeFinalAnswerTemporalAnchors(
        intentSummary,
        intentGraph,
      ),
      userFacingSummary: _normalizeFinalAnswerTemporalAnchors(
        userFacingSummary,
        intentGraph,
      ),
      retrievalDesignNarrative: _normalizeFinalAnswerTemporalAnchors(
        retrievalDesignNarrative,
        intentGraph,
      ),
      concernPoints: concernPoints,
      emotionSignal: parsed.emotionSignal,
      resolutionItems: parsed.resolutionItems.isNotEmpty
          ? parsed.resolutionItems
          : _deriveResolutionItemsFromIntentGraph(intentGraph),
      assumptions: parsed.assumptions,
      mismatchSignal: parsed.mismatchSignal,
      carryForwardFacts: parsed.carryForwardFacts,
      discardedAssumptions: parsed.discardedAssumptions,
    );
  }

  RunArtifactsAnswerProcessing _buildAnswerProcessingSnapshot({
    required Map<String, dynamic> raw,
    required String streamedReadinessSummary,
    required SynthesisReadinessResult synthesisReadiness,
    required ConversationStateDecision stateDecision,
    required EvidenceEvaluationResult evidenceEvaluation,
    required List<EvidenceLedgerEntry> evidenceLedger,
    required Map<String, dynamic> answerPayload,
  }) {
    final parsed = _hasStructuredContent(raw)
        ? RunArtifactsAnswerProcessing.fromJson(raw)
        : const RunArtifactsAnswerProcessing();
    final keyFacts =
        (parsed.keyFacts.isNotEmpty
                ? parsed.keyFacts
                : _buildAnswerKeyFacts(
                    answerPayload: answerPayload,
                    evidenceLedger: evidenceLedger,
                  ))
            .map(_sanitizeAnswerKeyFact)
            .where((item) => item.isNotEmpty)
            .take(4)
            .toList(growable: false);
    final missingDimensions = parsed.missingDimensions.isNotEmpty
        ? parsed.missingDimensions
        : stateDecision.missingCriticalSlots
              .where((item) => item.trim().isNotEmpty)
              .take(4)
              .toList(growable: false);
    final retrieveMoreReason = parsed.retrieveMoreReason.isNotEmpty
        ? parsed.retrieveMoreReason
        : (stateDecision.finalAnswerReady
              ? ''
              : _firstNonEmptyText(<String?>[
                  synthesisReadiness.reason,
                  evidenceEvaluation.summary,
                ]));
    final fallbackFact = _sanitizeAnswerKeyFact(
      _firstNonEmptyText(<String?>[
        (answerPayload['userMarkdown'] as String?)?.trim(),
        ((answerPayload['result'] as Map?)?['text'] as String?)?.trim(),
        streamedReadinessSummary,
      ]),
    );
    return RunArtifactsAnswerProcessing(
      readinessSummary: _mergeStableNarrativeFinalText(
        streamed: streamedReadinessSummary,
        finalized: parsed.readinessSummary,
      ),
      keyFacts: keyFacts.isNotEmpty
          ? keyFacts
          : (fallbackFact.isNotEmpty ? <String>[fallbackFact] : keyFacts),
      missingDimensions: missingDimensions,
      retrieveMoreReason: retrieveMoreReason,
    );
  }

  RunArtifactsHistoricalThinkingSnapshot _buildHistoricalThinkingSnapshot({
    required Map<String, dynamic> raw,
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
  }) {
    final parsed = _hasStructuredContent(raw)
        ? RunArtifactsHistoricalThinkingSnapshot.fromJson(raw)
        : const RunArtifactsHistoricalThinkingSnapshot();
    return RunArtifactsHistoricalThinkingSnapshot(
      continuityMode: parsed.continuityMode,
      mismatchSignal: parsed.mismatchSignal.isNotEmpty
          ? parsed.mismatchSignal
          : understandingSnapshot.mismatchSignal,
      carryForwardFacts: parsed.carryForwardFacts.isNotEmpty
          ? parsed.carryForwardFacts
          : understandingSnapshot.carryForwardFacts,
      needsRecheckFacts: parsed.needsRecheckFacts,
      discardedAssumptions: parsed.discardedAssumptions.isNotEmpty
          ? parsed.discardedAssumptions
          : understandingSnapshot.discardedAssumptions,
    );
  }

  String _normalizeFinalAnswerTemporalAnchors(
    String text,
    IntentGraph intentGraph,
  ) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return '';
    final normalized = _canonicalizeUnderstandingSnapshotDateAnchors(trimmed);
    final qn = intentGraph.queryNormalization;
    final modelAnchors =
        <String>[qn.timePoint, qn.timeRangeStart, qn.timeRangeEnd, qn.timeScope]
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false);
    for (final anchor in modelAnchors) {
      if (normalized == anchor) return anchor;
    }
    return normalized;
  }

  RetrievalProcessingSnapshot _buildRetrievalProcessingSnapshot({
    required Map<String, dynamic> processing,
    required String streamedProcessingSummary,
    required List<AssistantUiReferenceWireDto> uiReferences,
    required List<AssistantToolResultRow> toolResults,
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    final parsed = _hasStructuredContent(processing)
        ? RetrievalProcessingSnapshot.fromJson(processing)
        : const RetrievalProcessingSnapshot();
    final resolvedProcessingSummary = _firstNonEmptyText(<String?>[
      parsed.processingSummary.trim(),
      streamedProcessingSummary.trim(),
    ]);
    final acceptedReferences = parsed.acceptedReferences.isNotEmpty
        ? parsed.acceptedReferences
        : _fallbackAcceptedRetrievalReferences(
            evidenceLedger: evidenceLedger,
            toolResults: toolResults,
            uiReferences: uiReferences,
          );
    final selectedKeyPoints = parsed.selectedKeyPoints
        .map(_sanitizeAnswerKeyFact)
        .where((item) => item.isNotEmpty)
        .take(5)
        .toList(growable: false);
    final resolvedAcceptedDocumentCount = _fallbackAcceptedDocumentCount(
      parsedAcceptedDocumentCount: parsed.acceptedDocumentCount,
      acceptedReferences: acceptedReferences,
      toolResults: toolResults,
    );
    return RetrievalProcessingSnapshot(
      processedDocumentCount: parsed.processedDocumentCount > 0
          ? parsed.processedDocumentCount
          : _fallbackProcessedDocumentCount(
              toolResults: toolResults,
              acceptedDocumentCount: resolvedAcceptedDocumentCount,
              uiReferenceCount: uiReferences.length,
            ),
      acceptedDocumentCount: resolvedAcceptedDocumentCount,
      processingSummary: resolvedProcessingSummary,
      selectedKeyPoints: selectedKeyPoints.isNotEmpty
          ? selectedKeyPoints
          : _fallbackRetrievalSelectedKeyPoints(
              acceptedReferences: acceptedReferences,
              toolResults: toolResults,
              processingSummary: resolvedProcessingSummary,
            ),
      expansionReason: parsed.expansionReason.trim(),
      acceptedReferences: acceptedReferences,
    );
  }

  int _fallbackAcceptedDocumentCount({
    required int parsedAcceptedDocumentCount,
    required List<RetrievalProcessingReference> acceptedReferences,
    required List<AssistantToolResultRow> toolResults,
  }) {
    final seen = <String>{};

    void collectReference(RetrievalProcessingReference reference) {
      final key = reference.url.trim().isNotEmpty
          ? reference.url.trim()
          : '${reference.title.trim()}:${reference.source.trim()}';
      if (key.trim().isEmpty) {
        return;
      }
      if (reference.title.trim().isEmpty &&
          reference.url.trim().isEmpty &&
          reference.source.trim().isEmpty) {
        return;
      }
      seen.add(key);
    }

    for (final reference in acceptedReferences) {
      collectReference(reference);
    }
    for (final item in toolResults) {
      final references =
          (item.dataPayload['references'] as List?)
              ?.whereType<Map>()
              .map((entry) => entry.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      for (final reference in references) {
        collectReference(
          RetrievalProcessingReference(
            title: SafeReferenceNormalizer.normalizeText(
              (reference['title'] as String?)?.trim() ?? '',
            ),
            url: (reference['url'] as String?)?.trim() ?? '',
            source: SafeReferenceNormalizer.normalizeText(
              (reference['source'] as String?)?.trim() ??
                  (reference['sourceHost'] as String?)?.trim() ??
                  '',
            ),
            snippet: SafeReferenceNormalizer.normalizeSnippet(
              (reference['snippet'] as String?)?.trim() ?? '',
            ),
          ),
        );
      }
    }
    return math.max(parsedAcceptedDocumentCount, seen.length);
  }

  List<RetrievalProcessingReference> _fallbackAcceptedRetrievalReferences({
    required List<EvidenceLedgerEntry> evidenceLedger,
    required List<AssistantToolResultRow> toolResults,
    required List<AssistantUiReferenceWireDto> uiReferences,
  }) {
    final accepted = <RetrievalProcessingReference>[];
    final seen = <String>{};

    void addReference(RetrievalProcessingReference reference) {
      final key = reference.url.trim().isNotEmpty
          ? reference.url.trim()
          : '${reference.source.trim()}:${reference.title.trim()}';
      if (key.trim().isEmpty || !seen.add(key)) {
        return;
      }
      if (reference.title.trim().isEmpty &&
          reference.url.trim().isEmpty &&
          reference.source.trim().isEmpty) {
        return;
      }
      accepted.add(reference);
    }

    final strongEvidence = evidenceLedger
        .where((entry) => entry.relevanceScore >= 0.45)
        .toList(growable: false);
    final prioritizedEvidence =
        (strongEvidence.isNotEmpty
              ? strongEvidence
              : List<EvidenceLedgerEntry>.from(evidenceLedger))
          ..sort((left, right) {
            final relevanceCompare = right.relevanceScore.compareTo(
              left.relevanceScore,
            );
            if (relevanceCompare != 0) {
              return relevanceCompare;
            }
            final authorityCompare = right.authorityScore.compareTo(
              left.authorityScore,
            );
            if (authorityCompare != 0) {
              return authorityCompare;
            }
            return left.freshnessHours.compareTo(right.freshnessHours);
          });
    for (final entry in prioritizedEvidence) {
      addReference(
        RetrievalProcessingReference(
          title: SafeReferenceNormalizer.normalizeText(entry.title.trim()),
          url: entry.url.trim(),
          source: SafeReferenceNormalizer.normalizeText(
            entry.source.trim().isNotEmpty
                ? entry.source.trim()
                : entry.sourceHost.trim(),
          ),
          snippet: SafeReferenceNormalizer.normalizeSnippet(
            entry.snippet.trim(),
          ),
        ),
      );
      if (accepted.length >= 5) {
        return accepted;
      }
    }

    for (final item in toolResults) {
      final references =
          (item.dataPayload['references'] as List?)
              ?.whereType<Map>()
              .map((entry) => entry.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      for (final reference in references) {
        addReference(
          RetrievalProcessingReference(
            title: SafeReferenceNormalizer.normalizeText(
              (reference['title'] as String?)?.trim() ?? '',
            ),
            url: (reference['url'] as String?)?.trim() ?? '',
            source: SafeReferenceNormalizer.normalizeText(
              (reference['source'] as String?)?.trim() ??
                  (reference['sourceHost'] as String?)?.trim() ??
                  '',
            ),
            snippet: SafeReferenceNormalizer.normalizeSnippet(
              (reference['snippet'] as String?)?.trim() ?? '',
            ),
          ),
        );
        if (accepted.length >= 5) {
          return accepted;
        }
      }
    }

    for (final item in uiReferences) {
      addReference(
        RetrievalProcessingReference(
          title: item.title.trim(),
          url: item.url.trim(),
          source: item.source.trim(),
          snippet: item.snippet.trim(),
        ),
      );
      if (accepted.length >= 5) {
        return accepted;
      }
    }
    return accepted;
  }

  int _fallbackProcessedDocumentCount({
    required List<AssistantToolResultRow> toolResults,
    required int acceptedDocumentCount,
    required int uiReferenceCount,
  }) {
    var maxProcessed = math.max(acceptedDocumentCount, uiReferenceCount);
    var summed = 0;
    for (final item in toolResults) {
      final total =
          (item.dataPayload['totalReferences'] as num?)?.toInt() ??
          ((item.dataPayload['references'] as List?)?.length ?? 0);
      if (total > maxProcessed) {
        maxProcessed = total;
      }
      summed += total;
    }
    if (summed > maxProcessed) {
      maxProcessed = summed;
    }
    return maxProcessed;
  }

  List<String> _fallbackRetrievalSelectedKeyPoints({
    required List<RetrievalProcessingReference> acceptedReferences,
    required List<AssistantToolResultRow> toolResults,
    required String processingSummary,
  }) {
    final points = <String>[];
    final seen = <String>{};

    void collect(String raw) {
      final value = _sanitizeAnswerKeyFact(raw);
      if (value.isEmpty || value.length < 6 || !seen.add(value)) {
        return;
      }
      points.add(value);
    }

    for (final item in toolResults) {
      final summary = (item.dataPayload['summary'] as String?)?.trim() ?? '';
      if (summary.isNotEmpty) {
        collect(summary);
      }
      final hits =
          (item.dataPayload['hits'] as List?)
              ?.whereType<Map>()
              .map((entry) => entry.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      for (final hit in hits) {
        final snippet = (hit['snippet'] as String?)?.trim() ?? '';
        if (snippet.isNotEmpty) {
          collect(snippet);
        }
        if (points.length >= 5) {
          return points;
        }
      }
      if (points.length >= 5) {
        return points;
      }
    }

    for (final reference in acceptedReferences) {
      collect(
        reference.snippet.trim().isNotEmpty
            ? reference.snippet
            : reference.title,
      );
      if (points.length >= 5) {
        return points;
      }
    }

    if (points.isEmpty && processingSummary.trim().isNotEmpty) {
      collect(processingSummary);
    }
    return points;
  }

  AssistantJourney _enrichJourneyWithStructuredSnapshots(
    AssistantJourney journey, {
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
    required RetrievalProcessingSnapshot retrievalProcessing,
    required RunArtifactsAnswerProcessing answerProcessing,
    required bool finalAnswerReady,
  }) {
    return journey;
  }

  List<Map<String, dynamic>> _buildInlineEvidenceLinks({
    required Map<String, dynamic> answerPayload,
    required List<AssistantUiReferenceWireDto> uiReferences,
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    return _buildAnswerEvidenceBindings(
      answerPayload: answerPayload,
      uiReferences: uiReferences,
      evidenceLedger: evidenceLedger,
    ).map((item) => item.toJson()).toList(growable: false);
  }

  List<AnswerEvidenceBinding> _buildAnswerEvidenceBindings({
    required Map<String, dynamic> answerPayload,
    required List<AssistantUiReferenceWireDto> uiReferences,
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    final bindings = <AnswerEvidenceBinding>[];
    final seen = <String>{};
    for (final item in AssistantAnswerPayloadReadView(
      answerPayload,
    ).evidenceMaps) {
      final candidate = _normalizeInlineEvidenceBinding(
        item: item,
        uiReferences: uiReferences,
        evidenceLedger: evidenceLedger,
        index: bindings.length + 1,
      );
      if (candidate == null) continue;
      final dedupeKey = candidate.evidenceId.isNotEmpty
          ? candidate.evidenceId
          : candidate.url;
      if (dedupeKey.isEmpty || !seen.add(dedupeKey)) continue;
      bindings.add(candidate);
      if (bindings.length >= 4) break;
    }
    if (bindings.isEmpty) {
      for (final entry in evidenceLedger.take(2)) {
        final dedupeKey = entry.evidenceId.isNotEmpty
            ? entry.evidenceId
            : entry.url;
        if (dedupeKey.isEmpty || !seen.add(dedupeKey)) continue;
        bindings.add(
          _fallbackBindingFromEvidenceEntry(
            entry: entry,
            index: bindings.length + 1,
          ),
        );
      }
    }
    if (bindings.isEmpty) {
      for (final ref in uiReferences.take(2)) {
        final refMap = ref.toJson();
        final url = (refMap['url'] as String?)?.trim() ?? '';
        if (url.isEmpty || !seen.add(url)) continue;
        bindings.add(
          _fallbackBindingFromReference(
            ref: refMap,
            index: bindings.length + 1,
          ),
        );
      }
    }
    return bindings;
  }

  AnswerEvidenceBinding? _normalizeInlineEvidenceBinding({
    required Map<String, dynamic> item,
    required List<AssistantUiReferenceWireDto> uiReferences,
    required List<EvidenceLedgerEntry> evidenceLedger,
    required int index,
  }) {
    final claim =
        ((item['text'] as String?)?.trim().isNotEmpty == true
            ? (item['text'] as String).trim()
            : (item['claim'] as String?)?.trim()) ??
        '';
    final directEvidenceId = (item['evidenceId'] as String?)?.trim() ?? '';
    final directUrl = SafeReferenceNormalizer.canonicalizeUrl(
      (item['url'] as String?)?.trim() ?? '',
    );
    final directTitle = (item['title'] as String?)?.trim() ?? '';
    final directSource = (item['source'] as String?)?.trim() ?? '';
    final directSnippet = (item['snippet'] as String?)?.trim() ?? '';
    final matchedEvidence = _matchEvidenceEntryForBinding(
      claim: claim,
      title: directTitle,
      snippet: directSnippet,
      directUrl: directUrl,
      directEvidenceId: directEvidenceId,
      evidenceLedger: evidenceLedger,
    );
    Map<String, dynamic> matchedReference = const <String, dynamic>{};
    if (directUrl.isEmpty && matchedEvidence == null) {
      matchedReference = _matchReferenceForEvidence(
        claim: claim,
        title: directTitle,
        snippet: directSnippet,
        uiReferences: uiReferences,
      );
    }
    final url = directUrl.isNotEmpty
        ? directUrl
        : (matchedEvidence?.url.isNotEmpty == true
              ? matchedEvidence!.url
              : SafeReferenceNormalizer.canonicalizeUrl(
                  (matchedReference['url'] as String?)?.trim() ?? '',
                ));
    if (url.isEmpty) return null;
    final normalizedReference = SafeReferenceNormalizer.normalize(<
      String,
      dynamic
    >{
      'url': url,
      'title': directTitle.isNotEmpty
          ? directTitle
          : (matchedEvidence?.title.isNotEmpty == true
                ? matchedEvidence!.title
                : ((matchedReference['title'] as String?)?.trim().isNotEmpty ==
                          true
                      ? (matchedReference['title'] as String).trim()
                      : url)),
      'source': matchedEvidence?.source.isNotEmpty == true
          ? matchedEvidence!.source
          : (directSource.isNotEmpty
                ? directSource
                : (matchedEvidence?.sourceHost.isNotEmpty == true
                      ? matchedEvidence!.sourceHost
                      : (matchedReference['source'] as String?)?.trim() ?? '')),
      'snippet': directSnippet.isNotEmpty
          ? directSnippet
          : (matchedEvidence?.snippet.isNotEmpty == true
                ? matchedEvidence!.snippet
                : (matchedReference['snippet'] as String?)?.trim() ?? ''),
    });
    if (normalizedReference == null) return null;
    final source = matchedEvidence?.source.isNotEmpty == true
        ? matchedEvidence!.source
        : (directSource.isNotEmpty
              ? directSource
              : (matchedEvidence?.sourceHost.isNotEmpty == true
                    ? matchedEvidence!.sourceHost
                    : (normalizedReference['source'] as String?)?.trim() ??
                          ''));
    return AnswerEvidenceBinding(
      bindingId: 'answer_evidence_${index}_${url.hashCode}',
      label: _buildEvidenceBindingLabel(
        title: (normalizedReference['title'] as String?)?.trim() ?? '',
        source: source,
        url: url,
      ),
      claim: claim,
      evidenceId: matchedEvidence?.evidenceId ?? '',
      url: url,
      title: (normalizedReference['title'] as String?)?.trim() ?? url,
      source: source,
      snippet: (normalizedReference['snippet'] as String?)?.trim() ?? '',
    );
  }

  AnswerEvidenceBinding _fallbackBindingFromEvidenceEntry({
    required EvidenceLedgerEntry entry,
    required int index,
  }) {
    return AnswerEvidenceBinding(
      bindingId:
          'answer_evidence_${index}_${entry.evidenceId.isNotEmpty ? entry.evidenceId : entry.url.hashCode}',
      label: _buildEvidenceBindingLabel(
        title: entry.title,
        source: entry.source.isNotEmpty ? entry.source : entry.sourceHost,
        url: entry.url,
      ),
      claim: entry.title,
      evidenceId: entry.evidenceId,
      url: entry.url,
      title: entry.title.isNotEmpty ? entry.title : entry.url,
      source: entry.source.isNotEmpty ? entry.source : entry.sourceHost,
      snippet: entry.snippet,
    );
  }

  AnswerEvidenceBinding _fallbackBindingFromReference({
    required Map<String, dynamic> ref,
    required int index,
  }) {
    final normalized = SafeReferenceNormalizer.normalize(ref) ?? ref;
    final url = SafeReferenceNormalizer.canonicalizeUrl(
      (normalized['url'] as String?)?.trim() ?? '',
    );
    final title = (normalized['title'] as String?)?.trim().isNotEmpty == true
        ? (normalized['title'] as String).trim()
        : url;
    return AnswerEvidenceBinding(
      bindingId: 'answer_evidence_${index}_${url.hashCode}',
      label: _buildEvidenceBindingLabel(
        title: title,
        source: (ref['source'] as String?)?.trim() ?? '',
        url: url,
      ),
      claim: title,
      evidenceId: (ref['evidenceId'] as String?)?.trim() ?? '',
      url: url,
      title: title,
      source: (ref['source'] as String?)?.trim() ?? '',
      snippet: (ref['snippet'] as String?)?.trim() ?? '',
    );
  }

  EvidenceLedgerEntry? _matchEvidenceEntryForBinding({
    required String claim,
    required String title,
    required String snippet,
    required String directUrl,
    required String directEvidenceId,
    required List<EvidenceLedgerEntry> evidenceLedger,
  }) {
    for (final entry in evidenceLedger) {
      if (directEvidenceId.isNotEmpty && entry.evidenceId == directEvidenceId)
        return entry;
      if (directUrl.isNotEmpty &&
          SafeReferenceNormalizer.canonicalizeUrl(entry.url) == directUrl)
        return entry;
      final haystack = <String>[
        entry.evidenceId,
        entry.title,
        entry.source,
        entry.sourceHost,
        entry.snippet,
        entry.url,
      ].join(' ').toLowerCase();
      if (claim.trim().isNotEmpty &&
          haystack.contains(claim.trim().toLowerCase()))
        return entry;
      if (title.trim().isNotEmpty &&
          haystack.contains(title.trim().toLowerCase()))
        return entry;
      if (snippet.trim().isNotEmpty &&
          haystack.contains(snippet.trim().toLowerCase()))
        return entry;
    }
    return null;
  }

  Map<String, dynamic> _matchReferenceForEvidence({
    required String claim,
    required String title,
    required String snippet,
    required List<AssistantUiReferenceWireDto> uiReferences,
  }) {
    for (final ref in uiReferences) {
      final map = ref.toJson();
      final haystack = <String>[
        (map['title'] as String?)?.trim() ?? '',
        (map['source'] as String?)?.trim() ?? '',
        (map['snippet'] as String?)?.trim() ?? '',
        (map['url'] as String?)?.trim() ?? '',
      ].join(' ').toLowerCase();
      if (claim.trim().isNotEmpty &&
          haystack.contains(claim.trim().toLowerCase()))
        return map;
      if (title.trim().isNotEmpty &&
          haystack.contains(title.trim().toLowerCase()))
        return map;
      if (snippet.trim().isNotEmpty &&
          haystack.contains(snippet.trim().toLowerCase()))
        return map;
    }
    return const <String, dynamic>{};
  }
}
