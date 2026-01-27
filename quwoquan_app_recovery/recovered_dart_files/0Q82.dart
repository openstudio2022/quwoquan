import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:photo_view/photo_view.dart';
import 'package:photo_view/photo_view_gallery.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 图片浏览器组件 - 基于原型代码实现
/// 支持状态与Post同步，包含更多功能、点赞、收藏、评论、转发
class ImageViewer extends ConsumerStatefulWidget {
  final bool isOpen;
  final VoidCallback onClose;
  final List<String> imageUrls;
  final int initialIndex;
  final dynamic post;
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

  const ImageViewer({
    super.key,
    required this.isOpen,
    required this.onClose,
    required this.imageUrls,
    required this.initialIndex,
    required this.post,
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
  });

  @override
  ConsumerState<ImageViewer> createState() => _ImageViewerState();
}

class _ImageViewerState extends ConsumerState<ImageViewer> with TickerProviderStateMixin {
  late PageController _pageController;
  late AnimationController _fadeController;
  late AnimationController _slideController;
  
  int _currentIndex = 0;
  bool _showControls = true;
  bool _isLiked = false;
  bool _isSaved = false;
  int _likesCount = 0;
  int _savesCount = 0;
  int _commentsCount = 0;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    _pageController = PageController(initialPage: _currentIndex);
    
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    
    _slideController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    
    _initializePostState();
    
