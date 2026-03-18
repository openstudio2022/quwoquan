import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:file_picker/file_picker.dart';
import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/assistant/application/assistant_backend.dart';
import 'package:quwoquan_app/assistant/application/assistant_providers.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/assistant_streaming_answer_decoder.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/capabilities/capabilities.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/orchestration/orchestration.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_display_fallbacks.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_dev_replay_page.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_chat_settings_page.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_manager.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_journey_view_model.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_turn_message_resolver.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/regenerate_options_popup.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/streaming_scroll_fab.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';

/// 聊天气泡时间分隔符 — 直接透传 ChatTimeFormatter 的完整格式
///
/// 接收已格式化的 "{日期标签} 上午/下午H:mm" 或 ISO 字符串，
/// 返回用于展示的时间文本。空串表示发送中。
String formatChatTime(String? raw) {
  if (raw == null || raw.isEmpty) return '';
  return raw;
}

/// 聊天详情页 - 1:1 对应 WeChatStyleChatDetail → CircleChatSystem / ChatDetail.tsx
/// 含：消息气泡、输入栏、长按菜单（转发/多选/复制/撤回/删除）；私人助理会话显示「助理主页」入口
class ChatDetailPage extends ConsumerStatefulWidget {
  const ChatDetailPage({
    super.key,
    required this.conversationId,
    required this.onBack,
    this.assistantOpenContext,
    this.embedded = false,
  });

  final String conversationId;
  final VoidCallback onBack;
  final bool embedded;

  /// 从半弹窗「进入完整对话」传入时携带，用于首条欢迎与推荐（与半弹窗一致）。
  final AssistantOpenContext? assistantOpenContext;

  @override
  ConsumerState<ChatDetailPage> createState() => _ChatDetailPageState();
}

class _ChatDetailPageState extends ConsumerState<ChatDetailPage> {
  static const int _assistantHistoryPageSize = 18;
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  List<Map<String, dynamic>> _messages = [];
  String? _resolvedTitle;

  /// 会话基本信息（type/memberCount），initState 后异步加载
  ConversationDto? _conversationDto;

  /// 1v1 会话中对方的用户 ID（从成员列表推断）
  String? _otherParticipantId;
  RelationshipCapabilityDto? _relationshipCapability;

  bool _isSelectionMode = false;
  final Set<String> _selectedIds = {};
  Map<String, dynamic>? _actionMenuMessage;
  Offset? _actionMenuPosition;
  bool _showEmojiPanel = false;
  final FocusNode _inputFocusNode = FocusNode();
  bool _assistantResponding = false;
  final Map<String, Map<String, dynamic>> _assistantReplayByMessageId =
      <String, Map<String, dynamic>>{};
  final List<Map<String, dynamic>> _assistantReplayRecords =
      <Map<String, dynamic>>[];
  final Map<String, String> _assistantFeedbackStatusByMessageId =
      <String, String>{};
  double _lastViewportWidth = 390;
  Timer? _assistantProgressTimer;
  DateTime? _assistantProgressStartedAt;

  /// 当前轮过程状态机展示文案（等待/深度搜索中/深度思考中），由 trace 事件驱动
  String _assistantPhaseLabel = '';
  String? _activeAssistantStreamingMessageId;
  final AssistantStreamingAnswerDecoder _streamingAnswerDecoder =
      AssistantStreamingAnswerDecoder();

  AssistantJourney _currentJourney = const AssistantJourney();
  int _currentJourneyElapsedMs = 0;
  bool _answerGateOpen = true;

  /// Whether the user has scrolled away from the bottom during streaming.
  bool _userScrolledAway = false;

  /// Whether to show the scroll-to-bottom FAB.
  bool _showScrollFab = false;
  AssistantBackend _assistantBackend = AssistantBackend.remote;
  String _assistantRuntimeSessionId = '';
  String _assistantTopicTitle = UITextConstants.assistantHistoryAll;
  List<Map<String, dynamic>> _assistantHiddenHistory = <Map<String, dynamic>>[];
  bool _assistantLoadingOlderHistory = false;
  bool _showAssistantHistoryPeek = false;
  final ImagePicker _imagePicker = ImagePicker();
  final stt.SpeechToText _speechToText = stt.SpeechToText();
  bool _speechReady = false;
  String _lastAsrText = '';
  bool _assistantRemoteConfiguredCached = false;

