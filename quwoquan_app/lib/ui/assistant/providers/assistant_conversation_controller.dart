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
import 'package:quwoquan_app/assistant/orchestration/orchestration.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
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

  final Map<String, AssistantReplayRecord> _assistantReplayByMessageId =
      <String, AssistantReplayRecord>{};
  final List<AssistantReplayRecord> _assistantReplayRecords =
      <AssistantReplayRecord>[];
  final Map<String, String> _assistantFeedbackStatusByMessageId =
      <String, String>{};

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

  Map<String, dynamic> _rowToMap(AssistantTranscriptTimelineRow row) =>
      PersistedTimelineTurnCodec.encode(row);

  AssistantTranscriptTimelineRow _mapToRow(Map<String, dynamic> m) =>
      PersistedTimelineTurnCodec.decode(m);

  AssistantTranscriptTimelineRow _patchRow(
    AssistantTranscriptTimelineRow row,
    Map<String, dynamic> patch,
  ) =>
      patchTranscriptRowWithMapMerge(row, patch);

  bool _rowEligibleForAssistantRun(AssistantTranscriptTimelineRow r) {
    final m = _rowToMap(r);
    if ((m['type'] as String? ?? 'text') != 'text') return false;
    if (m['streaming'] == true) return false;
    if (m['isError'] == true) return false;
    if (m['isSelf'] == true) {
      return ((m['content'] as String?)?.trim().isNotEmpty ?? false);
    }
    return _assistantHistoryContentForModel(m).trim().isNotEmpty;
  }

  AssistantRunMessage? _rowAsRunMessage(AssistantTranscriptTimelineRow r) {
    final m = _rowToMap(r);
    final isUser = m['isSelf'] == true;
    final content = isUser
        ? ((m['content'] as String?) ?? '')
        : _assistantHistoryContentForModel(m);
    if (content.trim().isEmpty) return null;
    return AssistantRunMessage(
      role: isUser ? 'user' : 'assistant',
      content: content,
    );
  }

  void _ensureTranscriptRowsGrowable() {
    _transcriptRows = List<AssistantTranscriptTimelineRow>.from(_transcriptRows);
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
    _transcriptRows = List<AssistantTranscriptTimelineRow>.from(<AssistantTranscriptTimelineRow>[
      ...olderChunk,
      ..._transcriptRows,
    ]);
    _assistantHiddenHistory =
        List<AssistantTranscriptTimelineRow>.from(remainingHidden);
    _assistantLoadingOlderHistory = false;
    _showAssistantHistoryPeek = remainingHidden.isNotEmpty;
    _notify();
  }

  Future<bool> syncSessionInfo() async {
    if (_assistantBackend != AssistantBackend.local) return false;
    final sessions = await _ref.read(assistantGatewayProvider).listSessions();
    if (_disposed || sessions.isEmpty) return false;
    final namespacedSessions = sessions
        .where((item) {
          final sessionId = (item['sessionId'] ?? '').toString();
          return isAssistantSessionForBackend(
            sessionId,
            AssistantBackend.local,
          );
        })
        .toList(growable: false);
    if (namespacedSessions.isEmpty) return false;
    Map<String, dynamic> active = namespacedSessions.first;
    for (final item in namespacedSessions) {
      if (item['isActive'] == true) {
        active = item;
        break;
      }
    }
    final nextSessionId = (active['sessionId'] ?? '').toString();
    final nextTopic = (active['topicTitle'] as String?)?.trim();
    if (nextSessionId.isEmpty) return false;
    _assistantBackend = assistantBackendForSessionId(nextSessionId);
    _assistantRuntimeSessionId = nextSessionId;
    _assistantTopicTitle = (nextTopic?.isNotEmpty ?? false)
        ? nextTopic!
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
    final messages =
        (detail['messages'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final now = DateTime.now();
    var serial = 0;
    final mapped = messages
        .map((item) {
          final isUser = (item['role'] ?? '').toString() == 'user';
          final normalizedContent = isUser
              ? (item['content'] ?? '').toString()
              : _assistantHistoryContentForModel(item);
          final hasPersistedTurn =
              !isUser &&
              (!resolvePersistedAssistantTimeline(item).isEmpty ||
                  isCanonicalPersistedAssistantTurnMessage(item));
          if (!isUser &&
              normalizedContent.trim().isEmpty &&
              !hasPersistedTurn) {
            return null;
          }
          serial += 1;
          return <String, dynamic>{
            ...item,
            'id': 'assistant_${sessionId}_$serial',
            'conversationId': AppConceptConstants.assistantConversationId,
            'type': 'text',
            'content': normalizedContent,
            'senderId': isUser
                ? _currentProfileSubjectId()
                : AppConceptConstants.assistantSenderId,
            'senderName': isUser ? '我' : AppConceptConstants.assistantLabel,
            'senderAvatar': '',
            'timestamp': '${now.hour}:${now.minute.toString().padLeft(2, '0')}',
            'isRead': true,
            'isSelf': isUser,
          };
        })
        .whereType<Map<String, dynamic>>()
        .toList(growable: false);
    final splitIndex = math.max(0, mapped.length - _assistantHistoryPageSize);
    final hiddenHistory = mapped.sublist(0, splitIndex);
    final visibleMessages = mapped.sublist(splitIndex);
    _assistantHiddenHistory = hiddenHistory
        .map(_mapToRow)
        .toList(growable: false);
    _assistantLoadingOlderHistory = false;
    _showAssistantHistoryPeek = hiddenHistory.isNotEmpty;
    _transcriptRows =
        visibleMessages.map(_mapToRow).toList(growable: false);
    final topic = (detail['topicTitle'] as String?)?.trim();
    if (topic != null && topic.isNotEmpty) {
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
      final contextScope = _withActivePersonaContextScope(
        buildContextScope(),
        activeContext: activeContext,
      );
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
        contextScopeHint: contextScope,
        privacyProfile: 'default',
        privacyPolicy:
            (contextScope['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
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
      final displayText = _resolveAssistantDisplayText(runResponse);
      final displayPlainText = _resolveAssistantDisplayPlainText(runResponse);
      final artifactMarkdown = _responseArtifactDisplayMarkdown(runResponse);
      final displayMarkdown =
          AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
            artifactMarkdown.isNotEmpty ? artifactMarkdown : displayText,
            allowJsonExtraction: false,
          );
      _resetStreamingAnswerDecoder();
      final resolvedSessionId =
          (runResponse.structuredResponse['effectiveSessionId'] as String?)
              ?.trim() ??
          '';
      final activeSessionId =
          isAssistantSessionForBackend(resolvedSessionId, _assistantBackend)
          ? resolvedSessionId
          : effectiveAssistantSessionId;
      final activeTopicTitle =
          (runResponse.structuredResponse['activeTopicTitle'] as String?)
              ?.trim();
      final dialogueRuntime =
          (runResponse.structuredResponse['dialogueRuntime'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final elapsedMs = DateTime.now().difference(runStartedAt).inMilliseconds;
      final replyTime = ChatTimeFormatter.format(DateTime.now());
      final assistantMessageId =
          'assistant_${DateTime.now().millisecondsSinceEpoch}';
      final uiReferences =
          (runResponse.structuredResponse['uiReferences'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final uiActions =
          (runResponse.structuredResponse['uiActions'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final uiUsageStats = _buildConversationCumulativeUsageStats(
        runUsageStats:
            (runResponse.structuredResponse['uiUsageStats'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{},
        excludeMessageId: streamingAssistantMessageId,
      );
      final resolvedJourney = resolveAssistantJourneyFromResponse(runResponse);
      final resolvedCanonicalProcessTimeline =
          resolveAssistantProcessTimelineFromRunResponse(runResponse);
      final resolvedProcessTimeline = buildVisibleProcessTimeline(
        resolvedCanonicalProcessTimeline,
      );
      final effectiveJourney = _persistableAssistantJourney(
        response: runResponse,
        journey: resolvedJourney.isEmpty ? _currentJourney : resolvedJourney,
      );
      final retrievalProcessing =
          resolveAssistantRetrievalProcessingFromResponse(runResponse);
      final understandingSnapshot =
          (runResponse.structuredResponse[assistantUnderstandingSnapshotField]
                  as Map?)
              ?.cast<String, dynamic>();
      if (_disposed) return;
      _currentJourney = effectiveJourney;
      _currentCanonicalProcessTimeline =
          resolvedCanonicalProcessTimeline.isNotEmpty
          ? resolvedCanonicalProcessTimeline
          : _currentCanonicalProcessTimeline;
      _currentProcessTimeline = resolvedProcessTimeline.isNotEmpty
          ? resolvedProcessTimeline
          : _currentProcessTimeline;
      _currentRetrievalProcessing = retrievalProcessing;
      _currentUnderstandingSnapshot =
          understandingSnapshot != null && understandingSnapshot.isNotEmpty
          ? RunArtifactsUnderstandingSnapshot.fromJson(understandingSnapshot)
          : _understandingSnapshotFromTimeline(
              _currentCanonicalProcessTimeline,
            );
      _currentJourneyElapsedMs = elapsedMs;
      final persistedTurnFields = _buildAssistantPersistedTurnFieldsForResponse(
        response: runResponse,
        journey: effectiveJourney,
        processTimeline: _currentCanonicalProcessTimeline,
        displayMarkdown: displayMarkdown,
        displayPlainText: displayPlainText,
        elapsedMs: elapsedMs,
      );
      _ensureTranscriptRowsGrowable();
      final existingIndex = _findStreamingAssistantMessageIndex(
        streamingAssistantMessageId,
      );
      if (existingIndex >= 0) {
        final clearedRow = _clearStreamingAnswerState(
          _transcriptRows[existingIndex],
        );
        final completedDisplayState =
            resolveAssistantDisplayStateFromRunResponse(runResponse);
        final responseDisplayState = AssistantDisplayState(
          process: buildAssistantDisplayState(
            explicitState: AssistantDisplayState(
              answer: completedDisplayState.answer,
            ),
            processTimeline: _currentCanonicalProcessTimeline,
            understandingSnapshot: _currentUnderstandingSnapshot,
            retrievalProcessing: _currentRetrievalProcessing,
            answerProcessing: _answerProcessingFromResponse(runResponse),
            finalAnswerReady: true,
          ).process,
          answer: _resolvedCompletedAnswerState(
            completedDisplayState: completedDisplayState,
            displayMarkdown: displayMarkdown,
            existingRow: clearedRow,
          ),
        );
        _transcriptRows[existingIndex] = _mapToRow({
          ..._rowToMap(clearedRow),
          'content': displayMarkdown,
          'timestamp': replyTime,
          'runId': runResponse.runId ?? '',
          'traceId': runResponse.traceId ?? '',
          'sourceQuery': trimmed,
          'templateVersionUsed':
              (runResponse.structuredResponse['templateVersionUsed']
                  as String?) ??
              '',
          'phaseOneRoutingDiagnostics':
              (runResponse.structuredResponse['phaseOneRoutingDiagnostics']
                      as Map?)
                  ?.cast<String, dynamic>() ??
              const <String, dynamic>{},
          'degraded': runResponse.degraded,
          'qualityMetrics':
              (runResponse.structuredResponse['qualityMetrics'] as Map?)
                  ?.cast<String, dynamic>() ??
              const <String, dynamic>{},
          'heuristicFallbackUsed':
              (((runResponse.structuredResponse['qualityMetrics'] as Map?)
                  ?.cast<String, dynamic>())?['heuristicFallbackUsed']) ==
              true,
          'runArtifacts': _withDisplayOverrides(
            _responseRunArtifactsMap(runResponse),
            displayMarkdown: displayMarkdown,
            displayPlainText: displayPlainText,
            displayState: responseDisplayState,
          ),
          'domainId': (dialogueRuntime['domainId'] ?? '').toString(),
          'dialogueState': dialogueRuntime,
          'uiReferences': uiReferences,
          'uiActions': uiActions,
          'uiUsageStats': uiUsageStats,
          ...persistedTurnFields,
          assistantDisplayMarkdownField: displayMarkdown,
          assistantDisplayPlainTextField: displayPlainText,
          assistantDisplayStateField: responseDisplayState.toJson(),
          'streamFinalAnswer': '',
          'streaming': false,
        });
      } else {
        final completedDisplayState =
            resolveAssistantDisplayStateFromRunResponse(runResponse);
        final responseDisplayState = AssistantDisplayState(
          process: buildAssistantDisplayState(
            explicitState: AssistantDisplayState(
              answer: completedDisplayState.answer,
            ),
            processTimeline: _currentCanonicalProcessTimeline,
            understandingSnapshot: _currentUnderstandingSnapshot,
            retrievalProcessing: _currentRetrievalProcessing,
            answerProcessing: _answerProcessingFromResponse(runResponse),
            finalAnswerReady: true,
          ).process,
          answer: _resolvedCompletedAnswerState(
            completedDisplayState: completedDisplayState,
            displayMarkdown: displayMarkdown,
          ),
        );
        _transcriptRows.add(
          _mapToRow({
            'id': assistantMessageId,
            'conversationId': AppConceptConstants.assistantConversationId,
            'type': 'text',
            'content': displayMarkdown,
            'senderId': AppConceptConstants.assistantSenderId,
            'senderName': AppConceptConstants.assistantLabel,
            'senderAvatar': '',
            'timestamp': replyTime,
            'isRead': true,
            'isSelf': false,
            'runId': runResponse.runId ?? '',
            'traceId': runResponse.traceId ?? '',
            'sourceQuery': trimmed,
            'templateVersionUsed':
                (runResponse.structuredResponse['templateVersionUsed']
                    as String?) ??
                '',
            'phaseOneRoutingDiagnostics':
                (runResponse.structuredResponse['phaseOneRoutingDiagnostics']
                        as Map?)
                    ?.cast<String, dynamic>() ??
                const <String, dynamic>{},
            'degraded': runResponse.degraded,
            'qualityMetrics':
                (runResponse.structuredResponse['qualityMetrics'] as Map?)
                    ?.cast<String, dynamic>() ??
                const <String, dynamic>{},
            'heuristicFallbackUsed':
                (((runResponse.structuredResponse['qualityMetrics'] as Map?)
                    ?.cast<String, dynamic>())?['heuristicFallbackUsed']) ==
                true,
            'runArtifacts': _withDisplayOverrides(
              _responseRunArtifactsMap(runResponse),
              displayMarkdown: displayMarkdown,
              displayPlainText: displayPlainText,
              displayState: responseDisplayState,
            ),
            'domainId': (dialogueRuntime['domainId'] ?? '').toString(),
            'dialogueState': dialogueRuntime,
            'uiReferences': uiReferences,
            'uiActions': uiActions,
            'uiUsageStats': uiUsageStats,
            ...persistedTurnFields,
            assistantDisplayMarkdownField: displayMarkdown,
            assistantDisplayPlainTextField: displayPlainText,
            assistantDisplayStateField: responseDisplayState.toJson(),
          }),
        );
      }
      _assistantResponding = false;
      _assistantPhaseLabel = '';
      _activeAssistantStreamingMessageId = null;
      _answerGateOpen = true;
      if (activeSessionId.isNotEmpty) {
        _assistantRuntimeSessionId = activeSessionId;
      }
      if (activeTopicTitle != null && activeTopicTitle.isNotEmpty) {
        _assistantTopicTitle = activeTopicTitle;
      }
      _stopAssistantProgress();
      final userTags =
          (contextScope['userTags'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      _storeAssistantReplayRecord(
        messageId: assistantMessageId,
        query: trimmed,
        response: runResponse,
      );
      _notify();
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
            sessionId: effectiveAssistantSessionId,
            pageType: (contextScope['pageType'] as String?) ?? 'chat',
            queryText: trimmed,
            answerText: _resolveAssistantDisplayPlainText(runResponse),
            userTags: userTags,
            durationMs: elapsedMs,
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
    final contextScope = _withActivePersonaContextScope(
      buildContextScope(),
      activeContext: activeContext,
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
      await for (final streamEvent in _runAssistantStream(request)) {
        switch (streamEvent.type) {
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
          default:
            continue;
        }
        if (response != null) break;
      }
      if (response != null && !_disposed) {
        final finalResponse = response;
        final uiUsageStats = _buildConversationCumulativeUsageStats(
          runUsageStats:
              (finalResponse.structuredResponse['uiUsageStats'] as Map?)
                  ?.cast<String, dynamic>() ??
              const <String, dynamic>{},
          excludeMessageId: streamingAssistantMessageId,
        );
        final resolvedJourney = resolveAssistantJourneyFromResponse(
          finalResponse,
        );
        final resolvedCanonicalProcessTimeline =
            resolveAssistantProcessTimelineFromRunResponse(finalResponse);
        final resolvedProcessTimeline = buildVisibleProcessTimeline(
          resolvedCanonicalProcessTimeline,
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
        _currentJourney = effectiveJourney;
        _currentCanonicalProcessTimeline =
            resolvedCanonicalProcessTimeline.isNotEmpty
            ? resolvedCanonicalProcessTimeline
            : _currentCanonicalProcessTimeline;
        _currentProcessTimeline = resolvedProcessTimeline.isNotEmpty
            ? resolvedProcessTimeline
            : _currentProcessTimeline;
        final understandingSnapshot =
            (finalResponse
                        .structuredResponse[assistantUnderstandingSnapshotField]
                    as Map?)
                ?.cast<String, dynamic>();
        _currentUnderstandingSnapshot =
            understandingSnapshot != null && understandingSnapshot.isNotEmpty
            ? RunArtifactsUnderstandingSnapshot.fromJson(understandingSnapshot)
            : _understandingSnapshotFromTimeline(
                _currentCanonicalProcessTimeline,
              );
        final persistedTurnFields =
            _buildAssistantPersistedTurnFieldsForResponse(
              response: finalResponse,
              journey: effectiveJourney,
              processTimeline: _currentCanonicalProcessTimeline,
              displayMarkdown: displayMarkdown,
              displayPlainText: displayPlainText,
              elapsedMs: _currentJourneyElapsedMs,
            );
        _ensureTranscriptRowsGrowable();
        final idx = _findStreamingAssistantMessageIndex(
          streamingAssistantMessageId,
        );
        if (idx >= 0) {
          final clearedRow = _clearStreamingAnswerState(_transcriptRows[idx]);
          final completedDisplayState =
              resolveAssistantDisplayStateFromRunResponse(finalResponse);
          final responseDisplayState = AssistantDisplayState(
            process: buildAssistantDisplayState(
              explicitState: AssistantDisplayState(
                answer: completedDisplayState.answer,
              ),
              processTimeline: _currentCanonicalProcessTimeline,
              understandingSnapshot: _currentUnderstandingSnapshot,
              retrievalProcessing: _currentRetrievalProcessing,
              answerProcessing: _answerProcessingFromResponse(finalResponse),
              finalAnswerReady: true,
            ).process,
            answer: _resolvedCompletedAnswerState(
              completedDisplayState: completedDisplayState,
              displayMarkdown: displayMarkdown,
              existingRow: clearedRow,
            ),
          );
          _transcriptRows[idx] = _mapToRow({
            ..._rowToMap(clearedRow),
            'content': displayMarkdown,
            'streamFinalAnswer': '',
            'streaming': false,
            'sourceQuery': query,
            'templateVersionUsed':
                (finalResponse.structuredResponse['templateVersionUsed']
                    as String?) ??
                '',
            'phaseOneRoutingDiagnostics':
                (finalResponse.structuredResponse['phaseOneRoutingDiagnostics']
                        as Map?)
                    ?.cast<String, dynamic>() ??
                const <String, dynamic>{},
            'degraded': finalResponse.degraded,
            'qualityMetrics':
                (finalResponse.structuredResponse['qualityMetrics'] as Map?)
                    ?.cast<String, dynamic>() ??
                const <String, dynamic>{},
            'heuristicFallbackUsed':
                (((finalResponse.structuredResponse['qualityMetrics'] as Map?)
                    ?.cast<String, dynamic>())?['heuristicFallbackUsed']) ==
                true,
            'runArtifacts': _withDisplayOverrides(
              _responseRunArtifactsMap(finalResponse),
              displayMarkdown: displayMarkdown,
              displayPlainText: displayPlainText,
              displayState: responseDisplayState,
            ),
            'uiUsageStats': uiUsageStats,
            ...persistedTurnFields,
            assistantDisplayMarkdownField: displayMarkdown,
            assistantDisplayPlainTextField: displayPlainText,
            assistantDisplayStateField: responseDisplayState.toJson(),
          });
        }
      }
    } catch (_) {
      // Preserve streamed fallback content when rewrite fails midway.
    } finally {
      _resetStreamingAnswerDecoder();
      _assistantResponding = false;
      _assistantPhaseLabel = '';
      _activeAssistantStreamingMessageId = null;
      _stopAssistantProgress();
      _notify();
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
    final userTags =
        (contextScope['userTags'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
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
          pageType: (contextScope['pageType'] as String?) ?? 'chat',
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
    final tags = userTags.isNotEmpty
        ? userTags
        : ((contextScope['userTags'] as List?)
                  ?.whereType<String>()
                  .map((item) => item.trim())
                  .where((item) => item.isNotEmpty)
                  .toList(growable: false) ??
              const <String>[]);
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
          pageType: (contextScope['pageType'] as String?) ?? 'chat',
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
    final contextScope = buildContextScope();
    final privacyPolicy =
        (contextScope['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
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
    final privacyPolicy =
        (hints['privacyPolicy'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{
          'webAccessMode': 'limited',
          'allowedCapabilities': AssistantCapabilityCatalog.defaultCatalog,
          'allowedProviders': <String>[
            'page_context',
            'conversation',
            'memory',
            'web',
          ],
          'blockedProviders': <String>[],
          'allowedPageTypes': <String>[
            'discovery',
            'circles',
            'create',
            'chat',
            'home',
          ],
          'maxWebRounds': 1,
          'redactBeforeWeb': true,
          'allowedReferenceHosts':
              AppConceptConstants.assistantReferenceHostWhitelist,
        };
    final contentAccessState = _ref.read(personalContentAccessProvider);
    final identityIndexFeatureFlag = _ref.read(
      contentFeatureFlagProvider('enable_assistant_content_identity_index'),
    );
    final identityIndexEnabled = _ref.read(
      assistantContentIdentityIndexEnabledProvider,
    );
    final allowedProviders =
        ((privacyPolicy['allowedProviders'] as List?)
            ?.map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: true) ??
        <String>[]);
    final blockedProviders =
        ((privacyPolicy['blockedProviders'] as List?)
            ?.map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: true) ??
        <String>[]);
    if (!contentAccessState.granted) {
      allowedProviders.remove('page_context');
      if (!blockedProviders.contains('page_context')) {
        blockedProviders.add('page_context');
      }
    }
    final normalizedPrivacyPolicy = <String, dynamic>{
      ...privacyPolicy,
      'allowedProviders': allowedProviders,
      'blockedProviders': blockedProviders,
    };
    final userTags =
        (hints['userTags'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    final latestDialogueState = _latestAssistantDialogueState();
    final latestRunArtifacts = _latestAssistantRunArtifacts();
    final scope = <String, dynamic>{
      'pageType': _assistantSourceToPageType(openContext?.source),
      'sessionId': effectiveAssistantSessionId,
      'assistantBackend': _assistantBackend.wireName,
      if (openContext?.entityId != null) 'entityId': openContext!.entityId!,
      if (openContext?.tab != null) 'tab': openContext!.tab!,
      if (openContext?.dimension != null) 'dimension': openContext!.dimension!,
      'hints': hints,
      if (hints['behaviorTimeline'] is List<dynamic>)
        'behaviorTimeline': hints['behaviorTimeline'],
      if (userTags.isNotEmpty) 'userTags': userTags,
      if (latestDialogueState.isNotEmpty) 'dialogueState': latestDialogueState,
      if (latestRunArtifacts != null)
        'runArtifacts': latestRunArtifacts.toJson(),
      if (latestDialogueState['suggestedNextStateId'] is String &&
          (latestDialogueState['suggestedNextStateId'] as String)
              .trim()
              .isNotEmpty)
        'currentStateId':
            (latestDialogueState['suggestedNextStateId'] as String).trim(),
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

  AssistantJourneyViewModel buildJourneyViewModel({
    required AssistantJourney journey,
    List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
    required bool isRunning,
    AssistantUiUsageStatsViewData usageStats =
        AssistantUiUsageStatsViewData.empty,
    int? elapsedMs,
    AssistantDisplayState displayState = const AssistantDisplayState(),
    RetrievalProcessingSnapshot retrievalProcessing =
        const RetrievalProcessingSnapshot(),
  }) {
    return buildAssistantJourneyViewModel(
      journey: journey,
      processTimeline: processTimeline,
      isRunning: isRunning,
      allowAnswerStage: !isRunning || _answerGateOpen,
      displayState: displayState,
      retrievalProcessing: retrievalProcessing,
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
    _currentProcessTimeline = buildVisibleProcessTimeline(processTimeline);
    _currentCanonicalProcessTimeline =
        rebuildCanonicalProcessTimelineFromVisible(
          visibleProcessTimeline: _currentProcessTimeline,
          seedProcessTimeline: _currentCanonicalProcessTimeline,
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
    return snapshot.userFacingSummary.trim().isNotEmpty;
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

  void _resetStreamingAnswerDecoder() {
    _streamingAnswerDecoder.reset();
  }

  String _visibleStreamingAnswerChunk(String rawChunk) {
    return _streamingAnswerDecoder.appendChunk(rawChunk);
  }

  int _findStreamingAssistantMessageIndex(String messageId) {
    if (messageId.isEmpty) return -1;
    final exactIndex = _transcriptRows.indexWhere((item) => item.id == messageId);
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
        resolvePersistedAssistantDisplayState(_rowToMap(existingRow))
            .answer
            .blocks,
      );
      final nextMarkdown = renderAnswerBlocksToMarkdown(
        mergedDisplayState.answer.blocks,
      );
      if (nextMarkdown == prevMarkdown) {
        return;
      }
      _transcriptRows[existingIndex] = _patchRow(
        existingRow,
        {assistantDisplayStateField: mergedDisplayState.toJson()},
      );
    } else {
      final initialDisplayState = _streamingAnswerDisplayState(value);
      _transcriptRows.add(
        _mapToRow({
          'id': messageId,
          'conversationId': AppConceptConstants.assistantConversationId,
          'type': 'text',
          'content': '',
          'streamFinalAnswer': '',
          'senderId': AppConceptConstants.assistantSenderId,
          'senderName': AppConceptConstants.assistantLabel,
          'senderAvatar': '',
          'timestamp': ts,
          'isRead': true,
          'isSelf': false,
          'streaming': true,
          if (hasAssistantDisplayState(initialDisplayState))
            assistantDisplayStateField: initialDisplayState.toJson(),
        }),
      );
    }
    if (value.trim().isNotEmpty ||
        _shouldOpenAnswerGateForJourney(_currentJourney)) {
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
    final message = _rowToMap(row);
    final current = resolvePersistedAssistantDisplayState(message);
    final currentMarkdown = renderAnswerBlocksToMarkdown(current.answer.blocks);
    final mergedMarkdown = streamedAnswerDelta.trim().isEmpty
        ? currentMarkdown
        : _mergeStreamingAnswerText(
            previous: currentMarkdown,
            incoming: streamedAnswerDelta,
          );
    final effectiveUnderstandingSnapshot =
        understandingSnapshot ??
        (_hasStructuredUnderstandingSummary(_currentUnderstandingSnapshot)
            ? _currentUnderstandingSnapshot
            : resolveAssistantUnderstandingSnapshotFromMessage(message));
    final answerState = _streamingAnswerDisplayState(mergedMarkdown).answer;
    final mergedProcess = buildAssistantDisplayState(
      explicitState: AssistantDisplayState(answer: current.answer),
      processTimeline: resolveAssistantProcessTimelineFromMessage(message),
      understandingSnapshot: effectiveUnderstandingSnapshot,
      retrievalProcessing: resolveAssistantRetrievalProcessingFromMessage(
        message,
      ),
      answerProcessing: resolveAssistantAnswerProcessingFromMessage(message),
      finalAnswerReady: false,
    ).process;
    return AssistantDisplayState(process: mergedProcess, answer: answerState);
  }

  AssistantAnswerDisplayState _resolvedCompletedAnswerState({
    required AssistantDisplayState completedDisplayState,
    required String displayMarkdown,
    AssistantTranscriptTimelineRow? existingRow,
  }) {
    if (completedDisplayState.answer.blocks.isNotEmpty) {
      return completedDisplayState.answer;
    }
    final carriedAnswer = existingRow == null
        ? const AssistantAnswerDisplayState()
        : resolvePersistedAssistantDisplayState(_rowToMap(existingRow)).answer;
    if (carriedAnswer.blocks.isNotEmpty) {
      return AssistantAnswerDisplayState(
        summary: completedDisplayState.answer.summary,
        blocks: carriedAnswer.blocks,
      );
    }
    final fallback = _streamingAnswerDisplayState(displayMarkdown).answer;
    return AssistantAnswerDisplayState(
      summary: completedDisplayState.answer.summary,
      blocks: fallback.blocks,
    );
  }

  AssistantTranscriptTimelineRow _clearStreamingAnswerState(
    AssistantTranscriptTimelineRow row,
  ) =>
      _patchRow(row, {'streamFinalAnswer': ''});

  Map<String, dynamic> _withDisplayOverrides(
    Map<String, dynamic> runArtifacts, {
    required String displayMarkdown,
    required String displayPlainText,
    AssistantDisplayState displayState = const AssistantDisplayState(),
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
  }) {
    final runArtifacts = response.runArtifacts;
    final displayState = resolveAssistantDisplayStateFromRunResponse(response);
    return buildPersistedAssistantTurnFields(
      journey: journey,
      processTimeline: processTimeline,
      displayMarkdown: displayMarkdown,
      displayPlainText: displayPlainText,
      displayState: displayState.toJson(),
      followupPrompt: resolveAssistantFollowupPromptFromResponse(response),
      actionHints: resolveAssistantActionHintsFromResponse(response),
      elapsedMs: elapsedMs,
      understandingSnapshot:
          (response.structuredResponse[assistantUnderstandingSnapshotField]
                  as Map?)
              ?.cast<String, dynamic>() ??
          runArtifacts?.understandingSnapshot.toJson() ??
          const <String, dynamic>{},
      answerProcessing:
          (response.structuredResponse[assistantAnswerProcessingField] as Map?)
              ?.cast<String, dynamic>() ??
          runArtifacts?.answerProcessing.toJson() ??
          const <String, dynamic>{},
      historicalThinkingSnapshot:
          (response.structuredResponse[assistantHistoricalThinkingSnapshotField]
                  as Map?)
              ?.cast<String, dynamic>() ??
          runArtifacts?.historicalThinkingSnapshot.toJson() ??
          const <String, dynamic>{},
      retrievalProcessing:
          (response.structuredResponse[assistantRetrievalProcessingField]
                  as Map?)
              ?.cast<String, dynamic>() ??
          runArtifacts?.retrievalProcessing.toJson() ??
          const <String, dynamic>{},
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
    final readiness = journey.readiness;
    if (readiness.finalAnswerReady ||
        !_responseMarksFinalAnswerReady(response)) {
      return journey;
    }
    return AssistantJourney(
      stages: journey.stages,
      entries: journey.entries,
      summary: journey.summary,
      referenceSummary: journey.referenceSummary,
      readiness: AssistantJourneyReadiness(
        nextAction: readiness.nextAction,
        finalAnswerMode: readiness.finalAnswerMode,
        answerEligibility: readiness.answerEligibility,
        finalAnswerReady: true,
        clarificationNeeded: readiness.clarificationNeeded,
        needExpansion: readiness.needExpansion,
      ),
    );
  }

  bool _responseMarksFinalAnswerReady(AssistantRunResponse response) {
    if (response.degraded) return false;
    final answerDecision =
        response.runArtifacts?.answerDecision ?? const <String, dynamic>{};
    final conversationDecision =
        (response.structuredResponse['conversationStateDecision'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final nextActionCandidates = <String>[
      (answerDecision['nextAction'] as String?)?.trim() ?? '',
      (conversationDecision['nextAction'] as String?)?.trim() ?? '',
    ];
    if (nextActionCandidates.any((item) => item == 'answer')) {
      return true;
    }
    final visibleText = _resolveAssistantDisplayText(response).trim();
    return visibleText.isNotEmpty && visibleText != '助手未生成有效回答，请重试。';
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
    Map<String, dynamic> webSearchDiagnostics = const <String, dynamic>{};
    for (var i = traces.length - 1; i >= 0; i--) {
      final trace = traces[i];
      if (trace.type != AssistantTraceEventType.toolResult &&
          trace.type != AssistantTraceEventType.toolError) {
        continue;
      }
      final data = trace.data ?? const <String, dynamic>{};
      final diagnostics =
          (data['diagnostics'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      if (diagnostics.isNotEmpty) {
        webSearchDiagnostics = diagnostics;
        break;
      }
    }
    for (var i = traces.length - 1; i >= 0; i--) {
      final trace = traces[i];
      if (trace.type != AssistantTraceEventType.toolResult) continue;
      final data = trace.data ?? const <String, dynamic>{};
      final queryPlan = (data['queryPlan'] as Map?)?.cast<String, dynamic>();
      final policyDecision = (data['policyDecision'] as Map?)
          ?.cast<String, dynamic>();
      final roundTraces = (data['roundTraces'] as List?)
          ?.whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false);
      if (queryPlan != null || policyDecision != null || roundTraces != null) {
        return <String, dynamic>{
          'queryPlan': queryPlan ?? const <String, dynamic>{},
          'policyDecision': policyDecision ?? const <String, dynamic>{},
          'roundTraces': roundTraces ?? const <Map<String, dynamic>>[],
          'webSearchDiagnostics': webSearchDiagnostics,
        };
      }
    }
    return <String, dynamic>{
      'queryPlan': const <String, dynamic>{},
      'policyDecision': const <String, dynamic>{},
      'roundTraces': const <Map<String, dynamic>>[],
      'webSearchDiagnostics': webSearchDiagnostics,
    };
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
