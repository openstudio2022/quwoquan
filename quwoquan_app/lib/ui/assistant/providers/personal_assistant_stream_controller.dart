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
import 'package:quwoquan_app/cloud/assistant/generated/assistant_errors.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/assistant/providers/assistant_history_loader.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'personal_assistant_stream_controller_projection.dart';

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
      final subAccountId = await _historySubAccountId();
      final snapshot = await ref
          .read(assistantHistoryLoaderProvider)
          .load(subAccountId: subAccountId);
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

  Future<String> _historySubAccountId() async {
    try {
      final activeContext = await ref.read(activePersonaContextProvider.future);
      final subAccountId = activeContext.subAccountId.trim();
      if (subAccountId.isNotEmpty) {
        return subAccountId;
      }
    } catch (_) {
      /* best-effort: 解析活跃分身上下文失败时回退到当前用户 id 作为归属键 */
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
    } catch (_) {
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
    state = state.copyWith(running: true, errorMessage: '');
    try {
      final turn = await ref
          .read(assistantRepositoryProvider)
          .getAssistantRun(runId: trimmed);
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
      }
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

/// 从流式事件中提取小艺对话浮现的兴趣标签（路径制 tagRef）。
///
/// 读取 `assistant.turn.completed` envelope 的 `payload['emergedTags']`（云侧
/// `collectEmergedTags` 下发的 `List<String>`），去重并过滤空值。
