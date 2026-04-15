import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/application/assistant_backend.dart';
import 'package:quwoquan_app/assistant/application/transcript/assistant_feedback_target.dart';
import 'package:quwoquan_app/assistant/application/transcript/assistant_replay_record_factory.dart';
import 'package:quwoquan_app/assistant/application/transcript/assistant_transcript_assembler.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/assistant_streaming_answer_decoder.dart';
import 'package:quwoquan_app/assistant/capabilities/capabilities.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/intent_bridge/assistant_intent_bridge_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/orchestration.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_transcript_loader.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_replay_trace_payload.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';
import 'package:quwoquan_app/assistant/reasoning/geo/geo_resolution_catalog.dart';
import 'package:quwoquan_app/assistant/tool/impl/device/local_context_tool.dart';
import 'package:quwoquan_app/assistant/transcript/assistant_answer/assistant_dialogue_runtime_read_view.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/assistant_transcript_row_patch.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/assistant/transcript/replay/assistant_replay_record.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_context_scope_read_view.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_privacy_policy_hint_read_view.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_structured_run_response_read_view.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_display_fallbacks.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_ui_usage_stats_view_data.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_journey_view_model.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_turn_message_resolver.dart';

class AssistantConversationController extends ChangeNotifier {
  AssistantConversationController({required WidgetRef ref, this.openContext})
    : _ref = ref;

  static const int _assistantHistoryPageSize = 18;

  final WidgetRef _ref;
  final AssistantOpenContext? openContext;
  final AssistantStreamingAnswerDecoder _streamingAnswerDecoder =
      AssistantStreamingAnswerDecoder();
  final LocalContextTool _localContextTool = LocalContextTool(
    MethodChannelAdapter(),
  );

  final Map<String, AssistantReplayRecord> _assistantReplayByMessageId =
      <String, AssistantReplayRecord>{};
  final List<AssistantReplayRecord> _assistantReplayRecords =
      <AssistantReplayRecord>[];
  final Map<String, String> _assistantFeedbackStatusByMessageId =
      <String, String>{};
  _AssistantGeoRuntimeContext? _cachedGeoRuntimeContext;

  List<AssistantTranscriptTimelineRow> _transcriptRows =
      <AssistantTranscriptTimelineRow>[];
  AssistantJourney _currentJourney = const AssistantJourney();
  List<ProcessTimelineFrame> _currentCanonicalProcessTimeline =
      const <ProcessTimelineFrame>[];
  List<ProcessTimelineFrame> _currentProcessTimeline =
      const <ProcessTimelineFrame>[];
  RetrievalProcessingSnapshot _currentRetrievalProcessing =
      const RetrievalProcessingSnapshot();
  RunArtifactsUnderstandingSnapshot _currentUnderstandingSnapshot =
      const RunArtifactsUnderstandingSnapshot();
  Timer? _assistantProgressTimer;
  DateTime? _assistantProgressStartedAt;
  String _assistantPhaseLabel = '';
  String? _activeAssistantStreamingMessageId;
  bool _assistantResponding = false;
  bool _assistantLoadingOlderHistory = false;
  bool _showAssistantHistoryPeek = false;
  bool _answerGateOpen = true;
  bool _assistantRemoteConfiguredCached = false;
  int _currentJourneyElapsedMs = 0;
  AssistantBackend _assistantBackend = AssistantBackend.remote;
  String _assistantRuntimeSessionId = '';
  String _assistantTopicTitle = UITextConstants.assistantHistoryAll;
  List<AssistantTranscriptTimelineRow> _assistantHiddenHistory =
      <AssistantTranscriptTimelineRow>[];
  bool _disposed = false;

  List<AssistantTranscriptTimelineRow> get transcriptRows => _transcriptRows;
  AssistantJourney get currentJourney => _currentJourney;
  List<ProcessTimelineFrame> get currentProcessTimeline =>
      _currentProcessTimeline;
  RetrievalProcessingSnapshot get currentRetrievalProcessing =>
      _currentRetrievalProcessing;
  RunArtifactsUnderstandingSnapshot get currentUnderstandingSnapshot =>
      _currentUnderstandingSnapshot;
  String get assistantPhaseLabel => _assistantPhaseLabel;
  String? get activeAssistantStreamingMessageId =>
      _activeAssistantStreamingMessageId;
  bool get assistantResponding => _assistantResponding;
  bool get assistantLoadingOlderHistory => _assistantLoadingOlderHistory;
  bool get showAssistantHistoryPeek => _showAssistantHistoryPeek;
  bool get answerGateOpen => _answerGateOpen;
  int get currentJourneyElapsedMs => _currentJourneyElapsedMs;
  AssistantBackend get assistantBackend => _assistantBackend;
  String get assistantRuntimeSessionId => _assistantRuntimeSessionId;
  String get assistantTopicTitle => _assistantTopicTitle;
  List<AssistantTranscriptTimelineRow> get assistantHiddenHistory =>
      _assistantHiddenHistory;
  Map<String, String> get feedbackStatusByMessageId =>
      _assistantFeedbackStatusByMessageId;
  List<AssistantReplayRecord> get replayRecords => _assistantReplayRecords;

  AssistantTranscriptTimelineRow _mapToRow(Map<String, dynamic> m) =>
      PersistedTimelineTurnCodec.decode(m);

  AssistantTranscriptTimelineRow _patchRow(
    AssistantTranscriptTimelineRow row,
    Map<String, dynamic> patch,
  ) => patchTranscriptRowWithMapMerge(row, patch);

  bool _rowEligibleForAssistantRun(AssistantTranscriptTimelineRow r) {
    switch (r) {
      case ErrorTranscriptTimelineRow():
        return false;
      case UserTranscriptTimelineRow row:
        if (row.type != 'text') return false;
        return row.content.trim().isNotEmpty;
      case AssistantAnswerTranscriptRow row:
        if (row.type != 'text') return false;
        if (row.streaming) return false;
        return _assistantHistoryContentForAssistantRow(row).trim().isNotEmpty;
    }
  }

  AssistantRunMessage? _rowAsRunMessage(AssistantTranscriptTimelineRow r) {
    switch (r) {
      case UserTranscriptTimelineRow row:
        if (row.content.trim().isEmpty) return null;
        return AssistantRunMessage(role: 'user', content: row.content);
      case AssistantAnswerTranscriptRow row:
        final content = _assistantHistoryContentForAssistantRow(row);
        if (content.trim().isEmpty) return null;
        return AssistantRunMessage(role: 'assistant', content: content);
      case ErrorTranscriptTimelineRow():
        return null;
    }
  }

  /// 助手行送入模型的正文候选（与历史 Map 路径 [ _assistantHistoryContentForModel ] 对齐）。
  String _assistantHistoryContentForAssistantRow(AssistantAnswerTranscriptRow row) {
    final candidates = <String>[
      row.persisted.displayPlainText,
      row.persisted.displayMarkdown,
      row.content,
    ];
    for (final candidate in candidates) {
      final sanitized = _sanitizeAssistantHistoryContent(candidate);
      if (sanitized.isNotEmpty) return sanitized;
    }
    return '';
  }

  void _ensureTranscriptRowsGrowable() {
    _transcriptRows = List<AssistantTranscriptTimelineRow>.from(
      _transcriptRows,
    );
  }

  String get effectiveAssistantSessionId {
    _assistantBackend = _resolveAvailableAssistantBackend(_assistantBackend);
    final sessionId = _assistantRuntimeSessionId.trim();
    if (sessionId.isNotEmpty &&
        isAssistantSessionForBackend(sessionId, _assistantBackend)) {
      return sessionId;
    }
    final freshSessionId = newAssistantSessionId(_assistantBackend);
    _assistantRuntimeSessionId = freshSessionId;
    return freshSessionId;
  }

  Future<void> initialize() async {
    _assistantRemoteConfiguredCached = _ref.read(
      assistantRemoteConfiguredProvider,
    );
    _assistantBackend = _preferredAssistantBackendOnOpen();
    _assistantRuntimeSessionId = newAssistantSessionId(_assistantBackend);
    _notify();
    final synced = await syncSessionInfo();
    if (!_disposed && !synced) {
      await _startFreshAssistantSessionOnOpen();
    }
  }

  Future<void> _startFreshAssistantSessionOnOpen() async {
    if (_disposed) return;
    final backend = _resolveAvailableAssistantBackend(_assistantBackend);
    final freshSessionId = newAssistantSessionId(backend);
    _assistantBackend = backend;
    _assistantRuntimeSessionId = freshSessionId;
    _assistantTopicTitle = UITextConstants.assistantHistoryAll;
    _assistantHiddenHistory = <AssistantTranscriptTimelineRow>[];
    _assistantLoadingOlderHistory = false;
    _showAssistantHistoryPeek = false;
    _transcriptRows = <AssistantTranscriptTimelineRow>[];
    _notify();
  }

  void appendOutgoingAttachments(List<ChatInputAttachment> attachments) {
    if (attachments.isEmpty) return;
    final currentUser = _ref.read(userDataProvider);
    final senderId = _currentProfileSubjectId();
    final attachmentMessages = attachments
        .map((item) {
          final kind = item.type == ChatInputAttachmentType.image
              ? UITextConstants.chatMorePhoto
              : UITextConstants.chatMoreFile;
          return <String, dynamic>{
            'id':
                'msg_attachment_${DateTime.now().millisecondsSinceEpoch}_${item.id}',
            'conversationId': AppConceptConstants.assistantConversationId,
            'type': 'text',
            'content': '[$kind] ${item.name}',
            'senderId': senderId,
            'senderName': currentUser?.displayName ?? '我',
            'senderAvatar': currentUser?.avatarUrlOrAvatar ?? '',
            'timestamp': '',
            'status': 'sending',
            'isRead': true,
            'isSelf': true,
          };
        })
        .toList(growable: false);
    _ensureTranscriptRowsGrowable();
    _transcriptRows.addAll(attachmentMessages.map(_mapToRow));
    _notify();
  }

  Future<void> loadOlderHistory() async {
    if (_assistantLoadingOlderHistory || _assistantHiddenHistory.isEmpty) {
      return;
    }
    _assistantLoadingOlderHistory = true;
    _notify();
    final splitIndex = math.max(
      0,
      _assistantHiddenHistory.length - _assistantHistoryPageSize,
    );
    final olderChunk = _assistantHiddenHistory.sublist(splitIndex);
    final remainingHidden = _assistantHiddenHistory.sublist(0, splitIndex);
    _transcriptRows = List<AssistantTranscriptTimelineRow>.from(
      <AssistantTranscriptTimelineRow>[...olderChunk, ..._transcriptRows],
    );
    _assistantHiddenHistory = List<AssistantTranscriptTimelineRow>.from(
      remainingHidden,
    );
    _assistantLoadingOlderHistory = false;
    _showAssistantHistoryPeek = remainingHidden.isNotEmpty;
    _notify();
  }

  Future<bool> syncSessionInfo() async {
    if (_assistantBackend != AssistantBackend.local) return false;
    final sessions = await _ref.read(assistantGatewayProvider).listSessions();
    if (_disposed || sessions.isEmpty) return false;
    final namespacedSessions = sessions
        .where(
          (d) => isAssistantSessionForBackend(
            d.sessionId,
            AssistantBackend.local,
          ),
        )
        .toList(growable: false);
    if (namespacedSessions.isEmpty) return false;
    final active = namespacedSessions.firstWhere(
      (d) => d.isActive,
      orElse: () => namespacedSessions.first,
    );
    final nextSessionId = active.sessionId;
    final nextTopic = active.topicTitle.trim();
    if (nextSessionId.isEmpty) return false;
    _assistantBackend = assistantBackendForSessionId(nextSessionId);
    _assistantRuntimeSessionId = nextSessionId;
    _assistantTopicTitle = nextTopic.isNotEmpty
        ? nextTopic
        : UITextConstants.assistantHistoryAll;
    _notify();
    await _loadAssistantSessionMessages(nextSessionId);
    return true;
  }

  Future<void> _loadAssistantSessionMessages(String sessionId) async {
    if (sessionId.trim().isEmpty) return;
    final detail = await _ref
        .read(assistantGatewayProvider)
        .sessionDetail(sessionId);
    if (_disposed || detail == null) return;
    final result = await loadTranscriptRowsFromSessionDetail(
      detail: detail,
      pageSize: _assistantHistoryPageSize,
      profileSubjectId: _currentProfileSubjectId(),
      normalizeAssistantContentForModel: _assistantHistoryContentForModel,
    );
    _assistantHiddenHistory = result.hiddenRows;
    _assistantLoadingOlderHistory = false;
    _showAssistantHistoryPeek = result.hiddenRows.isNotEmpty;
    _transcriptRows = result.visibleRows;
    final topic = detail.topicTitle.trim();
    if (topic.isNotEmpty) {
      _assistantTopicTitle = topic;
    }
    _notify();
  }

  Future<void> switchSession(String sessionId) async {
    if (sessionId.trim().isEmpty) return;
    final backend = _resolveAvailableAssistantBackend(
      assistantBackendForSessionId(sessionId),
    );
    final resolvedSessionId = isAssistantSessionForBackend(sessionId, backend)
        ? sessionId
        : newAssistantSessionId(backend);
    if (backend == AssistantBackend.local) {
      await _ref
          .read(assistantGatewayProvider)
          .switchSession(resolvedSessionId);
    }
    _assistantBackend = backend;
    _assistantRuntimeSessionId = resolvedSessionId;
    if (backend == AssistantBackend.remote) {
      _assistantTopicTitle = UITextConstants.assistantHistoryAll;
      _assistantHiddenHistory = <AssistantTranscriptTimelineRow>[];
      _assistantLoadingOlderHistory = false;
      _showAssistantHistoryPeek = false;
      _transcriptRows = <AssistantTranscriptTimelineRow>[];
      _notify();
      return;
    }
    _notify();
    await _loadAssistantSessionMessages(resolvedSessionId);
  }

