import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/comment_system/comment_detail_surface.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';

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
    this.shareCount = 0,
    this.isLiked = false,
    this.isShared = false,
    this.onLikeTap,
    this.onShareTap,
    this.onClose,
  });

  final String postId;
  final Widget content;
  final MediaViewerCommentContext commentContext;
  final CommentConfig config;
  final int likeCount;
  final int shareCount;
  final bool isLiked;
  final bool isShared;
  final VoidCallback? onLikeTap;
  final VoidCallback? onShareTap;
  final VoidCallback? onClose;

  @override
  ConsumerState<ImmersiveCommentSplitSheet> createState() =>
      _ImmersiveCommentSplitSheetState();
}

class _ImmersiveCommentSplitSheetState
    extends ConsumerState<ImmersiveCommentSplitSheet> {
  double _sheetRatio = AppSpacing.immersiveCommentSheetRatio;
  final ScrollController _scrollController = ScrollController();

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
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

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.sizeOf(context).height;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );

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
              child: CommentDetailSurface(
                postId: widget.postId,
                mode: widget.commentContext.usesProfileInteractionMode
                    ? CommentDetailSurfaceMode.profileInteraction
                    : CommentDetailSurfaceMode.immersiveSplit,
                config: widget.config,
                commentContext: widget.commentContext,
                scrollController: _scrollController,
                flexibleThread: false,
                showDragHandle: true,
                onHeaderVerticalDragUpdate: (d) =>
                    _onDragUpdate(d, screenHeight),
                likeCount: widget.likeCount,
                shareCount: widget.shareCount,
                isLiked: widget.isLiked,
                isShared: widget.isShared,
                onLikeTap: widget.onLikeTap,
                onShareTap: widget.onShareTap,
                onClose: _close,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
