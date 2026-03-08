// ignore_for_file: unused_element, deprecated_member_use_from_same_package

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer.dart';
import 'package:quwoquan_app/components/comment_system/comment_models.dart' as comment_models;

/// 媒体帖子卡片基类
/// 按照Figma原型设计，包含完整的交互功能和评论显示
abstract class MediaPostCard extends ConsumerStatefulWidget {
  final dynamic post;
  final Function(dynamic, int) onPostTap;
  final Function(String) onUserTap;
  final Function(dynamic)? onLike;
  final Function(dynamic)? onComment;
  final Function(dynamic)? onShare;
  final Function(dynamic)? onBookmark;
  final Function(dynamic)? onMore;
  final bool isFirstPost;

  const MediaPostCard({
    super.key,
    required this.post,
    required this.onPostTap,
    required this.onUserTap,
    this.onLike,
    this.onComment,
    this.onShare,
    this.onBookmark,
    this.onMore,
    this.isFirstPost = false,
  });

  @override
  ConsumerState<MediaPostCard> createState() => _MediaPostCardState();

  /// 子类需要实现的媒体内容构建方法
  Widget buildMediaContent(BuildContext context, bool isDark);
}

class _MediaPostCardState extends ConsumerState<MediaPostCard> {
  bool _isLiked = false;
  bool _isBookmarked = false;
  int _likesCount = 0;
  int _commentsCount = 0;
  int _savesCount = 0;

