import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';

/// 评论贴底工具栏（图一）。
///
/// 左侧是圆角只读「说点什么…」输入条，点击触发统一评论输入浮层；右侧依次为
/// 点赞、评论两组「图标 + 计数」（内容只有 赞/评/转 三动作）。
/// 计数由宿主从 `postInteractionStateProvider` / 评论数实时下发，工具栏只负责展示与回调。
class CommentToolbar extends StatelessWidget {
  const CommentToolbar({
    super.key,
    required this.likeCount,
    required this.commentCount,
    this.isLiked = false,
    this.placeholder = UITextConstants.commentPlaceholder,
    this.onInputTap,
    this.onLikeTap,
    this.onCommentTap,
  });

  final int likeCount;
  final int commentCount;
  final bool isLiked;
  final String placeholder;
  final VoidCallback? onInputTap;
  final VoidCallback? onLikeTap;
  final VoidCallback? onCommentTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return Container(
      key: TestKeys.commentToolbar,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundPrimary,
        ),
        border: Border(
          top: BorderSide(
            color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: GestureDetector(
              key: TestKeys.commentInputBar,
              behavior: HitTestBehavior.opaque,
              onTap: onInputTap,
              child: Container(
                height: AppSpacing.commentInputHeight,
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                alignment: Alignment.centerLeft,
                decoration: BoxDecoration(
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.backgroundSecondary,
                  ),
                  borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                ),
                child: Row(
                  children: [
                    Icon(
                      CupertinoIcons.pencil,
                      size: AppSpacing.iconSmall,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.foregroundTertiary,
                      ),
                    ),
                    SizedBox(width: AppSpacing.xs),
                    Expanded(
                      child: Text(
                        placeholder,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundTertiary,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          SizedBox(width: AppSpacing.sm),
          _CountAction(
            buttonKey: TestKeys.likeButton,
            icon: isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
            count: likeCount,
            active: isLiked,
            activeColor: AppColors.error,
            onTap: onLikeTap,
          ),
          _CountAction(
            buttonKey: TestKeys.commentButton,
            icon: CupertinoIcons.chat_bubble,
            count: commentCount,
            onTap: onCommentTap,
          ),
        ],
      ),
    );
  }
}

class _CountAction extends StatelessWidget {
  const _CountAction({
    required this.buttonKey,
    required this.icon,
    required this.count,
    this.active = false,
    this.activeColor,
    this.onTap,
  });

  final Key buttonKey;
  final IconData icon;
  final int count;
  final bool active;
  final Color? activeColor;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return CupertinoButton(
      key: buttonKey,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: AppSpacing.appChromeActionIconSize,
            color: active
                ? (activeColor ?? AppColors.primaryColor)
                : AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundSecondary,
                  ),
          ),
          if (count > 0) ...[
            SizedBox(width: AppSpacing.xs),
            Text(
              '$count',
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
