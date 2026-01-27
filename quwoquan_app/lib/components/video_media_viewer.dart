import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/video_player_widget.dart';

/// 视频媒体查看器
/// 继承自侵入式媒体浏览器，专门处理视频播放
class VideoMediaViewer extends ConsumerStatefulWidget {
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
  final String? source;
  final Map<String, dynamic>? userProfileData;
  final bool isCommentsOpen;
  final double commentsHeight;

  const VideoMediaViewer({
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
    this.commentsHeight = 0.0,
  });

  @override
  ConsumerState<VideoMediaViewer> createState() => _VideoMediaViewerState();
}

class _VideoMediaViewerState extends ConsumerState<VideoMediaViewer> {
  late PageController _pageController;
  int _currentIndex = 0;
  bool _isPlaying = false;
  String? _currentVideoUrl;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    _pageController = PageController(initialPage: widget.initialIndex);
  }

  @override
  void dispose() {
    _pageController.dispose();
    if (_currentVideoUrl != null) {
      VideoPlayerManager.disposeController(_currentVideoUrl!);
    }
    super.dispose();
  }

  void _onPageChanged(int index) {
    setState(() {
      _currentIndex = index;
      _isPlaying = false;
    });
  }

  void _togglePlayPause() {
    setState(() {
      _isPlaying = !_isPlaying;
    });
  }

  Widget _buildVideoPlayer(String videoUrl, String? thumbnailUrl) {
    return VideoPlayerWidget(
      videoUrl: videoUrl,
      thumbnailUrl: thumbnailUrl,
      autoPlay: _isPlaying,
      showControls: true,
      onTap: _togglePlayPause,
      aspectRatio: 9 / 16, // 竖屏视频比例
    );
  }

  Widget _buildTopBar() {
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        // 顶部工具栏直接贴到顶部，包括状态栏区域
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
        child: SafeArea(
          top: false, // 不添加顶部安全区域，让工具栏贴到顶部
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md.w),
            child: Row(
              children: [
                // 返回按钮
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
                
                // 视频指示器
                if (widget.mediaItems.length > 1) ...[
                  SizedBox(width: AppSpacing.md.w),
                  Expanded(
                    child: Row(
                      children: List.generate(widget.mediaItems.length, (index) {
                        return Container(
                          width: (MediaQuery.of(context).size.width - AppSpacing.avatarSize * 2 - AppSpacing.md * 2) / widget.mediaItems.length,
                          height: 2.h,
                          margin: EdgeInsets.only(right: index < widget.mediaItems.length - 1 ? 2.w : 0),
                          decoration: BoxDecoration(
                            color: index == _currentIndex 
                                ? AppColors.white 
                                : AppColors.overlayMedium,
                            borderRadius: BorderRadius.circular(1.h),
                          ),
                        );
                      }),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBottomBar() {
    final isDark = ref.watch(isDarkProvider);
    final currentPost = widget.posts[_currentIndex];
    final isFollowing = widget.followingUsers?.contains(currentPost['username']) ?? false;

    return Positioned(
      bottom: 0,
      left: 0,
      right: 0,
      child: Container(
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
        child: SafeArea(
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.md.w),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // 用户信息
                Row(
                  children: [
                    // 用户头像
                    GestureDetector(
                      onTap: () => widget.onUserClick(currentPost['username']),
                      child: Container(
                        width: AppSpacing.avatarSize.w,
                        height: AppSpacing.avatarSize.w,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: AppColors.primaryColor,
                            width: 2,
                          ),
                        ),
                        child: CircleAvatar(
                          radius: (AppSpacing.avatarSize / 2).w,
                          backgroundColor: isDark ? AppColors.dark.backgroundTertiary : AppColors.light.backgroundTertiary,
                          backgroundImage: currentPost['avatar']?.isNotEmpty == true
                              ? NetworkImage(currentPost['avatar'])
                              : null,
                          child: currentPost['avatar']?.isEmpty != false
                              ? Icon(
                                  Icons.person,
                                  color: isDark ? AppColors.dark.foregroundTertiary : AppColors.light.foregroundTertiary,
                                  size: AppSpacing.iconMedium.sp,
                                )
                              : null,
                        ),
                      ),
                    ),
                    
                    SizedBox(width: AppSpacing.sm.w),
                    
                    // 用户信息
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            currentPost['displayName'] ?? currentPost['username'] ?? UITextConstants.user,
                            style: TextStyle(
                              color: AppColors.white,
                              fontSize: AppTypography.base.sp,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                          SizedBox(height: 2.h),
                          Text(
                            '@${currentPost['username']}',
                            style: TextStyle(
                              color: AppColors.overlayStrong,
                              fontSize: AppTypography.sm.sp,
                            ),
                          ),
                        ],
                      ),
                    ),
                    
                    // 关注按钮
                    if (!widget.isBlocked)
                      GestureDetector(
                        onTap: () => widget.onFollowClick?.call(currentPost['username'], !isFollowing),
                        child: Container(
                          padding: EdgeInsets.symmetric(
                            horizontal: AppSpacing.md.w,
                            vertical: AppSpacing.sm.h,
                          ),
                          decoration: BoxDecoration(
                            color: isFollowing 
                                ? (isDark ? AppColors.dark.backgroundTertiary : AppColors.light.backgroundTertiary)
                                : AppColors.primaryColor,
                            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
                          ),
                          child: Text(
                            isFollowing ? UITextConstants.following : UITextConstants.follow,
                            style: TextStyle(
                              color: isFollowing 
                                  ? (isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary)
                                  : AppColors.white,
                              fontSize: AppTypography.xs.sp,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
                
                SizedBox(height: AppSpacing.md.h),
                
                // 操作按钮
                Row(
                  children: [
                    // 点赞按钮
                    _buildActionButton(
                      icon: Icons.favorite,
                      count: widget.getPostLikesCount?.call(currentPost) ?? 0,
                      isActive: widget.likedPosts?.contains(currentPost['id']) ?? false,
                      onTap: () => widget.onLikeClick?.call(currentPost),
                    ),
                    
                    SizedBox(width: AppSpacing.lg.w),
                    
                    // 评论按钮
                    _buildActionButton(
                      icon: Icons.chat_bubble_outline,
                      count: currentPost['commentsCount'] ?? 0,
                      onTap: () => widget.onCommentsClick?.call(currentPost),
                    ),
                    
                    SizedBox(width: AppSpacing.lg.w),
                    
                    // 保存按钮
                    _buildActionButton(
                      icon: Icons.bookmark_outline,
                      count: widget.getPostBookmarksCount?.call(currentPost) ?? 0,
                      isActive: widget.savedPosts?.contains(currentPost['id']) ?? false,
                      onTap: () => widget.onSaveClick?.call(currentPost),
                    ),
                    
                    SizedBox(width: AppSpacing.lg.w),
                    
                    // 分享按钮
                    _buildActionButton(
                      icon: Icons.share,
                      onTap: () => widget.onShareClick?.call(currentPost),
                    ),
                    
                    const Spacer(),
                    
                    // 更多按钮
                    _buildActionButton(
                      icon: Icons.more_horiz,
                      onTap: () => widget.onMoreClick?.call(currentPost),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildActionButton({
    required IconData icon,
    int count = 0,
    bool isActive = false,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            color: isActive ? AppColors.primaryColor : AppColors.white,
            size: AppSpacing.iconLarge.sp,
          ),
          if (count > 0) ...[
            SizedBox(height: 2.h),
            Text(
              count > 1000 ? '${(count / 1000).toStringAsFixed(1)}k' : count.toString(),
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.xs.sp,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isOpen) return const SizedBox.shrink();

    final isDark = ref.watch(isDarkProvider);
    
    return Scaffold(
      backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      body: Stack(
        children: [
          // 视频播放器
          PageView.builder(
            controller: _pageController,
            onPageChanged: _onPageChanged,
            itemCount: widget.mediaItems.length,
            itemBuilder: (context, index) {
              final mediaItem = widget.mediaItems[index];
              if (mediaItem.type == 'video') {
                return _buildVideoPlayer(mediaItem.url, null);
              }
              return const SizedBox.shrink();
            },
          ),
          
          // 顶部工具栏
          _buildTopBar(),
          
          // 底部工具栏
          _buildBottomBar(),
        ],
      ),
    );
  }
}
