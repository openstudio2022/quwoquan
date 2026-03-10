import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:quwoquan_app/components/assistant/assistant_avatar.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';
import 'package:quwoquan_app/personal_assistant/contracts/explainable_flow_event.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_answer_toolbar.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/assistant_process_drawer.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/regenerate_options_popup.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/voice_message_bubble.dart';

/// 聊天气泡最大宽度（语义尺寸，多屏适配由布局约束决定）
const double chatBubbleMaxWidth = 280.0;
const double chatBubbleWidthFactor = 0.84;

/// 聊天气泡内图片展示尺寸（语义尺寸）
const double chatBubbleImageSize = 200.0;

class ChatMessageBubble extends StatelessWidget {
  const ChatMessageBubble({
    super.key,
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
    this.onActionHintTap,
    this.onReferenceTap,
    this.hideAvatarAndName = false,
    this.useFullWidth = false,
    this.renderSelfTextWithoutBubble = false,
    this.runningStatusLabel,
    this.processState,
    this.flowEvents = const <ExplainableFlowEvent>[],
    this.answerGateOpen = true,
    this.isAssistantRunning = false,
    this.onRegenerateOptionSelected,
    this.receiptEnabled = false,
    this.memberCount = 2,
    this.messageStatus,
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

  /// 为 true 时不展示头像与昵称（新会话交互布局）
  final bool hideAvatarAndName;

  /// 为 true 时气泡内容占满可用宽度（新会话交互布局）
  final bool useFullWidth;

  /// 为 true 时，自己的文本消息改为右对齐纯文本，不再使用气泡。
  final bool renderSelfTextWithoutBubble;

  /// 当前轮助手回复的顶部状态文案（如「小趣正在规划与执行中」），非 null 时在气泡顶部展示
  final String? runningStatusLabel;

  /// Unified process state driving the single-drawer UI.
  final AssistantProcessState? processState;

  /// Explainable flow events for the new unified process drawer.
  final List<ExplainableFlowEvent> flowEvents;

  /// Whether the answer gate is open (aggregate/merge phase completed).
  /// When false and assistant is running, the answer area is suppressed.
  final bool answerGateOpen;

  /// Whether the assistant is currently running (drives drawer animation).
  final bool isAssistantRunning;

  /// Callback from the regenerate options popup.
  final void Function(RegenerateOption option)? onRegenerateOptionSelected;

  /// 会话是否开启已读回执
  final bool receiptEnabled;

  /// 会话成员数（群聊 >2 时不展示逐条回执）
  final int memberCount;

  /// 消息发送状态（sending / sent / failed / recalled）
  final String? messageStatus;
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
  final Future<void> Function(String hint)? onActionHintTap;
  final void Function(Map<String, dynamic> reference)? onReferenceTap;

  @override
  Widget build(BuildContext context) {
    final viewportWidth = MediaQuery.of(context).size.width;
    const horizontalPadding = 24.0;
    final effectiveMaxWidth = useFullWidth
        ? viewportWidth - 2 * horizontalPadding
        : math.max(chatBubbleMaxWidth, viewportWidth * chatBubbleWidthFactor);
    final type = message['type'] as String? ?? 'text';
    final content = message['content'] as String? ?? '';
    final streamFinalAnswer = message['streamFinalAnswer'] as String? ?? '';
    final senderName = message['senderName'] as String? ?? '';
    final avatar = message['senderAvatar'] as String?;
    final isRead = message['isRead'] == true;
    final isAssistantMessage =
        (message['senderId'] as String?) ==
        AppConceptConstants.assistantSenderId;
    final gatedStreamAnswer =
        isAssistantMessage && isAssistantRunning && !answerGateOpen
            ? ''
            : streamFinalAnswer;
    final answerText =
        isAssistantMessage && gatedStreamAnswer.trim().isNotEmpty
            ? gatedStreamAnswer
            : content;
    final renderPlainSelfText =
        renderSelfTextWithoutBubble &&
        isRight &&
        !isAssistantMessage &&
        type == 'text';

    Widget contentWidget;
    if (type == 'task_card') {
      final tasks = message['tasks'] as List<dynamic>? ?? [];
      contentWidget = Container(
        constraints: BoxConstraints(maxWidth: effectiveMaxWidth),
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
          width: chatBubbleImageSize,
          height: chatBubbleImageSize,
          fit: BoxFit.cover,
          errorBuilder: (context, error, stackTrace) => Container(
            width: chatBubbleImageSize,
            height: chatBubbleImageSize,
            color: bubbleColor,
            child: Icon(Icons.broken_image, color: textColor),
          ),
        ),
      );
    } else if (type == 'audio') {
      final media = message['media'] is Map
          ? (message['media'] as Map).cast<String, dynamic>()
          : <String, dynamic>{};
      final mediaUrl =
          (media['url'] as String?) ?? (message['mediaUrl'] as String?) ?? '';
      final durationMs = (media['durationMs'] as num?)?.toInt() ?? 0;
      final waveformRaw = media['waveform'];
      final waveform = waveformRaw is List
          ? waveformRaw.map((e) => (e as num).toDouble()).toList()
          : <double>[];
      final msgId = (message['_id'] ?? message['id'] ?? '') as String;
      final msgStatus =
          (message['messageStatus'] ?? message['status'] ?? 'sent') as String;
      contentWidget = VoiceMessageBubble(
        messageId: msgId,
        mediaUrl: mediaUrl,
        durationMs: durationMs,
        waveform: waveform,
        isOutgoing: isRight,
        isRead: isRead,
        messageStatus: msgStatus,
      );
    } else if (isAssistantMessage) {
      contentWidget = Container(
        width: double.infinity,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupLg,
        ),
        child: _buildAssistantMarkdownContent(
          context: context,
          content: answerText,
          textColor: textColor,
        ),
      );
    } else if (renderPlainSelfText) {
      contentWidget = Container(
        constraints: BoxConstraints(maxWidth: effectiveMaxWidth),
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.xs,
          vertical: AppSpacing.xs / 2,
        ),
        alignment: Alignment.centerRight,
        child: SelectableText(
          answerText,
          textAlign: TextAlign.right,
          style: TextStyle(
            fontSize:
                Theme.of(context).textTheme.bodyLarge?.fontSize ??
                AppSpacing.md,
            color: textColor,
            height: AppTypography.bodyLineHeight,
            fontWeight: FontWeight.w500,
          ),
        ),
      );
    } else {
      contentWidget = _BubbleWithTail(
        isRight: isRight,
        color: bubbleColor,
        child: Container(
          constraints: BoxConstraints(maxWidth: effectiveMaxWidth),
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerSm,
            AppSpacing.intraGroupLg,
            AppSpacing.containerSm + 2,
            AppSpacing.intraGroupLg,
          ),
          child: SelectableText(
            answerText,
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

    final phaseTimeline =
        (message['uiPhaseTimelineV1'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final hideAnswerBubbleWhileStreamingProcess =
        isAssistantMessage &&
        phaseTimeline.isNotEmpty &&
        answerText.trim().isEmpty;
    final followupPrompt =
        (((message['uiAnswer'] as Map?)?['followupPrompt']) as String?)
            ?.trim() ??
        '';
    final usageStats =
        (message['uiUsageStatsV1'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final actionHints =
        ((((message['uiAnswer'] as Map?)?['actionHints']) as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false)) ??
        const <String>[];
    Widget? avatarWidget;
    if (!hideAvatarAndName) {
      final chatAvatarRadius = AppSpacing.avatarUserSm / 2;
      if (showAssistantAvatar) {
        avatarWidget = AssistantAvatar(
          radius: chatAvatarRadius,
          onTap: onAvatarTap,
        );
      } else if (avatar != null && avatar.isNotEmpty) {
        avatarWidget = GestureDetector(
          onTap: onAvatarTap,
          child: RoundedSquareAvatar(
            size: AppSpacing.avatarUserSm,
            imageUrl: avatar,
            name: senderName,
          ),
        );
      }
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
            if (!hideAvatarAndName && !isRight && avatarWidget != null)
              avatarWidget,
            if (!hideAvatarAndName && !isRight && avatarWidget != null)
              SizedBox(width: AppSpacing.sm),
            Flexible(
              child: Column(
                crossAxisAlignment: isRight
                    ? CrossAxisAlignment.end
                    : CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (!hideAvatarAndName && senderName.isNotEmpty && !isRight)
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
                  if (isAssistantMessage && processState != null)
                    AssistantProcessDrawer(
                      processState: processState!,
                      isRunning: isAssistantRunning,
                      initiallyExpanded: isAssistantRunning,
                      flowEvents: flowEvents,
                      onReferenceUrlTap: onReferenceTap != null
                          ? (url) =>
                                onReferenceTap!(<String, dynamic>{'url': url})
                          : null,
                    )
                  else if (isAssistantMessage &&
                      _hasPersistedProcessBlocks(message))
                    AssistantProcessDrawer(
                      processState: _rebuildProcessStateFromMessage(message),
                      isRunning: false,
                      initiallyExpanded: false,
                      onReferenceUrlTap: onReferenceTap != null
                          ? (url) =>
                                onReferenceTap!(<String, dynamic>{'url': url})
                          : null,
                    )
                  else if (runningStatusLabel != null)
                    _RunningStatusRow(
                      label: runningStatusLabel!,
                      textColor: textColor,
                    )
                  else if (phaseTimeline.isNotEmpty) ...[
                    SizedBox(height: AppSpacing.xs),
                    _AssistantPhaseTimelineCard(
                      phases: phaseTimeline,
                      usageStats: usageStats,
                      onReferenceTap: onReferenceTap,
                    ),
                  ],
                  if (!hideAnswerBubbleWhileStreamingProcess)
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
                          _ReceiptStatusIndicator(
                            isRead: isRead,
                            receiptEnabled: receiptEnabled,
                            memberCount: memberCount,
                            messageStatus: messageStatus,
                            textColor: textColor,
                          ),
                        if (renderPlainSelfText)
                          Flexible(fit: FlexFit.loose, child: contentWidget)
                        else
                          Expanded(child: contentWidget),
                      ],
                    ),
                  if (followupPrompt.isNotEmpty || actionHints.isNotEmpty) ...[
                    SizedBox(height: AppSpacing.xs),
                    _AssistantFollowupCard(
                      followupPrompt: followupPrompt,
                      actionHints: actionHints,
                      onActionHintTap: onActionHintTap,
                    ),
                  ],
                  // References card removed — source data shown inside process drawer.
                  // v4: New unified toolbar replaces old feedback buttons.
                  if (showFeedbackActions && isAssistantMessage)
                    AssistantAnswerToolbar(
                      feedbackStatus: feedbackStatus,
                      onFeedbackHelpful: onFeedbackHelpful,
                      onFeedbackUnhelpful: onFeedbackUnhelpful,
                      onCopyAnswer: onCopyAnswer,
                      onShareAnswer: onShareAnswer,
                      onRegenerateSelected: onRegenerateOptionSelected,
                    )
                  else if (showFeedbackActions) ...[
                    SizedBox(height: AppSpacing.xs),
                    Wrap(
                      spacing: AppSpacing.xs,
                      runSpacing: AppSpacing.xs,
                      children: [
                        IconButton(
                          onPressed: onFeedbackHelpful,
                          icon: const Icon(Icons.thumb_up_alt_outlined),
                          tooltip: UITextConstants.assistantFeedbackHelpful,
                          iconSize: AppSpacing.iconSmall,
                        ),
                        IconButton(
                          onPressed: onFeedbackUnhelpful,
                          icon: const Icon(Icons.thumb_down_alt_outlined),
                          tooltip: UITextConstants.assistantFeedbackUnhelpful,
                          iconSize: AppSpacing.iconSmall,
                        ),
                        IconButton(
                          onPressed: onRegenerateAnswer,
                          icon: const Icon(Icons.refresh),
                          tooltip: UITextConstants.assistantActionRegenerate,
                          iconSize: AppSpacing.iconSmall,
                        ),
                      ],
                    ),
                  ],
                ],
              ),
            ),
            if (!hideAvatarAndName && isRight && avatarWidget != null)
              SizedBox(width: AppSpacing.sm),
            if (!hideAvatarAndName && isRight && avatarWidget != null)
              avatarWidget,
          ],
        ),
      ),
    );
  }

