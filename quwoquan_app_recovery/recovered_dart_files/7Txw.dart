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
    super.isSecondPost,
  });

  @override
  Widget buildMediaContent(BuildContext context, bool isDark) {
    final videoUrl = post['videoUrl'] as String?;
    final thumbnailUrl = post['thumbnailUrl'] as String?;
    final duration = post['duration'] as int?; // 秒数
    
    if (videoUrl == null || videoUrl.isEmpty) {
      return const SizedBox.shrink(); // 不显示任何内容
    }

    return _buildVideoContent(context, isDark, videoUrl, thumbnailUrl, duration);
  }

  /// 构建视频内容
  Widget _buildVideoContent(BuildContext context, bool isDark, String videoUrl, String? thumbnailUrl, int? duration) {
    return GestureDetector(
      onTap: () => onPostTap(post, 0),
      child: LayoutBuilder(
        builder: (context, constraints) {
          // 获取屏幕高度
          final screenHeight = MediaQuery.of(context).size.height;
          final maxHeight = screenHeight * 2 / 3; // 最大高度不超过屏幕2/3
          
          // 获取视频的长宽比信息（这里模拟，实际应该从视频元数据获取）
          final videoAspectRatio = _getVideoAspectRatio(post);
          
          // 计算视频容器的高度
          double containerHeight;
          if (videoAspectRatio > 1) {
            // 横屏视频：宽度占满，高度按比例计算
            containerHeight = constraints.maxWidth / videoAspectRatio;
            if (containerHeight > maxHeight) {
              containerHeight = maxHeight;
            }
          } else {
            // 竖屏视频：高度不超过2/3屏幕
            containerHeight = constraints.maxWidth / videoAspectRatio;
            if (containerHeight > maxHeight) {
              containerHeight = maxHeight;
            }
          }
          
          return Container(
            width: double.infinity,
            height: containerHeight,
            color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
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
                      color: AppColors.overlayMedium, // 使用语义标签
                    ),
                    child: Center(
                      child: Container(
                        width: (AppSpacing.avatarSize * 2).w,
                        height: (AppSpacing.avatarSize * 2).w,
                        decoration: BoxDecoration(
                          color: AppColors.white.withValues(alpha: 0.9), // 使用语义标签
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: AppColors.black.withValues(alpha: 0.2), // 使用语义标签
                              blurRadius: AppSpacing.sm.r, // 使用语义标签
                              offset: const Offset(0, AppSpacing.xs), // 使用语义标签
                            ),
                          ],
                        ),
                        child: Icon(
                          Icons.play_arrow,
                          size: AppSpacing.avatarSize.sp,
                          color: AppColors.black, // 使用语义标签
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
  
  /// 获取视频长宽比（模拟实现，实际应该从视频元数据获取）
  double _getVideoAspectRatio(dynamic post) {
    // 模拟不同的视频长宽比
    final videoType = post['videoType'] ?? ContentTypeConstants.vertical;
    switch (videoType) {
      case ContentTypeConstants.horizontal:
        return DesignSemanticConstants.horizontalAspectRatio; // 横屏视频
      case ContentTypeConstants.square:
        return DesignSemanticConstants.squareAspectRatio; // 正方形视频
      case ContentTypeConstants.vertical:
      default:
        return DesignSemanticConstants.verticalAspectRatio; // 竖屏视频
    }
  }


  /// 构建视频占位符
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
              size: AppSpacing.iconLarge, // 使用语义标签
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
            ),
            SizedBox(height: AppSpacing.md.h), // 使用语义标签
            Text(
              UITextConstants.loading, // 使用语义字符串
              style: TextStyle(
                fontSize: AppTypography.base, // 使用语义标签
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
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
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: AppSpacing.buttonSize.w,
              height: AppSpacing.buttonSize.w,
              child: CircularProgressIndicator(
                strokeWidth: AppSpacing.xs.h, // 使用语义标签
                valueColor: AlwaysStoppedAnimation<Color>(
                  isDark 
                      ? AppColors.dark.foregroundTertiary 
                      : AppColors.light.foregroundTertiary,
                ),
              ),
            ),
            SizedBox(height: AppSpacing.xs.h), // 使用语义标签
            Text(
              UITextConstants.loading, // 使用语义字符串
              style: TextStyle(
                fontSize: AppTypography.sm, // 使用语义标签
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
              ),
            ),
          ],
        ),
      ),
    );
  }

}
