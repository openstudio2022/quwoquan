import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart'
    show CommentDto;
import 'package:quwoquan_app/components/comment_system/comment_input_overlay.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/comment_system/comment_thread_view.dart';
import 'package:quwoquan_app/components/comment_system/comment_toolbar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

/// 侵入式分屏评论（图三 / 图四）。
///
/// 媒体内容压在上方，评论区默认占屏高 2/3，顶部拖拽手柄可在 1/2 ~ 90% 之间调节；
/// 媒体区点击或评论区关闭按钮回到沉浸式内容态。状态栏样式由宿主沉浸式壳维持
/// （本组件不强制白底），点击评论输入条弹出统一输入浮层。
class ImmersiveCommentSplitSheet extends ConsumerStatefulWidget {
  const ImmersiveCommentSplitSheet({
    super.key,
    required this.postId,
    required this.content,
    this.commentContext = const MediaViewerCommentContext(),
    this.config = const CommentConfig(),
    this.likeCount = 0,
    this.isLiked = false,
    this.onLikeTap,
    this.onClose,
  });

  final String postId;
  final Widget content;
  final MediaViewerCommentContext commentContext;
  final CommentConfig config;
  final int likeCount;
  final bool isLiked;
  final VoidCallback? onLikeTap;
  final VoidCallback? onClose;

  @override
  ConsumerState<ImmersiveCommentSplitSheet> createState() =>
      _ImmersiveCommentSplitSheetState();
}

