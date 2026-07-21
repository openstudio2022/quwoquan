part of 'personal_assistant_stream_controller.dart';

List<String> extractAssistantEmergedTags(
  List<AssistantStreamEventWire> events,
) {
  final result = <String>[];
  final seen = <String>{};
  for (final event in events) {
    final streamEvent = AssistantRunStreamEvent.fromWire(event);
    if (streamEvent.type != AssistantRunStreamEventType.completed) {
      continue;
    }
    for (final tag in streamEvent.emergedTags) {
      if (tag.isEmpty || !seen.add(tag)) continue;
      result.add(tag);
    }
  }
  return result;
}

void _debugPersonalAssistant(String message) {
  if (!kDebugMode && !kProfileMode) {
    return;
  }
  debugPrint('[personal-assistant] $message');
}

String _debugSnippet(String value, {int maxLength = 120}) {
  final normalized = value.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return '${normalized.substring(0, maxLength)}...';
}

PersonalAssistantProcessSummary _projectProcessSummary(
  PersonalAssistantProcessSummary current,
  AssistantRunStreamEvent event, {
  required int elapsedMs,
}) {
  if (event.type == AssistantRunStreamEventType.processReplace) {
    return const PersonalAssistantProcessSummary().copyWith(
      elapsedMs: elapsedMs,
      processes: List<AssistantRunVisibleProcess>.unmodifiable(event.processes),
    );
  }
  final incoming = event.process;
  if (incoming == null) {
    return current.copyWith(elapsedMs: elapsedMs);
  }
  final byId = <String, AssistantRunVisibleProcess>{
    for (final process in current.processes) process.processId: process,
  };
  final existing = byId[incoming.processId];
  byId[incoming.processId] = existing == null
      ? incoming
      : existing.copyWith(
          status: incoming.status,
          summary: incoming.summary.isEmpty ? existing.summary : incoming.summary,
          searchedDocumentCount: incoming.searchedDocumentCount > 0
              ? incoming.searchedDocumentCount
              : existing.searchedDocumentCount,
          processedDocumentCount: incoming.processedDocumentCount > 0
              ? incoming.processedDocumentCount
              : existing.processedDocumentCount,
          acceptedDocumentCount: incoming.acceptedDocumentCount > 0
              ? incoming.acceptedDocumentCount
              : existing.acceptedDocumentCount,
          acceptedReferences: incoming.acceptedReferences.isEmpty
              ? existing.acceptedReferences
              : incoming.acceptedReferences,
        );
  final processes = byId.values.toList()
    ..sort((left, right) => left.order.compareTo(right.order));
  var processedCount = current.processedCount;
  var searchCount = current.searchCount;
  var acceptedCount = current.acceptedCount;
  var understandingSummary = current.understandingSummary;
  var retrievalDesignNarrative = current.retrievalDesignNarrative;
  var processingSummary = current.processingSummary;
  var expansionReason = current.expansionReason;
  var finalAnswerSummary = current.finalAnswerSummary;
  var finalAnswerReady = current.finalAnswerReady;
  var selectedKeyPoints = current.selectedKeyPoints;
  var acceptedReferences = current.acceptedReferences;
  final lines = <String>[];
  for (final process in processes) {
    final line = _processLineForProcess(process);
    if (line.isNotEmpty && !lines.contains(line)) {
      lines.add(line);
    }
    switch (process.stage) {
      case 'planning':
        if (process.summary.isNotEmpty) {
          understandingSummary = process.summary;
          retrievalDesignNarrative = process.summary;
        }
        break;
      case 'evidence_review':
        searchCount = process.searchedDocumentCount > 0
            ? process.searchedDocumentCount
            : searchCount;
        processedCount = process.processedDocumentCount > 0
            ? process.processedDocumentCount
            : processedCount;
        acceptedCount = process.acceptedDocumentCount > 0
            ? process.acceptedDocumentCount
            : acceptedCount;
        if (process.summary.isNotEmpty) {
          processingSummary = process.summary;
        }
        if (process.acceptedReferences.isNotEmpty) {
          acceptedReferences = process.acceptedReferences
              .map(
                (reference) => RetrievalProcessingReference(
                  title: reference.title,
                  url: reference.url,
                  source: reference.source,
                  snippet: reference.snippet,
                ),
              )
              .toList(growable: false);
        }
        break;
      case 'answer_generation':
        finalAnswerSummary = AssistantText.assistantProcessFinalAnswerNarrative;
        finalAnswerReady =
            finalAnswerReady || process.status == 'completed';
        break;
    }
  }
  return current.copyWith(
    processedCount: processedCount,
    searchCount: searchCount,
    acceptedCount: acceptedCount,
    elapsedMs: elapsedMs,
    lines: List<String>.unmodifiable(lines.take(6)),
    understandingSummary: understandingSummary,
    retrievalDesignNarrative: retrievalDesignNarrative,
    processingSummary: processingSummary,
    expansionReason: expansionReason,
    finalAnswerSummary: finalAnswerSummary,
    finalAnswerReady: finalAnswerReady,
    processes: List<AssistantRunVisibleProcess>.unmodifiable(processes),
    selectedKeyPoints: List<String>.unmodifiable(selectedKeyPoints),
    acceptedReferences: List<RetrievalProcessingReference>.unmodifiable(
      acceptedReferences,
    ),
  );
}