  static final RegExp _referenceBlockPattern = RegExp(
    r'\n---\n📚\s*\*{0,2}参考资料\*{0,2}[\s\S]*$',
  );

  Widget _buildAssistantMarkdownContent({
    required BuildContext context,
    required String content,
    required Color textColor,
  }) {
    final cleaned = content
        .replaceFirst(_referenceBlockPattern, '')
        .trimRight();
    final segments = _MarkdownSegment.parse(cleaned);
    final textStyle = TextStyle(
      fontSize:
          Theme.of(context).textTheme.bodyLarge?.fontSize ?? AppSpacing.md,
      color: textColor,
      height: AppTypography.bodyLineHeight,
    );
    final mdStyle = MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
      p: textStyle,
      h1: textStyle.copyWith(fontWeight: FontWeight.w700),
      h2: textStyle.copyWith(fontWeight: FontWeight.w700),
      h3: textStyle.copyWith(fontWeight: FontWeight.w600),
      listBullet: textStyle,
      blockquote: textStyle,
      code: textStyle.copyWith(color: textColor, fontFamily: 'monospace'),
      codeblockPadding: EdgeInsets.all(AppSpacing.containerSm),
      blockquotePadding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      tableColumnWidth: const IntrinsicColumnWidth(),
      tableCellsPadding: EdgeInsets.symmetric(
        horizontal: AppSpacing.xs,
        vertical: AppSpacing.xs / 2,
      ),
      tableBody: textStyle.copyWith(fontSize: AppTypography.sm),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: segments
          .map((segment) {
            if (!segment.isCard) {
              return _safeMarkdownBody(
                markdownText: segment.content,
                styleSheet: mdStyle,
                textStyle: textStyle,
              );
            }
            return Container(
              margin: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
              padding: EdgeInsets.all(AppSpacing.containerSm),
              decoration: BoxDecoration(
                color: AppColors.primaryColor.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                border: Border.all(
                  color: AppColors.primaryColor.withValues(alpha: 0.24),
                ),
              ),
              child: _safeMarkdownBody(
                markdownText: segment.toCardMarkdown(),
                styleSheet: mdStyle,
                textStyle: textStyle,
              ),
            );
          })
          .toList(growable: false),
    );
  }

  Widget _safeMarkdownBody({
    required String markdownText,
    required MarkdownStyleSheet styleSheet,
    required TextStyle textStyle,
  }) {
    final hasTable =
        markdownText.contains('|') &&
        RegExp(r'\|[^\n]+\|').hasMatch(markdownText);
    try {
      final body = MarkdownBody(
        data: markdownText,
        selectable: true,
        styleSheet: styleSheet,
      );
      if (hasTable) {
        return SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minWidth: 360),
            child: body,
          ),
        );
      }
      return body;
    } catch (_) {
      return SelectableText(markdownText, style: textStyle);
    }
  }
}

