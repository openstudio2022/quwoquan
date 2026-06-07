import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/comment_system/comment_input_overlay.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/components/comment_system/comment_thread_view.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/providers/comment_provider.dart';

/// 文章内容平铺评论区。
///
/// 评论区平铺在文章正文之后，与正文用「分隔线 + 共 N 条评论」标题明确分割，
/// 评论列表随文章主滚动流展开（shrinkWrap），不再是固定高度的二级滚动窗口。
/// 点击标题区的「说点什么…」或某条评论的回复，弹出统一评论输入浮层。
class InlineArticleCommentSection extends ConsumerWidget {
  const InlineArticleCommentSection({
    super.key,
    required this.postId,
    this.config = const CommentConfig(),
  });

  final String postId;
  final CommentConfig config;

  Future<void> _openInput(BuildContext context, {CommentModel? replyTo}) {
    return CommentInputOverlay.show(
      context,
      postId: postId,
      config: config,
      replyTo: replyTo,
      surfaceMode: 'inline_article',
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final state = ref.watch(commentProviderFamily(postId));
    final commentCount = ref
        .watch(postInteractionStateProvider)
        .commentCountFor(postId, fallback: state.comments.length);
    return Container(
      key: TestKeys.inlineArticleCommentSection,
      padding: EdgeInsets.only(top: AppSpacing.lg, bottom: AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.backgroundPrimary,
        ),
        border: Border(
          top: BorderSide(
            color: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
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
          SizedBox(height: AppSpacing.sm),
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => _openInput(context),
              child: Container(
                height: AppSpacing.commentInputHeight,
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                alignment: Alignment.centerLeft,
                decoration: BoxDecoration(
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.backgroundSecondary,
                  ),
                  borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                ),
                child: Text(
                  UITextConstants.commentPlaceholder,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundTertiary,
                    ),
                  ),
                ),
              ),
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          CommentThreadView(
            postId: postId,
            showHeader: false,
            shrinkWrap: true,
            onReplySelected: (comment) => _openInput(
              context,
              replyTo: CommentModel(
                id: comment.id,
                content: comment.content,
                authorId: comment.authorId,
                username: comment.displayName ?? comment.authorId,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
