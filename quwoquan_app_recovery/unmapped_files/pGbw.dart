import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:photo_view/photo_view.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/video_player_widget.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/shared/components/comment_system/comment_viewer.dart';
import 'package:quwoquan_app/shared/components/comment_system/comment_models.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_popup.dart';

/// 媒体项接口
class MediaItem {
  final String type; // 'image' | 'video'
  final String url;
  final double? aspectRatio;

  const MediaItem({
    required this.type,
    required this.url,
    this.aspectRatio,
  });
}

/// 沉浸式媒体查看器 - 基于Figma原型实现
/// 支持与作者主页、评论和帖子的完整联动
class ImmersiveMediaViewer extends ConsumerStatefulWidget {
  final bool isOpen;
  final VoidCallback onClose;
  final List<MediaItem> mediaItems;
  final int initialIndex;
  final List<dynamic> posts;
  final int initialPostIndex;
  final Function(String) onUserClick;
  final Function(String, bool)? onFollowClick;
  final Function(dynamic)? onCommentsClick;
  final Function(dynamic)? onMoreClick;
  final Function(dynamic)? onLikeClick;
  final Function(dynamic)? onSaveClick;
  final Function(dynamic)? onShareClick;
  final Set<String>? followingUsers;
  final Set<String>? savedPosts;
  final Set<String>? likedPosts;
  final Function(dynamic)? getPostLikesCount;
  final Function(dynamic)? getPostBookmarksCount;
  final bool isBlocked;
  final String? source; // 'feed' | 'userProfile'
  final Map<String, dynamic>? userProfileData;
  final bool isCommentsOpen;
  final double commentsHeight;
  final bool enableHeroAnimation;
  final Map<String, dynamic>? heroAnimationSource;
  final Function(String)? onHeroAnimationComplete;

  const ImmersiveMediaViewer({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.mediaItems,
    required this.initialIndex,
    required this.posts,
    required this.initialPostIndex,
    required this.onUserClick,
    this.onFollowClick,
    this.onCommentsClick,
    this.onMoreClick,
    this.onLikeClick,
    this.onSaveClick,
    this.onShareClick,
    this.followingUsers,
    this.savedPosts,
    this.likedPosts,
    this.getPostLikesCount,
    this.getPostBookmarksCount,
    this.isBlocked = false,
    this.source,
    this.userProfileData,
    this.isCommentsOpen = false,
    this.commentsHeight = 0,
    this.enableHeroAnimation = false,
    this.heroAnimationSource,
    this.onHeroAnimationComplete,
  });

  @override
  ConsumerState<ImmersiveMediaViewer> createState() => _ImmersiveMediaViewerState();
}

