import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

import 'package:quwoquan_app/shared/components/media_post_card.dart';

/// 视频帖子卡片
/// 继承自MediaPostCard，专门处理视频内容展示
class VideoPostCard extends MediaPostCard {
  const VideoPostCard({
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
    final videoUrl = post['videoUrl'] as String?;
    final thumbnailUrl = post['thumbnailUrl'] as String?;

    if (videoUrl == null || videoUrl.isEmpty) {
      return const SizedBox.shrink();
    }

    return _buildVideoPlayer(context, isDark, videoUrl, thumbnailUrl);
  }

  Widget _buildVideoPlayer(BuildContext context, bool isDark, String videoUrl, String? thumbnailUrl) {
    final screenHeight = MediaQuery.of(context).size.height;
    final maxVideoHeight = screenHeight * 0.67; // 不超过屏幕高度的2/3
    
    return LayoutBuilder(
      builder: (context, constraints) {
        final postWidth = constraints.maxWidth;
        
        // 假设视频是16:9比例，计算高度
        final videoHeight = (postWidth * 9 / 16).clamp(200.0, maxVideoHeight);
        
        return Container(
          width: double.infinity,
          height: videoHeight,
          color: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
          child: Stack(
            alignment: Alignment.center,
            children: [
              // 视频缩略图或播放器
              if (thumbnailUrl != null && thumbnailUrl.isNotEmpty)
                Image.network(
                  thumbnailUrl,
                  width: double.infinity,
                  height: double.infinity,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) {
                    return _buildVideoPlaceholder(context, isDark);
                  },
                )
              else
                _buildVideoPlaceholder(context, isDark),
              
              // 播放按钮
              Container(
                width: 60.w,
                height: 60.w,
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.6),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  Icons.play_arrow,
                  color: Colors.white,
                  size: 30.w,
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildVideoPlaceholder(BuildContext context, bool isDark) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.video_library_outlined,
              size: AppSpacing.iconLarge,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
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
}