  Future<String> selectBackend(AssistantBackend backend) async {
    final resolvedBackend = _resolveAvailableAssistantBackend(backend);
    if (resolvedBackend == _assistantBackend &&
        isAssistantSessionForBackend(
          effectiveAssistantSessionId,
          resolvedBackend,
        )) {
      return effectiveAssistantSessionId;
    }
    _assistantBackend = resolvedBackend;
    _assistantRuntimeSessionId = newAssistantSessionId(resolvedBackend);
    _assistantTopicTitle = UITextConstants.assistantHistoryAll;
    _assistantHiddenHistory = <AssistantTranscriptTimelineRow>[];
    _assistantLoadingOlderHistory = false;
    _showAssistantHistoryPeek = false;
    _transcriptRows = <AssistantTranscriptTimelineRow>[];
    _notify();
    if (resolvedBackend == AssistantBackend.local) {
      final synced = await syncSessionInfo();
      if (_disposed || synced) return effectiveAssistantSessionId;
    }
    return effectiveAssistantSessionId;
  }

  Future<void> sendMessage({
    required String text,
    required double viewportWidth,
  }) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;
    final activeContext = await _resolveActivePersonaContext();
    final userMessageId = 'msg_${DateTime.now().millisecondsSinceEpoch}';
    _ensureTranscriptRowsGrowable();
    _transcriptRows.add(
      AssistantTranscriptAssembler.userTextMessage(
        id: userMessageId,
        trimmedText: trimmed,
        profileSubjectId: activeContext.profileSubjectId,
        displayName: activeContext.displayName,
        avatarUrl: activeContext.avatarUrl,
        subAccountId: activeContext.subAccountId,
      ),
    );
    final streamNow = DateTime.now();
    final streamTs =
        '${streamNow.hour}:${streamNow.minute.toString().padLeft(2, '0')}';
    _resetStreamingAnswerDecoder();
    _ensureTranscriptRowsGrowable();
    final streamingAssistantMessageId =
        'assistant_stream_${DateTime.now().millisecondsSinceEpoch}';
    _activeAssistantStreamingMessageId = streamingAssistantMessageId;
    _answerGateOpen = false;
    _assistantResponding = true;
    _assistantPhaseLabel = UITextConstants.assistantPhaseUnderstanding;
    _currentJourney = const AssistantJourney();
    _currentCanonicalProcessTimeline = const <ProcessTimelineFrame>[];
    _currentProcessTimeline = const <ProcessTimelineFrame>[];
    _currentRetrievalProcessing = const RetrievalProcessingSnapshot();
    _currentUnderstandingSnapshot = const RunArtifactsUnderstandingSnapshot();
    _currentJourneyElapsedMs = 0;
    _transcriptRows.add(
      AssistantTranscriptAssembler.assistantStreamingPlaceholder(
        id: streamingAssistantMessageId,
        streamTimestamp: streamTs,
      ),
    );
    _startAssistantProgress();
    _notify();
    try {
      final deviceProfile = _assistantDeviceProfileByWidth(viewportWidth);
      if (_assistantBackend == AssistantBackend.local) {
        try {
          await _ref.read(assistantGatewayProvider).ensureRemoteConfigLoaded();
        } catch (error) {
          if (kDebugMode) {
            debugPrint('Assistant remote config load failed, continue: $error');
          }
        }
      }
      final runStartedAt = DateTime.now();
      final assistantMessages = _transcriptRows
          .where(_rowEligibleForAssistantRun)
          .map(_rowAsRunMessage)
          .whereType<AssistantRunMessage>()
          .toList(growable: false);
      final geoRuntimeContext = await _resolveAssistantGeoRuntimeContext();
      final contextScope = _withGeoRuntimeContextScope(
        _withActivePersonaContextScope(
          buildContextScope(),
          activeContext: activeContext,
        ),
        geoRuntimeContext,
      );
      final contextScopeView = AssistantContextScopeReadView(contextScope);
      final sourceQueryHint =
          openContext?.hints['sourceQuery']?.toString().trim() ?? '';
      final sourceSurfaceIdHint =
          openContext?.hints['sourceSurfaceId']?.toString().trim() ?? '';
      final fromGlobalSearch =
          openContext?.hints['fromGlobalSearch'] == true &&
          sourceQueryHint.isNotEmpty &&
          sourceQueryHint == trimmed;
      final request = AssistantRunRequest(
        messages: assistantMessages,
        sessionId: effectiveAssistantSessionId,
        userId: activeContext.profileSubjectId,
        profileSubjectId: activeContext.profileSubjectId,
        subAccountId: activeContext.subAccountId,
        personaContextVersion: activeContext.personaContextVersion,
        deviceProfile: deviceProfile,
        channel: 'app',
        capabilityCatalog: AssistantCapabilityCatalog.defaultCatalog,
        gpsLocation: geoRuntimeContext.gpsLocation,
        contextScopeHint: contextScope,
        privacyProfile: 'default',
        privacyPolicy: contextScopeView.privacyPolicy,
        sourceSurfaceId: fromGlobalSearch && sourceSurfaceIdHint.isNotEmpty
            ? sourceSurfaceIdHint
            : null,
        sourceQuery: fromGlobalSearch ? sourceQueryHint : null,
        fromGlobalSearch: fromGlobalSearch,
      );
      AssistantRunResponse? response;
      try {
        await for (final streamEvent in _runAssistantStream(request)) {
          switch (streamEvent.type) {
            case AssistantRunStreamEventType.trace:
              continue;
            case AssistantRunStreamEventType.failed:
              response = AssistantRunResponse(
                finalText: streamEvent.errorMessage ?? '助手流式调用失败',
                degraded: true,
                errorCode: 'stream_failed',
                traces: const <AssistantTraceEvent>[],
              );
              break;
            case AssistantRunStreamEventType.chunk:
              if ((streamEvent.chunkText ?? '').isNotEmpty) {
                _appendStreamingAnswerChunk(streamEvent.chunkText!);
              }
              continue;
            case AssistantRunStreamEventType.completed:
              if (streamEvent.response != null) {
                response = streamEvent.response;
              }
              break;
            case AssistantRunStreamEventType.answerDelta:
              if ((streamEvent.chunkText ?? '').isNotEmpty) {
                _appendStreamingAnswerChunk(streamEvent.chunkText!);
              }
              continue;
            case AssistantRunStreamEventType.journeyUpdate:
              final journey = streamEvent.journey;
              if (journey != null) {
                _consumeJourneyUpdate(journey);
              }
              continue;
            case AssistantRunStreamEventType.processTimelineUpdate:
              final processTimeline = streamEvent.processTimeline;
              if (processTimeline != null) {
                _consumeProcessTimelineUpdate(processTimeline);
              }
              continue;
          }
          if (response != null) break;
        }
      } catch (streamError) {
        if (kDebugMode) {
          debugPrint('[AssistantConversation] stream error: $streamError');
        }
        response = AssistantRunResponse(
          finalText: '助手初始化异常: ${streamError.runtimeType}',
          degraded: true,
          errorCode: 'provider_or_stream_error',
          traces: const <AssistantTraceEvent>[],
        );
      }
      response ??= const AssistantRunResponse(
        finalText: '助手未返回有效响应',
        degraded: true,
        errorCode: 'no_response',
        traces: <AssistantTraceEvent>[],
      );
      final runResponse = response;
      final finalAnswerReady = _responseMarksFinalAnswerReady(runResponse);
      final displayText = _resolveAssistantDisplayText(runResponse);
      final displayPlainText = _resolveAssistantDisplayPlainText(runResponse);
      final artifactMarkdown = _responseArtifactDisplayMarkdown(runResponse);
      final displayMarkdown =
          AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
            artifactMarkdown.isNotEmpty ? artifactMarkdown : displayText,
            allowJsonExtraction: false,
          );
      _resetStreamingAnswerDecoder();
      final structuredRead = AssistantStructuredRunResponseReadView(
        runResponse.structuredResponse,
      );
      final resolvedSessionId = structuredRead.effectiveSessionIdOrEmpty;
      final activeSessionId =
          isAssistantSessionForBackend(resolvedSessionId, _assistantBackend)
          ? resolvedSessionId
          : effectiveAssistantSessionId;
      final activeTopicTitle = structuredRead.activeTopicTitleOrNull;
      final elapsedMs = DateTime.now().difference(runStartedAt).inMilliseconds;
      final replyTime = ChatTimeFormatter.format(DateTime.now());
      final assistantMessageId =
          'assistant_${DateTime.now().millisecondsSinceEpoch}';
      final uiUsageStats = _buildConversationCumulativeUsageStats(
        runUsageStats: structuredRead.uiUsageStats,
        excludeMessageId: streamingAssistantMessageId,
      );
      final resolvedJourney = resolveAssistantJourneyFromResponse(runResponse);
      final effectiveJourney = _persistableAssistantJourney(
        response: runResponse,
        journey: resolvedJourney.isEmpty ? _currentJourney : resolvedJourney,
      );
      _ensureTranscriptRowsGrowable();
      final existingIndex = _findStreamingAssistantMessageIndex(
        streamingAssistantMessageId,
      );
      final clearedRow = existingIndex >= 0
          ? _clearStreamingAnswerState(_transcriptRows[existingIndex])
          : null;
      final completedDisplayState = resolveAssistantDisplayStateFromRunResponse(
        runResponse,
      );
      final completedCanonicalState = _resolveCompletedCanonicalState(
        response: runResponse,
        journey: effectiveJourney,
        completedDisplayState: completedDisplayState,
        incomingCanonicalProcessTimeline:
            resolveAssistantProcessTimelineFromRunResponse(runResponse),
        incomingAnswerProcessing: _answerProcessingFromResponse(runResponse),
        existingRow: clearedRow,
        finalAnswerReady: finalAnswerReady,
        displayMarkdown: displayMarkdown,
      );
      if (_disposed) return;
      _currentJourney = completedCanonicalState.journey;
      _currentCanonicalProcessTimeline =
          completedCanonicalState.canonicalProcessTimeline;
      _currentProcessTimeline = completedCanonicalState.visibleProcessTimeline;
      _currentRetrievalProcessing = completedCanonicalState.retrievalProcessing;
      _currentUnderstandingSnapshot =
          completedCanonicalState.understandingSnapshot;
      _currentJourneyElapsedMs = elapsedMs;
      final persistedTurnFields = _buildAssistantPersistedTurnFieldsForResponse(
        response: runResponse,
        journey: completedCanonicalState.journey,
        processTimeline: _currentCanonicalProcessTimeline,
        displayMarkdown: displayMarkdown,
        displayPlainText: displayPlainText,
        elapsedMs: elapsedMs,
        displayState: completedCanonicalState.displayState,
        understandingSnapshot: completedCanonicalState.understandingSnapshot,
        retrievalProcessing: completedCanonicalState.retrievalProcessing,
        answerProcessing: completedCanonicalState.answerProcessing,
      );
      final mergedRunArtifacts = _withDisplayOverrides(
        _responseRunArtifactsMap(runResponse),
        displayMarkdown: displayMarkdown,
        displayPlainText: displayPlainText,
        displayState: completedCanonicalState.displayState,
        journey: completedCanonicalState.journey,
        processTimeline: completedCanonicalState.canonicalProcessTimeline,
        understandingSnapshot: completedCanonicalState.understandingSnapshot,
        retrievalProcessing: completedCanonicalState.retrievalProcessing,
        answerProcessing: completedCanonicalState.answerProcessing,
      );
      final completedAssistantRow =
          AssistantTranscriptAssembler.completedAssistantAnswerTranscriptRow(
        mergeFrom: existingIndex >= 0
            ? clearedRow! as AssistantAnswerTranscriptRow
            : null,
        newRowId: assistantMessageId,
        content: displayMarkdown,
        timestamp: replyTime,
        sourceQuery: trimmed,
        runId: runResponse.runId ?? '',
        traceId: runResponse.traceId ?? '',
        degraded: runResponse.degraded,
        templateVersionUsed: structuredRead.templateVersionUsedOrEmpty,
        phaseOneRoutingDiagnostics: structuredRead.phaseOneRoutingDiagnosticsMap,
        qualityMetrics: structuredRead.qualityMetricsMap,
        heuristicFallbackUsed:
            structuredRead.heuristicFallbackUsedFromQualityMetrics,
        dialogueState: structuredRead.dialogueRuntime,
        uiReferences: structuredRead.uiReferences,
        uiActions: structuredRead.uiActions,
        mergedRunArtifacts: mergedRunArtifacts,
        uiUsageStats: uiUsageStats,
        persistedTurnFields: persistedTurnFields,
      );
      if (existingIndex >= 0) {
        _transcriptRows[existingIndex] = completedAssistantRow;
      } else {
        _transcriptRows.add(completedAssistantRow);
      }
      _assistantResponding = false;
      _assistantPhaseLabel = '';
      _activeAssistantStreamingMessageId = null;
      _answerGateOpen = finalAnswerReady;
      if (activeSessionId.isNotEmpty) {
        _assistantRuntimeSessionId = activeSessionId;
      }
      if (activeTopicTitle != null && activeTopicTitle.isNotEmpty) {
        _assistantTopicTitle = activeTopicTitle;
      }
      _stopAssistantProgress();
      _storeAssistantReplayRecord(
        messageId: completedAssistantRow.id,
        query: trimmed,
        response: runResponse,
      );
      _notify();
      await _recordAssistantInteractionSafely(
        runResponse: runResponse,
        activeContext: activeContext,
        contextScopeView: contextScopeView,
        trimmedQuery: trimmed,
        elapsedMs: elapsedMs,
        sessionId: effectiveAssistantSessionId,
      );
    } catch (e, st) {
      if (kDebugMode) {
        debugPrint('[AssistantConversation] assistant run failed: $e');
        debugPrint('$st');
      }
      _resetStreamingAnswerDecoder();
      _ensureTranscriptRowsGrowable();
      _assistantResponding = false;
      _assistantPhaseLabel = '';
      _activeAssistantStreamingMessageId = null;
      _answerGateOpen = true;
      _transcriptRows.removeWhere(
        (item) => item.id == streamingAssistantMessageId,
      );
      final errorHint = kDebugMode ? '助手异常: ${e.runtimeType}' : '助手出现异常，请重试。';
      _transcriptRows.add(
        AssistantTranscriptAssembler.assistantErrorMessage(
          id: 'assistant_err_${DateTime.now().millisecondsSinceEpoch}',
          errorHint: errorHint,
        ),
      );
      _stopAssistantProgress();
      _notify();
    }
  }

  Future<void> sendRewrite({
    required String query,
    required RewriteInstruction rewrite,
  }) async {
    if (_assistantResponding) return;
    final activeContext = await _resolveActivePersonaContext();
    final now = DateTime.now();
    final ts = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
    _ensureTranscriptRowsGrowable();
    _transcriptRows.add(
      AssistantTranscriptAssembler.userRewriteLabel(
        id: 'user_rewrite_${now.millisecondsSinceEpoch}',
        label: _rewriteUserLabel(rewrite.mode),
        profileSubjectId: activeContext.profileSubjectId,
        displayName: activeContext.displayName,
        timestamp: ts,
      ),
    );
    final geoRuntimeContext = await _resolveAssistantGeoRuntimeContext();
    final contextScope = _withGeoRuntimeContextScope(
      _withActivePersonaContextScope(
        buildContextScope(),
        activeContext: activeContext,
      ),
      geoRuntimeContext,
    );
    final request = AssistantRunRequest(
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: query),
      ],
      sessionId: _assistantRuntimeSessionId,
      userId: activeContext.profileSubjectId,
      profileSubjectId: activeContext.profileSubjectId,
      subAccountId: activeContext.subAccountId,
      personaContextVersion: activeContext.personaContextVersion,
      maxIterations: rewrite.mode == RewriteMode.deepThink ? 6 : 1,
      capabilityCatalog: AssistantCapabilityCatalog.defaultCatalog,
      gpsLocation: geoRuntimeContext.gpsLocation,
      contextScopeHint: contextScope,
      rewriteInstruction: rewrite,
    );
    String? streamingAssistantMessageId;
    _resetStreamingAnswerDecoder();
    _ensureTranscriptRowsGrowable();
    streamingAssistantMessageId =
        'assistant_rewrite_${now.millisecondsSinceEpoch}';
    _activeAssistantStreamingMessageId = streamingAssistantMessageId;
    _answerGateOpen = false;
    _assistantResponding = true;
    _assistantPhaseLabel = UITextConstants.assistantPhaseAnswering;
    _currentJourney = const AssistantJourney();
    _currentCanonicalProcessTimeline = const <ProcessTimelineFrame>[];
    _currentProcessTimeline = const <ProcessTimelineFrame>[];
    _currentRetrievalProcessing = const RetrievalProcessingSnapshot();
    _currentUnderstandingSnapshot = const RunArtifactsUnderstandingSnapshot();
    _currentJourneyElapsedMs = 0;
    _transcriptRows.add(
      AssistantTranscriptAssembler.assistantStreamingPlaceholderWithSourceQuery(
        id: streamingAssistantMessageId,
        streamTimestamp: ts,
        sourceQuery: query,
      ),
    );
    _startAssistantProgress();
    _notify();
    try {
      AssistantRunResponse? response;
      if (_assistantBackend == AssistantBackend.local) {
        try {
          await _ref.read(assistantGatewayProvider).ensureRemoteConfigLoaded();
        } catch (error) {
          if (kDebugMode) {
            debugPrint('Assistant remote config load failed, continue: $error');
          }
        }
      }
      try {
        await for (final streamEvent in _runAssistantStream(request)) {
          switch (streamEvent.type) {
            case AssistantRunStreamEventType.trace:
              continue;
            case AssistantRunStreamEventType.failed:
              response = AssistantRunResponse(
                finalText: streamEvent.errorMessage ?? '助手流式调用失败',
                degraded: true,
                errorCode: 'stream_failed',
                traces: const <AssistantTraceEvent>[],
              );
              break;
            case AssistantRunStreamEventType.journeyUpdate:
              final journey = streamEvent.journey;
              if (journey != null) {
                _consumeJourneyUpdate(journey);
              }
              continue;
            case AssistantRunStreamEventType.chunk:
            case AssistantRunStreamEventType.answerDelta:
              if ((streamEvent.chunkText ?? '').isNotEmpty) {
                _appendStreamingAnswerChunk(streamEvent.chunkText!);
              }
              continue;
            case AssistantRunStreamEventType.processTimelineUpdate:
              final processTimeline = streamEvent.processTimeline;
              if (processTimeline != null) {
                _consumeProcessTimelineUpdate(processTimeline);
              }
              continue;
            case AssistantRunStreamEventType.completed:
              if (streamEvent.response != null) response = streamEvent.response;
              break;
          }
          if (response != null) break;
        }
      } catch (streamError) {
        if (kDebugMode) {
          debugPrint('[AssistantConversation] rewrite stream error: $streamError');
        }
        response = AssistantRunResponse(
          finalText: '助手初始化异常: ${streamError.runtimeType}',
          degraded: true,
          errorCode: 'provider_or_stream_error',
          traces: const <AssistantTraceEvent>[],
        );
      }
      response ??= const AssistantRunResponse(
        finalText: '助手未返回有效响应',
        degraded: true,
        errorCode: 'no_response',
        traces: <AssistantTraceEvent>[],
      );
      if (!_disposed) {
        final finalResponse = response;
        final finalAnswerReady = _responseMarksFinalAnswerReady(finalResponse);
        final structuredRead = AssistantStructuredRunResponseReadView(
          finalResponse.structuredResponse,
        );
        final uiUsageStats = _buildConversationCumulativeUsageStats(
          runUsageStats: structuredRead.uiUsageStats,
          excludeMessageId: streamingAssistantMessageId,
        );
        final resolvedJourney = resolveAssistantJourneyFromResponse(
          finalResponse,
        );
        final effectiveJourney = _persistableAssistantJourney(
          response: finalResponse,
          journey: resolvedJourney.isEmpty ? _currentJourney : resolvedJourney,
        );
        final finalText = _resolveAssistantDisplayText(finalResponse);
        final displayPlainText = _resolveAssistantDisplayPlainText(
          finalResponse,
        );
        final artifactMarkdown = _responseArtifactDisplayMarkdown(
          finalResponse,
        );
        final displayMarkdown =
            AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
              artifactMarkdown.isNotEmpty ? artifactMarkdown : finalText,
              allowJsonExtraction: false,
            );
        _resetStreamingAnswerDecoder();
        _ensureTranscriptRowsGrowable();
        final idx = _findStreamingAssistantMessageIndex(
          streamingAssistantMessageId,
        );
        final clearedRow = idx >= 0
            ? _clearStreamingAnswerState(_transcriptRows[idx])
            : null;
        final completedDisplayState =
            resolveAssistantDisplayStateFromRunResponse(finalResponse);
        final completedCanonicalState = _resolveCompletedCanonicalState(
          response: finalResponse,
          journey: effectiveJourney,
          completedDisplayState: completedDisplayState,
          incomingCanonicalProcessTimeline:
              resolveAssistantProcessTimelineFromRunResponse(finalResponse),
          incomingAnswerProcessing: _answerProcessingFromResponse(
            finalResponse,
          ),
          existingRow: clearedRow,
          finalAnswerReady: finalAnswerReady,
          displayMarkdown: displayMarkdown,
        );
        _currentJourney = completedCanonicalState.journey;
        _currentCanonicalProcessTimeline =
            completedCanonicalState.canonicalProcessTimeline;
        _currentProcessTimeline =
            completedCanonicalState.visibleProcessTimeline;
        _currentRetrievalProcessing =
            completedCanonicalState.retrievalProcessing;
        _currentUnderstandingSnapshot =
            completedCanonicalState.understandingSnapshot;
        final persistedTurnFields =
            _buildAssistantPersistedTurnFieldsForResponse(
              response: finalResponse,
              journey: completedCanonicalState.journey,
              processTimeline: _currentCanonicalProcessTimeline,
              displayMarkdown: displayMarkdown,
              displayPlainText: displayPlainText,
              elapsedMs: _currentJourneyElapsedMs,
              displayState: completedCanonicalState.displayState,
              understandingSnapshot:
                  completedCanonicalState.understandingSnapshot,
              retrievalProcessing: completedCanonicalState.retrievalProcessing,
              answerProcessing: completedCanonicalState.answerProcessing,
            );
        if (idx >= 0) {
          final mergeRow = clearedRow! as AssistantAnswerTranscriptRow;
          final mergedRunArtifacts = _withDisplayOverrides(
            _responseRunArtifactsMap(finalResponse),
            displayMarkdown: displayMarkdown,
            displayPlainText: displayPlainText,
            displayState: completedCanonicalState.displayState,
            journey: completedCanonicalState.journey,
            processTimeline: completedCanonicalState.canonicalProcessTimeline,
            understandingSnapshot:
                completedCanonicalState.understandingSnapshot,
            retrievalProcessing: completedCanonicalState.retrievalProcessing,
            answerProcessing: completedCanonicalState.answerProcessing,
          );
          _transcriptRows[idx] =
              AssistantTranscriptAssembler.completedAssistantAnswerTranscriptRow(
            mergeFrom: mergeRow,
            newRowId: streamingAssistantMessageId,
            content: displayMarkdown,
            timestamp: mergeRow.timestamp,
            sourceQuery: query,
            runId: finalResponse.runId ?? '',
            traceId: finalResponse.traceId ?? '',
            degraded: finalResponse.degraded,
            templateVersionUsed: structuredRead.templateVersionUsedOrEmpty,
            phaseOneRoutingDiagnostics:
                structuredRead.phaseOneRoutingDiagnosticsMap,
            qualityMetrics: structuredRead.qualityMetricsMap,
            heuristicFallbackUsed:
                structuredRead.heuristicFallbackUsedFromQualityMetrics,
            dialogueState: structuredRead.dialogueRuntime,
            uiReferences: structuredRead.uiReferences,
            uiActions: structuredRead.uiActions,
            mergedRunArtifacts: mergedRunArtifacts,
            uiUsageStats: uiUsageStats,
            persistedTurnFields: persistedTurnFields,
          );
        }
        _answerGateOpen = finalAnswerReady;
      }
    } catch (e, st) {
      if (kDebugMode) {
        debugPrint('[AssistantConversation] rewrite failed: $e');
        debugPrint('$st');
      }
      _answerGateOpen = true;
    } finally {
      _resetStreamingAnswerDecoder();
      _assistantResponding = false;
      _assistantPhaseLabel = '';
      _activeAssistantStreamingMessageId = null;
      _stopAssistantProgress();
      _notify();
    }
  }

  Future<void> _recordAssistantInteractionSafely({
    required AssistantRunResponse runResponse,
    required ActivePersonaContextViewData activeContext,
    required AssistantContextScopeReadView contextScopeView,
    required String trimmedQuery,
    required int elapsedMs,
    required String sessionId,
  }) async {
    try {
      await _ref
          .read(assistantLearningServiceProvider)
          .recordInteraction(
            runId:
                runResponse.runId ??
                'run_${DateTime.now().millisecondsSinceEpoch}',
            traceId:
                runResponse.traceId ??
                'trace_${DateTime.now().millisecondsSinceEpoch}',
            userId: activeContext.profileSubjectId,
            sessionId: sessionId,
            pageType: contextScopeView.pageType,
            queryText: trimmedQuery,
            answerText: _resolveAssistantDisplayPlainText(runResponse),
            userTags: contextScopeView.normalizedUserTags,
            durationMs: elapsedMs,
          );
    } catch (error, st) {
      if (kDebugMode) {
        debugPrint(
          '[AssistantConversation] learning record failed, keep answer row: $error',
        );
        debugPrint('$st');
      }
    }
  }

  Future<void> submitFeedback({
    required AssistantFeedbackTarget target,
    required String explicitThumb,
    required List<String> reasonCodes,
    String correctionText = '',
  }) async {
    final messageId = target.messageId;
    final replay = _assistantReplayByMessageId[messageId];
    final query = target.sourceQuery.isNotEmpty
        ? target.sourceQuery
        : (replay?.query ?? '');
    final runId = target.runId.isNotEmpty
        ? target.runId
        : (replay?.runId ?? '');
    final traceId = target.traceId.isNotEmpty
        ? target.traceId
        : (replay?.traceId ?? '');
    final contextScope = buildContextScope();
    final scopeView = AssistantContextScopeReadView(contextScope);
    final userTags = scopeView.normalizedUserTags;
    await _ref
        .read(assistantLearningServiceProvider)
        .recordExplicitFeedback(
          runId: runId.isNotEmpty
              ? runId
              : 'run_${DateTime.now().millisecondsSinceEpoch}',
          traceId: traceId.isNotEmpty
              ? traceId
              : 'trace_${DateTime.now().millisecondsSinceEpoch}',
          userId: _currentProfileSubjectId(),
          sessionId: effectiveAssistantSessionId,
          pageType: scopeView.pageType,
          queryText: query,
          answerText: target.answerText,
          userTags: userTags,
          explicitThumb: explicitThumb,
          explicitReasonCodes: reasonCodes,
          correctionText: correctionText,
          feedbackTargetMessageId: messageId,
        );
    final statusLabel = explicitThumb == 'up'
        ? UITextConstants.assistantFeedbackHelpful
        : UITextConstants.assistantFeedbackUnhelpful;
    _assistantFeedbackStatusByMessageId[messageId] = statusLabel;
    _notify();
  }

  Future<void> recordImplicitFeedback({
    required AssistantFeedbackTarget target,
    bool copiedAnswer = false,
    bool sharedAnswer = false,
    bool favoritedAnswer = false,
    bool regeneratedAnswer = false,
    bool styleAdjusted = false,
    bool modelSwitched = false,
    bool referenceOpened = false,
    List<String> userTags = const <String>[],
  }) async {
    final contextScope = buildContextScope();
    final scopeView = AssistantContextScopeReadView(contextScope);
    final tags = userTags.isNotEmpty
        ? userTags
        : scopeView.normalizedUserTags;
    await _ref
        .read(assistantLearningServiceProvider)
        .recordInteraction(
          runId: target.runId.trim().isNotEmpty
              ? target.runId.trim()
              : 'run_${DateTime.now().millisecondsSinceEpoch}',
          traceId: target.traceId.trim().isNotEmpty
              ? target.traceId.trim()
              : 'trace_${DateTime.now().millisecondsSinceEpoch}',
          userId: _currentProfileSubjectId(),
          sessionId: effectiveAssistantSessionId,
          pageType: scopeView.pageType,
          queryText: target.sourceQuery,
          answerText: target.displayPlainText.trim().isNotEmpty
              ? target.displayPlainText
              : target.answerText,
          userTags: tags,
          durationMs: 0,
          copiedAnswer: copiedAnswer,
          sharedAnswer: sharedAnswer,
          favoritedAnswer: favoritedAnswer,
          regeneratedAnswer: regeneratedAnswer,
          styleAdjusted: styleAdjusted,
          modelSwitched: modelSwitched,
          referenceOpened: referenceOpened,
          feedbackTargetMessageId: target.messageId,
        );
  }

  bool isReferenceHostAllowed(Uri uri) {
    if (uri.scheme != 'https') return false;
    final host = uri.host.trim().toLowerCase();
    if (host.isEmpty) return false;
    final whitelist = referenceWhitelistHosts();
    if (whitelist.isEmpty) return false;
    for (final allowed in whitelist) {
      if (host == allowed || host.endsWith('.$allowed')) {
        return true;
      }
    }
    return false;
  }

  List<String> referenceWhitelistHosts() {
    final scopeView = AssistantContextScopeReadView(buildContextScope());
    final privacyPolicy = scopeView.privacyPolicy;
    final rawHosts =
        (privacyPolicy['allowedReferenceHosts'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim().toLowerCase())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (rawHosts.isNotEmpty) return rawHosts;
    return AppConceptConstants.assistantReferenceHostWhitelist;
  }

  Map<String, dynamic> replayForMessage(String messageId) {
    return _assistantReplayByMessageId[messageId]?.toJson() ??
        const <String, dynamic>{};
  }

  void removeMessageById(String id) {
    _transcriptRows = List<AssistantTranscriptTimelineRow>.from(_transcriptRows)
      ..removeWhere((item) => item.id == id);
    _notify();
  }

  String _currentProfileSubjectId() {
    final currentUser = _ref.read(userDataProvider);
    if (currentUser?.id.isNotEmpty == true) {
      return currentUser!.id;
    }
    return _ref.read(currentUserIdProvider);
  }

  Future<ActivePersonaContextViewData> _resolveActivePersonaContext() async {
    final activeContext = await _ref.read(activePersonaContextProvider.future);
    if (_assistantBackend == AssistantBackend.remote &&
        activeContext.isFallback) {
      throw StateError('active persona context unavailable');
    }
    return activeContext;
  }

  Map<String, dynamic> _withActivePersonaContextScope(
    Map<String, dynamic> baseScope, {
    ActivePersonaContextViewData? activeContext,
  }) {
    final resolvedContext =
        activeContext ??
        _ref
            .read(activePersonaContextProvider)
            .maybeWhen(data: (value) => value, orElse: () => null);
    final profileSubjectId =
        resolvedContext?.profileSubjectId.isNotEmpty == true
        ? resolvedContext!.profileSubjectId
        : _currentProfileSubjectId();
    return <String, dynamic>{
      ...baseScope,
      'userId': profileSubjectId,
      if (resolvedContext?.profileSubjectId.isNotEmpty == true)
        'profileSubjectId': resolvedContext!.profileSubjectId,
      if (resolvedContext?.subAccountId.isNotEmpty == true)
        'subAccountId': resolvedContext!.subAccountId,
      if (resolvedContext?.personaContextVersion.isNotEmpty == true)
        'personaContextVersion': resolvedContext!.personaContextVersion,
    };
  }

  Map<String, dynamic> buildContextScope() {
    final hints = openContext?.hints ?? const <String, dynamic>{};
    final privacyView =
        AssistantPrivacyPolicyHintReadView.fromOpenContextHints(hints);
    final contentAccessState = _ref.read(personalContentAccessProvider);
    final identityIndexFeatureFlag = _ref.read(
      contentFeatureFlagProvider('enable_assistant_content_identity_index'),
    );
    final identityIndexEnabled = _ref.read(
      assistantContentIdentityIndexEnabledProvider,
    );
    final allowedProviders = List<String>.from(privacyView.allowedProviders);
    final blockedProviders = List<String>.from(privacyView.blockedProviders);
    if (!contentAccessState.granted) {
      allowedProviders.remove('page_context');
      if (!blockedProviders.contains('page_context')) {
        blockedProviders.add('page_context');
      }
    }
    final normalizedPrivacyPolicy = privacyView.copyWithProviderLists(
      allowedProviders: allowedProviders,
      blockedProviders: blockedProviders,
    );
    final userTags =
        (hints['userTags'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    final latestDialogueState = _latestAssistantDialogueState();
    final dialogueRuntimeView =
        AssistantDialogueRuntimeReadView(latestDialogueState);
    final latestRunArtifacts = _latestAssistantRunArtifacts();
    final scope = <String, dynamic>{
      'pageType': _assistantSourceToPageType(openContext?.source),
      'sessionId': effectiveAssistantSessionId,
      'assistantBackend': _assistantBackend.wireName,
      if (openContext?.entityId != null) 'entityId': openContext!.entityId!,
      if (openContext?.tab != null) 'tab': openContext!.tab!,
      if (openContext?.dimension != null) 'dimension': openContext!.dimension!,
      'hints': hints,
      if (hints['behaviorTimeline'] is List)
        'behaviorTimeline': hints['behaviorTimeline'],
      if (userTags.isNotEmpty) 'userTags': userTags,
      if (latestDialogueState.isNotEmpty) 'dialogueState': latestDialogueState,
      if (latestRunArtifacts != null)
        'runArtifacts': latestRunArtifacts.toJson(),
      if (dialogueRuntimeView.suggestedNextStateIdOrEmpty.isNotEmpty)
        'currentStateId': dialogueRuntimeView.suggestedNextStateIdOrEmpty,
      'assistantContentAccess': <String, dynamic>{
        'skillId': kPersonalContentAccessSkillId,
        'granted': contentAccessState.granted,
        'grantedScope': contentAccessState.grantedScope,
        'source': contentAccessState.source,
        if (contentAccessState.updatedAt != null)
          'updatedAt': contentAccessState.updatedAt!.toIso8601String(),
      },
      'assistantContentIndex': <String, dynamic>{
        'enabled': identityIndexEnabled,
        'featureFlagEnabled': identityIndexFeatureFlag,
        'fallbackReason': contentAccessState.granted
            ? (identityIndexEnabled ? '' : 'feature_flag_disabled')
            : 'consent_denied',
      },
      'privacyProfile': 'default',
      'privacyPolicy': normalizedPrivacyPolicy,
    };
    return _withActivePersonaContextScope(scope);
  }

  Map<String, dynamic> _withGeoRuntimeContextScope(
    Map<String, dynamic> scope,
    _AssistantGeoRuntimeContext geoRuntimeContext,
  ) {
    if (geoRuntimeContext.availableGeoContext.isEmpty) {
      return scope;
    }
    return <String, dynamic>{
      ...scope,
      'availableGeoContext': geoRuntimeContext.availableGeoContext,
      if (geoRuntimeContext.availableGeoContext['cityLabel']
              ?.toString()
              .trim()
              .isNotEmpty ==
          true)
        'city': geoRuntimeContext.availableGeoContext['cityLabel'],
      if (geoRuntimeContext.availableGeoContext['countryCode']
              ?.toString()
              .trim()
              .isNotEmpty ==
          true)
        'countryCode': geoRuntimeContext.availableGeoContext['countryCode'],
      if (geoRuntimeContext.availableGeoContext['countryLabel']
              ?.toString()
              .trim()
              .isNotEmpty ==
          true)
        'countryLabel': geoRuntimeContext.availableGeoContext['countryLabel'],
      if (geoRuntimeContext.availableGeoContext['timezone']
              ?.toString()
              .trim()
              .isNotEmpty ==
          true)
        'timezone': geoRuntimeContext.availableGeoContext['timezone'],
    };
  }

  Future<_AssistantGeoRuntimeContext>
  _resolveAssistantGeoRuntimeContext() async {
    if (_cachedGeoRuntimeContext != null) {
      return _cachedGeoRuntimeContext!;
    }
    try {
      final result = await _localContextTool
          .execute(AssistantToolArguments())
          .timeout(const Duration(seconds: 2));
      final data = result.data?.toDynamicJson() ?? const <String, dynamic>{};
      final geoCatalog = await GeoResolutionCatalog.load();
      final resolved = _AssistantGeoRuntimeContext(
        gpsLocation: _buildGpsLocationFromLocalContext(data),
        availableGeoContext: _buildAvailableGeoContextFromLocalContext(
          data,
          geoCatalog: geoCatalog,
        ),
      );
      _cachedGeoRuntimeContext = resolved;
      return resolved;
    } catch (_) {
      const empty = _AssistantGeoRuntimeContext();
      _cachedGeoRuntimeContext = empty;
      return empty;
    }
  }

  Map<String, dynamic> _buildGpsLocationFromLocalContext(
    Map<String, dynamic> data,
  ) {
    final location =
        (data['location'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final city = (data['city'] as String?)?.trim().isNotEmpty == true
        ? (data['city'] as String).trim()
        : (location['city'] as String?)?.trim() ?? '';
    final latitude = _numValue(location['latitude']);
    final longitude = _numValue(location['longitude']);
    final accuracy = _numValue(location['accuracyM']);
    return <String, dynamic>{
      if (city.isNotEmpty) 'city': city,
      if (latitude != null) 'lat': latitude,
      if (longitude != null) 'lng': longitude,
      if (accuracy != null)
        'locationPrecision': accuracy <= 500 ? 'coarse' : 'approximate',
      'locationTimestamp': DateTime.now().toIso8601String(),
    };
  }

  Map<String, dynamic> _buildAvailableGeoContextFromLocalContext(
    Map<String, dynamic> data, {
    required GeoResolutionCatalog geoCatalog,
  }) {
    final location =
        (data['location'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final device =
        (data['device'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final city = (data['city'] as String?)?.trim().isNotEmpty == true
        ? (data['city'] as String).trim()
        : (location['city'] as String?)?.trim() ?? '';
    final timezone = (device['timezone'] as String?)?.trim() ?? '';
    final locale = (device['locale'] as String?)?.trim() ?? '';
    final countryCode = geoCatalog.resolveCountryCode(
      locale: locale,
      timezone: timezone,
    );
    final latitude = _numValue(location['latitude']);
    final longitude = _numValue(location['longitude']);
    if (city.isEmpty &&
        countryCode.isEmpty &&
        timezone.isEmpty &&
        latitude == null &&
        longitude == null) {
      return const <String, dynamic>{};
    }
    return <String, dynamic>{
      if (countryCode.isNotEmpty) 'countryCode': countryCode,
      if (countryCode.isNotEmpty)
        'countryLabel': geoCatalog.countryLabelFor(countryCode),
      if (city.isNotEmpty) 'cityLabel': city,
      if (latitude != null) 'lat': latitude,
      if (longitude != null) 'lng': longitude,
      if (timezone.isNotEmpty) 'timezone': timezone,
      'source': city.isNotEmpty ? 'device_gps' : 'device_locale',
      'confidence': city.isNotEmpty ? 0.82 : 0.68,
      'capturedAt': DateTime.now().toIso8601String(),
      'privacyTier': city.isNotEmpty ? 'city' : 'region_only',
    };
  }

  double? _numValue(Object? raw) {
    if (raw is num) {
      return raw.toDouble();
    }
    return double.tryParse(raw?.toString().trim() ?? '');
  }

  AssistantJourneyViewModel buildJourneyViewModel({
    required AssistantJourney journey,
    List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
    required bool isRunning,
    AssistantUiUsageStatsViewData usageStats =
        AssistantUiUsageStatsViewData.empty,
    int? elapsedMs,
    AssistantDisplayState displayState = const AssistantDisplayState(),
    RunArtifactsUnderstandingSnapshot understandingSnapshot =
        const RunArtifactsUnderstandingSnapshot(),
    RetrievalProcessingSnapshot retrievalProcessing =
        const RetrievalProcessingSnapshot(),
    RunArtifactsAnswerProcessing answerProcessing =
        const RunArtifactsAnswerProcessing(),
  }) {
    return buildAssistantJourneyViewModel(
      journey: journey,
      processTimeline: processTimeline,
      isRunning: isRunning,
      allowAnswerStage: !isRunning || _answerGateOpen,
      displayState: displayState,
      understandingSnapshot: understandingSnapshot,
      retrievalProcessing: retrievalProcessing,
      answerProcessing: answerProcessing,
      usageStats: usageStats,
      elapsedMs: elapsedMs ?? _currentJourneyElapsedMs,
    );
  }

  @override
  void dispose() {
    _disposed = true;
    _assistantProgressTimer?.cancel();
    super.dispose();
  }

  void _notify() {
    if (!_disposed) {
      notifyListeners();
    }
  }

  void _startAssistantProgress() {
    _assistantProgressTimer?.cancel();
    _assistantProgressStartedAt = DateTime.now();
    _assistantProgressTimer = Timer.periodic(
      const Duration(milliseconds: 500),
      (_) {
        if (_disposed || !_assistantResponding) return;
        final startedAt = _assistantProgressStartedAt;
        if (startedAt == null) return;
        _currentJourneyElapsedMs = DateTime.now()
            .difference(startedAt)
            .inMilliseconds;
        _notify();
      },
    );
  }

  void _stopAssistantProgress() {
    _assistantProgressTimer?.cancel();
    _assistantProgressTimer = null;
    final startedAt = _assistantProgressStartedAt;
    _assistantProgressStartedAt = null;
    if (_disposed || startedAt == null) return;
    _currentJourneyElapsedMs = DateTime.now()
        .difference(startedAt)
        .inMilliseconds;
  }

  AssistantBackend _preferredAssistantBackendOnOpen() {
    final hinted = openContext?.hints['assistantBackend']?.toString() ?? '';
    if (hinted.trim().isNotEmpty) {
      return _resolveAvailableAssistantBackend(parseAssistantBackend(hinted));
    }
    return _resolveAvailableAssistantBackend(AssistantBackend.remote);
  }

  AssistantBackend _resolveAvailableAssistantBackend(AssistantBackend backend) {
    final remoteConfigured = _disposed
        ? _assistantRemoteConfiguredCached
        : _ref.read(assistantRemoteConfiguredProvider);
    _assistantRemoteConfiguredCached = remoteConfigured;
    if (backend == AssistantBackend.remote && !remoteConfigured) {
      return AssistantBackend.local;
    }
    return backend;
  }

  Stream<AssistantRunStreamEvent> _runAssistantStream(
    AssistantRunRequest request,
  ) {
    _assistantBackend = _resolveAvailableAssistantBackend(_assistantBackend);
    switch (_assistantBackend) {
      case AssistantBackend.local:
        return _ref
            .read(localAssistantEntryProvider)
            .runStream(request: request);
      case AssistantBackend.remote:
        return _ref
            .read(remoteAssistantEntryProvider)
            .runStream(request: request);
    }
  }

  String _assistantPhaseLabelFromJourney(
    AssistantJourney journey, {
    List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
    required bool isRunning,
  }) {
    if (isRunning && processTimeline.isEmpty) {
      return UITextConstants.assistantProcessStageUnderstand;
    }
    final viewModel = buildJourneyViewModel(
      journey: journey,
      processTimeline: processTimeline,
      isRunning: isRunning,
    );
    if (isRunning && viewModel.activeStageLabel.isNotEmpty) {
      return viewModel.activeStageLabel;
    }
    if (viewModel.summary.isNotEmpty) {
      return viewModel.summary;
    }
    return UITextConstants.assistantPhaseCompleted;
  }

  bool _shouldOpenAnswerGateForJourney(AssistantJourney journey) {
    return journey.readiness.finalAnswerReady;
  }

  void _consumeJourneyUpdate(AssistantJourney journey) {
    if (_disposed || !_assistantResponding) return;
    final messageId = _activeAssistantStreamingMessageId;
    _currentJourney = journey;
    _assistantPhaseLabel = _assistantPhaseLabelFromJourney(
      journey,
      processTimeline: _currentProcessTimeline,
      isRunning: true,
    );
    if (_shouldOpenAnswerGateForJourney(journey)) {
      _answerGateOpen = true;
    }
    if (messageId != null && messageId.isNotEmpty) {
      final index = _findStreamingAssistantMessageIndex(messageId);
      if (index >= 0) {
        final uiProcessTimeline =
            buildAssistantUiProcessTimelineFromProcessTimeline(
              _currentCanonicalProcessTimeline,
              fallbackJourney: journey,
            );
        _transcriptRows[index] = _patchRow(_transcriptRows[index], {
          assistantJourneyField: journey.toJson(),
          assistantUiProcessTimelineField: uiProcessTimeline.toJson(),
          if (_currentCanonicalProcessTimeline.isNotEmpty)
            assistantProcessTimelineField: _currentCanonicalProcessTimeline
                .map((item) => item.toJson())
                .toList(growable: false),
          'assistantElapsedMs': _currentJourneyElapsedMs,
        });
      }
    }
    _notify();
  }

  void _consumeProcessTimelineUpdate(
    List<ProcessTimelineFrame> processTimeline,
  ) {
    if (_disposed || !_assistantResponding) return;
    final messageId = _activeAssistantStreamingMessageId;
    _currentCanonicalProcessTimeline = rebuildCanonicalProcessTimelineFromVisible(
      visibleProcessTimeline: processTimeline,
      seedProcessTimeline: _currentCanonicalProcessTimeline,
    );
    _currentProcessTimeline = buildVisibleProcessTimeline(
      _currentCanonicalProcessTimeline,
    );
    final retrievalProcessing = _retrievalProcessingFromTimeline(
      _currentCanonicalProcessTimeline,
    );
    if (_hasStructuredRetrievalProcessing(retrievalProcessing)) {
      _currentRetrievalProcessing = retrievalProcessing;
    }
    final understandingSnapshot = _understandingSnapshotFromTimeline(
      _currentCanonicalProcessTimeline,
    );
    if (_hasStructuredUnderstandingSummary(understandingSnapshot)) {
      _currentUnderstandingSnapshot = understandingSnapshot;
    }
    _assistantPhaseLabel = _assistantPhaseLabelFromJourney(
      _currentJourney,
      processTimeline: _currentProcessTimeline,
      isRunning: true,
    );
    if (messageId != null && messageId.isNotEmpty) {
      final index = _findStreamingAssistantMessageIndex(messageId);
      if (index >= 0) {
        final uiProcessTimeline =
            buildAssistantUiProcessTimelineFromProcessTimeline(
              _currentCanonicalProcessTimeline,
              fallbackJourney: _currentJourney,
            );
        final existingRow = _transcriptRows[index];
        final mergedDisplayState = _mergeStreamingDisplayState(
          row: existingRow,
          understandingSnapshot: _currentUnderstandingSnapshot,
        );
        _transcriptRows[index] = _patchRow(existingRow, {
          if (_currentCanonicalProcessTimeline.isNotEmpty)
            assistantProcessTimelineField: _currentCanonicalProcessTimeline
                .map((item) => item.toJson())
                .toList(growable: false),
          if (!uiProcessTimeline.isEmpty)
            assistantUiProcessTimelineField: uiProcessTimeline.toJson(),
          if (_hasStructuredUnderstandingSummary(_currentUnderstandingSnapshot))
            assistantUnderstandingSnapshotField: _currentUnderstandingSnapshot
                .toJson(),
          if (hasAssistantDisplayState(mergedDisplayState))
            assistantDisplayStateField: mergedDisplayState.toJson(),
          'assistantElapsedMs': _currentJourneyElapsedMs,
        });
      }
    }
    _notify();
  }

  RetrievalProcessingSnapshot _retrievalProcessingFromTimeline(
    List<ProcessTimelineFrame> processTimeline,
  ) {
    for (final frame in processTimeline) {
      if (frame.stepId != ProcessStepId.retrievalProcessing) {
        continue;
      }
      if (_hasStructuredRetrievalProcessing(frame.retrievalProcessing)) {
        return frame.retrievalProcessing;
      }
    }
    return const RetrievalProcessingSnapshot();
  }

  RunArtifactsUnderstandingSnapshot _understandingSnapshotFromTimeline(
    List<ProcessTimelineFrame> processTimeline,
  ) {
    for (final frame in processTimeline) {
      if (frame.stepId != ProcessStepId.understanding) {
        continue;
      }
      if (_hasStructuredUnderstandingSummary(frame.understandingSnapshot)) {
        return frame.understandingSnapshot;
      }
    }
    return const RunArtifactsUnderstandingSnapshot();
  }

  bool _hasStructuredRetrievalProcessing(RetrievalProcessingSnapshot snapshot) {
    return snapshot.processingSummary.trim().isNotEmpty ||
        snapshot.selectedKeyPoints.isNotEmpty ||
        snapshot.acceptedReferences.isNotEmpty ||
        snapshot.processedDocumentCount > 0 ||
        snapshot.acceptedDocumentCount > 0;
  }

  bool _hasStructuredUnderstandingSummary(
    RunArtifactsUnderstandingSnapshot snapshot,
  ) {
    return snapshot.userFacingSummary.trim().isNotEmpty ||
        snapshot.concernPoints.any((item) => item.trim().isNotEmpty) ||
        snapshot.resolutionItems.any(
          (item) =>
              item.visibleInUnderstanding &&
              (item.detail.trim().isNotEmpty ||
                  item.resolvedValue.trim().isNotEmpty),
        );
  }

  bool _hasStructuredAnswerProcessing(RunArtifactsAnswerProcessing snapshot) {
    return snapshot.readinessSummary.trim().isNotEmpty ||
        snapshot.keyFacts.isNotEmpty ||
        snapshot.missingDimensions.isNotEmpty ||
        snapshot.retrieveMoreReason.trim().isNotEmpty;
  }

  RunArtifactsAnswerProcessing _answerProcessingFromResponse(
    AssistantRunResponse response,
  ) {
    final direct =
        (response.structuredResponse[assistantAnswerProcessingField] as Map?)
            ?.cast<String, dynamic>();
    if (direct != null && direct.isNotEmpty) {
      return RunArtifactsAnswerProcessing.fromJson(direct);
    }
    return response.runArtifacts?.answerProcessing ??
        const RunArtifactsAnswerProcessing();
  }

  RunArtifactsAnswerProcessing _answerProcessingFromTimeline(
    List<ProcessTimelineFrame> processTimeline,
  ) {
    for (final frame in processTimeline) {
      if (frame.stepId != ProcessStepId.answerOrganization) {
        continue;
      }
      if (_hasStructuredAnswerProcessing(frame.answerProcessing)) {
        return frame.answerProcessing;
      }
    }
    return const RunArtifactsAnswerProcessing();
  }

  _CompletedAssistantCanonicalState _resolveCompletedCanonicalState({
    required AssistantRunResponse response,
    required AssistantJourney journey,
    required AssistantDisplayState completedDisplayState,
    required List<ProcessTimelineFrame> incomingCanonicalProcessTimeline,
    required RunArtifactsAnswerProcessing incomingAnswerProcessing,
    required AssistantTranscriptTimelineRow? existingRow,
    required bool finalAnswerReady,
    required String displayMarkdown,
  }) {
    final carriedProcessTimeline = existingRow == null
        ? const <ProcessTimelineFrame>[]
        : resolveAssistantProcessTimelineFromTranscriptRow(existingRow);
    final carriedUnderstandingSnapshot = existingRow == null
        ? const RunArtifactsUnderstandingSnapshot()
        : resolveAssistantUnderstandingSnapshotFromTranscriptRow(existingRow);
    final carriedRetrievalProcessing = existingRow == null
        ? const RetrievalProcessingSnapshot()
        : resolveAssistantRetrievalProcessingFromTranscriptRow(existingRow);
    final carriedAnswerProcessing = existingRow == null
        ? const RunArtifactsAnswerProcessing()
        : resolveAssistantAnswerProcessingFromTranscriptRow(existingRow);
    final responseUnderstandingSnapshot =
        (response.structuredResponse[assistantUnderstandingSnapshotField]
                as Map?)
            ?.cast<String, dynamic>();
    final mergedUnderstandingSnapshot =
        _mergeUnderstandingSnapshots(<RunArtifactsUnderstandingSnapshot>[
          carriedUnderstandingSnapshot,
          _currentUnderstandingSnapshot,
          _understandingSnapshotFromTimeline(_currentCanonicalProcessTimeline),
          if (responseUnderstandingSnapshot != null &&
              responseUnderstandingSnapshot.isNotEmpty)
            parseRunArtifactsUnderstandingSnapshotFromMap(
              responseUnderstandingSnapshot,
            ),
          _understandingSnapshotFromTimeline(incomingCanonicalProcessTimeline),
        ]);
    final mergedRetrievalProcessing =
        _mergeRetrievalProcessingSnapshots(<RetrievalProcessingSnapshot>[
          carriedRetrievalProcessing,
          _currentRetrievalProcessing,
          _retrievalProcessingFromTimeline(_currentCanonicalProcessTimeline),
          resolveAssistantRetrievalProcessingFromResponse(response),
          _retrievalProcessingFromTimeline(incomingCanonicalProcessTimeline),
        ]);
    final mergedAnswerProcessing =
        _mergeAnswerProcessingSnapshots(<RunArtifactsAnswerProcessing>[
          carriedAnswerProcessing,
          _answerProcessingFromTimeline(_currentCanonicalProcessTimeline),
          incomingAnswerProcessing,
          _answerProcessingFromTimeline(incomingCanonicalProcessTimeline),
        ]);
    final mergedCanonicalProcessTimeline =
        _mergeCompletedCanonicalProcessTimeline(
          carriedProcessTimeline: carriedProcessTimeline,
          currentProcessTimeline: _currentCanonicalProcessTimeline,
          incomingProcessTimeline: incomingCanonicalProcessTimeline,
          understandingSnapshot: mergedUnderstandingSnapshot,
          retrievalProcessing: mergedRetrievalProcessing,
          answerProcessing: mergedAnswerProcessing,
        );
    final carriedDisplayState = existingRow == null
        ? const AssistantDisplayState()
        : resolvePersistedAssistantDisplayStateFromTranscriptRow(existingRow);
    final mergedDisplayState = AssistantDisplayState(
      process: buildAssistantDisplayState(
        explicitState: AssistantDisplayState(
          process: carriedDisplayState.process,
        ),
        processTimeline: mergedCanonicalProcessTimeline,
        understandingSnapshot: mergedUnderstandingSnapshot,
        retrievalProcessing: mergedRetrievalProcessing,
        answerProcessing: mergedAnswerProcessing,
        finalAnswerReady: finalAnswerReady,
      ).process,
      answer: _resolvedCompletedAnswerState(
        completedDisplayState: completedDisplayState,
        displayMarkdown: displayMarkdown,
        existingRow: existingRow,
        fallbackSummary: mergedAnswerProcessing.readinessSummary,
      ),
    );
    return _CompletedAssistantCanonicalState(
      journey: journey,
      canonicalProcessTimeline: mergedCanonicalProcessTimeline,
      visibleProcessTimeline: buildVisibleProcessTimeline(
        mergedCanonicalProcessTimeline,
      ),
      understandingSnapshot: mergedUnderstandingSnapshot,
      retrievalProcessing: mergedRetrievalProcessing,
      answerProcessing: mergedAnswerProcessing,
      displayState: mergedDisplayState,
    );
  }

  List<ProcessTimelineFrame> _mergeCompletedCanonicalProcessTimeline({
    required List<ProcessTimelineFrame> carriedProcessTimeline,
    required List<ProcessTimelineFrame> currentProcessTimeline,
    required List<ProcessTimelineFrame> incomingProcessTimeline,
    required RunArtifactsUnderstandingSnapshot understandingSnapshot,
    required RetrievalProcessingSnapshot retrievalProcessing,
    required RunArtifactsAnswerProcessing answerProcessing,
  }) {
    final mergedByStep = <ProcessStepId, ProcessTimelineFrame>{};

    void absorb(List<ProcessTimelineFrame> timeline) {
      for (final frame in normalizeProcessTimeline(timeline)) {
        final existing = mergedByStep[frame.stepId];
        mergedByStep[frame.stepId] = existing == null
            ? frame
            : _mergeCompletedProcessFrame(existing: existing, incoming: frame);
      }
    }

    absorb(carriedProcessTimeline);
    absorb(currentProcessTimeline);
    absorb(incomingProcessTimeline);
    return buildProcessTimelineFromSnapshots(
      processTimeline: mergedByStep.values.toList(growable: false),
      understandingSnapshot: understandingSnapshot,
      retrievalProcessing: retrievalProcessing,
      answerProcessing: answerProcessing,
    );
  }

  ProcessTimelineFrame _mergeCompletedProcessFrame({
    required ProcessTimelineFrame existing,
    required ProcessTimelineFrame incoming,
  }) {
    return existing.copyWith(
      status: _mergeCompletedProcessStatus(existing.status, incoming.status),
      headline: _preferRicherText(existing.headline, incoming.headline),
      detail: _preferRicherText(existing.detail, incoming.detail),
      references: _mergeRetrievalReferences(
        existing.references,
        incoming.references,
      ),
      understandingSnapshot: _mergeUnderstandingSnapshots(
        <RunArtifactsUnderstandingSnapshot>[
          existing.understandingSnapshot,
          incoming.understandingSnapshot,
        ],
      ),
      retrievalProcessing: _mergeRetrievalProcessingSnapshots(
        <RetrievalProcessingSnapshot>[
          existing.retrievalProcessing,
          incoming.retrievalProcessing,
        ],
      ),
      answerProcessing: _mergeAnswerProcessingSnapshots(
        <RunArtifactsAnswerProcessing>[
          existing.answerProcessing,
          incoming.answerProcessing,
        ],
      ),
    );
  }

  JourneyStageStatus _mergeCompletedProcessStatus(
    JourneyStageStatus existing,
    JourneyStageStatus incoming,
  ) {
    if (incoming == JourneyStageStatus.unknown ||
        incoming == JourneyStageStatus.pending) {
      return existing;
    }
    if (existing == JourneyStageStatus.completed ||
        existing == JourneyStageStatus.blocked) {
      return existing;
    }
    if (incoming == JourneyStageStatus.completed ||
        incoming == JourneyStageStatus.blocked) {
      return incoming;
    }
    if (existing == JourneyStageStatus.pending) {
      return incoming;
    }
    return existing == JourneyStageStatus.active ? existing : incoming;
  }

  RunArtifactsUnderstandingSnapshot _mergeUnderstandingSnapshots(
    Iterable<RunArtifactsUnderstandingSnapshot> candidates,
  ) {
    var merged = const RunArtifactsUnderstandingSnapshot();
    for (final candidate in candidates) {
      if (!_hasStructuredUnderstandingSummary(candidate)) {
        continue;
      }
      if (!_hasStructuredUnderstandingSummary(merged)) {
        merged = candidate;
        continue;
      }
      merged = RunArtifactsUnderstandingSnapshot(
        intentSummary: _preferRicherText(
          merged.intentSummary,
          candidate.intentSummary,
        ),
        userFacingSummary: _preferRicherText(
          merged.userFacingSummary,
          candidate.userFacingSummary,
        ),
        concernPoints: _mergeStringList(
          merged.concernPoints,
          candidate.concernPoints,
        ),
        emotionSignal: _preferRicherText(
          merged.emotionSignal,
          candidate.emotionSignal,
        ),
        resolutionItems: _mergeUnderstandingResolutionItems(
          merged.resolutionItems,
          candidate.resolutionItems,
        ),
        assumptions: _mergeStringList(
          merged.assumptions,
          candidate.assumptions,
        ),
        mismatchSignal: _preferRicherText(
          merged.mismatchSignal,
          candidate.mismatchSignal,
          preferIncoming: true,
        ),
        carryForwardFacts: _mergeStringList(
          merged.carryForwardFacts,
          candidate.carryForwardFacts,
        ),
        discardedAssumptions: _mergeStringList(
          merged.discardedAssumptions,
          candidate.discardedAssumptions,
        ),
      );
    }
    return merged;
  }

  RetrievalProcessingSnapshot _mergeRetrievalProcessingSnapshots(
    Iterable<RetrievalProcessingSnapshot> candidates,
  ) {
    var merged = const RetrievalProcessingSnapshot();
    for (final candidate in candidates) {
      if (!_hasStructuredRetrievalProcessing(candidate)) {
        continue;
      }
      if (!_hasStructuredRetrievalProcessing(merged)) {
        merged = candidate;
        continue;
      }
      merged = RetrievalProcessingSnapshot(
        processedDocumentCount: math.max(
          merged.processedDocumentCount,
          candidate.processedDocumentCount,
        ),
        acceptedDocumentCount: math.max(
          merged.acceptedDocumentCount,
          candidate.acceptedDocumentCount,
        ),
        processingSummary: _preferRicherText(
          merged.processingSummary,
          candidate.processingSummary,
          preferIncoming: true,
        ),
        selectedKeyPoints: _mergeStringList(
          merged.selectedKeyPoints,
          candidate.selectedKeyPoints,
        ),
        expansionReason: _preferRicherText(
          merged.expansionReason,
          candidate.expansionReason,
          preferIncoming: true,
        ),
        acceptedReferences: _mergeRetrievalReferences(
          merged.acceptedReferences,
          candidate.acceptedReferences,
        ),
      );
    }
    return merged;
  }

  RunArtifactsAnswerProcessing _mergeAnswerProcessingSnapshots(
    Iterable<RunArtifactsAnswerProcessing> candidates,
  ) {
    var merged = const RunArtifactsAnswerProcessing();
    for (final candidate in candidates) {
      if (!_hasStructuredAnswerProcessing(candidate)) {
        continue;
      }
      if (!_hasStructuredAnswerProcessing(merged)) {
        merged = candidate;
        continue;
      }
      merged = RunArtifactsAnswerProcessing(
        readinessSummary: _preferRicherText(
          merged.readinessSummary,
          candidate.readinessSummary,
          preferIncoming: true,
        ),
        keyFacts: _mergeStringList(merged.keyFacts, candidate.keyFacts),
        missingDimensions: _mergeStringList(
          merged.missingDimensions,
          candidate.missingDimensions,
        ),
        retrieveMoreReason: _preferRicherText(
          merged.retrieveMoreReason,
          candidate.retrieveMoreReason,
          preferIncoming: true,
        ),
      );
    }
    return merged;
  }

  List<RunArtifactsUnderstandingResolutionItem>
  _mergeUnderstandingResolutionItems(
    List<RunArtifactsUnderstandingResolutionItem> existing,
    List<RunArtifactsUnderstandingResolutionItem> incoming,
  ) {
    final merged = <String, RunArtifactsUnderstandingResolutionItem>{};
    for (final item in <RunArtifactsUnderstandingResolutionItem>[
      ...existing,
      ...incoming,
    ]) {
      final key = <String>[
        item.kind.trim(),
        item.title.trim(),
        item.resolvedValue.trim(),
        item.detail.trim(),
      ].where((part) => part.isNotEmpty).join('|');
      if (key.isEmpty) {
        continue;
      }
      final current = merged[key];
      if (current == null) {
        merged[key] = item;
        continue;
      }
      merged[key] = RunArtifactsUnderstandingResolutionItem(
        kind: _preferRicherText(current.kind, item.kind),
        title: _preferRicherText(current.title, item.title),
        detail: _preferRicherText(
          current.detail,
          item.detail,
          preferIncoming: true,
        ),
        source: _preferRicherText(current.source, item.source),
        originalValue: _preferRicherText(
          current.originalValue,
          item.originalValue,
        ),
        resolvedValue: _preferRicherText(
          current.resolvedValue,
          item.resolvedValue,
        ),
        defaultApplied: current.defaultApplied || item.defaultApplied,
        visibleInUnderstanding:
            current.visibleInUnderstanding || item.visibleInUnderstanding,
      );
    }
    return merged.values.toList(growable: false);
  }

  List<RetrievalProcessingReference> _mergeRetrievalReferences(
    List<RetrievalProcessingReference> existing,
    List<RetrievalProcessingReference> incoming,
  ) {
    final merged = <String, RetrievalProcessingReference>{};
    for (final reference in <RetrievalProcessingReference>[
      ...existing,
      ...incoming,
    ]) {
      final key = reference.url.trim().isNotEmpty
          ? reference.url.trim()
          : '${reference.source.trim()}:${reference.title.trim()}';
      if (key.trim().isEmpty || merged.containsKey(key)) {
        continue;
      }
      merged[key] = reference;
    }
    return merged.values.toList(growable: false);
  }

  List<String> _mergeStringList(List<String> existing, List<String> incoming) {
    final out = <String>[];
    final seen = <String>{};
    for (final item in <String>[...existing, ...incoming]) {
      final normalized = item.trim();
      if (normalized.isEmpty || !seen.add(normalized)) {
        continue;
      }
      out.add(normalized);
    }
    return out;
  }

  String _preferRicherText(
    String existing,
    String incoming, {
    bool preferIncoming = false,
  }) {
    final current = existing.trim();
    final next = incoming.trim();
    if (current.isEmpty) return next;
    if (next.isEmpty) return current;
    if (preferIncoming) return next;
    return next.length >= current.length ? next : current;
  }

  void _resetStreamingAnswerDecoder() {
    _streamingAnswerDecoder.reset();
  }

  String _visibleStreamingAnswerChunk(String rawChunk) {
    return _streamingAnswerDecoder.appendChunk(rawChunk);
  }

  int _findStreamingAssistantMessageIndex(String messageId) {
    if (messageId.isEmpty) return -1;
    final exactIndex = _transcriptRows.indexWhere(
      (item) => item.id == messageId,
    );
    if (exactIndex >= 0) return exactIndex;
    for (var index = _transcriptRows.length - 1; index >= 0; index--) {
      final row = _transcriptRows[index];
      if (row is AssistantAnswerTranscriptRow &&
          row.senderId == AppConceptConstants.assistantSenderId &&
          row.streaming) {
        return index;
      }
    }
    return -1;
  }

  String _mergeStreamingAnswerText({
    required String previous,
    required String incoming,
  }) {
    if (incoming.isEmpty) return previous;
    if (previous.isEmpty) return incoming;
    if (previous.endsWith(incoming) || previous.contains(incoming)) {
      return previous;
    }
    if (incoming.endsWith(previous)) {
      return incoming;
    }
    final maxOverlap = math.min(previous.length, incoming.length);
    for (var overlap = maxOverlap; overlap > 0; overlap--) {
      if (previous.substring(previous.length - overlap) ==
          incoming.substring(0, overlap)) {
        return '$previous${incoming.substring(overlap)}';
      }
    }
    return '$previous$incoming';
  }

  void _appendStreamingAnswerChunk(String chunk) {
    final messageId = _activeAssistantStreamingMessageId;
    if (messageId == null || messageId.isEmpty) return;
    final value = _visibleStreamingAnswerChunk(chunk);
    if (value.isEmpty || _isInternalChunk(value)) {
      return;
    }
    final now = DateTime.now();
    final ts = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
    _ensureTranscriptRowsGrowable();
    final existingIndex = _findStreamingAssistantMessageIndex(messageId);
    if (existingIndex >= 0) {
      final existingRow = _transcriptRows[existingIndex];
      final mergedDisplayState = _mergeStreamingDisplayState(
        row: existingRow,
        streamedAnswerDelta: value,
      );
      final prevMarkdown = renderAnswerBlocksToMarkdown(
        resolvePersistedAssistantDisplayStateFromTranscriptRow(
          existingRow,
        ).answer.blocks,
      );
      final nextMarkdown = renderAnswerBlocksToMarkdown(
        mergedDisplayState.answer.blocks,
      );
      if (nextMarkdown == prevMarkdown) {
        return;
      }
      _transcriptRows[existingIndex] = _patchRow(existingRow, {
        assistantDisplayStateField: mergedDisplayState.toJson(),
      });
      if (nextMarkdown.trim().isNotEmpty) {
        _answerGateOpen = true;
      }
    } else {
      final initialDisplayState = _streamingAnswerDisplayState(value);
      _transcriptRows.add(
        AssistantTranscriptAssembler.assistantStreamingPlaceholderWithInitialDisplayState(
          id: messageId,
          streamTimestamp: ts,
          initialDisplayState: initialDisplayState,
        ),
      );
      if (renderAnswerBlocksToMarkdown(initialDisplayState.answer.blocks)
          .trim()
          .isNotEmpty) {
        _answerGateOpen = true;
      }
    }
    if (_shouldOpenAnswerGateForJourney(_currentJourney)) {
      _answerGateOpen = true;
    }
    _notify();
  }

  AssistantDisplayState _streamingAnswerDisplayState(String markdown) {
    final normalizedMarkdown =
        AssistantDisplayTextResolver.stabilizeStreamingMarkdownCandidate(
          markdown,
        );
    if (normalizedMarkdown.isEmpty) {
      return const AssistantDisplayState();
    }
    return AssistantDisplayState(
      answer: AssistantAnswerDisplayState(
        blocks: <AssistantAnswerDisplayBlock>[
          AssistantAnswerDisplayBlock(
            blockId: 'answer_stream_markdown',
            kind: DisplayBlockKind.markdown,
            body: normalizedMarkdown,
          ),
        ],
      ),
    );
  }

  AssistantDisplayState _mergeStreamingDisplayState({
    required AssistantTranscriptTimelineRow row,
    String streamedAnswerDelta = '',
    RunArtifactsUnderstandingSnapshot? understandingSnapshot,
  }) {
    final current = resolvePersistedAssistantDisplayStateFromTranscriptRow(row);
    final currentMarkdown = renderAnswerBlocksToMarkdown(current.answer.blocks);
    final mergedMarkdown = streamedAnswerDelta.trim().isEmpty
        ? currentMarkdown
        : _mergeStreamingAnswerText(
            previous: currentMarkdown,
            incoming: streamedAnswerDelta,
          );
    final carriedUnderstandingSnapshot =
        resolveAssistantUnderstandingSnapshotFromTranscriptRow(row);
    final effectiveUnderstandingSnapshot =
        _mergeUnderstandingSnapshots(<RunArtifactsUnderstandingSnapshot>[
          carriedUnderstandingSnapshot,
          if (_hasStructuredUnderstandingSummary(_currentUnderstandingSnapshot))
            _currentUnderstandingSnapshot,
          if (understandingSnapshot != null) understandingSnapshot,
        ]);
    final effectiveProcessTimeline = _currentCanonicalProcessTimeline.isNotEmpty
        ? _currentCanonicalProcessTimeline
        : resolveAssistantProcessTimelineFromTranscriptRow(row);
    final effectiveRetrievalProcessing =
        _mergeRetrievalProcessingSnapshots(<RetrievalProcessingSnapshot>[
          resolveAssistantRetrievalProcessingFromTranscriptRow(row),
          if (_hasStructuredRetrievalProcessing(_currentRetrievalProcessing))
            _currentRetrievalProcessing,
        ]);
    final answerState = _streamingAnswerDisplayState(mergedMarkdown).answer;
    final carriedProcess = AssistantProcessDisplayState(
      summary: current.process.summary,
      blocks: current.process.blocks,
      finalAnswerReady: current.process.finalAnswerReady,
    );
    final mergedProcess = buildAssistantDisplayState(
      explicitState: AssistantDisplayState(
        process: carriedProcess,
        answer: current.answer,
      ),
      processTimeline: effectiveProcessTimeline,
      understandingSnapshot: effectiveUnderstandingSnapshot,
      retrievalProcessing: effectiveRetrievalProcessing,
      answerProcessing: resolveAssistantAnswerProcessingFromTranscriptRow(row),
      finalAnswerReady: false,
    ).process;
    return AssistantDisplayState(process: mergedProcess, answer: answerState);
  }

  AssistantAnswerDisplayState _resolvedCompletedAnswerState({
    required AssistantDisplayState completedDisplayState,
    required String displayMarkdown,
    AssistantTranscriptTimelineRow? existingRow,
    String fallbackSummary = '',
  }) {
    final completedSummary = completedDisplayState.answer.summary.trim();
    if (completedDisplayState.answer.blocks.isNotEmpty) {
      return AssistantAnswerDisplayState(
        summary: completedSummary.isNotEmpty
            ? completedSummary
            : fallbackSummary.trim(),
        blocks: completedDisplayState.answer.blocks,
      );
    }
    final carriedAnswer = existingRow == null
        ? const AssistantAnswerDisplayState()
        : resolvePersistedAssistantDisplayStateFromTranscriptRow(existingRow)
              .answer;
    final carriedSummary = carriedAnswer.summary.trim();
    final resolvedSummary = completedSummary.isNotEmpty
        ? completedSummary
        : (carriedSummary.isNotEmpty ? carriedSummary : fallbackSummary.trim());
    if (carriedAnswer.blocks.isNotEmpty) {
      return AssistantAnswerDisplayState(
        summary: resolvedSummary,
        blocks: carriedAnswer.blocks,
      );
    }
    final fallback = _streamingAnswerDisplayState(displayMarkdown).answer;
    return AssistantAnswerDisplayState(
      summary: resolvedSummary,
      blocks: fallback.blocks,
    );
  }

  AssistantTranscriptTimelineRow _clearStreamingAnswerState(
    AssistantTranscriptTimelineRow row,
  ) => _patchRow(row, {'streamFinalAnswer': ''});

  Map<String, dynamic> _withDisplayOverrides(
    Map<String, dynamic> runArtifacts, {
    required String displayMarkdown,
    required String displayPlainText,
    AssistantDisplayState displayState = const AssistantDisplayState(),
    AssistantJourney journey = const AssistantJourney(),
    List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
    RunArtifactsUnderstandingSnapshot understandingSnapshot =
        const RunArtifactsUnderstandingSnapshot(),
    RetrievalProcessingSnapshot retrievalProcessing =
        const RetrievalProcessingSnapshot(),
    RunArtifactsAnswerProcessing answerProcessing =
        const RunArtifactsAnswerProcessing(),
  }) {
    return <String, dynamic>{
      ...runArtifacts,
      assistantDisplayMarkdownField:
          AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
            displayMarkdown,
            allowJsonExtraction: false,
          ),
      assistantDisplayPlainTextField:
          AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
            displayPlainText,
            allowJsonExtraction: false,
          ),
      if (!journey.isEmpty) assistantJourneyField: journey.toJson(),
      if (processTimeline.isNotEmpty)
        assistantProcessTimelineField: processTimeline
            .map((item) => item.toJson())
            .toList(growable: false),
      if (_hasStructuredUnderstandingSummary(understandingSnapshot))
        assistantUnderstandingSnapshotField: understandingSnapshot.toJson(),
      if (_hasStructuredRetrievalProcessing(retrievalProcessing))
        assistantRetrievalProcessingField: retrievalProcessing.toJson(),
      if (_hasStructuredAnswerProcessing(answerProcessing))
        assistantAnswerProcessingField: answerProcessing.toJson(),
      if (hasAssistantDisplayState(displayState))
        assistantDisplayStateField: displayState.toJson(),
    };
  }

  String _firstCompletedDisplayCandidate(Iterable<String> candidates) {
    for (final candidate in candidates) {
      final sanitized = _sanitizeCompletedDisplayCandidate(candidate);
      if (sanitized.isNotEmpty) {
        return sanitized;
      }
    }
    return '';
  }

  String _sanitizeCompletedDisplayCandidate(
    String raw, {
    bool allowJsonExtraction = true,
  }) {
    final text =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          raw,
          allowJsonExtraction: allowJsonExtraction,
        );
    if (text.isEmpty) return '';
    if (_isInternalChunk(text) ||
        _containsInternalDisplayFragment(text) ||
        AssistantContentFilters.isProgressPlaceholder(text) ||
        AssistantContentFilters.isDegradedText(text) ||
        AssistantContentFilters.isJsonEnvelope(text)) {
      return '';
    }
    return text;
  }

  bool _containsInternalDisplayFragment(String value) {
    final text = value.trim();
    if (text.isEmpty) return false;
    return AssistantContentFilters.isJsonEnvelope(text) ||
        AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
          text,
        );
  }

  int _usageInt(Object? value) {
    if (value is num) {
      final n = value.toInt();
      return n < 0 ? 0 : n;
    }
    final parsed = int.tryParse(value?.toString() ?? '');
    if (parsed == null || parsed < 0) return 0;
    return parsed;
  }

  Map<String, dynamic> _buildConversationCumulativeUsageStats({
    required Map<String, dynamic> runUsageStats,
    String? excludeMessageId,
  }) {
    final currentRunCalls = _usageInt(
      runUsageStats['runModelCallCount'] ?? runUsageStats['modelCallCount'],
    );
    final currentRunTokens = _usageInt(
      runUsageStats['runTotalTokens'] ?? runUsageStats['totalTokens'],
    );
    final currentRunMaxTokens = _usageInt(
      runUsageStats['runMaxTokensPerCall'] ?? runUsageStats['maxTokensPerCall'],
    );
    final currentRunLedger =
        (runUsageStats['usageLedger'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];

    var prevCalls = 0;
    var prevTokens = 0;
    var prevMaxTokens = 0;
    final cumulativeLedger = <Map<String, dynamic>>[];
    for (final row in _transcriptRows) {
      if (row is! AssistantAnswerTranscriptRow) continue;
      if (row.senderId != AppConceptConstants.assistantSenderId) continue;
      if (excludeMessageId != null && row.id == excludeMessageId) continue;
      final usageStats = row.uiUsageStats;
      if (usageStats.isEmpty) continue;
      prevCalls += _usageInt(
        usageStats['runModelCallCount'] ?? usageStats['modelCallCount'],
      );
      prevTokens += _usageInt(
        usageStats['runTotalTokens'] ?? usageStats['totalTokens'],
      );
      final maxTokens = _usageInt(
        usageStats['runMaxTokensPerCall'] ?? usageStats['maxTokensPerCall'],
      );
      if (maxTokens > prevMaxTokens) prevMaxTokens = maxTokens;
      final messageLedger =
          ((usageStats['runUsageLedger'] ?? usageStats['usageLedger']) as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      cumulativeLedger.addAll(messageLedger);
    }
    cumulativeLedger.addAll(currentRunLedger);

    final cumulativeCalls = prevCalls + currentRunCalls;
    final cumulativeTokens = prevTokens + currentRunTokens;
    final cumulativeMaxTokens = math.max(prevMaxTokens, currentRunMaxTokens);

    return <String, dynamic>{
      ...runUsageStats,
      'runModelCallCount': currentRunCalls,
      'runTotalTokens': currentRunTokens,
      'runMaxTokensPerCall': currentRunMaxTokens,
      'runUsageLedger': currentRunLedger,
      'sessionUsageStats': <String, dynamic>{
        'modelCallCount': cumulativeCalls,
        'totalTokens': cumulativeTokens,
        'maxTokensPerCall': cumulativeMaxTokens,
        'usageLedger': cumulativeLedger,
      },
      'cumulativeModelCallCount': cumulativeCalls,
      'cumulativeTotalTokens': cumulativeTokens,
      'cumulativeMaxTokensPerCall': cumulativeMaxTokens,
      'cumulativeUsageLedger': cumulativeLedger,
      'modelCallCount': currentRunCalls,
      'totalTokens': currentRunTokens,
      'maxTokensPerCall': currentRunMaxTokens,
    };
  }

  static final RegExp _xmlToolCallTagRe = RegExp(
    r'<tool_call>[\s\S]*?</tool_call>|'
    r'<function=[^>]+>[\s\S]*?</function>|'
    r'<tool_call>|</tool_call>|'
    r'<function=[^>]*>|</function>|'
    r'<parameter=[^>]*>[\s\S]*?</parameter>|'
    r'</?parameter[^>]*>',
  );
  static final RegExp _xmlToolCallOpenRe = RegExp(r'<tool_call>|<function=');

  bool _containsXmlToolCall(String text) => _xmlToolCallOpenRe.hasMatch(text);

  String _stripXmlToolCallsPreservingWhitespace(String text) =>
      text.replaceAll(_xmlToolCallTagRe, '');

  String _stripXmlToolCalls(String text) =>
      _stripXmlToolCallsPreservingWhitespace(text).trim();

  String _assistantDeviceProfileByWidth(double width) {
    if (width >= 600) return 'pc';
    if (width >= 360) return 'tablet';
    return 'mobile';
  }

  String _assistantHistoryContentForModel(Map<String, dynamic> message) {
    final candidates = <String>[
      (message['displayPlainText'] ?? '').toString(),
      (message['displayMarkdown'] ?? '').toString(),
      (message['content'] ?? '').toString(),
    ];
    for (final candidate in candidates) {
      final sanitized = _sanitizeAssistantHistoryContent(candidate);
      if (sanitized.isNotEmpty) return sanitized;
    }
    return '';
  }

  String _sanitizeAssistantHistoryContent(String raw) {
    final sanitized =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(raw);
    if (sanitized.isEmpty) return '';
    if (_isInternalChunk(sanitized)) return '';
    if (AssistantContentFilters.isDegradedText(sanitized)) return '';
    if (AssistantContentFilters.isProgressPlaceholder(sanitized)) return '';
    if (AssistantDisplayTextResolver.containsUnsafeDisplayProtocolLeak(
      sanitized,
    )) {
      return '';
    }
    return sanitized;
  }

  Map<String, dynamic> _latestAssistantDialogueState() {
    for (var i = _transcriptRows.length - 1; i >= 0; i--) {
      final row = _transcriptRows[i];
      if (row is! AssistantAnswerTranscriptRow) continue;
      if (row.senderId != AppConceptConstants.assistantSenderId) continue;
      if (row.dialogueState.isNotEmpty) return row.dialogueState;
    }
    return const <String, dynamic>{};
  }

  RunArtifacts? _latestAssistantRunArtifacts() {
    for (var i = _transcriptRows.length - 1; i >= 0; i--) {
      final row = _transcriptRows[i];
      if (row is! AssistantAnswerTranscriptRow) continue;
      if (row.senderId != AppConceptConstants.assistantSenderId) continue;
      final raw = row.runArtifacts;
      if (raw.isEmpty) continue;
      try {
        return parseRunArtifacts(raw);
      } catch (_) {
        continue;
      }
    }
    return null;
  }

  Map<String, dynamic> _responseRunArtifactsMap(AssistantRunResponse response) {
    final structured =
        (response.structuredResponse['runArtifacts'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (structured.isNotEmpty) {
      return structured;
    }
    return response.runArtifacts?.toJson() ?? const <String, dynamic>{};
  }

  AssistantDisplayProjection? _assistantTurnProjectionFromMap(
    Map<String, dynamic> payload,
  ) {
    if (payload.isEmpty) return null;
    final turn = tryParseAssistantTurnOutput(payload);
    if (turn == null) return null;
    final projection = AssistantDisplayTextResolver.projectTurn(
      AssistantDisplayTextResolver.normalizeTurn(turn),
    );
    if (!projection.hasRenderableContent) return null;
    return projection;
  }

  AssistantDisplayProjection? _assistantTurnProjectionFromRawText(String raw) {
    final markdown =
        AssistantDisplayTextResolver.extractDisplayMarkdownFromStructuredText(
          raw,
        ).trim();
    final plainText =
        AssistantDisplayTextResolver.extractPlainTextFromStructuredText(
          raw,
        ).trim();
    if (markdown.isEmpty && plainText.isEmpty) return null;
    final effectiveMarkdown = markdown.isNotEmpty ? markdown : plainText;
    final effectivePlainText = plainText.isNotEmpty
        ? plainText
        : AssistantDisplayTextResolver.stripMarkdown(effectiveMarkdown).trim();
    return AssistantDisplayProjection(
      markdown: effectiveMarkdown,
      plainText: effectivePlainText,
      summary: effectivePlainText.isNotEmpty
          ? effectivePlainText
          : effectiveMarkdown,
    );
  }

  AssistantDisplayProjection? _structuredResponseAssistantTurnProjection(
    AssistantRunResponse response,
  ) {
    final topLevel = _assistantTurnProjectionFromMap(
      response.structuredResponse,
    );
    if (topLevel != null) return topLevel;
    final nested =
        (response.structuredResponse['answerPayload'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return _assistantTurnProjectionFromMap(nested);
  }

  String _responseArtifactDisplayMarkdown(AssistantRunResponse response) {
    final displayState = resolveAssistantDisplayStateFromRunResponse(response);
    if (displayState.answer.blocks.isNotEmpty) {
      final markdown = renderAnswerBlocksToMarkdown(displayState.answer.blocks);
      if (markdown.isNotEmpty) {
        return _firstCompletedDisplayCandidate(<String>[markdown]);
      }
    }
    final projection = _structuredResponseAssistantTurnProjection(response);
    if (projection != null) {
      return _firstCompletedDisplayCandidate(<String>[
        projection.markdown,
        projection.plainText,
      ]);
    }
    final runArtifacts = _responseRunArtifactsMap(response);
    final normalized =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          (runArtifacts['displayMarkdown'] as String?)?.trim() ?? '',
          allowJsonExtraction: false,
        );
    if (normalized.isNotEmpty) {
      return normalized;
    }
    final normalizedPlain =
        AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
          (runArtifacts['displayPlainText'] as String?)?.trim() ?? '',
          allowJsonExtraction: false,
        );
    if (normalizedPlain.isNotEmpty) {
      return normalizedPlain;
    }
    final rawProjection = _assistantTurnProjectionFromRawText(
      response.finalText,
    );
    if (rawProjection != null) {
      return _firstCompletedDisplayCandidate(<String>[
        rawProjection.markdown,
        rawProjection.plainText,
      ]);
    }
    return (runArtifacts['displayMarkdown'] as String?)?.trim() ?? '';
  }

  String _responseArtifactDisplayPlainText(AssistantRunResponse response) {
    final displayState = resolveAssistantDisplayStateFromRunResponse(response);
    if (displayState.answer.blocks.isNotEmpty) {
      final plain = renderAnswerBlocksToPlainText(displayState.answer.blocks);
      if (plain.isNotEmpty) {
        return AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
          plain,
          allowJsonExtraction: false,
        );
      }
    }
    final projection = _structuredResponseAssistantTurnProjection(response);
    if (projection != null) {
      final effectivePlainText = projection.plainText.trim().isNotEmpty
          ? projection.plainText
          : AssistantDisplayTextResolver.stripMarkdown(projection.markdown);
      return AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
        effectivePlainText,
        allowJsonExtraction: false,
      );
    }
    final runArtifacts = _responseRunArtifactsMap(response);
    final normalizedPlain =
        AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
          (runArtifacts['displayPlainText'] as String?)?.trim() ?? '',
          allowJsonExtraction: false,
        );
    if (normalizedPlain.isNotEmpty) {
      return normalizedPlain;
    }
    final normalizedMarkdown =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          (runArtifacts['displayMarkdown'] as String?)?.trim() ?? '',
          allowJsonExtraction: false,
        );
    if (normalizedMarkdown.isNotEmpty) {
      return AssistantDisplayTextResolver.stripMarkdown(
        normalizedMarkdown,
      ).trim();
    }
    final rawProjection = _assistantTurnProjectionFromRawText(
      response.finalText,
    );
    if (rawProjection != null) {
      final effectivePlainText = rawProjection.plainText.trim().isNotEmpty
          ? rawProjection.plainText
          : AssistantDisplayTextResolver.stripMarkdown(rawProjection.markdown);
      return AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
        effectivePlainText,
        allowJsonExtraction: false,
      );
    }
    return (runArtifacts['displayPlainText'] as String?)?.trim() ?? '';
  }

  String _resolveAssistantDisplayText(AssistantRunResponse response) {
    final displayText = _firstCompletedDisplayCandidate(<String>[
      _responseArtifactDisplayMarkdown(response),
      _responseArtifactDisplayPlainText(response),
    ]);
    if (displayText.isNotEmpty) {
      return displayText;
    }
    final actionFallback = resolveActionLikeCompletedFallback(response);
    if (actionFallback.isNotEmpty) {
      return actionFallback;
    }
    return '助手未生成有效回答，请重试。';
  }

  String _resolveAssistantDisplayPlainText(AssistantRunResponse response) {
    final artifactPlain =
        AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
          _responseArtifactDisplayPlainText(response),
          allowJsonExtraction: false,
        );
    if (artifactPlain.isNotEmpty) {
      return artifactPlain;
    }
    final artifactMarkdown =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          _responseArtifactDisplayMarkdown(response),
          allowJsonExtraction: false,
        );
    if (artifactMarkdown.isNotEmpty) {
      return AssistantDisplayTextResolver.stripMarkdown(artifactMarkdown);
    }
    return '';
  }

  Map<String, dynamic> _buildAssistantPersistedTurnFieldsForResponse({
    required AssistantRunResponse response,
    required AssistantJourney journey,
    required List<ProcessTimelineFrame> processTimeline,
    required String displayMarkdown,
    required String displayPlainText,
    required int elapsedMs,
    AssistantDisplayState? displayState,
    RunArtifactsUnderstandingSnapshot? understandingSnapshot,
    RetrievalProcessingSnapshot? retrievalProcessing,
    RunArtifactsAnswerProcessing? answerProcessing,
  }) {
    final runArtifacts = response.runArtifacts;
    final resolvedDisplayState =
        displayState ?? resolveAssistantDisplayStateFromRunResponse(response);
    final directUnderstandingSnapshot =
        (response.structuredResponse[assistantUnderstandingSnapshotField]
                as Map?)
            ?.cast<String, dynamic>();
    final resolvedUnderstandingSnapshot =
        understandingSnapshot ??
        (directUnderstandingSnapshot != null &&
                directUnderstandingSnapshot.isNotEmpty
            ? parseRunArtifactsUnderstandingSnapshotFromMap(
                directUnderstandingSnapshot,
              )
            : (runArtifacts?.understandingSnapshot ??
                  const RunArtifactsUnderstandingSnapshot()));
    final resolvedRetrievalProcessing =
        retrievalProcessing ??
        resolveAssistantRetrievalProcessingFromResponse(response);
    final resolvedAnswerProcessing =
        answerProcessing ?? _answerProcessingFromResponse(response);
    return buildPersistedAssistantTurnFields(
      journey: journey,
      processTimeline: processTimeline,
      displayMarkdown: displayMarkdown,
      displayPlainText: displayPlainText,
      displayState: resolvedDisplayState.toJson(),
      followupPrompt: resolveAssistantFollowupPromptFromResponse(response),
      actionHints: resolveAssistantActionHintsFromResponse(response),
      elapsedMs: elapsedMs,
      understandingSnapshot: resolvedUnderstandingSnapshot.toJson(),
      answerProcessing: resolvedAnswerProcessing.toJson(),
      historicalThinkingSnapshot:
          (response.structuredResponse[assistantHistoricalThinkingSnapshotField]
                  as Map?)
              ?.cast<String, dynamic>() ??
          runArtifacts?.historicalThinkingSnapshot.toJson() ??
          const <String, dynamic>{},
      retrievalProcessing: resolvedRetrievalProcessing.toJson(),
      providerReasoningContinuation:
          (response.structuredResponse[assistantProviderReasoningContinuationField]
                  as String?)
              ?.trim() ??
          '',
    );
  }

  AssistantJourney _persistableAssistantJourney({
    required AssistantRunResponse response,
    required AssistantJourney journey,
  }) {
    final gate = response.answerGateDecision;
    final readiness = journey.readiness;
    final resolvedNextAction = gate.nextAction.trim().isNotEmpty
        ? parseAssistantNextAction(gate.nextAction)
        : readiness.nextAction;
    final resolvedEligibility = gate.answerEligibility.trim().isNotEmpty
        ? parseAnswerEligibility(gate.answerEligibility)
        : readiness.answerEligibility;
    if (readiness.finalAnswerReady == gate.finalAnswerReady &&
        readiness.nextAction == resolvedNextAction &&
        readiness.answerEligibility == resolvedEligibility) {
      return journey;
    }
    return AssistantJourney(
      stages: journey.stages,
      entries: journey.entries,
      summary: journey.summary,
      referenceSummary: journey.referenceSummary,
      readiness: AssistantJourneyReadiness(
        nextAction: resolvedNextAction,
        finalAnswerMode: readiness.finalAnswerMode,
        answerEligibility: resolvedEligibility,
        finalAnswerReady: gate.finalAnswerReady,
        clarificationNeeded: readiness.clarificationNeeded,
        needExpansion: readiness.needExpansion,
      ),
    );
  }

  bool _responseMarksFinalAnswerReady(AssistantRunResponse response) {
    return response.answerGateDecision.finalAnswerReady;
  }

  bool _isInternalChunk(String value) {
    final text = value.trim();
    if (text.isEmpty) return false;
    if (text == '</think>' || text == '<think>') return true;
    if (AssistantContentFilters.isJsonEnvelope(text)) return true;
    if (AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
      text,
    )) {
      return true;
    }
    if (_containsXmlToolCall(text)) {
      final stripped = _stripXmlToolCalls(text);
      if (stripped.isEmpty) return true;
    }
    if (text.startsWith('{') || text.startsWith('```')) {
      final parsed = LlmResponseParser.parse(text);
      if (parsed.ok) return true;
    }
    return false;
  }

  String _assistantSourceToPageType(AssistantSource? source) {
    switch (source) {
      case AssistantSource.discovery:
        return 'discovery';
      case AssistantSource.circles:
        return 'circles';
      case AssistantSource.article:
      case AssistantSource.profile:
        return 'home';
      case AssistantSource.chat:
        return 'chat';
      case AssistantSource.create:
        return 'create';
      case AssistantSource.search:
        return 'search';
      case null:
        return 'chat';
    }
  }

  void _storeAssistantReplayRecord({
    required String messageId,
    required String query,
    required AssistantRunResponse response,
  }) {
    final replayPayload = _extractReplayPayload(response.traces);
    final record = AssistantReplayRecordFactory.build(
      messageId: messageId,
      query: query,
      response: response,
      replayPayload: replayPayload,
      runArtifactsMap: _responseRunArtifactsMap(response),
      answerText: _resolveAssistantDisplayText(response),
      displayPlainText: _resolveAssistantDisplayPlainText(response),
    );
    _assistantReplayByMessageId[messageId] = record;
    _assistantReplayRecords.insert(0, record);
    if (_assistantReplayRecords.length > 40) {
      _assistantReplayRecords.removeRange(40, _assistantReplayRecords.length);
    }
  }

  Map<String, dynamic> _extractReplayPayload(List<AssistantTraceEvent> traces) {
    return AssistantReplayTracePayload.fromTraces(traces).toPayloadMap();
  }

  String _rewriteUserLabel(RewriteMode mode) {
    switch (mode) {
      case RewriteMode.regenerate:
        return '请重新生成回答';
      case RewriteMode.concise:
        return '请给我更简洁的版本';
      case RewriteMode.detailed:
        return '请给我更详细的版本';
      case RewriteMode.casual:
        return '请用更口语化的方式回答';
      case RewriteMode.deepThink:
        return '请进行深度思考并重新回答';
    }
  }
}

class _AssistantGeoRuntimeContext {
  const _AssistantGeoRuntimeContext({
    this.gpsLocation = const <String, dynamic>{},
    this.availableGeoContext = const <String, dynamic>{},
  });

  final Map<String, dynamic> gpsLocation;
  final Map<String, dynamic> availableGeoContext;
}

class _CompletedAssistantCanonicalState {
  const _CompletedAssistantCanonicalState({
    required this.journey,
    required this.canonicalProcessTimeline,
    required this.visibleProcessTimeline,
    required this.understandingSnapshot,
    required this.retrievalProcessing,
    required this.answerProcessing,
    required this.displayState,
  });

  final AssistantJourney journey;
  final List<ProcessTimelineFrame> canonicalProcessTimeline;
  final List<ProcessTimelineFrame> visibleProcessTimeline;
  final RunArtifactsUnderstandingSnapshot understandingSnapshot;
  final RetrievalProcessingSnapshot retrievalProcessing;
  final RunArtifactsAnswerProcessing answerProcessing;
  final AssistantDisplayState displayState;
}
