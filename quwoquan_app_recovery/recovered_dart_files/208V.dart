import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

import 'package:quwoquan_app/shared/components/media_post_card.dart';

/// 图片帖子卡片
/// 继承自MediaPostCard，专门处理图片内容展示
class ImagePostCard extends MediaPostCard {
  @override
  final bool isFirstPost;
  
  // 静态Map来存储每个post的展开状态
  static final Map<String, bool> _expandedStates = {};

  const ImagePostCard({
    super.key,
    required super.post,
    required super.onPostTap,
    required super.onUserTap,
    super.onLike,
    super.onComment,
    super.onShare,
    super.onBookmark,
    super.onMore,
    this.isFirstPost = false,
  });

  @override
  Widget? buildBeforeMediaContent(BuildContext context, bool isDark) {
    // 使用扩展点：在媒体内容上方显示标题和配文
    return _buildImageCaption(context, isDark);
  }

  @override
  Widget buildMediaContent(BuildContext context, bool isDark) {
    final images = post['images'] as List<dynamic>? ?? [];
    
    if (images.isEmpty) {
      return const SizedBox.shrink(); // 不显示任何内容
    }

    // 图片内容
    return images.length > 1
        ? _buildMultiImageContent(context, isDark, images)
        : _buildSingleImageContent(context, isDark, images);
  }

