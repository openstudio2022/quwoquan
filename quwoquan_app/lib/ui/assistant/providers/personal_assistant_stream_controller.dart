import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/debug/console_pretty_log_formatter.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_answer_anchor.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_assistant_timeline_payload.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/assistant/generated/contracts/runtime_failure.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/assistant/providers/assistant_history_loader.dart';

enum PersonalAssistantTranscriptRole { user, assistant, system }

/// 测试收集：`flutter test --dart-define=ASSISTANT_MODEL_LOG_COLLECT=true`
final personalAssistantModelInteractionLogLinesForTest = <String>[];

class PersonalAssistantTranscriptItem {
  const PersonalAssistantTranscriptItem({
    required this.id,
    required this.role,
    required this.text,
    this.turnId = '',
    this.eventType = '',
    this.proactive = false,
    this.streaming = false,
  });

  final String id;
  final PersonalAssistantTranscriptRole role;
  final String text;
  final String turnId;
  final String eventType;
  final bool proactive;
  final bool streaming;

  PersonalAssistantTranscriptItem copyWith({
    String? text,
    String? turnId,
    String? eventType,
    bool? proactive,
    bool? streaming,
  }) {
    return PersonalAssistantTranscriptItem(
      id: id,
      role: role,
      text: text ?? this.text,
      turnId: turnId ?? this.turnId,
      eventType: eventType ?? this.eventType,
      proactive: proactive ?? this.proactive,
      streaming: streaming ?? this.streaming,
    );
  }
}

class PersonalAssistantStreamState {
  const PersonalAssistantStreamState({
    this.conversationId = '',
    this.turnId = '',
    this.answer = '',
    this.transcript = const <AssistantTranscriptTimelineRow>[],
    this.processSummary = const PersonalAssistantProcessSummary(),
    this.events = const <AssistantStreamEventWire>[],
    this.answerGateOpen = false,
    this.running = false,
    this.errorMessage = '',
    this.appMessageUnreadCount = 0,
    this.managementSummaryLoading = false,
    this.feedbackMessage = '',
    this.historyInitialized = false,
    this.historyLoading = false,
  });

  final String conversationId;
  final String turnId;
  final String answer;
  final List<AssistantTranscriptTimelineRow> transcript;
  final PersonalAssistantProcessSummary processSummary;
  final List<AssistantStreamEventWire> events;
  final bool answerGateOpen;
  final bool running;
  final String errorMessage;
  final int appMessageUnreadCount;
  final bool managementSummaryLoading;
  final String feedbackMessage;
  final bool historyInitialized;
  final bool historyLoading;

  PersonalAssistantStreamState copyWith({
    String? conversationId,
    String? turnId,
    String? answer,
    List<AssistantTranscriptTimelineRow>? transcript,
    PersonalAssistantProcessSummary? processSummary,
    List<AssistantStreamEventWire>? events,
    bool? answerGateOpen,
    bool? running,
    String? errorMessage,
    int? appMessageUnreadCount,
    bool? managementSummaryLoading,
    String? feedbackMessage,
    bool? historyInitialized,
    bool? historyLoading,
  }) {
    return PersonalAssistantStreamState(
      conversationId: conversationId ?? this.conversationId,
      turnId: turnId ?? this.turnId,
      answer: answer ?? this.answer,
      transcript: transcript ?? this.transcript,
      processSummary: processSummary ?? this.processSummary,
      events: events ?? this.events,
      answerGateOpen: answerGateOpen ?? this.answerGateOpen,
      running: running ?? this.running,
      errorMessage: errorMessage ?? this.errorMessage,
      appMessageUnreadCount:
          appMessageUnreadCount ?? this.appMessageUnreadCount,
      managementSummaryLoading:
          managementSummaryLoading ?? this.managementSummaryLoading,
      feedbackMessage: feedbackMessage ?? this.feedbackMessage,
      historyInitialized: historyInitialized ?? this.historyInitialized,
      historyLoading: historyLoading ?? this.historyLoading,
    );
  }
}

class PersonalAssistantProcessSummary {
  const PersonalAssistantProcessSummary({
    this.processedCount = 0,
    this.searchCount = 0,
    this.acceptedCount = 0,
    this.elapsedMs = 0,
    this.lines = const <String>[],
    this.understandingSummary = '',
    this.retrievalDesignNarrative = '',
    this.processingSummary = '',
    this.expansionReason = '',
    this.finalAnswerSummary = '',
    this.finalAnswerReady = false,
    this.selectedKeyPoints = const <String>[],
    this.acceptedReferences = const <RetrievalProcessingReference>[],
  });

