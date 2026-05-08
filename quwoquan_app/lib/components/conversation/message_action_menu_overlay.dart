import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/chat/models/message_dto.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// Shared long-press action menu for conversation messages.
class ConversationMessageActionMenuOverlay extends StatelessWidget {
  const ConversationMessageActionMenuOverlay({
    super.key,
    required this.message,
    required this.position,
    required this.onAction,
    required this.onClose,
  });

  final ChatMessageDisplayItem message;
  final Offset position;
  final void Function(String action) onAction;
  final VoidCallback onClose;

  static const _recallWindowDuration = Duration(minutes: 2);

  Color _cupertinoColor(BuildContext context, CupertinoDynamicColor color) {
    return CupertinoDynamicColor.resolve(color, context);
  }

  Color _labelColor(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.label);

  Color _separatorColor(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.separator);

  Color _destructiveColor(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.systemRed);

  IconData _iconForAction(String action) {
    switch (action) {
      case 'forward':
        return Icons.share;
      case 'select':
        return Icons.check_box_outlined;
      case 'copy':
        return Icons.copy;
      case 'recall':
        return Icons.undo;
      case 'delete':
        return Icons.delete_outline;
      default:
        return Icons.more_horiz;
    }
  }

  static bool _isWithinRecallWindow(ChatMessageDisplayItem message) {
    if (message.sentAtIso.isNotEmpty) {
      final sentAt = DateTime.tryParse(message.sentAtIso);
      if (sentAt != null) {
        return DateTime.now().difference(sentAt) <= _recallWindowDuration;
      }
    }
    if (message.timestampLabel.isNotEmpty) {
      final parsed = DateTime.tryParse(message.timestampLabel);
      if (parsed != null) {
        return DateTime.now().difference(parsed) <= _recallWindowDuration;
      }
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    final type = message.type;
    final isSelf = message.isSelf;
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
          child: Container(
            width: menuWidth,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              boxShadow: [
                BoxShadow(
                  color: AppColors.black.withValues(alpha: 0.2),
                  blurRadius: AppSpacing.sm * 2,
                  offset: Offset(0, AppSpacing.xs),
                ),
              ],
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
              child: SizedBox(
                width: menuWidth,
                child: CupertinoPopupSurface(
                  isSurfacePainted: true,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: actions.asMap().entries.map((indexedEntry) {
                      final index = indexedEntry.key;
                      final entry = indexedEntry.value;
                      final isDelete = entry.key == 'delete';
                      final foreground = isDelete
                          ? _destructiveColor(context)
                          : _labelColor(context);
                      return DecoratedBox(
                        decoration: BoxDecoration(
                          border: index == 0
                              ? null
                              : Border(
                                  top: BorderSide(
                                    color: _separatorColor(
                                      context,
                                    ).withValues(alpha: 0.32),
                                  ),
                                ),
                        ),
                        child: CupertinoButton(
                          padding: EdgeInsets.symmetric(
                            horizontal:
                                AppSpacing.semantic[DesignSemanticConstants
                                    .container]?[DesignSemanticConstants.md] ??
                                AppSpacing.containerMd,
                            vertical: AppSpacing.containerSm,
                          ),
                          minimumSize: const Size(
                            0,
                            AppSpacing.minInteractiveSize,
                          ),
                          borderRadius: BorderRadius.zero,
                          alignment: Alignment.centerLeft,
                          onPressed: () {
                            onAction(entry.key);
                            onClose();
                          },
                          child: Row(
                            children: [
                              Icon(
                                _iconForAction(entry.key),
                                size: AppSpacing.iconMedium,
                                color: foreground,
                              ),
                              SizedBox(width: AppSpacing.containerSm),
                              Text(
                                entry.value,
                                style: TextStyle(
                                  fontSize: AppTypography.base,
                                  fontWeight: FontWeight.w500,
                                  color: foreground,
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
          ),
        ),
      ],
    );
  }
}
