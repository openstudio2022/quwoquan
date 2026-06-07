import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

class CommentThreadView extends ConsumerStatefulWidget {
  const CommentThreadView({
    super.key,
    required this.postId,
    this.scrollController,
    this.showHeader = true,
    this.onReplySelected,
    this.shrinkWrap = false,
  });

  final String postId;
  final ScrollController? scrollController;
  final bool showHeader;
  final ValueChanged<CommentDto>? onReplySelected;

  /// 平铺模式：列表用 `shrinkWrap + NeverScrollable`，随父滚动流展开，
  /// 不再要求外部给定有界高度（文章内容平铺评论区使用）。
  final bool shrinkWrap;

  @override
  ConsumerState<CommentThreadView> createState() => _CommentThreadViewState();
}

class _CommentThreadViewState extends ConsumerState<CommentThreadView> {
  late final ScrollController _scrollController;
  bool _ownsController = false;
  bool _initialLoaded = false;

  @override
  void initState() {
    super.initState();
    _scrollController = widget.scrollController ?? ScrollController();
    _ownsController = widget.scrollController == null;
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    if (_ownsController) {
      _scrollController.dispose();
    }
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - AppSpacing.xl) {
      ref.read(commentProviderFamily(widget.postId).notifier).loadMore();
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(commentProviderFamily(widget.postId));
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    if (!_initialLoaded) {
      _initialLoaded = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref
            .read(commentObservabilityProvider)
            .trackAction(
              eventName: CommentEventNames.surfaceExpose,
              postId: widget.postId,
              surfaceMode: widget.showHeader ? 'thread' : 'embedded',
            );
        ref.read(commentProviderFamily(widget.postId).notifier).loadComments();
      });
    }
    return Column(
      key: TestKeys.commentThreadView,
      children: [
        if (widget.showHeader)
          _CommentThreadHeader(
            isDark: isDark,
            commentCount: state.comments.length,
            sortMode: state.sortMode,
            onSortChanged: (mode) => ref
                .read(commentProviderFamily(widget.postId).notifier)
                .switchSort(mode),
          ),
        if (state.hasNewComments)
          _NewCommentsNotice(
            isRefreshing: state.isRefreshing,
            onTap: () => ref
                .read(commentProviderFamily(widget.postId).notifier)
                .refreshFromNewCommentNotice(),
          ),
        if (widget.shrinkWrap)
          _buildBody(context, state, isDark)
        else
          Expanded(child: _buildBody(context, state, isDark)),
      ],
    );
  }

  Widget _buildBody(BuildContext context, CommentState state, bool isDark) {
    if (state.isLoading && state.comments.isEmpty) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.xl),
        child: const Center(child: CupertinoActivityIndicator()),
      );
    }
    if (state.status == CommentListStatus.error && state.comments.isEmpty) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: AppSectionErrorCard(
            semantic: UiErrorSemantic(
              category: UiErrorCategory.sectionLoad,
              scope: UiErrorScope.section,
              title: UITextConstants.contentLoadSoftFailed,
              message:
                  state.errorMessage ?? UITextConstants.contentLoadSoftFailed,
              primaryAction: const UiErrorAction(
                type: UiErrorActionType.retry,
                label: UITextConstants.tryAgain,
              ),
            ),
            margin: EdgeInsets.zero,
            onAction: (_) async {
              await ref
                  .read(commentProviderFamily(widget.postId).notifier)
                  .loadComments();
            },
          ),
        ),
      );
    }
    if (state.comments.isEmpty) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.xl),
        child: Center(
          child: Text(
            UITextConstants.noComment,
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundSecondary,
              ),
            ),
          ),
        ),
      );
    }
    return ListView.builder(
      controller: widget.shrinkWrap ? null : _scrollController,
      shrinkWrap: widget.shrinkWrap,
      // ignore: deprecated_member_use
      cacheExtent: AppSpacing.commentListCacheExtent,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
      physics: widget.shrinkWrap
          ? const NeverScrollableScrollPhysics()
          : const BouncingScrollPhysics(),
      itemCount:
          state.comments.length +
          (state.status == CommentListStatus.loadingMore ? 1 : 0),
      itemBuilder: (context, index) {
        if (index >= state.comments.length) {
          return Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: const Center(child: CupertinoActivityIndicator()),
          );
        }
        final comment = state.comments[index];
        return _CommentThreadItem(
          postId: widget.postId,
          comment: comment,
          isDark: isDark,
          loadingReplies: state.loadingReplyCommentIds.contains(comment.id),
          onReplySelected: widget.onReplySelected,
        );
      },
    );
  }
}

