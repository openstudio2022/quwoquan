import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
// import '../../core/data/data_service_provider.dart'; // 已通过core.dart导入
import 'image_post_card.dart';
import 'video_post_card.dart';

class FeedSection extends ConsumerStatefulWidget {
  final String category;
  final Function(dynamic) onPostTap;
  final Function(String) onUserTap;

  const FeedSection({
    super.key,
    required this.category,
    required this.onPostTap,
    required this.onUserTap,
  });

  @override
  ConsumerState<FeedSection> createState() => _FeedSectionState();
}

class _FeedSectionState extends ConsumerState<FeedSection> {

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final responsive = ref.watch(responsiveProvider);
    final dataService = ref.watch(dataServiceProvider);

    // 按照Figma迁移指导：跟踪Feed加载
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _trackFeedLoad(ref, widget.category);
      }
    });

    return FutureBuilder(
      future: dataService.getDataList(
        endpoint: '/posts',
        params: {'category': widget.category},
        limit: 20,
      ),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return _buildLoadingWidget(context, isDark, responsive);
        }

        if (snapshot.hasError) {
          return _buildErrorWidget(context, snapshot.error!, isDark, responsive);
        }

        final response = snapshot.data as Map<String, dynamic>?;
        if (response == null || !response['success'] || response['data'] == null) {
          return _buildErrorWidget(context, UITextConstants.loadFailed, isDark, responsive);
        }

        return _buildPostsList(context, response['data'], isDark, responsive, ref);
      },
    );
  }
  
  /// 跟踪Feed加载 - 符合用户行为与体验规则
  void _trackFeedLoad(WidgetRef ref, String category) {
    final analytics = ref.read(analyticsProvider);
    final event = AnalyticsEvent(
      eventType: 'feed_load',
      eventName: 'Feed Load',
      properties: {
        'category': category,
        'timestamp': DateTime.now().toIso8601String(),
      },
    );
    analytics.trackEvent(event);
  }

  Widget _buildPostsList(BuildContext context, List<dynamic> posts, bool isDark, dynamic responsive, WidgetRef ref) {
    if (posts.isEmpty) {
      return _buildEmptyWidget(context, isDark);
    }

    return RefreshIndicator(
      onRefresh: () async {
        _trackFeedRefresh(ref, widget.category);
        ref.refresh(dataServiceProvider);
      },
      child: ListView.builder(
        padding: EdgeInsets.symmetric(vertical: 8.h),
        itemCount: posts.length,
        itemBuilder: (context, index) {
          final post = posts[index];
          return _buildPostCard(context, post, isDark, responsive, ref);
        },
      ),
    );
  }
  
  /// 跟踪Feed刷新 - 符合用户行为与体验规则
  void _trackFeedRefresh(WidgetRef ref, String category) {
    final analytics = ref.read(analyticsProvider);
    final event = AnalyticsEvent(
      eventType: 'feed_refresh',
      eventName: 'Feed Refresh',
      properties: {
        'category': category,
        'timestamp': DateTime.now().toIso8601String(),
      },
    );
    analytics.trackEvent(event);
  }

  Widget _buildPostCard(BuildContext context, dynamic post, bool isDark, dynamic responsive, WidgetRef ref) {
    // 根据帖子类型和分类选择合适的卡片组件
    final postType = post['type'] ?? ContentTypeConstants.image;
    final category = widget.category;
    
    // 如果在视频分类下，强制使用视频卡片
    if (category == 'video') {
      return VideoPostCard(
        post: post,
        onPostTap: widget.onPostTap,
        onUserTap: widget.onUserTap,
        onLike: _handleLike,
        onComment: _handleComment,
        onShare: _handleShare,
        onBookmark: _handleBookmark,
        onMore: _handleMore,
      );
    }
    
    // 根据帖子类型选择合适的卡片组件
    switch (postType) {
      case 'image':
        return ImagePostCard(
          post: post,
          onPostTap: widget.onPostTap,
          onUserTap: widget.onUserTap,
          onLike: _handleLike,
          onComment: _handleComment,
          onShare: _handleShare,
          onBookmark: _handleBookmark,
          onMore: _handleMore,
        );
      case 'video':
        return VideoPostCard(
          post: post,
          onPostTap: widget.onPostTap,
          onUserTap: widget.onUserTap,
          onLike: _handleLike,
          onComment: _handleComment,
          onShare: _handleShare,
          onBookmark: _handleBookmark,
          onMore: _handleMore,
        );
      default:
        return ImagePostCard(
          post: post,
          onPostTap: widget.onPostTap,
          onUserTap: widget.onUserTap,
          onLike: _handleLike,
          onComment: _handleComment,
          onShare: _handleShare,
          onBookmark: _handleBookmark,
          onMore: _handleMore,
        );
    }
  }

  /// 处理点赞操作
  void _handleLike(dynamic post) {
    _trackPostInteraction(ref, 'like', post);
    // TODO: 实现点赞逻辑
  }

  /// 处理评论操作
  void _handleComment(dynamic post) {
    _trackPostInteraction(ref, 'comment', post);
    // TODO: 实现评论逻辑
  }

  /// 处理分享操作
  void _handleShare(dynamic post) {
    _trackPostInteraction(ref, 'share', post);
    // TODO: 实现分享逻辑
  }

  /// 处理收藏操作
  void _handleBookmark(dynamic post) {
    _trackPostInteraction(ref, 'bookmark', post);
    // TODO: 实现收藏逻辑
  }

  /// 处理更多操作
  void _handleMore(dynamic post) {
    _trackPostInteraction(ref, 'more', post);
    // TODO: 实现更多操作逻辑
  }

  /// 跟踪帖子交互 - 符合用户行为与体验规则
  void _trackPostInteraction(WidgetRef ref, String action, dynamic post) {
    final analytics = ref.read(analyticsProvider);
    final event = AnalyticsEvent(
      eventType: 'post_interaction',
      eventName: 'Post Interaction',
      properties: {
        'page_name': 'home',
        'category': widget.category,
        'action': action,
        'post_id': post['id'] ?? UITextConstants.unknown,
        'post_type': post['type'] ?? UITextConstants.unknown,
        'timestamp': DateTime.now().toIso8601String(),
      },
    );
    analytics.trackEvent(event);
  }

  Widget _buildLoadingWidget(BuildContext context, bool isDark, dynamic responsive) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 40.w,
            height: 40.w,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              valueColor: AlwaysStoppedAnimation<Color>(
                AppColors.primaryColor,
              ),
            ),
          ),
          SizedBox(height: 16.h),
          Text(
            UITextConstants.loading,
            style: TextStyle(
              fontSize: 14.sp,
              color: isDark ? Colors.grey[400] : Colors.grey[600],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorWidget(BuildContext context, dynamic error, bool isDark, dynamic responsive) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(32.w),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.error_outline,
              size: 64.sp,
              color: isDark ? Colors.grey[600] : Colors.grey[400],
            ),
            SizedBox(height: 16.h),
            Text(
              '加载失败',
              style: TextStyle(
                fontSize: 18.sp,
                fontWeight: FontWeight.w600,
                color: isDark ? Colors.white : Colors.black,
              ),
            ),
            SizedBox(height: 8.h),
            Text(
              error.toString(),
              style: TextStyle(
                fontSize: 14.sp,
                color: isDark ? Colors.grey[400] : Colors.grey[600],
              ),
              textAlign: TextAlign.center,
            ),
            SizedBox(height: 24.h),
            ElevatedButton(
              onPressed: () {
                setState(() {});
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primaryColor,
                foregroundColor: AppColors.light.foregroundInverse,
                padding: EdgeInsets.symmetric(horizontal: 24.w, vertical: 12.h),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8.r),
                ),
              ),
              child: Text(
                UITextConstants.retry,
                style: TextStyle(
                  fontSize: 14.sp,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyWidget(BuildContext context, bool isDark) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(32.w),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.photo_library_outlined,
              size: 64.sp,
              color: isDark ? Colors.grey[600] : Colors.grey[400],
            ),
            SizedBox(height: 16.h),
            Text(
              '暂无内容',
              style: TextStyle(
                fontSize: 18.sp,
                fontWeight: FontWeight.w600,
                color: isDark ? Colors.white : Colors.black,
              ),
            ),
            SizedBox(height: 8.h),
            Text(
              '下拉刷新试试',
              style: TextStyle(
                fontSize: 14.sp,
                color: isDark ? Colors.grey[400] : Colors.grey[600],
              ),
            ),
          ],
        ),
      ),
    );
  }
}