  final int processedCount;
  final int searchCount;
  final int acceptedCount;
  final int elapsedMs;
  final List<String> lines;
  final String understandingSummary;
  final String retrievalDesignNarrative;
  final String processingSummary;
  final String expansionReason;
  final String finalAnswerSummary;
  final bool finalAnswerReady;
  final List<String> selectedKeyPoints;
  final List<RetrievalProcessingReference> acceptedReferences;

  PersonalAssistantProcessSummary copyWith({
    int? processedCount,
    int? searchCount,
    int? acceptedCount,
    int? elapsedMs,
    List<String>? lines,
    String? understandingSummary,
    String? retrievalDesignNarrative,
    String? processingSummary,
    String? expansionReason,
    String? finalAnswerSummary,
    bool? finalAnswerReady,
    List<String>? selectedKeyPoints,
    List<RetrievalProcessingReference>? acceptedReferences,
  }) {
    return PersonalAssistantProcessSummary(
      processedCount: processedCount ?? this.processedCount,
      searchCount: searchCount ?? this.searchCount,
      acceptedCount: acceptedCount ?? this.acceptedCount,
      elapsedMs: elapsedMs ?? this.elapsedMs,
      lines: lines ?? this.lines,
      understandingSummary: understandingSummary ?? this.understandingSummary,
      retrievalDesignNarrative:
          retrievalDesignNarrative ?? this.retrievalDesignNarrative,
      processingSummary: processingSummary ?? this.processingSummary,
      expansionReason: expansionReason ?? this.expansionReason,
      finalAnswerSummary: finalAnswerSummary ?? this.finalAnswerSummary,
      finalAnswerReady: finalAnswerReady ?? this.finalAnswerReady,
      selectedKeyPoints: selectedKeyPoints ?? this.selectedKeyPoints,
      acceptedReferences: acceptedReferences ?? this.acceptedReferences,
    );
  }

  bool get hasContent =>
      processedCount > 0 ||
      searchCount > 0 ||
      acceptedCount > 0 ||
      lines.isNotEmpty ||
      understandingSummary.trim().isNotEmpty ||
      retrievalDesignNarrative.trim().isNotEmpty ||
      processingSummary.trim().isNotEmpty ||
      finalAnswerSummary.trim().isNotEmpty ||
      acceptedReferences.isNotEmpty;
}

