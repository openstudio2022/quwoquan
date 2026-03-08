import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer.dart'
    show CommentInput;
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

class CommentViewer {
  static Future<void> showModal({
    required BuildContext context,
    required String postId,
    List<CommentModel> initialComments = const [],
    CommentConfig config = const CommentConfig(),
    CommentModalHeight modalHeight = CommentModalHeight.adaptive,
    Function(String)? onCommentAdded,
    Future<void> Function(String content)? onSubmitComment,
    Function(CommentModel)? onCommentLiked,
    Function(String, String)? onReplyAdded,
    Function(String)? onUserTapped,
    Function(String)? onLoadMoreComments,
    VoidCallback? onClose,
  }) async {
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _CommentSheet(
        postId: postId,
        config: config,
        onCommentAdded: onCommentAdded,
        onClose: onClose,
      ),
    );
  }
}

class _CommentSheet extends ConsumerStatefulWidget {
  final String postId;
  final CommentConfig config;
  final Function(String)? onCommentAdded;
  final VoidCallback? onClose;

  const _CommentSheet({
    required this.postId,
    required this.config,
    this.onCommentAdded,
    this.onClose,
  });

  @override
  ConsumerState<_CommentSheet> createState() => _CommentSheetState();
}

class _CommentSheetState extends ConsumerState<_CommentSheet> {
  CommentModel? _replyTo;
  final ScrollController _scrollController = ScrollController();
  bool _initialLoaded = false;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 200) {
      ref.read(commentProviderFamily(widget.postId).notifier).loadMore();
    }
  }

  @override
  Widget build(BuildContext context) {
    final commentState = ref.watch(commentProviderFamily(widget.postId));
    final isDark = Theme.of(context).brightness == Brightness.dark;

    if (!_initialLoaded) {
      _initialLoaded = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref
            .read(commentProviderFamily(widget.postId).notifier)
            .loadComments();
      });
    }

    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      builder: (ctx, scrollController) {
        return Container(
          decoration: BoxDecoration(
            color: AppColorsFunctional.getColor(
                isDark, ColorType.backgroundPrimary),
            borderRadius: BorderRadius.vertical(
              top: Radius.circular(AppSpacing.largeBorderRadius),
            ),
          ),
          child: Column(
            children: [
              _DragHandle(isDark: isDark),
              _Header(
                isDark: isDark,
                commentCount: commentState.comments.length,
                sortMode: commentState.sortMode,
                onSortChanged: (mode) {
                  ref
                      .read(commentProviderFamily(widget.postId).notifier)
                      .switchSort(mode);
                },
                onClose: () => Navigator.of(context).pop(),
              ),
              Expanded(
                child: _buildCommentList(commentState, isDark, scrollController),
              ),
              CommentInput(
                config: widget.config,
                replyTo: _replyTo,
                onSubmit: (content) async {
                  try {
                    final confirmed = await ref
                        .read(commentProviderFamily(widget.postId).notifier)
                        .addComment(
                          content,
                          replyToCommentId: _replyTo?.id,
                        );
                    if (confirmed != null) {
                      widget.onCommentAdded?.call(confirmed.id);
                    }
                    if (mounted) setState(() => _replyTo = null);
                  } catch (_) {}
                },
                onCancelReply: () {
                  setState(() => _replyTo = null);
                },
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildCommentList(
      CommentState state, bool isDark, ScrollController scrollController) {
    if (state.isLoading && state.comments.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (state.status == CommentListStatus.error && state.comments.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(CupertinoIcons.exclamationmark_circle,
                size: AppSpacing.iconLarge,
                color: AppColorsFunctional.getColor(
                    isDark, ColorType.foregroundTertiary)),
            SizedBox(height: AppSpacing.sm),
            Text(
              UITextConstants.loadFailed,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColorsFunctional.getColor(
                    isDark, ColorType.foregroundSecondary),
              ),
            ),
            SizedBox(height: AppSpacing.md),
            CupertinoButton(
              onPressed: () => ref
                  .read(commentProviderFamily(widget.postId).notifier)
                  .loadComments(),
              child: Text(UITextConstants.retry),
            ),
          ],
        ),
      );
    }
    if (state.comments.isEmpty) {
      return Center(
        child: Text(
          UITextConstants.noComment,
          style: TextStyle(
            fontSize: AppTypography.sm,
            color: AppColorsFunctional.getColor(
                isDark, ColorType.foregroundSecondary),
          ),
        ),
      );
    }

    final topLevel =
        state.comments.where((c) => c.replyToCommentId == null || c.replyToCommentId!.isEmpty).toList();

    return ListView.builder(
      controller: _scrollController,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
      itemCount: topLevel.length + (state.status == CommentListStatus.loadingMore ? 1 : 0),
      itemBuilder: (ctx, index) {
        if (index >= topLevel.length) {
          return Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: const Center(child: CupertinoActivityIndicator()),
          );
        }
        final comment = topLevel[index];
        final replies = state.comments
            .where((c) => c.replyToCommentId == comment.id)
            .toList();
        final isLiked = state.likedCommentIds.contains(comment.id);

        return _CommentItem(
          comment: comment,
          replies: replies,
          isLiked: isLiked,
          likedIds: state.likedCommentIds,
          isDark: isDark,
          onLike: () => ref
              .read(commentProviderFamily(widget.postId).notifier)
              .toggleLike(comment.id),
          onReply: () {
            setState(() {
              _replyTo = CommentModel(
                id: comment.id,
                content: comment.content,
                authorId: comment.authorId,
                username: comment.displayName ?? comment.authorId,
              );
            });
          },
          onDelete: comment.authorId == 'me'
              ? () => ref
                  .read(commentProviderFamily(widget.postId).notifier)
                  .deleteComment(comment.id)
              : null,
          onReplyLike: (replyId) => ref
              .read(commentProviderFamily(widget.postId).notifier)
              .toggleLike(replyId),
        );
      },
    );
  }
}

