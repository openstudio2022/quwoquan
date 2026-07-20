import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/debug/console_pretty_log_formatter.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_answer_anchor.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_assistant_timeline_payload.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/assistant/generated/contracts/runtime_failure.g.dart';
import 'package:quwoquan_app/cloud/assistant/generated/assistant_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/assistant/providers/assistant_history_loader.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/regenerate_options_popup.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

part 'personal_assistant_stream_controller_projection.dart';

enum PersonalAssistantTranscriptRole { user, assistant, system }

enum _PersonalAssistantRetryKind { send, openTurn }

const Object _unsetAssistantFailure = Object();

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
    this.errorFailure,
    this.retryAvailable = false,
    this.appMessageUnreadCount = 0,
    this.managementSummaryLoading = false,
    this.feedbackMessage = '',
    this.feedbackType = '',
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
  final RuntimeFailureBase? errorFailure;
  final bool retryAvailable;
  final int appMessageUnreadCount;
  final bool managementSummaryLoading;
  final String feedbackMessage;
  final String feedbackType;
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
    Object? errorFailure = _unsetAssistantFailure,
    bool? retryAvailable,
    int? appMessageUnreadCount,
    bool? managementSummaryLoading,
    String? feedbackMessage,
    String? feedbackType,
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
      errorFailure: identical(errorFailure, _unsetAssistantFailure)
          ? this.errorFailure
          : errorFailure as RuntimeFailureBase?,
      retryAvailable: retryAvailable ?? this.retryAvailable,
      appMessageUnreadCount:
          appMessageUnreadCount ?? this.appMessageUnreadCount,
      managementSummaryLoading:
          managementSummaryLoading ?? this.managementSummaryLoading,
      feedbackMessage: feedbackMessage ?? this.feedbackMessage,
      feedbackType: feedbackType ?? this.feedbackType,
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
  _PersonalAssistantRetryKind? _retryKind;
  String _retryValue = '';

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
      final subAccountId = await _historySubAccountId();
      final snapshot = await ref
          .read(assistantHistoryLoaderProvider)
          .load(subAccountId: subAccountId);
      if (snapshot == null) {
        state = state.copyWith(historyInitialized: true, historyLoading: false);
        return;
      }
      final currentIds = state.transcript.map((row) => row.id).toSet();
      final importedRows = snapshot.transcript
          .where((row) => !currentIds.contains(row.id))
          .toList(growable: false);
      state = state.copyWith(
        // 云端最近会话绑定为当前会话，后续 send 续聊同一 conversation。
        conversationId: state.conversationId.isEmpty
            ? snapshot.conversationId
            : state.conversationId,
        transcript: <AssistantTranscriptTimelineRow>[
          ...importedRows,
          ...state.transcript,
        ],
        historyInitialized: true,
        historyLoading: false,
      );
    } catch (error, stackTrace) {
      // 云端历史恢复失败可容忍：记录后按"无历史"继续，不阻断新会话。
      developer.log(
        'assistant history initialization failed',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
      state = state.copyWith(historyInitialized: true, historyLoading: false);
    }
  }

  /// 切换到指定云端会话：清空当前时间线并恢复该会话的终态轮次。
  Future<void> switchConversation(String conversationId) async {
    final target = conversationId.trim();
    if (target.isEmpty || state.running) {
      return;
    }
    if (target == state.conversationId && state.historyInitialized) {
      return;
    }
    state = state.copyWith(
      conversationId: target,
      turnId: '',
      answer: '',
      transcript: const <AssistantTranscriptTimelineRow>[],
      processSummary: const PersonalAssistantProcessSummary(),
      events: const <AssistantStreamEventWire>[],
      answerGateOpen: false,
      errorMessage: '',
      errorFailure: null,
      retryAvailable: false,
      historyInitialized: true,
      historyLoading: true,
    );
    try {
      final subAccountId = await _historySubAccountId();
      final snapshot = await ref
          .read(assistantHistoryLoaderProvider)
          .load(subAccountId: subAccountId, conversationId: target);
      state = state.copyWith(
        transcript:
            snapshot?.transcript ?? const <AssistantTranscriptTimelineRow>[],
        historyLoading: false,
      );
    } catch (error, stackTrace) {
      developer.log(
        'assistant conversation switch failed conversationId=$target',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
      state = state.copyWith(
        historyLoading: false,
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
      );
    }
  }

  /// 开启新会话：清空状态；下一次 send 自动创建云端 conversation。
  void startNewConversation() {
    if (state.running) {
      return;
    }
    state = state.copyWith(
      conversationId: '',
      turnId: '',
      answer: '',
      transcript: const <AssistantTranscriptTimelineRow>[],
      processSummary: const PersonalAssistantProcessSummary(),
      events: const <AssistantStreamEventWire>[],
      answerGateOpen: false,
      errorMessage: '',
      errorFailure: null,
      retryAvailable: false,
      historyInitialized: true,
      historyLoading: false,
    );
    _clearRetry();
  }

  /// 停止当前生成：发送 CancelAssistantRun 命令；SSE 会以
  /// turn_cancelled 终态事件结束流，send() 收尾时落停止态。
  Future<void> stopGeneration() async {
    final runId = state.turnId.trim();
    if (runId.isEmpty || !state.running) {
      return;
    }
    try {
      await ref
          .read(assistantConversationRunFacetProvider)
          .cancelAssistantRun(runId: runId);
    } catch (error, stackTrace) {
      // 取消命令失败不阻塞（流可能已自然完成）；记录后由流终态兜底。
      developer.log(
        'assistant cancel run failed runId=$runId',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  /// 重新生成上一轮回答；[option] 携带风格约束（简洁/详细/口语化/深思）。
  Future<void> regenerateLastAnswer({RegenerateOption? option}) async {
    if (state.running) {
      return;
    }
    final lastQuestion = _lastUserQuestion();
    if (lastQuestion.isEmpty) {
      return;
    }
    final preference = switch (option) {
      RegenerateOption.concise => (
        kind: AssistantPreferenceKind.replyLength,
        value: 'concise',
      ),
      RegenerateOption.detailed => (
        kind: AssistantPreferenceKind.replyLength,
        value: 'detailed',
      ),
      RegenerateOption.casual => (
        kind: AssistantPreferenceKind.tone,
        value: 'casual',
      ),
      RegenerateOption.deepThink => (
        kind: AssistantPreferenceKind.responseStyle,
        value: 'deep_think',
      ),
      RegenerateOption.regenerate || null => null,
    };
    if (preference != null) {
      final conversationId = state.conversationId.trim();
      if (conversationId.isEmpty) {
        return;
      }
      try {
        await ref
            .read(assistantPreferenceFactFacetProvider)
            .setAssistantPreference(
              scope: AssistantPreferenceScope.session,
              conversationId: conversationId,
              kind: preference.kind,
              value: preference.value,
              sourceType: AssistantPreferenceSourceType.explicitRewrite,
            );
      } catch (error) {
        state = state.copyWith(
          errorMessage: runtimeErrorDisplayMessage(error),
          errorFailure: runtimeFailureFromError(error),
          retryAvailable: false,
        );
        return;
      }
    }
    unawaited(_reportRegenerateInteraction(option));
    await send(lastQuestion);
  }

  String _lastUserQuestion() {
    for (final row in state.transcript.reversed) {
      if (row is UserTranscriptTimelineRow) {
        final content = row.content.trim();
        if (content.isNotEmpty) {
          return content;
        }
      }
    }
    return '';
  }

  Future<void> _reportRegenerateInteraction(RegenerateOption? option) async {
    final runId = state.turnId.trim();
    if (runId.isEmpty) {
      return;
    }
    final event = InteractionEvent(
      eventId: 'regen:$runId:${option?.name ?? 'regenerate'}',
      runId: runId,
      userId: await _historySubAccountId(),
      sessionId: AppTraceContextStore.instance.sessionId,
      pageType: 'assistant_dialog',
      domainId: 'assistant',
      feedbackType: 'regenerated',
      copiedAnswer: false,
      sharedAnswer: false,
      regeneratedAnswer: true,
      styleAdjusted: option != null && option != RegenerateOption.regenerate,
      modelSwitched: false,
      referenceOpened: false,
      interrupted: false,
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
    _pendingFeedbackEvents
      ..removeWhere((pending) => pending.eventId == event.eventId)
      ..add(event);
    await _flushPendingFeedbackEvents();
  }

  Future<String> _historySubAccountId() async {
    // 历史恢复不能等待远端 Persona 查询；仅消费已就绪的上下文，否则立即
    // 回退当前用户归属键，避免会话首发被非关键画像请求阻塞。
    final activeContext = ref.read(activePersonaContextProvider).asData?.value;
    final subAccountId = activeContext?.subAccountId.trim() ?? '';
    if (subAccountId.isNotEmpty) {
      return subAccountId;
    }
    return ref.read(currentUserIdProvider).trim();
  }

  Future<void> refreshManagementSummary() async {
    if (!ref.mounted) {
      return;
    }
    if (state.managementSummaryLoading) {
      return;
    }
    state = state.copyWith(managementSummaryLoading: true);
    try {
      final unread = await ref
          .read(appMessageQueryProvider)
          .getUnreadCount(const GetAppMessageUnreadCountQuery());
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        appMessageUnreadCount: unread.unreadCount,
        managementSummaryLoading: false,
      );
    } catch (error, stackTrace) {
      // 结构化记录 NOTIFICATION.* 错误码后降级为徽标缺省，不阻断助手会话。
      final domainCode = error is CloudException
          ? (error.domainErrorCode?.code ?? error.code ?? '')
          : '';
      developer.log(
        'assistant unread-count degraded (code=$domainCode)',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
      if (ref.mounted) {
        state = state.copyWith(managementSummaryLoading: false);
      }
    }
  }

  Future<void> openTurnFromAppMessage(String turnId) async {
    final trimmed = turnId.trim();
    if (trimmed.isEmpty) {
      return;
    }
    await ensureHistoryInitialized();
    state = state.copyWith(
      running: true,
      errorMessage: '',
      errorFailure: null,
      retryAvailable: false,
    );
    try {
      final turn = await ref
          .read(assistantConversationRunFacetProvider)
          .getAssistantRun(runId: trimmed);
      state = state.copyWith(
        conversationId: turn.conversationId,
        turnId: turn.turnId,
        answer: _openedTurnAnswer(turn),
        transcript: _appendOpenedTurnTranscript(state.transcript, turn),
        running: false,
        errorMessage: '',
        errorFailure: null,
        retryAvailable: false,
      );
      _clearRetry();
    } catch (error) {
      developer.log(
        'open proactive turn failed turnId=$trimmed',
        name: 'personal_assistant',
        error: error,
      );
      state = state.copyWith(
        running: false,
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: true,
      );
      _rememberRetry(_PersonalAssistantRetryKind.openTurn, trimmed);
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
      errorFailure: null,
      retryAvailable: false,
      answer: '',
      answerGateOpen: false,
      processSummary: const PersonalAssistantProcessSummary(),
      feedbackMessage: '',
      feedbackType: '',
      transcript: <AssistantTranscriptTimelineRow>[
        ...state.transcript,
        _personalAssistantUserRow(
          id: 'user_${DateTime.now().microsecondsSinceEpoch}',
          text: trimmed,
        ),
      ],
      events: const <AssistantStreamEventWire>[],
    );
    final repository = ref.read(assistantConversationRunFacetProvider);
    try {
      var conversationId = state.conversationId;
      if (conversationId.isEmpty) {
        final conversation = await repository.createAssistantConversation(
          summary: AssistantText.assistantCloudConversationSummary,
        );
        conversationId = conversation.conversationId;
        _debugPersonalAssistant('conversation created id=$conversationId');
      }
      final turn = await repository.startAssistantRun(
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
      var cancelled = false;
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
      await for (final event in repository.watchAssistantRunEvents(
        runId: turn.turnId,
      )) {
        if (event.seq <= lastSeq) {
          continue;
        }
        lastSeq = event.seq;
        events.add(event);
        if (event.eventType == 'assistant.model.interaction') {
          _emitAssistantModelInteractionToConsole(event.payload);
        }
        if (event.eventType == 'turn_cancelled') {
          cancelled = true;
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
        if (answer.isNotEmpty ||
            processSummary.hasContent ||
            event.eventType == 'answer_reset') {
          transcript = _upsertAssistantTranscript(
            transcript,
            assistantItemId,
            text: answer,
            turnId: turn.turnId,
            traceId: turn.traceId,
            sourceQuery: trimmed,
            eventType: event.eventType,
            streaming: event.eventType != 'final_answer',
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
      // 取消后无任何 partial answer 时以停止占位收尾，避免空气泡。
      final finalAnswerText = cancelled && answer.trim().isEmpty
          ? AssistantText.assistantGenerationStopped
          : answer;
      state = state.copyWith(
        running: false,
        answerGateOpen: finalAnswerText.isNotEmpty || state.answerGateOpen,
        processSummary: processSummary.copyWith(
          elapsedMs: DateTime.now().difference(startedAt).inMilliseconds,
        ),
        transcript: failed
            ? transcript
            : _upsertAssistantTranscript(
                transcript,
                assistantItemId,
                text: finalAnswerText,
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
      if (!failed) {
        // 对话浮现兴趣回流（P3 飞轮小循环）：从 turn.completed envelope 取
        // 云侧 collectEmergedTags 下发的路径制 tagRefs，合成 assistant_interest
        // 行为上报，进入推荐特征（rm_recommend_feature.tagInteraction）。不绑定 post。
        final emergedTags = extractAssistantEmergedTags(events);
        if (emergedTags.isNotEmpty) {
          ref
              .read(contentBehaviorTrackerProvider)
              .trackAssistantInterest(emergedTags);
        }
      }
      if (ref.mounted) {
        unawaited(refreshManagementSummary());
        // turn 完成时补发上一轮反馈上报失败留下的待重试事件。
        unawaited(_flushPendingFeedbackEvents());
      }
      _clearRetry();
    } catch (error, stackTrace) {
      developer.log(
        'personal assistant stream failed',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
      state = state.copyWith(
        running: false,
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: true,
      );
      _rememberRetry(_PersonalAssistantRetryKind.send, trimmed);
    }
  }

  Future<void> retryLastFailedAction() async {
    final kind = _retryKind;
    final value = _retryValue.trim();
    if (kind == null || value.isEmpty || state.running) {
      return;
    }
    switch (kind) {
      case _PersonalAssistantRetryKind.send:
        final transcript = List<AssistantTranscriptTimelineRow>.of(
          state.transcript,
        );
        if (transcript.isNotEmpty &&
            transcript.last is UserTranscriptTimelineRow &&
            (transcript.last as UserTranscriptTimelineRow).content.trim() ==
                value) {
          transcript.removeLast();
          state = state.copyWith(transcript: transcript);
        }
        return send(value);
      case _PersonalAssistantRetryKind.openTurn:
        return openTurnFromAppMessage(value);
    }
  }

  void dismissError() {
    state = state.copyWith(
      errorMessage: '',
      errorFailure: null,
      retryAvailable: false,
    );
    _clearRetry();
  }

  void _rememberRetry(_PersonalAssistantRetryKind kind, String value) {
    _retryKind = kind;
    _retryValue = value;
  }

  void _clearRetry() {
    _retryKind = null;
    _retryValue = '';
  }

  /// 反馈事件内存待重试队列：ack 全拒或请求失败时保留，下次
  /// [submitFeedback] 或 turn 完成时补发；不建持久队列。
  final List<InteractionEvent> _pendingFeedbackEvents = <InteractionEvent>[];

  @visibleForTesting
  int get pendingFeedbackEventCount => _pendingFeedbackEvents.length;

  void submitFeedback(String feedbackType) {
    final normalized = feedbackType.trim();
    final label = switch (normalized) {
      'useful' => AssistantText.assistantFeedbackUsefulLabel,
      'irrelevant' => AssistantText.assistantFeedbackIrrelevantLabel,
      'too_frequent' => AssistantText.assistantFeedbackTooFrequentLabel,
      _ => AssistantText.assistantFeedbackRecordedLabel,
    };
    // 本地反馈展示先行；学习回路上报为 best-effort，失败不阻塞 UI。
    state = state.copyWith(
      feedbackMessage: AssistantText.assistantFeedbackRecorded(label),
      feedbackType: normalized,
    );
    unawaited(_reportFeedbackInteraction(normalized));
  }

  Future<void> _reportFeedbackInteraction(String feedbackType) async {
    final runId = state.turnId.trim();
    if (feedbackType.isEmpty || runId.isEmpty) {
      return;
    }
    final event = InteractionEvent(
      // 稳定派生 id：同一 run 上同一反馈动作重试不产生新事件。
      eventId: 'fb:$runId:$feedbackType',
      runId: runId,
      userId: await _historySubAccountId(),
      sessionId: AppTraceContextStore.instance.sessionId,
      pageType: 'assistant_dialog',
      domainId: 'assistant',
      feedbackType: feedbackType,
      copiedAnswer: feedbackType == 'copied',
      sharedAnswer: false,
      regeneratedAnswer: false,
      styleAdjusted: false,
      modelSwitched: false,
      referenceOpened: false,
      interrupted: false,
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
    _pendingFeedbackEvents
      ..removeWhere((pending) => pending.eventId == event.eventId)
      ..add(event);
    await _flushPendingFeedbackEvents();
  }

  Future<void> _flushPendingFeedbackEvents() async {
    if (_pendingFeedbackEvents.isEmpty) {
      return;
    }
    final batch = List<InteractionEvent>.unmodifiable(_pendingFeedbackEvents);
    try {
      final ack = await ref
          .read(assistantLearningAppendFacetProvider)
          .reportInteractionEvents(events: batch);
      final acceptedCount =
          ack.acceptedCount ?? (ack.accepted ? batch.length : 0);
      if (acceptedCount > 0) {
        _pendingFeedbackEvents.clear();
      }
    } catch (error) {
      developer.log(
        'feedback interaction report failed; kept for retry '
        '(pending=${_pendingFeedbackEvents.length})',
        name: 'AssistantLearningAppend',
        error: error,
      );
    }
  }
}

/// 从流式事件中提取小艺对话浮现的兴趣标签（路径制 tagRef）。
///
/// 读取 `assistant.turn.completed` envelope 的 `payload['emergedTags']`（云侧
/// `collectEmergedTags` 下发的 `List<String>`），去重并过滤空值。
