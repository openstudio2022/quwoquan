import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_run_stream_event.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_answer_anchor.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_assistant_timeline_payload.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/assistant/generated/contracts/runtime_failure.g.dart';
import 'package:quwoquan_app/cloud/assistant/generated/assistant_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/assistant/providers/assistant_history_loader.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/regenerate_options_popup.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:uuid/uuid.dart';

part 'personal_assistant_stream_controller_projection.dart';
part 'personal_assistant_stream_controller_models.dart';

class PersonalAssistantStreamController
    extends Notifier<PersonalAssistantStreamState> {
  Future<void>? _historyInitializationFuture;
  _PersonalAssistantRetryKind? _retryKind;
  String _retryValue = '';
  String _retryRunClientRequestId = '';
  String _retryConversationClientRequestId = '';
  List<AssistantIntersectionEvidenceRef> _pendingIntersectionEvidenceRefs =
      const <AssistantIntersectionEvidenceRef>[];
  AssistantOpenContext? _openContext;
  Future<void>? _pageContextReportFuture;
  String _pendingSuggestedActionId = '';

  @override
  PersonalAssistantStreamState build() {
    return const PersonalAssistantStreamState();
  }

  /// 页面入口设置的交集引用只消费给下一次 StartAssistantRun，避免后续手工对话继续
  /// 携带已经过期的页面证据。所有带页面上下文的完整会话入口也必须在首个
  /// StartAssistantRun 前完成同一份 PageContext 上报，不能绕过半弹层专属路径。
  void setOpenContext(AssistantOpenContext? context) {
    _openContext = context;
    _pageContextReportFuture = null;
    _pendingSuggestedActionId =
        context?.hints['suggestedActionId']?.toString().trim() ?? '';
    _pendingIntersectionEvidenceRefs =
        List<AssistantIntersectionEvidenceRef>.unmodifiable(
          context?.intersectionEvidenceRefs ??
              const <AssistantIntersectionEvidenceRef>[],
        );
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
        state = state.copyWith(
          historyInitialized: true,
          historyLoading: false,
          errorMessage: '',
          errorFailure: null,
          retryAvailable: false,
        );
        _clearRetry();
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
        errorMessage: '',
        errorFailure: null,
        retryAvailable: false,
      );
      _clearRetry();
    } catch (error, stackTrace) {
      developer.log(
        'assistant history initialization failed',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
      state = state.copyWith(
        historyInitialized: false,
        historyLoading: false,
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: true,
      );
      _rememberRetry(_PersonalAssistantRetryKind.history, 'history');
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
        historyInitialized: true,
        historyLoading: false,
        errorMessage: '',
        errorFailure: null,
        retryAvailable: false,
      );
      _clearRetry();
    } catch (error, stackTrace) {
      developer.log(
        'assistant conversation switch failed conversationId=$target',
        name: 'personal_assistant',
        error: error,
        stackTrace: stackTrace,
      );
      state = state.copyWith(
        historyInitialized: false,
        historyLoading: false,
        errorMessage: runtimeErrorDisplayMessage(error),
        errorFailure: runtimeFailureFromError(error),
        retryAvailable: true,
      );
      _rememberRetry(_PersonalAssistantRetryKind.switchConversation, target);
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
  /// cancelled 终态事件结束流，send() 收尾时落停止态。
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
    await _reportRegenerateInteraction(option);
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
    final fact = AppendAssistantLearningFactRequest(
      eventId: 'regen:$runId:${option?.name ?? 'regenerate'}',
      eventVersion: 1,
      factType: AssistantLearningFactType.interactionOutcome,
      assistantTurnId: runId,
      referralSource: assistantReferralSourceForOpenContext(_openContext),
      domainId: 'assistant',
      eventType: InteractionEventType.actionClick,
      feedbackType: FeedbackType.regenerated,
      actionType: option?.name ?? 'regenerate',
      trainingEligible: false,
      occurredAt: DateTime.now().toUtc().toIso8601String(),
    );
    await _persistAndFlushLearningFact(fact);
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
    if (!state.historyInitialized) {
      return;
    }
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

  Future<void> send(String text) {
    return _send(text);
  }

  Future<void> _ensureOpenPageContextReported() {
    final context = _openContext;
    if (context == null) {
      return Future<void>.value();
    }
    final inFlight = _pageContextReportFuture;
    if (inFlight != null) {
      return inFlight;
    }
    final report = () async {
      try {
        await ref
            .read(assistantPersonalizationFacetProvider)
            .reportPageContext(
              context: context,
              userAction: 'open_assistant_conversation',
            );
      } catch (_) {
        _pageContextReportFuture = null;
        rethrow;
      }
    }();
    _pageContextReportFuture = report;
    return report;
  }

  Future<void> _send(
    String text, {
    String runClientRequestId = '',
    String conversationClientRequestId = '',
  }) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty || state.running) {
      return;
    }
    await ensureHistoryInitialized();
    if (!state.historyInitialized) {
      return;
    }
    final resolvedRunClientRequestId = _assistantClientRequestId(
      runClientRequestId,
      scope: 'run',
    );
    final resolvedConversationClientRequestId =
        state.conversationId.trim().isEmpty
        ? _assistantClientRequestId(
            conversationClientRequestId,
            scope: 'conversation',
          )
        : '';
    _debugPersonalAssistant(
      'send text="${_debugSnippet(trimmed)}" existingConversation=${state.conversationId}',
    );
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
    final turnStartedAt = DateTime.now();
    var runStarted = false;
    try {
      await _ensureOpenPageContextReported();
      var conversationId = state.conversationId;
      if (conversationId.isEmpty) {
        final conversation = await repository.createAssistantConversation(
          summary: AssistantText.assistantCloudConversationSummary,
          clientRequestId: resolvedConversationClientRequestId,
        );
        conversationId = conversation.conversationId.trim();
        if (conversationId.isEmpty) {
          throw const FormatException(
            'CreateAssistantConversation returned an empty conversationId',
          );
        }
        // 创建成功后立即固定会话，StartAssistantRun 超时/失败的重试才会沿用该
        // conversation 与同一 run intent，而不是额外创建空会话。
        state = state.copyWith(conversationId: conversationId);
        _debugPersonalAssistant('conversation created id=$conversationId');
      }
      final turn = await repository.startAssistantRun(
        conversationId: conversationId,
        text: trimmed,
        clientRequestId: resolvedRunClientRequestId,
        domainId: 'assistant',
        intersectionEvidenceRefs: _pendingIntersectionEvidenceRefs,
      );
      _pendingIntersectionEvidenceRefs =
          const <AssistantIntersectionEvidenceRef>[];
      runStarted = true;
      _recordAssistantTurnQuality(
        turnAction: _assistantTurnActionSubmit,
        result: _assistantTurnResultSuccess,
        startedAt: turnStartedAt,
        operationId: AssistantApiMetadata.startAssistantRunOperation,
      );
      _debugPersonalAssistant(
        'turn created conversationId=$conversationId turnId=${turn.turnId} traceId=${turn.traceId}',
      );
      var answer = '';
      var lastSeq = 0;
      var failed = false;
      var cancelled = false;
      var firstAnswerObserved = false;
      var terminalEventObserved = false;
      final startedAt = turnStartedAt;
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
      _reportPendingSuggestedAction(turn.turnId);
      await for (final event in repository.watchAssistantRunEvents(
        runId: turn.turnId,
      )) {
        if (event.seq <= lastSeq) {
          continue;
        }
        lastSeq = event.seq;
        events.add(event);
        final streamEvent = AssistantRunStreamEvent.fromWire(event);
        if (streamEvent.type == AssistantRunStreamEventType.unknown) {
          throw FormatException(
            'Unsupported assistant stream event type ${event.eventType}',
          );
        }
        if (streamEvent.type == AssistantRunStreamEventType.runStarted &&
            streamEvent.restarted) {
          answer = '';
          processSummary = const PersonalAssistantProcessSummary();
        }
        if (streamEvent.type == AssistantRunStreamEventType.cancelled) {
          cancelled = true;
        }
        if (streamEvent.type == AssistantRunStreamEventType.answerDelta &&
            !firstAnswerObserved) {
          firstAnswerObserved = true;
          _recordAssistantTurnQuality(
            turnAction: _assistantTurnActionFirstAnswer,
            result: _assistantTurnResultSuccess,
            startedAt: startedAt,
            operationId: AssistantApiMetadata.streamAssistantRunEventsOperation,
          );
        }
        if (streamEvent.type.isTerminal) {
          terminalEventObserved = true;
          _recordAssistantTurnQuality(
            turnAction: switch (streamEvent.type) {
              AssistantRunStreamEventType.completed =>
                _assistantTurnActionCompleted,
              AssistantRunStreamEventType.failed => _assistantTurnActionFailed,
              AssistantRunStreamEventType.cancelled =>
                _assistantTurnActionCancelled,
              _ => _assistantTurnActionStreamFailure,
            },
            result: switch (streamEvent.type) {
              AssistantRunStreamEventType.completed =>
                _assistantTurnResultSuccess,
              AssistantRunStreamEventType.cancelled =>
                _assistantTurnResultCancelled,
              _ => _assistantTurnResultFailure,
            },
            startedAt: startedAt,
            failReasonCode: streamEvent.wire.runtimeFailure?.code,
            operationId: AssistantApiMetadata.streamAssistantRunEventsOperation,
          );
        }
        _debugPersonalAssistant(
          'stream event type=${event.eventType} seq=${event.seq} turnId=${turn.turnId} '
          'process=${streamEvent.process?.stage ?? ''} '
          'status=${streamEvent.process?.status ?? ''}',
        );
        processSummary = _projectProcessSummary(
          processSummary,
          streamEvent,
          elapsedMs: DateTime.now().difference(startedAt).inMilliseconds,
        );
        final failureMessage = _failureMessageForEvent(streamEvent);
        if (failureMessage.isNotEmpty) {
          failed = true;
          transcript = _upsertAssistantTranscript(
            transcript,
            assistantItemId,
            text: failureMessage,
            turnId: turn.turnId,
            traceId: turn.traceId,
            sourceQuery: trimmed,
            eventType: event.eventType.wireName,
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
        answer = _projectAnswer(answer, streamEvent);
        final answerGateOpen =
            state.answerGateOpen ||
            _isAnswerEvent(streamEvent) ||
            answer.isNotEmpty;
        if (_isAnswerEvent(streamEvent)) {
          _debugPersonalAssistant(
            'answer event type=${event.eventType} answerLength=${answer.length}',
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
            eventType: event.eventType.wireName,
            streaming:
                streamEvent.type != AssistantRunStreamEventType.completed,
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
      if (!terminalEventObserved) {
        throw const FormatException(
          'Assistant SSE stream ended without a terminal event',
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
        // turn 完成时补发上一轮保存在 actor-scoped outbox 中的学习事实。
        await ref.read(assistantLearningFactOutboxProvider.notifier).flush();
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
      _recordAssistantTurnQuality(
        turnAction: runStarted
            ? _assistantTurnActionStreamFailure
            : _assistantTurnActionSubmit,
        result: _assistantTurnResultFailure,
        startedAt: turnStartedAt,
        failReasonCode: runtimeFailureFromError(error)?.code,
        operationId: runStarted
            ? AssistantApiMetadata.streamAssistantRunEventsOperation
            : AssistantApiMetadata.startAssistantRunOperation,
      );
      _rememberRetry(
        _PersonalAssistantRetryKind.send,
        trimmed,
        runClientRequestId: resolvedRunClientRequestId,
        conversationClientRequestId: resolvedConversationClientRequestId,
      );
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
        return _send(
          value,
          runClientRequestId: _retryRunClientRequestId,
          conversationClientRequestId: _retryConversationClientRequestId,
        );
      case _PersonalAssistantRetryKind.openTurn:
        return openTurnFromAppMessage(value);
      case _PersonalAssistantRetryKind.history:
        state = state.copyWith(
          errorMessage: '',
          errorFailure: null,
          retryAvailable: false,
        );
        _clearRetry();
        return ensureHistoryInitialized();
      case _PersonalAssistantRetryKind.switchConversation:
        return switchConversation(value);
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

  String _assistantClientRequestId(String value, {required String scope}) {
    final normalized = value.trim();
    if (normalized.isNotEmpty) {
      return normalized;
    }
    return 'assistant-$scope-${const Uuid().v4()}';
  }

  void _rememberRetry(
    _PersonalAssistantRetryKind kind,
    String value, {
    String runClientRequestId = '',
    String conversationClientRequestId = '',
  }) {
    _retryKind = kind;
    _retryValue = value;
    _retryRunClientRequestId = runClientRequestId.trim();
    _retryConversationClientRequestId = conversationClientRequestId.trim();
  }

  void _clearRetry() {
    _retryKind = null;
    _retryValue = '';
    _retryRunClientRequestId = '';
    _retryConversationClientRequestId = '';
  }

  void _recordAssistantTurnQuality({
    required String turnAction,
    required String result,
    required DateTime startedAt,
    String? failReasonCode,
    String? operationId,
  }) {
    if (!ref.mounted) {
      return;
    }
    final durationMs = DateTime.now()
        .difference(startedAt)
        .inMilliseconds
        .clamp(0, 1 << 31)
        .toInt();
    unawaited(() async {
      try {
        await ref
            .read(appTelemetryReporterProvider)
            .record(
              AppTelemetryPayload.assistantTurnQuality(
                turnAction: turnAction,
                result: result,
                durationMs: durationMs,
                failReasonCode: failReasonCode?.trim().isEmpty ?? true
                    ? null
                    : failReasonCode!.trim(),
                operationId: operationId?.trim().isEmpty ?? true
                    ? null
                    : operationId!.trim(),
              ),
            );
      } catch (error, stackTrace) {
        developer.log(
          'assistant turn telemetry failed',
          name: 'personal_assistant',
          error: error.runtimeType,
          stackTrace: stackTrace,
        );
      }
    }());
  }

  @visibleForTesting
  int get pendingFeedbackEventCount =>
      ref.read(assistantLearningFactOutboxProvider);

  Future<void> submitFeedback(String feedbackType) async {
    final normalized = feedbackType.trim();
    if (normalized.isEmpty || state.feedbackType == normalized) {
      return;
    }
    final label = switch (normalized) {
      'useful' => AssistantText.assistantFeedbackUsefulLabel,
      'irrelevant' => AssistantText.assistantFeedbackIrrelevantLabel,
      'too_frequent' => AssistantText.assistantFeedbackTooFrequentLabel,
      _ => AssistantText.assistantFeedbackRecordedLabel,
    };
    // 本地反馈展示先行；学习事实先持久化到 actor-scoped outbox，再异步确认。
    state = state.copyWith(
      feedbackMessage: AssistantText.assistantFeedbackRecorded(label),
      feedbackType: normalized,
    );
    await _reportFeedbackInteraction(normalized);
  }

  /// 用户实际打开已验证的引用后，追加可审计的交互结果。
  ///
  /// 仅记录 internal/external 类型，不上传 URL、标题或引用正文。
  void reportReferenceOpened({required bool external}) {
    final assistantTurnId = state.turnId.trim();
    if (assistantTurnId.isEmpty) {
      return;
    }
    final referenceKind = external ? 'external' : 'internal';
    unawaited(
      _persistAndFlushLearningFact(
        AppendAssistantLearningFactRequest(
          eventId: 'reference-open:$assistantTurnId:$referenceKind',
          eventVersion: 1,
          factType: AssistantLearningFactType.interactionOutcome,
          assistantTurnId: assistantTurnId,
          referralSource: assistantReferralSourceForOpenContext(_openContext),
          domainId: 'assistant',
          eventType: InteractionEventType.actionClick,
          actionType: 'open_${referenceKind}_reference',
          trainingEligible: false,
          occurredAt: DateTime.now().toUtc().toIso8601String(),
        ),
      ),
    );
  }

  void _reportPendingSuggestedAction(String assistantTurnId) {
    final suggestedActionId = _pendingSuggestedActionId;
    if (suggestedActionId.isEmpty || assistantTurnId.trim().isEmpty) {
      return;
    }
    _pendingSuggestedActionId = '';
    unawaited(
      _persistAndFlushLearningFact(
        AppendAssistantLearningFactRequest(
          eventId: 'suggested-action:$assistantTurnId:$suggestedActionId',
          eventVersion: 1,
          factType: AssistantLearningFactType.interactionOutcome,
          assistantTurnId: assistantTurnId,
          referralSource: assistantReferralSourceForOpenContext(_openContext),
          domainId: 'assistant',
          eventType: InteractionEventType.actionClick,
          actionType: 'suggested_action',
          suggestedActionId: suggestedActionId,
          trainingEligible: false,
          occurredAt: DateTime.now().toUtc().toIso8601String(),
        ),
      ),
    );
  }

  Future<void> _reportFeedbackInteraction(String feedbackType) async {
    final runId = state.turnId.trim();
    if (feedbackType.isEmpty || runId.isEmpty) {
      return;
    }
    final fact = AppendAssistantLearningFactRequest(
      // 稳定派生 id：同一 run 上同一反馈动作重试不产生新事件。
      eventId: 'fb:$runId:$feedbackType',
      eventVersion: 1,
      factType: AssistantLearningFactType.userFeedback,
      assistantTurnId: runId,
      referralSource: assistantReferralSourceForOpenContext(_openContext),
      domainId: 'assistant',
      feedbackType: parseFeedbackTypeStrict(feedbackType),
      actionType: feedbackType,
      trainingEligible: false,
      occurredAt: DateTime.now().toUtc().toIso8601String(),
    );
    await _persistAndFlushLearningFact(fact);
  }

  Future<void> _persistAndFlushLearningFact(
    AppendAssistantLearningFactRequest fact,
  ) async {
    try {
      final persisted = await ref
          .read(assistantLearningFactOutboxProvider.notifier)
          .enqueue(fact);
      if (!persisted) {
        developer.log(
          'learning fact encrypted outbox unavailable',
          name: 'AssistantLearningFactOutbox',
          error: 'persist_failed',
        );
        return;
      }
      await ref.read(assistantLearningFactOutboxProvider.notifier).flush();
    } catch (error) {
      developer.log(
        'learning fact remains pending for retry',
        name: 'AssistantLearningFactOutbox',
        error: error,
      );
    }
  }
}

/// 从流式事件中提取小艺对话浮现的兴趣标签（路径制 tagRef）。
///
/// 读取 `completed` envelope 的 `payload['emergedTags']`（云侧
/// `collectEmergedTags` 下发的 `List<String>`），去重并过滤空值。
