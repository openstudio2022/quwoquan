import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/comment_system/comment_toolbar.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/interactions/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/comments/widgets/comment_input_overlay.dart';
import 'package:quwoquan_app/ui/content/comments/widgets/comment_thread_view.dart';
import 'package:quwoquan_app/ui/content/comments/providers/comment_provider.dart';
import 'package:quwoquan_app/ui/content/comments/models/comment_view_data.dart';

enum CommentDetailSurfaceMode {
  cardModal('card_modal', AppUiSurfaces.homeFeed),
  immersiveSplit('immersive_split', AppUiSurfaces.workBrowser),
  profileInteraction('profile_interaction', AppUiSurfaces.profileHome);

  const CommentDetailSurfaceMode(this.analyticsName, this.sourceSurface);

  final String analyticsName;
  final AppUiSurface sourceSurface;
}

class CommentDetailSurface extends ConsumerStatefulWidget {
  const CommentDetailSurface({
    super.key,
    required this.postId,
    required this.mode,
    this.config = const CommentConfig(),
    this.commentContext = const MediaViewerCommentContext(),
    this.entryObservedCommentCount,
    this.scrollController,
    this.flexibleThread = true,
    this.showDragHandle = false,
    this.onHeaderVerticalDragUpdate,
    this.likeCount,
    this.shareCount,
    this.isLiked,
    this.onLikeTap,
    this.onShareTap,
    this.onClose,
    this.onCommentAdded,
  });

  final String postId;
  final CommentDetailSurfaceMode mode;
  final CommentConfig config;
  final MediaViewerCommentContext commentContext;
  final int? entryObservedCommentCount;
  final ScrollController? scrollController;
  final bool flexibleThread;
  final bool showDragHandle;
  final GestureDragUpdateCallback? onHeaderVerticalDragUpdate;
  final int? likeCount;
  final int? shareCount;
  final bool? isLiked;
  final VoidCallback? onLikeTap;
  final VoidCallback? onShareTap;
  final VoidCallback? onClose;
  final void Function(String commentId)? onCommentAdded;

  @override
  ConsumerState<CommentDetailSurface> createState() =>
      _CommentDetailSurfaceState();
}

class _CommentDetailSurfaceState extends ConsumerState<CommentDetailSurface> {
  late final ScrollController _scrollController;
  late final bool _ownsScrollController;
  bool _handledInitialCommentContext = false;
  bool _entryCountNoticeResolved = false;
  String? _entryCountNoticeMessage;

  @override
  void initState() {
    super.initState();
    _scrollController = widget.scrollController ?? ScrollController();
    _ownsScrollController = widget.scrollController == null;
  }