  @override
  void initState() {
    super.initState();
    _isLiked = widget.post['isLiked'] ?? false;
    _isBookmarked = widget.post['isBookmarked'] ?? false;
    _likesCount = widget.post['likesCount'] ?? 0;
    _commentsCount = widget.post['commentsCount'] ?? 0;
    _savesCount = widget.post['savesCount'] ?? 0;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer(
      builder: (context, ref, child) {
        final isDark = ref.watch(isDarkProvider);

        return Container(
          margin: EdgeInsets.only(
            // 第一个Post与Stories/Tab之间无间距，其他Post之间使用统一间距
            // 使用only方式，只在上方添加间距，确保所有post之间的间距一致（避免symmetric导致的间距叠加）
            top: widget.isFirstPost ? 0 : AppSpacing.postSpacingXs.h,
            bottom: 0, // 底部不添加间距，由下一个post的top提供，确保间距一致
            left: 0,
            right: 0,
          ),
          decoration: BoxDecoration(
            // 浅色模式：post卡片使用乳白色/白色（backgroundPrimary）
            // 深色模式：post卡片使用稍微明亮一点的黑色 (#262626)
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
            borderRadius: widget.isFirstPost
                ? BorderRadius.only(
                    // 第一个post的顶部两个角保持直角
                    topLeft: Radius.zero,
                    topRight: Radius.zero,
                    bottomLeft: Radius.circular(AppSpacing.borderRadius.r),
                    bottomRight: Radius.circular(AppSpacing.borderRadius.r),
                  )
                : BorderRadius.circular(AppSpacing.borderRadius.r),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              // 用户信息头部
              _buildPostHeader(context, isDark),

              // 媒体内容 - 由子类实现
              widget.buildMediaContent(context, isDark),

              // 交互工具栏 - 按照Figma原型设计，包含动效和数字
              _buildInteractionToolbar(context, isDark),

              // 点赞和评论数 - 基于原型代码新增
              _buildLikesAndCommentsCount(context, isDark),

              // 帖子标题
              _buildPostCaption(context, isDark),
            ],
          ),
        );
      },
    );
  }

  /// 处理点赞
  void _handleLike() {
    setState(() {
      _isLiked = !_isLiked;
      _likesCount += _isLiked ? 1 : -1;
    });
    widget.onLike?.call(widget.post);
  }

  /// 处理评论
  void _handleComment() {
    _showCommentViewer();
    widget.onComment?.call(widget.post);
  }

  /// 处理收藏
  void _handleBookmark() {
    setState(() {
      _isBookmarked = !_isBookmarked;
      _savesCount += _isBookmarked ? 1 : -1;
    });
    widget.onBookmark?.call(widget.post);
  }

  /// 处理分享
  void _handleShare() {
    widget.onShare?.call(widget.post);
  }

  /// 处理打赏 - 基于原型代码新增
  void _handleReward() {
    // TODO: 实现打赏功能
    _showToast(AppStrings.rewardFeatureDeveloping);
  }

  /// 处理保存 - 基于原型代码新增
  void _handleSave() {
    // TODO: 实现保存功能
    _showToast(AppStrings.saveFeatureDeveloping);
  }

  /// 处理私信 - 基于原型代码新增
  void _handleMessage() {
    // TODO: 实现私信功能
    _showToast(AppStrings.messageFeatureDeveloping);
  }

  /// 处理复制链接 - 基于原型代码新增
  void _handleCopyLink() {
    // TODO: 实现复制链接功能
    _showToast(AppStrings.linkCopied);
  }

  /// 处理查看原图 - 基于原型代码新增
  void _handleViewOriginal() {
    // TODO: 实现查看原图功能
    _showToast(AppStrings.viewOriginalFeatureDeveloping);
  }

  /// 处理字体设置 - 基于原型代码新增
  void _handleFontSettings() {
    // TODO: 实现字体设置功能
    _showToast(AppStrings.fontSettingsFeatureDeveloping);
  }

  /// 处理主题切换 - 基于原型代码新增
  void _handleThemeToggle() {
    // 切换主题 - 添加mounted检查防止dispose后访问ref
    if (!mounted) return;
    
    try {
      // 立即关闭弹窗，避免在主题切换过程中出现布局异常
      if (Navigator.canPop(context)) {
        Navigator.pop(context);
      }
      
      // 延迟切换主题，确保弹窗关闭完成
      Future.delayed(const Duration(milliseconds: 100), () {
        if (mounted) {
          try {
            ref.read(themeProvider.notifier).toggleTheme();
            // 刷新主组件状态
            setState(() {});
          } catch (e) {
            debugPrint('主题切换失败: $e');
          }
        }
      });
    } catch (e) {
      // 如果出现任何异常，尝试关闭弹窗
      debugPrint('主题切换处理异常: $e');
      if (mounted && Navigator.canPop(context)) {
        Navigator.pop(context);
      }
    }
  }

  /// 处理功能反馈 - 基于原型代码新增
  void _handleFeedback() {
    // TODO: 实现功能反馈功能
    _showToast(AppStrings.feedbackFeatureDeveloping);
  }

  /// 处理不感兴趣 - 基于原型代码新增
  void _handleNotInterested() {
    // TODO: 实现不感兴趣功能
    _showToast(AppStrings.markedAsNotInterested);
  }

  /// 处理屏蔽用户 - 基于原型代码新增
  void _handleBlockUser() {
    // TODO: 实现屏蔽用户功能
    _showToast(AppStrings.userBlocked);
  }

  /// 处理举报 - 基于原型代码新增
  void _handleReport() {
    // TODO: 实现举报功能
    _showToast(AppStrings.reportedContent);
  }

  /// 显示提示信息
  void _showToast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
            margin: EdgeInsets.all(context.safeGetContainerSpacing(SpacingSize.lg)),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8.r),
        ),
      ),
    );
  }

  /// 显示更多选项弹窗 - 使用通用组件
  void _showMoreOptions() {
    final config = MediaPostMoreActionConfig(
      post: widget.post,
      onReward: _handleReward,
      onSave: _handleSave,
      onMessage: _handleMessage,
      onCopyLink: _handleCopyLink,
      onViewOriginal: _handleViewOriginal,
      onFontSettings: _handleFontSettings,
      onThemeToggle: () => _handleThemeToggle(),
      onFeedback: _handleFeedback,
      onNotInterested: _handleNotInterested,
      onBlockUser: _handleBlockUser,
      onReport: _handleReport,
    );
    
    MoreActionPopup.show(
      context: context,
      config: config,
    );
  }





  /// 显示评论查看器
  void _showCommentViewer() {
    CommentViewer.showModal(
      context: context,
      postId: (widget.post['id'] ?? widget.post['postId'] ?? 'mock_post_id').toString(),
    );
  }


  /// 构建用户信息头部 - 基于原型代码增强，支持发布者类型和关注功能
  Widget _buildPostHeader(BuildContext context, bool isDark) {
    final publisherType = widget.post['publisherType'] ?? 'author';
    final isVerified = widget.post['isVerified'] ?? false;

    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.contentSpacingMd.w,  // 使用更小的内容间距
        AppSpacing.contentSpacingMd.h,
        AppSpacing.contentSpacingMd.w,
        AppSpacing.contentSpacingMd.h,
      ),
      child: Row(
        children: [
          // 用户头像 - 基于原型代码增强，支持发布者类型
          GestureDetector(
            onTap: () => widget.onUserTap(widget.post['username']),
            child: Container(
              width: AppSpacing.avatarSize.w,
              height: AppSpacing.avatarSize.w,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                // 移除蓝色边框
              ),
              child: CircleAvatar(
                radius: (AppSpacing.avatarSize / 2).r,
                backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
                backgroundImage:
                    widget.post['publisher']?['avatar']?.isNotEmpty == true
                        ? NetworkImage(widget.post['publisher']['avatar'])
                        : null,
                child: widget.post['publisher']?['avatar']?.isEmpty != false
                    ? Icon(Icons.person,
                        size: AppSpacing.iconMedium, // 使用语义标签
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary))
                    : null,
              ),
            ),
          ),
          SizedBox(
              width: context
                              .safeGetIntraGroupSpacing(SpacingSize.sm)
                  .w),

          // 用户名和时间 - 基于原型代码增强
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 用户名和认证标识
                Row(
                  children: [
                    GestureDetector(
                      onTap: () => widget.onUserTap(widget.post['username']),
                      child: Text(
                        publisherType == 'circle'
                            ? (widget.post['displayName'] ??
                                widget.post['username'] ??
                                UITextConstants.unknownUser)
                            : (widget.post['username'] ??
                                UITextConstants.unknownUser),
                        style: TextStyle(
                          fontWeight: AppTypography.medium,
                          fontSize: AppTypography.base, // 使用语义标签
                          color: isDark
                              ? AppColors.dark.foregroundPrimary
                              : AppColors.light.foregroundPrimary,
                        ),
                      ),
                    ),
                    // 认证标识 - 基于原型代码
                    if (isVerified) ...[
                      SizedBox(width: AppSpacing.smallBorderRadius.w),
                      Container(
                        width: AppSpacing.iconSmall.w,
                        height: AppSpacing.iconSmall.w,
                        decoration: BoxDecoration(
                          color: AppColors.primaryColor,
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          Icons.check,
                          size: AppTypography.xs, // 使用语义标签
                          color: AppColors.white,
                        ),
                      ),
                    ],
                    SizedBox(width: AppSpacing.smallBorderRadius.w),
                    Text(
                      '•',
                      style: TextStyle(
                        fontSize: AppTypography.sm, // 使用语义标签
                        color: isDark
                            ? AppColors.dark.foregroundSecondary
                            : AppColors.light.foregroundSecondary,
                      ),
                    ),
                    SizedBox(width: AppSpacing.smallBorderRadius.w),
                    Text(
                      _formatTimeAgo(widget.post['createdAt']),
                      style: TextStyle(
                        fontSize: AppTypography.sm, // 使用语义标签
                        color: isDark
                            ? AppColors.dark.foregroundSecondary
                            : AppColors.light.foregroundSecondary,
                      ),
                    ),
                  ],
                ),

                // IP地址标签 - 显示作品发布时的IP地址
                Text(
                  _getLocationFromIP(widget.post['publishIP'] ?? '192.168.1.1'),
                  style: TextStyle(
                    fontSize: AppTypography.sm, // 使用语义标签
                    color: isDark
                        ? AppColors.dark.foregroundSecondary
                        : AppColors.light.foregroundSecondary,
                  ),
                ),
              ],
            ),
          ),

          // 更多选项按钮
          GestureDetector(
            onTap: _showMoreOptions,
            child: Padding(
              padding: EdgeInsets.all(context
                              .safeGetIntraGroupSpacing(SpacingSize.sm)
                  .w),
              child: Icon(
                Icons.more_horiz,
                size: AppSpacing.iconMedium, // 使用语义标签
                color: isDark
                    ? AppColors.dark.foregroundSecondary // 黑夜模式使用次颜色
                    : AppColors.light.foregroundSecondary,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// 处理关注功能 - 基于原型代码新增
  void _handleFollow() {
    // TODO: 实现关注功能
    _showToast(AppStrings.feedbackFeatureDeveloping);
  }

  /// 根据IP地址获取地理位置标签
  String _getLocationFromIP(String ip) {
    // 模拟IP地址到地理位置的映射
    final ipLocationMap = {
      '192.168.1.1': '北京',
      '192.168.1.2': '上海',
      '192.168.1.3': '广州',
      '192.168.1.4': '深圳',
      '192.168.1.5': '杭州',
      '192.168.1.6': '成都',
      '192.168.1.7': '武汉',
      '192.168.1.8': '西安',
      '192.168.1.9': '南京',
      '192.168.1.10': '重庆',
    };
    
    return ipLocationMap[ip] ?? '未知地区';
  }

  /// 构建交互工具栏 - 按照Figma原型设计，包含动效和数字
  Widget _buildInteractionToolbar(BuildContext context, bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.contentSpacingMd.w,  // 使用更小的内容间距
        vertical: AppSpacing.contentSpacingMd.h,
      ),
      child: Row(
        children: [
          // 点赞按钮
          _buildInteractionButton(
            iconWidget: Icon(
              _isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
              size: AppSpacing.iconSmall,
              color: _isLiked
                  ? AppColors.error
                  : (isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary),
            ),
            count: _likesCount,
            isActive: _isLiked,
            onTap: _handleLike,
            isDark: isDark,
            buttonKey: TestKeys.likeButton,
            countKey: TestKeys.likeCountText,
          ),

          SizedBox(
            width: context.safeGetInterGroupSpacing(SpacingSize.lg).w,
          ),

          // 收藏按钮
          _buildInteractionButton(
            iconWidget: AppStarIcon(
              size: AppSpacing.iconSmall,
              color: _isBookmarked
                  ? AppColors.warning
                  : (isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary),
              filled: _isBookmarked,
            ),
            count: _savesCount,
            isActive: _isBookmarked,
            onTap: _handleBookmark,
            isDark: isDark,
          ),

          SizedBox(
            width: context.safeGetInterGroupSpacing(SpacingSize.lg).w,
          ),

          // 评论按钮
          _buildInteractionButton(
            iconWidget: AppBubbleIcon(
              size: AppSpacing.iconSmall,
              color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
            ),
            count: _commentsCount,
            isActive: false,
            onTap: _handleComment,
            isDark: isDark,
            buttonKey: TestKeys.commentButton,
            countKey: TestKeys.commentCountText,
          ),

          SizedBox(
            width: context.safeGetInterGroupSpacing(SpacingSize.sm).w,
          ),

          // 转发按钮 - 与左组固定组间间距
          _buildShareButton(isDark),
        ],
      ),
    );
  }

  /// 构建交互按钮，包含图标 Widget、数字和动效
  Widget _buildInteractionButton({
    required Widget iconWidget,
    required int count,
    required bool isActive,
    required VoidCallback? onTap,
    required bool isDark,
    Key? buttonKey,
    Key? countKey,
  }) {
    return GestureDetector(
      key: buttonKey,
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: EdgeInsets.symmetric(
          horizontal: context
                              .safeGetIntraGroupSpacing(SpacingSize.sm)
              .w,
          vertical: context
                    .safeGetIntraGroupSpacing(SpacingSize.xs)
              .h,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedScale(
              scale: isActive ? 1.1 : 1.0,
              duration: const Duration(milliseconds: 200),
              child: iconWidget,
            ),
            SizedBox(
                width: context
                    .safeGetIntraGroupSpacing(SpacingSize.xs)
                    .w),
            SizedBox(
              width: 40.w,
              child: Text(
                count > 0 ? _formatCount(count) : '',
                key: countKey,
                style: TextStyle(
                  fontSize: AppTypography.actionCount,
                  color: isDark
                      ? AppColors.dark.foregroundSecondary
                      : AppColors.light.foregroundSecondary,
                  fontWeight: AppTypography.medium,
                ),
                textAlign: TextAlign.left,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 构建转发按钮 - 不显示数字，靠右对齐
  Widget _buildShareButton(bool isDark) {
    return GestureDetector(
      onTap: _handleShare,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: context
                              .safeGetIntraGroupSpacing(SpacingSize.sm)
              .w,
          vertical: context
                    .safeGetIntraGroupSpacing(SpacingSize.xs)
              .h,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              CupertinoIcons.arrowshape_turn_up_right,
              size: AppSpacing.iconSmall,
              color: isDark
                  ? AppColors.dark.foregroundPrimary
                  : AppColors.light.foregroundPrimary,
            ),
          ],
        ),
      ),
    );
  }

  /// 构建点赞和评论数显示 - 基于原型代码新增
  Widget _buildLikesAndCommentsCount(BuildContext context, bool isDark) {
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.contentSpacingMd.w,  // 使用更小的内容间距
        vertical: AppSpacing.contentSpacingXs.h,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 点赞数显示
          if (_likesCount > 0)
            Padding(
              padding: EdgeInsets.only(
                  bottom: context
                    .safeGetIntraGroupSpacing(SpacingSize.xs)
                      .h),
              child: Row(
                children: [
                  Text(
                    _formatCount(_likesCount),
                    style: TextStyle(
                      fontSize: AppTypography.base, // 使用语义标签
                      fontWeight: AppTypography.semiBold,
                      color: isDark
                          ? AppColors.dark.foregroundPrimary
                          : AppColors.light.foregroundPrimary,
                    ),
                  ),
                  SizedBox(width: 4.w),
                  Text(
                    AppStrings.likes,
                    style: TextStyle(
                      fontSize: AppTypography.base, // 使用语义标签
                      color: isDark
                          ? AppColors.dark.foregroundSecondary
                          : AppColors.light.foregroundSecondary,
                    ),
                  ),
                ],
              ),
            ),

          // 评论数显示
          if (_commentsCount > 0)
            GestureDetector(
              onTap: _handleComment,
              child: Text(
                '${AppStrings.viewAllComments} $_commentsCount ${AppStrings.comments}',
                style: TextStyle(
                  fontSize: AppTypography.base, // 使用语义标签
                  color: isDark
                      ? AppColors.dark.foregroundSecondary
                      : AppColors.light.foregroundSecondary,
                ),
              ),
            ),
        ],
      ),
    );
  }

  /// 构建帖子标题
  Widget _buildPostCaption(BuildContext context, bool isDark) {
    final caption = widget.post['caption'] ?? '';
    if (caption.isEmpty) return const SizedBox.shrink();

    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.contentSpacingMd.w,  // 使用更小的内容间距
        vertical: AppSpacing.contentSpacingXs.h,
      ),
      child: RichText(
        text: TextSpan(
          children: [
            TextSpan(
              text: widget.post['username'] ?? 'Unknown User',
              style: TextStyle(
                fontWeight: AppTypography.medium,
                fontSize: AppTypography.base, // 使用语义标签
                color: isDark
                    ? AppColors.dark.foregroundPrimary
                    : AppColors.light.foregroundPrimary,
              ),
            ),
            TextSpan(
              text: ' $caption',
              style: TextStyle(
                fontSize: AppTypography.base, // 使用语义标签
                color: isDark
                    ? AppColors.dark.foregroundPrimary
                    : AppColors.light.foregroundPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 格式化时间
  String _formatTimeAgo(dynamic createdAt) {
    if (createdAt == null) return AppStrings.justNow;

    try {
      final now = DateTime.now();
      final created = DateTime.parse(createdAt.toString());
      final difference = now.difference(created);

      if (difference.inMinutes < 1) {
        return AppStrings.justNow;
      } else if (difference.inMinutes < 60) {
        return '${difference.inMinutes}${AppStrings.minutesAgo}';
      } else if (difference.inHours < 24) {
        return '${difference.inHours}${AppStrings.hoursAgo}';
      } else if (difference.inDays < 7) {
        return '${difference.inDays}${AppStrings.daysAgo}';
      } else {
        return '${created.month}${AppStrings.monthDay}${created.day}';
      }
    } catch (e) {
      return AppStrings.justNow;
    }
  }

  /// 格式化数量显示 - 按照Figma原型设计，确保数字长度可控
  String _formatCount(int count) {
    if (count == 0) {
      return ''; // 若是0不显示
    } else if (count >= 100000) {
      return AppStrings.tenThousandPlus; // 超过10万显示"10万+"
    } else if (count >= 10000) {
      return '${(count / 10000).toStringAsFixed(1)}万'; // 万前带一个小数点，比如1.1万
    } else {
      return count.toString(); // 小于万就全部数字显示，比如9999
    }
  }


  /// 处理评论添加
  void _handleCommentAdded(String content) {
    _showToast(UITextConstants.commentSent);
    // TODO: 实现实际的评论添加逻辑
  }

  /// 处理评论点赞
  void _handleCommentLiked(comment_models.CommentModel comment) {
    _showToast(AppStrings.likeSuccess);
    // TODO: 实现实际的评论点赞逻辑
  }
  
  void _handleCommentLikedById(String commentId) {
    _showToast(AppStrings.likeSuccess);
    // TODO: 实现实际的评论点赞逻辑
  }

  /// 处理回复添加
  void _handleReplyAdded(String commentId, String content) {
    _showToast(AppStrings.replySent);
    // TODO: 实现实际的回复添加逻辑
  }

  /// 处理用户点击
  void _handleUserTapped(String userId) {
    _showToast(AppStrings.goToUserProfile);
    // TODO: 实现跳转到用户主页的逻辑
  }

  /// 处理加载更多评论
  void _handleLoadMoreComments(String postId) {
    _showToast(AppStrings.loadMoreComments);
    // TODO: 实现加载更多评论的逻辑
  }

  /// 处理评论关闭
  void _handleCommentClosed() {
    // TODO: 实现评论关闭时的清理逻辑
  }
}