class _DragHandle extends StatelessWidget {
  final bool isDark;
  const _DragHandle({required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(top: AppSpacing.sm, bottom: AppSpacing.xs),
      alignment: Alignment.center,
      child: Container(
        width: 36,
        height: 4,
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(
              isDark, ColorType.foregroundTertiary),
          borderRadius: BorderRadius.circular(2),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final bool isDark;
  final int commentCount;
  final CommentSortMode sortMode;
  final ValueChanged<CommentSortMode> onSortChanged;
  final VoidCallback onClose;

  const _Header({
    required this.isDark,
    required this.commentCount,
    required this.sortMode,
    required this.onSortChanged,
    required this.onClose,
  });

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
            style: TextStyle(fontSize: AppTypography.base, fontWeight: FontWeight.w600),
          ),
          const Spacer(),
          _SortToggle(
            isDark: isDark,
            sortMode: sortMode,
            onChanged: onSortChanged,
          ),
          SizedBox(width: AppSpacing.sm),
          GestureDetector(
            onTap: onClose,
            child: Icon(
              CupertinoIcons.xmark,
              size: AppSpacing.iconMedium,
              color: AppColorsFunctional.getColor(
                  isDark, ColorType.foregroundSecondary),
            ),
          ),
        ],
      ),
    );
  }
}

class _SortToggle extends StatelessWidget {
  final bool isDark;
  final CommentSortMode sortMode;
  final ValueChanged<CommentSortMode> onChanged;

  const _SortToggle({
    required this.isDark,
    required this.sortMode,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildChip(context, CommentSortMode.latest, '最新'),
        SizedBox(width: AppSpacing.xs),
        _buildChip(context, CommentSortMode.hot, '最热'),
      ],
    );
  }

  Widget _buildChip(BuildContext context, CommentSortMode mode, String label) {
    final isActive = sortMode == mode;
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
              : Colors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.xs,
            color: isActive
                ? AppColors.primaryColor
                : AppColorsFunctional.getColor(
                    isDark, ColorType.foregroundSecondary),
            fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}

class _CommentItem extends StatelessWidget {
  final CommentDto comment;
  final List<CommentDto> replies;
  final bool isLiked;
  final Set<String> likedIds;
  final bool isDark;
  final VoidCallback onLike;
  final VoidCallback onReply;
  final VoidCallback? onDelete;
  final ValueChanged<String> onReplyLike;

