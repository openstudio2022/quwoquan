import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

import 'package:quwoquan_app/shared/components/media_post_card.dart';

/// 图片帖子卡片
/// 继承自MediaPostCard，专门处理图片内容展示
class ImagePostCard extends MediaPostCard {
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
    super.isFirstPost,
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
    } else {
      return _buildSingleImageContent(context, isDark, images[0] as String);
    }
  }

  Widget _buildSingleImageContent(BuildContext context, bool isDark, String imageUrl) {
    return GestureDetector(
      onTap: () => onPostTap(post, 0),
      child: Container(
        width: double.infinity,
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.6, // 限制最大高度
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8.r),
          child: Image.network(
            imageUrl,
            fit: BoxFit.cover,
            loadingBuilder: (context, child, loadingProgress) {
              if (loadingProgress == null) return child;
              return _buildLoadingPlaceholder(context, isDark);
            },
            errorBuilder: (context, error, stackTrace) {
              return _buildErrorPlaceholder(context, isDark);
            },
          ),
        ),
      ),
    );
  }

  Widget _buildMultiImageContent(BuildContext context, bool isDark, List<dynamic> images) {
    return GestureDetector(
      onTap: () => onPostTap(post, 0),
      child: Container(
        width: double.infinity,
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.6,
        ),
        child: Stack(
          children: [
            // 主图片
            ClipRRect(
              borderRadius: BorderRadius.circular(8.r),
              child: Image.network(
                images[0] as String,
                width: double.infinity,
                fit: BoxFit.cover,
                loadingBuilder: (context, child, loadingProgress) {
                  if (loadingProgress == null) return child;
                  return _buildLoadingPlaceholder(context, isDark);
                },
                errorBuilder: (context, error, stackTrace) {
                  return _buildErrorPlaceholder(context, isDark);
                },
              ),
            ),
            // 多图片指示器
            Positioned(
              top: 8.h,
              right: 8.w,
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: 8.w,
                  vertical: 4.h,
                ),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(12.r),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.grid_on,
                      color: Colors.white,
                      size: 16.w,
                    ),
                    SizedBox(width: 4.w),
                    Text(
                      '${images.length}',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 12.sp,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadingPlaceholder(BuildContext context, bool isDark) {
    return Container(
      width: double.infinity,
      height: 200.h,
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: 40.w,
              height: 40.w,
              child: CircularProgressIndicator(
                strokeWidth: 3,
                valueColor: AlwaysStoppedAnimation<Color>(
                  AppColorsFunctional.getColor(isDark, ColorType.primary),
                ),
              ),
            ),
            SizedBox(height: AppSpacing.md.h),
            Text(
              UITextConstants.loading,
              style: TextStyle(
                fontSize: AppTypography.base,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorPlaceholder(BuildContext context, bool isDark) {
    return Container(
      width: double.infinity,
      height: 200.h,
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.broken_image_outlined,
              size: 48.w,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
            ),
            SizedBox(height: AppSpacing.md.h),
            Text(
              UITextConstants.retry,
              style: TextStyle(
                fontSize: AppTypography.base,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}