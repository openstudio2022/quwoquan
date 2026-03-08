// ignore_for_file: unused_import, unnecessary_underscores

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
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:quwoquan_app/components/input/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_engine_provider.dart';
import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_response_parser.dart';
import 'package:quwoquan_app/personal_assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/ui/assistant/config/assistant_prompt_config.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_dev_replay_page.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_chat_settings_page.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_manager.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/chat_message_bubble.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/regenerate_options_popup.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/streaming_scroll_fab.dart';
import 'package:quwoquan_app/ui/chat/widgets/session/assistant_session_header.dart';

/// 仅显示「上午/下午 HH:mm」，不显示「今天」或日期（图一）
String formatChatTime(String? raw) {
  if (raw == null || raw.isEmpty) return '';
  final s = raw.replaceFirst(RegExp(r'^(今天|昨天)\s*'), '').trim();
  final am = UITextConstants.timeFormatAM;
  final pm = UITextConstants.timeFormatPM;
  if (s.startsWith(am) || s.startsWith(pm)) return s;
  final match = RegExp(r'^(\d{1,2}):(\d{2})$').firstMatch(s);
  if (match != null) {
    final h = int.tryParse(match.group(1) ?? '0') ?? 0;
    final m = match.group(2) ?? '00';
    if (h < 12) return '$am$h:$m';
    return '$pm${h == 12 ? 12 : h - 12}:$m';
  }
  return s;
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
  final TextEditingController _inputController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  List<Map<String, dynamic>> _messages = [];
  String? _resolvedTitle;
  bool _isSelectionMode = false;
  final Set<String> _selectedIds = {};
  Map<String, dynamic>? _actionMenuMessage;
  Offset? _actionMenuPosition;
  bool _showEmojiPanel = false;
  final FocusNode _inputFocusNode = FocusNode();
  bool _assistantResponding = false;
  List<String> _availableSkillNames = const <String>[];
  final Map<String, Map<String, dynamic>> _assistantReplayByMessageId =
      <String, Map<String, dynamic>>{};
  final List<Map<String, dynamic>> _assistantReplayRecords =
      <Map<String, dynamic>>[];
  final Map<String, String> _assistantFeedbackStatusByMessageId =
      <String, String>{};
  double _lastViewportWidth = 390;
  int _assistantSearchingCount = 0;
  int _assistantReferenceCount = 0;

  /// 当前轮过程状态机展示文案（等待/深度搜索中/深度思考中），由 trace 事件驱动
  String _assistantPhaseLabel = '';
  String? _activeAssistantStreamingMessageId;

  /// v4: Unified process state for the single-drawer UI.
  AssistantProcessState _currentProcessState = const AssistantProcessState();

  /// Accumulated structured content blocks for the process drawer.
  List<ProcessContentBlock> _processContentBlocks = <ProcessContentBlock>[];

  /// Accumulated search references across all tool calls in a single run.
  List<ProcessReference> _collectedSearchRefs = <ProcessReference>[];

  /// Whether the user has scrolled away from the bottom during streaming.
  bool _userScrolledAway = false;

  /// Whether to show the scroll-to-bottom FAB.
  bool _showScrollFab = false;
  String _assistantRuntimeSessionId =
      AppConceptConstants.assistantConversationId;
  String _assistantTopicTitle = UITextConstants.assistantHistoryAll;
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
        final skills = await ref.read(assistantGatewayProvider).listSkills();
        if (!mounted) return;
        setState(() {
          _availableSkillNames = skills
              .where((s) => s.enabled)
              .map((s) => s.manifest.name)
              .toList(growable: false);
        });
      });
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        await _startFreshAssistantSessionOnOpen();
      });
    }
  }

  Future<void> _loadConversationTitle() async {
    if (_resolvedTitle != null) return;
    try {
      final conv = await ref
          .read(chatRepositoryProvider)
          .getConversation(widget.conversationId);
      if (mounted) {
        setState(() {
          _resolvedTitle = conv['title'] as String? ?? widget.conversationId;
        });
      }
    } catch (_) {}
  }

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
    _assistantSearchingCount = 0;
    _assistantReferenceCount = 0;
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

  Future<void> _syncAssistantSessionInfo() async {
    if (!_isAssistantConversation) return;
    final sessions = await ref.read(assistantGatewayProvider).listSessions();
    if (!mounted || sessions.isEmpty) return;
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
    }
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
          serial += 1;
          return <String, dynamic>{
            'id': 'assistant_${sessionId}_$serial',
            'conversationId': widget.conversationId,
            'type': 'text',
            'content': (item['content'] ?? '').toString(),
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
        .toList(growable: false);
    setState(() {
      // 始终使用 List.from 得到可 grow 列表，避免定长列表导致后续 add 抛 UnsupportedError。
      _messages = List<Map<String, dynamic>>.from(mapped);
      final topic = (detail['topicTitle'] as String?)?.trim();
      if (topic != null && topic.isNotEmpty) {
        _assistantTopicTitle = topic;
      }
    });
  }

  Future<void> _switchAssistantSession(String sessionId) async {
    if (sessionId.trim().isEmpty) return;
    await ref.read(assistantGatewayProvider).switchSession(sessionId);
    if (!mounted) return;
    setState(() => _assistantRuntimeSessionId = sessionId);
    await _loadAssistantSessionMessages(sessionId);
  }

  Future<void> _initiateCall(String callType) async {
    final notifier = ref.read(callSessionProvider.notifier);
    final callId = await notifier.initiateCall(
      callTypeStr: callType,
      targetUserIds: [widget.conversationId],
      conversationId: widget.conversationId,
    );
    if (callId != null && mounted) {
      context.push('/rtc/outgoing/$callId');
    }
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

  void _consumeAssistantTraceEvent(AssistantTraceEvent event) {
    if (!mounted || !_assistantResponding) return;
    final type = event.type;
    final data = event.data ?? const <String, dynamic>{};
    var searchingCount = _assistantSearchingCount;
    var referenceCount = _assistantReferenceCount;
    String? nextPhaseLabel;
    // streamDelta 是合成阶段 LLM 的原始输出 token，内容是 JSON 结构片段
    // （如 `"userMarkdown": "正在查询..."` 的字段名+值），绝对不能写入
    // streamFinalAnswer——这是导致进度文本泄露的根本原因。
    // 精美的最终 Markdown 通过 completed 事件的 uiAnswer.markdownText 展示，
    // 流式打字机效果通过 capability_gateway 的 chunk 事件（仅含已解析的
    // markdownText）驱动，两者都不依赖 streamDelta。
    if (type == AssistantTraceEventType.streamDelta) {
      return; // 完全忽略，不写 streamFinalAnswer
    }
    if (type == AssistantTraceEventType.toolStart &&
        _isSearchLikeTrace(event, data)) {
      searchingCount += 1;
      nextPhaseLabel = UITextConstants.assistantPhaseSearching;
    } else if (type == AssistantTraceEventType.toolStart) {
      nextPhaseLabel = UITextConstants.assistantPhaseSearching;
    }
    if (type == AssistantTraceEventType.toolResult ||
        type == AssistantTraceEventType.assistantDelta) {
      referenceCount = math.max(
        referenceCount,
        _extractReferenceCountFromTraceData(data),
      );
      if (type == AssistantTraceEventType.assistantDelta) {
        final phase = (data['phase'] as String?) ?? '';
        nextPhaseLabel = phase == 'analyzing'
            ? UITextConstants.assistantPhaseAnalyzing
            : UITextConstants.assistantPhaseThinking;
      }
      if (type == AssistantTraceEventType.toolResult &&
          data['isAssessment'] == true) {
        nextPhaseLabel = UITextConstants.assistantPhaseAssessing;
      }
    }
    if (type == AssistantTraceEventType.replanTriggered) {
      nextPhaseLabel = UITextConstants.assistantPhaseSearching;
    }
    final timelineChanged = _appendStreamingTimelineFromTrace(
      event: event,
      data: data,
      referenceCount: referenceCount,
    );
    final phaseChanged =
        nextPhaseLabel != null && nextPhaseLabel != _assistantPhaseLabel;
    final countChanged =
        searchingCount != _assistantSearchingCount ||
        referenceCount != _assistantReferenceCount;
    if (!phaseChanged && !countChanged && !timelineChanged) return;
    setState(() {
      if (nextPhaseLabel != null) _assistantPhaseLabel = nextPhaseLabel;
      _assistantSearchingCount = searchingCount;
      _assistantReferenceCount = referenceCount;
      // 同步更新 _currentProcessState，确保 trace 事件（来自远端/静默本地路径）
      // 也能驱动过程抽屉的阶段标签与动画状态更新
      if (nextPhaseLabel != null &&
          nextPhaseLabel != _currentProcessState.stageLabel) {
        _currentProcessState = _currentProcessState.copyWith(
          stageLabel: nextPhaseLabel,
          stage: _mapLabelToProcessStage(nextPhaseLabel),
          contentBlocks: List<ProcessContentBlock>.of(_processContentBlocks),
        );
      }
    });
  }

  ProcessStage _mapLabelToProcessStage(String label) {
    if (label == UITextConstants.assistantPhaseSearching) {
      return ProcessStage.searching;
    }
    if (label == UITextConstants.assistantPhaseAnalyzing ||
        label == UITextConstants.assistantPhaseAssessing ||
        label == UITextConstants.assistantPhaseThinking) {
      return ProcessStage.analyzing;
    }
    if (label == UITextConstants.assistantPhaseAnswering) {
      return ProcessStage.answering;
    }
    return ProcessStage.understanding;
  }

  void _consumeUserPhaseEvent(AssistantRunStreamEvent streamEvent) {
    if (!mounted || !_assistantResponding) return;
    final phaseType = streamEvent.userPhaseType;
    if (phaseType == null) return;
    final message = streamEvent.chunkText ?? '';
    final toolName = streamEvent.userPhaseToolName;
    final isExtracted = streamEvent.trace?.data?['extracted'] == true;

    final isThinkingType =
        phaseType == UserPhaseEventType.understandingThinking ||
        phaseType == UserPhaseEventType.analyzingThinking ||
        phaseType == UserPhaseEventType.toolReasoningThinking;
    if (isThinkingType && !isExtracted) {
      return;
    }

    String? nextPhaseLabel;
    late final String timelinePhaseType;
    String detail = isExtracted
        ? message.trim()
        : _sanitizeTraceDetail(message);

    switch (phaseType) {
      case UserPhaseEventType.understandingStarted:
        nextPhaseLabel = UITextConstants.assistantPhaseUnderstanding;
        timelinePhaseType = 'understanding';
      case UserPhaseEventType.understandingThinking:
        nextPhaseLabel = UITextConstants.assistantPhaseUnderstanding;
        timelinePhaseType = 'understanding';
      case UserPhaseEventType.toolExecutionStarted:
        nextPhaseLabel = UITextConstants.assistantPhaseSearching;
        timelinePhaseType = toolName != null ? 'tool:$toolName' : 'searching';
      case UserPhaseEventType.toolExecutionProgress:
        timelinePhaseType = toolName != null ? 'tool:$toolName' : 'searching';
      case UserPhaseEventType.toolExecutionCompleted:
        timelinePhaseType = toolName != null ? 'tool:$toolName' : 'searching';
      case UserPhaseEventType.toolReasoningStarted:
      case UserPhaseEventType.toolReasoningThinking:
        timelinePhaseType = 'understanding';
      case UserPhaseEventType.toolAssessmentStarted:
        nextPhaseLabel = UITextConstants.assistantPhaseAssessing;
        timelinePhaseType = 'assessing';
      case UserPhaseEventType.toolAssessmentResult:
        nextPhaseLabel = UITextConstants.assistantPhaseAssessing;
        timelinePhaseType = 'assessing';
      case UserPhaseEventType.analyzingStarted:
        nextPhaseLabel = UITextConstants.assistantPhaseAnalyzing;
        timelinePhaseType = 'analyzing';
      case UserPhaseEventType.analyzingThinking:
        nextPhaseLabel = UITextConstants.assistantPhaseAnalyzing;
        timelinePhaseType = 'analyzing';
      case UserPhaseEventType.answeringStarted:
        nextPhaseLabel = UITextConstants.assistantPhaseAnswering;
        timelinePhaseType = 'answering';
      case UserPhaseEventType.answeringDelta:
        return;
      case UserPhaseEventType.answeringCompleted:
        nextPhaseLabel = UITextConstants.assistantPhaseAnswering;
        timelinePhaseType = 'answering';
      case UserPhaseEventType.loopDegraded:
        timelinePhaseType = 'assessing';
    }

    _updateProcessContentBlocks(
      phaseType: phaseType,
      timelinePhaseType: timelinePhaseType,
      detail: detail,
      data: streamEvent.trace?.data,
    );

    final effectiveLabel = nextPhaseLabel;
    if (effectiveLabel != null && effectiveLabel != _assistantPhaseLabel) {
      setState(() {
        _assistantPhaseLabel = effectiveLabel;
        _currentProcessState = _currentProcessState.copyWith(
          stageLabel: effectiveLabel,
          stage: _mapPhaseToStage(timelinePhaseType),
          isStreaming: phaseType == UserPhaseEventType.answeringDelta,
          contentBlocks: List<ProcessContentBlock>.of(_processContentBlocks),
        );
      });
      _autoScrollToBottomIfNeeded();
    } else if (detail.isNotEmpty) {
      setState(() {
        _currentProcessState = _currentProcessState.copyWith(
          contentBlocks: List<ProcessContentBlock>.of(_processContentBlocks),
        );
      });
    }
  }

  /// Build structured content blocks for the process drawer.
  void _updateProcessContentBlocks({
    required UserPhaseEventType phaseType,
    required String timelinePhaseType,
    required String detail,
    Map<String, dynamic>? data,
  }) {
    final isSearchTool =
        timelinePhaseType == 'searching' ||
        (timelinePhaseType.startsWith('tool:') &&
            timelinePhaseType.contains('search'));
    final isExtracted = data?['extracted'] == true;

    if (phaseType == UserPhaseEventType.toolExecutionCompleted &&
        isSearchTool) {
      final refs = _extractReferencesFromData(data);
      if (refs.isNotEmpty) {
        final seenUrls = _collectedSearchRefs.map((r) => r.url).toSet();
        for (final ref in refs) {
          if (ref.url.isNotEmpty && !seenUrls.contains(ref.url)) {
            _collectedSearchRefs.add(ref);
            seenUrls.add(ref.url);
          }
        }
        _replaceOrAppendBlock(
          ProcessContentBlockType.searchSummary,
          ProcessContentBlock(
            type: ProcessContentBlockType.searchSummary,
            text: '搜索了 ${_collectedSearchRefs.length} 篇文档',
            references: List<ProcessReference>.of(_collectedSearchRefs),
          ),
        );
      }
    } else if (phaseType == UserPhaseEventType.analyzingStarted ||
        phaseType == UserPhaseEventType.analyzingThinking) {
      _replaceOrAppendBlock(
        ProcessContentBlockType.analysisSummary,
        ProcessContentBlock(
          type: ProcessContentBlockType.analysisSummary,
          text: '分析参考了 ${_collectedSearchRefs.length} 篇文档',
          references: List<ProcessReference>.of(_collectedSearchRefs),
        ),
      );
    } else if (detail.isNotEmpty) {
      if (isExtracted) {
        _replaceLastTextBlock(detail);
      } else {
        _processContentBlocks.add(
          ProcessContentBlock(type: ProcessContentBlockType.text, text: detail),
        );
      }
    }
  }

  /// Replace the last text block with extracted thinking text, removing
  /// any accumulated fragment blocks from the same reasoning phase.
  void _replaceLastTextBlock(String extractedText) {
    int lastTextIdx = -1;
    for (int i = _processContentBlocks.length - 1; i >= 0; i--) {
      if (_processContentBlocks[i].type == ProcessContentBlockType.text) {
        lastTextIdx = i;
        break;
      }
    }
    final block = ProcessContentBlock(
      type: ProcessContentBlockType.text,
      text: extractedText,
    );
    if (lastTextIdx >= 0) {
      _processContentBlocks[lastTextIdx] = block;
    } else {
      _processContentBlocks.add(block);
    }
  }

  /// Replace the first block of [type] in [_processContentBlocks], or append.
  void _replaceOrAppendBlock(
    ProcessContentBlockType type,
    ProcessContentBlock block,
  ) {
    final idx = _processContentBlocks.indexWhere((b) => b.type == type);
    if (idx >= 0) {
      _processContentBlocks[idx] = block;
    } else {
      _processContentBlocks.add(block);
    }
  }

  List<ProcessReference> _extractReferencesFromData(
    Map<String, dynamic>? data,
  ) {
    if (data == null) return const <ProcessReference>[];
    final rawRefs =
        (data['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    if (rawRefs.isEmpty) return const <ProcessReference>[];
    return rawRefs
        .map((ref) {
          final url = (ref['url'] as String?)?.trim() ?? '';
          final title = (ref['title'] as String?)?.trim() ?? '';
          final source =
              (ref['source'] as String?)?.trim() ??
              (Uri.tryParse(url)?.host ?? '');
          return ProcessReference(title: title, url: url, source: source);
        })
        .where((r) => r.url.isNotEmpty && r.title.isNotEmpty)
        .toList(growable: false);
  }

  ProcessStage _mapPhaseToStage(String timelinePhaseType) {
    if (timelinePhaseType == 'understanding') return ProcessStage.understanding;
    if (timelinePhaseType.startsWith('tool:') ||
        timelinePhaseType == 'searching') {
      return ProcessStage.searching;
    }
    if (timelinePhaseType == 'analyzing' || timelinePhaseType == 'assessing') {
      return ProcessStage.analyzing;
    }
    if (timelinePhaseType == 'answering') return ProcessStage.answering;
    return ProcessStage.understanding;
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

  /// Directly appends a streaming delta to the active assistant message.
  bool _appendStreamingTimelineFromTrace({
    required AssistantTraceEvent event,
    required Map<String, dynamic> data,
    required int referenceCount,
  }) {
    final messageId = _activeAssistantStreamingMessageId;
    if (messageId == null || messageId.isEmpty) return false;
    final index = _messages.indexWhere(
      (item) => (item['id'] as String?) == messageId,
    );
    if (index < 0) return false;
    final currentPhases =
        ((_messages[index]['uiPhaseTimelineV1'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: true)) ??
        <Map<String, dynamic>>[];
    String? nextPhaseType;
    String detail = '';
    String query = '';
    List<String> keywords = const <String>[];
    if (event.type == AssistantTraceEventType.toolStart &&
        _isSearchLikeTrace(event, data)) {
      nextPhaseType = 'searching';
      query = _extractSearchQueryFromTraceData(data);
      keywords = _extractSearchKeywords(query);
      detail = _sanitizeTraceDetail(event.message);
    } else if (event.type == AssistantTraceEventType.assistantDelta) {
      final searchQueries =
          (data['searchQueries'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      if (searchQueries.isNotEmpty) {
        nextPhaseType = 'searching';
        keywords = searchQueries.take(6).toList(growable: false);
        query = searchQueries.first;
        detail = '规划检索词：$query';
      } else {
        nextPhaseType = 'thinking';
        // assistantDelta.message 可能是原始 JSON，不能直接展示。
        // 提取有意义的思考摘要：若 message 不像 JSON，取前 60 字；否则留空由 summary 展示。
        final raw = _sanitizeTraceDetail(event.message);
        detail = raw.isNotEmpty ? raw : '';
      }
    } else if (event.type == AssistantTraceEventType.toolResult) {
      if (data['isAssessment'] == true) {
        // Merge assessment into searching phase with user-friendly message
        nextPhaseType = 'searching';
        final userMsg = (data['userMessage'] as String?) ?? '';
        detail = userMsg.isNotEmpty ? userMsg : '正在验证搜索结果...';
      } else {
        nextPhaseType = 'searching';
        detail = _sanitizeTraceDetail(event.message);
        final hasRefs = (data['references'] as List?)?.isNotEmpty ?? false;
        if (referenceCount <= 0 && detail.isEmpty && !hasRefs) return false;
      }
    } else if (event.type == AssistantTraceEventType.replanTriggered ||
        (event.type == AssistantTraceEventType.lifecycleStart &&
            event.message.toLowerCase().contains('replanning'))) {
      // Merge replan into searching phase
      nextPhaseType = 'searching';
      detail = '扩大搜索范围...';
    } else if (event.type == AssistantTraceEventType.thinkingProgress) {
      final phase = (data['phase'] as String?) ?? 'understanding';
      nextPhaseType = phase == 'analyzing' ? 'analyzing' : 'understanding';
      detail = _sanitizeTraceDetail(event.message);
    } else if (event.type == AssistantTraceEventType.subagentStart) {
      nextPhaseType = 'subagent_running';
      final goal = (data['goal'] as String?)?.trim() ?? '';
      detail = goal.isNotEmpty ? '子任务：$goal' : '启动并行研究';
    } else if (event.type == AssistantTraceEventType.subagentResult) {
      nextPhaseType = 'subagent_done';
      final summary = (data['summary'] as String?)?.trim() ?? '';
      detail = summary.isNotEmpty ? summary : '子任务完成';
    } else if (event.type == AssistantTraceEventType.subagentError) {
      nextPhaseType = 'subagent_done';
      detail = '子任务异常: ${(data['errorClass'] as String?) ?? 'unknown'}';
    }
    if (nextPhaseType == null) return false;
    final phase = _ensureStreamingPhase(
      phases: currentPhases,
      phaseType: nextPhaseType,
    );
    final details = _mutableStringList(phase['details']);
    phase['details'] = details;
    if (query.isNotEmpty) {
      final line = '检索查询：$query';
      if (!details.contains(line)) details.add(line);
    }
    if (keywords.isNotEmpty) {
      phase['keywords'] = keywords;
    }
    if (detail.isNotEmpty && !details.contains(detail)) {
      details.add(detail);
    }
    if (nextPhaseType == 'searching' || nextPhaseType == 'replan_searching') {
      final refs =
          (data['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final phaseRefs = _mutableMapList(phase['references']);
      phase['references'] = phaseRefs;
      final seen = phaseRefs
          .map((item) => (item['url'] as String?) ?? '')
          .where((item) => item.isNotEmpty)
          .toSet();
      for (final ref in refs) {
        final url = (ref['url'] as String?)?.trim() ?? '';
        if (url.isEmpty || seen.contains(url)) continue;
        phaseRefs.add(<String, dynamic>{
          'title': (ref['title'] ?? '').toString(),
          'url': url,
          'source': (ref['source'] ?? '').toString(),
          'provider': (ref['provider'] ?? '').toString(),
          'snippet': (ref['snippet'] ?? '').toString(),
        });
        seen.add(url);
      }
      phase['summary'] = phaseRefs.isEmpty
          ? '正在搜索相关资料'
          : '已找到 ${phaseRefs.length} 篇相关资料';
    } else if (nextPhaseType == 'thinking' || nextPhaseType == 'analyzing') {
      phase['summary'] = '正在分析与整理信息';
    } else if (nextPhaseType == 'understanding') {
      phase['summary'] = '正在分析您的问题...';
    } else if (nextPhaseType == 'assessing') {
      phase['summary'] = detail.isNotEmpty ? detail : '正在检查信息是否充分...';
      phase['status'] = 'completed';
    } else if (nextPhaseType == 'subagent_running') {
      if (detail.isNotEmpty) phase['summary'] = detail;
    } else if (nextPhaseType == 'subagent_done') {
      phase['status'] = 'completed';
      if (detail.isNotEmpty) phase['summary'] = detail;
    }
    _markStreamingPhaseStatus(currentPhases, activeType: nextPhaseType);
    _messages[index] = <String, dynamic>{
      ..._messages[index],
      'uiPhaseTimelineV1': currentPhases,
    };
    return true;
  }

  Map<String, dynamic> _ensureStreamingPhase({
    required List<Map<String, dynamic>> phases,
    required String phaseType,
  }) {
    final existingIndex = phases.lastIndexWhere(
      (item) =>
          (item['phaseType'] as String?) == phaseType &&
          (item['status'] as String?) == 'running',
    );
    if (existingIndex >= 0) return phases[existingIndex];
    final next = <String, dynamic>{
      'phaseId': 'phase_${phaseType}_${phases.length + 1}',
      'phaseType': phaseType,
      'status': 'running',
      'title': _phaseTitle(phaseType),
      'summary': _phaseSummary(phaseType),
      'details': <String>[],
      'references': <Map<String, dynamic>>[],
      'keywords': <String>[],
    };
    phases.add(next);
    return next;
  }

  List<String> _mutableStringList(Object? raw) {
    return ((raw as List?) ?? const <dynamic>[])
        .map((item) => item.toString())
        .toList(growable: true);
  }

  List<Map<String, dynamic>> _mutableMapList(Object? raw) {
    return ((raw as List?) ?? const <dynamic>[])
        .whereType<Map>()
        .map((item) => item.cast<String, dynamic>())
        .toList(growable: true);
  }

  void _markStreamingPhaseStatus(
    List<Map<String, dynamic>> phases, {
    required String activeType,
  }) {
    for (final phase in phases) {
      final type = (phase['phaseType'] as String?) ?? '';
      phase['status'] = type == activeType ? 'running' : 'completed';
    }
  }

  String _phaseTitle(String phaseType) {
    // v3: fixed user-facing phases
    if (phaseType == 'understanding') {
      return UITextConstants.assistantPhaseUnderstanding;
    }
    if (phaseType == 'analyzing') {
      return UITextConstants.assistantPhaseAnalyzing;
    }
    if (phaseType == 'answering') {
      return UITextConstants.assistantPhaseAnswering;
    }
    if (phaseType == 'assessing') {
      return UITextConstants.assistantPhaseAssessing;
    }
    // v3: tool phases from metadata (tool:web_search, tool:local_context, etc.)
    if (phaseType.startsWith('tool:')) {
      final toolName = phaseType.substring(5).split(':').first;
      // TODO: read from ToolMetadataRegistry.userInteractionForTool when available
      switch (toolName) {
        case 'web_search':
          return '搜索资料';
        case 'local_context':
          return '获取位置';
        case 'media_gallery':
          return '浏览相册';
        case 'intent_bridge':
          return '执行操作';
        default:
          return toolName;
      }
    }
    // Legacy compatibility
    switch (phaseType) {
      case 'searching':
        return '搜索资料';
      case 'thinking':
        return UITextConstants.assistantPhaseAnalyzing;
      case 'replan_searching':
        return '补充搜索';
      case 'subagent_running':
        return '并行研究';
      case 'subagent_done':
        return '子任务完成';
      default:
        return '处理中';
    }
  }

  String _phaseSummary(String phaseType) {
    // v3: fixed user-facing phases
    if (phaseType == 'understanding') return '正在分析您的问题...';
    if (phaseType == 'analyzing') return '正在分析获取到的信息...';
    if (phaseType == 'answering') return '正在组织回答...';
    if (phaseType == 'assessing') return '正在检查信息是否充分...';
    // v3: tool phases
    if (phaseType.startsWith('tool:')) {
      final toolName = phaseType.substring(5).split(':').first;
      switch (toolName) {
        case 'web_search':
          return '正在搜索相关资料';
        case 'local_context':
          return '正在获取您的位置';
        case 'media_gallery':
          return '正在浏览相册';
        case 'intent_bridge':
          return '正在执行操作';
        default:
          return '正在处理...';
      }
    }
    // Legacy compatibility
    switch (phaseType) {
      case 'searching':
      case 'replan_searching':
        return '正在搜索相关资料';
      case 'thinking':
        return '正在分析与整理信息';
      case 'answering':
        return '正在组织回答';
      case 'subagent_running':
        return '并行执行子任务';
      case 'subagent_done':
        return '子任务已完成';
      default:
        return '';
    }
  }

  bool _isSearchLikeTrace(
    AssistantTraceEvent event,
    Map<String, dynamic> data,
  ) {
    final toolNames = <String>[
      (data['tool'] ?? '').toString(),
      (data['toolName'] ?? '').toString(),
      (data['name'] ?? '').toString(),
    ].map((item) => item.trim().toLowerCase()).where((item) => item.isNotEmpty);
    for (final tool in toolNames) {
      if (tool == 'web_search' ||
          tool == 'knowledge_search' ||
          tool == 'search' ||
          tool == 'retrieval') {
        return true;
      }
    }
    final tokens = <String>[
      event.message,
      (data['tool'] ?? '').toString(),
      (data['toolName'] ?? '').toString(),
      (data['name'] ?? '').toString(),
      (data['description'] ?? '').toString(),
    ].map((item) => item.toLowerCase()).join(' ');
    return tokens.contains('search') ||
        tokens.contains('retrieval') ||
        tokens.contains('web');
  }

  String _extractSearchQueryFromTraceData(Map<String, dynamic> data) {
    final direct = (data['query'] as String?)?.trim() ?? '';
    if (direct.isNotEmpty) return direct;
    final keyword = (data['keyword'] as String?)?.trim() ?? '';
    if (keyword.isNotEmpty) return keyword;
    final args =
        (data['arguments'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final argsQuery = (args['query'] as String?)?.trim() ?? '';
    if (argsQuery.isNotEmpty) return argsQuery;
    final argsKeyword = (args['keyword'] as String?)?.trim() ?? '';
    if (argsKeyword.isNotEmpty) return argsKeyword;
    final keywords =
        (data['keywords'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (keywords.isNotEmpty) return keywords.join(' ');
    return '';
  }

  List<String> _extractSearchKeywords(String query) {
    final normalized = query.trim();
    if (normalized.isEmpty) return const <String>[];
    return normalized
        .split(RegExp(r'[\s,，。；;]+'))
        .where((item) => item.trim().isNotEmpty)
        .map((item) => item.trim())
        .take(6)
        .toList(growable: false);
  }

  String _sanitizeTraceDetail(String raw) {
    String text = raw.trim();
    if (text.isEmpty) return '';
    if (_isInternalChunk(text)) return '';
    if (_jsonKeyFragmentRe.hasMatch(text)) return '';
    if (_jsonSyntaxOnlyRe.hasMatch(text)) return '';
    if (text.startsWith('calling ') && text.length < 40) return '';
    if (text.contains('工具执行遇到问题') || text.contains('toolFailed')) return '';
    if (_internalErrorRe.hasMatch(text)) return '';
    if (_containsXmlToolCall(text)) {
      text = _stripXmlToolCalls(text);
      if (text.isEmpty) return '';
    }
    if (text.length <= 80) return text;
    return '${text.substring(0, 80)}...';
  }

  static final _internalErrorRe = RegExp(
    r'模板渲染失败|模板缺失|template.*not.?found|'
    r'模型调用失败|模型调用异常|HTTP [45]\d\d|'
    r'agent loop (started|finished)|llm request iteration|'
    r'model_answered_without_tools|'
    r'第 \d+ 轮推理|正在思考\.\.\.',
  );

  static final _jsonKeyFragmentRe = RegExp(
    r'"?(contractVersion|decision|nextAction|toolPlan|thinkingText|'
    r'userMarkdown|messageKind|slotFillPlan|queryNormalization|'
    r'selfCheck|diagnostics|reasoningBasis|turnPhase|traceId|'
    r'queryTasks|contextSlots|subagentPlan|evidence|result|'
    r'confidence|reasoning|answerEligibility|missingCriticalSlots|'
    r'assistant_turn_v4|plan|answer|ask_user|tool_call)"?\s*:?',
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

  String _stripXmlToolCalls(String text) =>
      text.replaceAll(_xmlToolCallTagRe, '').trim();

  int _extractReferenceCountFromTraceData(Map<String, dynamic> data) {
    final references = data['references'];
    if (references is List) return references.length;
    final items = data['items'];
    if (items is List) return items.length;
    final countRaw =
        data['count'] ?? data['referenceCount'] ?? data['resultCount'];
    if (countRaw is int) return countRaw;
    if (countRaw is String) return int.tryParse(countRaw.trim()) ?? 0;
    return 0;
  }

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
      final now = DateTime.now();
      final timeStr = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
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
              'timestamp': timeStr,
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

    final now = DateTime.now();
    final timeStr = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
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
        'timestamp': timeStr,
        'sentAtIso': now.toIso8601String(),
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
      setState(() {
        _ensureMessagesGrowable();
        streamingAssistantMessageId =
            'assistant_stream_${DateTime.now().millisecondsSinceEpoch}';
        _activeAssistantStreamingMessageId = streamingAssistantMessageId;
        _assistantResponding = true;
        _assistantPhaseLabel = UITextConstants.assistantPhaseUnderstanding;
        _assistantSearchingCount = 0;
        _assistantReferenceCount = 0;
        _currentProcessState = const AssistantProcessState(
          stageLabel: '正在理解问题...',
        );
        _processContentBlocks = <ProcessContentBlock>[];
        _collectedSearchRefs = <ProcessReference>[];
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
          'uiPhaseTimelineV1': <Map<String, dynamic>>[
            <String, dynamic>{
              'phaseId': 'phase_understanding_1',
              'phaseType': 'understanding',
              'status': 'running',
              'title': UITextConstants.assistantPhaseUnderstanding,
              'summary': '正在分析您的问题...',
              'details': <String>[],
              'references': <Map<String, dynamic>>[],
            },
          ],
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
              // 过滤错误消息：不发送降级/错误提示文本给 LLM
              if (m['isError'] == true) return false;
              final content = (m['content'] as String?)?.trim() ?? '';
              if (content.isEmpty) return false;
              // 过滤已知的降级/错误/进度文本，防止这类内容污染 LLM 历史
              if (content.startsWith('助手暂时不可用') ||
                  content.startsWith('模型调用失败') ||
                  content.startsWith('模型调用异常') ||
                  content.startsWith('当前模型服务不可用') ||
                  content.contains('HTTP 400') ||
                  content.contains('HTTP 500')) {
                return false;
              }
              // 过滤进度/占位文本
              if (content.contains('正在查询') ||
                  content.contains('正在获取') ||
                  content.contains('正在检索') ||
                  content.contains('正在搜索') ||
                  content.contains('正在为您') ||
                  content.contains('正在规划') ||
                  content.contains('正在执行')) {
                return false;
              }
              // 过滤未解析的 JSON 格式 assistant 消息（历史遗留）
              if (m['isSelf'] != true &&
                  content.startsWith('{') &&
                  (content.contains('"decision"') ||
                      content.contains('"contractVersion"'))) {
                return false;
              }
              return true;
            })
            .map(
              (m) => AssistantRunMessage(
                role: (m['isSelf'] == true) ? 'user' : 'assistant',
                content: (m['content'] as String?) ?? '',
              ),
            )
            .toList(growable: false);
        final contextScope = _buildAssistantContextScope();
        var domainId = 'fallback_general_search';
        try {
          final classified = await ref
              .read(assistantGatewayProvider)
              .classifyDomain(text, contextScope);
          if (classified.trim().isNotEmpty) {
            domainId = classified.trim();
          }
        } catch (error) {
          if (kDebugMode) {
            debugPrint(
              'Assistant classify domain failed, use fallback: $error',
            );
          }
        }
        contextScope['domainId'] = domainId;
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
        void appendStreamingChunk(String chunk) {
          if (!mounted) return;
          final messageId = streamingAssistantMessageId!;
          final value = chunk.trimRight();

          // 空 chunk 是重置信号：清除已积累的 streamFinalAnswer（用于 remote→local fallback）
          if (value.isEmpty) {
            setState(() {
              _ensureMessagesGrowable();
              final existingIndex = _messages.indexWhere(
                (item) => (item['id'] as String?) == messageId,
              );
              if (existingIndex >= 0) {
                _messages[existingIndex] = <String, dynamic>{
                  ..._messages[existingIndex],
                  'streamFinalAnswer': '',
                };
              }
            });
            return;
          }

          if (_isInternalChunk(value)) {
            return;
          }
          final now = DateTime.now();
          final ts = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
          setState(() {
            _ensureMessagesGrowable();
            final existingIndex = _messages.indexWhere(
              (item) => (item['id'] as String?) == messageId,
            );
            if (existingIndex >= 0) {
              final prev =
                  (_messages[existingIndex]['streamFinalAnswer'] as String?) ??
                  '';
              _messages[existingIndex] = <String, dynamic>{
                ..._messages[existingIndex],
                'streamFinalAnswer': '$prev$value',
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

        try {
          await for (final streamEvent
              in ref
                  .read(capabilityGatewayProvider)
                  .runStream(request: request, mode: routeMode)) {
            switch (streamEvent.type) {
              case AssistantRunStreamEventType.trace:
                if (streamEvent.trace != null) {
                  _consumeAssistantTraceEvent(streamEvent.trace!);
                }
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
                if (streamEvent.chunkText != null) {
                  appendStreamingChunk(streamEvent.chunkText!);
                }
                continue;
              case AssistantRunStreamEventType.completed:
                if (streamEvent.response != null) {
                  response = streamEvent.response;
                }
                break;
              // v2 semantic events
              case AssistantRunStreamEventType.planStarted:
                _consumeAssistantTraceEvent(
                  AssistantTraceEvent(
                    type: AssistantTraceEventType.planStarted,
                    message: streamEvent.chunkText ?? '规划中...',
                    timestamp: DateTime.now(),
                  ),
                );
                continue;
              case AssistantRunStreamEventType.searchProgress:
                _consumeAssistantTraceEvent(
                  AssistantTraceEvent(
                    type: AssistantTraceEventType.searchStarted,
                    message: streamEvent.chunkText ?? '检索中...',
                    timestamp: DateTime.now(),
                  ),
                );
                continue;
              case AssistantRunStreamEventType.thinkingProgress:
                _consumeAssistantTraceEvent(
                  AssistantTraceEvent(
                    type: AssistantTraceEventType.thinkingProgress,
                    message: streamEvent.chunkText ?? '思考中...',
                    timestamp: DateTime.now(),
                  ),
                );
                continue;
              case AssistantRunStreamEventType.answerDelta:
                if (streamEvent.chunkText != null) {
                  appendStreamingChunk(streamEvent.chunkText!);
                }
                continue;
              case AssistantRunStreamEventType.phaseTimeline:
                if (streamEvent.trace != null) {
                  _consumeAssistantTraceEvent(streamEvent.trace!);
                }
                continue;
              case AssistantRunStreamEventType.userPhaseEvent:
                _consumeUserPhaseEvent(streamEvent);
                continue;
              case AssistantRunStreamEventType.processUpdate:
                if (mounted) {
                  final data = streamEvent.trace?.data;
                  final stageStr = data?['stage'] as String? ?? '';
                  final processLines =
                      (data?['processLines'] as List?)
                          ?.whereType<String>()
                          .toList(growable: false) ??
                      const <String>[];
                  final isStreaming = data?['isStreaming'] == true;
                  setState(() {
                    _currentProcessState = AssistantProcessState(
                      stage: ProcessStage.values.firstWhere(
                        (s) => s.name == stageStr,
                        orElse: () => ProcessStage.understanding,
                      ),
                      stageLabel: streamEvent.chunkText ?? '处理中',
                      processLines: processLines,
                      isStreaming: isStreaming,
                    );
                  });
                  _autoScrollToBottomIfNeeded();
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
        final replyNow = DateTime.now();
        final replyTime =
            '${replyNow.hour}:${replyNow.minute.toString().padLeft(2, '0')}';
        final assistantMessageId =
            'assistant_${DateTime.now().millisecondsSinceEpoch}';
        final uiPhaseTimelineV1 = _normalizeUiPhaseTimelineV1(
          (runResponse.structuredResponse['uiPhaseTimelineV1'] as List?)
                  ?.whereType<Map>()
                  .map((item) => item.cast<String, dynamic>())
                  .toList(growable: false) ??
              const <Map<String, dynamic>>[],
        );
        final streamedPhases = (() {
          if (streamingAssistantMessageId == null) {
            return const <Map<String, dynamic>>[];
          }
          final existingIndex = _messages.indexWhere(
            (item) => (item['id'] as String?) == streamingAssistantMessageId,
          );
          if (existingIndex < 0) return const <Map<String, dynamic>>[];
          return ((_messages[existingIndex]['uiPhaseTimelineV1'] as List?)
                  ?.whereType<Map>()
                  .map((item) => item.cast<String, dynamic>())
                  .toList(growable: false)) ??
              const <Map<String, dynamic>>[];
        })();
        final mergedPhases = _normalizeUiPhaseTimelineV1(<Map<String, dynamic>>[
          ...streamedPhases,
          ...uiPhaseTimelineV1,
        ]);
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
        final uiUsageStatsV1 =
            (runResponse.structuredResponse['uiUsageStatsV1'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        setState(() {
          _ensureMessagesGrowable();
          if (streamingAssistantMessageId != null) {
            final existingIndex = _messages.indexWhere(
              (item) => (item['id'] as String?) == streamingAssistantMessageId,
            );
            if (existingIndex >= 0) {
              _messages[existingIndex] = <String, dynamic>{
                ..._messages[existingIndex],
                'id': assistantMessageId,
                'content': displayText,
                'timestamp': replyTime,
                'runId': runResponse.runId ?? '',
                'traceId': runResponse.traceId ?? '',
                'sourceQuery': text,
                'domainId': (dialogueRuntime['domainId'] ?? '').toString(),
                'dialogueState': dialogueRuntime,
                'uiPhaseTimelineV1': mergedPhases,
                'uiReferences': uiReferences,
                'uiActions': uiActions,
                'uiAnswer': uiAnswer,
                'uiUsageStatsV1': uiUsageStatsV1,
                'streamFinalAnswer': displayText,
                'streaming': false,
                'uiProcessContentBlocks': _processContentBlocks
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
                    .toList(growable: false),
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
              'domainId': (dialogueRuntime['domainId'] ?? '').toString(),
              'dialogueState': dialogueRuntime,
              'uiPhaseTimelineV1': mergedPhases,
              'uiReferences': uiReferences,
              'uiActions': uiActions,
              'uiAnswer': uiAnswer,
              'uiUsageStatsV1': uiUsageStatsV1,
              'uiProcessContentBlocks': _processContentBlocks
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
                  .toList(growable: false),
            });
          }
          _assistantResponding = false;
          _assistantPhaseLabel = '';
          _activeAssistantStreamingMessageId = null;
          _currentProcessState = AssistantProcessState(
            stage: ProcessStage.completed,
            stageLabel: '已完成',
            contentBlocks: List<ProcessContentBlock>.of(_processContentBlocks),
            usageStats: uiUsageStatsV1,
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
              answerText: runResponse.finalText,
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
            'timestamp': timeStr,
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
    final userTags =
        (hints['userTags'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    final latestDialogueState = _latestAssistantDialogueState();
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
      if (latestDialogueState['suggestedNextStateId'] is String &&
          (latestDialogueState['suggestedNextStateId'] as String)
              .trim()
              .isNotEmpty)
        'currentStateId':
            (latestDialogueState['suggestedNextStateId'] as String).trim(),
      'privacyProfile': 'default',
      'privacyPolicy': privacyPolicy,
    };
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

  String _resolveAssistantDisplayText(AssistantRunResponse response) {
    final structured = response.structuredResponse;

    // Gate 1: uiAnswer.markdownText — 引擎层已保证是纯文本
    final uiAnswer =
        (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final markdownText = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
    if (markdownText.isNotEmpty &&
        !AssistantContentFilters.isProgressPlaceholder(markdownText)) {
      return markdownText;
    }

    // Gate 2: answerPayload.userMarkdown
    final answerPayload =
        (structured['answerPayload'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final userMd = (answerPayload['userMarkdown'] as String?)?.trim() ?? '';
    if (userMd.isNotEmpty &&
        !_isInternalChunk(userMd) &&
        !AssistantContentFilters.isProgressPlaceholder(userMd)) {
      return userMd;
    }

    // Gate 3: LlmResponseParser 从 finalText 中提取 userMarkdown
    final parsed = LlmResponseParser.parse(response.finalText);
    if (parsed.ok) {
      final um = parsed.userMarkdown;
      if (um.isNotEmpty &&
          !_isInternalChunk(um) &&
          !AssistantContentFilters.isProgressPlaceholder(um)) {
        return um;
      }
    }

    // Gate 4: result.text 兜底
    final resultMap =
        (answerPayload['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final resultText = (resultMap['text'] as String?)?.trim() ?? '';
    if (resultText.isNotEmpty &&
        !_isInternalChunk(resultText) &&
        !AssistantContentFilters.isProgressPlaceholder(resultText)) {
      return resultText;
    }

    // Gate 5: degraded 场景 — 从 finalText 中剥离 JSON，提取可读内容
    final rawFinal = response.finalText.trim();
    // 优先尝试从任何 JSON 结构体中提取可读内容（不仅限于已知签名的信封格式）
    if (rawFinal.startsWith('{') || rawFinal.startsWith('[')) {
      final stripped = _stripJsonForDisplay(rawFinal);
      if (stripped.isNotEmpty) return stripped;
      // 是 JSON 但无法提取可读内容 → 返回降级提示而非裸 JSON
      return '助手未生成有效回答，请重试。';
    }
    if (rawFinal.isNotEmpty &&
        !AssistantContentFilters.isJsonEnvelope(rawFinal)) {
      return rawFinal;
    }
    if (rawFinal.isNotEmpty) {
      final stripped = _stripJsonForDisplay(rawFinal);
      if (stripped.isNotEmpty) return stripped;
    }

    return '助手未生成有效回答，请重试。';
  }

  /// Attempt to extract displayable text from a JSON-formatted LLM output.
  String _stripJsonForDisplay(String jsonText) {
    try {
      final dynamic raw = const JsonDecoder().convert(jsonText);
      if (raw is! Map) return '';
      final decoded = raw.cast<String, dynamic>();

      // Priority 1: uiAnswer.markdownText
      final uiAns = (decoded['uiAnswer'] as Map?)?.cast<String, dynamic>();
      final uiMd = (uiAns?['markdownText'] as String?)?.trim() ?? '';
      if (uiMd.isNotEmpty && uiMd.length > 5 && !uiMd.startsWith('{')) {
        return uiMd;
      }

      // Priority 2: userMarkdown (legacy top-level)
      final um = (decoded['userMarkdown'] as String?)?.trim() ?? '';
      if (um.isNotEmpty && um.length > 5 && !um.startsWith('{')) return um;

      // Priority 3: answerPayload.userMarkdown
      final answerPayload = (decoded['answerPayload'] as Map?)
          ?.cast<String, dynamic>();
      final apUm = (answerPayload?['userMarkdown'] as String?)?.trim() ?? '';
      if (apUm.isNotEmpty && apUm.length > 5 && !apUm.startsWith('{')) {
        return apUm;
      }

      // Priority 4: result.text (under answerPayload or top-level)
      final result =
          (decoded['result'] as Map?) ?? (answerPayload?['result'] as Map?);
      final text = (result?['text'] as String?)?.trim() ?? '';
      if (text.isNotEmpty && text.length > 5 && !text.startsWith('{')) {
        return text;
      }

      // Priority 5: any string field with reasonable length
      for (final entry in decoded.entries) {
        if (entry.value is String) {
          final v = (entry.value as String).trim();
          if (v.length > 10 && !v.startsWith('{') && !v.startsWith('[')) {
            return v;
          }
        }
      }
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
      'answer': response.finalText,
      'createdAt': DateTime.now().toIso8601String(),
      'uiPhaseTimelineV1': _normalizeUiPhaseTimelineV1(
        (structured['uiPhaseTimelineV1'] as List?)?.whereType<Map>().toList(
              growable: false,
            ) ??
            const <Map>[],
      ),
      'uiReferences':
          (structured['uiReferences'] as List?)?.whereType<Map>().toList(
            growable: false,
          ) ??
          const <Map>[],
      'uiUsageStatsV1':
          (structured['uiUsageStatsV1'] as Map?)?.cast<String, dynamic>() ??
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

  List<Map<String, dynamic>> _normalizeUiPhaseTimelineV1(List<Map> rawPhases) {
    final normalized = rawPhases
        .map((item) => item.cast<String, dynamic>())
        .where(
          (item) =>
              ((item['phaseType'] as String?)?.trim().isNotEmpty ?? false),
        )
        .toList(growable: false);
    if (normalized.isEmpty) return const <Map<String, dynamic>>[];
    final mergedByType = <String, Map<String, dynamic>>{};
    for (final phase in normalized) {
      final type = (phase['phaseType'] as String?)?.trim() ?? '';
      if (type.isEmpty) continue;
      final details =
          (phase['details'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      final references =
          (phase['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      if (!mergedByType.containsKey(type)) {
        mergedByType[type] = <String, dynamic>{
          'phaseId': (phase['phaseId'] ?? 'phase_${type}_1').toString(),
          'phaseType': type,
          'status': (phase['status'] ?? 'completed').toString(),
          'title': ((phase['title'] as String?)?.trim().isNotEmpty ?? false)
              ? (phase['title'] as String).trim()
              : _phaseTitle(type),
          'summary': ((phase['summary'] as String?)?.trim() ?? ''),
          'details': <String>[...details],
          'references': <Map<String, dynamic>>[...references],
          'keywords':
              (phase['keywords'] as List?)?.whereType<String>().toList(
                growable: false,
              ) ??
              const <String>[],
        };
        continue;
      }
      final current = mergedByType[type]!;
      current['status'] = (phase['status'] ?? current['status']).toString();
      final currentSummary = (phase['summary'] as String?)?.trim() ?? '';
      if (currentSummary.isNotEmpty) current['summary'] = currentSummary;
      final currentDetails = (current['details'] as List).cast<String>();
      for (final detail in details) {
        if (!currentDetails.contains(detail)) currentDetails.add(detail);
      }
      final currentRefs = (current['references'] as List)
          .cast<Map<String, dynamic>>();
      final seenUrls = currentRefs
          .map((item) => (item['url'] as String?) ?? '')
          .where((item) => item.isNotEmpty)
          .toSet();
      for (final ref in references) {
        final url = (ref['url'] as String?)?.trim() ?? '';
        if (url.isEmpty || seenUrls.contains(url)) continue;
        currentRefs.add(ref);
        seenUrls.add(url);
      }
    }
    return mergedByType.values.toList(growable: false);
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
          answerText: (message['content'] as String?) ?? '',
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
    setState(() {
      _ensureMessagesGrowable();
      streamingAssistantMessageId =
          'assistant_rewrite_${now.millisecondsSinceEpoch}';
      _activeAssistantStreamingMessageId = streamingAssistantMessageId;
      _assistantResponding = true;
      _assistantPhaseLabel = '正在重新生成...';
      _currentProcessState = AssistantProcessState(
        stage: ProcessStage.answering,
        stageLabel: '正在重新生成...',
        isStreaming: true,
      );
      _processContentBlocks = <ProcessContentBlock>[];
      _collectedSearchRefs = <ProcessReference>[];
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
          case AssistantRunStreamEventType.chunk:
          case AssistantRunStreamEventType.answerDelta:
            if (streamEvent.chunkText != null &&
                streamEvent.chunkText!.isNotEmpty &&
                streamingAssistantMessageId != null) {
              setState(() {
                _ensureMessagesGrowable();
                final idx = _messages.indexWhere(
                  (item) =>
                      (item['id'] as String?) == streamingAssistantMessageId,
                );
                if (idx >= 0) {
                  final prev =
                      (_messages[idx]['streamFinalAnswer'] as String?) ?? '';
                  _messages[idx] = <String, dynamic>{
                    ..._messages[idx],
                    'streamFinalAnswer': '$prev${streamEvent.chunkText}',
                  };
                }
              });
              _autoScrollToBottomIfNeeded();
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
        final uiAnswer =
            (response.structuredResponse['uiAnswer'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final mdText = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
        final finalText = mdText.isNotEmpty ? mdText : response.finalText;
        setState(() {
          _ensureMessagesGrowable();
          final idx = _messages.indexWhere(
            (item) => (item['id'] as String?) == streamingAssistantMessageId,
          );
          if (idx >= 0) {
            _messages[idx] = <String, dynamic>{
              ..._messages[idx],
              'content': finalText,
              'streamFinalAnswer': finalText,
              'streaming': false,
              'sourceQuery': query,
            };
          }
        });
      }
    } catch (_) {
      // Swallow exceptions; message will show whatever was streamed.
    } finally {
      if (mounted) {
        setState(() {
          _assistantResponding = false;
          _assistantPhaseLabel = '';
          _currentProcessState = AssistantProcessState(
            stage: ProcessStage.completed,
            stageLabel: '已完成',
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
                if (!_isAssistantConversation) ...[
                  IconButton(
                    icon: const Icon(CupertinoIcons.phone),
                    tooltip: UITextConstants.call,
                    onPressed: () => _initiateCall('voice'),
                  ),
                  IconButton(
                    icon: const Icon(CupertinoIcons.video_camera),
                    tooltip: UITextConstants.videoCall,
                    onPressed: () => _initiateCall('video'),
                  ),
                ],
                if (_isAssistantConversation)
                  IconButton(
                    icon: const Icon(CupertinoIcons.gear),
                    tooltip: UITextConstants.settings,
                    onPressed: _openAssistantSettingsPage,
                  )
                else
                  IconButton(
                    icon: const Icon(Icons.more_horiz),
                    onPressed: () =>
                        context.push('/chat/${widget.conversationId}/settings'),
                  ),
              ],
            ],
          ),
          body: Column(
            children: [
              if (_isAssistantConversation)
                AssistantSessionHeader(
                  fgPrimary: fgPrimary,
                  showWelcome: _messages.isEmpty,
                ),
              if (_isAssistantConversation &&
                  widget.assistantOpenContext != null)
                Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal:
                        AppSpacing.semantic[DesignSemanticConstants
                            .container]?[DesignSemanticConstants.sm] ??
                        AppSpacing.containerSm,
                    vertical: AppSpacing.sm,
                  ),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      AssistantPromptConfig.getWelcomeMessage(
                        widget.assistantOpenContext!,
                      ),
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgPrimary.withValues(alpha: 0.8),
                      ),
                    ),
                  ),
                ),
              if (_isAssistantConversation && _availableSkillNames.isNotEmpty)
                Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal:
                        AppSpacing.semantic[DesignSemanticConstants
                            .container]?[DesignSemanticConstants.sm] ??
                        AppSpacing.containerSm,
                    vertical: AppSpacing.xs,
                  ),
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: _availableSkillNames
                          .map(
                            (name) => Container(
                              margin: EdgeInsets.only(right: AppSpacing.xs),
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpacing.containerSm,
                                vertical: AppSpacing.xs,
                              ),
                              decoration: BoxDecoration(
                                color: AppColors.primaryColor.withValues(
                                  alpha: 0.08,
                                ),
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.fullBorderRadius,
                                ),
                              ),
                              child: Text(
                                name,
                                style: TextStyle(
                                  fontSize: AppTypography.sm,
                                  color: fgPrimary.withValues(alpha: 0.9),
                                ),
                              ),
                            ),
                          )
                          .toList(growable: false),
                    ),
                  ),
                ),
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
                                    processState:
                                        _isAssistantConversation &&
                                            _assistantResponding &&
                                            index == _messages.length - 1 &&
                                            isAssistantMessage
                                        ? _currentProcessState
                                        : null,
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
                                              context.push('/profile');
                                            } else if (senderId.isNotEmpty) {
                                              context.push('/user/$senderId');
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
              Container(
                padding: EdgeInsets.symmetric(
                  horizontal:
                      AppSpacing.semantic[DesignSemanticConstants
                          .container]?[DesignSemanticConstants.sm] ??
                      AppSpacing.containerSm,
                  vertical: AppSpacing.sm,
                ),
                decoration: BoxDecoration(
                  color: isDark ? bgColor : AppColors.chatToolbarBackground,
                  border: Border(
                    top: BorderSide(color: borderColor.withValues(alpha: 0.3)),
                  ),
                ),
                child: SafeArea(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CustomizableChatInputBar(
                        controller: _inputController,
                        focusNode: _inputFocusNode,
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
                            ? null
                            : _buildQuliaoLeftButton,
                        rightBuilder: _isAssistantConversation
                            ? null
                            : _buildQuliaoRightButtons,
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
