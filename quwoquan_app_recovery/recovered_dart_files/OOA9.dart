import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

import 'package:quwoquan_app/shared/components/media_post_card.dart';

/// 图片帖子卡片
/// 继承自MediaPostCard，专门处理图片内容展示
class ImagePostCard extends MediaPostCard {
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
  Widget buildMediaContent(BuildContext context, bool isDark) {
    final images = post['images'] as List<dynamic>? ?? [];
    
    if (images.isEmpty) {
      return const SizedBox.shrink(); // 不显示任何内容
    }

    // 如果是多张图片，显示第一张并添加指示器
    if (images.length > 1) {
      return _buildMultiImageContent(context, isDark, images);
    }

    // 单张图片
    return _buildSingleImageContent(context, isDark, images);
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
