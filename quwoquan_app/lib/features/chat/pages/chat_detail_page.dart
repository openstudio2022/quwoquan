// ignore_for_file: unused_import, unnecessary_underscores

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:quwoquan_app/components/assistant_avatar.dart';
import 'package:quwoquan_app/components/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_engine_provider.dart';
import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/capability_catalog.dart';
import 'package:quwoquan_app/features/assistant/config/assistant_prompt_config.dart';
import 'package:quwoquan_app/features/assistant/context/assistant_open_context.dart';
import 'package:quwoquan_app/features/assistant/pages/assistant_dev_replay_page.dart';
import 'package:quwoquan_app/features/assistant/widgets/assistant_half_sheet.dart';

/// 聊天气泡最大宽度（语义尺寸，多屏适配由布局约束决定）
const double _chatBubbleMaxWidth = 280.0;
const double _chatBubbleWidthFactor = 0.84;

/// 聊天气泡内图片展示尺寸（语义尺寸）
const double _chatBubbleImageSize = 200.0;

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
  bool _isSelectionMode = false;
  final Set<String> _selectedIds = {};
  Map<String, dynamic>? _actionMenuMessage;
  Offset? _actionMenuPosition;
  bool _voiceInputMode = false;
  bool _showEmojiPanel = false;
  bool _showMorePanel = false;
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
  Timer? _assistantProgressTimer;
  int _assistantThinkingDots = 1;
  int _assistantSearchingCount = 0;
  int _assistantReferenceCount = 0;

  @override
  void initState() {
    super.initState();
    _messages = List.from(
      ref
          .read(appContentRepositoryProvider)
          .chatMessagesFor(widget.conversationId),
    );
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
    }
  }

  void _onInputChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _assistantProgressTimer?.cancel();
    _inputController.removeListener(_onInputChanged);
    _inputController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  void _startAssistantProgress() {
    _assistantProgressTimer?.cancel();
    _assistantThinkingDots = 1;
    _assistantSearchingCount = 0;
    _assistantReferenceCount = 0;
    _assistantProgressTimer = Timer.periodic(const Duration(milliseconds: 420), (
      timer,
    ) {
      if (!mounted || !_assistantResponding) {
        timer.cancel();
        return;
      }
      setState(() {
        _assistantThinkingDots = _assistantThinkingDots >= 3
            ? 1
            : _assistantThinkingDots + 1;
      });
    });
  }

  void _stopAssistantProgress() {
    _assistantProgressTimer?.cancel();
    _assistantProgressTimer = null;
  }

  void _consumeAssistantTraceEvent(AssistantTraceEvent event) {
    if (!mounted || !_assistantResponding) return;
    final type = event.type;
    final data = event.data ?? const <String, dynamic>{};
    var searchingCount = _assistantSearchingCount;
    var referenceCount = _assistantReferenceCount;
    if (type == AssistantTraceEventType.toolStart &&
        _isSearchLikeTrace(event, data)) {
      searchingCount += 1;
    }
    if (type == AssistantTraceEventType.toolResult ||
        type == AssistantTraceEventType.assistantDelta) {
      referenceCount = math.max(
        referenceCount,
        _extractReferenceCountFromTraceData(data),
      );
    }
    if (searchingCount == _assistantSearchingCount &&
        referenceCount == _assistantReferenceCount) {
      return;
    }
    setState(() {
      _assistantSearchingCount = searchingCount;
      _assistantReferenceCount = referenceCount;
    });
  }

  bool _isSearchLikeTrace(
    AssistantTraceEvent event,
    Map<String, dynamic> data,
  ) {
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

  int _extractReferenceCountFromTraceData(Map<String, dynamic> data) {
    final references = data['references'];
    if (references is List) return references.length;
    final items = data['items'];
    if (items is List) return items.length;
    final countRaw = data['count'] ?? data['referenceCount'] ?? data['resultCount'];
    if (countRaw is int) return countRaw;
    if (countRaw is String) return int.tryParse(countRaw.trim()) ?? 0;
    return 0;
  }

  String get _conversationTitle {
    if (widget.conversationId == AppConceptConstants.assistantConversationId) {
      return ref
                  .read(appContentRepositoryProvider)
                  .chatAssistantConversation['title']
              as String? ??
          AppConceptConstants.assistantLabel;
    }
    for (final c
        in ref.read(appContentRepositoryProvider).chatMockConversations) {
      if (c['id'] == widget.conversationId) {
        return c['title'] as String? ?? widget.conversationId;
      }
    }
    return widget.conversationId;
  }

  bool get _isAssistantConversation =>
      widget.conversationId == AppConceptConstants.assistantConversationId;

  Widget _buildInputField(bool isDark, Color fgPrimary) {
    if (_voiceInputMode) {
      return GestureDetector(
        onTap: () => setState(() => _voiceInputMode = false),
        child: Container(
          height: AppSpacing.buttonSize,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.white,
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius * 2),
          ),
          child: Text(
            '按住 说话',
            style: TextStyle(
              fontSize:
                  Theme.of(context).textTheme.bodyLarge?.fontSize ??
                  AppSpacing.md,
              color: fgPrimary.withValues(alpha: 0.6),
            ),
          ),
        ),
      );
    }
    return TextField(
      controller: _inputController,
      focusNode: _inputFocusNode,
      decoration: InputDecoration(
        hintText: '',
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius * 2),
          borderSide: BorderSide.none,
        ),
        contentPadding: EdgeInsets.symmetric(
          horizontal:
              AppSpacing.semantic[DesignSemanticConstants
                  .container]?[DesignSemanticConstants.md] ??
              AppSpacing.containerMd,
          vertical: AppSpacing.intraGroupLg,
        ),
      ),
      maxLines: 4,
      minLines: 1,
      onSubmitted: (_) => _sendMessage(),
    );
  }

  Widget _buildAddOrSendButton(Color fgPrimary) {
    if (_inputController.text.trim().isEmpty) {
      return SizedBox(
        height: AppSpacing.buttonSize,
        width: AppSpacing.buttonSize,
        child: IconTheme(
          data: IconThemeData(
            size: AppSpacing.iconMedium + 2,
            color: fgPrimary.withValues(alpha: 0.5),
            fill: 0,
            weight: 100,
          ),
          child: IconButton(
            style: IconButton.styleFrom(
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            icon: const Icon(Icons.add_circle_outline),
            onPressed: () {
              setState(() {
                _showMorePanel = !_showMorePanel;
                if (_showMorePanel) {
                  _showEmojiPanel = false;
                }
                _inputFocusNode.unfocus();
              });
            },
          ),
        ),
      );
    }
    return Material(
      color: AppColors.primaryColor,
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      child: InkWell(
        onTap: _sendMessage,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal:
                AppSpacing.semantic[DesignSemanticConstants
                    .container]?[DesignSemanticConstants.md] ??
                AppSpacing.containerMd,
            vertical: AppSpacing.containerSm,
          ),
          child: Text(
            UITextConstants.send,
            style: TextStyle(
              fontSize:
                  Theme.of(context).textTheme.bodyLarge?.fontSize ??
                  AppSpacing.md,
              fontWeight: FontWeight.w500,
              color: Colors.white,
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _sendMessage() async {
    _inputFocusNode.unfocus();
    await Future<void>.delayed(const Duration(milliseconds: 150));
    final text = _inputController.text.trim();
    if (text.isEmpty) return;
    final now = DateTime.now();
    final timeStr = '${now.hour}:${now.minute.toString().padLeft(2, '0')}';
    final userMessageId = 'msg_${DateTime.now().millisecondsSinceEpoch}';
    setState(() {
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
        'isRead': true,
        'isSelf': true,
      });
    });
    _inputController.clear();
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
      setState(() => _assistantResponding = true);
      _startAssistantProgress();
      try {
        final deviceProfile = _assistantDeviceProfileByWidth(
          _lastViewportWidth,
        );
        await ref.read(assistantRuntimeProvider).ensureRemoteConfigLoaded();
        final runStartedAt = DateTime.now();
        final assistantMessages = _messages
            .where((m) => (m['type'] as String? ?? 'text') == 'text')
            .map(
              (m) => AssistantRunMessage(
                role: (m['isSelf'] == true) ? 'user' : 'assistant',
                content: (m['content'] as String?) ?? '',
              ),
            )
            .toList(growable: false);
        final contextScope = _buildAssistantContextScope();
        final domainId = await ref.read(assistantGatewayProvider).classifyDomain(
          text,
          contextScope,
        );
        contextScope['domainId'] = domainId;
        final request = AssistantRunRequest(
          messages: assistantMessages,
          sessionId: widget.conversationId,
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
        await for (final streamEvent in ref
            .read(capabilityGatewayProvider)
            .runStream(request: request, mode: routeMode)) {
          if (streamEvent.type == AssistantRunStreamEventType.trace &&
              streamEvent.trace != null) {
            _consumeAssistantTraceEvent(streamEvent.trace!);
            continue;
          }
          if (streamEvent.type == AssistantRunStreamEventType.failed) {
            throw StateError(
              streamEvent.errorMessage ?? UITextConstants.assistantUnavailable,
            );
          }
          if (streamEvent.type == AssistantRunStreamEventType.completed &&
              streamEvent.response != null) {
            response = streamEvent.response;
          }
        }
        if (response == null) {
          throw StateError(UITextConstants.assistantUnavailable);
        }
        final runResponse = response;
        final displayText = _resolveAssistantDisplayText(runResponse);
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
        final uiTimeline =
            (runResponse.structuredResponse['uiTimeline'] as List?)
                ?.whereType<Map>()
                .map((item) => item.cast<String, dynamic>())
                .toList(growable: false) ??
            const <Map<String, dynamic>>[];
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
        setState(() {
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
            'uiTimeline': uiTimeline,
            'uiReferences': uiReferences,
            'uiActions': uiActions,
            'uiAnswer': uiAnswer,
          });
          _assistantResponding = false;
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
              sessionId: widget.conversationId,
              pageType: (contextScope['pageType'] as String?) ?? 'chat',
              queryText: text,
              answerText: runResponse.finalText,
              userTags: userTags,
              durationMs: elapsedMs,
            );
      } catch (e, st) {
        if (kDebugMode) {
          debugPrint('Assistant run failed: $e');
          debugPrint('Stack trace: $st');
        }
        if (!mounted) return;
        setState(() {
          _assistantResponding = false;
          _messages.add({
            'id': 'assistant_err_${DateTime.now().millisecondsSinceEpoch}',
            'conversationId': widget.conversationId,
            'type': 'text',
            'content': UITextConstants.assistantUnavailable,
            'senderId': AppConceptConstants.assistantSenderId,
            'senderName': AppConceptConstants.assistantLabel,
            'senderAvatar': '',
            'timestamp': timeStr,
            'isRead': true,
            'isSelf': false,
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
          'allowedReferenceHosts': AppConceptConstants.assistantReferenceHostWhitelist,
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
      'sessionId': widget.conversationId,
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
        'currentStateId': (latestDialogueState['suggestedNextStateId'] as String)
            .trim(),
      'privacyProfile': 'default',
      'privacyPolicy': privacyPolicy,
    };
  }

  Map<String, dynamic> _latestAssistantDialogueState() {
    for (var i = _messages.length - 1; i >= 0; i--) {
      final message = _messages[i];
      if ((message['senderId'] as String?) != AppConceptConstants.assistantSenderId) {
        continue;
      }
      final state = (message['dialogueState'] as Map?)?.cast<String, dynamic>();
      if (state != null && state.isNotEmpty) return state;
    }
    return const <String, dynamic>{};
  }

  String _resolveAssistantDisplayText(AssistantRunResponse response) {
    final structured = response.structuredResponse;
    final uiAnswer =
        (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final markdown = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
    if (markdown.isNotEmpty) return markdown;
    final answerPayload =
        (structured['answerPayload'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final userFacingMarkdown =
        (answerPayload['userFacingMarkdown'] as String?)?.trim() ?? '';
    if (userFacingMarkdown.isNotEmpty) return userFacingMarkdown;
    final parsed = _extractTextFromPotentialJson(response.finalText);
    if (parsed.isNotEmpty) return parsed;
    return UITextConstants.assistantUnavailable;
  }

  String _extractTextFromPotentialJson(String raw) {
    final text = raw.trim();
    if (text.isEmpty) return '';
    if (!text.startsWith('{') && !text.startsWith('```')) return text;
    final cleaned = text
        .replaceAll(RegExp(r'^```json\s*'), '')
        .replaceAll(RegExp(r'^```\s*'), '')
        .replaceAll(RegExp(r'```$'), '')
        .trim();
    try {
      final decoded = jsonDecode(cleaned);
      if (decoded is Map<String, dynamic>) {
        final result = (decoded['result'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final markdown = (decoded['userFacingMarkdown'] as String?)?.trim() ?? '';
        if (markdown.isNotEmpty) return markdown;
        final resultText = (result['text'] as String?)?.trim() ?? '';
        if (resultText.isNotEmpty) return resultText;
      }
    } catch (_) {}
    return '';
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
    final structured =
        response.structuredResponse.isEmpty ? const <String, dynamic>{} : response.structuredResponse;
    final record = <String, dynamic>{
      'messageId': messageId,
      'runId': response.runId ?? '',
      'traceId': response.traceId ?? '',
      'query': query,
      'answer': response.finalText,
      'createdAt': DateTime.now().toIso8601String(),
      'uiTimeline':
          (structured['uiTimeline'] as List?)?.whereType<Map>().toList(growable: false) ??
              const <Map>[],
      'uiReferences':
          (structured['uiReferences'] as List?)?.whereType<Map>().toList(growable: false) ??
              const <Map>[],
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
          sessionId: widget.conversationId,
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
    await ref.read(assistentLearningServiceProvider).recordInteraction(
      runId: (message['runId'] as String?)?.trim().isNotEmpty == true
          ? (message['runId'] as String).trim()
          : 'run_${DateTime.now().millisecondsSinceEpoch}',
      traceId: (message['traceId'] as String?)?.trim().isNotEmpty == true
          ? (message['traceId'] as String).trim()
          : 'trace_${DateTime.now().millisecondsSinceEpoch}',
      userId: 'current_user',
      sessionId: widget.conversationId,
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
    final rawHosts = (privacyPolicy['allowedReferenceHosts'] as List?)
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

    return Stack(
      children: [
        Scaffold(
          backgroundColor: bgColor,
          appBar: AppBar(
            backgroundColor: bgColor,
            elevation: 0,
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
                          (item) => _selectedIds.contains((item['id'] as String?) ?? ''),
                        )
                        .toList(growable: false);
                    await _shareMessages(selectedMessages);
                    _cancelSelection();
                  },
                  child: Text(UITextConstants.messageActionForward),
                )
              else ...[
                if (_isAssistantConversation && kDebugMode)
                  IconButton(
                    icon: const Icon(Icons.playlist_play_outlined),
                    tooltip: UITextConstants.assistantDevReplayOpen,
                    onPressed: _openAssistantDevReplayPage,
                  ),
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
                child: Container(
                  color: chatListBg,
                  child: ListView.builder(
                    controller: _scrollController,
                    padding: EdgeInsets.symmetric(
                      horizontal:
                          AppSpacing.semantic[DesignSemanticConstants
                              .container]?[DesignSemanticConstants.sm] ??
                          AppSpacing.containerSm,
                      vertical: AppSpacing.md,
                    ),
                    itemCount: _messages.length,
                    itemBuilder: (context, index) {
                      final msg = _messages[index];
                      final prevTime = index > 0
                          ? _messages[index - 1]['timestamp'] as String?
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
                                    AppSpacing.semantic[DesignSemanticConstants
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
                          _ChatBubble(
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
                            onLongPressStart: (details) => _onLongPressMessage(
                              msg,
                              details.globalPosition,
                            ),
                            onTap: _isSelectionMode
                                ? () => _toggleSelect(msg['id'] as String)
                                : null,
                            showFeedbackActions:
                                isAssistantMessage &&
                                !_isSelectionMode &&
                                (msg['type'] as String? ?? 'text') == 'text',
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
                                ? () => _showAssistantNegativeFeedbackSheet(msg)
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
                                    ScaffoldMessenger.of(this.context).showSnackBar(
                                      SnackBar(
                                        content: Text(
                                          UITextConstants.copiedToClipboard,
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
                                    ScaffoldMessenger.of(this.context).showSnackBar(
                                      SnackBar(
                                        content: Text(
                                          UITextConstants.assistantBookmarked,
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
                                ? () => _switchAssistantModelAndRegenerate(msg)
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
                                      experienceLevel: service.getExperience(
                                        target,
                                      ),
                                    );
                                    AssistantHalfSheet.show(context, ctx);
                                  }
                                : () {
                                    final senderId =
                                        msg['senderId'] as String? ?? '';
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
                  ),
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
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          SizedBox(
                            height: AppSpacing.buttonSize,
                            width: AppSpacing.buttonSize,
                            child: IconButton(
                              style: IconButton.styleFrom(
                                padding: EdgeInsets.zero,
                                minimumSize: Size.zero,
                                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                iconSize: AppSpacing.iconMedium,
                              ),
                              icon: Icon(
                                _voiceInputMode
                                    ? Icons.keyboard_rounded
                                    : Icons.mic_none,
                                color: fgPrimary.withValues(alpha: 0.5),
                              ),
                              onPressed: () {
                                setState(() {
                                  _voiceInputMode = !_voiceInputMode;
                                  if (_voiceInputMode) {
                                    _showEmojiPanel = false;
                                    _showMorePanel = false;
                                    _inputFocusNode.unfocus();
                                  }
                                });
                              },
                            ),
                          ),
                          Expanded(child: _buildInputField(isDark, fgPrimary)),
                          SizedBox(
                            height: AppSpacing.buttonSize,
                            width: AppSpacing.buttonSize,
                            child: IconButton(
                              style: IconButton.styleFrom(
                                padding: EdgeInsets.zero,
                                minimumSize: Size.zero,
                                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                iconSize: AppSpacing.iconMedium,
                              ),
                              icon: Icon(
                                Icons.mood_outlined,
                                color: fgPrimary.withValues(alpha: 0.5),
                              ),
                              onPressed: () {
                                setState(() {
                                  _showEmojiPanel = !_showEmojiPanel;
                                  if (_showEmojiPanel) {
                                    _showMorePanel = false;
                                    _inputFocusNode.unfocus();
                                  }
                                });
                              },
                            ),
                          ),
                          _buildAddOrSendButton(fgPrimary),
                        ],
                      ),
                      if (_isAssistantConversation && _assistantResponding)
                        Padding(
                          padding: EdgeInsets.only(top: AppSpacing.xs),
                          child: Row(
                            children: [
                              Icon(
                                Icons.bubble_chart_outlined,
                                size: AppSpacing.iconSmall,
                                color: AppColors.primaryColor,
                              ),
                              SizedBox(width: AppSpacing.xs),
                              Text(
                                '${UITextConstants.assistantRunningHint}${'.' * _assistantThinkingDots}',
                                style: TextStyle(
                                  fontSize: AppTypography.sm,
                                  color: fgPrimary.withValues(alpha: 0.7),
                                ),
                              ),
                              SizedBox(width: AppSpacing.xs),
                              Text(
                                UITextConstants.assistantSearchingReferenceCount
                                    .replaceFirst(
                                  '%s',
                                  math.max(
                                    _assistantSearchingCount,
                                    _assistantReferenceCount,
                                  )
                                      .clamp(0, 20)
                                      .toString(),
                                ),
                                style: TextStyle(
                                  fontSize: AppTypography.sm,
                                  color: fgPrimary.withValues(alpha: 0.6),
                                ),
                              ),
                            ],
                          ),
                        ),
                      if (_showEmojiPanel)
                        UnifiedEmojiPicker(
                          showCloseButton: true,
                          onClose: () =>
                              setState(() => _showEmojiPanel = false),
                          onEmojiSelected: (char) =>
                              setState(() => _inputController.text += char),
                        ),
                      if (_showMorePanel)
                        _ChatMorePanel(
                          onClose: () => setState(() => _showMorePanel = false),
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

/// 带侧边自然尾巴与 3D 阴影的气泡（原型图一：尾巴在气泡侧边略靠上、上下斜线不同）
class _BubbleWithTail extends StatelessWidget {
  const _BubbleWithTail({
    required this.isRight,
    required this.color,
    required this.child,
  });

  final bool isRight;
  final Color color;
  final Widget child;

  static const double _radius = 12;

  /// 尾巴伸出长度（指向头像方向）
  static const double _tailExtent = 8;

  /// 尾巴在气泡侧边的垂直范围：略靠上，约 35%～65% 高度
  static const double _tailTopRatio = 0.35;
  static const double _tailBottomRatio = 0.65;

  static Path _path(double w, double h, bool isRight) {
    final r = _radius;
    final path = Path();
    final ty0 = h * _tailTopRatio;
    final ty1 = h * 0.5;
    final ty2 = h * _tailBottomRatio;
    if (isRight) {
      path.moveTo(r, 0);
      path.lineTo(w - r, 0);
      path.arcTo(
        Rect.fromLTWH(w - r, 0, r, r),
        -math.pi / 2,
        math.pi / 2,
        false,
      );
      path.lineTo(w, ty0 - 1);
      path.lineTo(w + _tailExtent, ty1);
      path.lineTo(w, ty2 + 1);
      path.lineTo(w, h - r);
      path.arcTo(Rect.fromLTWH(w - r, h - r, r, r), 0, math.pi / 2, false);
      path.lineTo(r, h);
      path.arcTo(
        Rect.fromLTWH(0, h - r, r, r),
        math.pi / 2,
        math.pi / 2,
        false,
      );
      path.lineTo(0, r);
      path.arcTo(Rect.fromLTWH(0, 0, r, r), math.pi, math.pi / 2, false);
    } else {
      path.moveTo(r, 0);
      path.lineTo(w - r, 0);
      path.arcTo(
        Rect.fromLTWH(w - r, 0, r, r),
        -math.pi / 2,
        math.pi / 2,
        false,
      );
      path.lineTo(w, h - r);
      path.arcTo(Rect.fromLTWH(w - r, h - r, r, r), 0, math.pi / 2, false);
      path.lineTo(r, h);
      path.arcTo(
        Rect.fromLTWH(0, h - r, r, r),
        math.pi / 2,
        math.pi / 2,
        false,
      );
      path.lineTo(0, ty2 + 1);
      path.lineTo(-_tailExtent, ty1);
      path.lineTo(0, ty0 - 1);
      path.lineTo(0, r);
      path.arcTo(Rect.fromLTWH(0, 0, r, r), math.pi, math.pi / 2, false);
    }
    path.close();
    return path;
  }

  @override
  Widget build(BuildContext context) {
    final content = ClipRRect(
      borderRadius: BorderRadius.circular(_radius),
      child: child,
    );
    final sizedForTail = Padding(
      padding: EdgeInsets.only(
        left: isRight ? 0 : _tailExtent,
        right: isRight ? _tailExtent : 0,
      ),
      child: content,
    );
    return Stack(
      clipBehavior: Clip.none,
      alignment: Alignment.center,
      children: [
        // 用包含尾巴预留宽度的占位，避免真实内容被挤窄导致末字被裁切
        Opacity(opacity: 0, child: sizedForTail),
        Positioned.fill(
          child: CustomPaint(
            painter: _BubbleTailPainter(
              color: color,
              isRight: isRight,
              tailExtent: _tailExtent,
            ),
          ),
        ),
        Positioned(
          left: isRight ? 0 : _tailExtent,
          top: 0,
          right: isRight ? _tailExtent : 0,
          bottom: 0,
          child: content,
        ),
      ],
    );
  }
}

class _BubbleTailPainter extends CustomPainter {
  _BubbleTailPainter({
    required this.color,
    required this.isRight,
    required this.tailExtent,
  });

  final Color color;
  final bool isRight;
  final double tailExtent;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width - tailExtent;
    final h = size.height;
    final path = _BubbleWithTail._path(w, h, isRight);
    if (!isRight) canvas.translate(tailExtent, 0);
    final shadowPaint = Paint()
      ..color = Colors.black.withValues(alpha: 0.06)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
    canvas.save();
    canvas.translate(0, 2);
    canvas.drawPath(path, shadowPaint);
    canvas.restore();
    canvas.drawPath(path, Paint()..color = color);
    if (!isRight) canvas.translate(-tailExtent, 0);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _ChatBubble extends StatelessWidget {
  const _ChatBubble({
    required this.message,
    required this.isRight,
    required this.bubbleColor,
    required this.textColor,
    required this.isSelectionMode,
    required this.isSelected,
    required this.onLongPressStart,
    this.onTap,
    this.onAvatarTap,
    this.showAssistantAvatar = false,
    this.showFeedbackActions = false,
    this.feedbackStatus = '',
    this.onFeedbackHelpful,
    this.onFeedbackUnhelpful,
    this.onFeedbackCorrect,
    this.onCopyAnswer,
    this.onShareAnswer,
    this.onFavoriteAnswer,
    this.onRegenerateAnswer,
    this.onBriefAnswer,
    this.onDetailedAnswer,
    this.onSwitchModelAnswer,
    this.onReferenceTap,
  });

  final Map<String, dynamic> message;
  final bool isRight;
  final Color bubbleColor;
  final Color textColor;
  final bool isSelectionMode;
  final bool isSelected;
  final void Function(LongPressStartDetails details) onLongPressStart;
  final VoidCallback? onTap;
  final VoidCallback? onAvatarTap;
  final bool showAssistantAvatar;
  final bool showFeedbackActions;
  final String feedbackStatus;
  final VoidCallback? onFeedbackHelpful;
  final VoidCallback? onFeedbackUnhelpful;
  final VoidCallback? onFeedbackCorrect;
  final VoidCallback? onCopyAnswer;
  final VoidCallback? onShareAnswer;
  final VoidCallback? onFavoriteAnswer;
  final VoidCallback? onRegenerateAnswer;
  final VoidCallback? onBriefAnswer;
  final VoidCallback? onDetailedAnswer;
  final VoidCallback? onSwitchModelAnswer;
  final void Function(Map<String, dynamic> reference)? onReferenceTap;

  @override
  Widget build(BuildContext context) {
    final viewportWidth = MediaQuery.of(context).size.width;
    final bubbleMaxWidth = math.max(
      _chatBubbleMaxWidth,
      viewportWidth * _chatBubbleWidthFactor,
    );
    final type = message['type'] as String? ?? 'text';
    final content = message['content'] as String? ?? '';
    final senderName = message['senderName'] as String? ?? '';
    final avatar = message['senderAvatar'] as String?;
    final isRead = message['isRead'] == true;

    Widget contentWidget;
    if (type == 'task_card') {
      final tasks = message['tasks'] as List<dynamic>? ?? [];
      contentWidget = Container(
        constraints: BoxConstraints(maxWidth: bubbleMaxWidth),
        decoration: BoxDecoration(
          color: bubbleColor.withValues(alpha: 0.2),
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(color: bubbleColor.withValues(alpha: 0.3)),
        ),
        padding: EdgeInsets.all(AppSpacing.sm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '今日待办提醒',
              style: TextStyle(
                fontSize:
                    Theme.of(context).textTheme.bodySmall?.fontSize ??
                    AppSpacing.containerSm,
                fontWeight: FontWeight.w600,
                color: textColor,
              ),
            ),
            SizedBox(height: AppSpacing.sm),
            ...tasks.map<Widget>((t) {
              final map = t is Map
                  ? t as Map<String, dynamic>
                  : <String, dynamic>{};
              final title = map['title'] as String? ?? '';
              final time = map['time'] as String? ?? '';
              final status = map['status'] as String? ?? 'pending';
              return Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.xs),
                child: Row(
                  children: [
                    Icon(
                      status == 'completed'
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      size: AppSpacing.iconSmall,
                      color: textColor,
                    ),
                    SizedBox(width: AppSpacing.intraGroupSm),
                    Expanded(
                      child: Text(
                        '$title · $time',
                        style: TextStyle(
                          fontSize:
                              Theme.of(context).textTheme.bodySmall?.fontSize ??
                              AppSpacing.containerSm,
                          color: textColor,
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      );
    } else if (type == 'image') {
      final imageUrl =
          message['imageUrl'] as String? ??
          message['thumbnailUrl'] as String? ??
          '';
      contentWidget = ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: Image.network(
          imageUrl,
          width: _chatBubbleImageSize,
          height: _chatBubbleImageSize,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => Container(
            width: _chatBubbleImageSize,
            height: _chatBubbleImageSize,
            color: bubbleColor,
            child: Icon(Icons.broken_image, color: textColor),
          ),
        ),
      );
    } else {
      contentWidget = _BubbleWithTail(
        isRight: isRight,
        color: bubbleColor,
        child: Container(
          constraints: BoxConstraints(maxWidth: bubbleMaxWidth),
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerSm,
            AppSpacing.intraGroupLg,
            AppSpacing.containerSm + 2,
            AppSpacing.intraGroupLg,
          ),
          child: SelectableText(
            content,
            style: TextStyle(
              fontSize:
                  Theme.of(context).textTheme.bodyLarge?.fontSize ??
                  AppSpacing.md,
              color: textColor,
            ),
          ),
        ),
      );
    }

    final timeline = (message['uiTimeline'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final references = (message['uiReferences'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final followupPrompt = (((message['uiAnswer'] as Map?)?['followupPrompt'])
                as String?)
            ?.trim() ??
        '';
    final actionHints = ((((message['uiAnswer'] as Map?)?['actionHints'])
                as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false)) ??
        const <String>[];
    Widget? avatarWidget;
    final chatAvatarRadius = AppSpacing.avatarUserSm / 2;
    if (showAssistantAvatar) {
      avatarWidget = AssistantAvatar(
        radius: chatAvatarRadius,
        onTap: onAvatarTap,
      );
    } else if (avatar != null && avatar.isNotEmpty) {
      avatarWidget = GestureDetector(
        onTap: onAvatarTap,
        child: CircleAvatar(
          radius: chatAvatarRadius,
          backgroundImage: NetworkImage(avatar),
        ),
      );
    }

    return GestureDetector(
      onTap: onTap,
      onLongPressStart: onLongPressStart,
      child: Padding(
        padding: EdgeInsets.only(bottom: AppSpacing.sm),
        child: Row(
          mainAxisAlignment: isRight
              ? MainAxisAlignment.end
              : MainAxisAlignment.start,
          crossAxisAlignment: isRight
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          children: [
            if (!isRight && avatarWidget != null) avatarWidget,
            if (!isRight && avatarWidget != null) SizedBox(width: AppSpacing.sm),
            Flexible(
              child: Column(
                crossAxisAlignment: isRight
                    ? CrossAxisAlignment.end
                    : CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (senderName.isNotEmpty && !isRight)
                    Padding(
                      padding: EdgeInsets.only(
                        left: AppSpacing.xs,
                        right: AppSpacing.xs,
                        bottom: AppSpacing.xs,
                      ),
                      child: Text(
                        senderName,
                        style: TextStyle(
                          fontSize:
                              Theme.of(context).textTheme.bodySmall?.fontSize ??
                              AppSpacing.containerSm,
                          color: textColor.withValues(alpha: 0.8),
                        ),
                      ),
                    ),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      if (isSelectionMode)
                        Padding(
                          padding: EdgeInsets.only(
                            right: AppSpacing.intraGroupSm,
                          ),
                          child: Icon(
                            isSelected
                                ? Icons.check_circle
                                : Icons.radio_button_unchecked,
                            size: AppSpacing.iconMedium,
                            color: AppColors.primaryColor,
                          ),
                        ),
                      if (isRight && (type == 'text' || type == 'image'))
                        Padding(
                          padding: EdgeInsets.only(right: AppSpacing.xs),
                          child: Icon(
                            isRead ? Icons.done_all : Icons.done,
                            size: AppSpacing.iconSmall,
                            color: textColor.withValues(alpha: 0.8),
                          ),
                        ),
                      Expanded(
                        child: contentWidget,
                      ),
                    ],
                  ),
                  if (timeline.isNotEmpty) ...[
                    SizedBox(height: AppSpacing.xs),
                    _AssistantTimelineCard(
                      timeline: timeline,
                      references: references,
                      onReferenceTap: onReferenceTap,
                    ),
                  ],
                  if (followupPrompt.isNotEmpty || actionHints.isNotEmpty) ...[
                    SizedBox(height: AppSpacing.xs),
                    _AssistantFollowupCard(
                      followupPrompt: followupPrompt,
                      actionHints: actionHints,
                    ),
                  ],
                  if (showFeedbackActions) ...[
                    SizedBox(height: AppSpacing.xs),
                    Wrap(
                      spacing: AppSpacing.xs,
                      runSpacing: AppSpacing.xs,
                      children: [
                        TextButton(
                          onPressed: onFeedbackHelpful,
                          child: Text(UITextConstants.assistantFeedbackHelpful),
                        ),
                        TextButton(
                          onPressed: onFeedbackUnhelpful,
                          child: Text(
                            UITextConstants.assistantFeedbackUnhelpful,
                          ),
                        ),
                        TextButton(
                          onPressed: onFeedbackCorrect,
                          child: Text(UITextConstants.assistantFeedbackCorrect),
                        ),
                        if (feedbackStatus.isNotEmpty)
                          Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.xs,
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
                              feedbackStatus,
                              style: TextStyle(
                                fontSize: AppTypography.sm,
                                color: AppColors.primaryColor,
                              ),
                            ),
                          ),
                        IconButton(
                          onPressed: onCopyAnswer,
                          icon: const Icon(Icons.copy_outlined),
                          tooltip: UITextConstants.copyLink,
                          iconSize: AppSpacing.iconSmall,
                        ),
                        IconButton(
                          onPressed: onFavoriteAnswer,
                          icon: const Icon(Icons.bookmark_border),
                          tooltip: UITextConstants.bookmarks,
                          iconSize: AppSpacing.iconSmall,
                        ),
                        IconButton(
                          onPressed: onShareAnswer,
                          icon: const Icon(Icons.share_outlined),
                          tooltip: UITextConstants.share,
                          iconSize: AppSpacing.iconSmall,
                        ),
                        PopupMenuButton<String>(
                          onSelected: (value) {
                            if (value == 'regenerate') {
                              onRegenerateAnswer?.call();
                            } else if (value == 'brief') {
                              onBriefAnswer?.call();
                            } else if (value == 'detailed') {
                              onDetailedAnswer?.call();
                            } else if (value == 'switch_model') {
                              onSwitchModelAnswer?.call();
                            }
                          },
                          itemBuilder: (context) => const <PopupMenuEntry<String>>[
                            PopupMenuItem<String>(
                              value: 'regenerate',
                              child: Text(UITextConstants.assistantActionRegenerate),
                            ),
                            PopupMenuItem<String>(
                              value: 'brief',
                              child: Text(UITextConstants.assistantActionBrief),
                            ),
                            PopupMenuItem<String>(
                              value: 'detailed',
                              child: Text(UITextConstants.assistantActionDetailed),
                            ),
                            PopupMenuItem<String>(
                              value: 'switch_model',
                              child: Text(UITextConstants.assistantActionSwitchModel),
                            ),
                          ],
                          child: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.xs,
                              vertical: AppSpacing.xs,
                            ),
                            child: Icon(
                              Icons.sync,
                              size: AppSpacing.iconSmall,
                              color: AppColors.primaryColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
            if (isRight && avatarWidget != null) SizedBox(width: AppSpacing.sm),
            if (isRight && avatarWidget != null) avatarWidget,
          ],
        ),
      ),
    );
  }
}

class _AssistantTimelineCard extends StatefulWidget {
  const _AssistantTimelineCard({
    required this.timeline,
    required this.references,
    this.onReferenceTap,
  });

  final List<Map<String, dynamic>> timeline;
  final List<Map<String, dynamic>> references;
  final void Function(Map<String, dynamic> reference)? onReferenceTap;

  @override
  State<_AssistantTimelineCard> createState() => _AssistantTimelineCardState();
}

class _AssistantTimelineCardState extends State<_AssistantTimelineCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final title = widget.references.isEmpty
        ? UITextConstants.assistantTimelineSearchProcess
        : UITextConstants.assistantTimelineReferenceCount.replaceFirst(
            '%s',
            widget.references.length.toString(),
          );
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primaryColor,
                    ),
                  ),
                ),
                Icon(
                  _expanded ? Icons.expand_less : Icons.expand_more,
                  size: AppSpacing.iconSmall,
                  color: AppColors.primaryColor,
                ),
              ],
            ),
          ),
          if (_expanded) ...[
            SizedBox(height: AppSpacing.xs),
            ...widget.timeline.map(
              (item) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.xs),
                child: Text(
                  _timelineText(item),
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: AppColors.primaryColor.withValues(alpha: 0.85),
                  ),
                ),
              ),
            ),
            if (widget.references.isNotEmpty) ...[
              SizedBox(height: AppSpacing.xs),
              ...widget.references.map(
                (ref) => InkWell(
                  onTap: () => widget.onReferenceTap?.call(ref),
                  child: Padding(
                    padding: EdgeInsets.only(bottom: AppSpacing.xs),
                    child: Text(
                      '• ${(ref['title'] ?? '').toString()}',
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }

  String _timelineText(Map<String, dynamic> item) {
    final event = (item['event'] as String?)?.trim() ?? '';
    final label = switch (event) {
      'thinking' => UITextConstants.assistantTimelineThinking,
      'keyword_search' => UITextConstants.assistantTimelineKeywordSearch,
      'reference_increment' => UITextConstants.assistantTimelineReferenceIncrement,
      'reference_ready' => UITextConstants.assistantTimelineReady,
      _ => '',
    };
    final count = (item['count'] as num?)?.toInt() ?? 0;
    final keywords = (item['keywords'] as List?)
            ?.whereType<String>()
            .where((value) => value.trim().isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    if (keywords.isNotEmpty) return '$label：${keywords.join('、')}';
    if (count > 0) return '$label：$count';
    return label;
  }
}

class _AssistantFollowupCard extends StatelessWidget {
  const _AssistantFollowupCard({
    required this.followupPrompt,
    required this.actionHints,
  });

  final String followupPrompt;
  final List<String> actionHints;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (followupPrompt.isNotEmpty)
            Text(
              followupPrompt,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColors.primaryColor,
              ),
            ),
          if (actionHints.isNotEmpty) ...[
            if (followupPrompt.isNotEmpty) SizedBox(height: AppSpacing.xs),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: actionHints
                  .map(
                    (hint) => Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.containerSm,
                        vertical: AppSpacing.xs,
                      ),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(
                          AppSpacing.fullBorderRadius,
                        ),
                        color: Colors.white.withValues(alpha: 0.8),
                      ),
                      child: Text(
                        hint,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ),
                  )
                  .toList(growable: false),
            ),
          ],
        ],
      ),
    );
  }
}

/// 更多功能面板（图二：两行六项、无「更多」标题、与表情面板同高、不滚动）
class _ChatMorePanel extends ConsumerWidget {
  const _ChatMorePanel({required this.onClose});

  final VoidCallback onClose;

  static const double _panelHeight = 220;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final items = [
      (Icons.photo_library_outlined, UITextConstants.chatMorePhoto),
      (Icons.camera_alt_outlined, UITextConstants.chatMoreShoot),
      (
        Icons.local_fire_department_outlined,
        UITextConstants.chatMoreBurnAfterRead,
      ),
      (Icons.location_on_outlined, UITextConstants.chatMoreLocation),
      (Icons.call_outlined, UITextConstants.chatMoreAudioVideo),
      (Icons.card_giftcard_outlined, UITextConstants.chatMoreRedPacket),
    ];
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal:
            AppSpacing.semantic[DesignSemanticConstants
                .container]?[DesignSemanticConstants.md] ??
            AppSpacing.containerMd,
        vertical: AppSpacing.sm,
      ),
      height: _panelHeight,
      decoration: BoxDecoration(
        color: bgColor,
        border: Border(
          top: BorderSide(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.borderPrimary,
            ).withValues(alpha: 0.3),
          ),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: Alignment.centerRight,
            child: IconButton(
              icon: Icon(
                Icons.close,
                size: AppSpacing.iconMedium,
                color: fgPrimary,
              ),
              onPressed: onClose,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
          ),
          Expanded(
            child: GridView.builder(
              physics: const NeverScrollableScrollPhysics(),
              shrinkWrap: true,
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                childAspectRatio: 1.1,
                crossAxisSpacing: AppSpacing.sm,
                mainAxisSpacing: AppSpacing.sm,
              ),
              itemCount: items.length,
              itemBuilder: (context, index) {
                final e = items[index];
                return IconTheme(
                  data: IconThemeData(
                    size: AppSpacing.iconLarge,
                    color: fgPrimary,
                    fill: 0,
                    weight: 200,
                  ),
                  child: InkWell(
                    onTap: () {
                      ScaffoldMessenger.of(
                        context,
                      ).showSnackBar(SnackBar(content: Text('${e.$2}（开发中）')));
                    },
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(e.$1, size: AppSpacing.iconLarge),
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          e.$2,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color: fgPrimary,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
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

  @override
  Widget build(BuildContext context) {
    final type = message['type'] as String? ?? 'text';
    final isSelf = message['isSelf'] == true;
    final actions = <MapEntry<String, String>>[
      MapEntry('forward', UITextConstants.messageActionForward),
      MapEntry('select', UITextConstants.messageActionSelect),
      if (type == 'text') MapEntry('copy', UITextConstants.messageActionCopy),
      if (isSelf) MapEntry('recall', UITextConstants.messageActionRecall),
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