    // 自动隐藏控制栏
    _startAutoHideTimer();
  }

  void _initializePostState() {
    if (widget.post != null) {
      _isLiked = widget.likedPosts?.contains(widget.post['id']?.toString()) ?? false;
      _isSaved = widget.savedPosts?.contains(widget.post['id']?.toString()) ?? false;
      _likesCount = widget.getPostLikesCount?.call(widget.post) ?? 0;
      _savesCount = widget.getPostBookmarksCount?.call(widget.post) ?? 0;
      _commentsCount = widget.post['commentsCount'] ?? 0;
    }
  }

  void _startAutoHideTimer() {
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted && _showControls) {
        setState(() {
          _showControls = false;
        });
        _fadeController.reverse();
      }
    });
  }

  void _toggleControls() {
    setState(() {
      _showControls = !_showControls;
    });
    
    if (_showControls) {
      _fadeController.forward();
      _startAutoHideTimer();
    } else {
      _fadeController.reverse();
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    _fadeController.dispose();
    _slideController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isOpen) return const SizedBox.shrink();
    
    final isDark = ref.watch(isDarkProvider);
    
    return Material(
      color: Colors.black,
      child: Stack(
        children: [
          // 图片画廊
          _buildImageGallery(isDark),
          
          // 控制栏
          if (_showControls) _buildControls(isDark),
          
          // 底部操作栏
          if (_showControls) _buildBottomBar(isDark),
          
          // 关闭按钮
          if (_showControls) _buildCloseButton(isDark),
        ],
      ),
    );
  }

  /// 构建图片画廊 - 基于原型代码
  Widget _buildImageGallery(bool isDark) {
    return GestureDetector(
      onTap: _toggleControls,
      child: PhotoViewGallery.builder(
        pageController: _pageController,
        itemCount: widget.imageUrls.length,
        onPageChanged: (index) {
          setState(() {
            _currentIndex = index;
          });
        },
        builder: (context, index) {
          return PhotoViewGalleryPageOptions(
            imageProvider: NetworkImage(widget.imageUrls[index]),
            minScale: PhotoViewComputedScale.contained,
            maxScale: PhotoViewComputedScale.covered * 2.0,
            heroAttributes: PhotoViewHeroAttributes(tag: 'image_${widget.post['id']}_$index'),
          );
        },
        scrollPhysics: const BouncingScrollPhysics(),
        backgroundDecoration: const BoxDecoration(color: Colors.black),
        loadingBuilder: (context, event) => Center(
          child: CircularProgressIndicator(
            color: AppColors.primaryColor,
            value: event == null ? null : event.cumulativeBytesLoaded / event.expectedTotalBytes!,
          ),
        ),
      ),
    );
  }

  /// 构建控制栏 - 基于原型代码
  Widget _buildControls(bool isDark) {
    return AnimatedBuilder(
      animation: _fadeController,
      builder: (context, child) {
        return FadeTransition(
          opacity: _fadeController,
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withOpacity(0.7),
                  Colors.transparent,
                ],
              ),
            ),
            child: SafeArea(
              child: Padding(
                padding: EdgeInsets.all(16.w),
                child: Column(
                  children: [
                    // 顶部信息栏
                    _buildTopInfoBar(isDark),
                    const Spacer(),
                    // 图片指示器
                    if (widget.imageUrls.length > 1) _buildImageIndicator(),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  /// 构建顶部信息栏 - 基于原型代码
  Widget _buildTopInfoBar(bool isDark) {
    return Row(
      children: [
        // 用户信息
        Expanded(
          child: GestureDetector(
            onTap: () => widget.onUserClick(widget.post['username']),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 20.r,
                  backgroundImage: widget.post['publisher']?['avatar']?.isNotEmpty == true
                      ? NetworkImage(widget.post['publisher']['avatar'])
                      : null,
                  child: widget.post['publisher']?['avatar']?.isEmpty != false
                      ? Icon(Icons.person, color: Colors.white)
                      : null,
                ),
                SizedBox(width: 12.w),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.post['username'] ?? UITextConstants.unknownUser,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 16.sp,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      Text(
                        _formatTimeAgo(widget.post['createdAt']),
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.7),
                          fontSize: 12.sp,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        
        // 更多选项按钮
        GestureDetector(
          onTap: _showMoreOptions,
          child: Container(
            padding: EdgeInsets.all(8.w),
            child: Icon(
              Icons.more_horiz,
              color: Colors.white,
              size: 24.sp,
            ),
          ),
        ),
      ],
    );
  }

  /// 构建图片指示器 - 基于原型代码
  Widget _buildImageIndicator() {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: 16.w, vertical: 8.h),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: List.generate(widget.imageUrls.length, (index) {
          return Container(
            margin: EdgeInsets.symmetric(horizontal: 2.w),
            width: 8.w,
            height: 8.w,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: index == _currentIndex 
                  ? Colors.white 
                  : Colors.white.withOpacity(0.3),
            ),
          );
        }),
      ),
    );
  }

  /// 构建底部操作栏 - 基于原型代码
  Widget _buildBottomBar(bool isDark) {
    return AnimatedBuilder(
      animation: _fadeController,
      builder: (context, child) {
        return FadeTransition(
          opacity: _fadeController,
          child: Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.bottomCenter,
                end: Alignment.topCenter,
                colors: [
                  Colors.black.withOpacity(0.7),
                  Colors.transparent,
                ],
              ),
            ),
            child: SafeArea(
              child: Padding(
                padding: EdgeInsets.all(16.w),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // 交互按钮
                    _buildInteractionButtons(isDark),
                    SizedBox(height: 16.h),
                    // 点赞和评论数
                    _buildLikesAndCommentsCount(isDark),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  /// 构建交互按钮 - 基于原型代码
  Widget _buildInteractionButtons(bool isDark) {
    return Row(
      children: [
        // 点赞按钮
        _buildInteractionButton(
          icon: _isLiked ? Icons.favorite : Icons.favorite_border,
          count: _likesCount,
          isActive: _isLiked,
          activeColor: Colors.red,
          onTap: _handleLike,
        ),
        
        SizedBox(width: 24.w),
        
        // 评论按钮
        _buildInteractionButton(
          icon: Icons.comment_outlined, // 使用锚点居中的评论图标
          count: _commentsCount,
          isActive: false,
          activeColor: Colors.blue,
          onTap: _handleComment,
        ),
        
        SizedBox(width: 24.w),
        
        // 收藏按钮
        _buildInteractionButton(
          icon: _isSaved ? Icons.star : Icons.star_border,
          count: _savesCount,
          isActive: _isSaved,
          activeColor: Colors.amber,
          onTap: _handleSave,
        ),
        
        const Spacer(),
        
        // 分享按钮
        GestureDetector(
          onTap: _handleShare,
          child: Container(
            padding: EdgeInsets.all(8.w),
            child: Icon(
              Icons.share_outlined,
              color: Colors.white,
              size: 24.sp,
            ),
          ),
        ),
      ],
    );
  }

  /// 构建交互按钮
  Widget _buildInteractionButton({
    required IconData icon,
    required int count,
    required bool isActive,
    required Color activeColor,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          AnimatedScale(
            scale: isActive ? 1.1 : 1.0,
            duration: const Duration(milliseconds: 200),
            child: Icon(
              icon,
              size: 24.sp,
              color: isActive ? activeColor : Colors.white,
            ),
          ),
          if (count > 0) ...[
            SizedBox(width: 8.w),
            Text(
              _formatCount(count),
              style: TextStyle(
                color: Colors.white,
                fontSize: 14.sp,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// 构建点赞和评论数显示
  Widget _buildLikesAndCommentsCount(bool isDark) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 点赞数
        if (_likesCount > 0)
          Padding(
            padding: EdgeInsets.only(bottom: 8.h),
            child: Row(
              children: [
                Text(
                  _formatCount(_likesCount),
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16.sp,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                SizedBox(width: 4.w),
                Text(
                  '个赞',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 16.sp,
                  ),
                ),
              ],
            ),
          ),
        
        // 评论数
        if (_commentsCount > 0)
          GestureDetector(
            onTap: _handleComment,
            child: Text(
              '查看全部 $_commentsCount 条评论',
              style: TextStyle(
                color: Colors.white.withOpacity(0.7),
                fontSize: 14.sp,
              ),
            ),
          ),
      ],
    );
  }

  /// 构建关闭按钮
  Widget _buildCloseButton(bool isDark) {
    return AnimatedBuilder(
      animation: _fadeController,
      builder: (context, child) {
        return FadeTransition(
          opacity: _fadeController,
          child: Positioned(
            top: 50.h,
            right: 16.w,
            child: GestureDetector(
              onTap: widget.onClose,
              child: Container(
                padding: EdgeInsets.all(8.w),
                decoration: BoxDecoration(
                  color: Colors.black.withOpacity(0.5),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.close,
                  color: Colors.white,
                  size: 24.sp,
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  /// 显示更多选项
  void _showMoreOptions() {
    // 添加mounted检查，防止在widget销毁后访问ref
    if (!mounted) return;
    
    final isDark = ref.watch(isDarkProvider);
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Container(
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(20.r),
            topRight: Radius.circular(20.r),
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 拖拽指示器
            Container(
              width: 40.w,
              height: 4.h,
              margin: EdgeInsets.only(top: 12.h, bottom: 20.h),
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
                borderRadius: BorderRadius.circular(2.r),
              ),
            ),
            
            // 功能列表
            _buildMoreOptionItem(Icons.card_giftcard, '打赏', isDark, () => _handleReward()),
            _buildMoreOptionItem(Icons.download, '保存', isDark, () => _handleSave()),
            _buildMoreOptionItem(Icons.message_outlined, '私信', isDark, () => _handleMessage()),
            _buildMoreOptionItem(Icons.link, UITextConstants.copyLink, isDark, () => _handleCopyLink()),
            _buildMoreOptionItem(Icons.image_outlined, '查看原图', isDark, () => _handleViewOriginal()),
            
            SizedBox(height: 20.h),
          ],
        ),
      ),
    );
  }

  /// 构建更多选项项目
  Widget _buildMoreOptionItem(IconData icon, String title, bool isDark, VoidCallback onTap) {
    return ListTile(
      leading: Icon(
        icon,
        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
        size: 20.sp,
      ),
      title: Text(
        title,
        style: TextStyle(
          color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
          fontSize: 16.sp,
          fontWeight: FontWeight.w500,
        ),
      ),
      onTap: () {
        Navigator.pop(context);
        onTap();
      },
    );
  }

  // 交互处理方法
  void _handleLike() {
    setState(() {
      _isLiked = !_isLiked;
      _likesCount += _isLiked ? 1 : -1;
    });
        widget.onLikeClick?.call(widget.post);
  }

  void _handleComment() {
    widget.onCommentsClick?.call(widget.post);
  }

  void _handleSave() {
    setState(() {
      _isSaved = !_isSaved;
      _savesCount += _isSaved ? 1 : -1;
    });
    widget.onSaveClick?.call(widget.post);
  }

  void _handleShare() {
    widget.onShareClick?.call(widget.post);
  }

  void _handleReward() {
    _showToast('打赏功能开发中...');
  }

  void _handleMessage() {
    _showToast('私信功能开发中...');
  }

  void _handleCopyLink() {
    _showToast('链接已复制');
  }

  void _handleViewOriginal() {
    _showToast('查看原图功能开发中...');
  }

  void _showToast(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        margin: EdgeInsets.all(16.w),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8.r),
        ),
      ),
    );
  }

  /// 格式化时间
  String _formatTimeAgo(dynamic createdAt) {
    if (createdAt == null) return '刚刚';
    
    try {
      final now = DateTime.now();
      final created = DateTime.parse(createdAt.toString());
      final difference = now.difference(created);
      
      if (difference.inMinutes < 1) {
        return '刚刚';
      } else if (difference.inMinutes < 60) {
        return '${difference.inMinutes}分钟前';
      } else if (difference.inHours < 24) {
        return '${difference.inHours}小时前';
      } else if (difference.inDays < 7) {
        return '${difference.inDays}天前';
      } else {
        return '${created.month}月${created.day}日';
      }
    } catch (e) {
      return '刚刚';
    }
  }

  /// 格式化数量显示
  String _formatCount(int count) {
    if (count >= 1000000) {
      return '${(count / 1000000).toStringAsFixed(1)}M';
    } else if (count >= 10000) {
      return '${(count / 10000).toStringAsFixed(1)}万';
    } else if (count >= 1000) {
      return '${(count / 1000).toStringAsFixed(1)}k';
    } else {
      return count.toString();
    }
  }
}
