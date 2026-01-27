import 'dart:math';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'comment_models.dart';
import 'comment_responsive.dart';

/// 评论层级管理器 - 处理99层回复的层级显示逻辑
class CommentHierarchyManager {
  /// 构建评论层级结构
  static List<CommentModel> buildHierarchy(List<CommentModel> flatComments) {
    final Map<String, List<CommentModel>> replyMap = {};
    final List<CommentModel> rootComments = [];
    
    // 分离根评论和回复
    for (final comment in flatComments) {
      if (comment.parentId == null || comment.parentId!.isEmpty) {
        // 根评论
        rootComments.add(comment);
      } else {
        // 回复评论
        replyMap[comment.parentId!] ??= [];
        replyMap[comment.parentId!]!.add(comment);
      }
    }
    
    // 递归构建层级结构
    return _buildCommentTree(rootComments, replyMap, 0);
  }

  /// 递归构建评论树
  static List<CommentModel> _buildCommentTree(
    List<CommentModel> comments,
    Map<String, List<CommentModel>> replyMap,
    int currentLevel,
  ) {
    final List<CommentModel> result = [];
    
    for (final comment in comments) {
      // 检查是否超过最大层级（99层）
      if (currentLevel >= 99) {
        // 超过99层，不再追溯上级，按照正常回复处理
        final processedComment = comment.copyWith(
          level: 99,
        );
        result.add(processedComment);
        continue;
      }
      
      // 获取当前评论的回复
      final replies = replyMap[comment.id] ?? [];
      
      // 创建处理后的评论
      final processedComment = comment.copyWith(
        level: currentLevel,
        replyCount: replies.length,
      );
      
      result.add(processedComment);
    }
    
    return result;
  }

  /// 获取可见的回复列表
  static List<CommentModel> getVisibleReplies(
    List<CommentModel> replies,
    bool isExpanded,
    int maxInitial,
  ) {
    if (isExpanded || replies.length <= maxInitial) {
      return replies;
    }
    return replies.take(maxInitial).toList();
  }

  /// 检查是否有隐藏的回复
  static bool hasHiddenReplies(
    List<CommentModel> replies,
    bool isExpanded,
    int maxInitial,
  ) {
    return !isExpanded && replies.length > maxInitial;
  }

  /// 获取隐藏回复的数量
  static int getHiddenRepliesCount(
    List<CommentModel> replies,
    bool isExpanded,
    int maxInitial,
  ) {
    if (hasHiddenReplies(replies, isExpanded, maxInitial)) {
      return replies.length - maxInitial;
    }
    return 0;
  }

  /// 获取回复的显示文本
  static String getReplyDisplayText(
    List<CommentModel> replies,
    bool isExpanded,
    int maxInitial,
  ) {
    if (!hasHiddenReplies(replies, isExpanded, maxInitial)) {
      return '';
    }
    
    final hiddenCount = getHiddenRepliesCount(replies, isExpanded, maxInitial);
    return '${UITextConstants.expandHiddenFloors} ($hiddenCount)';
  }

  /// 获取回复缩进
  static double getReplyIndent(BuildContext context, int level) {
    return CommentResponsive.getReplyIndent(context, level);
  }

  /// 检查是否可以回复
  static bool canReply(CommentModel comment, CommentConfig config) {
    if (!config.canUserReply) return false;
    if (comment.level >= config.maxReplyLevel) return false;
    return true;
  }

  /// 获取回复的目标用户信息
  static String getReplyTarget(CommentModel comment) {
    return '@${comment.username}';
  }

  /// 获取回复占位符文本
  static String getReplyPlaceholder(CommentModel comment) {
    return UITextConstants.replyPlaceholder.replaceAll('{username}', comment.username);
  }
}

/// 评论层级显示组件
class CommentHierarchyWidget extends StatelessWidget {
  final CommentModel comment;
  final CommentConfig config;
  final bool isReplyExpanded;
  final VoidCallback? onToggleReplies;
  final Function(CommentModel)? onReply;
  final Function(CommentModel)? onLike;
  final Function(CommentModel)? onUserTap;

