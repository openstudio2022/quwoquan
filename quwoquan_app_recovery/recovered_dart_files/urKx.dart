import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/shared/components/image_post_card.dart';
import 'package:quwoquan_app/shared/components/video_post_card.dart';
import 'package:quwoquan_app/shared/components/stories_section.dart';
import 'package:quwoquan_app/shared/components/image_sub_tab_navigation.dart';

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

class _PostListSectionState extends ConsumerState<PostListSection> 
    with AutomaticKeepAliveClientMixin {
  
  Future<List<Map<String, dynamic>>>? _dataFuture;
  List<Map<String, dynamic>>? _cachedPosts; // 缓存已加载的数据，避免切换时闪烁

  @override
  bool get wantKeepAlive => true; // 保持PostListSection状态

  @override
  void initState() {
    super.initState();
    // 延迟加载，确保ref已准备好
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadData();
    });
  }

  @override
  void didUpdateWidget(PostListSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 当category改变时，清空缓存并重新加载
    if (oldWidget.category != widget.category) {
      setState(() {
        _cachedPosts = null; // 清空缓存
      });
      _loadData();
    }
    // 当subCategory改变时，保持缓存（避免闪烁），重新加载数据
    else if (oldWidget.subCategory != widget.subCategory) {
      _loadData();
    }
  }

  void _loadData() {
    final dataService = ref.read(dataServiceProvider);
    final params = <String, dynamic>{
      'category': widget.category,
    };
    if (widget.subCategory != null) {
      params['subCategory'] = widget.subCategory;
    }
    
    final newFuture = dataService.getDataList(
      endpoint: '/posts',
      params: params,
      limit: 20,
    );
    
    // 异步更新缓存
    newFuture.then((posts) {
      if (mounted) {
        setState(() {
          _cachedPosts = posts;
        });
      }
    }).catchError((error) {
      // 错误处理，保持旧数据
    });
    
    setState(() {
      _dataFuture = newFuture;
    });
  }

  Future<void> _refreshData() async {
    _loadData();
    // 等待数据加载完成
    if (_dataFuture != null) {
      await _dataFuture;
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context); // 必须调用，用于AutomaticKeepAliveClientMixin
    // 优先使用传入的主题参数，否则使用Provider
    final currentIsDark = (widget.isDark ?? ref.watch(effectiveIsDarkProvider))!;
    final responsive = ref.watch(responsiveProvider);

    // 将二级tab从FutureBuilder中分离出来
    final shouldShowImageSubTabs = _shouldShowImageSubTabs();
    
    return Column(
      children: [
        // 二级tab导航 - 始终显示，不受数据加载状态影响
        if (shouldShowImageSubTabs)
          ImageSubTabNavigation(
            key: const ValueKey('image_sub_tab_navigation'), // 稳定的key，防止重建
            activeCategory: widget.subCategory ?? 'all',
            isDark: currentIsDark,
            onCategoryChange: (category) {
              widget.onImageSubCategoryChange?.call(category);
            },
          ),
        // 内容区域 - 使用FutureBuilder加载数据
        Expanded(
          child: FutureBuilder<List<Map<String, dynamic>>>(
            key: ValueKey('${widget.category}_${widget.subCategory}'), // 确保subCategory改变时重新构建
            future: _dataFuture,
            builder: (context, snapshot) {
              // 如果有缓存数据且正在加载，显示缓存数据而不是loading
              if (snapshot.connectionState == ConnectionState.waiting && _cachedPosts != null) {
                return _buildPostList(context, _cachedPosts!, currentIsDark, responsive, ref);
              }
              
              if (snapshot.connectionState == ConnectionState.waiting) {
                return _buildLoadingWidget(context, currentIsDark);
              }

              if (snapshot.hasError) {
                return _buildErrorWidget(context, snapshot.error!, currentIsDark, ref);
              }

              final posts = snapshot.data ?? [];
              return _buildPostList(context, posts, currentIsDark, responsive, ref);
            },
          ),
        ),
      ],
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
        await _refreshData(); // 只刷新数据，不重建整个widget树
      },
      child: Container(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary), // 使用次要背景色区分列表
        child: NotificationListener<ScrollNotification>(
          onNotification: (notification) {
            // 拦截所有滑动事件，防止影响主布局的PageView
            return true;
          },
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

            // 调整Post索引（二级tab已移到外层，不再计算在内）
            final postIndex = _shouldShowStories() ? index - 1 : index;
            final post = validPosts[postIndex];
            
            // 第一个Post与Stories之间无间距，其他Post之间使用分割线
            final isFirstPost = _shouldShowStories() ? index == 1 : index == 0;
            
            // 构建post卡片和分割线
            return Column(
              children: [
                _buildPostCard(context, post, isDark, responsive, ref, isFirstPost: isFirstPost),
                // 在post之间添加分割线，但最后一个post不添加
                if (index < validPosts.length + (_shouldShowStories() ? 1 : 0) - 1)
                  Divider(
                    height: 1.h,
                    thickness: 0.5,
                    color: AppColorsFunctional.getColor(isDark, ColorType.borderSecondary),
                    indent: 0,
                    endIndent: 0,
                  ),
              ],
            );
          },
        ),
        ),
      ),
    );
  }
  
  /// 判断是否应该显示Stories
  /// 只在关注tab显示Stories，推荐tab去掉stories
  bool _shouldShowStories() {
    return widget.category == 'following';
  }

  /// 判断是否应该显示图片二级tab
  /// 只在图片tab显示二级导航
  bool _shouldShowImageSubTabs() {
    return widget.category == 'images';
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
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            SizedBox(
              width: AppSpacing.buttonSize.w,
              height: AppSpacing.buttonSize.w,
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
                fontSize: AppTypography.sm.sp,
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
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
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
                fontSize: AppTypography.sm.sp,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
              ),
              textAlign: TextAlign.center,
            ),
            SizedBox(height: AppSpacing.lg.h),
            ElevatedButton(
              onPressed: () {
                setState(() {}); // 触发FutureBuilder重新构建
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primaryColor,
                foregroundColor: AppColorsFunctional.getColor(false, ColorType.foregroundInverse),
                padding: EdgeInsets.symmetric(horizontal: 24.w, vertical: 12.h),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius.r),
                ),
              ),
              child: Text(
                UITextConstants.retry,
                style: TextStyle(
                  fontSize: AppTypography.base.sp,
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
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
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
                fontSize: AppTypography.sm.sp,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
