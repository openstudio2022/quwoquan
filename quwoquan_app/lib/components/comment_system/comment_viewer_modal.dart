import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/comment_system/comment_input_overlay.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/comment_system/comment_thread_view.dart';
import 'package:quwoquan_app/components/comment_system/comment_toolbar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

/// 卡片弹窗评论入口：从发现页 / Moment 卡 / 媒体卡片底部弹出。
class CommentViewer {
  const CommentViewer._();

  static Future<void> showModal({
    required BuildContext context,
    required String postId,
    CommentConfig config = const CommentConfig(),
    void Function(String commentId)? onCommentAdded,
    VoidCallback? onClose,
  }) async {
    await showCupertinoModalPopup<void>(
      context: context,
      barrierColor: AppColors.transparent,
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
  const _CommentSheet({
    required this.postId,
    required this.config,
    this.onCommentAdded,
    this.onClose,
  });

  final String postId;
  final CommentConfig config;
  final void Function(String commentId)? onCommentAdded;
  final VoidCallback? onClose;

  @override
  ConsumerState<_CommentSheet> createState() => _CommentSheetState();
}

class _CommentSheetState extends ConsumerState<_CommentSheet> {
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
    if (!_scrollController.hasClients) return;
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - AppSpacing.xl) {
      ref.read(commentProviderFamily(widget.postId).notifier).loadMore();
    }
  }

  void _scrollToList() {
    if (!_scrollController.hasClients) return;
    _scrollController.animateTo(
      0,
      duration: const Duration(milliseconds: 250),
      curve: Curves.easeOut,
    );
  }

  void _dismiss() {
    Navigator.of(context).pop();
    widget.onClose?.call();
  }

  Future<void> _openInput({CommentModel? replyTo}) async {
    await CommentInputOverlay.show(
      context,
      postId: widget.postId,
      config: widget.config,
      replyTo: replyTo,
      surfaceMode: 'card_modal',
    );
  }

  void _toggleLike() {
    final interaction = ref.read(postInteractionStateProvider);
    final isLiked = interaction.isLiked(widget.postId);
    final likeCount = interaction.likeCountFor(widget.postId);
    runWhenLoggedIn(ref, context, AuthGateReason.like, () {
      syncPostLikeIntent(
        ref,
        postId: widget.postId,
        isLiked: !isLiked,
        likeCount: isLiked
            ? (likeCount - 1).clamp(0, 1 << 31).toInt()
            : likeCount + 1,
      );
    });
  }

  void _toggleFavorite() {
    final interaction = ref.read(postInteractionStateProvider);
    final isSaved = interaction.isSaved(widget.postId);
    final bookmarkCount = interaction.bookmarkCountFor(widget.postId);
    runWhenLoggedIn(ref, context, AuthGateReason.favorite, () {
      syncPostSaveIntent(
        ref,
        postId: widget.postId,
        isSaved: !isSaved,
        bookmarkCount: isSaved
            ? (bookmarkCount - 1).clamp(0, 1 << 31).toInt()
            : bookmarkCount + 1,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final commentState = ref.watch(commentProviderFamily(widget.postId));
    final interaction = ref.watch(postInteractionStateProvider);
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;

    if (!_initialLoaded) {
      _initialLoaded = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(commentProviderFamily(widget.postId).notifier).loadComments();
      });
    }

    return AppBottomModalSurface(
      onDismiss: _dismiss,
      backgroundColor: SettingsSemanticConstants.conversationSheetPanelBackground(
        isDark,
      ),
      maxHeightRatio: AppSpacing.modalSheetMaxHeightRatio,
      showHandle: false,
      panelKey: TestKeys.modalBottomSheetPanel,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _Header(
            isDark: isDark,
            commentCount: interaction.commentCountFor(
              widget.postId,
              fallback: commentState.comments.length,
            ),
            sortMode: commentState.sortMode,
            onSortChanged: (mode) => ref
                .read(commentProviderFamily(widget.postId).notifier)
                .switchSort(mode),
            onClose: _dismiss,
          ),
          Flexible(
            fit: FlexFit.loose,
            child: CommentThreadView(
              postId: widget.postId,
              scrollController: _scrollController,
              showHeader: false,
              onReplySelected: (comment) => _openInput(
                replyTo: CommentModel(
                  id: comment.id,
                  content: comment.content,
                  authorId: comment.authorId,
                  username: comment.displayName ?? comment.authorId,
                ),
              ),
            ),
          ),
          CommentToolbar(
            likeCount: interaction.likeCountFor(widget.postId),
            favoriteCount: interaction.bookmarkCountFor(widget.postId),
            commentCount: interaction.commentCountFor(
              widget.postId,
              fallback: commentState.comments.length,
            ),
            isLiked: interaction.isLiked(widget.postId),
            isFavorited: interaction.isSaved(widget.postId),
            onInputTap: _openInput,
            onLikeTap: _toggleLike,
            onFavoriteTap: _toggleFavorite,
            onCommentTap: _scrollToList,
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.isDark,
    required this.commentCount,
    required this.sortMode,
    required this.onSortChanged,
    required this.onClose,
  });

  final bool isDark;
  final int commentCount;
  final CommentSortMode sortMode;
  final ValueChanged<CommentSortMode> onSortChanged;
  final VoidCallback onClose;

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
            UITextConstants.commentCountTitleTemplate.replaceFirst(
              '%s',
              '$commentCount',
            ),
            style: TextStyle(
              fontSize: AppTypography.sectionTitle,
              fontWeight: AppTypography.semiBold,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundPrimary,
              ),
            ),
          ),
          const Spacer(),
          _SortToggle(
            isDark: isDark,
            sortMode: sortMode,
            onChanged: onSortChanged,
          ),
          SizedBox(width: AppSpacing.sm),
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: const Size.square(AppSpacing.appChromeActionButtonSize),
            onPressed: onClose,
            child: Icon(
              CupertinoIcons.xmark,
              size: AppSpacing.appChromeActionIconSize,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SortToggle extends StatelessWidget {
  const _SortToggle({
    required this.isDark,
    required this.sortMode,
    required this.onChanged,
  });

  final bool isDark;
  final CommentSortMode sortMode;
  final ValueChanged<CommentSortMode> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildChip(
          CommentSortMode.latest,
          UITextConstants.circleSortLatest,
        ),
        SizedBox(width: AppSpacing.xs),
        _buildChip(
          CommentSortMode.recommended,
          UITextConstants.commentSortRecommended,
        ),
        SizedBox(width: AppSpacing.xs),
        _buildChip(
          CommentSortMode.mostLiked,
          UITextConstants.commentSortMostLiked,
        ),
      ],
    );
  }

  Widget _buildChip(CommentSortMode mode, String label) {
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