class _NewCommentsNotice extends StatelessWidget {
  const _NewCommentsNotice({required this.isRefreshing, required this.onTap});

  final bool isRefreshing;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.xs,
      ),
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        color: AppColors.primaryColor.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
        onPressed: isRefreshing ? null : onTap,
        child: isRefreshing
            ? const CupertinoActivityIndicator()
            : Text(
                UITextConstants.commentNewCommentsNotice,
                style: TextStyle(
                  color: AppColors.primaryColor,
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
      ),
    );
  }
}

class _CommentThreadHeader extends StatelessWidget {
  const _CommentThreadHeader({
    required this.isDark,
    required this.commentCount,
    required this.sortMode,
    required this.onSortChanged,
  });

  final bool isDark;
  final int commentCount;
  final CommentSortMode sortMode;
  final ValueChanged<CommentSortMode> onSortChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          Text(
            '${UITextConstants.comment}${commentCount > 0 ? " $commentCount" : ""}',
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundPrimary,
              ),
            ),
          ),
          const Spacer(),
          _SortChip(
            label: UITextConstants.commentSortRecommended,
            mode: CommentSortMode.recommended,
            activeMode: sortMode,
            isDark: isDark,
            onChanged: onSortChanged,
          ),
          SizedBox(width: AppSpacing.xs),
          _SortChip(
            label: UITextConstants.circleSortLatest,
            mode: CommentSortMode.latest,
            activeMode: sortMode,
            isDark: isDark,
            onChanged: onSortChanged,
          ),
          SizedBox(width: AppSpacing.xs),
          _SortChip(
            label: UITextConstants.commentSortMostLiked,
            mode: CommentSortMode.mostLiked,
            activeMode: sortMode,
            isDark: isDark,
            onChanged: onSortChanged,
          ),
        ],
      ),
    );
  }
}

class _SortChip extends StatelessWidget {
  const _SortChip({
    required this.label,
    required this.mode,
    required this.activeMode,
    required this.isDark,
    required this.onChanged,
  });

  final String label;
  final CommentSortMode mode;
  final CommentSortMode activeMode;
  final bool isDark;
  final ValueChanged<CommentSortMode> onChanged;

  @override
  Widget build(BuildContext context) {
    final isActive = mode == activeMode;
    return GestureDetector(
      onTap: () => onChanged(mode),
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: isActive
              ? AppColors.primaryColor.withValues(alpha: 0.1)
              : AppColors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.xs,
            color: isActive
                ? AppColors.primaryColor
                : AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundSecondary,
                  ),
            fontWeight: isActive ? AppTypography.semiBold : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}

class _CommentThreadItem extends ConsumerWidget {
  const _CommentThreadItem({
    required this.postId,
    required this.comment,
    required this.isDark,
    required this.loadingReplies,
    this.onReplySelected,
  });

