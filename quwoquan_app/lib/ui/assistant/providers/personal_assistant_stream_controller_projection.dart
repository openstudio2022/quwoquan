part of 'personal_assistant_stream_controller.dart';

List<String> extractAssistantEmergedTags(
  List<AssistantStreamEventWire> events,
) {
  final result = <String>[];
  final seen = <String>{};
  for (final event in events) {
    if (event.eventType != 'assistant.turn.completed') continue;
    final raw = event.payload['emergedTags'];
    if (raw is! List) continue;
    for (final item in raw) {
      final tag = item.toString().trim();
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

void _emitAssistantModelInteractionToConsole(Map<String, dynamic> payload) {
  if (!kDebugMode && !kProfileMode) {
    return;
  }
  const collect = bool.fromEnvironment(
    'ASSISTANT_MODEL_LOG_COLLECT',
    defaultValue: false,
  );
  debugPrint('[AssistantModel] INTERACTION');
  final collectLines = collect ? <String>[] : null;
  for (final entry in payload.entries) {
    final lines = ConsolePrettyLogFormatter.renderSection(
      prefix: '[AssistantModel] ',
      title: entry.key,
      value: entry.value,
    );
    for (final line in lines) {
      debugPrint(line);
      collectLines?.add(line);
    }
  }
  if (collect && collectLines != null) {
    personalAssistantModelInteractionLogLinesForTest.addAll(collectLines);
  }
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
  AssistantStreamEventWire event, {
  required int elapsedMs,
}) {
  final payload = _AssistantStreamPayload(event);
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
  final lines = <String>[...current.lines];

  if (payload.hasObject('understandingSnapshot')) {
    understandingSummary = _firstNonEmpty(<String>[
      payload.nestedString('understandingSnapshot', 'userFacingSummary'),
      understandingSummary,
    ]);
    retrievalDesignNarrative = _firstNonEmpty(<String>[
      payload.nestedString('understandingSnapshot', 'retrievalDesignNarrative'),
      retrievalDesignNarrative,
    ]);
  }

  if (payload.hasObject('retrievalProcessing')) {
    searchCount = _firstPositiveInt(<int>[
      payload.nestedInt('retrievalProcessing', 'searchedDocumentCount'),
      searchCount,
    ]);
    processedCount = _firstPositiveInt(<int>[
      payload.nestedInt('retrievalProcessing', 'processedDocumentCount'),
      processedCount,
    ]);
    acceptedCount = _firstPositiveInt(<int>[
      payload.nestedInt('retrievalProcessing', 'acceptedDocumentCount'),
      acceptedCount,
    ]);
    processingSummary = _firstNonEmpty(<String>[
      payload.nestedString('retrievalProcessing', 'processingSummary'),
      processingSummary,
    ]);
    expansionReason = _firstNonEmpty(<String>[
      payload.nestedString('retrievalProcessing', 'expansionReason'),
      expansionReason,
    ]);
    final keyPoints = payload.nestedStringList(
      'retrievalProcessing',
      'selectedKeyPoints',
    );
    if (keyPoints.isNotEmpty) {
      selectedKeyPoints = keyPoints;
    }
    final references = payload.nestedReferences(
      'retrievalProcessing',
      'acceptedReferences',
    );
    if (references.isNotEmpty) {
      acceptedReferences = references;
    }
  }

  if (event.eventType == 'search_query_generated' ||
      event.eventType == 'assistant.search_query.generated') {
    retrievalDesignNarrative = _firstNonEmpty(<String>[
      _retrievalDesignFromSearchPlans(event),
      retrievalDesignNarrative,
    ]);
  }

  if (_isAnswerEvent(event)) {
    finalAnswerSummary = AssistantText.assistantProcessFinalAnswerNarrative;
    finalAnswerReady = finalAnswerReady || event.eventType == 'final_answer';
  }

  switch (event.eventType) {
    case 'tool_use_requested':
    case 'tool_result_received':
    case 'assistant.tool.requested':
    case 'assistant.tool.completed':
    case 'search_query_generated':
    case 'assistant.search_query.generated':
    case 'search_query_accepted':
    case 'assistant.search_query.accepted':
      break;
  }
  final line = _processLineForEvent(event);
  if (line.isNotEmpty && !lines.contains(line)) {
    lines.add(line);
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
    selectedKeyPoints: List<String>.unmodifiable(selectedKeyPoints),
    acceptedReferences: List<RetrievalProcessingReference>.unmodifiable(
      acceptedReferences,
    ),
  );
}

String _processLineForEvent(AssistantStreamEventWire event) {
  final payload = _AssistantStreamPayload(event);
  final understandingSummary = payload.nestedString(
    'understandingSnapshot',
    'userFacingSummary',
  );
  if (understandingSummary.isNotEmpty) {
    return understandingSummary;
  }
  final retrievalDesign = payload.nestedString(
    'understandingSnapshot',
    'retrievalDesignNarrative',
  );
  if (retrievalDesign.isNotEmpty) {
    return retrievalDesign;
  }
  if (event.eventType == 'search_query_generated' ||
      event.eventType == 'assistant.search_query.generated') {
    return _retrievalDesignFromSearchPlans(event);
  }
  final processingSummary = payload.nestedString(
    'retrievalProcessing',
    'processingSummary',
  );
  if (processingSummary.isNotEmpty) {
    return processingSummary;
  }
  switch (event.eventType) {
    case 'partial_answer':
    case 'final_answer':
      return '';
    case 'tool_result_received':
    case 'assistant.tool.completed':
      return '';
  }
  return '';
}

class _AssistantStreamPayload {
  const _AssistantStreamPayload(this.event);

  final AssistantStreamEventWire event;

  Object? value(String key) => event.payload[key];

  bool hasObject(String key) => _objectValue(key) != null;

  String string(String key) => _stringValue(value(key));

  String nestedString(String objectKey, String fieldKey) {
    return _stringValue(_nestedValue(objectKey, fieldKey));
  }

  int nestedInt(String objectKey, String fieldKey) {
    return _intValue(_nestedValue(objectKey, fieldKey));
  }

  List<String> nestedStringList(String objectKey, String fieldKey) {
    return _stringListValue(_nestedValue(objectKey, fieldKey));
  }

  List<RetrievalProcessingReference> nestedReferences(
    String objectKey,
    String fieldKey,
  ) {
    final raw = _nestedValue(objectKey, fieldKey);
    if (raw is! List) {
      return const <RetrievalProcessingReference>[];
    }
    final references = <RetrievalProcessingReference>[];
    for (final item in raw) {
      if (item is! Map) {
        continue;
      }
      references.add(
        RetrievalProcessingReference(
          title: _stringValue(item['title']),
          url: _stringValue(item['url']),
          source: _stringValue(item['source']),
          snippet: _stringValue(item['snippet']),
          rank: _intValue(item['rank']),
        ),
      );
    }
    return references;
  }

  String get fixedNarrative {
    final understandingSummary = nestedString(
      'understandingSnapshot',
      'userFacingSummary',
    );
    if (understandingSummary.isNotEmpty) {
      return understandingSummary;
    }
    final processingSummary = nestedString(
      'retrievalProcessing',
      'processingSummary',
    );
    if (processingSummary.isNotEmpty) {
      return processingSummary;
    }
    return string('userMarkdown');
  }

  String get toolName {
    final toolUse = value('toolUse');
    if (toolUse is! Map) {
      return '';
    }
    return _firstNonEmpty(<String>[
      _stringValue(toolUse['toolName']),
      _stringValue(toolUse['tool_name']),
    ]);
  }

  String get toolSummary {
    final toolUse = value('toolUse');
    if (toolUse is! Map) {
      return '';
    }
    final result = toolUse['result'];
    if (result is! Map) {
      return '';
    }
    return _stringValue(result['summary']);
  }

  Object? _nestedValue(String objectKey, String fieldKey) {
    final object = _objectValue(objectKey);
    return object == null ? null : object[fieldKey];
  }

  Map? _objectValue(String key) {
    final raw = value(key);
    if (raw is Map) {
      return raw;
    }
    final runArtifacts = value('runArtifacts');
    if (runArtifacts is Map) {
      final nested = runArtifacts[key];
      if (nested is Map) {
        return nested;
      }
    }
    return null;
  }
}

String _stringValue(Object? value) {
  return value is String ? value.trim() : '';
}

int _intValue(Object? value) {
  if (value is num) {
    return value.toInt();
  }
  if (value is String) {
    return int.tryParse(value.trim()) ?? 0;
  }
  return 0;
}

List<String> _stringListValue(Object? raw) {
  if (raw is! List) {
    return const <String>[];
  }
  return raw
      .map((item) => item.toString().trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
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

int _firstPositiveInt(List<int> values) {
  for (final value in values) {
    if (value > 0) {
      return value;
    }
  }
  return 0;
}

String _retrievalDesignFromSearchPlans(AssistantStreamEventWire event) {
  final raw = event.payload['searchPlans'];
  if (raw is! List || raw.isEmpty) {
    return '';
  }
  final lines = <String>[];
  for (final item in raw) {
    if (item is! Map) {
      continue;
    }
    final query = _stringValue(item['query']);
    if (query.isEmpty) {
      continue;
    }
    final label = _firstNonEmpty(<String>[
      _stringValue(item['label']),
      _stringValue(item['dimension']),
    ]);
    lines.add(label.isEmpty ? query : '$label：$query');
  }
  if (lines.isEmpty) {
    return '';
  }
  return lines.join('\n');
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

String _projectAnswer(String current, AssistantStreamEventWire event) {
  if (event.eventType == 'answer_reset') {
    return '';
  }
  final text = _payloadText(event);
  if (text.isEmpty) {
    return current;
  }
  switch (event.eventType) {
    case 'partial_answer':
      return '$current$text';
    case 'final_answer':
      return text;
    default:
      return current;
  }
}

bool _isAnswerEvent(AssistantStreamEventWire event) {
  switch (event.eventType) {
    case 'partial_answer':
    case 'final_answer':
      return true;
    default:
      return false;
  }
}

String _payloadText(AssistantStreamEventWire event) {
  final directText = event.payload['text']?.toString().trim() ?? '';
  if (directText.isNotEmpty) {
    return directText;
  }
  final userMarkdown = event.payload['userMarkdown']?.toString().trim() ?? '';
  if (userMarkdown.isNotEmpty) {
    return userMarkdown;
  }
  final runArtifacts = event.payload['runArtifacts'];
  if (runArtifacts is Map) {
    for (final key in <String>[
      assistantDisplayMarkdownField,
      assistantDisplayPlainTextField,
    ]) {
      final text = runArtifacts[key]?.toString().trim() ?? '';
      if (text.isNotEmpty) {
        return text;
      }
    }
  }
  return '';
}

String _failureMessageForEvent(AssistantStreamEventWire event) {
  final failure = event.runtimeFailure;
  if (failure != null && failure.code.trim().isNotEmpty) {
    return _runtimeFailureMessage(failure);
  }
  if (event.eventType == 'turn_failed') {
    // 无 runtimeFailure 的 turn_failed 兜底提示；文案归口 UITextConstants。
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
