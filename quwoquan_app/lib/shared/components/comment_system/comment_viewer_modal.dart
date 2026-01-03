import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'comment_models.dart';
import 'comment_viewer.dart' show CommentInput;

/// 评论查看器 - 模态框模式
class CommentViewer {
  /// 显示评论模态框
  static Future<void> showModal({
    required BuildContext context,
    required String postId,
    required List<CommentModel> initialComments,
    required CommentConfig config,
    CommentModalHeight modalHeight = CommentModalHeight.adaptive,
    Function(String)? onCommentAdded,
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
      builder: (context) => _CommentViewerModal(
        postId: postId,
        initialComments: initialComments,
        config: config,
        modalHeight: modalHeight,
        onCommentAdded: onCommentAdded,
        onCommentLiked: onCommentLiked,
        onReplyAdded: onReplyAdded,
        onUserTapped: onUserTapped,
        onLoadMoreComments: onLoadMoreComments,
        onClose: onClose,
      ),
    );
  }
}

class _CommentViewerModal extends StatefulWidget {
  final String postId;
  final List<CommentModel> initialComments;
  final CommentConfig config;
  final CommentModalHeight modalHeight;
  final Function(String)? onCommentAdded;
  final Function(CommentModel)? onCommentLiked;
  final Function(String, String)? onReplyAdded;
  final Function(String)? onUserTapped;
  final Function(String)? onLoadMoreComments;
  final VoidCallback? onClose;

  const _CommentViewerModal({
    required this.postId,
    required this.initialComments,
    required this.config,
    this.modalHeight = CommentModalHeight.adaptive,
    this.onCommentAdded,
    this.onCommentLiked,
    this.onReplyAdded,
    this.onUserTapped,
    this.onLoadMoreComments,
    this.onClose,
  });

  @override
  State<_CommentViewerModal> createState() => _CommentViewerModalState();
}

class _CommentViewerModalState extends State<_CommentViewerModal> {
  final List<CommentModel> _comments = [];
  CommentModel? _replyTo;

  @override
  void initState() {
    super.initState();
    _comments.addAll(widget.initialComments);
  }

  double _getModalHeight(BuildContext context) {
    final screenHeight = MediaQuery.of(context).size.height;
    switch (widget.modalHeight) {
      case CommentModalHeight.adaptive:
        return screenHeight * 0.7;
      case CommentModalHeight.half:
        return screenHeight * 0.5;
      case CommentModalHeight.full:
        return screenHeight;
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final modalHeight = _getModalHeight(context);

    return Container(
      height: modalHeight,
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
      ),
      child: Column(
        children: [
          // 标题栏
          Container(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                const Text(
                  '评论',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.close),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
          ),
          // 评论列表
          Expanded(
            child: _comments.isEmpty
                ? Center(
                    child: Text(
                      '暂无评论',
                      style: TextStyle(
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                      ),
                    ),
                  )
                : ListView.builder(
                    itemCount: _comments.length,
                    itemBuilder: (context, index) {
                      final comment = _comments[index];
                      return ListTile(
                        title: Text(comment.username ?? '用户'),
                        subtitle: Text(comment.content),
                        onTap: () => widget.onUserTapped?.call(comment.authorId ?? ''),
                      );
                    },
                  ),
          ),
          // 评论输入
          CommentInput(
            config: widget.config,
            replyTo: _replyTo,
            onSubmit: (content) {
              widget.onCommentAdded?.call('comment_${DateTime.now().millisecondsSinceEpoch}');
              setState(() {
                _replyTo = null;
              });
            },
            onCancelReply: () {
              setState(() {
                _replyTo = null;
              });
            },
          ),
        ],
      ),
    );
  }
}

