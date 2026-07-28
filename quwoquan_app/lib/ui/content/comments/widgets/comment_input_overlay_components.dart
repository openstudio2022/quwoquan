part of 'comment_input_overlay.dart';

/// 评论输入浮层的无业务状态视图组件与配置投影。
///
/// 草稿、附件、登录续接和提交状态仍唯一归属 [_CommentInputSheetState]。
CommentConfig _resolveComposerConfig(
  CommentRemoteConfig remote,
  CommentConfig fallback,
) {
  return CommentConfig(
    maxLength: remote.maxLength > 0 ? remote.maxLength : fallback.maxLength,
    maxImageAttachments: remote.maxImageAttachments > 0
        ? remote.maxImageAttachments
        : fallback.maxImageAttachments,
    enabled: remote.enabled && fallback.enabled,
  );
}

class _ReplyIndicator extends StatelessWidget {
  const _ReplyIndicator({
    required this.isDark,
    required this.username,
    required this.onCancel,
  });

  final bool isDark;
  final String username;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.md,
        0,
      ),
      child: Row(
        children: [
          Icon(
            CupertinoIcons.arrowshape_turn_up_left,
            size: AppSpacing.iconSmall,
            color: AppColors.primaryColor,
          ),
          SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Text(
              '${ContentText.replyAction} @$username',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColors.primaryColor,
              ),
            ),
          ),
          GestureDetector(
            onTap: onCancel,
            child: Icon(
              CupertinoIcons.xmark,
              size: AppSpacing.iconSmall,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundTertiary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ToolIcon extends StatelessWidget {
  const _ToolIcon({
    super.key,
    required this.icon,
    required this.isDark,
    required this.semanticLabel,
    this.onTap,
    this.active = false,
    this.busy = false,
  });

  final IconData icon;
  final bool isDark;
  final String semanticLabel;
  final VoidCallback? onTap;
  final bool active;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: SizedBox(
        width: AppSpacing.minInteractiveSize,
        height: AppSpacing.minInteractiveSize,
        child: Center(
          child: busy
              ? AppRequestFeedback.inline()
              : Icon(
                  icon,
                  size: AppSpacing.appChromeActionIconSize,
                  semanticLabel: semanticLabel,
                  color: active
                      ? AppColors.primaryColor
                      : AppColorsFunctional.getColor(
                          isDark,
                          ColorType.foregroundSecondary,
                        ),
                ),
        ),
      ),
    );
  }
}

class _SendButton extends StatelessWidget {
  const _SendButton({required this.canSend, this.onTap});

  final bool canSend;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      key: TestKeys.submitCommentButton,
      padding: EdgeInsets.zero,
      minimumSize: const Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: canSend
              ? AppColors.primaryColor
              : AppColors.primaryColor.withValues(alpha: 0.4),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        ),
        child: Text(
          ContentText.commentSend,
          style: TextStyle(
            fontSize: AppTypography.body,
            fontWeight: AppTypography.semiBold,
            color: AppColors.white,
          ),
        ),
      ),
    );
  }
}

/// 输入框底部的单张图片缩略图（右上角可删除），形态参考主流评论输入。
class _AttachmentThumbnail extends StatelessWidget {
  const _AttachmentThumbnail({
    required this.mediaId,
    required this.isDark,
    required this.onRemove,
  });

  final String mediaId;
  final bool isDark;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final thumbnailUrl = 'media/comment/$mediaId/v1/comment.png';
    return SizedBox(
      width: AppSpacing.commentAttachmentThumbnailSize,
      height: AppSpacing.commentAttachmentThumbnailSize,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
            child: Container(
              width: AppSpacing.commentAttachmentThumbnailSize,
              height: AppSpacing.commentAttachmentThumbnailSize,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.backgroundPrimary,
              ),
              alignment: Alignment.center,
              child: AppCachedNetworkImage(
                imageUrl: thumbnailUrl,
                fit: BoxFit.cover,
                width: AppSpacing.commentAttachmentThumbnailSize,
                height: AppSpacing.commentAttachmentThumbnailSize,
                cdnPreset: CdnImagePreset.thumbnail,
                errorWidget: Icon(
                  CupertinoIcons.photo,
                  size: AppSpacing.iconMedium,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundTertiary,
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            top: -AppSpacing.xs,
            right: -AppSpacing.xs,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onRemove,
              child: Container(
                decoration: const BoxDecoration(
                  color: AppColors.overlayStrong,
                  shape: BoxShape.circle,
                ),
                padding: EdgeInsets.all(AppSpacing.xs),
                child: Icon(
                  CupertinoIcons.xmark,
                  size: AppSpacing.iconXSmall,
                  color: AppColors.white,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 最近常用 emoji 横条（无最近记录时不展示）。
class _RecentEmojiStrip extends ConsumerWidget {
  const _RecentEmojiStrip({required this.isDark, required this.onSelected});

  final bool isDark;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final recent = ref
        .watch(emojiRepositoryProvider)
        .when(
          data: (repo) => repo.getRecentEntries(),
          loading: () => const <EmojiEntry>[],
          error: (_, _) => const <EmojiEntry>[],
        );
    if (recent.isEmpty) {
      return const SizedBox.shrink();
    }
    return SizedBox(
      key: TestKeys.commentRecentEmojiStrip,
      height: AppSpacing.commentComposerRecentEmojiHeight,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
        itemCount: recent.length,
        separatorBuilder: (_, _) => SizedBox(width: AppSpacing.sm),
        itemBuilder: (context, index) {
          final entry = recent[index];
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => onSelected(entry.char),
            child: Center(
              child: Text(
                entry.char,
                style: const TextStyle(fontSize: AppTypography.xxl),
              ),
            ),
          );
        },
      ),
    );
  }
}