  const _CommentItem({
    required this.comment,
    required this.replies,
    required this.isLiked,
    required this.likedIds,
    required this.isDark,
    required this.onLike,
    required this.onReply,
    this.onDelete,
    required this.onReplyLike,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                radius: AppSpacing.iconMedium / 2,
                backgroundColor: AppColorsFunctional.getColor(
                    isDark, ColorType.backgroundSecondary),
                backgroundImage: comment.avatarUrl != null
                    ? NetworkImage(comment.avatarUrl!)
                    : null,
                child: comment.avatarUrl == null
                    ? Icon(CupertinoIcons.person_fill,
                        size: AppSpacing.iconSmall,
                        color: AppColorsFunctional.getColor(
                            isDark, ColorType.foregroundTertiary))
                    : null,
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
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
                                  isDark, ColorType.foregroundSecondary),
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                        if (comment.isAuthor)
                          Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.xs,
                              vertical: 1,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.primaryColor
                                  .withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(
                                  AppSpacing.smallBorderRadius),
                            ),
                            child: Text(
                              '作者',
                              style: TextStyle(
                                fontSize: 10,
                                color: AppColors.primaryColor,
                              ),
                            ),
                          ),
                      ],
                    ),
                    SizedBox(height: AppSpacing.xs),
                    Text(comment.content, style: TextStyle(fontSize: AppTypography.sm)),
                    SizedBox(height: AppSpacing.xs),
                    _buildActions(context),
                  ],
                ),
              ),
            ],
          ),
          if (replies.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(left: AppSpacing.iconMedium + AppSpacing.sm),
              child: Column(
                children: replies.take(3).map((reply) {
                  final replyLiked = likedIds.contains(reply.id);
                  return _ReplyItem(
                    reply: reply,
                    isDark: isDark,
                    isLiked: replyLiked,
                    onLike: () => onReplyLike(reply.id),
                  );
                }).toList(),
              ),
            ),
          if (replies.length > 3)
            Padding(
              padding: EdgeInsets.only(left: AppSpacing.iconMedium + AppSpacing.sm),
              child: GestureDetector(
                child: Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpacing.xs),
                  child: Text(
                    '展开 ${replies.length} 条回复',
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: AppColors.primaryColor,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildActions(BuildContext context) {
    return Row(
      children: [
        Text(
          _formatTime(comment.createdAt),
          style: TextStyle(
            fontSize: AppTypography.xs,
            color: AppColorsFunctional.getColor(
                isDark, ColorType.foregroundTertiary),
          ),
        ),
        SizedBox(width: AppSpacing.md),
        GestureDetector(
          onTap: onReply,
          child: Text(
            UITextConstants.replyAction,
            style: TextStyle(
              fontSize: AppTypography.xs,
              color: AppColorsFunctional.getColor(
                  isDark, ColorType.foregroundSecondary),
            ),
          ),
        ),
        const Spacer(),
        GestureDetector(
          onTap: onLike,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                isLiked
                    ? CupertinoIcons.heart_fill
                    : CupertinoIcons.heart,
                size: AppSpacing.iconSmall,
                color: isLiked
                    ? AppColors.error
                    : AppColorsFunctional.getColor(
                        isDark, ColorType.foregroundTertiary),
              ),
              if (comment.likeCount > 0) ...[
                SizedBox(width: AppSpacing.xs),
                Text(
                  '${comment.likeCount}',
                  style: TextStyle(
                    fontSize: AppTypography.xs,
                    color: AppColorsFunctional.getColor(
                        isDark, ColorType.foregroundTertiary),
                  ),
                ),
              ],
            ],
          ),
        ),
        if (onDelete != null) ...[
          SizedBox(width: AppSpacing.md),
          GestureDetector(
            onTap: onDelete,
            child: Icon(
              CupertinoIcons.trash,
              size: AppSpacing.iconSmall,
              color: AppColorsFunctional.getColor(
                  isDark, ColorType.foregroundTertiary),
            ),
          ),
        ],
      ],
    );
  }

  String _formatTime(DateTime time) {
    final diff = DateTime.now().difference(time);
    if (diff.inMinutes < 1) return '刚刚';
    if (diff.inHours < 1) return '${diff.inMinutes}分钟前';
    if (diff.inDays < 1) return '${diff.inHours}小时前';
    if (diff.inDays < 30) return '${diff.inDays}天前';
    return '${time.month}月${time.day}日';
  }
}

class _ReplyItem extends StatelessWidget {
  final CommentDto reply;
  final bool isDark;
  final bool isLiked;
  final VoidCallback onLike;

  const _ReplyItem({
    required this.reply,
    required this.isDark,
    required this.isLiked,
    required this.onLike,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CircleAvatar(
            radius: AppSpacing.iconSmall / 2,
            backgroundColor: AppColorsFunctional.getColor(
                isDark, ColorType.backgroundSecondary),
            child: Icon(CupertinoIcons.person_fill,
                size: AppSpacing.iconSmall / 2,
                color: AppColorsFunctional.getColor(
                    isDark, ColorType.foregroundTertiary)),
          ),
          SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                RichText(
                  text: TextSpan(
                    children: [
                      TextSpan(
                        text: reply.displayName ?? reply.authorId,
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          color: AppColorsFunctional.getColor(
                              isDark, ColorType.foregroundSecondary),
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                      if (reply.replyToDisplayName != null) ...[
                        TextSpan(
                          text: ' 回复 ',
                          style: TextStyle(
                            fontSize: AppTypography.xs,
                            color: AppColorsFunctional.getColor(
                                isDark, ColorType.foregroundTertiary),
                          ),
                        ),
                        TextSpan(
                          text: reply.replyToDisplayName!,
                          style: TextStyle(
                            fontSize: AppTypography.xs,
                            color: AppColors.primaryColor,
                          ),
                        ),
                      ],
                      TextSpan(
                        text: '：${reply.content}',
                        style: TextStyle(fontSize: AppTypography.xs),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          GestureDetector(
            onTap: onLike,
            child: Padding(
              padding: EdgeInsets.only(left: AppSpacing.xs),
              child: Icon(
                isLiked
                    ? CupertinoIcons.heart_fill
                    : CupertinoIcons.heart,
                size: AppSpacing.iconSmall - 2,
                color: isLiked
                    ? AppColors.error
                    : AppColorsFunctional.getColor(
                        isDark, ColorType.foregroundTertiary),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