String _processLineForProcess(AssistantRunVisibleProcess process) {
  final stage = switch (process.stage) {
    'skill_selection' => AssistantText.assistantProcessStageUnderstand,
    'planning' => AssistantText.assistantProcessStageRetrievalDesign,
    'tool_execution' => AssistantText.assistantProcessSearching,
    'evidence_review' => AssistantText.assistantProcessStageRetrievalProcessing,
    'answer_generation' => AssistantText.assistantProcessStageAnswer,
    _ => '',
  };
  if (stage.isEmpty) {
    return '';
  }
  if (process.summary.isEmpty) {
    return stage;
  }
  return '$stage：${process.summary}';
}

String _openedTurnAnswer(AssistantTurnEnvelopeWire turn) {
  final text = turn.input['text']?.toString().trim();
  if (text != null && text.isNotEmpty) {
    return AssistantText.assistantProactiveReminderOpened(text);
  }
  return AssistantText.assistantProactiveReminderOpenedDefault;
}

List<AssistantTranscriptTimelineRow> _appendOpenedTurnTranscript(
  List<AssistantTranscriptTimelineRow> current,
  AssistantTurnEnvelopeWire turn,
) {
  final answer = _openedTurnAnswer(turn);
  return <AssistantTranscriptTimelineRow>[
    ...current,
    _personalAssistantAssistantRow(
      id: 'proactive_source_${turn.turnId}',
      text: AssistantText.assistantProactiveReminderSource,
      turnId: turn.turnId,
      proactive: true,
    ),
    _personalAssistantAssistantRow(
      id: 'proactive_${turn.turnId}',
      text: answer,
      turnId: turn.turnId,
      traceId: turn.traceId,
      proactive: true,
    ),
  ];
}

List<AssistantTranscriptTimelineRow> _upsertAssistantTranscript(
  List<AssistantTranscriptTimelineRow> current,
  String id, {
  required String text,
  String turnId = '',
  String traceId = '',
  String sourceQuery = '',
  String eventType = '',
  bool streaming = false,
  PersonalAssistantProcessSummary processSummary =
      const PersonalAssistantProcessSummary(),
}) {
  return current
      .map(
        (item) => item.id == id && item is AssistantAnswerTranscriptRow
            ? _personalAssistantAssistantRow(
                id: id,
                text: text,
                turnId: turnId,
                traceId: traceId,
                sourceQuery: sourceQuery,
                eventType: eventType,
                streaming: streaming,
                processSummary: processSummary,
              )
            : item,
      )
      .toList(growable: false);
}

UserTranscriptTimelineRow _personalAssistantUserRow({
  required String id,
  required String text,
}) {
  return UserTranscriptTimelineRow(
    id: id,
    conversationId: AppConceptConstants.assistantConversationId,
    type: 'text',
    content: text,
    senderId: 'current_user',
    senderName: AssistantText.assistantCurrentUserSenderName,
    timestamp: _personalAssistantTimestamp(),
    status: '',
    isRead: true,
  );
}