class _ImmersiveCommentSplitSheetState
    extends ConsumerState<ImmersiveCommentSplitSheet> {
  double _sheetRatio = AppSpacing.immersiveCommentSheetRatio;
  final ScrollController _scrollController = ScrollController();
  bool _handledInitialCommentContext = false;

  bool get _hasSpecificCommentTarget =>
      (widget.commentContext.commentId?.isNotEmpty ?? false) ||
      (widget.commentContext.parentCommentId?.isNotEmpty ?? false) ||
      (widget.commentContext.replyToCommentId?.isNotEmpty ?? false);

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _scrollToList() {
    if (!_scrollController.hasClients) return;
    _scrollController.animateTo(
      0,
      duration: const Duration(milliseconds: 250),
      curve: Curves.easeOut,
    );
  }

  void _close() {
    ref
        .read(commentObservabilityProvider)
        .trackAction(
          eventName: CommentEventNames.surfaceClosed,
          postId: widget.postId,
          surfaceMode: 'immersive_split',
        );
    widget.onClose?.call();
  }

  void _onDragUpdate(DragUpdateDetails details, double screenHeight) {
    if (screenHeight <= 0) return;
    setState(() {
      _sheetRatio = (_sheetRatio - details.delta.dy / screenHeight).clamp(
        AppSpacing.immersiveCommentSheetMinRatio,
        AppSpacing.immersiveCommentSheetMaxRatio,
      );
    });
  }

  Future<void> _openInput({CommentModel? replyTo}) async {
    await CommentInputOverlay.show(
      context,
      postId: widget.postId,
      config: widget.config,
      replyTo: replyTo,
      surfaceMode: 'immersive_split',
    );
  }

  CommentModel? _resolveCommentModel(
    List<CommentDto> comments,
    String commentId,
  ) {
    for (final comment in comments) {
      if (comment.id == commentId) {
        return CommentModel(
          id: comment.id,
          content: comment.content,
          authorId: comment.authorId,
          username: comment.displayName ?? comment.authorId,
        );
      }
      for (final reply in comment.replyPreview) {
        if (reply.id == commentId) {
          return CommentModel(
            id: reply.id,
            content: reply.content,
            authorId: reply.authorId,
            username: reply.displayName ?? reply.authorId,
          );
        }
      }
    }
    return null;
  }

  Future<void> _consumeInitialCommentContext(CommentState commentState) async {
    if (_handledInitialCommentContext || !widget.commentContext.shouldOpen) {
      return;
    }
    final notifier = ref.read(commentProviderFamily(widget.postId).notifier);
    final parentCommentId = widget.commentContext.parentCommentId;
    var parentCanLoadMore = false;
    if (parentCommentId != null && parentCommentId.isNotEmpty) {
      final parentLoaded = commentState.comments.any(
        (comment) => comment.id == parentCommentId,
      );
      if (parentLoaded) {
        final parent = commentState.comments.firstWhere(
          (comment) => comment.id == parentCommentId,
        );
        parentCanLoadMore = parent.replyNextCursor != null;
        final hasReplyTarget =
            parent.replyPreview.any(
              (reply) =>
                  reply.id == widget.commentContext.commentId ||
                  reply.id == widget.commentContext.replyToCommentId,
            ) ||
            !parentCanLoadMore;
        if (!hasReplyTarget) {
          await notifier.expandReplies(parentCommentId);
          return;
        }
      }
    }
    final replyTargetId = widget.commentContext.replyToCommentId;
    if (replyTargetId != null && replyTargetId.isNotEmpty) {
      final replyTarget = _resolveCommentModel(
        commentState.comments,
        replyTargetId,
      );
      if (replyTarget != null) {
        _handledInitialCommentContext = true;
        await _openInput(replyTo: replyTarget);
        return;
      }
      if (parentCommentId != null &&
          parentCommentId.isNotEmpty &&
          parentCanLoadMore) {
        return;
      }
      _handledInitialCommentContext = true;
      return;
    }
    _handledInitialCommentContext = true;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final screenHeight = MediaQuery.sizeOf(context).height;
    final commentState = ref.watch(commentProviderFamily(widget.postId));
    final commentCount = ref
        .watch(postInteractionStateProvider)
        .commentCountFor(widget.postId, fallback: commentState.comments.length);
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final readyForInitialContext =
        !_hasSpecificCommentTarget ||
        commentState.comments.isNotEmpty ||
        commentState.status == CommentListStatus.error;
    if (!_handledInitialCommentContext &&
        widget.commentContext.shouldOpen &&
        !commentState.isLoading &&
        readyForInitialContext) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        unawaited(_consumeInitialCommentContext(commentState));
      });
    }

    return ColoredBox(
      key: TestKeys.immersiveCommentSplitSheet,
      color: AppColors.black,
      child: Column(
        children: [
          // 媒体内容区：点击回到沉浸态，随评论区拖拽而缩放。
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: _close,
              child: Stack(
                children: [
                  Positioned.fill(child: widget.content),
                  Positioned(
                    top: MediaQuery.viewPaddingOf(context).top + AppSpacing.sm,
                    right: AppSpacing.sm,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size.square(AppSpacing.buttonSize),
                      onPressed: _close,
                      child: Icon(
                        CupertinoIcons.xmark_circle_fill,
                        size: AppSpacing.iconLarge,
                        color: AppColors.white.withValues(alpha: 0.9),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          // 评论区：固定 2/3 起、可拖拽，圆角悬浮在沉浸式内容之上。
          SizedBox(
            height: screenHeight * _sheetRatio,
            child: Container(
              decoration: BoxDecoration(
                color: surface,
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.largeBorderRadius),
                ),
              ),
              child: Column(
                children: [
                  GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onVerticalDragUpdate: (d) => _onDragUpdate(d, screenHeight),
                    child: _SheetHeader(
                      isDark: isDark,
                      commentCount: commentCount,
                      onClose: _close,
                    ),
                  ),
                  Expanded(
                    child: CommentThreadView(
                      postId: widget.postId,
                      scrollController: _scrollController,
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
                    likeCount: widget.likeCount,
                    commentCount: commentCount,
                    isLiked: widget.isLiked,
                    onInputTap: _openInput,
                    onLikeTap: widget.onLikeTap,
                    onCommentTap: _scrollToList,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SheetHeader extends StatelessWidget {
  const _SheetHeader({
    required this.isDark,
    required this.commentCount,
    required this.onClose,
  });

  final bool isDark;
  final int commentCount;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.sm,
        AppSpacing.xs,
      ),
      child: Column(
        children: [
          Center(
            child: Container(
              width: AppSpacing.createEntrySheetHandleWidth,
              height: AppSpacing.createEntrySheetHandleHeight,
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.separatorOpaque,
                ),
                borderRadius: BorderRadius.circular(
                  AppSpacing.createEntrySheetHandleHeight,
                ),
              ),
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Expanded(
                child: Text(
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
              ),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size.square(AppSpacing.minInteractiveSize),
                onPressed: onClose,
                child: Icon(
                  CupertinoIcons.xmark,
                  size: AppSpacing.iconMedium,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundSecondary,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
