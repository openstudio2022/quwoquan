import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/shared/components/image_post_card.dart';
import 'package:quwoquan_app/shared/components/video_post_card.dart';
import 'package:quwoquan_app/shared/components/stories_section.dart';

/// Post列表区域组件
/// 专门处理post列表，不包含stories，实现更简洁的架构
class PostListSection extends ConsumerStatefulWidget {
  final String category;
  final String? subCategory; // 二级分类，用于图片tab
  final Function(dynamic, int) onPostTap;
  final Function(String) onUserTap;
  final bool? isDark; // 可选的主题参数
  final Function(String)? onImageSubCategoryChange; // 图片二级分类变化回调

  const PostListSection({
    super.key,
    required this.category,
    this.subCategory,
    required this.onPostTap,
    required this.onUserTap,
    this.isDark,
    this.onImageSubCategoryChange,
  });

  @override
  ConsumerState<PostListSection> createState() => _PostListSectionState();
}

class _PostListSectionState extends ConsumerState<PostListSection> {
  Future<List<Map<String, dynamic>>>? _postsFuture;
  String? _cachedCategory;
  String? _cachedSubCategory;

  @override
  void initState() {
    super.initState();
    // 在post-frame callback中初始化，确保ref可用
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _loadPosts();
      }
    });
  }

  @override
  void didUpdateWidget(PostListSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 只有在category或subCategory变化时才重新加载数据
    if (oldWidget.category != widget.category || 
        oldWidget.subCategory != widget.subCategory) {
      _loadPosts();
    }
  }

  /// 加载帖子数据
  void _loadPosts() {
    final dataService = ref.read(dataServiceProvider);
    
    // 构建请求参数
    final params = <String, dynamic>{
      'category': widget.category,
    };
    if (widget.subCategory != null) {
      params['subCategory'] = widget.subCategory;
    }

    // 缓存future，避免每次build都重新创建
    if (mounted) {
      setState(() {
        _postsFuture = dataService.getDataList(
          endpoint: '/posts',
          params: params,
          limit: 20,
        );
        _cachedCategory = widget.category;
        _cachedSubCategory = widget.subCategory;
      });
    }
  }

  /// 刷新帖子数据
  void _refreshPosts() {
    final dataService = ref.read(dataServiceProvider);
    
    // 构建请求参数
    final params = <String, dynamic>{
      'category': widget.category,
    };
    if (widget.subCategory != null) {
      params['subCategory'] = widget.subCategory;
    }

    // 重新创建future以触发刷新
    setState(() {
      _postsFuture = dataService.getDataList(
        endpoint: '/posts',
        params: params,
        limit: 20,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final responsive = ref.watch(responsiveProvider);
    final bool isDark = widget.isDark ?? ref.watch(isDarkProvider);

    // 如果future还没有初始化，显示加载状态
    // initState中的post-frame callback会负责初始化
    if (_postsFuture == null) {
      return _buildLoadingWidget(context, isDark);
    }

    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _postsFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return _buildLoadingWidget(context, isDark);
        }

        if (snapshot.hasError) {
          return _buildErrorWidget(context, snapshot.error!, isDark, ref);
        }

        final posts = snapshot.data ?? [];
        return _buildPostList(context, posts, isDark, responsive, ref);
      },
    );
  }

  /// 构建Post列表
  Widget _buildPostList(BuildContext context, List<Map<String, dynamic>> posts, bool isDark, dynamic responsive, WidgetRef ref) {
    // 过滤掉数据异常的Post
    // 注意：内容类型过滤由服务端完成，客户端只需验证数据完整性
    final validPosts = posts.where((post) => _isValidPost(post)).toList();
    
    if (validPosts.isEmpty && !_shouldShowStories()) {
      return _buildEmptyWidget(context, isDark);
    }

    return RefreshIndicator(
      onRefresh: () async {
        _trackFeedRefresh(ref, widget.category);
        _refreshPosts(); // 使用专门的刷新方法
      },
      child: Container(
        // 浅色模式：post列表使用浅灰（backgroundSecondary）
        // 深色模式：post列表使用深黑（backgroundPrimary）
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
        child: ListView.builder(
          // 移除垂直间距，让Post无缝连接
          padding: EdgeInsets.zero, // 确保没有默认padding
          itemCount: validPosts.length + (_shouldShowStories() ? 1 : 0),
          itemBuilder: (context, index) {
            // 只在关注tab显示Stories（推荐tab去掉stories）
            if (_shouldShowStories() && index == 0) {
              return StoriesSection(
                onStoryTap: (story) {
                  // 处理story点击
                },
                onUserTap: widget.onUserTap,
              );
            }

            // 调整Post索引
            final postIndex = _shouldShowStories() ? index - 1 : index;
            final post = validPosts[postIndex];
            
            // 第一个Post与Stories/Tab之间无间距，其他Post之间无分割线（与原型保持一致）
            final isFirstPost = _shouldShowStories()
                ? index == 1  // 有Stories的Tab，第一个Post索引是1
                : index == 0; // 没有Stories的Tab，第一个Post索引是0
            
            // 构建post卡片（无分割线，与原型保持一致）
            return _buildPostCard(context, post, isDark, responsive, ref, isFirstPost: isFirstPost);
          },
        ),
      ),
    );
  }
  
  /// 判断是否应该显示Stories
  /// 在关注和推荐tab显示Stories
  bool _shouldShowStories() {
    return widget.category == 'following' || widget.category == 'recommended';
  }

  /// 验证Post数据是否有效
  bool _isValidPost(dynamic post) {
    if (post == null) return false;
    
    final postType = post['type'] ?? '';
    final images = post['images'] as List<dynamic>? ?? [];
    final videoUrl = post['videoUrl'] as String?;
    
    // 验证图片帖子
    if (postType == 'image') {
      return images.isNotEmpty && images.first != null && images.first.toString().isNotEmpty;
    }
    
    // 验证视频帖子
    if (postType == 'video') {
      return videoUrl != null && videoUrl.isNotEmpty;
    }
    
    return true;
  }

  /// 构建Post卡片
  Widget _buildPostCard(BuildContext context, dynamic post, bool isDark, dynamic responsive, WidgetRef ref, {bool isFirstPost = false}) {
    // 根据帖子类型和分类选择合适的卡片组件
    final postType = post['type'] ?? ContentTypeConstants.image;
    final category = widget.category;
    
    // 如果在视频分类下，强制使用视频卡片
    if (category == 'video') {
      return VideoPostCard(
        post: post,
        isFirstPost: isFirstPost, // 传递isFirstPost参数
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
          isFirstPost: isFirstPost,
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
          isFirstPost: isFirstPost,
          onPostTap: widget.onPostTap,
          onUserTap: widget.onUserTap,
          onLike: _handleLike,
          onComment: _handleComment,
          onShare: _handleShare,
          onBookmark: _handleBookmark,
          onMore: _handleMore,
        );
      default:
        return const SizedBox.shrink();
    }
  }

  /// 处理点赞
  void _handleLike(dynamic post) {
    _trackInteraction(ref, 'like', widget.category, post);
  }

  /// 处理评论
  void _handleComment(dynamic post) {
    _trackInteraction(ref, 'comment', widget.category, post);
  }

  /// 处理分享
  void _handleShare(dynamic post) {
    _trackInteraction(ref, 'share', widget.category, post);
  }

  /// 处理收藏
  void _handleBookmark(dynamic post) {
    _trackInteraction(ref, 'bookmark', widget.category, post);
  }

  /// 处理更多操作
  void _handleMore(dynamic post) {
    _trackInteraction(ref, 'more', widget.category, post);
  }

  /// 跟踪交互事件
  void _trackInteraction(WidgetRef ref, String action, String category, dynamic post) {
    final analytics = ref.read(analyticsProvider);
    final event = AnalyticsEvent(
      eventName: 'post_interaction',
      eventType: 'interaction',
      properties: {
        'action': action,
        'category': category,
        'post_type': post['type'] ?? 'unknown',
        'post_id': post['id'] ?? 'unknown',
      },
    );
    analytics.trackEvent(event);
  }

  /// 跟踪Feed刷新
  void _trackFeedRefresh(WidgetRef ref, String category) {
    final analytics = ref.read(analyticsProvider);
    final event = AnalyticsEvent(
      eventName: 'feed_refresh',
      eventType: 'refresh',
      properties: {
        'category': category,
      },
    );
    analytics.trackEvent(event);
  }

  /// 构建加载中组件
  Widget _buildLoadingWidget(BuildContext context, bool isDark) {
    return Container(
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: AppSpacing.buttonSize,
              height: AppSpacing.buttonSize,
              child: CircularProgressIndicator(
                strokeWidth: AppSpacing.xs.h,
                valueColor: AlwaysStoppedAnimation<Color>(
                  isDark 
                      ? AppColors.dark.foregroundTertiary 
                      : AppColors.light.foregroundTertiary,
                ),
              ),
            ),
            SizedBox(height: AppSpacing.md.h),
            Text(
              UITextConstants.loading,
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 构建错误组件
  Widget _buildErrorWidget(BuildContext context, Object error, bool isDark, WidgetRef ref) {
    return Container(
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.error_outline,
              size: (AppSpacing.avatarSize * 1.6).sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
            ),
            SizedBox(height: AppSpacing.md.h),
            Text(
              UITextConstants.loading,
              style: TextStyle(
                fontSize: 18.sp,
                fontWeight: FontWeight.w600,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
              ),
            ),
            SizedBox(height: 8.h),
            Text(
              error.toString(),
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
              ),
              textAlign: TextAlign.center,
            ),
            SizedBox(height: AppSpacing.lg.h),
            ElevatedButton(
              onPressed: () {
                _refreshPosts(); // 使用专门的刷新方法
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primaryColor,
                foregroundColor: AppColorsFunctional.getColor(false, ColorType.foregroundInverse),
                padding: EdgeInsets.symmetric(horizontal: 24.w, vertical: 12.h),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                ),
              ),
              child: Text(
                UITextConstants.retry,
                style: TextStyle(
                  fontSize: AppTypography.base,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 构建空状态组件
  Widget _buildEmptyWidget(BuildContext context, bool isDark) {
    return Container(
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.photo_library_outlined,
              size: (AppSpacing.avatarSize * 1.6).sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
            ),
            SizedBox(height: AppSpacing.md.h),
            Text(
              UITextConstants.loading,
              style: TextStyle(
                fontSize: 18.sp,
                fontWeight: FontWeight.w600,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
              ),
            ),
            SizedBox(height: 8.h),
            Text(
              '下拉刷新试试',
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
