import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/regenerate_options_popup.dart';

/// Bottom toolbar for assistant answers — like / dislike / copy / share / regenerate.
///
/// Regenerate is positioned on the far right and shows a popup with options
/// (regenerate, concise, detailed, casual, deep think) above the button.
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
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final iconColor = isDark
        ? const Color(0xFF98989F)
        : const Color(0xFF8E8E93);
    final activeColor = isDark
        ? const Color(0xFF64D2FF)
        : const Color(0xFF007AFF);

    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.xs),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _ToolbarIcon(
            icon: feedbackStatus == 'helpful'
                ? CupertinoIcons.hand_thumbsup_fill
                : CupertinoIcons.hand_thumbsup,
            color: feedbackStatus == 'helpful' ? activeColor : iconColor,
            onTap: onFeedbackHelpful,
            semanticLabel: '有帮助',
          ),
          _ToolbarIcon(
            icon: feedbackStatus == 'unhelpful'
                ? CupertinoIcons.hand_thumbsdown_fill
                : CupertinoIcons.hand_thumbsdown,
            color: feedbackStatus == 'unhelpful' ? activeColor : iconColor,
            onTap: onFeedbackUnhelpful,
            semanticLabel: '没帮助',
          ),
          _ToolbarIcon(
            icon: CupertinoIcons.doc_on_doc,
            color: iconColor,
            onTap: onCopyAnswer,
            semanticLabel: '复制',
          ),
          _ToolbarIcon(
            icon: CupertinoIcons.arrowshape_turn_up_right,
            color: iconColor,
            onTap: onShareAnswer,
            semanticLabel: '转发',
          ),
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
        padding: const EdgeInsets.all(4),
        child: Icon(
          icon,
          size: 18,
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
        padding: const EdgeInsets.all(4),
        child: Icon(
          CupertinoIcons.arrow_2_circlepath,
          size: 18,
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
      barrierColor: Colors.transparent,
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
