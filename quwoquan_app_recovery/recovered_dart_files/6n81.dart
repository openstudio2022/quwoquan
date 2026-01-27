import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/lib/quwoquan_components.dart';

/// 视频频道页面
/// 专门展示视频内容，支持视频播放
class VideoChannelPage extends ConsumerStatefulWidget {
  const VideoChannelPage({super.key});

  @override
  ConsumerState<VideoChannelPage> createState() => _VideoChannelPageState();
}

class _VideoChannelPageState extends ConsumerState<VideoChannelPage> {
  final ScrollController _scrollController = ScrollController();
  final List<Map<String, dynamic>> _videos = [];

  @override
  void initState() {
    super.initState();
    _loadVideos();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void _loadVideos() {
    // 模拟加载视频数据
    setState(() {
      _videos.clear();
      _videos.addAll([
        {
          'id': 'video_1',
          'username': 'user1',
          'displayName': '视频创作者1',
          'avatar': 'https://picsum.photos/100/100?random=1',
          'videoUrl': 'https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4',
          'thumbnailUrl': 'https://picsum.photos/400/600?random=101',
          'duration': 120,
          'likesCount': 150,
          'savesCount': 25,
          'commentsCount': 30,
          'sharesCount': 8,
          'title': '精彩视频内容1',
          'description': '这是一个精彩的视频内容，展示了各种有趣的内容。',
          'createdAt': DateTime.now().subtract(const Duration(hours: 2)),
        },
        {
          'id': 'video_2',
          'username': 'user2',
          'displayName': '视频创作者2',
          'avatar': 'https://picsum.photos/100/100?random=2',
          'videoUrl': 'https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_2mb.mp4',
          'thumbnailUrl': 'https://picsum.photos/400/600?random=102',
          'duration': 180,
          'likesCount': 89,
          'savesCount': 15,
          'commentsCount': 22,
          'sharesCount': 5,
          'title': '精彩视频内容2',
          'description': '另一个精彩的视频内容，内容丰富多样。',
          'createdAt': DateTime.now().subtract(const Duration(hours: 4)),
        },
        {
          'id': 'video_3',
          'username': 'user3',
          'displayName': '视频创作者3',
          'avatar': 'https://picsum.photos/100/100?random=3',
          'videoUrl': 'https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_5mb.mp4',
          'thumbnailUrl': 'https://picsum.photos/400/600?random=103',
          'duration': 240,
          'likesCount': 234,
          'savesCount': 45,
          'commentsCount': 67,
          'sharesCount': 12,
          'title': '精彩视频内容3',
          'description': '第三个精彩的视频内容，内容更加丰富。',
          'createdAt': DateTime.now().subtract(const Duration(hours: 6)),
        },
      ]);
    });
  }

  void _onVideoTap(Map<String, dynamic> video, int index) {
    // 创建媒体项列表
    final mediaItems = _videos.map((video) => MediaItem(
      type: 'video',
      url: video['videoUrl'],
      aspectRatio: 9 / 16,
    )).toList();

    // 创建帖子列表
    final posts = _videos.map((video) => {
      'id': video['id'],
      'username': video['username'],
      'displayName': video['displayName'],
      'avatar': video['avatar'],
      'likesCount': video['likesCount'],
      'savesCount': video['savesCount'],
      'commentsCount': video['commentsCount'],
      'sharesCount': video['sharesCount'],
      'title': video['title'],
      'description': video['description'],
      'createdAt': video['createdAt'],
    }).toList();

    // 导航到视频媒体查看器
    context.push('/video-viewer/$index', extra: {
      'mediaItems': mediaItems,
      'posts': posts,
      'initialIndex': index,
    });
  }

  void _onUserTap(String username) {
    context.go('/user/$username');
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);

    return Scaffold(
      backgroundColor: isDark 
        ? AppColors.dark.backgroundPrimary
        : AppColors.light.backgroundPrimary,
      body: SafeArea(
        child: Column(
          children: [
            // 视频频道标题
            Container(
              padding: EdgeInsets.all(AppSpacing.md),
              child: Row(
                children: [
                  Icon(
                    Icons.play_circle_filled,
                    color: AppColors.primaryColor,
                    size: AppSpacing.iconLarge,
                  ),
                  SizedBox(width: AppSpacing.sm),
                  Text(
                    '视频频道',
                    style: TextStyle(
                      fontSize: AppTypography.xl,
                      fontWeight: FontWeight.bold,
                      color: isDark 
                        ? AppColors.dark.foregroundPrimary 
                        : AppColors.light.foregroundPrimary,
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    onPressed: () {
                      // 搜索功能
                    },
                    icon: Icon(
                      Icons.search,
                      color: isDark 
                        ? AppColors.dark.foregroundSecondary 
                        : AppColors.light.foregroundSecondary,
                    ),
                  ),
                ],
              ),
            ),
            
            // 视频列表
            Expanded(
              child: RefreshIndicator(
                onRefresh: () async {
                  _loadVideos();
                },
                child: ListView.builder(
                  controller: _scrollController,
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                  itemCount: _videos.length,
                  itemBuilder: (context, index) {
                    final video = _videos[index];
                    return Padding(
                      padding: EdgeInsets.only(bottom: AppSpacing.md),
                      child: VideoPostCard(
                        post: video,
                        onPostTap: (post, index) => _onVideoTap(post, index),
                        onUserTap: _onUserTap,
                        onLike: (post) {
                          // 处理点赞
                          setState(() {
                            video['likesCount'] = (video['likesCount'] as int) + 1;
                          });
                        },
                        onComment: (post) {
                          // 处理评论
                          _onVideoTap(post, index);
                        },
                        onShare: (post) {
                          // 处理分享
                        },
                        onBookmark: (post) {
                          // 处理收藏
                          setState(() {
                            video['savesCount'] = (video['savesCount'] as int) + 1;
                          });
                        },
                        onMore: (post) {
                          // 处理更多操作
                        },
                      ),
                    );
                  },
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
