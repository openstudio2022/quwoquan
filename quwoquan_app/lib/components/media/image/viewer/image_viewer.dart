// ignore_for_file: unused_element

import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:photo_view/photo_view.dart';
import 'package:photo_view/photo_view_gallery.dart';

import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/spacing/spacing_extensions.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/media_viewer_toolbar.dart';

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
  bool _isFollowing = false;
  int _likesCount = 0;
  int _savesCount = 0;
  int _commentsCount = 0;
  int _sharesCount = 0;
  bool _isPureMode = false;
  bool _isCaptionExpanded = false;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
    _pageController = PageController(initialPage: _currentIndex);
    
    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _fadeController.value = 1.0;
    
    _slideController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    
    _initializePostState();
    
    // 自动隐藏控制栏
    _startAutoHideTimer();
    _applySystemUiMode();
  }

  void _initializePostState() {
    if (widget.post != null) {
      _isLiked = widget.likedPosts?.contains(widget.post['id']?.toString()) ?? false;
      _isSaved = widget.savedPosts?.contains(widget.post['id']?.toString()) ?? false;
      _isFollowing = widget.followingUsers?.contains(widget.post['username']) ?? false;
      _likesCount = widget.getPostLikesCount?.call(widget.post) ?? 0;
      _savesCount = widget.getPostBookmarksCount?.call(widget.post) ?? 0;
      _commentsCount = widget.post['commentsCount'] ?? 0;
      _sharesCount = widget.post['sharesCount'] ?? widget.post['shareCount'] ?? 0;
    }
  }

  void _startAutoHideTimer() {
    return;
  }

  void _toggleControls() {
    if (_showControls) {
      // 先执行淡出动画，动画结束后再更新状态，避免控件被立即移出树导致无淡出效果
      _fadeController.reverse();
      void listener(AnimationStatus status) {
        if (status == AnimationStatus.dismissed) {
          _fadeController.removeStatusListener(listener);
          if (mounted) {
            setState(() {
              _showControls = false;
              _isPureMode = true;
            });
            _applySystemUiMode();
          }
        }
      }
      _fadeController.addStatusListener(listener);
    } else {
      setState(() {
        _showControls = true;
        _isPureMode = false;
      });
      _fadeController.forward();
      _applySystemUiMode();
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    _fadeController.dispose();
    _slideController.dispose();
    _restoreSystemUiMode();
    super.dispose();
  }

  void _applySystemUiMode() {
    if (_isPureMode) {
      SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);
      SystemChrome.setSystemUIOverlayStyle(
        const SystemUiOverlayStyle(
          statusBarColor: Colors.transparent,
          statusBarIconBrightness: Brightness.dark,
          statusBarBrightness: Brightness.light,
          systemNavigationBarColor: Colors.transparent,
          systemNavigationBarIconBrightness: Brightness.dark,
        ),
      );
      return;
    }

    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: Colors.transparent,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
  }

  void _restoreSystemUiMode() {
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.dark,
        statusBarBrightness: Brightness.light,
        systemNavigationBarColor: Colors.transparent,
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.isOpen) return const SizedBox.shrink();
    
    final isDark = ref.watch(isDarkProvider);
    
    return Material(
      color: AppColors.black,
      child: Stack(
        children: [
          // 图片画廊
          _buildImageGallery(isDark),

          // 控制栏与文案（始终构建以便 FadeTransition 能淡出，用 IgnorePointer 在纯模式屏蔽点击）
          Positioned.fill(
            child: FadeTransition(
              opacity: _fadeController,
              child: IgnorePointer(
                ignoring: _isPureMode,
                child: Column(
                  children: [
                    MediaViewerTopBar(
                      onBack: widget.onClose,
                      positionText: '${_currentIndex + 1}/${widget.imageUrls.length}',
                      authorName: _getAuthorName(),
                      authorAvatarUrl: _getAuthorAvatar(),
                      isFollowing: _isFollowing,
                      onFollow: _handleFollow,
                      onAuthorTap: _handleAuthorTap,
                      onMore: _showMoreOptions,
                      showPosition: widget.imageUrls.length > 1,
                    ),
                    const Spacer(),
                    _buildCaptionOverlay(context),
                    Align(
                      alignment: Alignment.bottomCenter,
                      child: MediaViewerBottomBar(
                        shareCount: _sharesCount,
                        commentCount: _commentsCount,
                        likeCount: _likesCount,
                        isLiked: _isLiked,
                        onShare: _handleShare,
                        onComment: _handleComment,
                        onLike: _handleLike,
                        onAssistant: null,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
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
        backgroundDecoration: const BoxDecoration(color: AppColors.black),
        loadingBuilder: (context, event) => Center(
          child: CupertinoActivityIndicator(),
        ),
      ),
    );
  }

  String _getAuthorName() {
    return widget.post?['displayName']?.toString() ??
        widget.post?['username']?.toString() ??
        widget.post?['publisher']?['displayName']?.toString() ??
        widget.post?['publisher']?['username']?.toString() ??
        UITextConstants.unknownUser;
  }

  String? _getAuthorAvatar() {
    return widget.post?['avatar']?.toString() ??
        widget.post?['publisher']?['avatar']?.toString();
  }

  Widget _buildCaptionOverlay(BuildContext context) {
    final title = widget.post?['title']?.toString() ?? '';
    final caption = (widget.post?['content'] ?? widget.post?['caption'])?.toString() ?? '';
    if (title.isEmpty && caption.isEmpty) return const SizedBox.shrink();

    final bottomOffset = MediaQuery.of(context).padding.bottom +
        AppSpacing.buttonHeight +
        context.safeGetIntraGroupSpacing(SpacingSize.md);

    return Align(
      alignment: Alignment.centerLeft,
      child: Padding(
        padding: EdgeInsets.only(
          left: context.safeGetContainerSpacing(SpacingSize.md),
          right: context.safeGetContainerSpacing(SpacingSize.md),
          bottom: bottomOffset,
        ),
        child: ClipRect(
          child: BackdropFilter(
            filter: ImageFilter.blur(
              sigmaX: AppSpacing.sm,
              sigmaY: AppSpacing.sm,
            ),
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: context.safeGetContainerSpacing(SpacingSize.xs),
                vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
              ),
              decoration: BoxDecoration(
                color: AppColors.overlayLight,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (title.isNotEmpty)
                    Padding(
                      padding: EdgeInsets.only(
                        bottom: context.safeGetIntraGroupSpacing(SpacingSize.xs),
                      ),
                      child: Text(
                        title,
                        style: TextStyle(
                          color: AppColors.white,
                          fontSize: AppTypography.lg,
                          fontWeight: AppTypography.medium,
                        ),
                      ),
                    ),
                  if (caption.isNotEmpty)
                    _buildExpandableCaption(
                      context,
                      caption: caption,
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildExpandableCaption(
    BuildContext context, {
    required String caption,
  }) {
    final captionStyle = TextStyle(
      color: AppColors.white,
      fontSize: AppTypography.base,
      fontWeight: AppTypography.normal,
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        // 溢出判断必须使用固定行数，不能依赖 _isCaptionExpanded：若用 maxLines: expanded ? null : 3，
        // didExceedMaxLines 在展开时恒为 false，会走下面 early return 导致无法显示「收起」按钮。
        const int captionOverflowMaxLines = 3;
        final overflowPainter = TextPainter(
          text: TextSpan(text: caption, style: captionStyle),
          maxLines: captionOverflowMaxLines,
          textDirection: TextDirection.ltr,
        )..layout(maxWidth: constraints.maxWidth);
        final isOverflow = overflowPainter.didExceedMaxLines;

        if (!isOverflow) {
          return Text(caption, style: captionStyle);
        }

        return GestureDetector(
          onTap: () {
            setState(() {
              _isCaptionExpanded = !_isCaptionExpanded;
            });
          },
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: _isCaptionExpanded
                      ? caption
                      : _truncateCaption(caption, overflowPainter, constraints.maxWidth),
                  style: captionStyle,
                ),
                TextSpan(
                  text: _isCaptionExpanded ? UITextConstants.collapse : UITextConstants.fullText,
                  style: captionStyle.copyWith(
                    color: AppColors.primaryColor,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  String _truncateCaption(String caption, TextPainter textPainter, double maxWidth) {
    final position = textPainter.getPositionForOffset(Offset(maxWidth, textPainter.height));
    final truncatedLength = (position.offset - 4).clamp(0, caption.length);
    return '${caption.substring(0, truncatedLength)}${UITextConstants.ellipsis}';
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
                  AppColors.overlayStrong,
                  Colors.transparent,
                ],
              ),
            ),
            child: SafeArea(
              child: Padding(
                padding: EdgeInsets.all(AppSpacing.md.w),
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
                      ? Icon(Icons.person, color: AppColors.white)
                      : null,
                ),
                SizedBox(width: AppSpacing.interGroupSm.w),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.post['username'] ?? UITextConstants.unknownUser,
                        style: TextStyle(
                          color: AppColors.white,
                          fontSize: AppTypography.lg,
                          fontWeight: AppTypography.semiBold,
                        ),
                      ),
                      Text(
                        _formatTimeAgo(widget.post['createdAt']),
                        style: TextStyle(
                          color: AppColors.overlayStrong,
                          fontSize: AppTypography.sm,
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
            padding: EdgeInsets.all(AppSpacing.sm.w),
            child: Icon(
              Icons.more_horiz,
              color: AppColors.white,
              size: AppSpacing.iconMedium,
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
            width: AppSpacing.sm.w,
            height: AppSpacing.sm.w,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: index == _currentIndex 
                  ? AppColors.white 
                  : AppColors.overlayMedium,
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
                    // 交互按钮
                    _buildInteractionButtons(isDark),
                    SizedBox(height: AppSpacing.md.h),
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
          iconWidget: Icon(
            _isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
            size: AppSpacing.iconMedium,
            color: _isLiked ? AppColors.error : AppColors.white,
          ),
          count: _likesCount,
          isActive: _isLiked,
          onTap: _handleLike,
        ),
        
        SizedBox(width: AppSpacing.interGroupSm),
        
        // 收藏按钮
        _buildInteractionButton(
          iconWidget: AppStarIcon(
            size: AppSpacing.iconMedium,
            color: _isSaved ? AppColors.warning : AppColors.white,
            filled: _isSaved,
          ),
          count: _savesCount,
          isActive: _isSaved,
          onTap: _handleSave,
        ),
        
        SizedBox(width: AppSpacing.interGroupSm),
        
        // 评论按钮
        _buildInteractionButton(
          iconWidget: AppBubbleIcon(
            size: AppSpacing.iconMedium,
            color: AppColors.white,
          ),
          count: _commentsCount,
          isActive: false,
          onTap: _handleComment,
        ),
        
        const Spacer(),
        
        // 转发按钮
        GestureDetector(
          onTap: _handleShare,
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.sm),
            child: Icon(
              CupertinoIcons.arrowshape_turn_up_right,
              color: AppColors.white,
              size: AppSpacing.iconMedium,
            ),
          ),
        ),
      ],
    );
  }

  /// 构建交互按钮
  Widget _buildInteractionButton({
    required Widget iconWidget,
    required int count,
    required bool isActive,
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
            child: iconWidget,
          ),
          if (count > 0) ...[
            SizedBox(width: AppSpacing.intraGroupSm),
            Text(
              _formatCount(count),
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.base,
                fontWeight: AppTypography.medium,
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
                    color: AppColors.white,
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(width: AppSpacing.xs.w),
                Text(
                  '个赞',
                  style: TextStyle(
                    color: AppColors.overlayStrong,
                    fontSize: AppTypography.lg,
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
                color: AppColors.overlayStrong,
                fontSize: AppTypography.base,
              ),
            ),
          ),
      ],
    );
  }

  /// 构建关闭按钮（Positioned 须为 Stack 直接子组件，不能包在 FadeTransition/Opacity 内）
  Widget _buildCloseButton(bool isDark) {
    return Positioned(
      top: 50.h,
      right: 16.w,
      child: AnimatedBuilder(
        animation: _fadeController,
        builder: (context, child) {
          return FadeTransition(
            opacity: _fadeController,
            child: GestureDetector(
              onTap: widget.onClose,
              child: Container(
                padding: EdgeInsets.all(AppSpacing.sm.w),
                decoration: BoxDecoration(
                  color: AppColors.overlayMedium,
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.close,
                  color: AppColors.white,
                  size: AppSpacing.iconMedium,
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  /// 显示更多选项
  void _showMoreOptions() {
    // 添加mounted检查，防止在widget销毁后访问ref
    if (!mounted) return;
    
    final isDark = ref.watch(isDarkProvider);
    showCupertinoModalPopup(
      context: context,
      builder: (context) => Material(
        type: MaterialType.transparency,
        child: Container(
          decoration: BoxDecoration(
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
            borderRadius: BorderRadius.vertical(top: Radius.circular(20.r)),
          ),
          child: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // 拖拽指示器
                Container(
                  width: AppSpacing.forty.w,
                  height: AppSpacing.xs.h,
                  margin: EdgeInsets.only(top: 12.h, bottom: 20.h),
                  decoration: BoxDecoration(
                    color: isDark ? AppColors.dark.foregroundTertiary : AppColors.light.foregroundTertiary,
                    borderRadius: BorderRadius.circular(2.r),
                  ),
                ),
                
                // 功能列表
                _buildMoreOptionItem(CupertinoIcons.gift, '打赏', isDark, () => _handleReward()),
                _buildMoreOptionItem(CupertinoIcons.arrow_down_to_line, '保存', isDark, () => _handleSave()),
                _buildMoreOptionItem(CupertinoIcons.chat_bubble, '私信', isDark, () => _handleMessage()),
                _buildMoreOptionItem(CupertinoIcons.link, UITextConstants.copyLink, isDark, () => _handleCopyLink()),
                _buildMoreOptionItem(CupertinoIcons.photo, '查看原图', isDark, () => _handleViewOriginal()),
                
                SizedBox(height: AppSpacing.twenty.h),
              ],
            ),
          ),
        ),
      ),
    );
  }

  /// 构建更多选项项目
  Widget _buildMoreOptionItem(IconData icon, String title, bool isDark, VoidCallback onTap) {
    return CupertinoListTile(
      leading: Icon(
        icon,
        color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
        size: AppSpacing.iconMedium - AppSpacing.xs,
      ),
      title: Text(
        title,
        style: TextStyle(
          color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
          fontSize: AppTypography.lg,
          fontWeight: FontWeight.w500, // Cupertino typography typically uses w500 or w600
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

  void _handleFollow() {
    setState(() {
      _isFollowing = !_isFollowing;
    });
    final username = widget.post?['username']?.toString() ??
        widget.post?['publisher']?['username']?.toString();
    if (username == null || username.isEmpty) return;
    widget.onFollowClick?.call(username, _isFollowing);
  }

  void _handleAuthorTap() {
    final username = widget.post?['username']?.toString() ??
        widget.post?['publisher']?['username']?.toString();
    if (username == null || username.isEmpty) return;
    widget.onUserClick(username);
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
    AppToast.show(context, message);
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
    return formatCompactActionCount(count);
  }
}
