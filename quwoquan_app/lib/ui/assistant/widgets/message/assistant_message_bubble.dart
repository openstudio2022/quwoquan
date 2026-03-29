import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/components/assistant/assistant_avatar.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/conversation/message_bubble_frame.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_answer_content.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_answer_toolbar.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_journey_view_model.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_process_drawer.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_turn_message_resolver.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/regenerate_options_popup.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/voice_message_bubble.dart';

bool _containsInternalAssistantText(String text) {
  final normalized = text.trim();
  if (normalized.isEmpty) return false;
  return AssistantDisplayTextResolver.containsInternalAssistantProtocolFragment(
    normalized,
  );
}

String _sanitizeAssistantTimelineText(String text) {
  final normalized =
      AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(text);
  if (normalized.isEmpty) return '';
  if (_containsInternalAssistantText(normalized)) return '';
  return normalized;
}

String _resolveAssistantVisibleAnswerText({
  required Map<String, dynamic> message,
  required String previewAnswer,
  required String content,
  required bool isStreaming,
}) {
  final runArtifacts = (message['runArtifacts'] as Map?)
      ?.cast<String, dynamic>();
  final candidates = isStreaming
      ? <String>[previewAnswer]
      : <String>[
          (message['displayMarkdown'] as String?) ?? '',
          (message['displayPlainText'] as String?) ?? '',
          (runArtifacts?['displayMarkdown'] as String?) ?? '',
          (runArtifacts?['displayPlainText'] as String?) ?? '',
          content,
        ];
  for (final candidate in candidates) {
    final sanitized = _sanitizeAssistantTimelineText(candidate);
    if (sanitized.isNotEmpty) return sanitized;
  }
  return '';
}

const double assistantBubbleMaxWidth = 280.0;
const double assistantBubbleWidthFactor = 0.84;
const double assistantBubbleImageSize = 200.0;