AssistantAnswerTranscriptRow _personalAssistantAssistantRow({
  required String id,
  required String text,
  String turnId = '',
  String traceId = '',
  String sourceQuery = '',
  String eventType = '',
  bool streaming = false,
  bool proactive = false,
  PersonalAssistantProcessSummary processSummary =
      const PersonalAssistantProcessSummary(),
}) {
  final projection = _personalAssistantRunArtifacts(
    text: text,
    processSummary: processSummary,
  );
  final runArtifacts = projection.toRunArtifactsJson(eventType: eventType);
  final persisted = PersistedAssistantTimelinePayload.empty()
      .copyWithMerged(<String, Object?>{
        assistantDisplayMarkdownField: text,
        assistantDisplayPlainTextField: text,
        assistantJourneyField: projection.journey.toJson(),
        assistantProcessTimelineField: projection.processTimeline
            .map((frame) => frame.toJson())
            .toList(growable: false),
        assistantUiProcessTimelineField: projection.journey.toJson(),
        assistantUnderstandingSnapshotField: projection.understandingSnapshot
            .toJson(),
        assistantRetrievalProcessingField: projection.retrievalProcessing
            .toJson(),
        'assistantElapsedMs': processSummary.elapsedMs,
      });
  return AssistantAnswerTranscriptRow(
    id: id,
    conversationId: AppConceptConstants.assistantConversationId,
    type: 'text',
    content: text,
    senderId: AppConceptConstants.assistantSenderId,
    senderName: AppConceptConstants.assistantLabel,
    timestamp: _personalAssistantTimestamp(),
    isRead: true,
    streaming: streaming,
    streamFinalAnswer: streaming ? text : '',
    anchor: AssistantAnswerAnchor(
      runId: turnId,
      traceId: traceId,
      sourceQuery: sourceQuery,
      domainId: 'assistant',
    ),
    persisted: persisted,
    runArtifacts: runArtifacts,
    extra: <String, Object?>{
      if (turnId.isNotEmpty) 'turnId': turnId,
      if (eventType.isNotEmpty) 'eventType': eventType,
      if (proactive) 'proactive': true,
    },
  );
}

_PersonalAssistantRunArtifactsProjection _personalAssistantRunArtifacts({
  required String text,
  required PersonalAssistantProcessSummary processSummary,
}) {
  final processTimeline = _personalAssistantProcessTimeline(processSummary);
  final journey = _personalAssistantJourney(processSummary);
  final understandingSnapshot = _personalAssistantUnderstandingSnapshot(
    processSummary,
  );
  final retrievalProcessing = _personalAssistantRetrievalProcessing(
    processSummary,
  );
  return _PersonalAssistantRunArtifactsProjection(
    displayMarkdown: text,
    displayPlainText: text,
    journey: journey,
    processTimeline: processTimeline,
    understandingSnapshot: understandingSnapshot,
    retrievalProcessing: retrievalProcessing,
    processedCount: processSummary.processedCount,
    searchCount: processSummary.searchCount,
    acceptedCount: processSummary.acceptedCount,
  );
}

class _PersonalAssistantRunArtifactsProjection {
  const _PersonalAssistantRunArtifactsProjection({
    required this.displayMarkdown,
    required this.displayPlainText,
    required this.journey,
    required this.processTimeline,
    required this.understandingSnapshot,
    required this.retrievalProcessing,
    required this.processedCount,
    required this.searchCount,
    required this.acceptedCount,
  });

  final String displayMarkdown;
  final String displayPlainText;
  final AssistantJourney journey;
  final List<ProcessTimelineFrame> processTimeline;
  final RunArtifactsUnderstandingSnapshot understandingSnapshot;
  final RetrievalProcessingSnapshot retrievalProcessing;
  final int processedCount;
  final int searchCount;
  final int acceptedCount;

  Map<String, Object?> toRunArtifactsJson({String eventType = ''}) {
    return <String, Object?>{
      assistantDisplayMarkdownField: displayMarkdown,
      assistantDisplayPlainTextField: displayPlainText,
      assistantJourneyField: journey.toJson(),
      assistantProcessTimelineField: processTimeline
          .map((frame) => frame.toJson())
          .toList(growable: false),
      assistantUnderstandingSnapshotField: understandingSnapshot.toJson(),
      assistantRetrievalProcessingField: retrievalProcessing.toJson(),
      'diagnostics': <String, Object?>{
        if (eventType.isNotEmpty) 'lastEventType': eventType,
        'processedCount': processedCount,
        'searchCount': searchCount,
        'acceptedCount': acceptedCount,
      },
    };
  }
}

