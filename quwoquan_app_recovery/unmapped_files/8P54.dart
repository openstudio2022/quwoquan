import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:photo_view/photo_view.dart';
import 'package:photo_view/photo_view_gallery.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'video_player_widget.dart';
import 'more_actions_popup/configs/media_post_config.dart';
import 'comment_system/comment_viewer.dart';
import 'comment_system/comment_models.dart';
import 'more_actions_popup/more_action_popup.dart';

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
            child: PhotoViewGallery.builder(
              pageController: _pageController,
              itemCount: widget.posts.length,
              onPageChanged: _handlePageChanged,
              builder: (context, index) {
                final post = widget.posts[index];
                final mediaItem = widget.mediaItems.isNotEmpty 
                    ? widget.mediaItems[index % widget.mediaItems.length]
                    : MediaItem(type: 'image', url: 'https://picsum.photos/400/400?random=999');

                return PhotoViewGalleryPageOptions(
                  imageProvider: NetworkImage(mediaItem.url),
                  minScale: PhotoViewComputedScale.contained,
                  maxScale: PhotoViewComputedScale.covered * 2.0,
                  heroAttributes: PhotoViewHeroAttributes(
                    tag: 'photo_${post['id']}_$index',
                  ),
                  onTapDown: (context, details, controllerValue) {
                    _toggleControls();
                  },
                );
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
        height: context.safeGetContainerSpacing(SpacingSize.xl) + 20,
        padding: EdgeInsets.symmetric(
          horizontal: context.safeGetContainerSpacing(SpacingSize.md),
          vertical: context.safeGetIntraGroupSpacing(SpacingSize.md),
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
                      borderRadius: BorderRadius.circular(16),
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

            const Spacer(),

            // 中间：作者信息（UserProfile模式）
            if (widget.source == 'userProfile' && currentPost != null)
              Expanded(
                child: Center(
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // 添加作者头像（更小的尺寸）
                      if (currentPost['avatar'] != null)
                        CircleAvatar(
                          radius: 12,
                          backgroundImage: NetworkImage(currentPost['avatar']),
                        )
                      else
                        CircleAvatar(
                          radius: 12,
                          backgroundColor: Colors.grey[600],
                          child: Icon(Icons.person, color: Colors.white, size: 12),
                        ),
                      
                      SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
                      
                      Flexible(
                        child: Text(
                          currentPost['displayName'] ?? currentPost['username'] ?? UITextConstants.user,
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: AppTypography.base,
                            fontWeight: FontWeight.w600,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      
                      if (widget.onFollowClick != null) ...[
                        SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
                        GestureDetector(
                          onTap: _handleFollowClick,
                          child: Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: context.safeGetContainerSpacing(SpacingSize.xs),
                              vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs),
                            ),
                            decoration: BoxDecoration(
                              color: _isFollowing 
                                  ? (isDark ? AppColors.dark.backgroundTertiary : AppColors.light.backgroundTertiary)
                                  : AppColors.primaryColor,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              _isFollowing ? UITextConstants.following : UITextConstants.follow,
                              style: TextStyle(
                                color: _isFollowing 
                                    ? (isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary)
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

            const Spacer(),

            // 右侧：更多操作按钮
            GestureDetector(
              onTap: _handleMoreClick,
              child: Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.5),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Icon(
                  Icons.more_horiz,
                  color: Colors.white,
                  size: 20,
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
                  radius: 20,
                  backgroundImage: currentPost?['avatar'] != null 
                      ? NetworkImage(currentPost['avatar'])
                      : null,
                  backgroundColor: isDark 
                      ? AppColors.dark.backgroundSecondary
                      : AppColors.light.backgroundSecondary,
                  child: currentPost?['avatar'] == null 
                      ? Icon(Icons.person, color: Colors.white, size: 20)
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
                            ? (isDark ? AppColors.dark.backgroundTertiary : AppColors.light.backgroundTertiary)
                            : AppColors.primaryColor,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        _isFollowing ? UITextConstants.following : UITextConstants.follow,
                        style: TextStyle(
                          color: _isFollowing 
                              ? (isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary)
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
              icon: _isLiked ? Icons.favorite : Icons.favorite_border,
              count: _likesCount,
              isActive: _isLiked,
              activeColor: AppColors.error,
              onTap: _handleLikeClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: Icons.chat_bubble_outline,
              count: _commentsCount,
              onTap: _handleCommentsClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: _isSaved ? Icons.bookmark : Icons.bookmark_border,
              count: _savesCount,
              isActive: _isSaved,
              activeColor: AppColors.warning,
              onTap: _handleSaveClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: Icons.share,
              count: _sharesCount,
              onTap: _handleShareClick,
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
              icon: _isLiked ? Icons.favorite : Icons.favorite_border,
              count: _likesCount,
              isActive: _isLiked,
              activeColor: AppColors.error,
              onTap: _handleLikeClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: Icons.chat_bubble_outline,
              count: _commentsCount,
              onTap: _handleCommentsClick,
            ),
            
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.md)),
            
            _buildActionButton(
              context: context,
              icon: _isSaved ? Icons.bookmark : Icons.bookmark_border,
              count: _savesCount,
              isActive: _isSaved,
              activeColor: AppColors.warning,
              onTap: _handleSaveClick,
            ),
          ],
        ),
        
        // 右侧：分享按钮
        _buildActionButton(
          context: context,
          icon: Icons.share,
          count: _sharesCount,
          onTap: _handleShareClick,
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
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(18),
            ),
            child: Icon(
              icon,
              color: isActive ? (activeColor ?? AppColors.primaryColor) : Colors.white,
              size: 20,
            ),
          ),
          
          SizedBox(height: 2),
          
          Text(
            count.toString(),
            style: TextStyle(
              color: Colors.white,
              fontSize: AppTypography.xs,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