class _ImmersiveMediaViewerState extends ConsumerState<ImmersiveMediaViewer> 
    with TickerProviderStateMixin {
  late PageController _pageController;
  late AnimationController _fadeController;
  late AnimationController _controlsController;
  
  int _currentPostIndex = 0;
  bool _showControls = true;
  
  // 本地状态
  bool _isLiked = false;
  bool _isSaved = false;
  bool _isFollowing = false;
  int _likesCount = 0;
  int _savesCount = 0;
  int _commentsCount = 0;
  final int _sharesCount = 95;

  @override
  void initState() {
    super.initState();
    _currentPostIndex = widget.initialPostIndex;
    
    _pageController = PageController(initialPage: _currentPostIndex);
    
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    
    _controlsController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );
    _controlsController.value = 1.0; // 默认显示工具栏
    
    _initializePostState();
    _startAutoHideTimer();
  }

  @override
  void dispose() {
    _pageController.dispose();
    _fadeController.dispose();
    _controlsController.dispose();
    super.dispose();
  }

  void _initializePostState() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      _isLiked = widget.likedPosts?.contains(currentPost['id']?.toString()) ?? false;
      _isSaved = widget.savedPosts?.contains(currentPost['id']?.toString()) ?? false;
      _isFollowing = widget.followingUsers?.contains(currentPost['username']) ?? false;
      _likesCount = widget.getPostLikesCount?.call(currentPost) ?? 0;
      _savesCount = widget.getPostBookmarksCount?.call(currentPost) ?? 0;
      _commentsCount = currentPost['commentsCount'] ?? 0;
    }
  }

  void _startAutoHideTimer() {
    // 在用户主页模式下不自动隐藏工具栏
    if (widget.source == 'userProfile') return;
    
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted && _showControls) {
        setState(() {
          _showControls = false;
        });
        _controlsController.reverse();
      }
    });
  }

  void _toggleControls() {
    setState(() {
      _showControls = !_showControls;
    });
    
    if (_showControls) {
      _controlsController.forward();
      _startAutoHideTimer();
    } else {
      _controlsController.reverse();
    }
  }

  void _handlePageChanged(int index) {
    setState(() {
      _currentPostIndex = index;
    });
    _initializePostState();
  }

  void _handleLikeClick() {
    setState(() {
      _isLiked = !_isLiked;
      if (_isLiked) {
        _likesCount++;
      } else {
        _likesCount = (_likesCount - 1).clamp(0, double.infinity).toInt();
      }
    });
    
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      widget.onLikeClick?.call(widget.posts[_currentPostIndex]);
    }
  }

  void _handleSaveClick() {
    setState(() {
      _isSaved = !_isSaved;
      if (_isSaved) {
        _savesCount++;
      } else {
        _savesCount = (_savesCount - 1).clamp(0, double.infinity).toInt();
      }
    });
    
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      widget.onSaveClick?.call(widget.posts[_currentPostIndex]);
    }
  }

  void _handleFollowClick() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      setState(() {
        _isFollowing = !_isFollowing;
      });
      widget.onFollowClick?.call(currentPost['username'], _isFollowing);
    }
  }

  void _handleCommentsClick() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      
      // 显示评论弹窗
      final commentConfig = CommentConfig(
        postId: currentPost['id'] ?? 'mock_post_id',
        postAuthorId: currentPost['username'] ?? 'mock_author_id',
        allowComments: true,
        isUserLoggedIn: true,
        isUserAuthor: false,
      );

      CommentViewer.showModal(
        context: context,
        postId: currentPost['id'] ?? 'mock_post_id',
        initialComments: [],
        config: commentConfig,
        modalHeight: CommentModalHeight.adaptive,
        onCommentAdded: (commentId) {
          debugPrint('Comment added: $commentId');
        },
        onCommentLiked: (comment) {
          debugPrint('Comment liked: ${comment.id}');
        },
        onReplyAdded: (commentId, replyId) {
          debugPrint('Reply added: $replyId to $commentId');
        },
        onUserTapped: (comment) {
          debugPrint('User tapped: ${comment.username}');
        },
        onLoadMore: () {
          debugPrint('Load more comments');
        },
        onClose: () {
          debugPrint('Comment modal closed');
        },
      );
    }
  }

  void _handleMoreClick() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      
      // 显示更多操作弹窗
      final config = MediaPostMoreActionConfig(
        post: currentPost,
        onReward: () => debugPrint('Reward post: ${currentPost['id']}'),
        onSave: () => _handleSaveClick(),
        onMessage: () => debugPrint('Message user: ${currentPost['username']}'),
        onCopyLink: () => debugPrint('Copy link: ${currentPost['id']}'),
        onViewOriginal: () => debugPrint('View original: ${currentPost['id']}'),
        onFontSettings: () => debugPrint('Font settings'),
        onThemeToggle: () => debugPrint('Theme toggle'),
        onFeedback: () => debugPrint('Feedback'),
        onNotInterested: () => debugPrint('Not interested'),
        onBlockUser: () => debugPrint('Block user: ${currentPost['username']}'),
        onReport: () => debugPrint('Report post: ${currentPost['id']}'),
      );

      MoreActionPopup.show(
        context: context,
        config: config,
      );
    }
  }

  void _handleShareClick() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      widget.onShareClick?.call(currentPost);
    }
  }

  void _handleAuthorClick() {
    if (widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length) {
      final currentPost = widget.posts[_currentPostIndex];
      widget.onUserClick(currentPost['username']);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isOpen) return const SizedBox.shrink();

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final currentPost = widget.posts.isNotEmpty && _currentPostIndex < widget.posts.length 
        ? widget.posts[_currentPostIndex] 
        : null;

    return Material(
      color: Colors.black,
      child: SafeArea(
        child: Stack(
          children: [
          // 媒体内容区域
          GestureDetector(
            onTap: _toggleControls,
            child: PageView.builder(
              controller: _pageController,
              itemCount: widget.posts.length,
              onPageChanged: _handlePageChanged,
              itemBuilder: (context, index) {
                final post = widget.posts[index];
                final mediaItem = widget.mediaItems.isNotEmpty 
                    ? widget.mediaItems[index % widget.mediaItems.length]
                    : MediaItem(type: 'image', url: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df9?w=400&h=400&fit=crop');

                // 根据媒体类型选择不同的显示方式
                if (mediaItem.type == 'video') {
                  return GestureDetector(
                    onTap: _toggleControls,
                    child: VideoPlayerWidget(
                      videoUrl: mediaItem.url,
                      autoPlay: index == _currentPostIndex,
                      showControls: true,
                      aspectRatio: mediaItem.aspectRatio ?? 9 / 16,
                      onTap: _toggleControls,
                    ),
                  );
                } else {
                  return GestureDetector(
                    onTap: _toggleControls,
                    child: PhotoView(
                      imageProvider: NetworkImage(mediaItem.url),
                      minScale: PhotoViewComputedScale.contained,
                      maxScale: PhotoViewComputedScale.covered * 2.0,
                      heroAttributes: PhotoViewHeroAttributes(
                        tag: 'photo_${post['id']}_$index',
                      ),
                      onTapDown: (context, details, controllerValue) {
                        _toggleControls();
                      },
                    ),
                  );
                }
              },
            ),
          ),

          // 头部工具栏
          AnimatedBuilder(
            animation: _controlsController,
            builder: (context, child) {
              return _buildHeaderBar(context, currentPost, isDark);
            },
          ),

          // 底部工具栏
          AnimatedBuilder(
            animation: _controlsController,
            builder: (context, child) {
              return _buildBottomBar(context, currentPost, isDark);
            },
          ),
        ],
        ),
      ),
    );
  }

  Widget _buildHeaderBar(BuildContext context, dynamic currentPost, bool isDark) {
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Opacity(
        opacity: _controlsController.value,
        child: Container(
        padding: EdgeInsets.only(
          left: context.safeGetContainerSpacing(SpacingSize.md),
          right: context.safeGetContainerSpacing(SpacingSize.md),
          top: MediaQuery.of(context).padding.top + context.safeGetIntraGroupSpacing(SpacingSize.sm), // 考虑状态栏高度
          bottom: context.safeGetIntraGroupSpacing(SpacingSize.sm), // 增加底部padding，避免位置指示器被遮挡
        ),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              AppColors.overlayStrong,
              Colors.transparent,
            ],
          ),
        ),
        child: Row(
          children: [
            // 左侧：返回按钮和数值指示器
            Row(
              children: [
                GestureDetector(
                  onTap: widget.onClose,
                  child: Container(
                    width: AppSpacing.avatarSize,
                    height: AppSpacing.avatarSize,
                    decoration: BoxDecoration(
                      color: AppColors.overlayDark,
                      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
                    ),
                    child: Icon(
                      Icons.arrow_back_ios,
                      color: AppColors.white,
                      size: AppSpacing.smallButtonSize,
                    ),
                  ),
                ),
                
                if (widget.posts.length > 1) ...[
                  SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
                  Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
                      vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.overlayDark,
                      borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
                    ),
                    child: Text(
                      '${_currentPostIndex + 1} / ${widget.posts.length}',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: AppTypography.sm,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ],
            ),

            // 中间：作者信息（UserProfile模式）- 居中显示
            if (widget.source == 'userProfile' && currentPost != null)
              Expanded(
                child: Center(
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      // 作者头像 - 使用较小尺寸，节省空间
                      if (currentPost['avatar'] != null)
                        CircleAvatar(
                          radius: AppSpacing.iconSmall / 2, // 使用语义图标尺寸
                          backgroundImage: NetworkImage(currentPost['avatar']),
                        )
                      else
                        CircleAvatar(
                          radius: AppSpacing.iconSmall / 2, // 使用语义图标尺寸
                          backgroundColor: Colors.grey[600],
                          child: Icon(Icons.person, color: Colors.white, size: AppSpacing.iconSmall),
                        ),
                      
                      SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.xs)), // 使用较小间距
                      
                      Flexible(
                        child: Text(
                          currentPost['displayName'] ?? currentPost['username'] ?? UITextConstants.user,
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: AppTypography.sm, // 使用较小字体，节省空间
                            fontWeight: FontWeight.w600,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      
                      if (widget.onFollowClick != null) ...[
                        SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.xs)), // 使用较小间距
                        GestureDetector(
                          onTap: _handleFollowClick,
                          child: Container(
                            width: AppSpacing.followButtonWidth, // 使用语义常量，固定按钮宽度
                            padding: EdgeInsets.symmetric(
                              horizontal: context.safeGetContainerSpacing(SpacingSize.sm), // 使用语义水平padding，确保文字完整显示且不溢出
                              vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs), // 使用语义垂直padding，确保美观对称
                            ),
                            decoration: BoxDecoration(
                              color: _isFollowing 
                                  ? AppColors.overlayDark // 使用半透明黑色背景，在暗色背景下更美观
                                  : AppColors.primaryColor,
                              borderRadius: BorderRadius.circular(AppSpacing.borderRadius), // 使用语义化圆角
                              border: _isFollowing ? Border.all(
                                color: Colors.white.withValues(alpha: 0.2), // 已关注状态添加淡边框，更美观
                                width: 1,
                              ) : null,
                            ),
                            child: Center(
                              child: Text(
                                _isFollowing ? UITextConstants.following : UITextConstants.follow,
                                style: TextStyle(
                                  color: Colors.white, // 统一使用白色文字，在暗色背景下更清晰
                                  fontSize: AppTypography.sm, // 使用语义字体大小，确保不溢出且清晰
                                  fontWeight: FontWeight.w600, // 使用更粗的字体，更清晰美观
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis, // 防止溢出
                              ),
                            ),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              )
            else
              const Spacer(),

            // 右侧：更多操作按钮
            GestureDetector(
              onTap: _handleMoreClick,
              child: Container(
                width: AppSpacing.avatarSize,
                height: AppSpacing.avatarSize,
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius / 2),
                ),
                child: Icon(
                  Icons.more_horiz,
                  color: Colors.white,
                  size: AppSpacing.smallButtonSize,
                ),
              ),
            ),
          ],
        ),
      ),
      ),
    );
  }

  Widget _buildBottomBar(BuildContext context, dynamic currentPost, bool isDark) {
    return Positioned(
      bottom: 0,
      left: 0,
      right: 0,
      child: Opacity(
        opacity: _controlsController.value,
        child: Container(
        padding: EdgeInsets.all(context.safeGetContainerSpacing(SpacingSize.md)),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.bottomCenter,
            end: Alignment.topCenter,
            colors: [
              AppColors.overlayStrong,
              Colors.transparent,
            ],
          ),
        ),
        child: widget.source == 'feed' 
            ? _buildFeedBottomBar(context, currentPost, isDark)
            : _buildUserProfileBottomBar(context, currentPost, isDark),
      ),
      ),
    );
  }

  Widget _buildFeedBottomBar(BuildContext context, dynamic currentPost, bool isDark) {
    return Row(
      children: [
        // 左侧：作者信息
        Expanded(
          child: GestureDetector(
            onTap: _handleAuthorClick,
            child: Row(
              children: [
                CircleAvatar(
                  radius: AppSpacing.circularBorderRadius / 2,
                  backgroundImage: currentPost?['avatar'] != null 
                      ? NetworkImage(currentPost['avatar'])
                      : null,
                  backgroundColor: isDark 
                      ? AppColors.dark.backgroundSecondary
                      : AppColors.light.backgroundSecondary,
                  child: currentPost?['avatar'] == null 
                      ? Icon(Icons.person, color: Colors.white, size: AppSpacing.smallButtonSize)
                      : null,
                ),
                
                SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
                
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        currentPost?['displayName'] ?? currentPost?['username'] ?? UITextConstants.user,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: AppTypography.base,
                          fontWeight: FontWeight.w600,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                
                if (widget.onFollowClick != null) ...[
                  GestureDetector(
                    onTap: _handleFollowClick,
                    child: Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
                        vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
                      ),
                      decoration: BoxDecoration(
                        color: _isFollowing 
                            ? AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary)
                            : AppColors.primaryColor,
                        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
                      ),
                      child: Text(
                        _isFollowing ? UITextConstants.following : UITextConstants.follow,
                        style: TextStyle(
                          color: _isFollowing 
                              ? AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary)
                              : Colors.white,
                          fontSize: AppTypography.xs,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
        
        SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
        
        // 右侧：操作按钮
        Row(
          children: [
            _buildActionButton(
              context: context,
              icon: _isLiked ? Icons.favorite : Icons.favorite_outlined,
              count: _likesCount,
              isActive: _isLiked,
              activeColor: AppColors.error,
              onTap: _handleLikeClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: Icons.chat_bubble_outline, // 使用简洁的评论图标（无中间三横）
              count: _commentsCount,
              onTap: _handleCommentsClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: _isSaved ? Icons.star : Icons.star_border, // 使用五角星图标，与瀑布流保持一致
              count: _savesCount,
              isActive: _isSaved,
              activeColor: Colors.amber, // 使用amber颜色，与图片瀑布流保持一致
              onTap: _handleSaveClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: Icons.ios_share, // 使用更直观简洁的分享图标
              count: _sharesCount,
              onTap: _handleShareClick,
              showCount: false, // 分享按钮不显示数字
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildUserProfileBottomBar(BuildContext context, dynamic currentPost, bool isDark) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        // 左侧：前三个按钮
        Row(
          children: [
            _buildActionButton(
              context: context,
              icon: _isLiked ? Icons.favorite : Icons.favorite_outlined,
              count: _likesCount,
              isActive: _isLiked,
              activeColor: AppColors.error,
              onTap: _handleLikeClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: Icons.chat_bubble_outline, // 使用简洁的评论图标（无中间三横）
              count: _commentsCount,
              onTap: _handleCommentsClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: _isSaved ? Icons.star : Icons.star_border, // 使用五角星图标，与瀑布流保持一致
              count: _savesCount,
              isActive: _isSaved,
              activeColor: Colors.amber, // 使用amber颜色，与图片瀑布流保持一致
              onTap: _handleSaveClick,
            ),
          ],
        ),
        
        // 右侧：分享按钮
        _buildActionButton(
          context: context,
          icon: Icons.share_outlined,
          count: _sharesCount,
          onTap: _handleShareClick,
          showCount: false, // 分享按钮不显示数字
        ),
      ],
    );
  }

  Widget _buildActionButton({
    required BuildContext context,
    required IconData icon,
    required int count,
    required VoidCallback onTap,
    bool isActive = false,
    Color? activeColor,
    bool showCount = true, // 是否显示数字，默认显示
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: AppSpacing.largeButtonSize * 0.75,
            height: AppSpacing.largeButtonSize * 0.75,
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular((AppSpacing.largeButtonSize * 0.75) / 2),
            ),
            child: Icon(
              icon,
              color: isActive ? (activeColor ?? AppColors.primaryColor) : Colors.white,
              size: AppSpacing.iconMedium, // 使用统一的图标大小，确保所有图标协调
            ),
          ),
          
          if (showCount) ...[
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
            Text(
              count.toString(),
              style: TextStyle(
                color: Colors.white,
                fontSize: AppTypography.xs,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