  final String postId;
  final CommentDto comment;
  final bool isDark;
  final bool loadingReplies;
  final ValueChanged<CommentDto>? onReplySelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              RoundedSquareAvatar(
                size: AppSpacing.iconMedium,
                imageUrl: comment.avatarUrl,
                name: comment.displayName,
                borderRadius: AppSpacing.iconMedium / 2,
                backgroundColor: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.backgroundSecondary,
                ),
                fallbackIcon: CupertinoIcons.person_fill,
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(child: _buildContent(context, ref)),
            ],
          ),
          if (comment.replyPreview.isNotEmpty || comment.replyCount > 0)
            Padding(
              padding: EdgeInsets.only(
                left: AppSpacing.iconMedium + AppSpacing.sm,
                top: AppSpacing.sm,
              ),
              child: _buildReplies(context, ref),
            ),
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context, WidgetRef ref) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                comment.displayName ?? comment.authorId,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundSecondary,
                  ),
                  fontWeight: AppTypography.medium,
                ),
              ),
            ),
            if (comment.isAuthor)
              _Badge(label: UITextConstants.commentAuthorBadge, isDark: isDark),
          ],
        ),
        SizedBox(height: AppSpacing.xs),
        Text(
          comment.content,
          style: TextStyle(
            fontSize: AppTypography.sm,
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundPrimary,
            ),
          ),
        ),
        if (comment.attachments.isNotEmpty) ...[
          SizedBox(height: AppSpacing.xs),
          Wrap(
            spacing: AppSpacing.xs,
            children: comment.attachments
                .map((attachment) {
                  final thumbnailUrl =
                      (attachment['thumbnailUrl'] ?? attachment['url'])
                          ?.toString();
                  return Container(
                    width: AppSpacing.xl,
                    height: AppSpacing.xl,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: AppColors.primaryColor.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.smallBorderRadius,
                      ),
                    ),
                    clipBehavior: Clip.antiAlias,
                    child: thumbnailUrl == null || thumbnailUrl.isEmpty
                        ? const Icon(CupertinoIcons.photo)
                        : Image.network(
                            thumbnailUrl,
                            width: AppSpacing.xl,
                            height: AppSpacing.xl,
                            fit: BoxFit.cover,
                            filterQuality: FilterQuality.low,
                            cacheWidth: 96,
                            errorBuilder: (context, error, stackTrace) =>
                                const Icon(CupertinoIcons.photo),
                          ),
                  );
                })
                .toList(growable: false),
          ),
        ],
        SizedBox(height: AppSpacing.xs),
        _CommentActions(
          comment: comment,
          isDark: isDark,
          onReply: comment.canReply
              ? () => onReplySelected?.call(comment)
              : null,
          onLike: () => runWhenLoggedIn(ref, context, AuthGateReason.like, () {
            ref
                .read(commentProviderFamily(postId).notifier)
                .toggleLike(comment.id);
          }),
          onDislike: () =>
              runWhenLoggedIn(ref, context, AuthGateReason.like, () {
                ref
                    .read(commentProviderFamily(postId).notifier)
                    .toggleDislike(comment.id);
              }),
          onDelete: comment.canDelete
              ? () => ref
                    .read(commentProviderFamily(postId).notifier)
                    .deleteComment(comment.id)
              : null,
          onReport: comment.canReport
              ? () => runWhenLoggedIn(ref, context, AuthGateReason.like, () {
                  ref
                      .read(commentObservabilityProvider)
                      .trackAction(
                        eventName: CommentEventNames.reported,
                        postId: postId,
                        commentId: comment.id,
                      );
                  AppToast.show(
                    context,
                    UITextConstants.commentReportSubmitted,
                  );
                })
              : null,
        ),
      ],
    );
  }

  Widget _buildReplies(BuildContext context, WidgetRef ref) {
    final remaining = comment.replyCount - comment.replyPreview.length;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ...comment.replyPreview.map(
          (reply) => Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.xs),
            child: _ReplyPreviewItem(
              postId: postId,
              reply: reply,
              isDark: isDark,
              onReplySelected: onReplySelected,
            ),
          ),
        ),
        if (comment.replyNextCursor != null && remaining > 0)
          GestureDetector(
            onTap: loadingReplies
                ? null
                : () => ref
                      .read(commentProviderFamily(postId).notifier)
                      .expandReplies(comment.id),
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.xs),
              child: loadingReplies
                  ? const CupertinoActivityIndicator()
                  : Text(
                      context.l10n.expandRepliesTemplate(remaining),
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        color: AppColors.primaryColor,
                      ),
                    ),
            ),
          ),
      ],
    );
  }
}

class _ReplyPreviewItem extends ConsumerWidget {
  const _ReplyPreviewItem({
    required this.postId,
    required this.reply,
    required this.isDark,
    this.onReplySelected,
  });

