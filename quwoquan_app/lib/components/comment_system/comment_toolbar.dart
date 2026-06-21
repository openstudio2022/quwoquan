import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';

/// 评论贴底工具栏（对标小红书底栏）。
///
/// 左侧是圆角只读「添加评论…」输入条，点击触发统一评论输入浮层；右侧依次为
/// 「点赞 + 计数」「转发 + 计数」两组动作（内容互动只保留 赞/评/转，评论入口已由
/// 左侧输入条承载，故底栏不再出现独立的评论计数按钮）。
/// 计数与状态由宿主从 `postInteractionStateProvider` 实时下发，工具栏只负责展示与回调。
class CommentToolbar extends StatelessWidget {
  const CommentToolbar({
    super.key,
    required this.likeCount,
    required this.shareCount,
    this.isLiked = false,
    this.isShared = false,
    this.placeholder = UITextConstants.commentPlaceholder,
    this.onInputTap,
    this.onLikeTap,
    this.onShareTap,
  });

  final int likeCount;
  final int shareCount;
  final bool isLiked;
  final bool isShared;
  final String placeholder;
  final VoidCallback? onInputTap;
  final VoidCallback? onLikeTap;
  final VoidCallback? onShareTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return Container(
      key: TestKeys.commentToolbar,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.commentToolbarVerticalPadding,
        AppSpacing.md,
        AppSpacing.commentToolbarVerticalPadding +
            MediaQuery.viewPaddingOf(context).bottom,
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundPrimary,
        ),
        border: Border(
          top: BorderSide(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.borderPrimary,
            ),
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
                key: TestKeys.commentInputCapsule,
                height: AppSpacing.commentToolbarInputHeight,
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                alignment: Alignment.centerLeft,
                decoration: BoxDecoration(
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.backgroundSecondary,
                  ),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.commentToolbarInputRadius,
                  ),
                  border: Border.all(
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.borderSecondary,
                    ),
                    width: AppSpacing.hairline,
                  ),
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
            zeroLabel: UITextConstants.interactionSubLikes,
            active: isLiked,
            activeColor: AppColors.error,
            onTap: onLikeTap,
          ),
          SizedBox(width: AppSpacing.xs),
          _CountAction(
            buttonKey: TestKeys.shareButton,
            icon: isShared
                ? CupertinoIcons.arrowshape_turn_up_right_fill
                : CupertinoIcons.arrowshape_turn_up_right,
            count: shareCount,
            zeroLabel: UITextConstants.interactionSubShares,
            active: isShared,
            onTap: onShareTap,
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
    required this.zeroLabel,
    this.active = false,
    this.activeColor,
    this.onTap,
  });

  final Key buttonKey;
  final IconData icon;
  final int count;
  final String zeroLabel;
  final bool active;
  final Color? activeColor;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final labelColor = active
        ? (activeColor ?? AppColors.primaryColor)
        : AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return CupertinoButton(
      key: buttonKey,
      padding: EdgeInsets.zero,
      minimumSize: const Size(
        AppSpacing.commentToolbarActionColumnWidth,
        AppSpacing.commentToolbarActionHitSize,
      ),
      onPressed: onTap,
      child: SizedBox(
        width: AppSpacing.commentToolbarActionColumnWidth,
        height: AppSpacing.commentToolbarActionHitSize,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Icon(
              icon,
              size: AppSpacing.commentToolbarActionIconSize,
              color: active
                  ? (activeColor ?? AppColors.primaryColor)
                  : AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundSecondary,
                    ),
            ),
            SizedBox(width: AppSpacing.xs),
            SizedBox(
              width: AppSpacing.commentReactionCountWidth,
              child: Text(
                count > 0 ? formatCompactActionCount(count) : zeroLabel,
                maxLines: 1,
                overflow: TextOverflow.clip,
                style: TextStyle(fontSize: AppTypography.sm, color: labelColor),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
