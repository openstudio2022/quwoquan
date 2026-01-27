import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'comment_models.dart';
import 'comment_responsive.dart';
import 'comment_hierarchy.dart';

/// 评论列表组件
class CommentList extends StatelessWidget {
  final List<CommentModel> comments;
  final CommentConfig config;
  final Map<String, bool> expandedReplies;
  final Function(String)? onToggleReplies;
  final Function(CommentModel)? onReply;
  final Function(CommentModel)? onLike;
  final Function(CommentModel)? onUserTap;
  final VoidCallback? onLoadMore;
  final bool hasMore;
  final bool isLoading;

  const CommentList({
    super.key,
    required this.comments,
    required this.config,
    required this.expandedReplies,
    this.onToggleReplies,
    this.onReply,
    this.onLike,
    this.onUserTap,
    this.onLoadMore,
    this.hasMore = false,
    this.isLoading = false,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    if (comments.isEmpty) {
      return _buildEmptyState(context, isDark);
    }
    
    return Column(
      children: [
        // 评论列表
        Expanded(
          child: ListView.builder(
            padding: CommentResponsive.getModalPadding(context),
            itemCount: comments.length + (hasMore ? 1 : 0),
            itemBuilder: (context, index) {
              if (index < comments.length) {
                return _buildCommentItem(context, comments[index], isDark);
              } else {
                return _buildLoadMoreButton(context, isDark);
              }
            },
          ),
        ),
      ],
    );
  }

  /// 构建空状态
  Widget _buildEmptyState(BuildContext context, bool isDark) {
    final fontSize = CommentResponsive.getFontSize(context, CommentFontSize.body);
    
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.chat_bubble_outline,
            size: CommentResponsive.getIconSize(context) * 2,
            color: isDark 
              ? AppColors.dark.foregroundTertiary 
              : AppColors.light.foregroundTertiary,
          ),
          
          SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.md)),
          
          Text(
            UITextConstants.noComments,
            style: TextStyle(
              fontSize: fontSize,
              color: isDark 
                ? AppColors.dark.foregroundSecondary 
                : AppColors.light.foregroundSecondary,
            ),
          ),
          
          if (config.canUserComment) ...[
            SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.sm)),
            
            Text(
              UITextConstants.commentPlaceholder,
              style: TextStyle(
                fontSize: CommentResponsive.getFontSize(context, CommentFontSize.small),
                color: isDark 
                  ? AppColors.dark.foregroundTertiary 
                  : AppColors.light.foregroundTertiary,
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// 构建评论项
  Widget _buildCommentItem(BuildContext context, CommentModel comment, bool isDark) {
    final isExpanded = expandedReplies[comment.id] ?? false;
    
    return Padding(
      padding: EdgeInsets.only(
        bottom: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.md),
      ),
      child: CommentHierarchyWidget(
        comment: comment,
        config: config,
        isReplyExpanded: isExpanded,
        onToggleReplies: () => onToggleReplies?.call(comment.id),
        onReply: onReply,
        onLike: onLike,
        onUserTap: onUserTap,
      ),
    );
  }

  /// 构建加载更多按钮
  Widget _buildLoadMoreButton(BuildContext context, bool isDark) {
    return Container(
      padding: CommentResponsive.getModalPadding(context),
      child: Center(
        child: isLoading 
          ? _buildLoadingIndicator(context, isDark)
          : _buildLoadMoreButtonWidget(context, isDark),
      ),
    );
  }

  /// 构建加载指示器
  Widget _buildLoadingIndicator(BuildContext context, bool isDark) {
    return Container(
      padding: EdgeInsets.symmetric(
        vertical: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.md),
      ),
      child: CircularProgressIndicator(
        strokeWidth: 2,
        valueColor: AlwaysStoppedAnimation<Color>(
          AppColors.primaryColor,
        ),
      ),
    );
  }

  /// 构建加载更多按钮组件
  Widget _buildLoadMoreButtonWidget(BuildContext context, bool isDark) {
    return GestureDetector(
      onTap: onLoadMore,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: CommentResponsive.getContainerSpacing(context, SpacingSize.lg),
          vertical: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.md),
        ),
        decoration: BoxDecoration(
          color: isDark 
            ? AppColors.dark.backgroundSecondary 
            : AppColors.light.backgroundSecondary,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isDark 
              ? AppColors.dark.borderPrimary 
              : AppColors.light.borderPrimary,
            width: 1,
          ),
        ),
        child: Text(
          UITextConstants.loadMoreComments,
          style: TextStyle(
            fontSize: CommentResponsive.getFontSize(context, CommentFontSize.body),
            color: AppColors.primaryColor,
            fontWeight: FontWeight.w500,
          ),
        ),
      ),
    );
  }
}

/// 评论列表状态管理
class CommentListController {
  final List<CommentModel> _comments = [];
  final Map<String, bool> _expandedReplies = {};
  bool _isLoading = false;
  bool _hasMore = true;
  int _currentPage = 1;

  List<CommentModel> get comments => _comments;
  Map<String, bool> get expandedReplies => _expandedReplies;
  bool get isLoading => _isLoading;
  bool get hasMore => _hasMore;
  int get currentPage => _currentPage;

  /// 设置评论列表
  void setComments(List<CommentModel> comments) {
    _comments.clear();
    _comments.addAll(comments);
  }

  /// 添加评论
  void addComment(CommentModel comment) {
    _comments.insert(0, comment);
  }

  /// 更新评论
  void updateComment(CommentModel updatedComment) {
    final index = _comments.indexWhere((c) => c.id == updatedComment.id);
    if (index != -1) {
      _comments[index] = updatedComment;
    }
  }

  /// 删除评论
  void removeComment(String commentId) {
    _comments.removeWhere((c) => c.id == commentId);
  }

  /// 切换回复展开状态
  void toggleReplyExpansion(String commentId) {
    _expandedReplies[commentId] = !(_expandedReplies[commentId] ?? false);
  }

  /// 设置加载状态
  void setLoading(bool loading) {
    _isLoading = loading;
  }

  /// 设置是否有更多数据
  void setHasMore(bool hasMore) {
    _hasMore = hasMore;
  }

  /// 增加页码
  void incrementPage() {
    _currentPage++;
  }

  /// 重置状态
  void reset() {
    _comments.clear();
    _expandedReplies.clear();
    _isLoading = false;
    _hasMore = true;
    _currentPage = 1;
  }
}
