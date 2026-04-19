part of 'assistant_pipeline_engine.dart';

bool _hasStructuredContent(Map<String, dynamic> value) => value.isNotEmpty;

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

String _mergeStableNarrativeFinalText({required String streamed, required String finalized}) {
  final streamedText = streamed.trim();
  final finalizedText = finalized.trim();
  if (streamedText.isEmpty) return finalizedText;
  if (finalizedText.isEmpty || streamedText == finalizedText || streamedText.startsWith(finalizedText)) return streamedText;
  final overlap = _suffixPrefixOverlap(streamedText, finalizedText);
  return overlap > 0 && overlap < finalizedText.length ? '$streamedText${finalizedText.substring(overlap)}'.trim() : streamedText;
}

int _suffixPrefixOverlap(String left, String right) {
  final maxOverlap = left.length < right.length ? left.length : right.length;
  for (var overlap = maxOverlap; overlap > 0; overlap--) {
    if (left.substring(left.length - overlap) == right.substring(0, overlap)) return overlap;
  }
  return 0;
}

String _sanitizeAnswerKeyFact(String raw) => SafeReferenceNormalizer.normalizeFact(raw);

String _formatChineseDate(DateTime date) {
  return '${date.year}年${date.month}月${date.day}日';
}

String _canonicalizeFinalAnswerTemporalAnchors(
  String text,
  IntentGraph intentGraph,
) {
  final trimmed = text.trim();
  if (trimmed.isEmpty) return '';
  final explicitDate = _firstUnderstandingSnapshotExplicitDate(intentGraph);
  if (explicitDate.isEmpty) return trimmed;
  final parsedDate = DateTime.tryParse(explicitDate);
  final dateText = parsedDate != null ? _formatChineseDate(parsedDate) : explicitDate;
  var normalized = trimmed;
  for (final token in const <String>[
    '明天',
    '后天',
    '今天',
    '昨日',
    '昨天',
    '前天',
    '今日',
    '明日',
  ]) {
    normalized = normalized.replaceAll(token, dateText);
  }
  return normalized;
}

String _composeDisplayMarkdown(
  String plainText,
  List<AssistantUiReferenceWireDto> uiReferences,
) {
  final references = uiReferences.take(3).map((item) {
    final title = item.title.trim().isNotEmpty ? item.title.trim() : item.source.trim();
    final safeTitle = title.isNotEmpty ? title : item.url.trim();
    return '[$safeTitle](${item.url.trim()})';
  }).where((item) => item.isNotEmpty).join(' ');
  if (references.isEmpty) return plainText.trim();
  return '${plainText.trim()}\n\n$references'.trim();
}

String _buildJourneyUnderstandingHeadline({
  required IntentGraph intentGraph,
  required String inferredCity,
}) {
  final goal = intentGraph.userGoal.trim();
  if (goal.isNotEmpty) return goal;
  if (inferredCity.isNotEmpty) return inferredCity;
  return '';
}

String _buildJourneyUnderstandingDetail({
  required IntentGraph intentGraph,
  required String reasonShort,
}) {
  final candidate = _firstNonEmptyText(<String?>[
    reasonShort,
    intentGraph.userJobToBeDone,
    intentGraph.inferredMotive,
  ]);
  return candidate;
}

String _buildJourneyAnalysisHeadline({
  required IntentGraph intentGraph,
  required String inferredCity,
  required String analysisSummary,
}) {
  final candidate = analysisSummary.trim();
  if (candidate.isNotEmpty) return candidate;
  if (inferredCity.isNotEmpty) return inferredCity;
  final goal = intentGraph.userGoal.trim();
  if (goal.isNotEmpty) return goal;
  return '';
}

