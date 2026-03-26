import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/application/assistant_backend.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/assistant_streaming_answer_decoder.dart';
import 'package:quwoquan_app/assistant/capabilities/capabilities.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/orchestration/orchestration.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_display_fallbacks.dart';
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

  final Map<String, Map<String, dynamic>> _assistantReplayByMessageId =
      <String, Map<String, dynamic>>{};
  final List<Map<String, dynamic>> _assistantReplayRecords =
      <Map<String, dynamic>>[];
  final Map<String, String> _assistantFeedbackStatusByMessageId =
      <String, String>{};

  List<Map<String, dynamic>> _messages = <Map<String, dynamic>>[];
  AssistantJourney _currentJourney = const AssistantJourney();
  RetrievalProcessingSnapshot _currentRetrievalProcessing =
      const RetrievalProcessingSnapshot();
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
  List<Map<String, dynamic>> _assistantHiddenHistory = <Map<String, dynamic>>[];
  bool _disposed = false;

  List<Map<String, dynamic>> get messages => _messages;
  AssistantJourney get currentJourney => _currentJourney;
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
  List<Map<String, dynamic>> get assistantHiddenHistory =>
      _assistantHiddenHistory;
  Map<String, String> get feedbackStatusByMessageId =>
      _assistantFeedbackStatusByMessageId;
  List<Map<String, dynamic>> get replayRecords => _assistantReplayRecords;

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
    _assistantHiddenHistory = <Map<String, dynamic>>[];
    _assistantLoadingOlderHistory = false;
    _showAssistantHistoryPeek = false;
    _messages = <Map<String, dynamic>>[];
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
    _ensureMessagesGrowable();
    _messages.addAll(attachmentMessages);
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
    _messages = List<Map<String, dynamic>>.from(<Map<String, dynamic>>[
      ...olderChunk,
      ..._messages,
    ]);
    _assistantHiddenHistory = List<Map<String, dynamic>>.from(remainingHidden);
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
          final hasPersistedTimeline =
              !isUser && !resolvePersistedAssistantTimeline(item).isEmpty;
          if (!isUser &&
              normalizedContent.trim().isEmpty &&
              !hasPersistedTimeline) {
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
    _assistantHiddenHistory = List<Map<String, dynamic>>.from(hiddenHistory);
    _assistantLoadingOlderHistory = false;
    _showAssistantHistoryPeek = hiddenHistory.isNotEmpty;
    _messages = List<Map<String, dynamic>>.from(visibleMessages);
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
      _assistantHiddenHistory = <Map<String, dynamic>>[];
      _assistantLoadingOlderHistory = false;
      _showAssistantHistoryPeek = false;
      _messages = <Map<String, dynamic>>[];
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
    _assistantHiddenHistory = <Map<String, dynamic>>[];
    _assistantLoadingOlderHistory = false;
    _showAssistantHistoryPeek = false;
    _messages = <Map<String, dynamic>>[];
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
    _ensureMessagesGrowable();
    _messages.add({
      'id': userMessageId,
      'conversationId': AppConceptConstants.assistantConversationId,
      'type': 'text',
      'content': trimmed,
      'senderId': activeContext.profileSubjectId,
      'senderName': activeContext.displayName.isNotEmpty
          ? activeContext.displayName
          : '我',
      'senderAvatar': activeContext.avatarUrl,
      if (activeContext.subAccountId.isNotEmpty)
        'senderPersonaId': activeContext.subAccountId,
      'timestamp': '',
      'status': 'sending',
      'isRead': true,
      'isSelf': true,
    });
    final streamNow = DateTime.now();
    final streamTs =
        '${streamNow.hour}:${streamNow.minute.toString().padLeft(2, '0')}';
    _resetStreamingAnswerDecoder();
    _ensureMessagesGrowable();
    final streamingAssistantMessageId =
        'assistant_stream_${DateTime.now().millisecondsSinceEpoch}';
    _activeAssistantStreamingMessageId = streamingAssistantMessageId;
    _answerGateOpen = false;
    _assistantResponding = true;
    _assistantPhaseLabel = UITextConstants.assistantPhaseUnderstanding;
    _currentJourney = const AssistantJourney();
    _currentRetrievalProcessing = const RetrievalProcessingSnapshot();
    _currentJourneyElapsedMs = 0;
    _messages.add(<String, dynamic>{
      'id': streamingAssistantMessageId,
      'conversationId': AppConceptConstants.assistantConversationId,
      'type': 'text',
      'content': '',
      'senderId': AppConceptConstants.assistantSenderId,
      'senderName': AppConceptConstants.assistantLabel,
      'senderAvatar': '',
      'timestamp': streamTs,
      'isRead': true,
      'isSelf': false,
      'streaming': true,
      'streamFinalAnswer': '',
      assistantTurnSchemaVersionField: assistantTurnSchemaVersion,
      assistantDisplayMarkdownField: '',
      assistantDisplayPlainTextField: '',
      'runArtifacts': const <String, dynamic>{},
      assistantJourneyField: const <String, dynamic>{},
      assistantUiProcessTimelineField: const <String, dynamic>{},
      assistantFollowupPromptField: '',
      assistantActionHintsField: const <String>[],
      'assistantElapsedMs': 0,
    });
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
      final assistantMessages = _messages
          .where((m) {
            if ((m['type'] as String? ?? 'text') != 'text') return false;
            if (m['streaming'] == true) return false;
            if (m['isError'] == true) return false;
            if (m['isSelf'] == true) {
              return ((m['content'] as String?)?.trim().isNotEmpty ?? false);
            }
            return _assistantHistoryContentForModel(m).trim().isNotEmpty;
          })
          .map((m) {
            final isUser = m['isSelf'] == true;
            final content = isUser
                ? ((m['content'] as String?) ?? '')
                : _assistantHistoryContentForModel(m);
            return AssistantRunMessage(
              role: isUser ? 'user' : 'assistant',
              content: content,
            );
          })
          .where((message) => message.content.trim().isNotEmpty)
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
            artifactMarkdown.isNotEmpty
                ? artifactMarkdown
                : (runResponse.displayMarkdown.trim().isNotEmpty
                      ? runResponse.displayMarkdown
                      : displayText),
            allowJsonExtraction:
                artifactMarkdown.isNotEmpty ||
                runResponse.displayMarkdown.trim().isNotEmpty,
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
      final effectiveJourney = _persistableAssistantJourney(
        response: runResponse,
        journey: resolvedJourney.isEmpty ? _currentJourney : resolvedJourney,
      );
      final retrievalProcessing =
          resolveAssistantRetrievalProcessingFromResponse(runResponse);
      if (_disposed) return;
      _currentJourney = effectiveJourney;
      _currentRetrievalProcessing = retrievalProcessing;
      _currentJourneyElapsedMs = elapsedMs;
      final persistedTurnFields = _buildAssistantPersistedTurnFieldsForResponse(
        response: runResponse,
        journey: effectiveJourney,
        displayMarkdown: displayMarkdown,
        displayPlainText: displayPlainText,
        elapsedMs: elapsedMs,
      );
      _ensureMessagesGrowable();
      final existingIndex = _messages.indexWhere(
        (item) => (item['id'] as String?) == streamingAssistantMessageId,
      );
      if (existingIndex >= 0) {
        final existingMessage = _messages[existingIndex];
        final effectiveDisplayText = _reconcileCompletedAnswerText(
          streamedText: (existingMessage['streamFinalAnswer'] as String?) ?? '',
          completedText: displayText,
        );
        _messages[existingIndex] = <String, dynamic>{
          ...existingMessage,
          'content': effectiveDisplayText,
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
          'runArtifacts': _responseRunArtifactsMap(runResponse),
          'domainId': (dialogueRuntime['domainId'] ?? '').toString(),
          'dialogueState': dialogueRuntime,
          'uiReferences': uiReferences,
          'uiActions': uiActions,
          'uiUsageStats': uiUsageStats,
          ...persistedTurnFields,
          'streamFinalAnswer': '',
          'streaming': false,
        };
      } else {
        _messages.add({
          'id': assistantMessageId,
          'conversationId': AppConceptConstants.assistantConversationId,
          'type': 'text',
          'content': displayText,
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
          'runArtifacts': _responseRunArtifactsMap(runResponse),
          'domainId': (dialogueRuntime['domainId'] ?? '').toString(),
          'dialogueState': dialogueRuntime,
          'uiReferences': uiReferences,
          'uiActions': uiActions,
          'uiUsageStats': uiUsageStats,
          ...persistedTurnFields,
        });
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
      _ensureMessagesGrowable();
      _assistantResponding = false;
      _assistantPhaseLabel = '';
      _activeAssistantStreamingMessageId = null;
      _messages.removeWhere(
        (item) => (item['id'] as String?) == streamingAssistantMessageId,
      );
      final errorHint = kDebugMode ? '助手异常: ${e.runtimeType}' : '助手出现异常，请重试。';
      _messages.add({
        'id': 'assistant_err_${DateTime.now().millisecondsSinceEpoch}',
        'conversationId': AppConceptConstants.assistantConversationId,
        'type': 'text',
        'content': errorHint,
        'senderId': AppConceptConstants.assistantSenderId,
        'senderName': AppConceptConstants.assistantLabel,
        'senderAvatar': '',
        'timestamp': '',
        'isRead': true,
        'isSelf': false,
        'isError': true,
      });
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
    _ensureMessagesGrowable();
    _messages.add(<String, dynamic>{
      'id': 'user_rewrite_${now.millisecondsSinceEpoch}',
      'conversationId': AppConceptConstants.assistantConversationId,
      'type': 'text',
      'content': _rewriteUserLabel(rewrite.mode),
      'senderId': activeContext.profileSubjectId,
      'senderName': activeContext.displayName,
      'timestamp': ts,
      'isRead': true,
      'isSelf': true,
    });
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
    _ensureMessagesGrowable();
    streamingAssistantMessageId =
        'assistant_rewrite_${now.millisecondsSinceEpoch}';
    _activeAssistantStreamingMessageId = streamingAssistantMessageId;
    _answerGateOpen = false;
    _assistantResponding = true;
    _assistantPhaseLabel = UITextConstants.assistantPhaseAnswering;
    _currentJourney = const AssistantJourney();
    _currentRetrievalProcessing = const RetrievalProcessingSnapshot();
    _currentJourneyElapsedMs = 0;
    _messages.add(<String, dynamic>{
      'id': streamingAssistantMessageId,
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
      'sourceQuery': query,
      assistantTurnSchemaVersionField: assistantTurnSchemaVersion,
      assistantDisplayMarkdownField: '',
      assistantDisplayPlainTextField: '',
      'runArtifacts': const <String, dynamic>{},
      assistantJourneyField: const <String, dynamic>{},
      assistantUiProcessTimelineField: const <String, dynamic>{},
      assistantFollowupPromptField: '',
      assistantActionHintsField: const <String>[],
      'assistantElapsedMs': 0,
    });
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
              artifactMarkdown.isNotEmpty
                  ? artifactMarkdown
                  : (finalResponse.displayMarkdown.trim().isNotEmpty
                        ? finalResponse.displayMarkdown
                        : finalText),
              allowJsonExtraction:
                  artifactMarkdown.isNotEmpty ||
                  finalResponse.displayMarkdown.trim().isNotEmpty,
            );
        _resetStreamingAnswerDecoder();
        _currentJourney = effectiveJourney;
        final persistedTurnFields =
            _buildAssistantPersistedTurnFieldsForResponse(
              response: finalResponse,
              journey: effectiveJourney,
              displayMarkdown: displayMarkdown,
              displayPlainText: displayPlainText,
              elapsedMs: _currentJourneyElapsedMs,
            );
        _ensureMessagesGrowable();
        final idx = _messages.indexWhere(
          (item) => (item['id'] as String?) == streamingAssistantMessageId,
        );
        if (idx >= 0) {
          final existingMessage = _messages[idx];
          final effectiveFinalText = _reconcileCompletedAnswerText(
            streamedText:
                (existingMessage['streamFinalAnswer'] as String?) ?? '',
            completedText: finalText,
          );
          _messages[idx] = <String, dynamic>{
            ...existingMessage,
            'content': effectiveFinalText,
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
            'runArtifacts': _responseRunArtifactsMap(finalResponse),
            'uiUsageStats': uiUsageStats,
            ...persistedTurnFields,
          };
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
    required Map<String, dynamic> message,
    required String explicitThumb,
    required List<String> reasonCodes,
    String correctionText = '',
  }) async {
    final messageId = (message['id'] as String?) ?? '';
    final replay =
        _assistantReplayByMessageId[messageId] ?? const <String, dynamic>{};
    final query =
        (message['sourceQuery'] as String?) ??
        (replay['query'] as String?) ??
        '';
    final runId =
        (message['runId'] as String?) ?? (replay['runId'] as String?) ?? '';
    final traceId =
        (message['traceId'] as String?) ?? (replay['traceId'] as String?) ?? '';
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
          answerText: (message['content'] as String?) ?? '',
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
    required Map<String, dynamic> message,
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
          runId: (message['runId'] as String?)?.trim().isNotEmpty == true
              ? (message['runId'] as String).trim()
              : 'run_${DateTime.now().millisecondsSinceEpoch}',
          traceId: (message['traceId'] as String?)?.trim().isNotEmpty == true
              ? (message['traceId'] as String).trim()
              : 'trace_${DateTime.now().millisecondsSinceEpoch}',
          userId: _currentProfileSubjectId(),
          sessionId: effectiveAssistantSessionId,
          pageType: (contextScope['pageType'] as String?) ?? 'chat',
          queryText: (message['sourceQuery'] as String?) ?? '',
          answerText:
              ((message['displayPlainText'] as String?)?.trim().isNotEmpty ==
                      true
                  ? (message['displayPlainText'] as String)
                  : (message['content'] as String?)) ??
              '',
          userTags: tags,
          durationMs: 0,
          copiedAnswer: copiedAnswer,
          sharedAnswer: sharedAnswer,
          favoritedAnswer: favoritedAnswer,
          regeneratedAnswer: regeneratedAnswer,
          styleAdjusted: styleAdjusted,
          modelSwitched: modelSwitched,
          referenceOpened: referenceOpened,
          feedbackTargetMessageId: (message['id'] as String?) ?? '',
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
    return _assistantReplayByMessageId[messageId] ?? const <String, dynamic>{};
  }

  void removeMessageById(String id) {
    _messages = List<Map<String, dynamic>>.from(_messages)
      ..removeWhere((item) => (item['id'] as String?) == id);
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
    required bool isRunning,
    Map<String, dynamic> usageStats = const <String, dynamic>{},
    int? elapsedMs,
    RetrievalProcessingSnapshot retrievalProcessing =
        const RetrievalProcessingSnapshot(),
  }) {
    return buildAssistantJourneyViewModel(
      journey: journey,
      isRunning: isRunning,
      allowAnswerStage:
          !isRunning || _answerGateOpen || journey.readiness.finalAnswerReady,
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

  void _ensureMessagesGrowable() {
    _messages = List<Map<String, dynamic>>.from(_messages);
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
    required bool isRunning,
  }) {
    final viewModel = buildJourneyViewModel(
      journey: journey,
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
      isRunning: true,
    );
    if (_shouldOpenAnswerGateForJourney(journey)) {
      _answerGateOpen = true;
    }
    if (messageId != null && messageId.isNotEmpty) {
      final index = _messages.indexWhere(
        (item) => (item['id'] as String?) == messageId,
      );
      if (index >= 0) {
        _messages[index] = <String, dynamic>{
          ..._messages[index],
          assistantJourneyField: journey.toJson(),
          assistantUiProcessTimelineField: buildAssistantUiProcessTimeline(
            journey,
          ).toJson(),
          'assistantElapsedMs': _currentJourneyElapsedMs,
        };
      }
    }
    _notify();
  }

  void _resetStreamingAnswerDecoder() {
    _streamingAnswerDecoder.reset();
  }

  String _visibleStreamingAnswerChunk(String rawChunk) {
    return _streamingAnswerDecoder.appendChunk(rawChunk);
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
    _ensureMessagesGrowable();
    final existingIndex = _messages.indexWhere(
      (item) => (item['id'] as String?) == messageId,
    );
    if (existingIndex >= 0) {
      final prev =
          (_messages[existingIndex]['streamFinalAnswer'] as String?) ?? '';
      final merged = _mergeStreamingAnswerText(previous: prev, incoming: value);
      if (merged == prev) {
        return;
      }
      _messages[existingIndex] = <String, dynamic>{
        ..._messages[existingIndex],
        'streamFinalAnswer': merged,
      };
    } else {
      _messages.add(<String, dynamic>{
        'id': messageId,
        'conversationId': AppConceptConstants.assistantConversationId,
        'type': 'text',
        'content': '',
        'streamFinalAnswer': value,
        'senderId': AppConceptConstants.assistantSenderId,
        'senderName': AppConceptConstants.assistantLabel,
        'senderAvatar': '',
        'timestamp': ts,
        'isRead': true,
        'isSelf': false,
        'streaming': true,
      });
    }
    if (value.trim().isNotEmpty ||
        _shouldOpenAnswerGateForJourney(_currentJourney)) {
      _answerGateOpen = true;
    }
    _notify();
  }

  String _reconcileCompletedAnswerText({
    required String streamedText,
    required String completedText,
  }) {
    final streamed = streamedText.trim();
    final completed = completedText.trim();
    final sanitizedCompleted = _sanitizeCompletedDisplayCandidate(
      completed,
      allowJsonExtraction: true,
    );
    final sanitizedStreamed = _sanitizeCompletedDisplayCandidate(
      streamed,
      allowJsonExtraction: true,
    );
    if (sanitizedCompleted.isNotEmpty) {
      if (sanitizedStreamed.isEmpty) return sanitizedCompleted;
      if (sanitizedCompleted == sanitizedStreamed) return sanitizedCompleted;
      if (sanitizedCompleted.startsWith(sanitizedStreamed)) {
        return sanitizedCompleted;
      }
      if (sanitizedCompleted.length >= sanitizedStreamed.length) {
        return sanitizedCompleted;
      }
    }
    if (sanitizedStreamed.isNotEmpty) return sanitizedStreamed;
    if (completed.isEmpty) return streamed;
    if (streamed.isEmpty) return completed;
    if (completed == streamed) return completed;
    if (_containsInternalDisplayFragment(streamed) &&
        !_containsInternalDisplayFragment(completed)) {
      return completed;
    }
    if (completed.startsWith(streamed)) return completed;
    if (completed.length >= streamed.length &&
        !_containsInternalDisplayFragment(completed)) {
      return completed;
    }
    return streamed;
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
    for (final message in _messages) {
      if ((message['senderId'] as String?) !=
          AppConceptConstants.assistantSenderId) {
        continue;
      }
      if (excludeMessageId != null &&
          (message['id'] as String?) == excludeMessageId) {
        continue;
      }
      final usageStats = (message['uiUsageStats'] as Map?)
          ?.cast<String, dynamic>();
      if (usageStats == null || usageStats.isEmpty) continue;
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
    if (sanitized.contains('tool_call') ||
        sanitized.contains('queryTasks') ||
        sanitized.contains('queryVariants') ||
        sanitized.contains('正在调用工具')) {
      return '';
    }
    return sanitized;
  }

  Map<String, dynamic> _latestAssistantDialogueState() {
    for (var i = _messages.length - 1; i >= 0; i--) {
      final message = _messages[i];
      if ((message['senderId'] as String?) !=
          AppConceptConstants.assistantSenderId) {
        continue;
      }
      final state = (message['dialogueState'] as Map?)?.cast<String, dynamic>();
      if (state != null && state.isNotEmpty) return state;
    }
    return const <String, dynamic>{};
  }

  RunArtifacts? _latestAssistantRunArtifacts() {
    for (var i = _messages.length - 1; i >= 0; i--) {
      final message = _messages[i];
      if ((message['senderId'] as String?) !=
          AppConceptConstants.assistantSenderId) {
        continue;
      }
      final raw = (message['runArtifacts'] as Map?)?.cast<String, dynamic>();
      if (raw == null || raw.isEmpty) continue;
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

  String _responseArtifactDisplayMarkdown(AssistantRunResponse response) {
    final runArtifacts = _responseRunArtifactsMap(response);
    return (runArtifacts['displayMarkdown'] as String?)?.trim() ?? '';
  }

  String _responseArtifactDisplayPlainText(AssistantRunResponse response) {
    final runArtifacts = _responseRunArtifactsMap(response);
    return (runArtifacts['displayPlainText'] as String?)?.trim() ?? '';
  }

  String _resolveAssistantDisplayText(AssistantRunResponse response) {
    final displayText = _firstCompletedDisplayCandidate(<String>[
      _responseArtifactDisplayMarkdown(response),
      _responseArtifactDisplayPlainText(response),
      response.displayMarkdown,
      response.displayPlainText,
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
          _responseArtifactDisplayPlainText(response).isNotEmpty
              ? _responseArtifactDisplayPlainText(response)
              : response.displayPlainText,
          allowJsonExtraction: false,
        );
    if (artifactPlain.isNotEmpty) {
      return artifactPlain;
    }
    final artifactMarkdown =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          _responseArtifactDisplayMarkdown(response).isNotEmpty
              ? _responseArtifactDisplayMarkdown(response)
              : response.displayMarkdown,
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
    required String displayMarkdown,
    required String displayPlainText,
    required int elapsedMs,
  }) {
    return buildPersistedAssistantTurnFields(
      journey: journey,
      displayMarkdown: displayMarkdown,
      displayPlainText: displayPlainText,
      followupPrompt: resolveAssistantFollowupPromptFromResponse(response),
      actionHints: resolveAssistantActionHintsFromResponse(response),
      elapsedMs: elapsedMs,
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
    final structured = response.structuredResponse.isEmpty
        ? const <String, dynamic>{}
        : response.structuredResponse;
    final record = <String, dynamic>{
      'messageId': messageId,
      'runId': response.runId ?? '',
      'traceId': response.traceId ?? '',
      'query': query,
      'answer': _resolveAssistantDisplayText(response),
      'displayPlainText': _resolveAssistantDisplayPlainText(response),
      'runArtifacts': _responseRunArtifactsMap(response),
      'createdAt': DateTime.now().toIso8601String(),
      'uiReferences':
          (structured['uiReferences'] as List?)?.whereType<Map>().toList(
            growable: false,
          ) ??
          const <Map>[],
      'uiUsageStats':
          (structured['uiUsageStats'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      ...replayPayload,
    };
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