  @override
  void initState() {
    super.initState();
    _assistantRemoteConfiguredCached = ref.read(
      assistantRemoteConfiguredProvider,
    );
    _scrollController.addListener(_onScrollChanged);
    if (_isAssistantConversation) {
      _assistantBackend = _preferredAssistantBackendOnOpen();
      _assistantRuntimeSessionId = newAssistantSessionId(_assistantBackend);
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (_isAssistantConversation) {
        _loadMessages();
      } else {
        Future<void>(() async {
          final notifier = ref.read(
            chatMessageProvider(widget.conversationId).notifier,
          );
          await notifier.loadMessages();
          final marked = await notifier.markConversationRead();
          if (marked && mounted) {
            ref
                .read(chatInboxListProvider.notifier)
                .markConversationRead(widget.conversationId);
          }
        });
        ref
            .read(realtimeConnectionManagerProvider.notifier)
            .onEnterChatDetail(widget.conversationId);
      }
    });
    _inputController.addListener(_onInputChanged);
    if (_isAssistantConversation) {
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        final synced = await _syncAssistantSessionInfo();
        if (!mounted || synced) return;
        await _startFreshAssistantSessionOnOpen();
      });
    }
  }

  Future<void> _loadConversationTitle() async {
    if (_resolvedTitle != null) return;
    try {
      final repo = ref.read(chatRepositoryProvider);
      final conv = await repo.getConversation(widget.conversationId);
      final dto = ConversationDto.fromMap(conv);
      if (!mounted) return;
      setState(() {
        _resolvedTitle = dto.title ?? widget.conversationId;
        _conversationDto = dto;
      });
      // 1v1 会话：异步加载对方成员 ID，用于精确传递 targetUserId
      if (dto.type == 'direct') {
        _loadOtherParticipantId(repo);
      }
    } catch (_) {}
  }

  Future<void> _loadOtherParticipantId(dynamic repo) async {
    try {
      final currentUserId = ref.read(userDataProvider)?.id ?? '';
      final members = await repo.listMembers(
        conversationId: widget.conversationId,
        limit: 10,
      );
      final other = (members as List<Map<String, dynamic>>).firstWhere(
        (m) => (m['userId'] as String? ?? '') != currentUserId,
        orElse: () => <String, dynamic>{},
      );
      final otherId = other['userId'] as String?;
      if (mounted && otherId != null && otherId.isNotEmpty) {
        setState(() => _otherParticipantId = otherId);
        await _loadRelationshipCapability(otherId);
      }
    } catch (_) {}
  }

  Future<void> _loadRelationshipCapability(String otherId) async {
    try {
      final capability = await ref
          .read(relationshipCapabilityRepositoryProvider)
          .getCapability(otherId);
      if (!mounted) return;
      setState(() => _relationshipCapability = capability);
    } catch (_) {}
  }

  bool get _isGroupChat => _conversationDto?.type == 'group';

  int get _memberCount => _conversationDto?.memberCount ?? 0;

  Future<void> _loadMessages() async {
    if (_isAssistantConversation) {
      if (!mounted) return;
      setState(
        () => _messages = List<Map<String, dynamic>>.from(
          const <Map<String, dynamic>>[],
        ),
      );
      return;
    }
    try {
      final repo = ref.read(chatRepositoryProvider);
      final list = await repo.listMessages(
        conversationId: widget.conversationId,
        limit: 50,
      );
      if (!mounted) return;
      setState(() => _messages = List<Map<String, dynamic>>.from(list));
    } catch (e) {
      // 保持页面可用：加载失败时回退到 ChatRepository mock 数据
      try {
        final fallback = await ref
            .read(chatRepositoryProvider)
            .listMessages(conversationId: widget.conversationId);
        if (!mounted) return;
        setState(() => _messages = List<Map<String, dynamic>>.from(fallback));
      } catch (_) {
        // 双重失败：保持空消息列表
      }
    }
  }

  Future<void> _startFreshAssistantSessionOnOpen() async {
    if (!_isAssistantConversation || !mounted) return;
    final backend = _resolveAvailableAssistantBackend(_assistantBackend);
    final freshSessionId = newAssistantSessionId(backend);
    setState(() {
      _assistantBackend = backend;
      _assistantRuntimeSessionId = freshSessionId;
      _assistantTopicTitle = UITextConstants.assistantHistoryAll;
      _assistantHiddenHistory = <Map<String, dynamic>>[];
      _assistantLoadingOlderHistory = false;
      _showAssistantHistoryPeek = false;
      _messages = List<Map<String, dynamic>>.from(
        const <Map<String, dynamic>>[],
      );
    });
  }

  void _onInputChanged() {
    if (mounted) setState(() {});
  }

  void _onScrollChanged() {
    if (!_scrollController.hasClients) return;
    final maxScroll = _scrollController.position.maxScrollExtent;
    final currentScroll = _scrollController.offset;
    final isNearBottom = maxScroll - currentScroll < 80;

    if (_isAssistantConversation && _assistantHiddenHistory.isNotEmpty) {
      if (!_showAssistantHistoryPeek) {
        setState(() => _showAssistantHistoryPeek = true);
      }
      if (!_assistantResponding &&
          !_assistantLoadingOlderHistory &&
          currentScroll <= AppSpacing.sm) {
        _loadOlderAssistantHistory();
      }
    }

    if (_assistantResponding) {
      if (!isNearBottom && !_userScrolledAway) {
        setState(() {
          _userScrolledAway = true;
          _showScrollFab = true;
        });
      } else if (isNearBottom && _userScrolledAway) {
        setState(() {
          _userScrolledAway = false;
          _showScrollFab = false;
        });
      }
    } else if (_showScrollFab) {
      setState(() => _showScrollFab = false);
    }
  }

  Future<void> _loadOlderAssistantHistory() async {
    if (!_isAssistantConversation ||
        _assistantLoadingOlderHistory ||
        _assistantHiddenHistory.isEmpty) {
      return;
    }
    final previousOffset = _scrollController.hasClients
        ? _scrollController.offset
        : 0.0;
    final previousMaxExtent = _scrollController.hasClients
        ? _scrollController.position.maxScrollExtent
        : 0.0;
    setState(() => _assistantLoadingOlderHistory = true);
    final splitIndex = math.max(
      0,
      _assistantHiddenHistory.length - _assistantHistoryPageSize,
    );
    final olderChunk = _assistantHiddenHistory.sublist(splitIndex);
    final remainingHidden = _assistantHiddenHistory.sublist(0, splitIndex);
    setState(() {
      _messages = List<Map<String, dynamic>>.from(<Map<String, dynamic>>[
        ...olderChunk,
        ..._messages,
      ]);
      _assistantHiddenHistory = List<Map<String, dynamic>>.from(
        remainingHidden,
      );
      _assistantLoadingOlderHistory = false;
      _showAssistantHistoryPeek = remainingHidden.isNotEmpty;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      final nextMaxExtent = _scrollController.position.maxScrollExtent;
      final delta = nextMaxExtent - previousMaxExtent;
      _scrollController.jumpTo(previousOffset + delta);
    });
  }

  void _scrollToBottomIfOverflow() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      final max = _scrollController.position.maxScrollExtent;
      if (max > 0) _scrollController.jumpTo(max);
    });
  }

  @override
  void deactivate() {
    if (!_isAssistantConversation) {
      ref.read(realtimeConnectionManagerProvider.notifier).onLeaveChatDetail();
    }
    super.deactivate();
  }

  @override
  void dispose() {
    _assistantProgressTimer?.cancel();
    _scrollController.removeListener(_onScrollChanged);
    _inputController.removeListener(_onInputChanged);
    _speechToText.cancel();
    _inputController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  void _startAssistantProgress() {
    _assistantProgressTimer?.cancel();
    _assistantProgressStartedAt = DateTime.now();
    _assistantProgressTimer = Timer.periodic(
      const Duration(milliseconds: 500),
      (_) {
        if (!mounted || !_assistantResponding) return;
        final startedAt = _assistantProgressStartedAt;
        if (startedAt == null) return;
        final elapsedMs = DateTime.now().difference(startedAt).inMilliseconds;
        setState(() {
          _currentJourneyElapsedMs = elapsedMs;
        });
      },
    );
  }

  void _stopAssistantProgress() {
    _assistantProgressTimer?.cancel();
    _assistantProgressTimer = null;
    final startedAt = _assistantProgressStartedAt;
    _assistantProgressStartedAt = null;
    if (!mounted || startedAt == null) return;
    final elapsedMs = DateTime.now().difference(startedAt).inMilliseconds;
    setState(() {
      _currentJourneyElapsedMs = elapsedMs;
    });
  }

  /// 保证 _messages 为可扩容列表，避免定长列表导致 add/addAll 抛 UnsupportedError。
  void _ensureMessagesGrowable() {
    _messages = List<Map<String, dynamic>>.from(_messages);
  }

  AssistantBackend _preferredAssistantBackendOnOpen() {
    final hinted =
        widget.assistantOpenContext?.hints['assistantBackend']?.toString() ??
        '';
    if (hinted.trim().isNotEmpty) {
      return _resolveAvailableAssistantBackend(parseAssistantBackend(hinted));
    }
    return _resolveAvailableAssistantBackend(AssistantBackend.remote);
  }

  AssistantBackend _resolveAvailableAssistantBackend(AssistantBackend backend) {
    final remoteConfigured = mounted
        ? ref.read(assistantRemoteConfiguredProvider)
        : _assistantRemoteConfiguredCached;
    _assistantRemoteConfiguredCached = remoteConfigured;
    if (backend == AssistantBackend.remote && !remoteConfigured) {
      return AssistantBackend.local;
    }
    return backend;
  }

  String get _effectiveAssistantSessionId {
    if (!_isAssistantConversation) return widget.conversationId;
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

  Future<bool> _syncAssistantSessionInfo() async {
    if (!_isAssistantConversation) return false;
    if (_assistantBackend != AssistantBackend.local) return false;
    final sessions = await ref.read(assistantGatewayProvider).listSessions();
    if (!mounted || sessions.isEmpty) return false;
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
    if (nextSessionId.isNotEmpty) {
      setState(() {
        _assistantBackend = assistantBackendForSessionId(nextSessionId);
        _assistantRuntimeSessionId = nextSessionId;
        _assistantTopicTitle = (nextTopic?.isNotEmpty ?? false)
            ? nextTopic!
            : UITextConstants.assistantHistoryAll;
      });
      await _loadAssistantSessionMessages(nextSessionId);
      return true;
    }
    return false;
  }

  Future<void> _loadAssistantSessionMessages(String sessionId) async {
    if (!_isAssistantConversation || sessionId.trim().isEmpty) return;
    final detail = await ref
        .read(assistantGatewayProvider)
        .sessionDetail(sessionId);
    if (!mounted || detail == null) return;
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
            'conversationId': widget.conversationId,
            'type': 'text',
            'content': normalizedContent,
            'senderId': isUser
                ? 'current_user'
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
    setState(() {
      _assistantHiddenHistory = List<Map<String, dynamic>>.from(hiddenHistory);
      _assistantLoadingOlderHistory = false;
      _showAssistantHistoryPeek = hiddenHistory.isNotEmpty;
      _messages = List<Map<String, dynamic>>.from(visibleMessages);
      final topic = (detail['topicTitle'] as String?)?.trim();
      if (topic != null && topic.isNotEmpty) {
        _assistantTopicTitle = topic;
      }
    });
    _scrollToBottomIfOverflow();
  }

  Future<void> _switchAssistantSession(String sessionId) async {
    if (sessionId.trim().isEmpty) return;
    final backend = _resolveAvailableAssistantBackend(
      assistantBackendForSessionId(sessionId),
    );
    final resolvedSessionId = isAssistantSessionForBackend(sessionId, backend)
        ? sessionId
        : newAssistantSessionId(backend);
    if (backend == AssistantBackend.local) {
      await ref.read(assistantGatewayProvider).switchSession(resolvedSessionId);
    }
    if (!mounted) return;
    setState(() {
      _assistantBackend = backend;
      _assistantRuntimeSessionId = resolvedSessionId;
      if (backend == AssistantBackend.remote) {
        _assistantTopicTitle = UITextConstants.assistantHistoryAll;
      }
    });
    if (backend == AssistantBackend.local) {
      await _loadAssistantSessionMessages(resolvedSessionId);
      return;
    }
    setState(() {
      _assistantHiddenHistory = <Map<String, dynamic>>[];
      _assistantLoadingOlderHistory = false;
      _showAssistantHistoryPeek = false;
      _messages = List<Map<String, dynamic>>.from(
        const <Map<String, dynamic>>[],
      );
    });
  }

  Future<String> _selectAssistantBackend(AssistantBackend backend) async {
    final resolvedBackend = _resolveAvailableAssistantBackend(backend);
    if (!_isAssistantConversation) return widget.conversationId;
    if (resolvedBackend == _assistantBackend &&
        isAssistantSessionForBackend(
          _effectiveAssistantSessionId,
          resolvedBackend,
        )) {
      return _effectiveAssistantSessionId;
    }
    if (!mounted) return _effectiveAssistantSessionId;
    setState(() {
      _assistantBackend = resolvedBackend;
      _assistantRuntimeSessionId = newAssistantSessionId(resolvedBackend);
      _assistantTopicTitle = UITextConstants.assistantHistoryAll;
      _assistantHiddenHistory = <Map<String, dynamic>>[];
      _assistantLoadingOlderHistory = false;
      _showAssistantHistoryPeek = false;
      _messages = List<Map<String, dynamic>>.from(
        const <Map<String, dynamic>>[],
      );
    });
    if (resolvedBackend == AssistantBackend.local) {
      final synced = await _syncAssistantSessionInfo();
      if (!mounted || synced) return _effectiveAssistantSessionId;
    }
    return _effectiveAssistantSessionId;
  }

  Stream<AssistantRunStreamEvent> _runAssistantStream(
    AssistantRunRequest request,
  ) {
    _assistantBackend = _resolveAvailableAssistantBackend(_assistantBackend);
    switch (_assistantBackend) {
      case AssistantBackend.local:
        return ref
            .read(localAssistantEntryProvider)
            .runStream(request: request);
      case AssistantBackend.remote:
        return ref
            .read(remoteAssistantEntryProvider)
            .runStream(request: request);
    }
  }

  /// 构建输入区 `+` 面板中的通话入口项
  /// 1v1：语音通话 / 视频通话（需同好关系才可见，当前阶段仅在已知对方 ID 时展示）
  /// 群聊：发起语音通话 / 发起视频通话（始终展示）
  List<ChatInputExtraPanelItem> _buildCallPanelItems() {
    final canCall =
        _isGroupChat ||
        (_otherParticipantId != null &&
            (_relationshipCapability?.canStartVoiceCall == true ||
                _relationshipCapability?.canStartVideoCall == true));
    if (!canCall) return const <ChatInputExtraPanelItem>[];
    final voiceLabel = _isGroupChat
        ? UITextConstants.callGroupVoice
        : UITextConstants.callVoice;
    final videoLabel = _isGroupChat
        ? UITextConstants.callGroupVideo
        : UITextConstants.callVideo;
    final items = <ChatInputExtraPanelItem>[
      ChatInputExtraPanelItem(
        icon: CupertinoIcons.phone,
        text: voiceLabel,
        onTap: () async => _initiateCall('voice'),
      ),
      ChatInputExtraPanelItem(
        icon: CupertinoIcons.video_camera,
        text: videoLabel,
        onTap: () async => _initiateCall('video'),
      ),
    ];
    if (kDebugMode) {
      items.addAll(<ChatInputExtraPanelItem>[
        ChatInputExtraPanelItem(
          icon: CupertinoIcons.phone_badge_plus,
          text: UITextConstants.callDebugSimulateIncomingVoice,
          onTap: () async => _simulateIncomingCall('voice'),
        ),
        ChatInputExtraPanelItem(
          icon: CupertinoIcons.video_camera_solid,
          text: UITextConstants.callDebugSimulateIncomingVideo,
          onTap: () async => _simulateIncomingCall('video'),
        ),
      ]);
    }
    return items;
  }

  Future<void> _initiateCall(String callType) async {
    final notifier = ref.read(callSessionProvider.notifier);
    final List<String> targetIds;
    if (_isGroupChat) {
      // 群聊：跳转选人页（<=8 人默认全选，>8 人默认不选）
      final result = await context.push<List<String>>(
        AppRoutePaths.rtcPickParticipants,
        extra: <String, dynamic>{
          'conversationId': widget.conversationId,
          'defaultSelectAll': _memberCount <= 8,
        },
      );
      if (result == null || result.isEmpty || !mounted) return;
      targetIds = result;
    } else {
      // 1v1：使用已加载的对方 ID（仅同好/密友可见入口，此处对方 ID 应已加载）
      final otherId = _otherParticipantId;
      if (otherId == null || otherId.isEmpty) return;
      targetIds = [otherId];
    }
    final callId = await notifier.initiateCall(
      callTypeStr: callType,
      targetUserIds: targetIds,
      conversationId: widget.conversationId,
    );
    if (callId != null && mounted) {
      context.push(AppRoutePaths.rtcOutgoing(callId: callId));
    }
  }

  Future<void> _simulateIncomingCall(String callType) async {
    final callId = 'debug_incoming_${DateTime.now().millisecondsSinceEpoch}';
    final callerName = _conversationTitle;
    ref
        .read(callSessionProvider.notifier)
        .debugSeedIncomingCall(
          callId: callId,
          callerName: callerName,
          callType: callType,
          conversationId: widget.conversationId,
        );
    if (!mounted) return;
    await context.push(AppRoutePaths.rtcIncoming(callId: callId));
  }

  Future<void> _sendSameInterestRequest() async {
    final otherId = _otherParticipantId;
    if (otherId == null || otherId.isEmpty) return;
    try {
      await ref
          .read(greetingRepositoryProvider)
          .sendGreeting(
            targetSubAccountId: otherId,
            requestMessage: '想和你成为同好，一起聊聊吧',
            source: 'chat',
          );
      if (!mounted) return;
      AppToast.show(context, '已发送同好邀请');
    } catch (_) {
      if (!mounted) return;
      AppToast.show(context, '发送失败，请稍后再试');
    }
  }

  Widget _buildSameInterestPromptBar() {
    return Container(
      width: double.infinity,
      margin: EdgeInsets.only(bottom: AppSpacing.sm),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        border: Border.all(
          color: AppColors.primaryColor.withValues(alpha: 0.18),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              '成为同好后可直接发起语音和视频通话',
              style: TextStyle(
                color: AppColors.primaryColor,
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          CupertinoButton(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.sm,
              vertical: AppSpacing.xs,
            ),
            color: AppColors.primaryColor,
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            onPressed: _sendSameInterestRequest,
            child: Text(
              UITextConstants.profileAddSameInterest,
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _openAssistantSettingsPage() async {
    await Navigator.of(context).push(
      CupertinoPageRoute<void>(
        builder: (_) => AssistantChatSettingsPage(
          currentSessionId: _effectiveAssistantSessionId,
          currentTopicTitle: _assistantTopicTitle,
          currentBackend: _assistantBackend,
          onOpenTrace: _openAssistantDevReplayPage,
          onSessionSelected: _switchAssistantSession,
          onBackendSelected: _selectAssistantBackend,
        ),
      ),
    );
    if (!mounted) return;
    await _syncAssistantSessionInfo();
  }

  AssistantJourneyViewModel _buildJourneyViewModel({
    required AssistantJourney journey,
    required bool isRunning,
    Map<String, dynamic> usageStats = const <String, dynamic>{},
    int? elapsedMs,
  }) {
    return buildAssistantJourneyViewModel(
      journey: journey,
      isRunning: isRunning,
      usageStats: usageStats,
      elapsedMs: elapsedMs ?? _currentJourneyElapsedMs,
    );
  }

  AssistantJourneyViewModel _journeyViewModelFromMessage(
    Map<String, dynamic> message, {
    bool isRunning = false,
  }) {
    return _buildJourneyViewModel(
      journey: resolveAssistantJourneyFromMessage(message),
      isRunning: isRunning,
      usageStats:
          (message['uiUsageStats'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      elapsedMs: ((message['assistantElapsedMs'] as num?)?.toInt() ?? 0),
    );
  }

  String _assistantPhaseLabelFromJourney(
    AssistantJourney journey, {
    required bool isRunning,
  }) {
    final viewModel = _buildJourneyViewModel(
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
    if (!mounted || !_assistantResponding) return;
    final messageId = _activeAssistantStreamingMessageId;
    setState(() {
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
            assistantUiProcessTimelineV2Field:
                buildAssistantUiProcessTimelineV2(journey).toJson(),
            'assistantElapsedMs': _currentJourneyElapsedMs,
          };
        }
      }
    });
    _autoScrollToBottomIfNeeded();
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
    if (!mounted) return;
    final messageId = _activeAssistantStreamingMessageId;
    if (messageId == null || messageId.isEmpty) return;
    final value = _visibleStreamingAnswerChunk(chunk);

    if (value.isEmpty) {
      return;
    }

    if (_isInternalChunk(value)) return;
    final now = DateTime.now();
    final ts = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
    setState(() {
      _ensureMessagesGrowable();
      final existingIndex = _messages.indexWhere(
        (item) => (item['id'] as String?) == messageId,
      );
      if (existingIndex >= 0) {
        final prev =
            (_messages[existingIndex]['streamFinalAnswer'] as String?) ?? '';
        final merged = _mergeStreamingAnswerText(
          previous: prev,
          incoming: value,
        );
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
          'conversationId': widget.conversationId,
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
      if (_shouldOpenAnswerGateForJourney(_currentJourney)) {
        _answerGateOpen = true;
      }
    });
    _autoScrollToBottomIfNeeded();
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

  String _actionLikeCompletedFallback(AssistantRunResponse response) {
    return resolveActionLikeCompletedFallback(response);
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
      // Backward-compatible fields expose当前轮数据；累计值走 cumulative* 字段。
      'modelCallCount': currentRunCalls,
      'totalTokens': currentRunTokens,
      'maxTokensPerCall': currentRunMaxTokens,
    };
  }

  void _autoScrollToBottomIfNeeded() {
    if (_userScrolledAway) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      final maxScroll = _scrollController.position.maxScrollExtent;
      final currentScroll = _scrollController.offset;
      if (maxScroll - currentScroll > 80) {
        _scrollController.animateTo(
          maxScroll,
          duration: const Duration(milliseconds: 150),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // XML tool-call patterns used by some model providers.
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

  String get _conversationTitle {
    if (widget.conversationId == AppConceptConstants.assistantConversationId) {
      return AppConceptConstants.assistantDisplayTitle;
    }
    if (_resolvedTitle != null) return _resolvedTitle!;
    _loadConversationTitle();
    return widget.conversationId;
  }

  bool get _isAssistantConversation =>
      widget.conversationId == AppConceptConstants.assistantConversationId;

  Widget _buildToolbarIconButton({
    required IconData icon,
    required VoidCallback onPressed,
    Color? color,
  }) {
    return SizedBox(
      width: AppSpacing.iconButtonMinSizeSm,
      height: AppSpacing.iconButtonMinSizeSm,
      child: IconButton(
        onPressed: onPressed,
        icon: Icon(icon, size: AppSpacing.iconMedium),
        color: color,
        padding: EdgeInsets.zero,
        constraints: const BoxConstraints(),
      ),
    );
  }

  Widget _buildAssistantComposerButton({
    required IconData icon,
    required VoidCallback onPressed,
    required Color fgPrimary,
    Color? backgroundColor,
    Key? buttonKey,
  }) {
    return GestureDetector(
      key: buttonKey,
      onTap: onPressed,
      child: Container(
        width: AppSpacing.buttonSize,
        height: AppSpacing.buttonSize,
        decoration: BoxDecoration(
          color: backgroundColor ?? Colors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.buttonSize),
        ),
        alignment: Alignment.center,
        child: Icon(icon, size: AppSpacing.iconMedium, color: fgPrimary),
      ),
    );
  }

  Widget _buildAssistantLeftButton(
    BuildContext context,
    ChatInputVisualState state,
    ChatInputDefaultActions actions,
  ) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    if (state.isVoiceMode) return const SizedBox.shrink();
    return _buildAssistantComposerButton(
      icon: Icons.add,
      fgPrimary: fgPrimary.withValues(alpha: 0.72),
      onPressed: () {
        setState(() => _showEmojiPanel = false);
        actions.toggleAddPanel();
      },
    );
  }

  List<Widget> _buildAssistantRightButtons(
    BuildContext context,
    ChatInputVisualState state,
    ChatInputDefaultActions actions,
  ) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    if (state.isVoiceMode) return const <Widget>[];
    if (state.hasText || state.hasAttachments) {
      return <Widget>[
        _buildAssistantComposerButton(
          icon: Icons.arrow_upward_rounded,
          fgPrimary: Colors.white,
          backgroundColor: AppColors.primaryColor,
          onPressed: actions.send,
          buttonKey: TestKeys.assistantSendButton,
        ),
      ];
    }
    return <Widget>[
      _buildAssistantComposerButton(
        icon: Icons.mic_none,
        fgPrimary: fgPrimary.withValues(alpha: 0.72),
        onPressed: actions.toggleVoiceMode,
      ),
    ];
  }

  Widget _buildQuliaoLeftButton(
    BuildContext context,
    ChatInputVisualState state,
    ChatInputDefaultActions actions,
  ) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    if (state.isVoiceMode) return const SizedBox.shrink();
    return _buildToolbarIconButton(
      icon: Icons.mic_none,
      color: fgPrimary.withValues(alpha: 0.5),
      onPressed: actions.toggleVoiceMode,
    );
  }

  List<Widget> _buildQuliaoRightButtons(
    BuildContext context,
    ChatInputVisualState state,
    ChatInputDefaultActions actions,
  ) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    if (state.isVoiceMode) return const <Widget>[];
    if (state.hasText || state.hasAttachments) {
      return <Widget>[
        _buildToolbarIconButton(
          icon: Icons.add,
          color: fgPrimary.withValues(alpha: 0.6),
          onPressed: () {
            setState(() => _showEmojiPanel = false);
            actions.toggleAddPanel();
          },
        ),
        SizedBox(width: AppSpacing.xs),
        GestureDetector(
          onTap: actions.send,
          child: Container(
            width: AppSpacing.buttonSize,
            height: AppSpacing.buttonSize,
            decoration: BoxDecoration(
              color: AppColors.primaryColor,
              borderRadius: BorderRadius.circular(AppSpacing.buttonSize),
            ),
            alignment: Alignment.center,
            child: Icon(
              Icons.arrow_upward_rounded,
              size: AppSpacing.iconMedium,
              color: Colors.white,
            ),
          ),
        ),
      ];
    }
    return <Widget>[
      _buildToolbarIconButton(
        icon: _showEmojiPanel ? Icons.keyboard_rounded : Icons.mood_outlined,
        color: fgPrimary.withValues(alpha: 0.5),
        onPressed: () {
          setState(() {
            _showEmojiPanel = !_showEmojiPanel;
            if (_showEmojiPanel) {
              _inputFocusNode.unfocus();
            }
          });
        },
      ),
      SizedBox(width: AppSpacing.xs),
      _buildToolbarIconButton(
        icon: Icons.add,
        color: fgPrimary.withValues(alpha: 0.6),
        onPressed: () {
          setState(() => _showEmojiPanel = false);
          actions.toggleAddPanel();
        },
      ),
    ];
  }

  Future<List<ChatInputAttachment>> _pickChatImages(int remaining) async {
    final picked = await _imagePicker.pickMultiImage(
      imageQuality: 85,
      limit: remaining,
    );
    return picked
        .take(remaining)
        .map(
          (x) => ChatInputAttachment(
            id: 'img_${DateTime.now().millisecondsSinceEpoch}_${x.name}',
            type: ChatInputAttachmentType.image,
            name: x.name,
            subtitle: '',
            thumbnailProvider: FileImage(
              // ignore: avoid_slow_async_io
              File(x.path),
            ),
          ),
        )
        .toList(growable: false);
  }

  Future<ChatInputAttachment?> _captureChatPhoto() async {
    final picked = await _imagePicker.pickImage(
      source: ImageSource.camera,
      imageQuality: 85,
    );
    if (picked == null) return null;
    return ChatInputAttachment(
      id: 'cam_${DateTime.now().millisecondsSinceEpoch}_${picked.name}',
      type: ChatInputAttachmentType.image,
      name: picked.name,
      thumbnailProvider: FileImage(
        // ignore: avoid_slow_async_io
        File(picked.path),
      ),
    );
  }

  Future<List<ChatInputAttachment>> _pickChatFiles(int remaining) async {
    final result = await FilePicker.platform.pickFiles(
      allowMultiple: true,
      withData: false,
    );
    if (result == null) return const <ChatInputAttachment>[];
    final now = DateTime.now().millisecondsSinceEpoch;
    return result.files
        .take(remaining)
        .map(
          (f) => ChatInputAttachment(
            id: 'file_${now}_${f.name}',
            type: ChatInputAttachmentType.file,
            name: f.name,
            subtitle: _formatFileSize(f.size),
          ),
        )
        .toList(growable: false);
  }

  String _formatFileSize(int bytes) {
    if (bytes < 1024) return '${bytes}B';
    if (bytes < 1024 * 1024) {
      return '${(bytes / 1024).toStringAsFixed(1)}KB';
    }
    if (bytes < 1024 * 1024 * 1024) {
      return '${(bytes / (1024 * 1024)).toStringAsFixed(2)}MB';
    }
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(2)}GB';
  }

  Future<bool> _ensureSpeechReady() async {
    if (_speechReady) return true;
    _speechReady = await _speechToText.initialize(
      onError: (_) {},
      onStatus: (_) {},
    );
    return _speechReady;
  }

  Future<bool> _requestMicPermissionForChat() async {
    final micStatus = await Permission.microphone.status;
    if (micStatus.isGranted) {
      return _ensureSpeechReady();
    }
    final requested = await Permission.microphone.request();
    if (requested.isGranted) {
      return _ensureSpeechReady();
    }
    if (requested.isPermanentlyDenied && mounted) {
      AppToast.show(context, UITextConstants.chatVoicePermissionDenied);
      openAppSettings();
    }
    return false;
  }

  Future<void> _startVoiceRecordForChat() async {
    _lastAsrText = '';
    if (!await _ensureSpeechReady()) return;
    if (_speechToText.isListening) {
      await _speechToText.stop();
    }
    await _speechToText.listen(
      onResult: (result) {
        _lastAsrText = result.recognizedWords.trim();
      },
      listenOptions: stt.SpeechListenOptions(
        partialResults: true,
        cancelOnError: true,
        listenMode: stt.ListenMode.dictation,
      ),
      localeId: 'zh_CN',
      pauseFor: const Duration(seconds: 2),
      listenFor: const Duration(minutes: 2),
    );
  }

  Future<void> _stopVoiceRecordForChat(Duration duration) async {
    if (_speechToText.isListening) {
      await _speechToText.stop();
    }
    await Future<void>.delayed(const Duration(milliseconds: 120));
  }

  Future<String?> _voiceAsrForChat(Duration duration) async {
    final text = _lastAsrText.trim();
    if (text.isNotEmpty) return text;
    if (duration.inMilliseconds < 500) return null;
    return '语音消息（${duration.inSeconds}s）';
  }

  Future<void> _submitChatInput(ChatInputSubmitPayload payload) async {
    if (payload.attachments.isNotEmpty) {
      final attachmentMessages = payload.attachments
          .map((item) {
            final kind = item.type == ChatInputAttachmentType.image
                ? UITextConstants.chatMorePhoto
                : UITextConstants.chatMoreFile;
            return <String, dynamic>{
              'id':
                  'msg_attachment_${DateTime.now().millisecondsSinceEpoch}_${item.id}',
              'conversationId': widget.conversationId,
              'type': 'text',
              'content': '[$kind] ${item.name}',
              'senderId': 'current_user',
              'senderName': '我',
              'senderAvatar':
                  'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400',
              'timestamp': '',
              'status': 'sending',
              'isRead': true,
              'isSelf': true,
            };
          })
          .toList(growable: false);
      setState(() {
        _ensureMessagesGrowable();
        _messages.addAll(attachmentMessages);
      });
    }

    var text = payload.text.trim();
    if (payload.isVoiceMessage && text.isEmpty) {
      text = '语音消息（${payload.voiceDuration.inSeconds}s）';
    }
    if (text.isNotEmpty) {
      await _sendMessage(draftText: text);
    }
  }

  Future<void> _sendMessage({String? draftText}) async {
    _inputFocusNode.unfocus();
    await Future<void>.delayed(const Duration(milliseconds: 150));
    final text = (draftText ?? _inputController.text).trim();
    if (text.isEmpty) return;

    if (!_isAssistantConversation) {
      if (draftText == null) _inputController.clear();
      ref
          .read(chatMessageProvider(widget.conversationId).notifier)
          .sendMessage('text', text);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scrollController.hasClients) {
          _scrollController.animateTo(
            _scrollController.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOut,
          );
        }
      });
      return;
    }

    final userMessageId = 'msg_${DateTime.now().millisecondsSinceEpoch}';
    setState(() {
      _ensureMessagesGrowable();
      _messages.add({
        'id': userMessageId,
        'conversationId': widget.conversationId,
        'type': 'text',
        'content': text,
        'senderId': 'current_user',
        'senderName': '我',
        'senderAvatar':
            'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=400',
        'timestamp': '',
        'status': 'sending',
        'isRead': true,
        'isSelf': true,
      });
    });
    if (draftText == null) {
      _inputController.clear();
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });

    if (_isAssistantConversation) {
      String? streamingAssistantMessageId;
      final streamNow = DateTime.now();
      final streamTs =
          '${streamNow.hour}:${streamNow.minute.toString().padLeft(2, '0')}';
      _resetStreamingAnswerDecoder();
      setState(() {
        _ensureMessagesGrowable();
        streamingAssistantMessageId =
            'assistant_stream_${DateTime.now().millisecondsSinceEpoch}';
        _activeAssistantStreamingMessageId = streamingAssistantMessageId;
        _answerGateOpen = false;
        _assistantResponding = true;
        _assistantPhaseLabel = UITextConstants.assistantPhaseUnderstanding;
        _currentJourney = const AssistantJourney();
        _currentJourneyElapsedMs = 0;
        _userScrolledAway = false;
        _showScrollFab = false;
        _messages.add(<String, dynamic>{
          'id': streamingAssistantMessageId!,
          'conversationId': widget.conversationId,
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
          assistantUiProcessTimelineV2Field: const <String, dynamic>{},
          assistantFollowupPromptField: '',
          assistantActionHintsField: const <String>[],
          'assistantElapsedMs': 0,
        });
      });
      _startAssistantProgress();
      try {
        final deviceProfile = _assistantDeviceProfileByWidth(
          _lastViewportWidth,
        );
        if (_assistantBackend == AssistantBackend.local) {
          try {
            await ref.read(assistantGatewayProvider).ensureRemoteConfigLoaded();
          } catch (error) {
            if (kDebugMode) {
              debugPrint(
                'Assistant remote config load failed, continue: $error',
              );
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
        final contextScope = _buildAssistantContextScope();
        final request = AssistantRunRequest(
          messages: assistantMessages,
          sessionId: _effectiveAssistantSessionId,
          userId: 'current_user',
          deviceProfile: deviceProfile,
          channel: 'app',
          capabilityCatalog: AssistantCapabilityCatalog.defaultCatalog,
          contextScopeHint: contextScope,
          privacyProfile: 'default',
          privacyPolicy:
              (contextScope['privacyPolicy'] as Map?)
                  ?.cast<String, dynamic>() ??
              const <String, dynamic>{},
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
          // Provider 链初始化失败、stream 迭代异常等均在此捕获，
          // 转为 degraded response 而非让外层 catch 吞掉诊断信息。
          if (kDebugMode) {
            debugPrint('[ChatPage] stream error: $streamError');
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
        final displayMarkdown =
            AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
              runResponse.displayMarkdown.trim().isNotEmpty
                  ? runResponse.displayMarkdown
                  : displayText,
              allowJsonExtraction: runResponse.displayMarkdown
                  .trim()
                  .isNotEmpty,
            );
        _resetStreamingAnswerDecoder();
        final resolvedSessionId =
            (runResponse.structuredResponse['effectiveSessionId'] as String?)
                ?.trim() ??
            '';
        final effectiveSessionId =
            isAssistantSessionForBackend(resolvedSessionId, _assistantBackend)
            ? resolvedSessionId
            : _effectiveAssistantSessionId;
        final activeTopicTitle =
            (runResponse.structuredResponse['activeTopicTitle'] as String?)
                ?.trim();
        final dialogueRuntime =
            (runResponse.structuredResponse['dialogueRuntime'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final elapsedMs = DateTime.now()
            .difference(runStartedAt)
            .inMilliseconds;
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
        final resolvedJourney = resolveAssistantJourneyFromResponse(
          runResponse,
        );
        final effectiveJourney = resolvedJourney.isEmpty
            ? _currentJourney
            : resolvedJourney;
        if (!mounted) return;
        setState(() {
          _currentJourney = effectiveJourney;
          _currentJourneyElapsedMs = elapsedMs;
          final persistedTurnFields =
              _buildAssistantPersistedTurnFieldsForResponse(
                response: runResponse,
                journey: effectiveJourney,
                displayMarkdown: displayMarkdown,
                displayPlainText: displayPlainText,
                elapsedMs: elapsedMs,
              );
          _ensureMessagesGrowable();
          if (streamingAssistantMessageId != null) {
            final existingIndex = _messages.indexWhere(
              (item) => (item['id'] as String?) == streamingAssistantMessageId,
            );
            if (existingIndex >= 0) {
              final existingMessage = _messages[existingIndex];
              final effectiveDisplayText = _reconcileCompletedAnswerText(
                streamedText:
                    (existingMessage['streamFinalAnswer'] as String?) ?? '',
                completedText: displayText,
              );
              _messages[existingIndex] = <String, dynamic>{
                ...existingMessage,
                'content': effectiveDisplayText,
                'timestamp': replyTime,
                'runId': runResponse.runId ?? '',
                'traceId': runResponse.traceId ?? '',
                'sourceQuery': text,
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
                'runArtifacts':
                    runResponse.runArtifacts?.toJson() ??
                    const <String, dynamic>{},
                'domainId': (dialogueRuntime['domainId'] ?? '').toString(),
                'dialogueState': dialogueRuntime,
                'uiReferences': uiReferences,
                'uiActions': uiActions,
                'uiUsageStats': uiUsageStats,
                ...persistedTurnFields,
                'streamFinalAnswer': '',
                'streaming': false,
              };
            }
          } else {
            _messages.add({
              'id': assistantMessageId,
              'conversationId': widget.conversationId,
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
              'sourceQuery': text,
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
              'runArtifacts':
                  runResponse.runArtifacts?.toJson() ??
                  const <String, dynamic>{},
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
          if (effectiveSessionId.isNotEmpty) {
            _assistantRuntimeSessionId = effectiveSessionId;
          }
          if (activeTopicTitle != null && activeTopicTitle.isNotEmpty) {
            _assistantTopicTitle = activeTopicTitle;
          }
        });
        _stopAssistantProgress();
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scrollController.hasClients) {
            _scrollController.animateTo(
              _scrollController.position.maxScrollExtent,
              duration: const Duration(milliseconds: 240),
              curve: Curves.easeOut,
            );
          }
        });
        final userTags =
            (contextScope['userTags'] as List?)
                ?.whereType<String>()
                .map((item) => item.trim())
                .where((item) => item.isNotEmpty)
                .toList(growable: false) ??
            const <String>[];
        _storeAssistantReplayRecord(
          messageId: assistantMessageId,
          query: text,
          response: runResponse,
        );
        await ref
            .read(assistantLearningServiceProvider)
            .recordInteraction(
              runId:
                  runResponse.runId ??
                  'run_${DateTime.now().millisecondsSinceEpoch}',
              traceId:
                  runResponse.traceId ??
                  'trace_${DateTime.now().millisecondsSinceEpoch}',
              userId: 'current_user',
              sessionId: _effectiveAssistantSessionId,
              pageType: (contextScope['pageType'] as String?) ?? 'chat',
              queryText: text,
              answerText: _resolveAssistantDisplayPlainText(runResponse),
              userTags: userTags,
              durationMs: elapsedMs,
            );
      } catch (e, st) {
        if (kDebugMode) {
          debugPrint('[ChatPage] assistant run failed: $e');
          debugPrint('$st');
        }
        if (!mounted) return;
        // 外层 catch 是最后防线：包含错误类型用于诊断，
        // 正常路径下不应到达此处（stream 错误已在内层 catch 处理）。
        final errorHint = kDebugMode ? '助手异常: ${e.runtimeType}' : '助手出现异常，请重试。';
        _resetStreamingAnswerDecoder();
        setState(() {
          _ensureMessagesGrowable();
          _assistantResponding = false;
          _assistantPhaseLabel = '';
          _activeAssistantStreamingMessageId = null;
          if (streamingAssistantMessageId != null) {
            _messages.removeWhere(
              (item) => (item['id'] as String?) == streamingAssistantMessageId,
            );
          }
          _messages.add({
            'id': 'assistant_err_${DateTime.now().millisecondsSinceEpoch}',
            'conversationId': widget.conversationId,
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
        });
        _stopAssistantProgress();
      }
    }
  }

  String _assistantDeviceProfileByWidth(double width) {
    if (width >= 600) return 'pc';
    if (width >= 360) return 'tablet';
    return 'mobile';
  }

  Map<String, dynamic> _buildAssistantContextScope() {
    final openContext = widget.assistantOpenContext;
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
    final contentAccessState = ref.read(personalContentAccessProvider);
    final identityIndexFeatureFlag = ref.read(
      contentFeatureFlagProvider('enable_assistant_content_identity_index'),
    );
    final identityIndexEnabled = ref.read(
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
    return <String, dynamic>{
      'pageType': _assistantSourceToPageType(openContext?.source),
      'sessionId': _effectiveAssistantSessionId,
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

  String _resolveAssistantDisplayText(AssistantRunResponse response) {
    final displayText = _firstCompletedDisplayCandidate(<String>[
      response.displayMarkdown,
      response.displayPlainText,
    ]);
    if (displayText.isNotEmpty) {
      return displayText;
    }
    final actionFallback = _actionLikeCompletedFallback(response);
    if (actionFallback.isNotEmpty) {
      return actionFallback;
    }

    return '助手未生成有效回答，请重试。';
  }

  String _resolveAssistantDisplayPlainText(AssistantRunResponse response) {
    final artifactPlain =
        AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
          response.displayPlainText,
          allowJsonExtraction: false,
        );
    if (artifactPlain.isNotEmpty) {
      return artifactPlain;
    }
    final artifactMarkdown =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
          response.displayMarkdown,
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

  /// 判断文本是否为内部 JSON 信封 / think 标签残留 / XML tool-call / 结构化协议字段，
  /// 不应展示给用户。
  bool _isInternalChunk(String value) {
    final t = value.trim();
    if (t.isEmpty) return false;
    if (t == '</think>' || t == '<think>') return true;
    if (AssistantContentFilters.isJsonEnvelope(t)) return true;
    if (AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
      t,
    )) {
      return true;
    }
    // XML tool-call blocks that some models (Qwen) output
    if (_containsXmlToolCall(t)) {
      // If after stripping XML there is no remaining readable content → internal
      final stripped = _stripXmlToolCalls(t);
      if (stripped.isEmpty) return true;
    }
    // 额外检查：包含 JSON 结构化关键字但不含可读内容
    if (t.startsWith('{') || t.startsWith('```')) {
      final parsed = LlmResponseParser.parse(t);
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
      'runArtifacts':
          response.runArtifacts?.toJson() ?? const <String, dynamic>{},
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

  Future<void> _submitAssistantFeedback({
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
    final contextScope = _buildAssistantContextScope();
    final userTags =
        (contextScope['userTags'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    await ref
        .read(assistantLearningServiceProvider)
        .recordExplicitFeedback(
          runId: runId.isNotEmpty
              ? runId
              : 'run_${DateTime.now().millisecondsSinceEpoch}',
          traceId: traceId.isNotEmpty
              ? traceId
              : 'trace_${DateTime.now().millisecondsSinceEpoch}',
          userId: 'current_user',
          sessionId: _effectiveAssistantSessionId,
          pageType: (contextScope['pageType'] as String?) ?? 'chat',
          queryText: query,
          answerText: (message['content'] as String?) ?? '',
          userTags: userTags,
          explicitThumb: explicitThumb,
          explicitReasonCodes: reasonCodes,
          correctionText: correctionText,
          feedbackTargetMessageId: messageId,
        );
    if (!mounted) return;
    final statusLabel = explicitThumb == 'up'
        ? UITextConstants.assistantFeedbackHelpful
        : UITextConstants.assistantFeedbackUnhelpful;
    setState(() {
      _assistantFeedbackStatusByMessageId[messageId] = statusLabel;
    });
    AppToast.show(context, UITextConstants.assistantFeedbackSubmitted);
  }

  Future<void> _showAssistantNegativeFeedbackSheet(
    Map<String, dynamic> message,
  ) async {
    final reasons = <MapEntry<String, String>>[
      MapEntry('off_topic', UITextConstants.assistantFeedbackReasonOffTopic),
      MapEntry(
        'insufficient',
        UITextConstants.assistantFeedbackReasonInsufficient,
      ),
      MapEntry('incorrect', UITextConstants.assistantFeedbackReasonIncorrect),
      MapEntry('style', UITextConstants.assistantFeedbackReasonStyle),
      MapEntry('privacy', UITextConstants.assistantFeedbackReasonPrivacy),
    ];
    final selected = <String>{};
    final submitted = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            return SafeArea(
              child: Padding(
                padding: EdgeInsets.all(
                  AppSpacing.semantic[DesignSemanticConstants
                          .container]?[DesignSemanticConstants.md] ??
                      AppSpacing.containerMd,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      UITextConstants.assistantFeedbackReasonTitle,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: AppSpacing.sm),
                    Wrap(
                      spacing: AppSpacing.xs,
                      runSpacing: AppSpacing.xs,
                      children: reasons
                          .map((reason) {
                            final isSelected = selected.contains(reason.key);
                            return FilterChip(
                              label: Text(reason.value),
                              selected: isSelected,
                              onSelected: (_) {
                                setSheetState(() {
                                  if (isSelected) {
                                    selected.remove(reason.key);
                                  } else {
                                    selected.add(reason.key);
                                  }
                                });
                              },
                            );
                          })
                          .toList(growable: false),
                    ),
                    SizedBox(height: AppSpacing.md),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: () => Navigator.of(context).pop(true),
                        child: Text(UITextConstants.confirm),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
    if (submitted != true) return;
    await _submitAssistantFeedback(
      message: message,
      explicitThumb: 'down',
      reasonCodes: selected.toList(growable: false),
    );
  }

  Future<void> _showAssistantCorrectionSheet(
    Map<String, dynamic> message,
  ) async {
    final controller = TextEditingController();
    final submitted = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      builder: (context) {
        return Padding(
          padding: EdgeInsets.only(
            left:
                AppSpacing.semantic[DesignSemanticConstants
                    .container]?[DesignSemanticConstants.md] ??
                AppSpacing.containerMd,
            right:
                AppSpacing.semantic[DesignSemanticConstants
                    .container]?[DesignSemanticConstants.md] ??
                AppSpacing.containerMd,
            top:
                AppSpacing.semantic[DesignSemanticConstants
                    .container]?[DesignSemanticConstants.md] ??
                AppSpacing.containerMd,
            bottom:
                MediaQuery.of(context).viewInsets.bottom +
                AppSpacing.containerMd,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                UITextConstants.assistantCorrectionTitle,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: FontWeight.w600,
                ),
              ),
              SizedBox(height: AppSpacing.sm),
              TextField(
                controller: controller,
                minLines: 2,
                maxLines: 4,
                decoration: InputDecoration(
                  hintText: UITextConstants.assistantCorrectionHint,
                  border: const OutlineInputBorder(),
                ),
              ),
              SizedBox(height: AppSpacing.sm),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: () => Navigator.of(context).pop(true),
                  child: Text(UITextConstants.confirm),
                ),
              ),
            ],
          ),
        );
      },
    );
    if (submitted != true) return;
    final correction = controller.text.trim();
    if (correction.isEmpty) return;
    await _submitAssistantFeedback(
      message: message,
      explicitThumb: 'down',
      reasonCodes: const <String>['correction'],
      correctionText: correction,
    );
  }

  Future<void> _recordAssistantImplicitFeedback({
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
    final contextScope = _buildAssistantContextScope();
    final tags = userTags.isNotEmpty
        ? userTags
        : ((contextScope['userTags'] as List?)
                  ?.whereType<String>()
                  .map((item) => item.trim())
                  .where((item) => item.isNotEmpty)
                  .toList(growable: false) ??
              const <String>[]);
    await ref
        .read(assistantLearningServiceProvider)
        .recordInteraction(
          runId: (message['runId'] as String?)?.trim().isNotEmpty == true
              ? (message['runId'] as String).trim()
              : 'run_${DateTime.now().millisecondsSinceEpoch}',
          traceId: (message['traceId'] as String?)?.trim().isNotEmpty == true
              ? (message['traceId'] as String).trim()
              : 'trace_${DateTime.now().millisecondsSinceEpoch}',
          userId: 'current_user',
          sessionId: _effectiveAssistantSessionId,
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

  Future<void> _requestAssistantRewrite({
    required Map<String, dynamic> message,
    required String mode,
  }) async {
    final query = (message['sourceQuery'] as String?)?.trim() ?? '';
    if (query.isEmpty) return;
    final text = switch (mode) {
      'brief' => '请基于同样问题给我更简洁版本：$query',
      'detailed' => '请基于同样问题给我更详细版本：$query',
      _ => query,
    };
    await _recordAssistantImplicitFeedback(
      message: message,
      regeneratedAnswer: mode == 'regenerate',
      styleAdjusted: mode == 'brief' || mode == 'detailed',
      userTags: <String>[mode],
    );
    _inputController.text = text;
    await _sendMessage();
  }

  Future<void> _requestAssistantRewriteV2({
    required Map<String, dynamic> message,
    required RegenerateOption option,
  }) async {
    final originalQuery = (message['sourceQuery'] as String?)?.trim() ?? '';
    if (originalQuery.isEmpty) return;
    final previousAnswer =
        (message['content'] as String?)?.trim() ??
        (message['streamFinalAnswer'] as String?)?.trim() ??
        '';
    final rewriteMode = switch (option) {
      RegenerateOption.regenerate => RewriteMode.regenerate,
      RegenerateOption.concise => RewriteMode.concise,
      RegenerateOption.detailed => RewriteMode.detailed,
      RegenerateOption.casual => RewriteMode.casual,
      RegenerateOption.deepThink => RewriteMode.deepThink,
    };
    await _recordAssistantImplicitFeedback(
      message: message,
      regeneratedAnswer: option == RegenerateOption.regenerate,
      styleAdjusted:
          option == RegenerateOption.concise ||
          option == RegenerateOption.detailed ||
          option == RegenerateOption.casual,
      userTags: <String>[option.name],
    );
    await _sendAssistantMessageWithRewrite(
      query: originalQuery,
      rewrite: RewriteInstruction(
        mode: rewriteMode,
        originalQuery: originalQuery,
        previousAnswer: previousAnswer,
      ),
    );
  }

  Future<void> _sendAssistantMessageWithRewrite({
    required String query,
    required RewriteInstruction rewrite,
  }) async {
    if (_assistantResponding) return;
    final now = DateTime.now();
    final ts = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
    setState(() {
      _ensureMessagesGrowable();
      _messages.add(<String, dynamic>{
        'id': 'user_rewrite_${now.millisecondsSinceEpoch}',
        'conversationId': widget.conversationId,
        'type': 'text',
        'content': _rewriteUserLabel(rewrite.mode),
        'senderId': 'current_user',
        'senderName': '',
        'timestamp': ts,
        'isRead': true,
        'isSelf': true,
      });
    });
    final contextScope = _buildAssistantContextScope();
    final request = AssistantRunRequest(
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: query),
      ],
      sessionId: _assistantRuntimeSessionId,
      userId: contextScope['userId'] as String? ?? '',
      maxIterations: rewrite.mode == RewriteMode.deepThink ? 6 : 1,
      capabilityCatalog: AssistantCapabilityCatalog.defaultCatalog,
      contextScopeHint: contextScope,
      rewriteInstruction: rewrite,
    );
    String? streamingAssistantMessageId;
    _resetStreamingAnswerDecoder();
    setState(() {
      _ensureMessagesGrowable();
      streamingAssistantMessageId =
          'assistant_rewrite_${now.millisecondsSinceEpoch}';
      _activeAssistantStreamingMessageId = streamingAssistantMessageId;
      _answerGateOpen = false;
      _assistantResponding = true;
      _assistantPhaseLabel = UITextConstants.assistantPhaseAnswering;
      _currentJourney = const AssistantJourney();
      _currentJourneyElapsedMs = 0;
      _messages.add(<String, dynamic>{
        'id': streamingAssistantMessageId!,
        'conversationId': widget.conversationId,
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
        assistantUiProcessTimelineV2Field: const <String, dynamic>{},
        assistantFollowupPromptField: '',
        assistantActionHintsField: const <String>[],
        'assistantElapsedMs': 0,
      });
    });
    _startAssistantProgress();
    _autoScrollToBottomIfNeeded();
    try {
      AssistantRunResponse? response;
      if (_assistantBackend == AssistantBackend.local) {
        try {
          await ref.read(assistantGatewayProvider).ensureRemoteConfigLoaded();
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
      if (response != null && mounted) {
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
        final effectiveJourney = resolvedJourney.isEmpty
            ? _currentJourney
            : resolvedJourney;
        final finalText = _resolveAssistantDisplayText(finalResponse);
        final displayPlainText = _resolveAssistantDisplayPlainText(
          finalResponse,
        );
        final displayMarkdown =
            AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
              finalResponse.displayMarkdown.trim().isNotEmpty
                  ? finalResponse.displayMarkdown
                  : finalText,
              allowJsonExtraction: finalResponse.displayMarkdown
                  .trim()
                  .isNotEmpty,
            );
        _resetStreamingAnswerDecoder();
        setState(() {
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
                  (finalResponse
                              .structuredResponse['phaseOneRoutingDiagnostics']
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
              'runArtifacts':
                  finalResponse.runArtifacts?.toJson() ??
                  const <String, dynamic>{},
              'uiUsageStats': uiUsageStats,
              ...persistedTurnFields,
            };
          }
        });
      }
    } catch (_) {
      // Swallow exceptions; message will show whatever was streamed.
    } finally {
      _resetStreamingAnswerDecoder();
      if (mounted) {
        setState(() {
          _assistantResponding = false;
          _assistantPhaseLabel = '';
          _activeAssistantStreamingMessageId = null;
        });
      }
      _stopAssistantProgress();
    }
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

  Future<void> _switchAssistantModelAndRegenerate(
    Map<String, dynamic> message,
  ) async {
    final models = ref.read(assistantGatewayProvider).listAvailableModels();
    if (models.isEmpty) {
      if (!mounted) return;
      AppToast.show(context, UITextConstants.assistantModelUnavailable);
      return;
    }
    final selected = await showModalBottomSheet<String>(
      context: context,
      builder: (context) {
        return SafeArea(
          child: ListView(
            shrinkWrap: true,
            children: models
                .map(
                  (modelRef) => ListTile(
                    title: Text(modelRef),
                    onTap: () => Navigator.of(context).pop(modelRef),
                  ),
                )
                .toList(growable: false),
          ),
        );
      },
    );
    if (selected == null || selected.trim().isEmpty) return;
    ref.read(assistantGatewayProvider).switchModel(selected);
    await _recordAssistantImplicitFeedback(
      message: message,
      modelSwitched: true,
      userTags: <String>['model_switch'],
    );
    await _requestAssistantRewrite(message: message, mode: 'regenerate');
  }

  Future<void> _onAssistantReferenceTap(
    Map<String, dynamic> message,
    Map<String, dynamic> reference,
  ) async {
    final url = (reference['url'] as String?)?.trim() ?? '';
    if (url.isEmpty) return;
    final uri = Uri.tryParse(url);
    final allowOpen = uri != null && _isAssistantReferenceHostAllowed(uri);
    var opened = false;
    if (allowOpen) {
      opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
    if (!opened || !allowOpen) {
      await Clipboard.setData(ClipboardData(text: url));
    }
    if (!mounted) return;
    AppToast.show(
      context,
      opened
          ? url
          : allowOpen
          ? UITextConstants.assistantReferenceOpenFailed
          : UITextConstants.assistantReferenceHostBlocked,
    );
    await _recordAssistantImplicitFeedback(
      message: message,
      referenceOpened: true,
      userTags: const <String>['reference_click'],
    );
  }

  List<String> _assistantReferenceWhitelistHosts() {
    final contextScope = _buildAssistantContextScope();
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

  bool _isAssistantReferenceHostAllowed(Uri uri) {
    if (uri.scheme != 'https') return false;
    final host = uri.host.trim().toLowerCase();
    if (host.isEmpty) return false;
    final whitelist = _assistantReferenceWhitelistHosts();
    if (whitelist.isEmpty) return false;
    for (final allowed in whitelist) {
      if (host == allowed || host.endsWith('.$allowed')) {
        return true;
      }
    }
    return false;
  }

  void _openAssistantDevReplayPage() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => AssistantDevReplayPage(
          records: List<Map<String, dynamic>>.from(_assistantReplayRecords),
          loadScoreSnapshot: () =>
              ref.read(assistantLearningServiceProvider).latestScoreSnapshot(),
        ),
      ),
    );
  }

  void _onLongPressMessage(
    Map<String, dynamic> message,
    Offset globalPosition,
  ) {
    setState(() {
      _actionMenuMessage = message;
      _actionMenuPosition = globalPosition;
    });
  }

  void _onMessageAction(String action) {
    final msg = _actionMenuMessage;
    if (msg == null) return;
    switch (action) {
      case 'forward':
        _shareMessages(<Map<String, dynamic>>[msg]);
        break;
      case 'select':
        setState(() {
          _isSelectionMode = true;
          _selectedIds.add(msg['id'] as String);
        });
        break;
      case 'copy':
        final content = msg['content'] as String? ?? '';
        if (content.isNotEmpty) {
          Clipboard.setData(ClipboardData(text: content));
          if (mounted) {
            AppToast.show(context, UITextConstants.copiedToClipboard);
          }
        }
        break;
      case 'recall':
        if (msg['isSelf'] == true) {
          setState(() => _messages.removeWhere((m) => m['id'] == msg['id']));
        }
        break;
      case 'delete':
        setState(() => _messages.removeWhere((m) => m['id'] == msg['id']));
        break;
    }
    setState(() {
      _actionMenuMessage = null;
      _actionMenuPosition = null;
    });
  }

  Future<void> _shareMessages(List<Map<String, dynamic>> messages) async {
    final lines = messages
        .map((item) => (item['content'] as String?)?.trim() ?? '')
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
    if (lines.isEmpty) return;
    final text = lines.join('\n\n');
    await SharePlus.instance.share(ShareParams(text: text));
  }

  void _toggleSelect(String id) {
    setState(() {
      if (_selectedIds.contains(id)) {
        _selectedIds.remove(id);
      } else {
        _selectedIds.add(id);
      }
    });
  }

  void _cancelSelection() {
    setState(() {
      _isSelectionMode = false;
      _selectedIds.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    _lastViewportWidth = MediaQuery.of(context).size.width;
    _assistantRemoteConfiguredCached = ref.watch(
      assistantRemoteConfiguredProvider,
    );
    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final bubbleSelf = AppColors.chatBubbleOutgoing;
    final bubbleOther = AppColors.chatBubbleIncoming;
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final chatListBg = isDark ? bgColor : AppColors.chatBackground;
    final latestAssistantTextMessageId = _messages.reversed
        .where(
          (item) =>
              (item['senderId'] as String?) ==
                  AppConceptConstants.assistantSenderId &&
              (item['type'] as String? ?? 'text') == 'text',
        )
        .map((item) => (item['id'] as String?) ?? '')
        .firstWhere((id) => id.isNotEmpty, orElse: () => '');

    final bodyContent = Material(
      color: Colors.transparent,
      child: Column(
        children: [
          Expanded(
            child: Stack(
              children: [
                Container(
                  color: chatListBg,
                  child: Builder(
                    builder: (context) {
                      final displayMessages = _isAssistantConversation
                          ? _messages
                          : ref
                                .watch(
                                  chatMessageProvider(widget.conversationId),
                                )
                                .messages
                                .map(
                                  (dto) => dto.toDisplayMap(
                                    currentUserId: 'current_user',
                                  ),
                                )
                                .toList();
                      return ListView.builder(
                        controller: _scrollController,
                        padding: EdgeInsets.symmetric(
                          horizontal:
                              AppSpacing.semantic[DesignSemanticConstants
                                  .container]?[DesignSemanticConstants.sm] ??
                              AppSpacing.containerSm,
                          vertical: AppSpacing.md,
                        ),
                        itemCount: displayMessages.length,
                        itemBuilder: (context, index) {
                          final msg = displayMessages[index];
                          final prevTime = index > 0
                              ? displayMessages[index - 1]['timestamp']
                                    as String?
                              : null;
                          final showTime =
                              index == 0 || msg['timestamp'] != prevTime;
                          final timeStr = formatChatTime(
                            msg['timestamp'] as String?,
                          );
                          final isAssistantMessage =
                              _isAssistantConversation &&
                              (msg['senderId'] ==
                                  AppConceptConstants.assistantSenderId);
                          return Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (showTime && timeStr.isNotEmpty)
                                Padding(
                                  padding: EdgeInsets.only(
                                    bottom:
                                        AppSpacing
                                            .semantic[DesignSemanticConstants
                                            .intraGroup]?[DesignSemanticConstants
                                            .sm] ??
                                        AppSpacing.intraGroupSm,
                                  ),
                                  child: Center(
                                    child: Text(
                                      timeStr,
                                      style: TextStyle(
                                        fontSize:
                                            Theme.of(
                                              context,
                                            ).textTheme.bodySmall?.fontSize ??
                                            AppSpacing.containerSm,
                                        color: fgPrimary.withValues(alpha: 0.5),
                                      ),
                                    ),
                                  ),
                                ),
                              ChatMessageBubble(
                                message: msg,
                                isRight: msg['isSelf'] == true,
                                bubbleColor: msg['isSelf'] == true
                                    ? bubbleSelf
                                    : bubbleOther,
                                textColor: msg['isSelf'] == true
                                    ? Colors.white
                                    : fgPrimary,
                                isSelectionMode: _isSelectionMode,
                                isSelected: _selectedIds.contains(msg['id']),
                                onLongPressStart: (details) =>
                                    _onLongPressMessage(
                                      msg,
                                      details.globalPosition,
                                    ),
                                onTap: _isSelectionMode
                                    ? () => _toggleSelect(msg['id'] as String)
                                    : null,
                                hideAvatarAndName: _isAssistantConversation,
                                useFullWidth: _isAssistantConversation,
                                renderSelfTextWithoutBubble:
                                    _isAssistantConversation,
                                journeyViewModel:
                                    _isAssistantConversation &&
                                        index == _messages.length - 1 &&
                                        isAssistantMessage &&
                                        _assistantResponding
                                    ? _buildJourneyViewModel(
                                        journey: _currentJourney,
                                        isRunning: true,
                                        elapsedMs: _currentJourneyElapsedMs,
                                      )
                                    : (_isAssistantConversation &&
                                              isAssistantMessage
                                          ? _journeyViewModelFromMessage(msg)
                                          : null),
                                answerGateOpen:
                                    !_isAssistantConversation ||
                                    !_assistantResponding ||
                                    index != _messages.length - 1 ||
                                    !isAssistantMessage ||
                                    _answerGateOpen,
                                isAssistantRunning:
                                    _assistantResponding &&
                                    index == _messages.length - 1 &&
                                    isAssistantMessage,
                                runningStatusLabel:
                                    _isAssistantConversation &&
                                        _assistantResponding &&
                                        index == _messages.length - 1 &&
                                        isAssistantMessage
                                    ? (_assistantPhaseLabel.isNotEmpty
                                          ? _assistantPhaseLabel
                                          : UITextConstants
                                                .assistantPhaseUnderstanding)
                                    : null,
                                showFeedbackActions:
                                    isAssistantMessage &&
                                    !_assistantResponding &&
                                    !_isSelectionMode &&
                                    (msg['type'] as String? ?? 'text') ==
                                        'text' &&
                                    ((msg['id'] as String?) ?? '') ==
                                        latestAssistantTextMessageId,
                                feedbackStatus:
                                    _assistantFeedbackStatusByMessageId[msg['id']
                                            as String? ??
                                        ''] ??
                                    '',
                                onFeedbackHelpful: isAssistantMessage
                                    ? () => _submitAssistantFeedback(
                                        message: msg,
                                        explicitThumb: 'up',
                                        reasonCodes: const <String>[],
                                      )
                                    : null,
                                onFeedbackUnhelpful: isAssistantMessage
                                    ? () => _showAssistantNegativeFeedbackSheet(
                                        msg,
                                      )
                                    : null,
                                onFeedbackCorrect: isAssistantMessage
                                    ? () => _showAssistantCorrectionSheet(msg)
                                    : null,
                                onCopyAnswer: isAssistantMessage
                                    ? () async {
                                        final content =
                                            (msg['content'] as String?) ?? '';
                                        if (content.isEmpty) return;
                                        await Clipboard.setData(
                                          ClipboardData(text: content),
                                        );
                                        if (!mounted) return;
                                        AppToast.show(
                                          this.context,
                                          UITextConstants.copiedToClipboard,
                                        );
                                        await _recordAssistantImplicitFeedback(
                                          message: msg,
                                          copiedAnswer: true,
                                        );
                                      }
                                    : null,
                                onShareAnswer: isAssistantMessage
                                    ? () async {
                                        final content =
                                            (msg['content'] as String?) ?? '';
                                        if (content.isNotEmpty) {
                                          await SharePlus.instance.share(
                                            ShareParams(text: content),
                                          );
                                        }
                                        await _recordAssistantImplicitFeedback(
                                          message: msg,
                                          sharedAnswer: true,
                                        );
                                      }
                                    : null,
                                onFavoriteAnswer: isAssistantMessage
                                    ? () async {
                                        await _recordAssistantImplicitFeedback(
                                          message: msg,
                                          favoritedAnswer: true,
                                        );
                                        if (!mounted) return;
                                        AppToast.show(
                                          this.context,
                                          UITextConstants.assistantBookmarked,
                                        );
                                      }
                                    : null,
                                onRegenerateAnswer: isAssistantMessage
                                    ? () => _requestAssistantRewrite(
                                        message: msg,
                                        mode: 'regenerate',
                                      )
                                    : null,
                                onRegenerateOptionSelected: isAssistantMessage
                                    ? (option) => _requestAssistantRewriteV2(
                                        message: msg,
                                        option: option,
                                      )
                                    : null,
                                onBriefAnswer: isAssistantMessage
                                    ? () => _requestAssistantRewrite(
                                        message: msg,
                                        mode: 'brief',
                                      )
                                    : null,
                                onDetailedAnswer: isAssistantMessage
                                    ? () => _requestAssistantRewrite(
                                        message: msg,
                                        mode: 'detailed',
                                      )
                                    : null,
                                onSwitchModelAnswer: isAssistantMessage
                                    ? () => _switchAssistantModelAndRegenerate(
                                        msg,
                                      )
                                    : null,
                                onActionHintTap: isAssistantMessage
                                    ? (hint) async {
                                        _inputController.text = hint;
                                        await _sendMessage();
                                      }
                                    : null,
                                onReferenceTap: isAssistantMessage
                                    ? (refItem) =>
                                          _onAssistantReferenceTap(msg, refItem)
                                    : null,
                                onAvatarTap: isAssistantMessage
                                    ? () {
                                        final target = VisitTarget.page('chat');
                                        final service = ref.read(
                                          visitRecorderServiceProvider,
                                        );
                                        final ctx = AssistantOpenContext(
                                          source: AssistantSource.chat,
                                          visitTarget: target,
                                          experienceLevel: service
                                              .getExperience(target),
                                        );
                                        AssistantHalfSheet.show(context, ctx);
                                      }
                                    : () {
                                        final senderId =
                                            msg['senderId'] as String? ?? '';
                                        if (senderId == 'current_user') {
                                          final currentUser = ref.read(
                                            userDataProvider,
                                          );
                                          final userId =
                                              currentUser?.username ??
                                              currentUser?.id;
                                          if (userId != null &&
                                              userId.isNotEmpty) {
                                            context.push(
                                              AppRoutePaths.userProfile(
                                                username: userId,
                                              ),
                                            );
                                          }
                                        } else if (senderId.isNotEmpty) {
                                          context.push(
                                            AppRoutePaths.userProfile(
                                              username: senderId,
                                            ),
                                          );
                                        }
                                      },
                                showAssistantAvatar: false,
                              ),
                            ],
                          );
                        },
                      );
                    },
                  ),
                ),
                if (_isAssistantConversation &&
                    (_showAssistantHistoryPeek ||
                        _assistantLoadingOlderHistory))
                  Positioned(
                    top: AppSpacing.sm,
                    left: 0,
                    right: 0,
                    child: Center(
                      child: GestureDetector(
                        onTap: _assistantLoadingOlderHistory
                            ? null
                            : _loadOlderAssistantHistory,
                        child: AnimatedOpacity(
                          opacity: 1,
                          duration: const Duration(milliseconds: 180),
                          child: Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.containerSm,
                              vertical: AppSpacing.xs,
                            ),
                            decoration: BoxDecoration(
                              color: isDark
                                  ? bgColor.withValues(alpha: 0.92)
                                  : Colors.white.withValues(alpha: 0.94),
                              borderRadius: BorderRadius.circular(
                                AppSpacing.fullBorderRadius,
                              ),
                              border: Border.all(
                                color: borderColor.withValues(alpha: 0.18),
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.04),
                                  blurRadius: AppSpacing.sm,
                                ),
                              ],
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                if (_assistantLoadingOlderHistory)
                                  Padding(
                                    padding: EdgeInsets.only(
                                      right: AppSpacing.xs,
                                    ),
                                    child: const CupertinoActivityIndicator(),
                                  )
                                else
                                  Icon(
                                    CupertinoIcons.chevron_up,
                                    size: AppSpacing.iconSmall,
                                    color: fgPrimary.withValues(alpha: 0.56),
                                  ),
                                if (!_assistantLoadingOlderHistory)
                                  SizedBox(width: AppSpacing.xs / 2),
                                Text(
                                  UITextConstants.assistantViewHistory,
                                  style: TextStyle(
                                    fontSize: AppTypography.sm,
                                    color: fgPrimary.withValues(alpha: 0.72),
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                if (_showScrollFab)
                  Positioned(
                    right: AppSpacing.md,
                    bottom: AppSpacing.md,
                    child: StreamingScrollFab(
                      onTap: () {
                        _scrollController.animateTo(
                          _scrollController.position.maxScrollExtent,
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeOut,
                        );
                        setState(() => _userScrolledAway = false);
                      },
                    ),
                  ),
              ],
            ),
          ),
          _isAssistantConversation
              ? SafeArea(
                  top: false,
                  child: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal:
                          AppSpacing.semantic[DesignSemanticConstants
                              .container]?[DesignSemanticConstants.sm] ??
                          AppSpacing.containerSm,
                      vertical: AppSpacing.sm,
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        CustomizableChatInputBar(
                          controller: _inputController,
                          focusNode: _inputFocusNode,
                          textFieldKey: TestKeys.assistantChatInputField,
                          hintText: UITextConstants.assistantAskPlaceholder,
                          maxTextLength: 5000,
                          maxVisibleLines: 4,
                          onPickImages: _pickChatImages,
                          onCapturePhoto: _captureChatPhoto,
                          onPickFiles: _pickChatFiles,
                          onRequestMicPermission: _requestMicPermissionForChat,
                          onStartRecord: _startVoiceRecordForChat,
                          onStopRecord: _stopVoiceRecordForChat,
                          onVoiceAsrTransform: _voiceAsrForChat,
                          onSend: _submitChatInput,
                          leftBuilder: _buildAssistantLeftButton,
                          rightBuilder: _buildAssistantRightButtons,
                          extraPanelItems: const <ChatInputExtraPanelItem>[],
                        ),
                      ],
                    ),
                  ),
                )
              : Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal:
                        AppSpacing.semantic[DesignSemanticConstants
                            .container]?[DesignSemanticConstants.sm] ??
                        AppSpacing.containerSm,
                  ),
                  child: Container(
                    padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
                    decoration: BoxDecoration(
                      color: isDark ? bgColor : AppColors.chatToolbarBackground,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.largeBorderRadius,
                      ),
                    ),
                    child: SafeArea(
                      top: false,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          if (!_isGroupChat &&
                              _relationshipCapability?.isSameInterest != true &&
                              _otherParticipantId != null)
                            _buildSameInterestPromptBar(),
                          CustomizableChatInputBar(
                            controller: _inputController,
                            focusNode: _inputFocusNode,
                            maxTextLength: 5000,
                            maxVisibleLines: 4,
                            onPickImages: _pickChatImages,
                            onCapturePhoto: _captureChatPhoto,
                            onPickFiles: _pickChatFiles,
                            onRequestMicPermission:
                                _requestMicPermissionForChat,
                            onStartRecord: _startVoiceRecordForChat,
                            onStopRecord: _stopVoiceRecordForChat,
                            onVoiceAsrTransform: _voiceAsrForChat,
                            onSend: _submitChatInput,
                            leftBuilder: _buildQuliaoLeftButton,
                            rightBuilder: _buildQuliaoRightButtons,
                            extraPanelItems: _buildCallPanelItems(),
                          ),
                          if (_showEmojiPanel)
                            UnifiedEmojiPicker(
                              showCloseButton: true,
                              onClose: () =>
                                  setState(() => _showEmojiPanel = false),
                              onEmojiSelected: (char) =>
                                  setState(() => _inputController.text += char),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
        ],
      ),
    );

    if (widget.embedded) {
      return Stack(
        children: [
          Container(color: bgColor, child: bodyContent),
          if (_actionMenuMessage != null && _actionMenuPosition != null)
            _MessageActionMenuOverlay(
              message: _actionMenuMessage!,
              position: _actionMenuPosition!,
              onAction: _onMessageAction,
              onClose: () => setState(() {
                _actionMenuMessage = null;
                _actionMenuPosition = null;
              }),
            ),
        ],
      );
    }

    return Stack(
      children: [
        AppScaffold(
          backgroundColor: bgColor,
          navigationBar: AppNavigationBar(
            backgroundColor: bgColor,
            leading: CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: _isSelectionMode ? _cancelSelection : widget.onBack,
              child: Icon(
                _isSelectionMode ? CupertinoIcons.xmark : CupertinoIcons.back,
                color: fgPrimary,
              ),
            ),
            middle: Text(
              _isSelectionMode
                  ? '已选 ${_selectedIds.length} 条'
                  : _conversationTitle,
              style: TextStyle(
                color: fgPrimary,
                fontSize: AppTypography.xl,
                fontWeight: FontWeight.w600,
              ),
            ),
            trailing: _isSelectionMode
                ? CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () async {
                      final selectedMessages = _messages
                          .where(
                            (item) => _selectedIds.contains(
                              (item['id'] as String?) ?? '',
                            ),
                          )
                          .toList(growable: false);
                      await _shareMessages(selectedMessages);
                      _cancelSelection();
                    },
                    child: Text(UITextConstants.messageActionForward),
                  )
                : (_isAssistantConversation
                      ? CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: _openAssistantSettingsPage,
                          child: const Icon(CupertinoIcons.gear),
                        )
                      : CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: () => context.push(
                            AppRoutePaths.chatSettings(
                              id: widget.conversationId,
                            ),
                          ),
                          child: const Icon(CupertinoIcons.ellipsis),
                        )),
          ),
          body: bodyContent,
        ),
        if (_actionMenuMessage != null && _actionMenuPosition != null)
          _MessageActionMenuOverlay(
            message: _actionMenuMessage!,
            position: _actionMenuPosition!,
            onAction: _onMessageAction,
            onClose: () => setState(() {
              _actionMenuMessage = null;
              _actionMenuPosition = null;
            }),
          ),
      ],
    );
  }
}

/// 长按消息弹出的操作菜单（1:1 对应 MessageActionMenu.tsx：转发/多选/复制/撤回/删除）
class _MessageActionMenuOverlay extends StatelessWidget {
  const _MessageActionMenuOverlay({
    required this.message,
    required this.position,
    required this.onAction,
    required this.onClose,
  });

  final Map<String, dynamic> message;
  final Offset position;
  final void Function(String action) onAction;
  final VoidCallback onClose;

  static const _recallWindowDuration = Duration(minutes: 2);

  static bool _isWithinRecallWindow(Map<String, dynamic> message) {
    final sentAtIso = message['sentAtIso'] as String?;
    if (sentAtIso != null) {
      final sentAt = DateTime.tryParse(sentAtIso);
      if (sentAt != null) {
        return DateTime.now().difference(sentAt) <= _recallWindowDuration;
      }
    }
    final timestampRaw = message['timestamp'];
    if (timestampRaw is String) {
      final parsed = DateTime.tryParse(timestampRaw);
      if (parsed != null) {
        return DateTime.now().difference(parsed) <= _recallWindowDuration;
      }
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    final type = message['type'] as String? ?? 'text';
    final isSelf = message['isSelf'] == true;
    final canRecall = isSelf && _isWithinRecallWindow(message);
    final actions = <MapEntry<String, String>>[
      MapEntry('forward', UITextConstants.messageActionForward),
      MapEntry('select', UITextConstants.messageActionSelect),
      if (type == 'text') MapEntry('copy', UITextConstants.messageActionCopy),
      if (canRecall) MapEntry('recall', UITextConstants.messageActionRecall),
      MapEntry('delete', UITextConstants.messageActionDelete),
    ];
    const menuWidth = 200.0;
    const menuPadding = 10.0;
    double left = position.dx - menuWidth / 2;
    double top = position.dy - 20;
    final size = MediaQuery.sizeOf(context);
    if (left + menuWidth > size.width - menuPadding) {
      left = size.width - menuWidth - menuPadding;
    }
    if (left < menuPadding) left = menuPadding;
    if (top + 250 > size.height - menuPadding) top = position.dy - 250;
    if (top < menuPadding) top = menuPadding;

    return Stack(
      children: [
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onClose,
          child: const SizedBox.expand(),
        ),
        Positioned(
          left: left,
          top: top,
          child: Material(
            elevation: AppSpacing.sm,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            child: Container(
              width: menuWidth,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.surface,
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
                border: Border.all(color: Theme.of(context).dividerColor),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: actions.map((e) {
                  final isDelete = e.key == 'delete';
                  return InkWell(
                    onTap: () {
                      onAction(e.key);
                      onClose();
                    },
                    child: Padding(
                      padding: EdgeInsets.symmetric(
                        horizontal:
                            AppSpacing.semantic[DesignSemanticConstants
                                .container]?[DesignSemanticConstants.md] ??
                            AppSpacing.containerMd,
                        vertical: AppSpacing.containerSm,
                      ),
                      child: Row(
                        children: [
                          Icon(
                            e.key == 'forward'
                                ? Icons.share
                                : e.key == 'select'
                                ? Icons.check_box_outlined
                                : e.key == 'copy'
                                ? Icons.copy
                                : e.key == 'recall'
                                ? Icons.undo
                                : Icons.delete_outline,
                            size: AppSpacing.iconMedium,
                            color: isDelete ? AppColors.error : null,
                          ),
                          SizedBox(width: AppSpacing.containerSm),
                          Text(
                            e.value,
                            style: TextStyle(
                              fontSize:
                                  Theme.of(
                                    context,
                                  ).textTheme.bodyMedium?.fontSize ??
                                  AppSpacing.containerMd,
                              fontWeight: FontWeight.w500,
                              color: isDelete ? AppColors.error : null,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