AssistantJourney _personalAssistantJourney(
  PersonalAssistantProcessSummary processSummary,
) {
  final hasProcess = processSummary.lines.isNotEmpty;
  final hasSearch = processSummary.searchCount > 0;
  final hasRetrieval =
      processSummary.processingSummary.trim().isNotEmpty ||
      processSummary.acceptedReferences.isNotEmpty ||
      processSummary.acceptedCount > 0;
  return AssistantJourney(
    stages: <AssistantJourneyStage>[
      _journeyStage(
        JourneyStageId.analyze,
        hasProcess ? JourneyStageStatus.completed : JourneyStageStatus.active,
        0,
      ),
      _journeyStage(
        JourneyStageId.search,
        hasSearch
            ? JourneyStageStatus.completed
            : (hasProcess
                  ? JourneyStageStatus.active
                  : JourneyStageStatus.pending),
        1,
        referenceCount: processSummary.searchCount,
      ),
      _journeyStage(
        JourneyStageId.verify,
        hasRetrieval
            ? JourneyStageStatus.completed
            : (hasSearch
                  ? JourneyStageStatus.active
                  : JourneyStageStatus.pending),
        2,
      ),
      _journeyStage(
        JourneyStageId.answer,
        processSummary.finalAnswerReady
            ? JourneyStageStatus.completed
            : (processSummary.finalAnswerSummary.trim().isNotEmpty
                  ? JourneyStageStatus.active
                  : (hasRetrieval
                        ? JourneyStageStatus.active
                        : JourneyStageStatus.pending)),
        3,
      ),
    ],
    entries: processSummary.lines
        .asMap()
        .entries
        .map(
          (entry) => AssistantJourneyEntry(
            entryId: 'personal_process_${entry.key}',
            stageId: _stageIdForProcessIndex(entry.key),
            kind: JourneyEntryKind.narrative,
            status: JourneyStageStatus.completed,
            order: entry.key,
            headline: entry.value,
          ),
        )
        .toList(growable: false),
    summary: processSummary.lines.isEmpty ? '' : processSummary.lines.last,
    referenceSummary: AssistantJourneyReferenceSummary(
      count: processSummary.searchCount,
      references: _journeyReferences(processSummary.acceptedReferences),
    ),
    readiness: AssistantJourneyReadiness(
      finalAnswerReady: processSummary.finalAnswerReady,
    ),
  );
}

AssistantJourneyStage _journeyStage(
  JourneyStageId stageId,
  JourneyStageStatus status,
  int order, {
  int referenceCount = 0,
}) {
  return AssistantJourneyStage(
    stageId: stageId,
    status: status,
    order: order,
    referenceCount: referenceCount,
  );
}

List<AssistantJourneyReference> _journeyReferences(
  List<RetrievalProcessingReference> references,
) {
  return references
      .map(
        (reference) => AssistantJourneyReference(
          title: reference.title,
          url: reference.url,
          source: reference.source,
        ),
      )
      .toList(growable: false);
}

List<ProcessTimelineFrame> _personalAssistantProcessTimeline(
  PersonalAssistantProcessSummary processSummary,
) {
  final frames = <ProcessTimelineFrame>[];
  final understandingSnapshot = _personalAssistantUnderstandingSnapshot(
    processSummary,
  );
  if (processSummary.understandingSummary.trim().isNotEmpty) {
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.understanding,
        headline: processSummary.understandingSummary.trim(),
        understandingSnapshot: understandingSnapshot,
      ),
    );
  }
  if (processSummary.retrievalDesignNarrative.trim().isNotEmpty) {
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.retrievalDesign,
        headline: processSummary.retrievalDesignNarrative.trim(),
        understandingSnapshot: understandingSnapshot,
      ),
    );
  }
  final retrievalProcessing = _personalAssistantRetrievalProcessing(
    processSummary,
  );
  if (processSummary.processingSummary.trim().isNotEmpty ||
      processSummary.acceptedReferences.isNotEmpty ||
      processSummary.acceptedCount > 0) {
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.retrievalProcessing,
        headline: processSummary.processingSummary.trim(),
        detail: processSummary.expansionReason.trim(),
        references: processSummary.acceptedReferences,
        retrievalProcessing: retrievalProcessing,
      ),
    );
  }
  if (processSummary.finalAnswerSummary.trim().isNotEmpty) {
    frames.add(
      buildProcessTimelineFrame(
        stepId: ProcessStepId.answerOrganization,
        status: processSummary.finalAnswerReady
            ? JourneyStageStatus.completed
            : JourneyStageStatus.active,
        headline: processSummary.finalAnswerSummary.trim(),
        answerProcessing: RunArtifactsAnswerProcessing(
          readinessSummary: processSummary.finalAnswerSummary.trim(),
        ),
      ),
    );
  }
  if (frames.isNotEmpty) {
    return frames;
  }
  return processSummary.lines
      .asMap()
      .entries
      .map(
        (entry) => _fallbackProcessFrame(
          stepId: _processStepIdForProcessIndex(entry.key),
          headline: entry.value,
          processSummary: processSummary,
        ),
      )
      .toList(growable: false);
}