  @override
  void dispose() {
    if (_ownsScrollController) {
      _scrollController.dispose();
    }
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant CommentDetailSurface oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.postId != widget.postId ||
        oldWidget.commentContext != widget.commentContext) {
      _handledInitialCommentContext = false;
    }
    if (oldWidget.postId != widget.postId ||
        oldWidget.entryObservedCommentCount !=
            widget.entryObservedCommentCount) {
      _entryCountNoticeResolved = false;
      _entryCountNoticeMessage = null;
    }
  }

  String? get _highlightTargetCommentId {
    final parent = widget.commentContext.targetParentCommentId?.trim();
    if (parent != null && parent.isNotEmpty) return parent;
    final comment = widget.commentContext.targetCommentId?.trim();
    if (comment != null && comment.isNotEmpty) return comment;
    return null;
  }

  String? get _highlightTargetReplyId {
    final reply = widget.commentContext.targetReplyId?.trim();
    if (reply != null && reply.isNotEmpty) return reply;
    return null;
  }

  Future<void> _openInput({CommentViewData? replyTo}) async {
    final submitted = await CommentInputOverlay.show(
      context,
      postId: widget.postId,
      config: widget.config,
      replyTo: replyTo,
      surfaceMode: widget.mode.analyticsName,
      sourceSurface: widget.mode.sourceSurface,
    );
    if (!mounted || !submitted) return;
    final comments = ref.read(commentProviderFamily(widget.postId)).comments;
    if (comments.isNotEmpty) {
      widget.onCommentAdded?.call(comments.first.id);
    }
  }

  CommentViewData? _resolveReplyTarget(
    List<CommentViewData> comments,
    String commentId,
  ) {
    for (final comment in comments) {
      if (comment.id == commentId) {
        return comment;
      }
      for (final reply in comment.replyPreview) {
        if (reply.id == commentId) {
          return reply;
        }
      }
    }
    return null;
  }

  Future<void> _consumeInitialCommentContext(CommentState commentState) async {
    if (_handledInitialCommentContext || !widget.commentContext.shouldOpen) {
      return;
    }
    final replyTargetId = widget.commentContext.replyToCommentId?.trim();
    if (replyTargetId == null || replyTargetId.isEmpty) {
      _handledInitialCommentContext = true;
      return;
    }

    final parentCommentId = widget.commentContext.targetParentCommentId?.trim();
    if (parentCommentId != null && parentCommentId.isNotEmpty) {
      CommentViewData? parent;
      for (final comment in commentState.comments) {
        if (comment.id == parentCommentId) {
          parent = comment;
          break;
        }
      }
      final parentCanLoadMore = parent?.replyNextCursor != null;
      final replyLoaded =
          parent?.replyPreview.any((reply) => reply.id == replyTargetId) ??
          false;
      if (!replyLoaded && parentCanLoadMore) {
        await ref
            .read(commentProviderFamily(widget.postId).notifier)
            .expandReplies(parentCommentId);
        return;
      }
    }

    final replyTarget = _resolveReplyTarget(
      commentState.comments,
      replyTargetId,
    );
    _handledInitialCommentContext = true;
    if (replyTarget != null) {
      await _openInput(replyTo: replyTarget);
    }
  }

  void _maybeConsumeInitialContext(CommentState commentState) {
    if (_handledInitialCommentContext || !widget.commentContext.shouldOpen) {
      return;
    }
    final ready =
        commentState.comments.isNotEmpty ||
        commentState.status == CommentListStatus.error;
    if (!ready || commentState.isLoading) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      unawaited(_consumeInitialCommentContext(commentState));
    });
  }

  void _maybeResolveEntryCountNotice(CommentState commentState) {
    if (_entryCountNoticeResolved) {
      return;
    }
    final observedCount = widget.entryObservedCommentCount;
    if (observedCount == null) {
      _entryCountNoticeResolved = true;
      return;
    }
    final ready =
        commentState.sessionLoadVersion > 0 &&
        commentState.status == CommentListStatus.idle &&
        !commentState.isLoading;
    if (!ready) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _entryCountNoticeResolved) {
        return;
      }
      final diff = commentState.totalCount - observedCount;
      setState(() {
        _entryCountNoticeResolved = true;
        if (diff > 0) {
          _entryCountNoticeMessage = ContentText
              .commentEntryCountIncreaseNoticeTemplate
              .replaceFirst('%s', '$diff');
          return;
        }
        if (diff < 0) {
          _entryCountNoticeMessage = ContentText
              .commentEntryCountDecreaseNoticeTemplate
              .replaceFirst('%s', '${diff.abs()}');
          return;
        }
        _entryCountNoticeMessage = null;
      });
    });
  }

  void _toggleLikeFromInteraction(PostInteractionState interaction) {
    final isLiked = interaction.isLiked(widget.postId);
    final likeCount = interaction.likeCountFor(widget.postId);
    runWhenLoggedIn(ref, context, AuthGateReason.like, () {
      final nextLiked = !isLiked;
      syncPostLikeIntent(
        ref,
        postId: widget.postId,
        previousLiked: isLiked,
        isLiked: nextLiked,
        likeCount: isLiked
            ? (likeCount - 1).clamp(0, 1 << 31).toInt()
            : likeCount + 1,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final commentState = ref.watch(commentProviderFamily(widget.postId));
    final interaction = ref.watch(postInteractionStateProvider);
    final loadedCommentTotal =
        commentState.status != CommentListStatus.idle ||
        commentState.totalCount > 0;
    final hasBlockingCommentFailure =
        commentState.status == CommentListStatus.error &&
        commentState.comments.isEmpty;
    final int? commentCount = hasBlockingCommentFailure
        ? null
        : loadedCommentTotal
        ? commentState.totalCount
        : interaction.commentCountFor(
            widget.postId,
            fallback: commentState.totalCount,
          );
    _maybeConsumeInitialContext(commentState);
    _maybeResolveEntryCountNotice(commentState);

    final thread = CommentThreadView(
      postId: widget.postId,
      scrollController: _scrollController,
      highlightCommentId: _highlightTargetCommentId,
      highlightReplyId: _highlightTargetReplyId,
      onReplySelected: (comment) => _openInput(replyTo: comment),
    );

    final content = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        GestureDetector(
          behavior: widget.onHeaderVerticalDragUpdate == null
              ? HitTestBehavior.deferToChild
              : HitTestBehavior.opaque,
          onVerticalDragUpdate: widget.onHeaderVerticalDragUpdate,
          child: CommentDetailHeader(
            isDark: isDark,
            commentCount: commentCount,
            showDragHandle: widget.showDragHandle,
            onClose: widget.onClose,
          ),
        ),
        if (_entryCountNoticeMessage != null)
          _CommentEntryConsistencyNotice(message: _entryCountNoticeMessage!),
        if (widget.flexibleThread)
          Flexible(fit: FlexFit.loose, child: thread)
        else
          Expanded(child: thread),
        CommentToolbar(
          likeCount:
              widget.likeCount ?? interaction.likeCountFor(widget.postId),
          shareCount:
              widget.shareCount ?? interaction.shareCountFor(widget.postId),
          isLiked: widget.isLiked ?? interaction.isLiked(widget.postId),
          onInputTap: _openInput,
          onLikeTap:
              widget.onLikeTap ?? () => _toggleLikeFromInteraction(interaction),
          onShareTap: widget.onShareTap,
        ),
      ],
    );

    return content;
  }
}

class _CommentEntryConsistencyNotice extends StatelessWidget {
  const _CommentEntryConsistencyNotice({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.xs,
      ),
      child: Container(
        key: TestKeys.commentEntryConsistencyNotice,
        width: double.infinity,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: AppColors.primaryColor.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
        ),
        child: Text(
          message,
          textAlign: TextAlign.center,
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

class CommentDetailHeader extends StatelessWidget {
  const CommentDetailHeader({
    super.key,
    required this.isDark,
    required this.commentCount,
    this.showDragHandle = false,
    this.onClose,
  });

  final bool isDark;

  /// `null` 表示评论总数尚不可确认，避免把加载失败误写成“共 0 条评论”。
  final int? commentCount;
  final bool showDragHandle;
  final VoidCallback? onClose;

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
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showDragHandle) ...[
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
          ],
          Row(
            children: [
              Expanded(
                child: Text(
                  commentCount == null
                      ? FoundationText.comment
                      : ContentText.commentCountTitleTemplate.replaceFirst(
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
              if (onClose != null)
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size.square(
                    AppSpacing.appChromeActionButtonSize,
                  ),
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
        ],
      ),
    );
  }
}