  const CommentHierarchyWidget({
    super.key,
    required this.comment,
    required this.config,
    this.isReplyExpanded = false,
    this.onToggleReplies,
    this.onReply,
    this.onLike,
    this.onUserTap,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 主评论内容
        _buildMainComment(context, isDark),
        
        // 回复展开/收起按钮
        if (comment.replies.isNotEmpty) ...[
          SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
          _buildReplyToggleButton(context, isDark),
        ],
        
        // 展开的回复列表（扁平化）
        if (isReplyExpanded && comment.replies.isNotEmpty) ...[
          SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.sm)),
          _buildFlatRepliesList(context, isDark),
        ],
      ],
    );
  }

  /// 构建主评论
  Widget _buildMainComment(BuildContext context, bool isDark) {
    return Container(
      padding: CommentResponsive.getCommentItemPadding(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 楼层编号和用户信息
          Row(
            children: [
              // 楼层编号
              Container(
                width: 32,
                height: 24,
                decoration: BoxDecoration(
                  color: isDark 
                    ? AppColors.dark.backgroundTertiary 
                    : AppColors.light.backgroundTertiary,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Center(
                  child: Text(
                    '${comment.floorNumber}',
                    style: TextStyle(
                      fontSize: CommentResponsive.getFontSize(context, CommentFontSize.small),
                      fontWeight: FontWeight.w600,
                      color: isDark 
                        ? AppColors.dark.foregroundSecondary 
                        : AppColors.light.foregroundSecondary,
                    ),
                  ),
                ),
              ),
              
              SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
              
              // 用户信息
              Expanded(child: _buildUserInfo(context, isDark)),
            ],
          ),
          
          SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
          
          // 评论内容
          _buildCommentText(context, isDark),
          
          SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
          
          // 操作按钮
          _buildActionButtons(context, isDark),
        ],
      ),
    );
  }

  /// 构建回复展开/收起按钮
  Widget _buildReplyToggleButton(BuildContext context, bool isDark) {
    final replyCount = comment.replies.length;
    final hiddenCount = replyCount - 2; // 最多显示2条回复
    
    return GestureDetector(
      onTap: onToggleReplies,
      child: Container(
        padding: EdgeInsets.symmetric(
          vertical: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs),
          horizontal: CommentResponsive.getContainerSpacing(context, SpacingSize.sm),
        ),
        child: Row(
          children: [
            Icon(
              isReplyExpanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
              size: CommentResponsive.getCommentItemIconSize(context),
              color: AppColors.primaryColor,
            ),
            SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
            Text(
              isReplyExpanded 
                ? UITextConstants.hideReplies
                : '共${replyCount}条回复',
              style: TextStyle(
                fontSize: CommentResponsive.getFontSize(context, CommentFontSize.small),
                color: AppColors.primaryColor,
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 构建扁平化回复列表
  Widget _buildFlatRepliesList(BuildContext context, bool isDark) {
    return Column(
      children: comment.replies.map((reply) => 
        Padding(
          padding: EdgeInsets.only(
            bottom: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.sm),
          ),
          child: _buildReplyItem(context, reply, isDark),
        ),
      ).toList(),
    );
  }

  /// 构建单个回复项（扁平化）
  Widget _buildReplyItem(BuildContext context, CommentModel reply, bool isDark) {
    return Container(
      padding: CommentResponsive.getCommentItemPadding(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 用户信息（不显示楼层编号）
          _buildUserInfo(context, isDark, reply),
          
          SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
          
          // 回复内容
          _buildCommentText(context, isDark, reply),
          
          SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
          
          // 操作按钮
          _buildActionButtons(context, isDark, reply),
        ],
      ),
    );
  }

  /// 构建评论内容
  Widget _buildCommentContent(BuildContext context, bool isDark) {
    final indent = CommentHierarchyManager.getReplyIndent(context, comment.level);
    
    return Container(
      margin: EdgeInsets.only(left: indent),
      child: _buildCommentItem(context, isDark),
    );
  }

  /// 构建评论项
  Widget _buildCommentItem(BuildContext context, bool isDark) {
    return Container(
      padding: CommentResponsive.getCommentItemPadding(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 楼层编号和用户信息
          Row(
            children: [
              // 楼层编号
              Container(
                width: 32,
                height: 24,
                decoration: BoxDecoration(
                  color: isDark 
                    ? AppColors.dark.backgroundTertiary 
                    : AppColors.light.backgroundTertiary,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Center(
                  child: Text(
                    '${comment.floorNumber}',
                    style: TextStyle(
                      fontSize: CommentResponsive.getFontSize(context, CommentFontSize.small),
                      fontWeight: FontWeight.w600,
                      color: isDark 
                        ? AppColors.dark.foregroundSecondary 
                        : AppColors.light.foregroundSecondary,
                    ),
                  ),
                ),
              ),
              
              SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
              
              // 用户信息
              Expanded(child: _buildUserInfo(context, isDark)),
            ],
          ),
          
          SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
          
          // 评论内容
          _buildCommentText(context, isDark),
          
          SizedBox(height: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
          
          // 操作按钮
          _buildActionButtons(context, isDark),
        ],
      ),
    );
  }

  /// 构建用户信息
  Widget _buildUserInfo(BuildContext context, bool isDark, [CommentModel? targetComment]) {
    final commentData = targetComment ?? comment;
    final avatarSize = CommentResponsive.getAvatarSize(context);
    final fontSize = CommentResponsive.getFontSize(context, CommentFontSize.small);
    
    return Row(
      children: [
        // 头像
        GestureDetector(
          onTap: () => onUserTap?.call(commentData),
          child: CircleAvatar(
            radius: avatarSize / 2,
            backgroundImage: commentData.avatar != null && commentData.avatar!.isNotEmpty
              ? NetworkImage(commentData.avatar!)
              : null,
            backgroundColor: isDark 
              ? AppColors.dark.backgroundSecondary 
              : AppColors.light.backgroundSecondary,
            child: commentData.avatar == null || commentData.avatar!.isEmpty
              ? Icon(Icons.person, size: avatarSize / 2)
              : null,
          ),
        ),
        
        SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
        
        // 用户名和角色
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    commentData.displayName,
                    style: TextStyle(
                      fontSize: fontSize,
                      fontWeight: FontWeight.w600,
                      color: isDark 
                        ? AppColors.dark.foregroundPrimary 
                        : AppColors.light.foregroundPrimary,
                    ),
                  ),
                  
                  if (commentData.isAuthor) ...[
                    SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
                    Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs),
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.primaryColor,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        '作者',
                        style: TextStyle(
                          fontSize: CommentResponsive.getFontSize(context, CommentFontSize.caption),
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ],
                  
                  if (comment.roleTypeText.isNotEmpty) ...[
                    SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
                    Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs),
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: isDark 
                          ? AppColors.dark.backgroundTertiary 
                          : AppColors.light.backgroundTertiary,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        commentData.roleTypeText,
                        style: TextStyle(
                          fontSize: CommentResponsive.getFontSize(context, CommentFontSize.caption),
                          color: isDark 
                            ? AppColors.dark.foregroundSecondary 
                            : AppColors.light.foregroundSecondary,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
              
              // 位置、设备和时间
              Text(
                '${commentData.location ?? ''} ${commentData.deviceInfo ?? ''} ${commentData.timeAgo}',
                style: TextStyle(
                  fontSize: CommentResponsive.getFontSize(context, CommentFontSize.caption),
                  color: isDark 
                    ? AppColors.dark.foregroundTertiary 
                    : AppColors.light.foregroundTertiary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// 构建评论文本
  Widget _buildCommentText(BuildContext context, bool isDark, [CommentModel? targetComment]) {
    final commentData = targetComment ?? comment;
    final fontSize = CommentResponsive.getFontSize(context, CommentFontSize.body);
    
    return Text(
      commentData.text,
      style: TextStyle(
        fontSize: fontSize,
        color: isDark 
          ? AppColors.dark.foregroundPrimary 
          : AppColors.light.foregroundPrimary,
      ),
    );
  }

  /// 构建操作按钮
  Widget _buildActionButtons(BuildContext context, bool isDark, [CommentModel? targetComment]) {
    final commentData = targetComment ?? comment;
    return Row(
      children: [
        // 点赞按钮
        if (commentData.canLike) ...[
          GestureDetector(
            onTap: () => onLike?.call(commentData),
            child: Row(
              children: [
                Icon(
                  commentData.isLiked ? Icons.thumb_up : Icons.thumb_up_outlined,
                  size: CommentResponsive.getCommentItemIconSize(context),
                  color: commentData.isLiked 
                    ? AppColors.success 
                    : (isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary),
                ),
                if (commentData.likes > 0) ...[
                  SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
                  Text(
                    '${commentData.likes}',
                    style: TextStyle(
                      fontSize: CommentResponsive.getFontSize(context, CommentFontSize.caption),
                      color: isDark 
                        ? AppColors.dark.foregroundSecondary 
                        : AppColors.light.foregroundSecondary,
                    ),
                  ),
                ],
              ],
            ),
          ),
          
          SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.md)),
        ],
        
        // 回复按钮
        if (CommentHierarchyManager.canReply(commentData, config)) ...[
          GestureDetector(
            onTap: () => onReply?.call(commentData),
            child: Text(
              UITextConstants.replyTo,
              style: TextStyle(
                fontSize: CommentResponsive.getFontSize(context, CommentFontSize.caption),
                color: AppColors.primaryColor,
              ),
            ),
          ),
          
          SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.md)),
          
          // 点踩按钮
          GestureDetector(
            onTap: () {
              // TODO: 实现点踩功能
            },
            child: Row(
              children: [
                Icon(
                  Icons.thumb_down_outlined,
                  size: CommentResponsive.getCommentItemIconSize(context),
                  color: isDark 
                    ? AppColors.dark.foregroundSecondary 
                    : AppColors.light.foregroundSecondary,
                ),
                SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
                Text(
                  '${Random().nextInt(10)}', // Mock点踩数
                  style: TextStyle(
                    fontSize: CommentResponsive.getFontSize(context, CommentFontSize.caption),
                    color: isDark 
                      ? AppColors.dark.foregroundSecondary 
                      : AppColors.light.foregroundSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
        
        const Spacer(),
        
        // 作者点赞标识
        if (comment.isAuthorLiked) ...[
          Row(
            children: [
              Icon(
                Icons.thumb_up,
                size: CommentResponsive.getCommentItemIconSize(context),
                color: AppColors.primaryColor,
              ),
              SizedBox(width: CommentResponsive.getIntraGroupSpacing(context, SpacingSize.xs)),
              Text(
                UITextConstants.authorLiked,
                style: TextStyle(
                  fontSize: CommentResponsive.getFontSize(context, CommentFontSize.caption),
                  color: AppColors.primaryColor,
                ),
              ),
            ],
          ),
        ],
      ],
    );
  }


}