import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/ui/content/comments/widgets/comment_detail_surface.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';

/// 卡片弹窗评论入口：从发现页 / Moment 卡 / 媒体卡片底部弹出。
class CommentViewer {
  const CommentViewer._();

  static Future<void> showModal({
    required BuildContext context,
    required String postId,
    int? entryObservedCommentCount,
    CommentConfig config = const CommentConfig(),
    void Function(String commentId)? onCommentAdded,
    VoidCallback? onClose,
    VoidCallback? onShareTap,
  }) async {
    await showAppBottomModal<void>(
      context: context,
      builder: (ctx) => _CommentSheet(
        postId: postId,
        entryObservedCommentCount: entryObservedCommentCount,
        config: config,
        onCommentAdded: onCommentAdded,
        onClose: onClose,
        onShareTap: onShareTap,
      ),
    );
  }
}

class _CommentSheet extends StatefulWidget {
  const _CommentSheet({
    required this.postId,
    this.entryObservedCommentCount,
    required this.config,
    this.onCommentAdded,
    this.onClose,
    this.onShareTap,
  });

  final String postId;
  final int? entryObservedCommentCount;
  final CommentConfig config;
  final void Function(String commentId)? onCommentAdded;
  final VoidCallback? onClose;
  final VoidCallback? onShareTap;

  @override
  State<_CommentSheet> createState() => _CommentSheetState();
}

class _CommentSheetState extends State<_CommentSheet> {
  void _dismiss() {
    Navigator.of(context).pop();
    widget.onClose?.call();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;

    return AppBottomModalSurface(
      onDismiss: _dismiss,
      backgroundColor:
          SettingsSemanticConstants.conversationSheetPanelBackground(isDark),
      maxHeightRatio: AppSpacing.modalSheetMaxHeightRatio,
      showHandle: false,
      includeBottomSafeAreaPadding: false,
      panelKey: TestKeys.modalBottomSheetPanel,
      child: CommentDetailSurface(
        postId: widget.postId,
        mode: CommentDetailSurfaceMode.cardModal,
        config: widget.config,
        entryObservedCommentCount: widget.entryObservedCommentCount,
        flexibleThread: true,
        onClose: _dismiss,
        onShareTap: widget.onShareTap,
        onCommentAdded: widget.onCommentAdded,
      ),
    );
  }
}