String _buildJourneyAnalysisDetail({
  required String reasonShort,
  required String renderedText,
}) {
  final candidate = _firstNonEmptyText(<String?>[reasonShort, renderedText]);
  return candidate;
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
  final contextCity = (intentGraph.contextSlots['city'] as String?)?.trim() ?? '';
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

SlotStateSnapshot _buildSlotStateSnapshot({
  required String domainId,
  required SlotStateSnapshot previousSlotState,
  required IntentGraph intentGraph,
  required List<AnswerEvidenceBinding> groundingBindings,
}) {
  final mergedSlots = <String, dynamic>{...previousSlotState.slots, ...intentGraph.contextSlots};
  final mergedValues = <String, SlotValueSnapshot>{...previousSlotState.slotValues};
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

List<RunArtifactsUnderstandingResolutionItem> _deriveResolutionItemsFromIntentGraph(IntentGraph intentGraph) {
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
  final fromPayload = AssistantAnswerPayloadReadView(answerPayload).evidenceMaps.map((item) {
    final claim = (item['claim'] as String?)?.trim() ?? '';
    final text = (item['text'] as String?)?.trim() ?? '';
    return _sanitizeAnswerKeyFact(claim.isNotEmpty ? claim : text);
  }).where((item) => item.isNotEmpty).toList(growable: false);
  if (fromPayload.isNotEmpty) return fromPayload;
  final fromLedger = evidenceLedger
      .map((entry) => _sanitizeAnswerKeyFact(entry.snippet.isNotEmpty ? entry.snippet : entry.title))
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  if (fromLedger.isNotEmpty) return fromLedger;
  final fallbackText = _sanitizeAnswerKeyFact(
    ((answerPayload['userMarkdown'] as String?)?.trim().isNotEmpty == true
            ? (answerPayload['userMarkdown'] as String).trim()
            : ((answerPayload['result'] as Map?)?['text'] as String?)?.trim()) ??
        '',
  );
  return fallbackText.isNotEmpty ? <String>[fallbackText] : const <String>[];
}

String _firstUnderstandingSnapshotExplicitDate(IntentGraph intentGraph) {
  final qn = intentGraph.queryNormalization;
  for (final candidate in <String>[qn.timePoint, qn.timeRangeStart, qn.timeRangeEnd]) {
    if (candidate.trim().isNotEmpty) {
      return _canonicalizeUnderstandingSnapshotDateAnchors(candidate.trim());
    }
  }
  for (final task in intentGraph.queryTasks) {
    if (task.timePoint.trim().isNotEmpty) return _canonicalizeUnderstandingSnapshotDateAnchors(task.timePoint.trim());
  }
  return '';
}

extension AssistantPipelineStructuredResponseAssemblyCore on LocalPhaseExecutionOwner {
  Future<Map<String, dynamic>> buildStructuredResponsePayload({
    required AssistantRunRequest request,
    required ContextAssemblyResult contextAssembly,
    required SynthesisReadinessResult synthesisReadiness,
    required dynamic result,
    required IntentGraph intentGraph,
    required List<SkillRun> skillRuns,
    required AggregationState aggregationState,
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
    Map<String, dynamic> carriedUnderstandingSnapshot = const <String, dynamic>{},
    Map<String, dynamic> carriedRetrievalProcessing = const <String, dynamic>{},
    Map<String, dynamic> carriedHistoricalThinkingSnapshot = const <String, dynamic>{},
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
    final traces = (result.traces as List?)?.whereType<AssistantTraceEvent>().toList(growable: false) ?? const <AssistantTraceEvent>[];
    final answerPayload = parseAnswerPayload(
      rawFinalText: result.finalText as String? ?? '',
      traces: traces,
    );
    final toolResults = traces.where((event) => event.type == AssistantTraceEventType.toolResult).map(AssistantToolResultRow.fromTraceEvent).toList(growable: false);
    final evidenceLedger = _baselineKernel.buildEvidenceLedger(
      domainId: dialogueRoundScript.domainId,
      toolResults: _toolResultsForEvidenceLedger(toolResults),
      slotState: previousSlotState,
      retrievalPolicy: retrievalPolicy,
    );
    final uiReferences = _buildUiReferences(toolResults, isRealtimeLike: isRealtimeLikeRequest(fallbackProblemClass: intentGraph.problemClassWireName, answerPayload: answerPayload));
    final fallbackUiReferences = uiReferences.isNotEmpty
        ? uiReferences
        : _buildUiReferencesFromLedger(
            evidenceLedger,
            toolResults: toolResults.map((item) => item.toJson()).toList(growable: false),
            isRealtimeLike: isRealtimeLikeRequest(
              fallbackProblemClass: intentGraph.problemClassWireName,
              answerPayload: answerPayload,
            ),
          );
    final effectiveUiReferences = fallbackUiReferences.isNotEmpty ? fallbackUiReferences : uiReferences;
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
    final canonicalRenderedText = _canonicalizeFinalAnswerTemporalAnchors(
      renderedText,
      intentGraph,
    );
    final projectedConversationStateDecision = _buildProjectedConversationStateDecision(
      aggregationState: aggregationState,
      answerBoundaryPolicy: answerBoundaryPolicy,
      synthesisReadiness: synthesisReadiness,
      blockedProcessStepId: blockedProcessStepId,
    );
    final messageKind = _resolveMessageKind(
      answerPayload: answerPayload,
      resultText: canonicalRenderedText,
    );
    final isFallbackOutput = messageKind == AssistantMessageKind.fallback;
    final inferredCity = _inferPrimaryCity(intentGraph);
    final analysisSummary = _firstNonEmptyText(<String?>[
      ((answerPayload['result'] as Map?)?['interpretation'] as String?)?.trim(),
      skillSynthesisOutput.summary.trim(),
      ((answerPayload['result'] as Map?)?['summary'] as String?)?.trim(),
      (answerPayload['reasonShort'] as String?)?.trim(),
    ]);
    final reasonShort = (answerPayload['reasonShort'] as String?)?.trim() ?? '';
    final syntheticUiReferences = (!isFallbackOutput && effectiveUiReferences.isNotEmpty)
        ? effectiveUiReferences
        : <AssistantUiReferenceWireDto>[
            AssistantUiReferenceWireDto(
              title: _buildEvidenceBindingLabel(
                title: intentGraph.primarySkill,
                source: intentGraph.authorityDomains.isNotEmpty
                    ? intentGraph.authorityDomains.first.trim()
                    : '',
                url: 'https://example.com',
              ),
              url: intentGraph.authorityDomains.isNotEmpty
                  ? _trimTrailingSlashes(
                      'https://${intentGraph.authorityDomains.first.trim()}/${inferredCity.isNotEmpty ? inferredCity : ''}',
                    )
                  : 'https://example.com',
              source: intentGraph.authorityDomains.isNotEmpty
                  ? intentGraph.authorityDomains.first.trim()
                  : 'pipeline',
              snippet: canonicalRenderedText,
            ),
          ];
    final displayMarkdown = _composeDisplayMarkdown(
      canonicalRenderedText,
      syntheticUiReferences,
    );
    final projectedDisplayState = buildAssistantDisplayState(
      answerMarkdown: displayMarkdown,
      answerPlainText: canonicalRenderedText,
      finalAnswerReady: aggregationState.finalAnswerReady,
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
    final projectedProcessTimeline = buildProcessTimelineFromSnapshots(
      understandingSnapshot: projectedUnderstandingSnapshot,
      retrievalProcessing: _licensedRetrievalProcessingForSynthesis(
        carriedRetrievalProcessing,
      ),
      answerProcessing: _buildAnswerProcessingSnapshot(
        raw: answerPayload,
        streamedReadinessSummary: streamedAnswerReadinessSummary,
        synthesisReadiness: synthesisReadiness,
        stateDecision: _buildProjectedConversationStateDecision(
          aggregationState: aggregationState,
          answerBoundaryPolicy: answerBoundaryPolicy,
          synthesisReadiness: synthesisReadiness,
          blockedProcessStepId: blockedProcessStepId,
        ),
        evidenceEvaluation: const EvidenceEvaluationResult(),
        evidenceLedger: evidenceLedger,
        answerPayload: answerPayload,
      ),
    );
    final projectedProcessTimelineWithBlock =
        blockedProcessStepId == ProcessStepId.unknown
        ? projectedProcessTimeline
        : <ProcessTimelineFrame>[
            ...projectedProcessTimeline.where(
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
              answerProcessing: _buildAnswerProcessingSnapshot(
                raw: answerPayload,
                streamedReadinessSummary: streamedAnswerReadinessSummary,
                synthesisReadiness: synthesisReadiness,
                stateDecision: _buildProjectedConversationStateDecision(
                  aggregationState: aggregationState,
                  answerBoundaryPolicy: answerBoundaryPolicy,
                  synthesisReadiness: synthesisReadiness,
                  blockedProcessStepId: blockedProcessStepId,
                ),
                evidenceEvaluation: const EvidenceEvaluationResult(),
                evidenceLedger: evidenceLedger,
                answerPayload: answerPayload,
              ),
            ),
          ];
    final journeyStages = <Map<String, dynamic>>[
      <String, dynamic>{'stageId': 'understand', 'status': 'done', 'order': 0, 'summary': intentGraph.userGoal, 'referenceCount': 0},
      <String, dynamic>{'stageId': 'search', 'status': 'done', 'order': 1, 'summary': intentGraph.primarySkill, 'referenceCount': effectiveUiReferences.length},
      <String, dynamic>{
        'stageId': 'analyze',
        'status': 'done',
        'order': 2,
        'summary': _buildJourneyAnalysisHeadline(
          intentGraph: intentGraph,
          inferredCity: inferredCity,
          analysisSummary: analysisSummary,
        ),
        'referenceCount': effectiveUiReferences.length,
      },
      <String, dynamic>{
        'stageId': 'answer',
        'status': 'done',
        'order': 3,
        'summary': canonicalRenderedText,
        'referenceCount': effectiveUiReferences.length,
      },
    ];
    final response = <String, dynamic>{
      ...answerPayload,
      'finalText': canonicalRenderedText,
      'displayPlainText': canonicalRenderedText,
      'displayMarkdown': displayMarkdown,
      'messageKind': messageKind.wireName,
      'intentGraph': intentGraph.toJson(),
      'primarySkill': intentGraph.primarySkill,
      'understandingSnapshot': projectedUnderstandingSnapshot.toJson(),
      'finalAnswerMode': projectedConversationStateDecision.finalAnswerModeWireName,
      'displayState': projectedDisplayState.toJson(),
      'followupPrompt': _firstNonEmptyText(<String?>[
        (answerPayload['followupPrompt'] as String?)?.trim(),
        skillSynthesisOutput.followUpSuggestions.join('\n').trim(),
      ]),
      'actionHints': skillSynthesisOutput.followUpSuggestions.isNotEmpty
          ? skillSynthesisOutput.followUpSuggestions
          : normalizeStringList(answerPayload['actionHints']),
      'decision': <String, dynamic>{
        'nextAction': projectedConversationStateDecision.nextActionWireName,
        'messageKind': messageKind.wireName,
        'finalAnswerMode': projectedConversationStateDecision.finalAnswerModeWireName,
      },
      'conversationStateDecision': projectedConversationStateDecision.toJson(),
      'answerEligibility': projectedConversationStateDecision.answerEligibilityWireName,
      'journey': <String, dynamic>{
        'stages': journeyStages,
        'entries': <Map<String, dynamic>>[
          <String, dynamic>{
            'entryId': 'understanding_${dialogueRoundScript.domainId}',
            'stageId': 'understand',
            'kind': 'summary',
            'status': 'done',
            'order': 0,
            'headline': _buildJourneyUnderstandingHeadline(
              intentGraph: intentGraph,
              inferredCity: inferredCity,
            ),
            'detail': _buildJourneyUnderstandingDetail(
              intentGraph: intentGraph,
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
            'entryId': 'answer_${dialogueRoundScript.domainId}',
            'stageId': 'answer',
            'kind': 'summary',
            'status': 'done',
            'order': 1,
            'headline': _buildJourneyAnalysisHeadline(
              intentGraph: intentGraph,
              inferredCity: inferredCity,
              analysisSummary: analysisSummary,
            ),
            'detail': _buildJourneyAnalysisDetail(
              reasonShort: reasonShort,
              renderedText: renderedText,
            ),
            'references': syntheticUiReferences.map((item) => item.toJson()).toList(growable: false),
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
              : syntheticUiReferences.map((item) => item.toJson()).toList(growable: false),
        },
        'readiness': <String, dynamic>{},
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
      'skillRuns': skillRuns.map((item) => item.toJson()).toList(growable: false),
      'subagentPlan': subagentPlan.map((item) => item.toJson()).toList(growable: false),
      'subagentRuns': subagentRuns.map((item) => item.toJson()).toList(growable: false),
      'skillSynthesis': <String, dynamic>{
        'input': skillSynthesisInput.toJson(),
        'output': skillSynthesisOutput.toJson(),
      },
      'uiTimeline': buildStructuredResponseUiTimeline(subagentRuns: subagentRuns),
      'aggregationState': aggregationState.toJson(),
      'uiReferences': _uiReferenceWireMaps(effectiveUiReferences),
      'evidenceLedger': evidenceLedger.map((item) => item.toJson()).toList(growable: false),
      'toolResults': toolResults.map((item) => item.toJson()).toList(growable: false),
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
                stageId: parseJourneyStageId((item['stageId'] as String?) ?? ''),
                status: parseJourneyStageStatus((item['status'] as String?) ?? ''),
                order: (item['order'] as num?)?.toInt() ?? 0,
                summary: (item['summary'] as String?)?.trim() ?? '',
                referenceCount: (item['referenceCount'] as num?)?.toInt() ?? 0,
              ),
            )
            .toList(growable: false),
        entries: <AssistantJourneyEntry>[
          AssistantJourneyEntry(
            entryId: 'understanding_${dialogueRoundScript.domainId}',
            stageId: parseJourneyStageId('understand'),
            kind: parseJourneyEntryKind('summary'),
            status: parseJourneyStageStatus('done'),
            order: 0,
            headline: _buildJourneyUnderstandingHeadline(
              intentGraph: intentGraph,
              inferredCity: inferredCity,
            ),
            detail: _buildJourneyUnderstandingDetail(
              intentGraph: intentGraph,
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
            entryId: 'analysis_${dialogueRoundScript.domainId}',
            stageId: parseJourneyStageId('analyze'),
            kind: parseJourneyEntryKind('summary'),
            status: parseJourneyStageStatus('done'),
            order: 1,
            headline: _buildJourneyAnalysisHeadline(
              intentGraph: intentGraph,
              inferredCity: inferredCity,
              analysisSummary: analysisSummary,
            ),
            detail: _buildJourneyAnalysisDetail(
              reasonShort: reasonShort,
              renderedText: renderedText,
            ),
            provenance: AssistantJourneyProvenance(
              phaseId: parsePlannerPhaseId('analysis'),
              actionCode: parsePlannerActionCode('frameProblem'),
              reasonCode: parsePlannerReasonCode('prepare_delivery'),
              toolName: 'pipeline',
              source: 'structured_response',
            ),
          ),
          AssistantJourneyEntry(
            entryId: 'answer_${dialogueRoundScript.domainId}',
            stageId: parseJourneyStageId('answer'),
            kind: parseJourneyEntryKind('summary'),
            status: parseJourneyStageStatus('done'),
            order: 2,
            headline: renderedText,
            detail: effectiveUiReferences.isNotEmpty
                ? effectiveUiReferences.first.url
                : '',
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
      ),
      understandingSnapshot: projectedUnderstandingSnapshot,
      answerProcessing: _buildAnswerProcessingSnapshot(
        raw: answerPayload,
        streamedReadinessSummary: streamedAnswerReadinessSummary,
        synthesisReadiness: synthesisReadiness,
        stateDecision: ConversationStateDecision(
          nextAction: aggregationState.finalAnswerReady
              ? AssistantNextAction.answer
              : AssistantNextAction.askUser,
          finalAnswerMode: aggregationState.finalAnswerReady
              ? FinalAnswerMode.full
              : FinalAnswerMode.blocked,
          answerEligibility: aggregationState.finalAnswerReady
              ? AnswerEligibility.eligible
              : AnswerEligibility.blocked,
          slotState: previousSlotState,
          missingCriticalSlots: const <String>[],
          askUser: const AssistantTurnAskUser(),
          qualityGates: const QualityGatesDto(),
          finalAnswerReady: aggregationState.finalAnswerReady,
        ),
        evidenceEvaluation: const EvidenceEvaluationResult(),
        evidenceLedger: evidenceLedger,
        answerPayload: answerPayload,
      ),
      historicalThinkingSnapshot: _buildHistoricalThinkingSnapshot(
        raw: carriedHistoricalThinkingSnapshot,
        understandingSnapshot: _buildUnderstandingSnapshot(
          raw: carriedUnderstandingSnapshot,
          intentGraph: intentGraph,
          latestUserQuery: request.messages.isNotEmpty ? request.messages.last.content : '',
        ),
      ),
      retrievalProcessing: _buildRetrievalProcessingSnapshot(
        processing: carriedRetrievalProcessing,
        streamedProcessingSummary: streamedRetrievalProcessingSummary,
        uiReferences: effectiveUiReferences,
        toolResults: toolResults,
        synthesisReadiness: synthesisReadiness,
        finalAnswerReady: aggregationState.finalAnswerReady,
      ),
      evidenceLedger: evidenceLedger,
      answerEvidenceBindings: answerEvidenceBindings,
      slotState: currentSlotState,
      domainPolicyBundle: previousDomainPolicyBundle ??
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
      final raw = (item.dataPayload['blockingDimensions'] as List?)?.whereType<String>().toList(growable: false) ?? const <String>[];
      dimensions.addAll(raw.map((value) => value.trim()).where((value) => value.isNotEmpty));
    }
    return dimensions.toList(growable: false);
  }

  bool _hasRenderableAnswerPayload({
    required Map<String, dynamic> payload,
    required Object? turn,
    required bool projectionRenderableContent,
  }) {
    final userMarkdown = (payload['userMarkdown'] as String?)?.trim() ?? '';
    final resultText = ((payload['result'] as Map?)?['text'] as String?)?.trim() ?? '';
    return projectionRenderableContent || userMarkdown.isNotEmpty || resultText.isNotEmpty;
  }

  List<AssistantUiReferenceWireDto> _buildUiReferences(
    List<AssistantToolResultRow> toolResults, {
    required bool isRealtimeLike,
  }) {
    final refs = <AssistantUiReferenceWireDto>[];
    final seen = <String>{};
    for (final item in toolResults) {
      final rawRefs = (item.dataPayload['references'] as List?)?.whereType<Map>().toList(growable: false) ?? const <Map>[];
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
        refs.add(AssistantUiReferenceWireDto(
          title: (map['title'] as String?)?.trim() ?? '',
          url: url,
          source: (map['source'] as String?)?.trim() ?? '',
          snippet: (map['snippet'] as String?)?.trim() ?? '',
        ));
      }
    }
    return refs;
  }

  ConversationStateDecision _buildProjectedConversationStateDecision({
    required AggregationState aggregationState,
    required AnswerBoundaryPolicy answerBoundaryPolicy,
    required SynthesisReadinessResult synthesisReadiness,
    required ProcessStepId blockedProcessStepId,
  }) {
    final shouldReplanForRetrievalBlock =
        !synthesisReadiness.ready && synthesisReadiness.replanTask != null;
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
    return ConversationStateDecision(
      nextAction: aggregationState.finalAnswerReady
          ? AssistantNextAction.answer
          : AssistantNextAction.askUser,
      finalAnswerMode: answerBoundaryPolicy.allowBoundedAnswer
          ? FinalAnswerMode.boundedAnswer
          : FinalAnswerMode.blocked,
      answerEligibility: aggregationState.finalAnswerReady
          ? AnswerEligibility.eligible
          : AnswerEligibility.blocked,
      slotState: const SlotStateSnapshot(),
      missingCriticalSlots: const <String>[],
      askUser: const AssistantTurnAskUser(),
      qualityGates: const QualityGatesDto(),
      finalAnswerReady: aggregationState.finalAnswerReady,
    );
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
      goal: _firstNonEmptyText(<String?>[intentGraph.userGoal, intentGraph.userJobToBeDone, intentGraph.targetObject]),
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

  SkillRun Function(AssistantSubagentRunRecord) get _skillRunFromLegacySubagentRun {
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
    final answerReady = ((answerPayload['result'] as Map?)?['text'] as String?)?.trim().isNotEmpty == true;
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
    final parsed = parseMessageKind((answerPayload['messageKind'] as String?)?.trim() ?? '');
    if (parsed != AssistantMessageKind.unknown) return parsed;
    return resultText.trim().isNotEmpty ? AssistantMessageKind.answer : AssistantMessageKind.fallback;
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
        : <String>[...intentGraph.hardConstraints, ...intentGraph.softConstraints].where((item) => item.trim().isNotEmpty).take(4).toList(growable: false);
    final canonicalQuery = _firstNonEmptyText(<String?>[
      intentGraph.queryNormalization.rewrittenQuery,
      intentGraph.queryNormalization.normalizedQuery,
      intentGraph.queryTasks.isNotEmpty ? intentGraph.queryTasks.first.query : '',
    ]);
    final intentSummary = parsed.intentSummary.trim().isNotEmpty
        ? parsed.intentSummary.trim()
        : _firstNonEmptyText(<String?>[
            intentGraph.userGoal,
            intentGraph.userJobToBeDone,
            intentGraph.targetObject,
            latestUserQuery,
            canonicalQuery,
          ]);
    final userFacingSummary = parsed.userFacingSummary.trim().isNotEmpty
        ? parsed.userFacingSummary.trim()
        : _firstNonEmptyText(<String?>[
            parsed.intentSummary,
            intentSummary,
            intentGraph.userGoal,
            intentGraph.userJobToBeDone,
            intentGraph.targetObject,
            latestUserQuery,
            canonicalQuery,
          ]);
    return RunArtifactsUnderstandingSnapshot(
      intentSummary: _normalizeFinalAnswerTemporalAnchors(intentSummary, intentGraph),
      userFacingSummary: _normalizeFinalAnswerTemporalAnchors(userFacingSummary, intentGraph),
      concernPoints: concernPoints,
      emotionSignal: parsed.emotionSignal,
      resolutionItems: parsed.resolutionItems.isNotEmpty ? parsed.resolutionItems : _deriveResolutionItemsFromIntentGraph(intentGraph),
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
    final keyFacts = (parsed.keyFacts.isNotEmpty ? parsed.keyFacts : _buildAnswerKeyFacts(answerPayload: answerPayload, evidenceLedger: evidenceLedger)).map(_sanitizeAnswerKeyFact).where((item) => item.isNotEmpty).take(4).toList(growable: false);
    final missingDimensions = parsed.missingDimensions.isNotEmpty ? parsed.missingDimensions : stateDecision.missingCriticalSlots.where((item) => item.trim().isNotEmpty).take(4).toList(growable: false);
    final retrieveMoreReason = parsed.retrieveMoreReason.isNotEmpty ? parsed.retrieveMoreReason : (stateDecision.finalAnswerReady ? '' : _firstNonEmptyText(<String?>[synthesisReadiness.reason, evidenceEvaluation.summary]));
    final fallbackFact = _sanitizeAnswerKeyFact(
      _firstNonEmptyText(<String?>[
        (answerPayload['userMarkdown'] as String?)?.trim(),
        ((answerPayload['result'] as Map?)?['text'] as String?)?.trim(),
        streamedReadinessSummary,
      ]),
    );
    return RunArtifactsAnswerProcessing(
      readinessSummary: _mergeStableNarrativeFinalText(streamed: streamedReadinessSummary, finalized: parsed.readinessSummary),
      keyFacts: keyFacts.isNotEmpty ? keyFacts : (fallbackFact.isNotEmpty ? <String>[fallbackFact] : keyFacts),
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
      mismatchSignal: parsed.mismatchSignal.isNotEmpty ? parsed.mismatchSignal : understandingSnapshot.mismatchSignal,
      carryForwardFacts: parsed.carryForwardFacts.isNotEmpty ? parsed.carryForwardFacts : understandingSnapshot.carryForwardFacts,
      needsRecheckFacts: parsed.needsRecheckFacts,
      discardedAssumptions: parsed.discardedAssumptions.isNotEmpty ? parsed.discardedAssumptions : understandingSnapshot.discardedAssumptions,
    );
  }

  String _normalizeFinalAnswerTemporalAnchors(String text, IntentGraph intentGraph) {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return '';
    final normalized = _canonicalizeUnderstandingSnapshotDateAnchors(trimmed);
    final qn = intentGraph.queryNormalization;
    final modelAnchors = <String>[
      qn.timePoint,
      qn.timeRangeStart,
      qn.timeRangeEnd,
      qn.timeScope,
    ].map((item) => item.trim()).where((item) => item.isNotEmpty).toList(growable: false);
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
    required SynthesisReadinessResult synthesisReadiness,
    required bool finalAnswerReady,
  }) {
    final selectedKeyPoints = uiReferences
        .map((item) => _sanitizeAnswerKeyFact(
              item.title.trim().isNotEmpty ? item.title.trim() : item.snippet.trim(),
            ))
        .where((item) => item.isNotEmpty)
        .take(5)
        .toList(growable: false);
    final map = <String, dynamic>{
      ...processing,
      'processedDocumentCount': math.max(toolResults.length, uiReferences.length),
      'acceptedDocumentCount': uiReferences.length,
      'selectedKeyPoints': selectedKeyPoints.isNotEmpty
          ? selectedKeyPoints
          : (streamedProcessingSummary.trim().isNotEmpty
              ? <String>[_sanitizeAnswerKeyFact(streamedProcessingSummary)]
              : const <String>[]),
      'acceptedReferences': uiReferences.map((item) => item.toJson()).toList(growable: false),
    };
    return RetrievalProcessingSnapshot.fromJson(map);
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
    for (final item in AssistantAnswerPayloadReadView(answerPayload).evidenceMaps) {
      final candidate = _normalizeInlineEvidenceBinding(item: item, uiReferences: uiReferences, evidenceLedger: evidenceLedger, index: bindings.length + 1);
      if (candidate == null) continue;
      final dedupeKey = candidate.evidenceId.isNotEmpty ? candidate.evidenceId : candidate.url;
      if (dedupeKey.isEmpty || !seen.add(dedupeKey)) continue;
      bindings.add(candidate);
      if (bindings.length >= 4) break;
    }
    if (bindings.isEmpty) {
      for (final entry in evidenceLedger.take(2)) {
        final dedupeKey = entry.evidenceId.isNotEmpty ? entry.evidenceId : entry.url;
        if (dedupeKey.isEmpty || !seen.add(dedupeKey)) continue;
        bindings.add(_fallbackBindingFromEvidenceEntry(entry: entry, index: bindings.length + 1));
      }
    }
    if (bindings.isEmpty) {
      for (final ref in uiReferences.take(2)) {
        final refMap = ref.toJson();
        final url = (refMap['url'] as String?)?.trim() ?? '';
        if (url.isEmpty || !seen.add(url)) continue;
        bindings.add(_fallbackBindingFromReference(ref: refMap, index: bindings.length + 1));
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
    final claim = ((item['text'] as String?)?.trim().isNotEmpty == true ? (item['text'] as String).trim() : (item['claim'] as String?)?.trim()) ?? '';
    final directEvidenceId = (item['evidenceId'] as String?)?.trim() ?? '';
    final directUrl = SafeReferenceNormalizer.canonicalizeUrl((item['url'] as String?)?.trim() ?? '');
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
      matchedReference = _matchReferenceForEvidence(claim: claim, title: directTitle, snippet: directSnippet, uiReferences: uiReferences);
    }
    final url = directUrl.isNotEmpty
        ? directUrl
        : (matchedEvidence?.url.isNotEmpty == true
            ? matchedEvidence!.url
            : SafeReferenceNormalizer.canonicalizeUrl((matchedReference['url'] as String?)?.trim() ?? ''));
    if (url.isEmpty) return null;
    final normalizedReference = SafeReferenceNormalizer.normalize(<String, dynamic>{
      'url': url,
      'title': directTitle.isNotEmpty
          ? directTitle
          : (matchedEvidence?.title.isNotEmpty == true ? matchedEvidence!.title : ((matchedReference['title'] as String?)?.trim().isNotEmpty == true ? (matchedReference['title'] as String).trim() : url)),
      'source': matchedEvidence?.source.isNotEmpty == true
          ? matchedEvidence!.source
          : (directSource.isNotEmpty
              ? directSource
              : (matchedEvidence?.sourceHost.isNotEmpty == true ? matchedEvidence!.sourceHost : (matchedReference['source'] as String?)?.trim() ?? '')),
      'snippet': directSnippet.isNotEmpty
          ? directSnippet
          : (matchedEvidence?.snippet.isNotEmpty == true ? matchedEvidence!.snippet : (matchedReference['snippet'] as String?)?.trim() ?? ''),
    });
    if (normalizedReference == null) return null;
    final source = matchedEvidence?.source.isNotEmpty == true
        ? matchedEvidence!.source
        : (directSource.isNotEmpty
            ? directSource
            : (matchedEvidence?.sourceHost.isNotEmpty == true ? matchedEvidence!.sourceHost : (normalizedReference['source'] as String?)?.trim() ?? ''));
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
      bindingId: 'answer_evidence_${index}_${entry.evidenceId.isNotEmpty ? entry.evidenceId : entry.url.hashCode}',
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
    final url = SafeReferenceNormalizer.canonicalizeUrl((normalized['url'] as String?)?.trim() ?? '');
    final title = (normalized['title'] as String?)?.trim().isNotEmpty == true ? (normalized['title'] as String).trim() : url;
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
      if (directEvidenceId.isNotEmpty && entry.evidenceId == directEvidenceId) return entry;
      if (directUrl.isNotEmpty && SafeReferenceNormalizer.canonicalizeUrl(entry.url) == directUrl) return entry;
      final haystack = <String>[entry.evidenceId, entry.title, entry.source, entry.sourceHost, entry.snippet, entry.url].join(' ').toLowerCase();
      if (claim.trim().isNotEmpty && haystack.contains(claim.trim().toLowerCase())) return entry;
      if (title.trim().isNotEmpty && haystack.contains(title.trim().toLowerCase())) return entry;
      if (snippet.trim().isNotEmpty && haystack.contains(snippet.trim().toLowerCase())) return entry;
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
      final haystack = <String>[(map['title'] as String?)?.trim() ?? '', (map['source'] as String?)?.trim() ?? '', (map['snippet'] as String?)?.trim() ?? '', (map['url'] as String?)?.trim() ?? ''].join(' ').toLowerCase();
      if (claim.trim().isNotEmpty && haystack.contains(claim.trim().toLowerCase())) return map;
      if (title.trim().isNotEmpty && haystack.contains(title.trim().toLowerCase())) return map;
      if (snippet.trim().isNotEmpty && haystack.contains(snippet.trim().toLowerCase())) return map;
    }
    return const <String, dynamic>{};
  }

  List<String> _evidenceScoreTokens(String text) {
    final tokens = <String>[];
    final buffer = StringBuffer();
    for (final rune in text.runes) {
      final ch = String.fromCharCode(rune).toLowerCase();
      final code = ch.codeUnitAt(0);
      final isAsciiLetterOrDigit = (code >= 48 && code <= 57) || (code >= 97 && code <= 122);
      final isChinese = code >= 0x4e00 && code <= 0x9fa5;
      if (isAsciiLetterOrDigit || isChinese) {
        buffer.write(ch);
        continue;
      }
      if (buffer.isNotEmpty) {
        tokens.add(buffer.toString());
        buffer.clear();
      }
    }
    if (buffer.isNotEmpty) tokens.add(buffer.toString());
    return tokens.toSet().toList(growable: false);
  }

  bool _isStrictRealtimeReference({
    required String title,
    required String source,
    required String snippet,
    required String sourceTier,
    required double authorityScore,
    required double freshnessHours,
    required bool isAuthoritative,
  }) {
    if (isAuthoritative) return true;
    if (authorityScore >= 0.8) return true;
    if (freshnessHours > 0 && freshnessHours <= 24) return true;
    final normalizedTier = sourceTier.trim().toLowerCase();
    return normalizedTier == 'authority' || normalizedTier == 'page';
  }
}