class PersonalAssistantStreamController
    extends Notifier<PersonalAssistantStreamState> {
  Future<void>? _historyInitializationFuture;

  @override
  PersonalAssistantStreamState build() {
    return const PersonalAssistantStreamState();
  }

  Future<void> ensureHistoryInitialized() {
    if (state.historyInitialized) {
      return Future<void>.value();
    }
    final inFlight = _historyInitializationFuture;
    if (inFlight != null) {
      return inFlight;
    }
    final future = _initializeHistory();
    _historyInitializationFuture = future.whenComplete(() {
      _historyInitializationFuture = null;
    });
    return _historyInitializationFuture!;
  }

  Future<void> _initializeHistory() async {
    if (state.historyInitialized) {
      return;
    }
    state = state.copyWith(historyLoading: true);
    try {
      final profileSubjectId = await _historyProfileSubjectId();
      final snapshot = await ref
          .read(assistantHistoryLoaderProvider)
          .load(profileSubjectId: profileSubjectId);
      if (snapshot == null || snapshot.transcript.isEmpty) {
        state = state.copyWith(historyInitialized: true, historyLoading: false);
        return;
      }
      final currentIds = state.transcript.map((row) => row.id).toSet();
      final importedRows = snapshot.transcript
          .where((row) => !currentIds.contains(row.id))
          .toList(growable: false);
      state = state.copyWith(
        transcript: <AssistantTranscriptTimelineRow>[
          ...importedRows,
          ...state.transcript,
        ],
        historyInitialized: true,
        historyLoading: false,
      );
    } catch (error, stackTrace) {
      debugPrint(
        'PersonalAssistantStreamController history initialization failed: $error\n$stackTrace',
      );
      state = state.copyWith(historyInitialized: true, historyLoading: false);
    }
  }

  Future<String> _historyProfileSubjectId() async {
    try {
      // 会话加载不应被活动账号上下文无限阻塞；超时后回退到当前用户。
      final activeContext = await ref
          .read(activePersonaContextProvider.future)
          .timeout(const Duration(seconds: 3));
      final profileSubjectId = activeContext.profileSubjectId.trim();
      if (profileSubjectId.isNotEmpty) {
        return profileSubjectId;
      }
    } catch (_) {}
    return ref.read(currentUserIdProvider).trim();
  }

  Future<void> refreshManagementSummary() async {
    if (state.managementSummaryLoading) {
      return;
    }
    state = state.copyWith(managementSummaryLoading: true);
    try {
      final unread = await ref
          .read(appMessageRepositoryProvider)
          .getUnreadCount();
      state = state.copyWith(
        appMessageUnreadCount: unread,
        managementSummaryLoading: false,
      );
    } catch (_) {
      state = state.copyWith(managementSummaryLoading: false);
    }
  }

  Future<void> openTurnFromAppMessage(String turnId) async {
    final trimmed = turnId.trim();
    if (trimmed.isEmpty) {
      return;
    }
    await ensureHistoryInitialized();
    state = state.copyWith(running: true, errorMessage: '');
    try {
      final turn = await ref
          .read(assistantRepositoryProvider)
          .getAssistantTurn(turnId: trimmed);
      state = state.copyWith(
        conversationId: turn.conversationId,
        turnId: turn.turnId,
        answer: _openedTurnAnswer(turn),
        transcript: _appendOpenedTurnTranscript(state.transcript, turn),
        running: false,
        errorMessage: '',
      );
    } catch (_) {
      state = state.copyWith(
        running: false,
        errorMessage: '暂时无法打开这条主动提醒，请稍后再试。',
      );
    }
  }

  Future<void> send(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || state.running) {
      return;
    }
    await ensureHistoryInitialized();
    _debugPersonalAssistant(
      'send text="${_debugSnippet(trimmed)}" existingConversation=${state.conversationId}',
    );
    if (const bool.fromEnvironment(
      'ASSISTANT_MODEL_LOG_COLLECT',
      defaultValue: false,
    )) {
      personalAssistantModelInteractionLogLinesForTest.clear();
    }
    state = state.copyWith(
      running: true,
      errorMessage: '',
      answer: '',
      answerGateOpen: false,
      processSummary: const PersonalAssistantProcessSummary(),
      transcript: <AssistantTranscriptTimelineRow>[
        ...state.transcript,
        _personalAssistantUserRow(
          id: 'user_${DateTime.now().microsecondsSinceEpoch}',
          text: trimmed,
        ),
      ],
      events: const <AssistantStreamEventWire>[],
    );
    final repository = ref.read(assistantRepositoryProvider);
    try {
      var conversationId = state.conversationId;
      if (conversationId.isEmpty) {
        final conversation = await repository.createAssistantConversation(
          summary: '找私助云端对话',
        );
        conversationId = conversation.conversationId;
        _debugPersonalAssistant('conversation created id=$conversationId');
      }
      final turn = await repository.createAssistantTurn(
        conversationId: conversationId,
        text: trimmed,
        domainId: 'assistant',
      );
      _debugPersonalAssistant(
        'turn created conversationId=$conversationId turnId=${turn.turnId} traceId=${turn.traceId}',
      );
      var answer = '';
      var lastSeq = 0;
      var failed = false;
      final startedAt = DateTime.now();
      var processSummary = const PersonalAssistantProcessSummary();
      final events = <AssistantStreamEventWire>[];
      final assistantItemId = 'assistant_${turn.turnId}';
      var transcript = <AssistantTranscriptTimelineRow>[
        ...state.transcript,
        _personalAssistantAssistantRow(
          id: assistantItemId,
          text: '',
          turnId: turn.turnId,
          traceId: turn.traceId,
          sourceQuery: trimmed,
          streaming: true,
        ),
      ];
      state = state.copyWith(
        conversationId: conversationId,
        turnId: turn.turnId,
        transcript: List<AssistantTranscriptTimelineRow>.unmodifiable(
          transcript,
        ),
      );
      await for (final event in repository.streamAssistantTurn(
        turnId: turn.turnId,
      )) {
        if (event.seq <= lastSeq) {
          continue;
        }
        lastSeq = event.seq;
        events.add(event);
        if (event.eventType == 'assistant.model.interaction') {
          _emitAssistantModelInteractionToConsole(event.payload);
        }
        final payload = _AssistantStreamPayload(event);
        _debugPersonalAssistant(
          'stream event type=${event.eventType} seq=${event.seq} turnId=${turn.turnId} '
          'skill=${payload.string('skillId')} tool=${payload.toolName} '
          'fixedNarrative="${_debugSnippet(payload.fixedNarrative)}"',
        );
        processSummary = _projectProcessSummary(
          processSummary,
          event,
          elapsedMs: DateTime.now().difference(startedAt).inMilliseconds,
        );
        final failureMessage = _failureMessageForEvent(event);
        if (failureMessage.isNotEmpty) {
          failed = true;
          transcript = _upsertAssistantTranscript(
            transcript,
            assistantItemId,
            text: failureMessage,
            turnId: turn.turnId,
            traceId: turn.traceId,
            sourceQuery: trimmed,
            eventType: event.eventType,
            streaming: false,
            processSummary: processSummary,
          );
          state = state.copyWith(
            conversationId: conversationId,
            turnId: turn.turnId,
            answer: answer,
            transcript: transcript,
            processSummary: processSummary,
            events: List<AssistantStreamEventWire>.unmodifiable(events),
            errorMessage: failureMessage,
          );
          continue;
        }
        answer = _projectAnswer(answer, event);
        final answerGateOpen =
            state.answerGateOpen || _isAnswerEvent(event) || answer.isNotEmpty;
        if (_isAnswerEvent(event)) {
          _debugPersonalAssistant(
            'answer event type=${event.eventType} answerLength=${answer.length} delta="${_debugSnippet(_payloadText(event))}"',
          );
        }
        if (answer.isNotEmpty || processSummary.hasContent) {
          transcript = _upsertAssistantTranscript(
            transcript,
            assistantItemId,
            text: answer,
            turnId: turn.turnId,
            traceId: turn.traceId,
            sourceQuery: trimmed,
            eventType: event.eventType,
            streaming:
                event.eventType != 'final_answer' &&
                event.eventType != 'assistant.answer.final',
            processSummary: processSummary,
          );
        }
        state = state.copyWith(
          conversationId: conversationId,
          turnId: turn.turnId,
          answer: answer,
          transcript: List<AssistantTranscriptTimelineRow>.unmodifiable(
            transcript,
          ),
          processSummary: processSummary,
          events: List<AssistantStreamEventWire>.unmodifiable(events),
          answerGateOpen: answerGateOpen,
        );
      }
      state = state.copyWith(
        running: false,
        answerGateOpen: answer.isNotEmpty || state.answerGateOpen,
        processSummary: processSummary.copyWith(
          elapsedMs: DateTime.now().difference(startedAt).inMilliseconds,
        ),
        transcript: failed
            ? transcript
            : _upsertAssistantTranscript(
                transcript,
                assistantItemId,
                text: answer,
                turnId: turn.turnId,
                traceId: turn.traceId,
                sourceQuery: trimmed,
                streaming: false,
                processSummary: processSummary.copyWith(
                  elapsedMs: DateTime.now()
                      .difference(startedAt)
                      .inMilliseconds,
                ),
              ),
      );
      _debugPersonalAssistant(
        'turn completed turnId=${turn.turnId} answerLength=${answer.length} '
        'events=${events.length} processLines=${processSummary.lines.length}',
      );
      unawaited(refreshManagementSummary());
    } catch (error, stackTrace) {
      debugPrint('personal assistant stream failed: $error\n$stackTrace');
      state = state.copyWith(running: false, errorMessage: '找私助暂时不可用，请稍后再试。');
    }
  }

  void submitFeedback(String feedbackType) {
    final normalized = feedbackType.trim();
    final label = switch (normalized) {
      'useful' => '有用',
      'irrelevant' => '不相关',
      'too_frequent' => '太频繁',
      _ => '已记录',
    };
    state = state.copyWith(feedbackMessage: '已记录反馈：$label');
  }
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
    finalAnswerSummary = UITextConstants.assistantProcessFinalAnswerNarrative;
    finalAnswerReady =
        finalAnswerReady ||
        event.eventType == 'assistant.answer.final' ||
        event.eventType == 'final_answer';
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
    case 'assistant.answer.delta':
    case 'partial_answer':
    case 'assistant.answer.final':
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
  final raw =
      event.payload['searchPlans'] ?? event.payload['acceptedSearchPlans'];
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
    return '已打开主动提醒：$text';
  }
  if (turn.skillId.trim().isNotEmpty) {
    return '已打开主动提醒：${turn.skillId}';
  }
  return '已打开主动提醒。';
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
      text: '来自云侧主动触发',
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
    senderName: '我',
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
  final text = _payloadText(event);
  if (text.isEmpty) {
    return current;
  }
  switch (event.eventType) {
    case 'assistant.answer.delta':
    case 'partial_answer':
      return '$current$text';
    case 'assistant.answer.final':
    case 'final_answer':
      return text;
    default:
      return current;
  }
}

bool _isAnswerEvent(AssistantStreamEventWire event) {
  switch (event.eventType) {
    case 'assistant.answer.delta':
    case 'partial_answer':
    case 'assistant.answer.final':
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
    return '找私助执行遇到问题，请稍后重试。';
  }
  return '';
}

String _runtimeFailureMessage(RuntimeFailureWire failure) {
  final code = failure.code.trim();
  if (code.isEmpty) {
    return '找私助暂时不可用，请稍后再试。';
  }
  if (code == 'ASSISTANT.MIDDLEWARE.tool_unavailable') {
    return '找私助暂时无法完成检索，我会保留当前问题，请稍后重试。';
  }
  return '找私助执行遇到问题，请稍后重试。';
}

final personalAssistantStreamControllerProvider =
    NotifierProvider<
      PersonalAssistantStreamController,
      PersonalAssistantStreamState
    >(PersonalAssistantStreamController.new);