bool _hasPersistedProcessBlocks(Map<String, dynamic> message) {
  final rawBlocks = (message['uiProcessContentBlocks'] as List?) ?? const [];
  final rawTimeline = (message['uiProcessTimelineV2'] as List?) ?? const [];
  return rawBlocks.isNotEmpty || rawTimeline.isNotEmpty;
}

AssistantProcessState _rebuildProcessStateFromMessage(
  Map<String, dynamic> message,
) {
  final rawBlocks = (() {
    final persisted =
        (message['uiProcessContentBlocks'] as List?)?.whereType<Map>().toList(
          growable: false,
        ) ??
        const <Map>[];
    if (persisted.isNotEmpty) return persisted;
    final timeline =
        (message['uiProcessTimelineV2'] as List?)?.whereType<Map>().toList(
          growable: false,
        ) ??
        const <Map>[];
    return timeline
        .map((item) => item.cast<String, dynamic>())
        .where(
          (item) => ((item['summary'] as String?)?.trim().isNotEmpty ?? false),
        )
        .map((item) {
          final refs =
              (item['references'] as List?)?.whereType<Map>().toList(
                growable: false,
              ) ??
              const <Map>[];
          return <String, dynamic>{
            'type': refs.isNotEmpty ? 'analysisSummary' : 'text',
            'text': (item['summary'] as String?)?.trim() ?? '',
            'references': refs,
          };
        })
        .toList(growable: false);
  })();
  final contentBlocks = <ProcessContentBlock>[];
  for (final raw in rawBlocks) {
    final typeName = (raw['type'] as String?) ?? 'text';
    final text = (raw['text'] as String?) ?? '';
    final rawRefs =
        (raw['references'] as List?)?.whereType<Map>() ?? const <Map>[];
    final refs = rawRefs
        .map(
          (r) => ProcessReference(
            title: (r['title'] as String?) ?? '',
            url: (r['url'] as String?) ?? '',
            source: (r['source'] as String?) ?? '',
          ),
        )
        .toList(growable: false);
    ProcessContentBlockType blockType;
    switch (typeName) {
      case 'searchSummary':
        blockType = ProcessContentBlockType.searchSummary;
      case 'analysisSummary':
        blockType = ProcessContentBlockType.analysisSummary;
      default:
        blockType = ProcessContentBlockType.text;
    }
    contentBlocks.add(
      ProcessContentBlock(type: blockType, text: text, references: refs),
    );
  }
  final usageStats =
      (message['uiUsageStatsV1'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final timeline = (message['uiProcessTimelineV2'] as List?) ?? const [];
  final stageLabel = timeline.isNotEmpty
      ? (((timeline.last as Map)['summary'] as String?)?.trim().isNotEmpty ??
                false)
            ? ((timeline.last as Map)['summary'] as String).trim()
            : '已完成'
      : '已完成';
  return AssistantProcessState(
    stage: ProcessStage.completed,
    stageLabel: stageLabel,
    isStreaming: false,
    contentBlocks: contentBlocks,
    usageStats: usageStats,
  );
}

/// 助手当前轮回复顶部的状态行：按阶段展示不同动效 + 文案 + 可选引用数
class _RunningStatusRow extends StatefulWidget {
  const _RunningStatusRow({required this.label, required this.textColor});

  final String label;
  final Color textColor;

  @override
  State<_RunningStatusRow> createState() => _RunningStatusRowState();
}

class _RunningStatusRowState extends State<_RunningStatusRow>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final label = widget.label.trim();
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.xs),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _PhaseActivityIndicator(
            phaseLabel: label,
            animation: _controller,
            color: AppColors.primaryColor,
          ),
          SizedBox(width: AppSpacing.xs),
          Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: widget.textColor.withValues(alpha: 0.7),
            ),
          ),
        ],
      ),
    );
  }
}

