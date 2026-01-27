import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

import 'package:quwoquan_app/shared/components/media_post_card.dart';

/// 图片帖子卡片
/// 继承自MediaPostCard，专门处理图片内容展示
class ImagePostCard extends MediaPostCard {
  @override
  final bool isFirstPost;

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
          maxLines: 2, // 限制2行
          textDirection: TextDirection.ltr,
        );
        
        textPainter.layout(maxWidth: constraints.maxWidth);
        final isOverflow = textPainter.didExceedMaxLines;
        
        return GestureDetector(
          onTap: isOverflow ? () {
            setState(() {
              _isContentExpanded = !_isContentExpanded;
            });
          } : null,
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: isOverflow && !_isContentExpanded
                      ? '${content.substring(0, textPainter.getPositionForOffset(
                          Offset(constraints.maxWidth, textPainter.height * 2)
                        ).offset - 3)}...'
                      : content,
                  style: TextStyle(
                    fontSize: AppTypography.base, // 与作者名一致的字号
                    fontWeight: FontWeight.normal, // 不加粗
                    color: isDark
                        ? AppColors.dark.foregroundPrimary
                        : AppColors.light.foregroundPrimary,
                  ),
                ),
                if (isOverflow && !_isContentExpanded)
                  TextSpan(
                    text: ' 全文', // 紧跟在省略号后面，不单独成行
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      color: AppColorsFunctional.getColor(isDark, ColorType.primary),
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                if (isOverflow && _isContentExpanded)
                  TextSpan(
                    text: ' 收起', // 展开时显示"收起"
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      color: AppColorsFunctional.getColor(isDark, ColorType.primary),
                      fontWeight: FontWeight.w500,
                    ),
                  ),
              ],
            ),
          ),
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
    return GestureDetector(
      onTap: () => _showMediaViewer(context),
      child: AspectRatio(
        aspectRatio: 1.0,
        child: Container(
          width: double.infinity,
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary), // 使用语义标签，与Post头部/底部保持一致
          child: Stack(
            children: [
              // 第一张图片
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
              
              // 多图指示器 - 只显示数量，无背景
              Positioned(
                top: 12.h,
                right: 12.w,
                child: Text(
                  '${images.length}',
                  style: TextStyle(
                    fontSize: 12.sp,
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              
            ],
          ),
        ),
      ),
    );
  }

  /// 构建占位符
  Widget _buildPlaceholder(BuildContext context, bool isDark) {
    return AspectRatio(
      aspectRatio: 1.0,
      child: Container(
        width: double.infinity,
        color: isDark ? Colors.grey[800] : Colors.grey[200],
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.image_outlined,
                size: AppSpacing.largeButtonSize.sp,
                color: isDark ? Colors.grey[600] : Colors.grey[400],
              ),
              SizedBox(height: 8.h),
              Text(
                '暂无图片',
                style: TextStyle(
                  fontSize: 14.sp,
                  color: isDark ? Colors.grey[500] : Colors.grey[600],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// 构建加载占位符
  Widget _buildLoadingPlaceholder(BuildContext context, bool isDark) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: isDark ? Colors.grey[800] : Colors.grey[200],
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: AppSpacing.buttonSize.w,
              height: AppSpacing.buttonSize.w,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                valueColor: AlwaysStoppedAnimation<Color>(
                  isDark ? Colors.grey[400]! : Colors.grey[600]!,
                ),
              ),
            ),
            SizedBox(height: 8.h),
            Text(
              '加载中...',
              style: TextStyle(
                fontSize: 12.sp,
                color: isDark ? Colors.grey[500] : Colors.grey[600],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 构建错误占位符
  Widget _buildErrorPlaceholder(BuildContext context, bool isDark) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: isDark ? Colors.grey[800] : Colors.grey[200],
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.error_outline,
              size: 48.sp,
              color: isDark ? Colors.grey[600] : Colors.grey[400],
            ),
            SizedBox(height: 8.h),
            Text(
              '加载失败',
              style: TextStyle(
                fontSize: 14.sp,
                color: isDark ? Colors.grey[500] : Colors.grey[600],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 显示媒体浏览器
  void _showMediaViewer(BuildContext context) {
    final images = post['images'] as List<dynamic>? ?? [];
    if (images.isEmpty) return;

    // 调用父组件传递的onPostTap回调，传递post和索引
    onPostTap(post, 0);
  }
}