  final String postId;
  final CommentDto reply;
  final bool isDark;
  final ValueChanged<CommentDto>? onReplySelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        RoundedSquareAvatar(
          size: AppSpacing.iconSmall,
          imageUrl: reply.avatarUrl,
          name: reply.displayName,
          borderRadius: AppSpacing.iconSmall / 2,
          backgroundColor: AppColorsFunctional.getColor(
            isDark,
            ColorType.backgroundSecondary,
          ),
          fallbackIcon: CupertinoIcons.person_fill,
        ),
        SizedBox(width: AppSpacing.xs),
        Expanded(
          child: GestureDetector(
            onTap: () => onReplySelected?.call(reply),
            child: Text(
              '${reply.displayName ?? reply.authorId}：${reply.content}',
              style: TextStyle(fontSize: AppTypography.xs),
            ),
          ),
        ),
        _ReactionIconButton(
          selected: reply.viewerReaction == 'like',
          icon: CupertinoIcons.heart,
          selectedIcon: CupertinoIcons.heart_fill,
          count: reply.likeCount,
          onTap: () => ref
              .read(commentProviderFamily(postId).notifier)
              .toggleLike(reply.id),
        ),
      ],
    );
  }
}

class _CommentActions extends StatelessWidget {
  const _CommentActions({
    required this.comment,
    required this.isDark,
    required this.onLike,
    required this.onDislike,
    this.onReply,
    this.onDelete,
    this.onReport,
  });

  final CommentDto comment;
  final bool isDark;
  final VoidCallback onLike;
  final VoidCallback onDislike;
  final VoidCallback? onReply;
  final VoidCallback? onDelete;
  final VoidCallback? onReport;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(
          _formatTime(context, comment.createdAt),
          style: TextStyle(
            fontSize: AppTypography.xs,
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundTertiary,
            ),
          ),
        ),
        if (onReply != null) ...[
          SizedBox(width: AppSpacing.md),
          GestureDetector(
            onTap: onReply,
            child: Text(
              UITextConstants.replyAction,
              style: TextStyle(
                fontSize: AppTypography.xs,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
              ),
            ),
          ),
        ],
        const Spacer(),
        _ReactionIconButton(
          selected: comment.viewerReaction == 'like',
          icon: CupertinoIcons.heart,
          selectedIcon: CupertinoIcons.heart_fill,
          count: comment.likeCount,
          onTap: onLike,
        ),
        SizedBox(width: AppSpacing.sm),
        _ReactionIconButton(
          selected: comment.viewerReaction == 'dislike',
          icon: CupertinoIcons.hand_thumbsdown,
          selectedIcon: CupertinoIcons.hand_thumbsdown_fill,
          count: comment.dislikeCount,
          onTap: onDislike,
        ),
        if (onDelete != null) ...[
          SizedBox(width: AppSpacing.md),
          GestureDetector(
            onTap: onDelete,
            child: Icon(
              CupertinoIcons.trash,
              size: AppSpacing.iconSmall,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundTertiary,
              ),
            ),
          ),
        ],
        if (onReport != null) ...[
          SizedBox(width: AppSpacing.md),
          GestureDetector(
            onTap: onReport,
            child: Icon(
              CupertinoIcons.flag,
              size: AppSpacing.iconSmall,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundTertiary,
              ),
            ),
          ),
        ],
      ],
    );
  }

  String _formatTime(BuildContext context, DateTime time) {
    final l10n = context.l10n;
    final diff = DateTime.now().difference(time);
    if (diff.inMinutes < 1) return l10n.justNow;
    if (diff.inHours < 1) return l10n.minutesAgoTemplate(diff.inMinutes);
    if (diff.inDays < 1) return l10n.hoursAgoTemplate(diff.inHours);
    if (diff.inDays < 30) return l10n.daysAgoTemplate(diff.inDays);
    return l10n.monthDayTemplate(time.month, time.day);
  }
}

class _ReactionIconButton extends StatelessWidget {
  const _ReactionIconButton({
    required this.selected,
    required this.icon,
    required this.selectedIcon,
    required this.count,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final IconData selectedIcon;
  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return GestureDetector(
      onTap: onTap,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            selected ? selectedIcon : icon,
            size: AppSpacing.iconSmall,
            color: selected
                ? AppColors.error
                : AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundTertiary,
                  ),
          ),
          if (count > 0) ...[
            SizedBox(width: AppSpacing.xs),
            Text(
              '$count',
              style: TextStyle(
                fontSize: AppTypography.xs,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundTertiary,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.isDark});

  final String label;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.xs,
        vertical: AppSpacing.one,
      ),
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.xs,
          color: AppColors.primaryColor,
        ),
      ),
    );
  }
}