class _PhaseActivityIndicator extends StatelessWidget {
  const _PhaseActivityIndicator({
    required this.phaseLabel,
    required this.animation,
    required this.color,
  });

  final String phaseLabel;
  final Animation<double> animation;
  final Color color;

  @override
  Widget build(BuildContext context) {
    if (phaseLabel.contains(UITextConstants.assistantPhaseSearching) ||
        phaseLabel.contains('搜索')) {
      return _SearchingFlowIndicator(animation: animation, color: color);
    }
    if (phaseLabel.contains(UITextConstants.assistantPhaseThinking) ||
        phaseLabel.contains(UITextConstants.assistantPhaseAnalyzing) ||
        phaseLabel.contains(UITextConstants.assistantPhaseAnswering)) {
      return _ThinkingPetalIndicator(animation: animation, color: color);
    }
    if (phaseLabel.contains(UITextConstants.assistantPhaseAssessing)) {
      return _ThinkingPetalIndicator(animation: animation, color: color);
    }
    return _WaitingTwistIndicator(animation: animation, color: color);
  }
}

class _WaitingTwistIndicator extends StatelessWidget {
  const _WaitingTwistIndicator({required this.animation, required this.color});

  final Animation<double> animation;
  final Color color;

  @override
  Widget build(BuildContext context) {
    const size = 14.0;
    return SizedBox(
      width: size,
      height: size,
      child: AnimatedBuilder(
        animation: animation,
        builder: (context, _) {
          final t = animation.value;
          final a = (math.sin(t * 2 * math.pi) + 1) / 2;
          return Stack(
            alignment: Alignment.center,
            children: [
              Transform.rotate(
                angle: math.pi / 4 * a,
                child: Container(
                  width: AppSpacing.interGroupSm,
                  height: AppSpacing.three,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.85),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.fullBorderRadius,
                    ),
                  ),
                ),
              ),
              Transform.rotate(
                angle: -math.pi / 4 * a,
                child: Container(
                  width: AppSpacing.sm,
                  height: AppSpacing.three,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.45),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.fullBorderRadius,
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _SearchingFlowIndicator extends StatelessWidget {
  const _SearchingFlowIndicator({required this.animation, required this.color});

  final Animation<double> animation;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.eighteen,
      height: AppSpacing.interGroupSm,
      child: AnimatedBuilder(
        animation: animation,
        builder: (context, _) {
          final t = animation.value;
          double alpha(int idx) =>
              ((math.sin((t - idx * 0.16) * 2 * math.pi) + 1) / 2) * 0.7 + 0.2;
          return Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: List<Widget>.generate(
              3,
              (i) => Container(
                width: AppSpacing.xs,
                height: AppSpacing.ten,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: alpha(i)),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.radiusNinetyNine,
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _ThinkingPetalIndicator extends StatelessWidget {
  const _ThinkingPetalIndicator({required this.animation, required this.color});

  final Animation<double> animation;
  final Color color;

  @override
  Widget build(BuildContext context) {
    const size = 14.0;
    return SizedBox(
      width: size,
      height: size,
      child: AnimatedBuilder(
        animation: animation,
        builder: (context, _) {
          final t = animation.value;
          return Stack(
            children: List<Widget>.generate(8, (i) {
              final angle = i * math.pi / 4;
              final pulse = ((math.sin((t - i * 0.08) * 2 * math.pi) + 1) / 2);
              final r = 5.0;
              final x = size / 2 + math.cos(angle) * r;
              final y = size / 2 + math.sin(angle) * r;
              return Positioned(
                left: x - AppSpacing.twoPointFour / 2,
                top: y - AppSpacing.twoPointFour / 2,
                child: Container(
                  width: AppSpacing.twoPointFour,
                  height: AppSpacing.twoPointFour,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.25 + pulse * 0.7),
                    shape: BoxShape.circle,
                  ),
                ),
              );
            }),
          );
        },
      ),
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

class _MarkdownSegment {
  const _MarkdownSegment._({
    required this.content,
    required this.isCard,
    this.cardType = '',
    this.cardPayload = const <String, dynamic>{},
  });

  final String content;
  final bool isCard;
  final String cardType;
  final Map<String, dynamic> cardPayload;

  static const Set<String> _supportedCardTypes = <String>{
    'compare',
    'trend',
    'diagram',
  };

  factory _MarkdownSegment.text(String content) =>
      _MarkdownSegment._(content: content, isCard: false);

  factory _MarkdownSegment.card({
    required String cardType,
    required String payload,
  }) {
    final type = cardType.trim().toLowerCase();
    if (!_supportedCardTypes.contains(type)) {
      return _MarkdownSegment.text('```card:$cardType\n$payload\n```');
    }
    final decoded = _tryDecode(payload);
    if (decoded == null || decoded.isEmpty) {
      return _MarkdownSegment.text('```card:$cardType\n$payload\n```');
    }
    return _MarkdownSegment._(
      content: payload,
      isCard: true,
      cardType: type,
      cardPayload: decoded,
    );
  }

  static List<_MarkdownSegment> parse(String raw) {
    if (!raw.contains('```card:')) {
      return <_MarkdownSegment>[_MarkdownSegment.text(raw)];
    }
    final regex = RegExp(r'```card:([a-zA-Z0-9_-]+)\n([\s\S]*?)```');
    final segments = <_MarkdownSegment>[];
    var index = 0;
    for (final match in regex.allMatches(raw)) {
      if (match.start > index) {
        segments.add(_MarkdownSegment.text(raw.substring(index, match.start)));
      }
      final type = (match.group(1) ?? '').trim();
      final payload = (match.group(2) ?? '').trim();
      segments.add(_MarkdownSegment.card(cardType: type, payload: payload));
      index = match.end;
    }
    if (index < raw.length) {
      segments.add(_MarkdownSegment.text(raw.substring(index)));
    }
    return segments.where((seg) => seg.content.trim().isNotEmpty).toList();
  }

  String toCardMarkdown() {
    if (!isCard || cardPayload.isEmpty) return content;
    final title = (cardPayload['title'] as String?)?.trim();
    final lines = <String>[
      '### ${title?.isNotEmpty == true ? title! : _fallbackTitle()}',
    ];
    if (cardType == 'diagram') {
      final mermaid = (cardPayload['mermaid'] as String?)?.trim() ?? '';
      if (mermaid.isNotEmpty) {
        lines
          ..add('```mermaid')
          ..add(mermaid)
          ..add('```');
      }
    }
    cardPayload.forEach((key, value) {
      if (key == 'title' || key == 'mermaid') return;
      lines.add('- **$key**: ${_valueText(value)}');
    });
    return lines.join('\n');
  }

  String _fallbackTitle() {
    switch (cardType) {
      case 'compare':
        return '对比卡片';
      case 'trend':
        return '趋势卡片';
      case 'diagram':
        return '结构图';
      default:
        return cardType;
    }
  }

  static Map<String, dynamic>? _tryDecode(String payload) {
    try {
      final decoded = jsonDecode(payload);
      if (decoded is Map<String, dynamic>) return decoded;
      if (decoded is Map) return decoded.cast<String, dynamic>();
      return null;
    } catch (_) {
      return null;
    }
  }

  static String _valueText(Object? value) {
    if (value == null) return '';
    if (value is num || value is bool || value is String) {
      return value.toString();
    }
    return jsonEncode(value);
  }
}

class _AssistantPhaseTimelineCard extends StatefulWidget {
  const _AssistantPhaseTimelineCard({
    required this.phases,
    required this.usageStats,
    this.onReferenceTap,
  });

  final List<Map<String, dynamic>> phases;
  final Map<String, dynamic> usageStats;
  final void Function(Map<String, dynamic> reference)? onReferenceTap;

  @override
  State<_AssistantPhaseTimelineCard> createState() =>
      _AssistantPhaseTimelineCardState();
}

class _AssistantPhaseTimelineCardState
    extends State<_AssistantPhaseTimelineCard> {
  final Set<String> _expandedPhaseIds = <String>{};

  @override
  Widget build(BuildContext context) {
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
          ...widget.phases.map((phase) {
            final phaseId =
                (phase['phaseId'] as String?)?.trim().isNotEmpty == true
                ? (phase['phaseId'] as String).trim()
                : 'phase_${phase.hashCode}';
            final expanded = _expandedPhaseIds.contains(phaseId);
            final title =
                ((phase['title'] as String?)?.trim().isNotEmpty ?? false)
                ? (phase['title'] as String).trim()
                : '过程阶段';
            final summary = (phase['summary'] as String?)?.trim() ?? '';
            final status = (phase['status'] as String?)?.trim() ?? '';
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
            return Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.xs),
              child: Container(
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.85),
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                ),
                child: Column(
                  children: [
                    InkWell(
                      onTap: () {
                        setState(() {
                          if (expanded) {
                            _expandedPhaseIds.remove(phaseId);
                          } else {
                            _expandedPhaseIds.add(phaseId);
                          }
                        });
                      },
                      child: Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.containerSm,
                          vertical: AppSpacing.xs,
                        ),
                        child: Row(
                          children: [
                            _phaseStatusDot(status),
                            SizedBox(width: AppSpacing.xs),
                            Expanded(
                              child: Text(
                                summary.isEmpty ? title : '$title：$summary',
                                style: TextStyle(
                                  fontSize: AppTypography.sm,
                                  color: AppColors.primaryColor.withValues(
                                    alpha: 0.9,
                                  ),
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                            Icon(
                              expanded ? Icons.expand_less : Icons.expand_more,
                              size: AppSpacing.iconSmall,
                              color: AppColors.primaryColor,
                            ),
                          ],
                        ),
                      ),
                    ),
                    if (expanded) ...[
                      if (details.isNotEmpty)
                        Padding(
                          padding: EdgeInsets.fromLTRB(
                            AppSpacing.containerSm,
                            0,
                            AppSpacing.containerSm,
                            AppSpacing.xs,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: details
                                .map(
                                  (line) => Padding(
                                    padding: EdgeInsets.only(
                                      bottom: AppSpacing.xs / 2,
                                    ),
                                    child: Text(
                                      '• $line',
                                      style: TextStyle(
                                        fontSize: AppTypography.sm,
                                        color: AppColors.primaryColor
                                            .withValues(alpha: 0.85),
                                      ),
                                    ),
                                  ),
                                )
                                .toList(growable: false),
                          ),
                        ),
                      if (references.isNotEmpty)
                        Padding(
                          padding: EdgeInsets.fromLTRB(
                            AppSpacing.containerSm,
                            0,
                            AppSpacing.containerSm,
                            AppSpacing.xs,
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: references
                                .map(
                                  (ref) => InkWell(
                                    onTap: () =>
                                        widget.onReferenceTap?.call(ref),
                                    child: Padding(
                                      padding: EdgeInsets.only(
                                        bottom: AppSpacing.xs / 2,
                                      ),
                                      child: Text(
                                        '来源：${(ref['title'] ?? '').toString()}',
                                        style: TextStyle(
                                          fontSize: AppTypography.sm,
                                          color: AppColors.primaryColor,
                                        ),
                                      ),
                                    ),
                                  ),
                                )
                                .toList(growable: false),
                          ),
                        ),
                    ],
                  ],
                ),
              ),
            );
          }),
          if (widget.usageStats.isNotEmpty) ...[
            SizedBox(height: AppSpacing.xs),
            Text(
              _usageLabel(widget.usageStats),
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColors.primaryColor.withValues(alpha: 0.8),
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _phaseStatusDot(String status) {
    if (status == 'completed') {
      return Icon(
        Icons.check_circle,
        size: AppSpacing.seven + 2,
        color: AppColors.primaryColor.withValues(alpha: 0.7),
      );
    }
    if (status == 'warning') {
      return Icon(
        Icons.info_outline,
        size: AppSpacing.seven + 2,
        color: Colors.orange.withValues(alpha: 0.8),
      );
    }
    final color = status == 'running'
        ? AppColors.primaryColor
        : AppColors.primaryColor.withValues(alpha: 0.45);
    return Container(
      width: AppSpacing.seven,
      height: AppSpacing.seven,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );
  }

  String _usageLabel(Map<String, dynamic> usage) {
    final calls = (usage['modelCallCount'] as num?)?.toInt() ?? 0;
    final total = (usage['totalTokens'] as num?)?.toInt() ?? 0;
    final max = (usage['maxTokensPerCall'] as num?)?.toInt() ?? 0;
    return '模型调用 $calls 次  ·  总 Token $total  ·  单次最大 $max';
  }
}

class _AssistantFollowupCard extends StatelessWidget {
  const _AssistantFollowupCard({
    required this.followupPrompt,
    required this.actionHints,
    this.onActionHintTap,
  });

  final String followupPrompt;
  final List<String> actionHints;
  final Future<void> Function(String hint)? onActionHintTap;

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
                    (hint) => InkWell(
                      onTap: onActionHintTap == null
                          ? null
                          : () => onActionHintTap!(hint),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.fullBorderRadius,
                      ),
                      child: Container(
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

/// 参考资料卡片：展示 web_search 工具返回的来源链接，默认收起仅显示一行摘要
class _AssistantReferencesCard extends StatefulWidget {
  const _AssistantReferencesCard({required this.references});

  final List<Map<String, dynamic>> references;

  @override
  State<_AssistantReferencesCard> createState() =>
      _AssistantReferencesCardState();
}

class _AssistantReferencesCardState extends State<_AssistantReferencesCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            onTap: () => setState(() => _expanded = !_expanded),
            behavior: HitTestBehavior.opaque,
            child: Row(
              children: [
                Icon(
                  Icons.link_rounded,
                  size: AppSpacing.iconSmall,
                  color: AppColors.primaryColor.withValues(alpha: 0.8),
                ),
                SizedBox(width: AppSpacing.xs / 2),
                Expanded(
                  child: Text(
                    '参考了 ${widget.references.length} 篇资料',
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: AppColors.primaryColor,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                Icon(
                  _expanded
                      ? CupertinoIcons.chevron_up
                      : CupertinoIcons.chevron_down,
                  size: AppSpacing.iconSmall,
                  color: AppColors.primaryColor.withValues(alpha: 0.6),
                ),
              ],
            ),
          ),
          if (_expanded) ...[
            SizedBox(height: AppSpacing.xs),
            ...widget.references.asMap().entries.map((entry) {
              final index = entry.key;
              final ref = entry.value;
              final title = (ref['title'] as String?)?.trim() ?? '';
              final url = (ref['url'] as String?)?.trim() ?? '';
              final source =
                  (ref['source'] as String?)?.trim().isNotEmpty == true
                  ? (ref['source'] as String).trim()
                  : Uri.tryParse(url)?.host ?? '';
              return InkWell(
                onTap: null,
                borderRadius: BorderRadius.circular(
                  AppSpacing.borderRadius / 2,
                ),
                child: Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpacing.xs / 2),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: AppSpacing.eighteen,
                        height: AppSpacing.eighteen,
                        margin: EdgeInsets.only(
                          top: AppSpacing.one,
                          right: AppSpacing.xs,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.primaryColor.withValues(alpha: 0.12),
                          shape: BoxShape.circle,
                        ),
                        child: Center(
                          child: Text(
                            '${index + 1}',
                            style: TextStyle(
                              fontSize: AppTypography.xs,
                              color: AppColors.primaryColor,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              title,
                              style: TextStyle(
                                fontSize: AppTypography.sm,
                                color: AppColors.primaryColor,
                                fontWeight: FontWeight.w500,
                                decoration: TextDecoration.underline,
                                decorationColor: AppColors.primaryColor
                                    .withValues(alpha: 0.5),
                              ),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            if (source.isNotEmpty)
                              Text(
                                source,
                                style: TextStyle(
                                  fontSize: AppTypography.xs,
                                  color: AppColors.primaryColor.withValues(
                                    alpha: 0.55,
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                      Icon(
                        Icons.open_in_new_rounded,
                        size: AppSpacing.iconSmall * 0.85,
                        color: AppColors.primaryColor.withValues(alpha: 0.45),
                      ),
                    ],
                  ),
                ),
              );
            }),
          ],
        ],
      ),
    );
  }
}

/// 消息回执状态指示器：根据 receiptEnabled / memberCount / messageStatus 显示不同状态。
/// - sending → 时钟图标
/// - failed → 红色感叹号
/// - 1:1 会话 + receiptEnabled → 双勾（已读）/ 单勾（已送达）
/// - 群聊（memberCount > 2）或 receiptEnabled=false → 单勾
class _ReceiptStatusIndicator extends StatelessWidget {
  const _ReceiptStatusIndicator({
    required this.isRead,
    required this.receiptEnabled,
    required this.memberCount,
    required this.textColor,
    this.messageStatus,
  });

  final bool isRead;
  final bool receiptEnabled;
  final int memberCount;
  final String? messageStatus;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    final IconData icon;
    final Color color;

    switch (messageStatus) {
      case 'sending':
        icon = Icons.access_time;
        color = textColor.withValues(alpha: 0.5);
      case 'failed':
        icon = Icons.error_outline;
        color = AppColors.error;
      default:
        if (receiptEnabled && memberCount <= 2 && isRead) {
          icon = Icons.done_all;
          color = AppColors.primaryColor;
        } else {
          icon = Icons.done;
          color = textColor.withValues(alpha: 0.6);
        }
    }

    return Padding(
      padding: EdgeInsets.only(right: AppSpacing.xs),
      child: Icon(icon, size: AppSpacing.iconSmall, color: color),
    );
  }
}