  /// 构建图片的标题和配文
  Widget _buildImageCaption(BuildContext context, bool isDark) {
    final title = post['title'] ?? '';
    final content = post['content'] ?? '';
    
    // 如果标题和配文都为空，不显示
    if (title.isEmpty && content.isEmpty) {
      return const SizedBox.shrink();
    }
    
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.contentSpacingMd.w,
        vertical: AppSpacing.contentSpacingSm.h,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 标题
          if (title.isNotEmpty)
            Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.xs.h),
              child: Text(
                title,
                style: TextStyle(
                  fontSize: AppTypography.base, // 与作者名一致的字号
                  fontWeight: FontWeight.w600, // 加粗
                  color: isDark
                      ? AppColors.dark.foregroundPrimary
                      : AppColors.light.foregroundPrimary,
                ),
              ),
            ),
          
          // 配文
          if (content.isNotEmpty)
            _buildExpandableContent(context, isDark, content),
        ],
      ),
    );
  }

  /// 构建可展开的配文内容
  Widget _buildExpandableContent(BuildContext context, bool isDark, String content) {
    final postId = post['id'] as String? ?? '';
    
    return StatefulBuilder(
      builder: (context, setState) {
        // 使用静态Map来管理展开状态，确保状态持久化
        final isExpanded = _expandedStates[postId] ?? false;
        
        return LayoutBuilder(
          builder: (context, constraints) {
            final textPainter = TextPainter(
              text: TextSpan(
                text: content,
                style: TextStyle(
                  fontSize: AppTypography.base, // 与作者名一致的字号
                  fontWeight: FontWeight.normal, // 不加粗
                  color: isDark
                      ? AppColors.dark.foregroundPrimary
                      : AppColors.light.foregroundPrimary,
                ),
              ),
              maxLines: isExpanded ? null : 2, // 展开时无限制行数
              textDirection: TextDirection.ltr,
            );
            
            textPainter.layout(maxWidth: constraints.maxWidth);
            final isOverflow = textPainter.didExceedMaxLines;
            
            return GestureDetector(
              onTap: isOverflow ? () {
                setState(() {
                  _expandedStates[postId] = !isExpanded;
                });
              } : null,
              child: isOverflow
                  ? Text.rich(
                      TextSpan(
                        children: [
                          TextSpan(
                            text: isExpanded ? content : () {
                              // 简单粗暴的方法：少显示更多字符，为"全文"留出足够空间
                              // 直接减少更多字符，避免精确计算
                              final truncatedLength = textPainter.getPositionForOffset(
                                Offset(constraints.maxWidth, textPainter.height * 2)
                              ).offset - 8; // 减少8个字符的位置，为"全文"留出空间
                              
                              final truncatedText = content.substring(0, truncatedLength > 0 ? truncatedLength : content.length);
                              return '$truncatedText...';
                            }(),
                            style: TextStyle(
                              fontSize: AppTypography.base,
                              fontWeight: FontWeight.normal,
                              color: isDark
                                  ? AppColors.dark.foregroundPrimary
                                  : AppColors.light.foregroundPrimary,
                            ),
                          ),
                          TextSpan(
                            text: isExpanded ? '收起' : '全文',
                            style: TextStyle(
                              fontSize: AppTypography.base,
                              color: AppColorsFunctional.getColor(isDark, ColorType.primary),
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    )
                  : Text(
                      content,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: FontWeight.normal,
                        color: isDark
                            ? AppColors.dark.foregroundPrimary
                            : AppColors.light.foregroundPrimary,
                      ),
                    ),
            );
          },
        );
      },
    );
  }


  /// 构建单张图片内容
  Widget _buildSingleImageContent(BuildContext context, bool isDark, List<dynamic> images) {
    return GestureDetector(
      onTap: () => _showMediaViewer(context),
      child: AspectRatio(
        aspectRatio: 1.0, // Instagram风格的正方形图片
        child: Container(
          width: double.infinity,
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary), // 使用语义标签，与Post头部/底部保持一致
          child: Stack(
            children: [
              // 图片 - 移除圆角效果
              Image.network(
                images.first,
                fit: BoxFit.cover,
                width: double.infinity,
                height: double.infinity,
              loadingBuilder: (context, child, loadingProgress) {
                if (loadingProgress == null) return child;
                return _buildLoadingPlaceholder(context, isDark);
              },
              errorBuilder: (context, error, stackTrace) {
                return _buildErrorPlaceholder(context, isDark);
              },
              ),
              
            ],
          ),
        ),
      ),
    );
  }

  /// 构建多张图片内容
  Widget _buildMultiImageContent(BuildContext context, bool isDark, List<dynamic> images) {
    return _MultiImageContent(
      images: images,
      isDark: isDark,
      onTap: () => _showMediaViewer(context),
      onPageChanged: (index) => _showMediaViewer(context, initialIndex: index),
    );
  }

  /// 构建加载占位符
  Widget _buildLoadingPlaceholder(BuildContext context, bool isDark) {
    return _buildImageLoadingPlaceholder(context, isDark);
  }

  /// 构建错误占位符
  Widget _buildErrorPlaceholder(BuildContext context, bool isDark) {
    return _buildImageErrorPlaceholder(context, isDark);
  }

  /// 显示媒体浏览器
  void _showMediaViewer(BuildContext context, {int initialIndex = 0}) {
    final images = post['images'] as List<dynamic>? ?? [];
    if (images.isEmpty) return;

    // 调用父组件传递的onPostTap回调，传递post和索引
    onPostTap(post, initialIndex);
  }
}

/// 多图内容组件（支持轮播和指示器）
class _MultiImageContent extends StatefulWidget {
  final List<dynamic> images;
  final bool isDark;
  final VoidCallback onTap;
  final ValueChanged<int> onPageChanged;

  const _MultiImageContent({
    required this.images,
    required this.isDark,
    required this.onTap,
    required this.onPageChanged,
  });

  @override
  State<_MultiImageContent> createState() => _MultiImageContentState();
}

class _MultiImageContentState extends State<_MultiImageContent> {
  late PageController _pageController;
  int _currentIndex = 0;

  @override
  void initState() {
    super.initState();
    _pageController = PageController(initialPage: 0);
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => widget.onPageChanged(_currentIndex),
      child: AspectRatio(
        aspectRatio: 1.0,
        child: Container(
          width: double.infinity,
          color: AppColorsFunctional.getColor(widget.isDark, ColorType.backgroundPrimary),
          child: Stack(
            children: [
              // PageView 图片轮播
              NotificationListener<ScrollNotification>(
                onNotification: _handleScrollNotification,
                child: PageView.builder(
                  controller: _pageController,
                  onPageChanged: (index) {
                    setState(() {
                      _currentIndex = index;
                    });
                  },
                  physics: const ClampingScrollPhysics(),
                  itemCount: widget.images.length,
                  itemBuilder: (context, index) => _buildImageItem(
                    widget.images[index],
                    widget.isDark,
                  ),
                ),
              ),

              // 页面指示器
              if (widget.images.length > 1)
                Positioned(
                  bottom: AppSpacing.sm,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: _buildPageIndicator(
                      context,
                      widget.isDark,
                      _currentIndex,
                      widget.images.length,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  /// 处理滑动通知，防止边界滑动触发Tab切换
  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification is ScrollUpdateNotification) {
      final isAtStart = _currentIndex == 0 &&
          notification.metrics.pixels <= notification.metrics.minScrollExtent;
      final isAtEnd = _currentIndex == widget.images.length - 1 &&
          notification.metrics.pixels >= notification.metrics.maxScrollExtent;
      
      // 在边界时阻止事件继续传播
      return isAtStart || isAtEnd;
    }
    return false;
  }

  /// 构建单个图片项
  Widget _buildImageItem(String imageUrl, bool isDark) {
    return Image.network(
      imageUrl,
      fit: BoxFit.cover,
      width: double.infinity,
      height: double.infinity,
      loadingBuilder: (context, child, loadingProgress) {
        if (loadingProgress == null) return child;
        return _buildImageLoadingPlaceholder(context, isDark);
      },
      errorBuilder: (context, error, stackTrace) {
        return _buildImageErrorPlaceholder(context, isDark);
      },
    );
  }

  /// 构建页面指示器（百分比方案）
  Widget _buildPageIndicator(
    BuildContext context,
    bool isDark,
    int currentIndex,
    int totalCount,
  ) {
    if (totalCount <= 1) return const SizedBox.shrink();

    // ≤7张图片：显示实际数量的dot
    if (totalCount <= 7) {
      return _buildDotsContainer(
        isDark: isDark,
        dotCount: totalCount,
        activeDotIndex: currentIndex,
      );
    }

    // >7张图片：固定显示7个dot，用百分比定位
    const maxDots = 7;
    final progress = currentIndex / (totalCount - 1); // 0.0 - 1.0
    final activeDotIndex = (progress * (maxDots - 1)).round(); // 0 - 6

    return _buildDotsContainer(
      isDark: isDark,
      dotCount: maxDots,
      activeDotIndex: activeDotIndex,
    );
  }

  /// 构建Dot容器
  Widget _buildDotsContainer({
    required bool isDark,
    required int dotCount,
    required int activeDotIndex,
  }) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.xs,
        vertical: AppSpacing.xs / 2,
      ),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.overlayMedium),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(
          dotCount,
          (index) => _buildIndicatorDot(
            isActive: index == activeDotIndex,
            isDark: isDark,
          ),
        ),
      ),
    );
  }

  /// 构建单个指示器圆点
  Widget _buildIndicatorDot({
    required bool isActive,
    required bool isDark,
  }) {
    final dotColor = AppColorsFunctional.getColor(isDark, ColorType.white);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeInOut,
      width: isActive ? 8.0 : 6.0,
      height: isActive ? 8.0 : 6.0,
      margin: EdgeInsets.symmetric(horizontal: AppSpacing.xs / 4),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isActive ? dotColor : dotColor.withOpacity(0.4),
      ),
    );
  }
}

/// 构建图片加载占位符（顶层函数，供多个组件共享）
Widget _buildImageLoadingPlaceholder(BuildContext context, bool isDark) {
  return Container(
    width: double.infinity,
    height: double.infinity,
    color: isDark
        ? AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary)
        : AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
    child: Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: AppSpacing.buttonSize,
            height: AppSpacing.buttonSize,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(
                AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
              ),
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.loading,
            style: TextStyle(
              fontSize: AppTypography.small,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
            ),
          ),
        ],
      ),
    ),
  );
}

/// 构建图片错误占位符（顶层函数，供多个组件共享）
Widget _buildImageErrorPlaceholder(BuildContext context, bool isDark) {
  return Container(
    width: double.infinity,
    height: double.infinity,
    color: isDark
        ? AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary)
        : AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
    child: Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.error_outline,
            size: AppSpacing.largeButtonSize,
            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.loadFailed,
            style: TextStyle(
              fontSize: AppTypography.small,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
            ),
          ),
        ],
      ),
    ),
  );
}
