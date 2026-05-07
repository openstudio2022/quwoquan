import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// Shared outer frame for conversation message renderers.
class MessageBubbleFrame extends StatelessWidget {
  const MessageBubbleFrame({
    super.key,
    required this.isRight,
    required this.hideAvatarAndName,
    required this.senderName,
    required this.textColor,
    required this.content,
    this.avatar,
  });

  final bool isRight;
  final bool hideAvatarAndName;
  final String senderName;
  final Color textColor;
  final Widget content;
  final Widget? avatar;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        mainAxisAlignment: isRight
            ? MainAxisAlignment.end
            : MainAxisAlignment.start,
        crossAxisAlignment: isRight
            ? CrossAxisAlignment.end
            : CrossAxisAlignment.start,
        children: <Widget>[
          if (!hideAvatarAndName && !isRight && avatar != null) avatar!,
          if (!hideAvatarAndName && !isRight && avatar != null)
            SizedBox(width: AppSpacing.sm),
          Flexible(
            child: DefaultTextStyle.merge(
              // 防御 Material/Cupertino 混合宿主把误装饰（黄下划线等）泄漏到会话气泡。
              style: const TextStyle(
                decoration: TextDecoration.none,
                decorationThickness: 0,
              ),
              child: Column(
                crossAxisAlignment: isRight
                    ? CrossAxisAlignment.end
                    : CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
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
                          fontSize: AppTypography.sm,
                          color: textColor.withValues(alpha: 0.8),
                        ),
                      ),
                    ),
                  content,
                ],
              ),
            ),
          ),
          if (!hideAvatarAndName && isRight && avatar != null)
            SizedBox(width: AppSpacing.sm),
          if (!hideAvatarAndName && isRight && avatar != null) avatar!,
        ],
      ),
    );
  }
}
