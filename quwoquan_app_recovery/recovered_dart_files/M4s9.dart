import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/analytics/analytics.dart';
import 'media_post_card.dart';

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
  });

  @override
  Widget buildMediaContent(BuildContext context, bool isDark) {
    final videoUrl = post['videoUrl'] as String?;
    final thumbnailUrl = post['thumbnailUrl'] as String?;
    final duration = post['duration'] as int?; // 秒数
    
    if (videoUrl == null || videoUrl.isEmpty) {
      return _buildPlaceholder(context, isDark);
    }

    return _buildVideoContent(context, isDark, videoUrl, thumbnailUrl, duration);
  }

  /// 构建视频内容
  Widget _buildVideoContent(BuildContext context, bool isDark, String videoUrl, String? thumbnailUrl, int? duration) {
    return GestureDetector(
      onTap: () => onPostTap(post, 0),
      child: AspectRatio(
        aspectRatio: 9 / 16, // 竖屏视频比例，适合手机
        child: Container(
          width: double.infinity,
          color: isDark ? Colors.grey[900] : Colors.grey[200],
          child: Stack(
            children: [
              // 视频缩略图或背景
              if (thumbnailUrl != null && thumbnailUrl.isNotEmpty)
                Image.network(
                  thumbnailUrl,
                  fit: BoxFit.cover,
                  width: double.infinity,
                  height: double.infinity,
                  loadingBuilder: (context, child, loadingProgress) {
                    if (loadingProgress == null) return child;
                    return _buildLoadingPlaceholder(context, isDark);
                  },
                  errorBuilder: (context, error, stackTrace) {
                    return _buildVideoPlaceholder(context, isDark);
                  },
                )
              else
                _buildVideoPlaceholder(context, isDark),
              
              // 播放按钮覆盖层
              Positioned.fill(
                child: Container(
                  decoration: BoxDecoration(
                    color: Colors.black.withOpacity(0.3),
                  ),
                  child: Center(
                    child: Container(
                      width: (AppSpacing.avatarSize * 2).w,
                      height: (AppSpacing.avatarSize * 2).w,
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.9),
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.2),
                            blurRadius: 8,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: Icon(
                        Icons.play_arrow,
                        size: AppSpacing.avatarSize.sp,
                        color: Colors.black,
                      ),
                    ),
                  ),
                ),
              ),
              
              // 视频时长
              if (duration != null)
                Positioned(
                  bottom: 12.h,
                  right: 12.w,
                  child: Container(
                    padding: EdgeInsets.symmetric(horizontal: 8.w, vertical: 4.h),
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.7),
                      borderRadius: BorderRadius.circular(12.r),
                    ),
                    child: Text(
                      _formatDuration(duration),
                      style: TextStyle(
                        fontSize: 12.sp,
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              
              // 视频指示器
              Positioned(
                top: 12.h,
                left: 12.w,
                child: Container(
                  padding: EdgeInsets.symmetric(horizontal: 8.w, vertical: 4.h),
                  decoration: BoxDecoration(
                    color: Colors.black.withOpacity(0.7),
                    borderRadius: BorderRadius.circular(12.r),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.play_circle_outline,
                        size: 14.sp,
                        color: Colors.white,
                      ),
                      SizedBox(width: 4.w),
                      Text(
                        '视频',
                        style: TextStyle(
                          fontSize: 12.sp,
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              
              // 点击播放指示器
              Positioned(
                bottom: 12.h,
                left: 12.w,
                child: Container(
                  padding: EdgeInsets.symmetric(horizontal: 8.w, vertical: 4.h),
                  decoration: BoxDecoration(
                    color: Colors.black.withOpacity(0.6),
                    borderRadius: BorderRadius.circular(12.r),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.touch_app,
                        size: 14.sp,
                        color: Colors.white,
                      ),
                      SizedBox(width: 4.w),
                      Text(
                        '点击播放',
                        style: TextStyle(
                          fontSize: 12.sp,
                          color: Colors.white,
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
      ),
    );
  }

  /// 构建占位符
  Widget _buildPlaceholder(BuildContext context, bool isDark) {
    return AspectRatio(
      aspectRatio: 9 / 16,
      child: Container(
        width: double.infinity,
        color: isDark ? Colors.grey[800] : Colors.grey[200],
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.video_library_outlined,
                size: 48.sp,
                color: isDark ? Colors.grey[600] : Colors.grey[400],
              ),
              SizedBox(height: 8.h),
              Text(
                '暂无视频',
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

  /// 构建视频占位符
  Widget _buildVideoPlaceholder(BuildContext context, bool isDark) {
    return Container(
      width: double.infinity,
      height: double.infinity,
      color: isDark ? Colors.grey[800] : Colors.grey[200],
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.video_library_outlined,
              size: 64.sp,
              color: isDark ? Colors.grey[600] : Colors.grey[400],
            ),
            SizedBox(height: 16.h),
            Text(
              '视频内容',
              style: TextStyle(
                fontSize: 16.sp,
                color: isDark ? Colors.grey[500] : Colors.grey[600],
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
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

  /// 格式化视频时长
  String _formatDuration(int seconds) {
    final hours = seconds ~/ 3600;
    final minutes = (seconds % 3600) ~/ 60;
    final remainingSeconds = seconds % 60;
    
    if (hours > 0) {
      return '${hours.toString().padLeft(2, '0')}:${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
    } else {
      return '${minutes.toString().padLeft(2, '0')}:${remainingSeconds.toString().padLeft(2, '0')}';
    }
  }
}
