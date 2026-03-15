import 'package:flutter/foundation.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/assistant/assistant_avatar.dart';

class MediaAssistantPanel extends StatelessWidget {
  const MediaAssistantPanel({
    super.key,
    required this.isDark,
    required this.titleText,
    required this.messages,
    required this.scrollController,
    required this.inputController,
    required this.inputFocusNode,
    required this.suggestions,
    required this.onClose,
    required this.onSend,
    required this.onSuggestionTap,
    required this.onAssistantAvatarTap,
  });

  final bool isDark;
  final String titleText;
  final ValueListenable<List<AssistantChatMessage>> messages;
  final ScrollController scrollController;
  final TextEditingController inputController;
  final FocusNode inputFocusNode;
  final List<String> suggestions;
  final VoidCallback onClose;
  final VoidCallback onSend;
  final ValueChanged<String> onSuggestionTap;
  final VoidCallback? onAssistantAvatarTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(AppSpacing.largeBorderRadius),
          topRight: Radius.circular(AppSpacing.largeBorderRadius),
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.12),
            blurRadius: AppSpacing.lg,
            offset: const Offset(0, -4),
          ),
        ],
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: context.safeGetContainerSpacing(SpacingSize.md),
            vertical: context.safeGetIntraGroupSpacing(SpacingSize.md),
          ),
          child: SizedBox(
            height: MediaQuery.of(context).size.height * AppSpacing.assistantPanelHeightRatioMax,
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Center(
                        child: Text(
                          titleText,
                          style: TextStyle(
                            fontSize: AppTypography.lg.sp,
                            fontWeight: FontWeight.w600,
                            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                          ),
                        ),
                      ),
                    ),
                    CupertinoButton(
                      padding: EdgeInsets.zero,
                      minSize: AppSpacing.minInteractiveSize,
                      onPressed: onClose,
                      child: Icon(
                        CupertinoIcons.xmark,
                        size: AppSpacing.iconMedium,
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                      ),
                    ),
                  ],
                ),
                SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
                Expanded(
                  child: ValueListenableBuilder<List<AssistantChatMessage>>(
                    valueListenable: messages,
                    builder: (context, items, child) {
                      return ListView.builder(
                        controller: scrollController,
                        padding: EdgeInsets.zero,
                        itemCount: items.length,
                        itemBuilder: (context, index) {
                          final message = items[index];
                          return _MediaAssistantMessageBubble(
                            isDark: isDark,
                            message: message,
                            onAssistantAvatarTap: onAssistantAvatarTap,
                          );
                        },
                      );
                    },
                  ),
                ),
                SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    UITextConstants.assistantPromptFollowUp,
                    style: TextStyle(
                      fontSize: AppTypography.sm.sp,
                      color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                    ),
                  ),
                ),
                SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
                Align(
                  alignment: Alignment.centerLeft,
                  child: Wrap(
                    spacing: context.safeGetIntraGroupSpacing(SpacingSize.sm),
                    runSpacing: context.safeGetIntraGroupSpacing(SpacingSize.sm),
                    children: suggestions
                        .map((text) => _MediaSuggestionChip(
                              isDark: isDark,
                              text: text,
                              onTap: () => onSuggestionTap(text),
                            ))
                        .toList(),
                  ),
                ),
                SizedBox(height: context.safeGetInterGroupSpacing(SpacingSize.sm)),
                _MediaAssistantInput(
                  isDark: isDark,
                  controller: inputController,
                  focusNode: inputFocusNode,
                  onSend: onSend,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MediaAssistantMessageBubble extends StatelessWidget {
  const _MediaAssistantMessageBubble({
    required this.isDark,
    required this.message,
    required this.onAssistantAvatarTap,
  });

  final bool isDark;
  final AssistantChatMessage message;
  final VoidCallback? onAssistantAvatarTap;

  @override
  Widget build(BuildContext context) {
    final messageKind = message.kind ?? 'text';
    final bubbleSelf = AppColors.chatBubbleOutgoing;
    final bubbleOther = AppColors.chatBubbleIncoming;
    final fgPrimary = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final isSelf = message.isSelf;
    final bubbleColor = isSelf ? bubbleSelf : bubbleOther;
    final textColor = isSelf ? AppColors.white : fgPrimary;
    final align = isSelf ? CrossAxisAlignment.end : CrossAxisAlignment.start;

    final selfAvatarUrl = _getSelfAvatarUrl(context);
    return Padding(
      padding: EdgeInsets.symmetric(
        vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: isSelf ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isSelf)
            Padding(
              padding: EdgeInsets.only(right: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
              child: AssistantAvatar(
                radius: AppSpacing.iconMedium,
                onTap: onAssistantAvatarTap,
              ),
            ),
          Flexible(
            child: Column(
              crossAxisAlignment: align,
              children: [
                if (messageKind == 'summary_cards')
                  _MediaAssistantSummaryCards(
                    isDark: isDark,
                    message: message,
                  )
                else
                  Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
                      vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
                    ),
                    decoration: BoxDecoration(
                      color: bubbleColor,
                      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                      boxShadow: [
                        BoxShadow(
                          color: AppColors.black.withValues(alpha: 0.08),
                          blurRadius: AppSpacing.sm,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Text(
                      message.text,
                      style: TextStyle(
                        color: textColor,
                        fontSize: AppTypography.base.sp,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          if (isSelf)
            Padding(
              padding: EdgeInsets.only(left: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
              child: CircleAvatar(
                radius: AppSpacing.iconMedium,
                backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                backgroundImage:
                    selfAvatarUrl != null ? NetworkImage(selfAvatarUrl) : null,
                child: selfAvatarUrl == null
                    ? Icon(
                        Icons.person,
                        size: AppSpacing.iconSmall,
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                      )
                    : null,
              ),
            ),
        ],
      ),
    );
  }

  String? _getSelfAvatarUrl(BuildContext context) {
    final user = ProviderScope.containerOf(context).read(userDataProvider);
    return user?.avatarUrlOrAvatar;
  }
}

class _MediaAssistantSummaryCards extends StatelessWidget {
  const _MediaAssistantSummaryCards({
    required this.isDark,
    required this.message,
  });

  final bool isDark;
  final AssistantChatMessage message;

  @override
  Widget build(BuildContext context) {
    final cards = message.cards ?? [];
    final summaryText = message.text.trim();
    final fgPrimary = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final cardBg = AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (summaryText.isNotEmpty)
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
              vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
            ),
            decoration: BoxDecoration(
              color: cardBg,
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              border: Border.all(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
                    .withValues(alpha: 0.2),
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.black.withValues(alpha: 0.08),
                  blurRadius: AppSpacing.sm,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: Text(
              summaryText,
              style: TextStyle(
                color: fgPrimary,
                fontSize: AppTypography.base.sp,
              ),
            ),
          ),
        if (summaryText.isNotEmpty)
          SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
        ...cards.map(
          (card) => Padding(
            padding: EdgeInsets.only(bottom: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
                vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
              ),
              decoration: BoxDecoration(
                color: cardBg,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                border: Border.all(
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
                      .withValues(alpha: 0.2),
                ),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.black.withValues(alpha: 0.08),
                    blurRadius: AppSpacing.sm,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    card.title,
                    style: TextStyle(
                      color: fgPrimary,
                      fontSize: AppTypography.base.sp,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
                  Text(
                    card.body,
                    style: TextStyle(
                      color: fgSecondary,
                      fontSize: AppTypography.sm.sp,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _MediaSuggestionChip extends StatelessWidget {
  const _MediaSuggestionChip({
    required this.isDark,
    required this.text,
    required this.onTap,
  });

  final bool isDark;
  final String text;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
        vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
              .withValues(alpha: 0.2),
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.08),
            blurRadius: AppSpacing.sm,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: context.safeGetIntraGroupSpacing(SpacingSize.xs),
            vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
          ),
          child: Text(
            text,
            style: TextStyle(
              fontSize: AppTypography.sm.sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
            ),
          ),
        ),
      ),
    );
  }
}

class _MediaAssistantInput extends StatelessWidget {
  const _MediaAssistantInput({
    required this.isDark,
    required this.controller,
    required this.focusNode,
    required this.onSend,
  });

  final bool isDark;
  final TextEditingController controller;
  final FocusNode focusNode;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Container(
            padding: EdgeInsets.symmetric(
              horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
              vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
            ),
            decoration: BoxDecoration(
              color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              border: Border.all(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
                    .withValues(alpha: 0.2),
              ),
              boxShadow: [
                BoxShadow(
                  color: AppColors.black.withValues(alpha: 0.08),
                  blurRadius: AppSpacing.sm,
                  offset: const Offset(0, 2),
                ),
              ],
            ),
            child: CupertinoTextField(
              controller: controller,
              focusNode: focusNode,
              decoration: BoxDecoration(
                color: Colors.transparent,
              ),
              placeholder: UITextConstants.assistantAskPlaceholder,
              placeholderStyle: TextStyle(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                fontSize: AppTypography.sm.sp,
              ),
              style: TextStyle(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                fontSize: AppTypography.sm.sp,
              ),
              onSubmitted: (_) => onSend(),
            ),
          ),
        ),
        SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
        Container(
          decoration: BoxDecoration(
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
            borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
            border: Border.all(
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary)
                  .withValues(alpha: 0.2),
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.black.withValues(alpha: 0.08),
                blurRadius: AppSpacing.sm,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            minSize: AppSpacing.minInteractiveSize,
            onPressed: onSend,
            child: Padding(
              padding: EdgeInsets.all(context.safeGetIntraGroupSpacing(SpacingSize.xs)),
              child: Icon(
                CupertinoIcons.arrow_up_circle_fill,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                size: AppSpacing.iconMedium,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
