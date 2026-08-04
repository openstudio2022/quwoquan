import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/presentation/regenerate_options_popup.dart';

class AssistantAnswerToolbar extends StatelessWidget {
  const AssistantAnswerToolbar({
    super.key,
    required this.feedbackStatus,
    this.onFeedbackHelpful,
    this.onFeedbackUnhelpful,
    this.onCopyAnswer,
    this.onShareAnswer,
    this.onRegenerateSelected,
  });

  final String feedbackStatus;
  final VoidCallback? onFeedbackHelpful;
  final VoidCallback? onFeedbackUnhelpful;
  final VoidCallback? onCopyAnswer;
  final VoidCallback? onShareAnswer;
  final void Function(RegenerateOption option)? onRegenerateSelected;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final iconColor = isDark
        ? AppColors.iosToolbarSecondaryIconDark
        : AppColors.iosToolbarSecondaryIconLight;
    final activeColor = isDark
        ? AppColors.iosSystemCyanAccent
        : AppColors.primaryColor;

    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.xs),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        children: [
          _ToolbarIcon(
            icon: feedbackStatus == 'useful'
                ? CupertinoIcons.hand_thumbsup_fill
                : CupertinoIcons.hand_thumbsup,
            color: feedbackStatus == 'useful' ? activeColor : iconColor,
            onTap: onFeedbackHelpful,
            semanticLabel: AssistantText.assistantFeedbackHelpful,
          ),
          SizedBox(width: AppSpacing.intraGroupMd),
          _ToolbarIcon(
            icon: feedbackStatus == 'irrelevant'
                ? CupertinoIcons.hand_thumbsdown_fill
                : CupertinoIcons.hand_thumbsdown,
            color: feedbackStatus == 'irrelevant' ? activeColor : iconColor,
            onTap: onFeedbackUnhelpful,
            semanticLabel: AssistantText.assistantFeedbackUnhelpful,
          ),
          SizedBox(width: AppSpacing.intraGroupMd),
          _ToolbarIcon(
            icon: CupertinoIcons.doc_on_doc,
            color: iconColor,
            onTap: onCopyAnswer,
            semanticLabel: ChatText.messageActionCopy,
          ),
          SizedBox(width: AppSpacing.intraGroupMd),
          _ToolbarIcon(
            icon: CupertinoIcons.arrowshape_turn_up_right,
            color: iconColor,
            onTap: onShareAnswer,
            semanticLabel: ChatText.messageActionForward,
          ),
          SizedBox(width: AppSpacing.intraGroupMd),
          _RegenerateButton(
            iconColor: iconColor,
            onSelected: onRegenerateSelected,
          ),
        ],
      ),
    );
  }
}

class _ToolbarIcon extends StatelessWidget {
  const _ToolbarIcon({
    required this.icon,
    required this.color,
    this.onTap,
    this.semanticLabel = '',
  });

  final IconData icon;
  final Color color;
  final VoidCallback? onTap;
  final String semanticLabel;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.xs),
        child: Icon(
          icon,
          size: AppSpacing.eighteen,
          color: color,
          semanticLabel: semanticLabel,
        ),
      ),
    );
  }
}

class _RegenerateButton extends StatelessWidget {
  const _RegenerateButton({required this.iconColor, this.onSelected});

  final Color iconColor;
  final void Function(RegenerateOption option)? onSelected;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _showPopup(context),
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.xs),
        child: Icon(
          CupertinoIcons.arrow_2_circlepath,
          size: AppSpacing.eighteen,
          color: iconColor,
        ),
      ),
    );
  }

  void _showPopup(BuildContext context) {
    final renderBox = context.findRenderObject() as RenderBox?;
    if (renderBox == null) return;
    final offset = renderBox.localToGlobal(Offset.zero);
    final size = renderBox.size;

    showAppFloatingModal<void>(
      context: context,
      builder: (ctx) {
        return RegenerateOptionsPopup(
          anchorRect: Rect.fromLTWH(
            offset.dx,
            offset.dy,
            size.width,
            size.height,
          ),
          onSelected: (option) {
            Navigator.of(ctx).pop();
            onSelected?.call(option);
          },
        );
      },
      transitionDuration: const Duration(milliseconds: 200),
    );
  }
}