class AssistantMessageBubble extends StatelessWidget {
  const AssistantMessageBubble({
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
    this.journeyViewModel,
    this.answerGateOpen = true,
    this.isAssistantRunning = false,
    this.expandProcessByDefault = false,
    this.onRegenerateOptionSelected,
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
  final bool hideAvatarAndName;
  final bool useFullWidth;
  final bool renderSelfTextWithoutBubble;
  final String? runningStatusLabel;
  final AssistantJourneyViewModel? journeyViewModel;
  final bool answerGateOpen;
  final bool isAssistantRunning;
  final bool expandProcessByDefault;
  final void Function(RegenerateOption option)? onRegenerateOptionSelected;
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
        : math.max(
            assistantBubbleMaxWidth,
            viewportWidth * assistantBubbleWidthFactor,
          );
    final type = message['type'] as String? ?? 'text';
    final content = message['content'] as String? ?? '';
    final senderName = message['senderName'] as String? ?? '';
    final avatar = message['senderAvatar'] as String?;
    final isAssistantMessage =
        (message['senderId'] as String?) ==
        AppConceptConstants.assistantSenderId;
    final persistedDisplayState = isAssistantMessage
        ? resolvePersistedAssistantDisplayState(message)
        : const AssistantDisplayState();
    final fallbackAnswerText = isAssistantMessage
        ? _resolveAssistantVisibleAnswerText(
            message: message,
            previewAnswer: '',
            content: content,
            isStreaming: isAssistantRunning,
          )
        : content;
    final resolvedProcessTimeline = isAssistantMessage
        ? resolveAssistantProcessTimelineFromMessage(message)
        : const <ProcessTimelineFrame>[];
    final resolvedRetrievalProcessing = isAssistantMessage
        ? resolveAssistantRetrievalProcessingFromMessage(message)
        : const RetrievalProcessingSnapshot();
    final resolvedDisplayState = isAssistantMessage
        ? buildAssistantDisplayState(
            explicitState: persistedDisplayState,
            processTimeline: resolvedProcessTimeline,
            understandingSnapshot:
                resolveAssistantUnderstandingSnapshotFromMessage(message),
            retrievalProcessing: resolvedRetrievalProcessing,
            answerProcessing: resolveAssistantAnswerProcessingFromMessage(
              message,
            ),
            answerMarkdown:
                persistedDisplayState.answer.blocks.isEmpty &&
                    resolvePersistedAssistantDisplayMarkdown(message).isNotEmpty
                ? resolvePersistedAssistantDisplayMarkdown(message)
                : fallbackAnswerText,
            answerPlainText:
                persistedDisplayState.answer.blocks.isEmpty &&
                    resolvePersistedAssistantDisplayPlainText(
                      message,
                    ).isNotEmpty
                ? resolvePersistedAssistantDisplayPlainText(message)
                : fallbackAnswerText,
            finalAnswerReady: !isAssistantRunning,
          )
        : const AssistantDisplayState();
    final answerText = isAssistantMessage
        ? renderAnswerBlocksToMarkdown(resolvedDisplayState.answer.blocks)
        : content;
    final renderPlainSelfText =
        renderSelfTextWithoutBubble &&
        isRight &&
        !isAssistantMessage &&
        type == 'text';
    final resolvedJourneyViewModel = isAssistantMessage
        ? (journeyViewModel ??
              buildAssistantJourneyViewModel(
                journey: resolveAssistantJourneyFromMessage(message),
                processTimeline: resolvedProcessTimeline,
                isRunning: isAssistantRunning,
                displayState: resolvedDisplayState,
                retrievalProcessing: resolvedRetrievalProcessing,
                usageStats:
                    (message['uiUsageStats'] as Map?)
                        ?.cast<String, dynamic>() ??
                    const <String, dynamic>{},
                elapsedMs:
                    ((message['assistantElapsedMs'] as num?)?.toInt() ?? 0),
              ))
        : const AssistantJourneyViewModel();

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
          width: assistantBubbleImageSize,
          height: assistantBubbleImageSize,
          fit: BoxFit.cover,
          errorBuilder: (context, error, stackTrace) => Container(
            width: assistantBubbleImageSize,
            height: assistantBubbleImageSize,
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
        isRead: message['isRead'] == true,
        messageStatus: msgStatus,
      );
    } else if (isAssistantMessage) {
      contentWidget = Container(
        width: double.infinity,
        constraints: BoxConstraints(maxWidth: effectiveMaxWidth),
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.intraGroupLg,
        ),
        child: AssistantAnswerContent(
          message: message,
          content: answerText,
          answerBlocks: resolvedDisplayState.answer.blocks,
          textColor: textColor,
          onReferenceTap: onReferenceTap,
        ),
      );
    } else if (renderPlainSelfText) {
      contentWidget = Align(
        alignment: Alignment.centerRight,
        child: Container(
          constraints: BoxConstraints(maxWidth: effectiveMaxWidth * 0.8),
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupLg,
          ),
          decoration: BoxDecoration(
            color: bubbleColor,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          child: SelectableText(
            answerText,
            textAlign: TextAlign.left,
            style: TextStyle(
              fontSize:
                  Theme.of(context).textTheme.bodyLarge?.fontSize ??
                  AppSpacing.md,
              color: Colors.white,
              height: AppTypography.bodyLineHeight,
            ),
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

    final showProcessDrawer =
        isAssistantMessage && resolvedJourneyViewModel.hasVisibleContent;
    final showAnswerPreview =
        isAssistantMessage &&
        isAssistantRunning &&
        answerGateOpen &&
        answerText.trim().isNotEmpty;
    final showFinalAnswer =
        isAssistantMessage &&
        !isAssistantRunning &&
        answerText.trim().isNotEmpty;
    final showAnswerBubble =
        !isAssistantMessage ||
        showAnswerPreview ||
        showFinalAnswer ||
        (!showProcessDrawer && answerText.trim().isNotEmpty);
    final followupPrompt = resolveAssistantFollowupPrompt(message);
    final actionHints = resolveAssistantActionHints(message);
    Widget? avatarWidget;
    if (!hideAvatarAndName) {
      final chatAvatarSize = AppSpacing.avatarUserMd;
      if (showAssistantAvatar) {
        avatarWidget = AssistantAvatar(
          radius: chatAvatarSize / 2,
          onTap: onAvatarTap,
        );
      } else if (avatar != null && avatar.isNotEmpty) {
        avatarWidget = GestureDetector(
          onTap: onAvatarTap,
          child: RoundedSquareAvatar(
            size: chatAvatarSize,
            imageUrl: avatar,
            name: senderName,
          ),
        );
      } else if (onAvatarTap != null) {
        avatarWidget = GestureDetector(
          onTap: onAvatarTap,
          child: RoundedSquareAvatar(
            size: chatAvatarSize,
            imageUrl: null,
            name: senderName,
          ),
        );
      }
    }

    return GestureDetector(
      onTap: onTap,
      onLongPressStart: onLongPressStart,
      child: MessageBubbleFrame(
        isRight: isRight,
        hideAvatarAndName: hideAvatarAndName,
        senderName: senderName,
        textColor: textColor,
        avatar: avatarWidget,
        content: Column(
          crossAxisAlignment: isRight
              ? CrossAxisAlignment.end
              : CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (showProcessDrawer)
              AssistantProcessDrawer(
                viewModel: resolvedJourneyViewModel,
                initiallyExpanded: isAssistantRunning || expandProcessByDefault,
                onReferenceTap: onReferenceTap,
              )
            else if (runningStatusLabel != null)
              _RunningStatusRow(
                label: runningStatusLabel!,
                stageId: resolvedJourneyViewModel.activeStageId,
                textColor: textColor,
              ),
            if (showAnswerBubble)
              Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  if (isSelectionMode)
                    Padding(
                      padding: EdgeInsets.only(right: AppSpacing.intraGroupSm),
                      child: Icon(
                        isSelected
                            ? Icons.check_circle
                            : Icons.radio_button_unchecked,
                        size: AppSpacing.iconMedium,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  Flexible(fit: FlexFit.loose, child: contentWidget),
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
            if (showFeedbackActions && isAssistantMessage)
              AssistantAnswerToolbar(
                feedbackStatus: feedbackStatus,
                onFeedbackHelpful: onFeedbackHelpful,
                onFeedbackUnhelpful: onFeedbackUnhelpful,
                onCopyAnswer: onCopyAnswer,
                onShareAnswer: onShareAnswer,
                onRegenerateSelected: onRegenerateOptionSelected,
              ),
          ],
        ),
      ),
    );
  }
}

class _RunningStatusRow extends StatefulWidget {
  const _RunningStatusRow({
    required this.label,
    required this.textColor,
    this.stageId = ProcessStepId.unknown,
  });

  final String label;
  final Color textColor;
  final ProcessStepId stageId;

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
            stageId: widget.stageId,
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
    required this.stageId,
    required this.animation,
    required this.color,
  });

  final ProcessStepId stageId;
  final Animation<double> animation;
  final Color color;

  @override
  Widget build(BuildContext context) {
    switch (stageId) {
      case ProcessStepId.retrievalDesign:
      case ProcessStepId.retrievalProcessing:
        return _SearchingFlowIndicator(animation: animation, color: color);
      case ProcessStepId.understanding:
      case ProcessStepId.answerOrganization:
        return _ThinkingPetalIndicator(animation: animation, color: color);
      case ProcessStepId.unknown:
        return _WaitingTwistIndicator(animation: animation, color: color);
    }
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
  static const double _tailExtent = 8;
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
