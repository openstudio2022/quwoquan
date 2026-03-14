import 'dart:async';
import 'dart:convert';
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
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_engine_provider.dart';
import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';
import 'package:quwoquan_app/personal_assistant/contracts/explainable_flow_event.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_response_parser.dart';
import 'package:quwoquan_app/personal_assistant/engine/process_journal_bus.dart';
import 'package:quwoquan_app/personal_assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_display_fallbacks.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_dev_replay_page.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_chat_settings_page.dart';
import 'package:quwoquan_app/cloud/chat/models/conversation_dto.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_manager.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/regenerate_options_popup.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/streaming_scroll_fab.dart';

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
  });

  final String conversationId;
  final VoidCallback onBack;

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

  /// 当前轮过程状态机展示文案（等待/深度搜索中/深度思考中），由 trace 事件驱动
  String _assistantPhaseLabel = '';
  String? _activeAssistantStreamingMessageId;
  String _streamingAnswerRawBuffer = '';
  String _streamingAnswerVisibleBuffer = '';

  /// v4: Unified process state for the single-drawer UI.
  AssistantProcessState _currentProcessState = const AssistantProcessState();

  /// v6: Explainable flow events for the unified process drawer.
  final List<ExplainableFlowEvent> _currentFlowEvents =
      <ExplainableFlowEvent>[];
  bool _answerGateOpen = true;

  /// v7: Accumulated model thinking text for the process drawer body.
  String _streamingThinkingText = '';

  /// Accumulated structured content blocks for the process drawer.
  List<ProcessContentBlock> _processContentBlocks = <ProcessContentBlock>[];

  List<ProcessJournalEvent> _currentProcessJournal = <ProcessJournalEvent>[];

  /// Whether the user has scrolled away from the bottom during streaming.
  bool _userScrolledAway = false;

  /// Whether to show the scroll-to-bottom FAB.
  bool _showScrollFab = false;
  String _assistantRuntimeSessionId =
      AppConceptConstants.assistantConversationId;
  String _assistantTopicTitle = UITextConstants.assistantHistoryAll;
  List<Map<String, dynamic>> _assistantHiddenHistory = <Map<String, dynamic>>[];
  bool _assistantLoadingOlderHistory = false;
  bool _showAssistantHistoryPeek = false;
  final ImagePicker _imagePicker = ImagePicker();
  final stt.SpeechToText _speechToText = stt.SpeechToText();
  bool _speechReady = false;
  String _lastAsrText = '';

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScrollChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (_isAssistantConversation) {
        _loadMessages();
      } else {
        ref
            .read(chatMessageProvider(widget.conversationId).notifier)
            .loadMessages();
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
    final freshSessionId = 'assistant_${DateTime.now().millisecondsSinceEpoch}';
    setState(() {
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

  void _scrollToBottom() {
    if (!_scrollController.hasClients) return;
    setState(() {
      _userScrolledAway = false;
      _showScrollFab = false;
    });
    _scrollController.animateTo(
      _scrollController.position.maxScrollExtent,
      duration: const Duration(milliseconds: 250),
      curve: Curves.easeOut,
    );
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
    _scrollController.removeListener(_onScrollChanged);
    _inputController.removeListener(_onInputChanged);
    _speechToText.cancel();
    _inputController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  void _startAssistantProgress() {
  }

  void _stopAssistantProgress() {}

  /// 保证 _messages 为可扩容列表，避免定长列表导致 add/addAll 抛 UnsupportedError。
  void _ensureMessagesGrowable() {
    _messages = List<Map<String, dynamic>>.from(_messages);
  }

  String get _effectiveAssistantSessionId {
    if (!_isAssistantConversation) return widget.conversationId;
    return _assistantRuntimeSessionId.trim().isEmpty
        ? AppConceptConstants.assistantConversationId
        : _assistantRuntimeSessionId;
  }

  Future<bool> _syncAssistantSessionInfo() async {
    if (!_isAssistantConversation) return false;
    final sessions = await ref.read(assistantGatewayProvider).listSessions();
    if (!mounted || sessions.isEmpty) return false;
    Map<String, dynamic> active = sessions.first;
    for (final item in sessions) {
      if (item['isActive'] == true) {
        active = item;
        break;
      }
    }
    final nextSessionId = (active['sessionId'] ?? '').toString();
    final nextTopic = (active['topicTitle'] as String?)?.trim();
    if (nextSessionId.isNotEmpty) {
      setState(() {
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
          if (!isUser && normalizedContent.trim().isEmpty) {
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
    await ref.read(assistantGatewayProvider).switchSession(sessionId);
    if (!mounted) return;
    setState(() => _assistantRuntimeSessionId = sessionId);
    await _loadAssistantSessionMessages(sessionId);
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
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('已发送同好邀请')));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('发送失败，请稍后再试')));
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
          onOpenTrace: _openAssistantDevReplayPage,
          onSessionSelected: _switchAssistantSession,
        ),
      ),
    );
    if (!mounted) return;
    await _syncAssistantSessionInfo();
  }

  String _stageHeaderLabel(ProcessStage stage) {
    switch (stage) {
      case ProcessStage.understanding:
        return UITextConstants.assistantPhaseUnderstanding;
      case ProcessStage.searching:
        return UITextConstants.assistantPhaseSearching;
      case ProcessStage.analyzing:
        return UITextConstants.assistantPhaseAnalyzing;
      case ProcessStage.answering:
        return UITextConstants.assistantPhaseAnswering;
      case ProcessStage.completed:
        return UITextConstants.assistantPhaseCompleted;
    }
  }

  void _resetStreamingAnswerDecoder() {
    _streamingAnswerRawBuffer = '';
    _streamingAnswerVisibleBuffer = '';
  }

  String _extractLenientJsonStringField(String raw, String fieldName) {
    final key = '"$fieldName"';
    final fieldIndex = raw.indexOf(key);
    if (fieldIndex < 0) return '';
    var cursor = fieldIndex + key.length;
    while (cursor < raw.length && _isWhitespaceCode(raw.codeUnitAt(cursor))) {
      cursor += 1;
    }
    if (cursor >= raw.length || raw[cursor] != ':') return '';
    cursor += 1;
    while (cursor < raw.length && _isWhitespaceCode(raw.codeUnitAt(cursor))) {
      cursor += 1;
    }
    if (cursor >= raw.length || raw[cursor] != '"') return '';
    cursor += 1;
    final buffer = StringBuffer();
    var escaped = false;
    while (cursor < raw.length) {
      final ch = raw[cursor];
      if (escaped) {
        switch (ch) {
          case 'n':
            buffer.write('\n');
            break;
          case 'r':
            buffer.write('\r');
            break;
          case 't':
            buffer.write('\t');
            break;
          case '"':
          case r'\':
          case '/':
            buffer.write(ch);
            break;
          case 'u':
            if (cursor + 4 < raw.length) {
              final hex = raw.substring(cursor + 1, cursor + 5);
              final codePoint = int.tryParse(hex, radix: 16);
              if (codePoint != null) {
                buffer.writeCharCode(codePoint);
                cursor += 4;
                break;
              }
            }
            break;
          default:
            buffer.write(ch);
            break;
        }
        escaped = false;
        cursor += 1;
        continue;
      }
      if (ch == r'\') {
        escaped = true;
        cursor += 1;
        continue;
      }
      if (ch == '"') {
        break;
      }
      buffer.write(ch);
      cursor += 1;
    }
    return buffer.toString();
  }

  bool _isWhitespaceCode(int codeUnit) {
    return codeUnit == 0x20 ||
        codeUnit == 0x0A ||
        codeUnit == 0x0D ||
        codeUnit == 0x09;
  }

  String _streamingAnswerDeltaFromCandidate(String candidate) {
    final sanitizedCandidate = _sanitizeStreamingMarkdownCandidate(candidate);
    if (sanitizedCandidate.isEmpty) {
      return '';
    }
    if (sanitizedCandidate.length <= _streamingAnswerVisibleBuffer.length) {
      return '';
    }
    final delta = sanitizedCandidate.substring(
      _streamingAnswerVisibleBuffer.length,
    );
    _streamingAnswerVisibleBuffer = sanitizedCandidate;
    return delta;
  }

  String _sanitizeStreamingMarkdownCandidate(String candidate) {
    if (candidate.trim().isEmpty) {
      return '';
    }
    final withoutWrapper = _stripLeadingStreamingMarkdownWrapper(candidate);
    if (withoutWrapper == null || withoutWrapper.isEmpty) {
      return '';
    }
    final trailingFenceStart = _trailingUnclosedFenceStart(withoutWrapper);
    if (trailingFenceStart < 0) {
      return withoutWrapper;
    }
    return withoutWrapper.substring(0, trailingFenceStart);
  }

  String? _stripLeadingStreamingMarkdownWrapper(String text) {
    if (!text.startsWith('```')) {
      return text;
    }
    final lineBreakIndex = _firstLineBreakIndex(text);
    if (lineBreakIndex < 0) {
      final prefix = text.trimRight().toLowerCase();
      if ('```md'.startsWith(prefix) || '```markdown'.startsWith(prefix)) {
        return null;
      }
      return prefix == '```' ? null : text;
    }
    final openingLine = text.substring(0, lineBreakIndex).trim().toLowerCase();
    if (openingLine != '```md' && openingLine != '```markdown') {
      return text;
    }
    final nextLineStart =
        text.codeUnitAt(lineBreakIndex) == 0x0D &&
            lineBreakIndex + 1 < text.length &&
            text.codeUnitAt(lineBreakIndex + 1) == 0x0A
        ? lineBreakIndex + 2
        : lineBreakIndex + 1;
    return nextLineStart >= text.length ? '' : text.substring(nextLineStart);
  }

  int _firstLineBreakIndex(String text) {
    for (int i = 0; i < text.length; i++) {
      final codeUnit = text.codeUnitAt(i);
      if (codeUnit == 0x0A || codeUnit == 0x0D) {
        return i;
      }
    }
    return -1;
  }

  int _trailingUnclosedFenceStart(String text) {
    final fenceStarts = <int>[];
    var offset = 0;
    while (offset < text.length) {
      final index = text.indexOf('```', offset);
      if (index < 0) {
        break;
      }
      fenceStarts.add(index);
      offset = index + 3;
    }
    if (fenceStarts.length.isEven) {
      return -1;
    }
    return fenceStarts.last;
  }

  String _visibleStreamingAnswerChunk(String rawChunk) {
    final strippedXml = _stripXmlToolCallsPreservingWhitespace(
      rawChunk,
    ).trimRight();
    if (strippedXml.trim().isEmpty) return '';
    _streamingAnswerRawBuffer = '$_streamingAnswerRawBuffer$strippedXml';
    final extractedVisible = _extractLenientJsonStringField(
      _streamingAnswerRawBuffer,
      'userMarkdown',
    );
    if (extractedVisible.isNotEmpty) {
      if (!_streamingChunkCanDisplayAnswer(_streamingAnswerRawBuffer)) {
        return '';
      }
      return _streamingAnswerDeltaFromCandidate(extractedVisible);
    }
    final normalized = strippedXml.trim();
    if (normalized.startsWith('{') ||
        normalized.startsWith('[') ||
        _jsonEnvelopeFragmentRe.hasMatch(normalized) ||
        _jsonKeyFragmentRe.hasMatch(normalized) ||
        _jsonSyntaxOnlyRe.hasMatch(normalized)) {
      return '';
    }
    return _streamingAnswerDeltaFromCandidate(_streamingAnswerRawBuffer);
  }

  bool _streamingChunkCanDisplayAnswer(String rawBuffer) {
    final raw = rawBuffer.trim();
    if (raw.isEmpty) return false;
    if (!raw.startsWith('{') && !raw.startsWith('[')) {
      return !_containsInternalDisplayFragment(raw);
    }
    final parsed = LlmResponseParser.parse(raw);
    if (parsed.ok) {
      return _parsedEnvelopeCanDisplayAnswer(parsed.json!);
    }
    final normalized = raw.replaceAll(RegExp(r'\s+'), '');
    if (normalized.contains('"nextAction":"ask_user"') ||
        normalized.contains('"nextAction":"tool_call"') ||
        normalized.contains('"nextAction":"clarify"') ||
        normalized.contains('"nextAction":"retry"') ||
        normalized.contains('"messageKind":"progress"')) {
      return false;
    }
    return normalized.contains('"nextAction":"answer"') ||
        normalized.contains('"messageKind":"answer"');
  }

  bool _parsedEnvelopeCanDisplayAnswer(Map<String, dynamic> envelope) {
    final nextAction = _envelopeNextAction(envelope);
    final messageKind = _envelopeMessageKind(envelope);
    if (nextAction.isNotEmpty && nextAction != 'answer') {
      return false;
    }
    if (messageKind == 'progress' ||
        messageKind == 'tool_call' ||
        messageKind == 'clarify') {
      return false;
    }
    final userMarkdown = _envelopeUserMarkdown(envelope);
    if (userMarkdown.isEmpty) return false;
    return !_containsInternalDisplayFragment(userMarkdown);
  }

  String _envelopeNextAction(Map<String, dynamic> envelope) {
    final answerPayload =
        (envelope['answerPayload'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final decision =
        (envelope['decision'] as Map?)?.cast<String, dynamic>() ??
        (answerPayload['decision'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return (decision['nextAction'] as String?)?.trim() ?? '';
  }

  String _envelopeMessageKind(Map<String, dynamic> envelope) {
    final topLevel = (envelope['messageKind'] as String?)?.trim() ?? '';
    if (topLevel.isNotEmpty) return topLevel;
    final answerPayload =
        (envelope['answerPayload'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return (answerPayload['messageKind'] as String?)?.trim() ?? '';
  }

  String _envelopeUserMarkdown(Map<String, dynamic> envelope) {
    final topLevel = (envelope['userMarkdown'] as String?)?.trim() ?? '';
    if (topLevel.isNotEmpty) return topLevel;
    final answerPayload =
        (envelope['answerPayload'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return (answerPayload['userMarkdown'] as String?)?.trim() ?? '';
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
      _answerGateOpen = true;
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
    });
    _autoScrollToBottomIfNeeded();
  }

  void _resetStreamingAnswer() {
    if (!mounted) return;
    _resetStreamingAnswerDecoder();
    final messageId = _activeAssistantStreamingMessageId;
    if (messageId == null || messageId.isEmpty) return;
    setState(() {
      _ensureMessagesGrowable();
      final existingIndex = _messages.indexWhere(
        (item) => (item['id'] as String?) == messageId,
      );
      if (existingIndex >= 0) {
        _messages[existingIndex] = <String, dynamic>{
          ..._messages[existingIndex],
          'streamFinalAnswer': '',
          'content': '',
        };
      }
    });
  }

  String _reconcileCompletedAnswerText({
    required String streamedText,
    required String completedText,
  }) {
    final streamed = streamedText.trim();
    final completed = completedText.trim();
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
    var text = raw.trim();
    if (text.isEmpty) return '';
    if (allowJsonExtraction &&
        (text.startsWith('{') ||
            text.startsWith('[') ||
            text.startsWith('```'))) {
      final stripped = _stripJsonForDisplay(text).trim();
      if (stripped.isNotEmpty && stripped != text) {
        return _sanitizeCompletedDisplayCandidate(
          stripped,
          allowJsonExtraction: false,
        );
      }
    }
    if (_containsXmlToolCall(text)) {
      text = _stripXmlToolCalls(text);
      if (text.isEmpty) return '';
    }
    text = _stripWrappedMarkdownEnvelope(text);
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

  String _stripWrappedMarkdownEnvelope(String text) {
    final match = RegExp(
      r'^```(?:md|markdown)\s*\r?\n([\s\S]*?)\r?\n```$',
      caseSensitive: false,
    ).firstMatch(text);
    if (match == null) {
      return text;
    }
    return (match.group(1) ?? '').trim();
  }

  String _actionLikeCompletedFallback(AssistantRunResponse response) {
    return resolveActionLikeCompletedFallback(response);
  }

  bool _containsInternalDisplayFragment(String value) {
    final text = value.trim();
    if (text.isEmpty) return false;
    return _jsonEnvelopeFragmentRe.hasMatch(text) ||
        _jsonKeyFragmentRe.hasMatch(text) ||
        text.contains('assistant_turn') ||
        text.contains('contractVersion') ||
        text.contains('toolCalls') ||
        text.contains('queryTasks') ||
        text.contains('runArtifacts') ||
        text.contains('machineEnvelope') ||
        _containsXmlToolCall(text);
  }

  void _consumeProcessJournalEvent(ProcessJournalEvent event) {
    if (!mounted || !_assistantResponding) return;
    final updated = _appendStreamingProcessJournalEvent(event);
    if (!updated) return;
    final journal = List<ProcessJournalEvent>.of(_currentProcessJournal);
    final blocks = _processBlocksFromJournal(journal);
    final stage = event.type == ProcessJournalEventType.completed
        ? ProcessStage.completed
        : _stageFromProcessJournal(journal);
    final headerLabel = _stageHeaderLabel(stage);
    setState(() {
      _processContentBlocks = List<ProcessContentBlock>.of(blocks);
      _currentProcessState = _currentProcessState.copyWith(
        stage: stage,
        stageLabel: headerLabel,
        contentBlocks: List<ProcessContentBlock>.of(blocks),
        isStreaming: stage != ProcessStage.completed,
      );
      _assistantPhaseLabel = stage == ProcessStage.completed ? '' : headerLabel;
    });
    _autoScrollToBottomIfNeeded();
  }

  List<ProcessContentBlock> _processBlocksFromStructuredResponse(
    Map<String, dynamic> structuredResponse,
  ) {
    final journal = _journalFromStructuredResponse(structuredResponse);
    if (journal.isNotEmpty) {
      return _processBlocksFromJournal(journal);
    }
    final rawBlocks =
        (structuredResponse['uiProcessContentBlocks'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    if (rawBlocks.isEmpty) {
      final timeline = _timelineV2FromStructuredResponse(structuredResponse);
      if (timeline.isEmpty) return const <ProcessContentBlock>[];
      return _processBlocksFromTimelineV2(timeline);
    }
    final blocks = <ProcessContentBlock>[];
    for (final item in rawBlocks) {
      final rawType = (item['type'] as String?)?.trim() ?? '';
      final text = (item['text'] as String?)?.trim() ?? '';
      final references =
          (item['references'] as List?)
              ?.whereType<Map>()
              .map((ref) => ref.cast<String, dynamic>())
              .map(
                (ref) => ProcessReference(
                  title: (ref['title'] as String?)?.trim() ?? '',
                  url: (ref['url'] as String?)?.trim() ?? '',
                  source: (ref['source'] as String?)?.trim() ?? '',
                ),
              )
              .where((ref) => ref.title.isNotEmpty && ref.url.isNotEmpty)
              .toList(growable: false) ??
          const <ProcessReference>[];
      final type = switch (rawType) {
        'searchSummary' => ProcessContentBlockType.searchSummary,
        'analysisSummary' => ProcessContentBlockType.analysisSummary,
        _ => ProcessContentBlockType.text,
      };
      if (text.isEmpty && references.isEmpty) continue;
      blocks.add(
        ProcessContentBlock(type: type, text: text, references: references),
      );
    }
    return blocks;
  }

  List<Map<String, dynamic>> _serializeProcessBlocks(
    List<ProcessContentBlock> blocks,
  ) {
    return blocks
        .map(
          (b) => <String, dynamic>{
            'type': b.type.name,
            'text': b.text,
            'references': b.references
                .map(
                  (r) => <String, dynamic>{
                    'title': r.title,
                    'url': r.url,
                    'source': r.source,
                  },
                )
                .toList(growable: false),
          },
        )
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _normalizeUiProcessTimelineV2(List<Map> raw) {
    return raw
        .map((item) => item.cast<String, dynamic>())
        .where(
          (item) => ((item['summary'] as String?)?.trim().isNotEmpty ?? false),
        )
        .toList(growable: false);
  }

  List<Map<String, dynamic>> _timelineV2FromStructuredResponse(
    Map<String, dynamic> structuredResponse,
  ) {
    final journal = _journalFromStructuredResponse(structuredResponse);
    if (journal.isNotEmpty) {
      return _timelineFromJournal(journal);
    }
    return _normalizeUiProcessTimelineV2(
      (structuredResponse['uiProcessTimelineV2'] as List?)
              ?.whereType<Map>()
              .toList(growable: false) ??
          const <Map>[],
    );
  }

  List<ProcessJournalEvent> _journalFromStructuredResponse(
    Map<String, dynamic> structuredResponse,
  ) {
    final artifacts =
        (structuredResponse['runArtifacts'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final raw =
        (artifacts['processJournal'] as List?)?.whereType<Map>().toList(
          growable: false,
        ) ??
        const <Map>[];
    return _normalizeProcessJournal(raw);
  }

  List<ProcessJournalEvent> _normalizeProcessJournal(List<Map> raw) {
    final normalized = <ProcessJournalEvent>[];
    final indexById = <String, int>{};
    final indexBySemanticKey = <String, int>{};
    for (final item in raw) {
      final event = ProcessJournalEvent.fromJson(item.cast<String, dynamic>());
      final semanticKey = _processJournalMergeKey(event);
      final existingIndex =
          (event.eventId.isNotEmpty ? indexById[event.eventId] : null) ??
          (semanticKey.isNotEmpty ? indexBySemanticKey[semanticKey] : null);
      if (existingIndex == null) {
        if (event.eventId.isNotEmpty) {
          indexById[event.eventId] = normalized.length;
        }
        if (semanticKey.isNotEmpty) {
          indexBySemanticKey[semanticKey] = normalized.length;
        }
        normalized.add(event);
      } else {
        normalized[existingIndex] = _preferProcessJournalEvent(
          normalized[existingIndex],
          event,
        );
      }
    }
    return normalized;
  }

  List<ProcessJournalEvent> _mergeProcessJournalEvents(
    List<ProcessJournalEvent> existing,
    List<ProcessJournalEvent> incoming,
  ) {
    final merged = List<ProcessJournalEvent>.of(existing);
    final indexById = <String, int>{
      for (var i = 0; i < merged.length; i++) merged[i].eventId: i,
    };
    final indexBySemanticKey = <String, int>{
      for (var i = 0; i < merged.length; i++)
        if (_processJournalMergeKey(merged[i]).isNotEmpty)
          _processJournalMergeKey(merged[i]): i,
    };
    for (final event in incoming) {
      final semanticKey = _processJournalMergeKey(event);
      final index =
          (event.eventId.isNotEmpty ? indexById[event.eventId] : null) ??
          (semanticKey.isNotEmpty ? indexBySemanticKey[semanticKey] : null);
      if (index == null) {
        if (event.eventId.isNotEmpty) {
          indexById[event.eventId] = merged.length;
        }
        if (semanticKey.isNotEmpty) {
          indexBySemanticKey[semanticKey] = merged.length;
        }
        merged.add(event);
      } else {
        merged[index] = _preferProcessJournalEvent(merged[index], event);
      }
    }
    return merged;
  }

  String _processJournalMergeKey(ProcessJournalEvent event) {
    if (event.type == ProcessJournalEventType.answerDelta) {
      return '';
    }
    return <String>[
      processJournalEventTypeToWire(event.type),
      event.phaseId.isNotEmpty ? event.phaseId : event.stage,
      event.actionCode,
      event.reasonCode,
      event.nodeId,
    ].join('::');
  }

  ProcessJournalEvent _preferProcessJournalEvent(
    ProcessJournalEvent existing,
    ProcessJournalEvent incoming,
  ) {
    final incomingRefs = incoming.references.length;
    final existingRefs = existing.references.length;
    if (incomingRefs > existingRefs) return incoming;
    if (incoming.displayMessage.length >= existing.displayMessage.length) {
      return incoming;
    }
    return existing;
  }

  List<ProcessJournalEvent> _displayProcessJournalSnapshot(
    List<ProcessJournalEvent> journal,
  ) {
    return ProcessJournalBus.toDisplaySnapshot(journal);
  }

  List<Map<String, dynamic>> _timelineFromJournal(
    List<ProcessJournalEvent> journal,
  ) {
    return ProcessJournalBus.toTimelineEntries(
      journal,
    ).map((item) => item.toJson()).toList(growable: false);
  }

  List<ProcessContentBlock> _processBlocksFromJournal(
    List<ProcessJournalEvent> journal,
  ) {
    final snapshot = _displayProcessJournalSnapshot(journal);
    final blocks = <ProcessContentBlock>[];
    for (final item in snapshot) {
      switch (item.type) {
        case ProcessJournalEventType.narrativeCommit:
        case ProcessJournalEventType.liveCursor:
          final text = item.displayMessage;
          if (text.isEmpty) continue;
          blocks.add(
            ProcessContentBlock(type: ProcessContentBlockType.text, text: text),
          );
          break;
        case ProcessJournalEventType.sourceUpdate:
          final refs = item.references
              .map(
                (ref) => ProcessReference(
                  title: ref.title,
                  url: ref.url,
                  source: ref.source,
                ),
              )
              .where((ref) => ref.title.isNotEmpty && ref.url.isNotEmpty)
              .toList(growable: false);
          if (item.displayMessage.isEmpty && refs.isEmpty) continue;
          blocks.add(
            ProcessContentBlock(
              type: item.stage == 'searching'
                  ? ProcessContentBlockType.searchSummary
                  : ProcessContentBlockType.analysisSummary,
              text: item.displayMessage,
              references: refs,
            ),
          );
          break;
        case ProcessJournalEventType.stageSet:
        case ProcessJournalEventType.answerDelta:
        case ProcessJournalEventType.completed:
          continue;
      }
    }
    return blocks;
  }

  ProcessStage _stageFromProcessJournal(List<ProcessJournalEvent> journal) {
    final snapshot = _displayProcessJournalSnapshot(journal);
    for (var i = snapshot.length - 1; i >= 0; i--) {
      final stage = snapshot[i].stage.trim();
      switch (stage) {
        case 'completed':
          return ProcessStage.completed;
        case 'answering':
          return ProcessStage.answering;
        case 'analyzing':
          return ProcessStage.analyzing;
        case 'searching':
          return ProcessStage.searching;
        case 'understanding':
          return ProcessStage.understanding;
      }
    }
    return ProcessStage.understanding;
  }

  bool _appendStreamingProcessJournalEvent(ProcessJournalEvent event) {
    final messageId = _activeAssistantStreamingMessageId;
    if (messageId == null || messageId.isEmpty) return false;
    final index = _messages.indexWhere(
      (item) => (item['id'] as String?) == messageId,
    );
    if (index < 0) return false;
    final currentJournal = _normalizeProcessJournal(
      (((_messages[index]['runArtifacts'] as Map?)?['processJournal'] as List?)
              ?.whereType<Map>()
              .toList(growable: false)) ??
          const <Map>[],
    );
    final mergedJournal = _mergeProcessJournalEvents(
      currentJournal,
      <ProcessJournalEvent>[event],
    );
    final updatedRunArtifacts = Map<String, dynamic>.from(
      ((_messages[index]['runArtifacts'] as Map?)?.cast<String, dynamic>()) ??
          const <String, dynamic>{},
    )..['processJournal'] = mergedJournal
        .map((item) => item.toJson())
        .toList(growable: false);
    _messages[index] = <String, dynamic>{
      ..._messages[index],
      'runArtifacts': updatedRunArtifacts,
      'uiProcessContentBlocks': _serializeProcessBlocks(
        _processBlocksFromJournal(mergedJournal),
      ),
    };
    _currentProcessJournal = mergedJournal;
    return true;
  }

  List<ProcessContentBlock> _processBlocksFromTimelineV2(
    List<Map<String, dynamic>> timeline,
  ) {
    final blocks = <ProcessContentBlock>[];
    for (final item in timeline) {
      final summary = (item['summary'] as String?)?.trim() ?? '';
      final references =
          (item['references'] as List?)
              ?.whereType<Map>()
              .map((ref) => ref.cast<String, dynamic>())
              .map(
                (ref) => ProcessReference(
                  title: (ref['title'] as String?)?.trim() ?? '',
                  url: (ref['url'] as String?)?.trim() ?? '',
                  source: (ref['source'] as String?)?.trim() ?? '',
                ),
              )
              .where((ref) => ref.title.isNotEmpty && ref.url.isNotEmpty)
              .toList(growable: false) ??
          const <ProcessReference>[];
      if (summary.isEmpty && references.isEmpty) continue;
      final scope = (item['scope'] as String?)?.trim() ?? '';
      final payload =
          (item['payload'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final stage = _stageFromUserEventPayload(payload);
      final type = references.isNotEmpty
          ? (stage == ProcessStage.searching || scope == 'skill'
                ? ProcessContentBlockType.searchSummary
                : ProcessContentBlockType.analysisSummary)
          : ProcessContentBlockType.text;
      blocks.add(
        ProcessContentBlock(type: type, text: summary, references: references),
      );
    }
    return blocks;
  }

  List<Map<String, dynamic>> _mergeProcessTimelineV2(
    List<Map<String, dynamic>> streamed,
    List<Map<String, dynamic>> completed,
  ) {
    final merged = streamed
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: true);
    final appendKeys = <String>{
      for (final item in merged.where(
        (entry) => (entry['type'] as String?) == 'processAppend',
      ))
        _timelineAppendKey(item),
    };
    for (final raw in completed) {
      final item = Map<String, dynamic>.from(raw);
      final type = (item['type'] as String?)?.trim() ?? '';
      if (type == 'processAppend') {
        final appendKey = _timelineAppendKey(item);
        if (appendKeys.contains(appendKey)) continue;
        appendKeys.add(appendKey);
        merged.add(item);
        continue;
      }
      final nodeKey = _timelineNodeKey(item);
      if (nodeKey.isEmpty) {
        merged.add(item);
        continue;
      }
      final existingIndex = merged.indexWhere(
        (entry) => _timelineNodeKey(entry) == nodeKey,
      );
      if (existingIndex < 0) {
        merged.add(item);
        continue;
      }
      merged[existingIndex] = _mergeTimelineEntry(merged[existingIndex], item);
    }
    return merged;
  }

  ProcessStage? _stageFromUserEventPayload(Map<String, dynamic> payload) {
    final raw = (payload['stage'] as String?)?.trim().toLowerCase() ?? '';
    switch (raw) {
      case 'understanding':
        return ProcessStage.understanding;
      case 'searching':
        return ProcessStage.searching;
      case 'analyzing':
        return ProcessStage.analyzing;
      case 'answering':
        return ProcessStage.answering;
      case 'completed':
        return ProcessStage.completed;
      default:
        return null;
    }
  }

  String _timelineNodeKey(Map<String, dynamic> item) {
    final scope = (item['scope'] as String?)?.trim() ?? '';
    final nodeId = (item['nodeId'] as String?)?.trim() ?? '';
    final runId = (item['runId'] as String?)?.trim() ?? '';
    if (scope.isEmpty && nodeId.isEmpty && runId.isEmpty) return '';
    return '$scope::$nodeId::$runId';
  }

  String _timelineAppendKey(Map<String, dynamic> item) {
    final eventId = (item['eventId'] as String?)?.trim() ?? '';
    if (eventId.isNotEmpty) return eventId;
    return '${_timelineNodeKey(item)}::${(item['summary'] as String?)?.trim() ?? ''}';
  }

  Map<String, dynamic> _mergeTimelineEntry(
    Map<String, dynamic> existing,
    Map<String, dynamic> incoming,
  ) {
    final existingPayload =
        (existing['payload'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final incomingPayload =
        (incoming['payload'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final mergedPayload = <String, dynamic>{
      ...existingPayload,
      ...incomingPayload,
    };
    return <String, dynamic>{
      ...existing,
      ...incoming,
      'summary': _mergeTimelineSummary(
        (existing['summary'] as String?)?.trim() ?? '',
        (incoming['summary'] as String?)?.trim() ?? '',
        existingPayload,
        incomingPayload,
      ),
      'payload': mergedPayload,
      'references': _mergeTimelineReferences(existing, incoming),
    };
  }

  String _mergeTimelineSummary(
    String existingSummary,
    String incomingSummary,
    Map<String, dynamic> existingPayload,
    Map<String, dynamic> incomingPayload,
  ) {
    final current = existingSummary.trim();
    final incoming = incomingSummary.trim();
    if (incoming.isEmpty) return current;
    if (incomingPayload['streaming'] == true) {
      if (current.isEmpty) return incoming;
      if (incoming.startsWith(current)) return incoming;
      if (current.endsWith(incoming) || current.contains(incoming)) {
        return current;
      }
      final joiner = existingPayload['streaming'] == true ? '' : '\n\n';
      return '$current$joiner$incoming';
    }
    return incoming;
  }

  List<Map<String, dynamic>> _mergeTimelineReferences(
    Map<String, dynamic> existing,
    Map<String, dynamic> incoming,
  ) {
    final refs = <Map<String, dynamic>>[];
    final seenUrls = <String>{};
    for (final source in <Object?>[
      existing['references'],
      incoming['references'],
    ]) {
      final list =
          (source as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      for (final ref in list) {
        final url = (ref['url'] as String?)?.trim() ?? '';
        final title = (ref['title'] as String?)?.trim() ?? '';
        if (url.isEmpty || title.isEmpty || !seenUrls.add(url)) continue;
        refs.add(ref);
      }
    }
    return refs;
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
      final usageStats =
          ((message['uiUsageStats'] as Map?) ??
                  (message['uiUsageStatsV1'] as Map?))
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

  static final _jsonEnvelopeFragmentRe = RegExp(
    r'"?(contractVersion|turnPhase|thinkingText|assistant_turn|traceId"?\s*:|'
    r'"decision"|"toolPlan"|"nextAction"|"userMarkdown")',
  );

  static final _jsonKeyFragmentRe = RegExp(
    r'"?(contractVersion|decision|nextAction|toolPlan|thinkingText|'
    r'userMarkdown|messageKind|slotFillPlan|queryNormalization|'
    r'selfCheck|diagnostics|reasoningBasis|turnPhase|traceId|'
    r'queryTasks|contextSlots|subagentPlan|evidence|result|'
    r'confidence|reasoning|answerEligibility|missingCriticalSlots|'
    r'assistant_turn|provider|freshnessHoursMax|timeScope|queryVariants|'
    r'plan|answer|ask_user|tool_call)"?\s*:?',
  );
  static final _jsonSyntaxOnlyRe = RegExp(r'^[\s"{}:\[\],\\.]+$');

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
  }) {
    return GestureDetector(
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
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(UITextConstants.chatVoicePermissionDenied)),
      );
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
        _currentProcessState = const AssistantProcessState(
          stageLabel: UITextConstants.assistantPhaseUnderstanding,
        );
        _streamingThinkingText = '';
        _processContentBlocks = <ProcessContentBlock>[];
        _currentProcessJournal = <ProcessJournalEvent>[];
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
          'displayMarkdown': '',
          'displayPlainText': '',
          'machineEnvelope': '',
          'runArtifacts': <String, dynamic>{
            'processJournal': <Map<String, dynamic>>[],
          },
        });
      });
      _startAssistantProgress();
      try {
        final deviceProfile = _assistantDeviceProfileByWidth(
          _lastViewportWidth,
        );
        try {
          await ref.read(assistantRuntimeProvider).ensureRemoteConfigLoaded();
        } catch (error) {
          if (kDebugMode) {
            debugPrint('Assistant remote config load failed, continue: $error');
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
          capabilityCatalog: AssistentCapabilityCatalog.defaultCatalog,
          contextScopeHint: contextScope,
          privacyProfile: 'default',
          privacyPolicy:
              (contextScope['privacyPolicy'] as Map?)
                  ?.cast<String, dynamic>() ??
              const <String, dynamic>{},
        );
        // 商用模式默认优先远端模型链路，避免先走本地启发式导致垂类与总分总失效。
        final routeMode = CapabilityRouteMode.remotePreferred;
        AssistantRunResponse? response;
        try {
          await for (final streamEvent
              in ref
                  .read(capabilityGatewayProvider)
                  .runStream(request: request, mode: routeMode)) {
            switch (streamEvent.type) {
              case AssistantRunStreamEventType.trace:
                continue;
              case AssistantRunStreamEventType.answerReset:
                _resetStreamingAnswer();
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
              case AssistantRunStreamEventType.planStarted:
              case AssistantRunStreamEventType.searchProgress:
              case AssistantRunStreamEventType.thinkingProgress:
                continue;
              case AssistantRunStreamEventType.answerDelta:
                if ((streamEvent.chunkText ?? '').isNotEmpty) {
                  _appendStreamingAnswerChunk(streamEvent.chunkText!);
                }
                continue;
              case AssistantRunStreamEventType.processJournalEvent:
                final journalEvent = streamEvent.processJournalEvent;
                if (journalEvent != null) {
                  _consumeProcessJournalEvent(journalEvent);
                }
                continue;
              case AssistantRunStreamEventType.phaseTimeline:
              case AssistantRunStreamEventType.userPhaseEvent:
              case AssistantRunStreamEventType.userEvent:
              case AssistantRunStreamEventType.explainableFlowEvent:
              case AssistantRunStreamEventType.processUpdate:
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
        _resetStreamingAnswerDecoder();
        final effectiveSessionId =
            (runResponse.structuredResponse['effectiveSessionId'] as String?)
                ?.trim() ??
            _effectiveAssistantSessionId;
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
        final uiAnswer =
            (runResponse.structuredResponse['uiAnswer'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final uiUsageStats = _buildConversationCumulativeUsageStats(
          runUsageStats:
              ((runResponse.structuredResponse['uiUsageStats'] as Map?) ??
                      (runResponse.structuredResponse['uiUsageStatsV1'] as Map?))
                  ?.cast<String, dynamic>() ??
              const <String, dynamic>{},
          excludeMessageId: streamingAssistantMessageId,
        );
        final structuredJournal = _journalFromStructuredResponse(
          runResponse.structuredResponse,
        );
        final uiProcessTimelineV2 = structuredJournal.isNotEmpty
            ? _timelineFromJournal(structuredJournal)
            : _timelineV2FromStructuredResponse(runResponse.structuredResponse);
        final streamedTimelineV2 = (() {
          if (streamingAssistantMessageId == null) {
            return const <Map<String, dynamic>>[];
          }
          final existingIndex = _messages.indexWhere(
            (item) => (item['id'] as String?) == streamingAssistantMessageId,
          );
          if (existingIndex < 0) return const <Map<String, dynamic>>[];
          return _normalizeUiProcessTimelineV2(
            ((_messages[existingIndex]['uiProcessTimelineV2'] as List?)
                    ?.whereType<Map>()
                    .toList(growable: false)) ??
                const <Map>[],
          );
        })();
        final streamedJournal = (() {
          if (streamingAssistantMessageId == null) {
            return const <ProcessJournalEvent>[];
          }
          final existingIndex = _messages.indexWhere(
            (item) => (item['id'] as String?) == streamingAssistantMessageId,
          );
          if (existingIndex < 0) return const <ProcessJournalEvent>[];
          return _normalizeProcessJournal(
            (((_messages[existingIndex]['runArtifacts'] as Map?)?['processJournal']
                        as List?)
                    ?.whereType<Map>()
                    .toList(growable: false)) ??
                const <Map>[],
          );
        })();
        final mergedJournal = _mergeProcessJournalEvents(
          streamedJournal,
          structuredJournal,
        );
        final mergedTimelineV2 = mergedJournal.isNotEmpty
            ? _timelineFromJournal(mergedJournal)
            : _mergeProcessTimelineV2(streamedTimelineV2, uiProcessTimelineV2);
        final structuredProcessBlocks = _processBlocksFromStructuredResponse(
          runResponse.structuredResponse,
        );
        final effectiveProcessBlocks = mergedJournal.isNotEmpty
            ? _processBlocksFromJournal(mergedJournal)
            : mergedTimelineV2.isNotEmpty
            ? _processBlocksFromTimelineV2(mergedTimelineV2)
            : (structuredProcessBlocks.isNotEmpty
                  ? structuredProcessBlocks
                  : List<ProcessContentBlock>.of(_processContentBlocks));
        if (!mounted) return;
        setState(() {
          if (mergedJournal.isNotEmpty) {
            _currentProcessJournal = List<ProcessJournalEvent>.of(
              mergedJournal,
            );
            _processContentBlocks = List<ProcessContentBlock>.of(
              _processBlocksFromJournal(mergedJournal),
            );
          } else if (mergedTimelineV2.isNotEmpty) {
            _processContentBlocks = List<ProcessContentBlock>.of(
              _processBlocksFromTimelineV2(mergedTimelineV2),
            );
          } else if (structuredProcessBlocks.isNotEmpty) {
            _processContentBlocks = List<ProcessContentBlock>.of(
              structuredProcessBlocks,
            );
          }
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
                'displayMarkdown': runResponse.displayMarkdown,
                'displayPlainText': displayPlainText,
                'machineEnvelope': runResponse.machineEnvelope,
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
                'uiAnswer': uiAnswer,
                'uiUsageStats': uiUsageStats,
                'streamFinalAnswer': effectiveDisplayText,
                'streaming': false,
                'uiProcessContentBlocks': _serializeProcessBlocks(
                  effectiveProcessBlocks,
                ),
                'processThinkingText': _streamingThinkingText,
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
              'displayMarkdown': runResponse.displayMarkdown,
              'displayPlainText': displayPlainText,
              'machineEnvelope': runResponse.machineEnvelope,
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
              'uiAnswer': uiAnswer,
              'uiUsageStats': uiUsageStats,
              'uiProcessContentBlocks': _serializeProcessBlocks(
                effectiveProcessBlocks,
              ),
              'processThinkingText': _streamingThinkingText,
            });
          }
          _assistantResponding = false;
          _assistantPhaseLabel = '';
          _activeAssistantStreamingMessageId = null;
          _answerGateOpen = true;
          _currentProcessState = AssistantProcessState(
            stage: ProcessStage.completed,
            stageLabel: UITextConstants.assistantPhaseCompleted,
            contentBlocks: List<ProcessContentBlock>.of(effectiveProcessBlocks),
            usageStats: uiUsageStats,
            elapsedMs: elapsedMs,
          );
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
            .read(assistentLearningServiceProvider)
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
          'allowedCapabilities': AssistentCapabilityCatalog.defaultCatalog,
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
      if (openContext?.entityId != null) 'entityId': openContext!.entityId!,
      if (openContext?.tab != null) 'tab': openContext!.tab!,
      if (openContext?.dimension != null) 'dimension': openContext!.dimension!,
      'hints': hints,
      if (hints['behaviorTimeline'] is List<dynamic>)
        'behaviorTimeline': hints['behaviorTimeline'],
      if (userTags.isNotEmpty) 'userTags': userTags,
      if (latestDialogueState.isNotEmpty) 'dialogueState': latestDialogueState,
      if (latestRunArtifacts != null) 'runArtifacts': latestRunArtifacts.toJson(),
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
    final strippedXml = OpenAiCompatibleLlmProvider.stripXmlToolCalls(
      raw,
    ).trim();
    if (strippedXml.isEmpty) return '';
    if (_containsXmlToolCall(raw)) return '';
    if (_isInternalChunk(strippedXml)) return '';
    if (AssistantContentFilters.isDegradedText(strippedXml)) return '';
    if (AssistantContentFilters.isProgressPlaceholder(strippedXml)) return '';
    if (strippedXml.contains('tool_call') ||
        strippedXml.contains('queryTasks') ||
        strippedXml.contains('queryVariants') ||
        strippedXml.contains('正在调用工具')) {
      return '';
    }
    if (strippedXml.startsWith('{') ||
        strippedXml.startsWith('[') ||
        strippedXml.startsWith('```')) {
      final display = _stripJsonForDisplay(strippedXml).trim();
      if (display.isEmpty ||
          _isInternalChunk(display) ||
          AssistantContentFilters.isProgressPlaceholder(display)) {
        return '';
      }
      return display;
    }
    return strippedXml;
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
    try {
      final structured = response.structuredResponse;
      final uiAnswer =
          (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final answerPayload =
          (structured['answerPayload'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final parsed = LlmResponseParser.parse(response.finalText);
      final resultMap =
          (answerPayload['result'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final rawFinal = OpenAiCompatibleLlmProvider.stripXmlToolCalls(
        response.finalText,
      ).trim();
      final displayText = _firstCompletedDisplayCandidate(<String>[
        response.displayMarkdown,
        response.displayPlainText,
        (uiAnswer['markdownText'] as String?) ?? '',
        (answerPayload['userMarkdown'] as String?) ?? '',
        parsed.ok ? parsed.explicitUserMarkdown : '',
        (resultMap['text'] as String?) ?? '',
        rawFinal,
      ]);
      if (displayText.isNotEmpty) {
        return displayText;
      }
    } catch (_) {}

    final actionFallback = _actionLikeCompletedFallback(response);
    if (actionFallback.isNotEmpty) {
      return actionFallback;
    }

    return '助手未生成有效回答，请重试。';
  }

  String _resolveAssistantDisplayPlainText(AssistantRunResponse response) {
    final artifactPlain = _sanitizeCompletedDisplayCandidate(
      response.displayPlainText,
      allowJsonExtraction: false,
    );
    if (artifactPlain.isNotEmpty) {
      return artifactPlain;
    }
    return _resolveAssistantDisplayText(response);
  }

  /// Attempt to extract displayable text from a JSON-formatted LLM output.
  String _stripJsonForDisplay(String jsonText) {
    try {
      final dynamic raw = const JsonDecoder().convert(jsonText);
      if (raw is! Map) return '';
      final decoded = raw.cast<String, dynamic>();
      final payload = decoded;

      final uiAns =
          ((payload['uiAnswer'] as Map?) ?? (decoded['uiAnswer'] as Map?))
              ?.cast<String, dynamic>();
      final answerPayload =
          ((payload['answerPayload'] as Map?) ??
                  (decoded['answerPayload'] as Map?))
              ?.cast<String, dynamic>();
      final topResult =
          (payload['result'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final nestedResult =
          (answerPayload?['result'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      return _firstCompletedDisplayCandidate(<String>[
        (uiAns?['markdownText'] as String?) ?? '',
        (payload['userMarkdown'] as String?) ?? '',
        (answerPayload?['userMarkdown'] as String?) ?? '',
        (topResult['text'] as String?) ?? '',
        (nestedResult['text'] as String?) ?? '',
      ]);
    } catch (_) {}
    return '';
  }

  /// 判断文本是否为内部 JSON 信封 / think 标签残留 / XML tool-call / 结构化协议字段，
  /// 不应展示给用户。
  bool _isInternalChunk(String value) {
    final t = value.trim();
    if (t.isEmpty) return false;
    if (t == '</think>' || t == '<think>') return true;
    if (AssistantContentFilters.isJsonEnvelope(t)) return true;
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
      'machineEnvelope': response.machineEnvelope,
      'runArtifacts': response.runArtifacts?.toJson() ?? const <String, dynamic>{},
      'createdAt': DateTime.now().toIso8601String(),
      'uiReferences':
          (structured['uiReferences'] as List?)?.whereType<Map>().toList(
            growable: false,
          ) ??
          const <Map>[],
      'uiUsageStats':
          ((structured['uiUsageStats'] as Map?) ??
                  (structured['uiUsageStatsV1'] as Map?))
              ?.cast<String, dynamic>() ??
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
        .read(assistentLearningServiceProvider)
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
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(UITextConstants.assistantFeedbackSubmitted)),
    );
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
        .read(assistentLearningServiceProvider)
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
      capabilityCatalog: AssistentCapabilityCatalog.defaultCatalog,
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
      _currentProcessState = AssistantProcessState(
        stage: ProcessStage.answering,
        stageLabel: UITextConstants.assistantPhaseAnswering,
        isStreaming: true,
      );
      _currentProcessJournal = <ProcessJournalEvent>[];
      _processContentBlocks = <ProcessContentBlock>[];
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
        'displayMarkdown': '',
        'displayPlainText': '',
        'machineEnvelope': '',
        'runArtifacts': <String, dynamic>{
          'processJournal': <Map<String, dynamic>>[],
        },
      });
    });
    _autoScrollToBottomIfNeeded();
    try {
      AssistantRunResponse? response;
      final routeMode = CapabilityRouteMode.localOnly;
      await for (final streamEvent
          in ref
              .read(capabilityGatewayProvider)
              .runStream(request: request, mode: routeMode)) {
        switch (streamEvent.type) {
          case AssistantRunStreamEventType.answerReset:
            _resetStreamingAnswer();
            continue;
          case AssistantRunStreamEventType.processJournalEvent:
            final journalEvent = streamEvent.processJournalEvent;
            if (journalEvent != null) {
              _consumeProcessJournalEvent(journalEvent);
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
        final uiAnswer =
            (finalResponse.structuredResponse['uiAnswer'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final structuredJournal = _journalFromStructuredResponse(
          finalResponse.structuredResponse,
        );
        final structuredProcessBlocks = _processBlocksFromStructuredResponse(
          finalResponse.structuredResponse,
        );
        final uiUsageStats = _buildConversationCumulativeUsageStats(
          runUsageStats:
              ((finalResponse.structuredResponse['uiUsageStats'] as Map?) ??
                      (finalResponse.structuredResponse['uiUsageStatsV1'] as Map?))
                  ?.cast<String, dynamic>() ??
              const <String, dynamic>{},
          excludeMessageId: streamingAssistantMessageId,
        );
        final streamedRunArtifacts =
            (_messages.firstWhere(
                  (item) => (item['id'] as String?) == streamingAssistantMessageId,
                  orElse: () => const <String, dynamic>{},
                )['runArtifacts'] as Map?)
                ?.cast<String, dynamic>();
        final streamedJournal = _normalizeProcessJournal(
          (streamedRunArtifacts?['processJournal'] as List?)
                  ?.whereType<Map>()
                  .map((item) => item.cast<String, dynamic>())
                  .toList(growable: false) ??
              const <Map<String, dynamic>>[],
        );
        final effectiveJournal = _mergeProcessJournalEvents(
          streamedJournal,
          structuredJournal,
        );
        final effectiveProcessBlocks = effectiveJournal.isNotEmpty
            ? _processBlocksFromJournal(effectiveJournal)
            : (structuredProcessBlocks.isNotEmpty
                  ? structuredProcessBlocks
                  : List<ProcessContentBlock>.of(_processContentBlocks));
        final finalText = _resolveAssistantDisplayText(finalResponse);
        final displayPlainText = _resolveAssistantDisplayPlainText(
          finalResponse,
        );
        _resetStreamingAnswerDecoder();
        setState(() {
          if (effectiveJournal.isNotEmpty) {
            _currentProcessJournal = List<ProcessJournalEvent>.of(
              effectiveJournal,
            );
            _processContentBlocks = List<ProcessContentBlock>.of(
              _processBlocksFromJournal(effectiveJournal),
            );
          } else if (structuredProcessBlocks.isNotEmpty) {
            _processContentBlocks = List<ProcessContentBlock>.of(
              structuredProcessBlocks,
            );
          }
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
              'streamFinalAnswer': effectiveFinalText,
              'streaming': false,
              'sourceQuery': query,
              'displayMarkdown': finalResponse.displayMarkdown,
              'displayPlainText': displayPlainText,
              'machineEnvelope': finalResponse.machineEnvelope,
              'degraded': finalResponse.degraded,
              'qualityMetrics':
                  (finalResponse.structuredResponse['qualityMetrics'] as Map?)
                      ?.cast<String, dynamic>() ??
                  const <String, dynamic>{},
              'heuristicFallbackUsed':
                  (((finalResponse.structuredResponse['qualityMetrics'] as Map?)
                      ?.cast<String, dynamic>())?['heuristicFallbackUsed']) ==
                  true,
              'runArtifacts': <String, dynamic>{
                ...(finalResponse.runArtifacts?.toJson() ??
                    const <String, dynamic>{}),
                'processJournal': effectiveJournal
                    .map((item) => item.toJson())
                    .toList(growable: false),
              },
              'uiAnswer': uiAnswer,
              'uiProcessContentBlocks': _serializeProcessBlocks(
                effectiveProcessBlocks,
              ),
              'uiUsageStats': uiUsageStats,
            };
          }
          _currentProcessState = AssistantProcessState(
            stage: ProcessStage.completed,
            stageLabel: UITextConstants.assistantPhaseCompleted,
            contentBlocks: List<ProcessContentBlock>.of(effectiveProcessBlocks),
            usageStats: uiUsageStats,
          );
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
          _currentProcessState = AssistantProcessState(
            stage: ProcessStage.completed,
            stageLabel: UITextConstants.assistantPhaseCompleted,
            contentBlocks: List<ProcessContentBlock>.of(_processContentBlocks),
          );
        });
      }
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
    final models = ref.read(assistantRuntimeProvider).listAvailableModels();
    if (models.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(UITextConstants.assistantModelUnavailable)),
      );
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
    ref.read(assistantRuntimeProvider).switchModel(selected);
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
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          opened
              ? url
              : allowOpen
              ? UITextConstants.assistantReferenceOpenFailed
              : UITextConstants.assistantReferenceHostBlocked,
        ),
      ),
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
              ref.read(assistentLearningServiceProvider).latestScoreSnapshot(),
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
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text(UITextConstants.copiedToClipboard)),
            );
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

    return Stack(
      children: [
        Scaffold(
          backgroundColor: bgColor,
          appBar: AppBar(
            backgroundColor: bgColor,
            elevation: 0,
            centerTitle: _isAssistantConversation,
            leading: _isSelectionMode
                ? IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: _cancelSelection,
                  )
                : IconButton(
                    icon: const Icon(Icons.arrow_back),
                    onPressed: widget.onBack,
                  ),
            title: Text(
              _isSelectionMode
                  ? '已选 ${_selectedIds.length} 条'
                  : _conversationTitle,
              style: TextStyle(
                color: fgPrimary,
                fontSize: AppTypography.xl,
                fontWeight: FontWeight.w600,
              ),
            ),
            actions: [
              if (_isSelectionMode)
                TextButton(
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
              else ...[
                if (_isAssistantConversation)
                  IconButton(
                    icon: const Icon(CupertinoIcons.gear),
                    tooltip: UITextConstants.settings,
                    onPressed: _openAssistantSettingsPage,
                  )
                else
                  IconButton(
                    icon: const Icon(Icons.more_horiz),
                    onPressed: () => context.push(
                      AppRoutePaths.chatSettings(id: widget.conversationId),
                    ),
                  ),
              ],
            ],
          ),
          body: Column(
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
                                      chatMessageProvider(
                                        widget.conversationId,
                                      ),
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
                                      .container]?[DesignSemanticConstants
                                      .sm] ??
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
                                                Theme.of(context)
                                                    .textTheme
                                                    .bodySmall
                                                    ?.fontSize ??
                                                AppSpacing.containerSm,
                                            color: fgPrimary.withValues(
                                              alpha: 0.5,
                                            ),
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
                                    isSelected: _selectedIds.contains(
                                      msg['id'],
                                    ),
                                    onLongPressStart: (details) =>
                                        _onLongPressMessage(
                                          msg,
                                          details.globalPosition,
                                        ),
                                    onTap: _isSelectionMode
                                        ? () =>
                                              _toggleSelect(msg['id'] as String)
                                        : null,
                                    hideAvatarAndName: _isAssistantConversation,
                                    useFullWidth: _isAssistantConversation,
                                    renderSelfTextWithoutBubble:
                                        _isAssistantConversation,
                                    processState:
                                        _isAssistantConversation &&
                                            index == _messages.length - 1 &&
                                            isAssistantMessage &&
                                            (_assistantResponding ||
                                                _streamingThinkingText
                                                    .isNotEmpty)
                                        ? _currentProcessState
                                        : null,
                                    flowEvents:
                                        _isAssistantConversation &&
                                            index == _messages.length - 1 &&
                                            isAssistantMessage &&
                                            (_assistantResponding ||
                                                _currentFlowEvents.isNotEmpty)
                                        ? _currentFlowEvents
                                        : const <ExplainableFlowEvent>[],
                                    streamingThinkingText:
                                        _isAssistantConversation &&
                                            index == _messages.length - 1 &&
                                            isAssistantMessage
                                        ? _streamingThinkingText
                                        : '',
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
                                                    .assistantRunningHint)
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
                                        ? () =>
                                              _showAssistantNegativeFeedbackSheet(
                                                msg,
                                              )
                                        : null,
                                    onFeedbackCorrect: isAssistantMessage
                                        ? () =>
                                              _showAssistantCorrectionSheet(msg)
                                        : null,
                                    onCopyAnswer: isAssistantMessage
                                        ? () async {
                                            final content =
                                                (msg['content'] as String?) ??
                                                '';
                                            if (content.isEmpty) return;
                                            await Clipboard.setData(
                                              ClipboardData(text: content),
                                            );
                                            if (!mounted) return;
                                            ScaffoldMessenger.of(
                                              this.context,
                                            ).showSnackBar(
                                              SnackBar(
                                                content: Text(
                                                  UITextConstants
                                                      .copiedToClipboard,
                                                ),
                                              ),
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
                                                (msg['content'] as String?) ??
                                                '';
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
                                            ScaffoldMessenger.of(
                                              this.context,
                                            ).showSnackBar(
                                              SnackBar(
                                                content: Text(
                                                  UITextConstants
                                                      .assistantBookmarked,
                                                ),
                                              ),
                                            );
                                          }
                                        : null,
                                    onRegenerateAnswer: isAssistantMessage
                                        ? () => _requestAssistantRewrite(
                                            message: msg,
                                            mode: 'regenerate',
                                          )
                                        : null,
                                    onRegenerateOptionSelected:
                                        isAssistantMessage
                                        ? (option) =>
                                              _requestAssistantRewriteV2(
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
                                        ? () =>
                                              _switchAssistantModelAndRegenerate(
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
                                        ? (refItem) => _onAssistantReferenceTap(
                                            msg,
                                            refItem,
                                          )
                                        : null,
                                    onAvatarTap: isAssistantMessage
                                        ? () {
                                            final target = VisitTarget.page(
                                              'chat',
                                            );
                                            final service = ref.read(
                                              visitRecorderServiceProvider,
                                            );
                                            final ctx = AssistantOpenContext(
                                              source: AssistantSource.chat,
                                              visitTarget: target,
                                              experienceLevel: service
                                                  .getExperience(target),
                                            );
                                            AssistantHalfSheet.show(
                                              context,
                                              ctx,
                                            );
                                          }
                                        : () {
                                            final senderId =
                                                msg['senderId'] as String? ??
                                                '';
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
                                      color: Colors.black.withValues(
                                        alpha: 0.04,
                                      ),
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
                                        child:
                                            const CupertinoActivityIndicator(),
                                      )
                                    else
                                      Icon(
                                        CupertinoIcons.chevron_up,
                                        size: AppSpacing.iconSmall,
                                        color: fgPrimary.withValues(
                                          alpha: 0.56,
                                        ),
                                      ),
                                    if (!_assistantLoadingOlderHistory)
                                      SizedBox(width: AppSpacing.xs / 2),
                                    Text(
                                      UITextConstants.assistantViewHistory,
                                      style: TextStyle(
                                        fontSize: AppTypography.sm,
                                        color: fgPrimary.withValues(
                                          alpha: 0.72,
                                        ),
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
                    if (_showScrollFab && _assistantResponding)
                      Positioned(
                        bottom: 16,
                        left: 0,
                        right: 0,
                        child: Center(
                          child: StreamingScrollFab(onTap: _scrollToBottom),
                        ),
                      ),
                  ],
                ),
              ),
              Padding(
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
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (!_isAssistantConversation &&
                            !_isGroupChat &&
                            _relationshipCapability?.isSameInterest != true &&
                            _otherParticipantId != null)
                          _buildSameInterestPromptBar(),
                        CustomizableChatInputBar(
                          controller: _inputController,
                          focusNode: _inputFocusNode,
                          hintText: _isAssistantConversation
                              ? UITextConstants.assistantAskPlaceholder
                              : null,
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
                          leftBuilder: _isAssistantConversation
                              ? _buildAssistantLeftButton
                              : _buildQuliaoLeftButton,
                          rightBuilder: _isAssistantConversation
                              ? _buildAssistantRightButtons
                              : _buildQuliaoRightButtons,
                          extraPanelItems: _isAssistantConversation
                              ? const <ChatInputExtraPanelItem>[]
                              : _buildCallPanelItems(),
                        ),
                        if (_showEmojiPanel && !_isAssistantConversation)
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