ProcessTimelineFrame _fallbackProcessFrame({
  required ProcessStepId stepId,
  required String headline,
  required PersonalAssistantProcessSummary processSummary,
}) {
  if (stepId == ProcessStepId.understanding) {
    return buildProcessTimelineFrame(
      stepId: stepId,
      headline: headline,
      understandingSnapshot: RunArtifactsUnderstandingSnapshot(
        intentSummary: headline,
        userFacingSummary: headline,
      ),
    );
  }
  return buildProcessTimelineFrame(
    stepId: stepId,
    headline: headline,
    retrievalProcessing: _personalAssistantRetrievalProcessing(
      processSummary.copyWith(processingSummary: headline),
    ),
  );
}

RunArtifactsUnderstandingSnapshot _personalAssistantUnderstandingSnapshot(
  PersonalAssistantProcessSummary processSummary,
) {
  return RunArtifactsUnderstandingSnapshot(
    intentSummary: processSummary.understandingSummary.trim(),
    userFacingSummary: processSummary.understandingSummary.trim(),
    retrievalDesignNarrative: processSummary.retrievalDesignNarrative.trim(),
  );
}

RetrievalProcessingSnapshot _personalAssistantRetrievalProcessing(
  PersonalAssistantProcessSummary processSummary,
) {
  final acceptedCount = processSummary.acceptedCount > 0
      ? processSummary.acceptedCount
      : processSummary.acceptedReferences.length;
  return RetrievalProcessingSnapshot(
    searchedDocumentCount: processSummary.searchCount,
    processedDocumentCount: processSummary.processedCount,
    acceptedDocumentCount: acceptedCount,
    processingSummary: processSummary.processingSummary.trim(),
    selectedKeyPoints: processSummary.selectedKeyPoints,
    expansionReason: processSummary.expansionReason.trim(),
    acceptedReferences: processSummary.acceptedReferences,
  );
}

JourneyStageId _stageIdForProcessIndex(int index) {
  if (index <= 0) {
    return JourneyStageId.analyze;
  }
  if (index == 1) {
    return JourneyStageId.search;
  }
  return JourneyStageId.verify;
}

ProcessStepId _processStepIdForProcessIndex(int index) {
  if (index <= 0) {
    return ProcessStepId.understanding;
  }
  if (index == 1) {
    return ProcessStepId.retrievalDesign;
  }
  return ProcessStepId.retrievalProcessing;
}

String _personalAssistantTimestamp() => DateTime.now().toIso8601String();

String _projectAnswer(String current, AssistantRunStreamEvent event) {
  return switch (event.type) {
    AssistantRunStreamEventType.answerDelta => '$current${event.text}',
    AssistantRunStreamEventType.completed =>
      event.finalAnswer.isEmpty ? current : event.finalAnswer,
    _ => current,
  };
}

bool _isAnswerEvent(AssistantRunStreamEvent event) => event.isAnswerEvent;

String _failureMessageForEvent(AssistantRunStreamEvent event) {
  final failure = event.wire.runtimeFailure;
  if (failure != null && failure.code.trim().isNotEmpty) {
    return _runtimeFailureMessage(failure);
  }
  if (event.type == AssistantRunStreamEventType.failed) {
    // 无 runtimeFailure 的 failed 兜底提示；文案归口 UITextConstants。
    return AssistantText.assistantTurnFailedFallback;
  }
  return '';
}

String _runtimeFailureMessage(RuntimeFailureWire failure) {
  // 文案唯一真相源：assistant errors.yaml -> 生成的 AssistantErrorCode.defaultMessage，
  // 禁止在端侧硬编码错误码字符串或文案（军规 R06/§3.3）。未知码统一回退 unknown 文案。
  return AssistantErrorCode.fromCode(failure.code.trim()).defaultMessage;
}

final personalAssistantStreamControllerProvider =
    NotifierProvider<
      PersonalAssistantStreamController,
      PersonalAssistantStreamState
    >(PersonalAssistantStreamController.new);
