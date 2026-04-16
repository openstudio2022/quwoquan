import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/regenerate_options_popup.dart';

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
    final isDark =
        CupertinoTheme.of(context).brightness == Brightness.dark;
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
            icon: feedbackStatus == 'helpful'
                ? CupertinoIcons.hand_thumbsup_fill
                : CupertinoIcons.hand_thumbsup,
            color: feedbackStatus == 'helpful' ? activeColor : iconColor,
            onTap: onFeedbackHelpful,
            semanticLabel: '有帮助',
          ),
          SizedBox(width: AppSpacing.intraGroupMd),
          _ToolbarIcon(
            icon: feedbackStatus == 'unhelpful'
                ? CupertinoIcons.hand_thumbsdown_fill
                : CupertinoIcons.hand_thumbsdown,
            color: feedbackStatus == 'unhelpful' ? activeColor : iconColor,
            onTap: onFeedbackUnhelpful,
            semanticLabel: '没帮助',
          ),
          SizedBox(width: AppSpacing.intraGroupMd),
          _ToolbarIcon(
            icon: CupertinoIcons.doc_on_doc,
            color: iconColor,
            onTap: onCopyAnswer,
            semanticLabel: '复制',
          ),
          SizedBox(width: AppSpacing.intraGroupMd),
          _ToolbarIcon(
            icon: CupertinoIcons.arrowshape_turn_up_right,
            color: iconColor,
            onTap: onShareAnswer,
            semanticLabel: '转发',
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
  const _RegenerateButton({
    required this.iconColor,
    this.onSelected,
  });

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

    showGeneralDialog(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'dismiss',
      barrierColor: AppColors.transparent,
      pageBuilder: (ctx, anim1, anim2) {
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
      transitionBuilder: (ctx, anim1, anim2, child) {
        return FadeTransition(
          opacity: CurvedAnimation(parent: anim1, curve: Curves.easeOut),
          child: child,
        );
      },
      transitionDuration: const Duration(milliseconds: 200),
    );
  }
}
