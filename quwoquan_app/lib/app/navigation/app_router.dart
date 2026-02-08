import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/features/home/pages/home_page.dart';
import 'package:quwoquan_app/features/profile/pages/my_profile_page.dart';
import 'package:quwoquan_app/components/author_profile.dart';
import 'package:quwoquan_app/components/immersive_media_viewer.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(
        path: '/',
        pageBuilder: (context, state) => NoTransitionPage(
          key: state.pageKey,
          child: const HomePage(),
        ),
      ),
      GoRoute(
        path: '/my-profile',
        pageBuilder: (context, state) => NoTransitionPage(
          key: state.pageKey,
          child: const MyProfilePage(),
        ),
      ),
      GoRoute(
        path: '/user/:username',
        builder: (context, state) {
          final username = state.pathParameters['username'] ?? '';
          return AuthorProfile(
            username: username,
            onBack: () {
              // 安全地弹出路由，如果无法弹出则返回到首页
              if (context.canPop()) {
                context.pop();
              } else {
                context.go('/');
              }
            },
          );
        },
      ),
      GoRoute(
        path: '/media-viewer/:category/:index',
        builder: (context, state) {
          final category = state.pathParameters['category'] ?? 'images';
          final indexStr = state.pathParameters['index'] ?? '0';
          final index = int.tryParse(indexStr) ?? 0;
          
          // 获取数据服务
          final dataService = ref.read(dataServiceProvider);
          
          return _MediaViewerPage(
            category: category,
            initialIndex: index,
            dataService: dataService,
          );
        },
      ),
      GoRoute(
        path: '/video-viewer/:index',
        builder: (context, state) {
          final indexStr = state.pathParameters['index'] ?? '0';
          final index = int.tryParse(indexStr) ?? 0;
          
          // 获取数据服务
          final dataService = ref.read(dataServiceProvider);
          
          return _VideoViewerPage(
            initialIndex: index,
            dataService: dataService,
          );
        },
      ),
    ],
  );
});

/// 媒体查看器页面包装器
class _MediaViewerPage extends ConsumerStatefulWidget {
  final String category;
  final int initialIndex;
  final dynamic dataService;

  const _MediaViewerPage({
    required this.category,
    required this.initialIndex,
    required this.dataService,
  });

  @override
  ConsumerState<_MediaViewerPage> createState() => _MediaViewerPageState();
}

class _MediaViewerPageState extends ConsumerState<_MediaViewerPage> {
  bool _isOpen = true;
  List<MediaItem> _mediaItems = [];
  List<dynamic> _posts = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    try {
      // 加载帖子数据（不指定category，获取所有帖子）
      final posts = await widget.dataService.getDataList(
        endpoint: '/posts',
        params: {'category': widget.category == 'images' ? 'images' : null},
        limit: 100,
      );

      // 过滤出图片帖子
      final imagePosts = posts.where((post) {
        final postType = post['type'] as String?;
        final images = post['images'] as List<dynamic>? ?? [];
        return postType == 'image' && images.isNotEmpty;
      }).toList();
      
      if (imagePosts.isEmpty) {
        if (mounted) {
          setState(() {
            _isLoading = false;
          });
        }
        return;
      }

      // 转换为 MediaItem 和 posts
      _mediaItems = imagePosts.map<MediaItem>((post) {
        final images = post['images'] as List<dynamic>? ?? [];
        if (images.isNotEmpty) {
          return MediaItem(
            type: 'image',
            url: images[0].toString(),
          );
        }
        return MediaItem(
          type: 'image',
          url: 'https://picsum.photos/800/800?random=999',
        );
      }).toList();

      _posts = imagePosts;
      
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    } catch (e) {
      debugPrint('MediaViewer loadData error: $e');
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    
    if (_isLoading) {
      return Scaffold(
        backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        body: Center(
          child: CircularProgressIndicator(
            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
          ),
        ),
      );
    }

    if (!_isOpen || _mediaItems.isEmpty || _posts.isEmpty) {
      return Scaffold(
        backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.error_outline,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                size: 48.w,
              ),
              SizedBox(height: 16.h),
              Text(
                AppStrings.unableToLoadImage,
                style: TextStyle(
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                  fontSize: 16.sp,
                ),
              ),
              SizedBox(height: 16.h),
              ElevatedButton(
                onPressed: () => context.pop(),
                child: Text(AppStrings.back),
              ),
            ],
          ),
        ),
      );
    }

    // 确保索引在有效范围内
    final safeIndex = widget.initialIndex >= 0 && widget.initialIndex < _posts.length
        ? widget.initialIndex
        : 0;

    return ImmersiveMediaViewer(
      isOpen: _isOpen,
      onClose: () {
        setState(() {
          _isOpen = false;
        });
        context.pop();
      },
      mediaItems: _mediaItems,
      initialIndex: safeIndex < _mediaItems.length ? safeIndex : 0,
      posts: _posts,
      initialPostIndex: safeIndex,
      onUserClick: (username) {
        context.push('/user/$username');
      },
      getPostLikesCount: (post) => _getLikesCountFromPost(post),
      getPostBookmarksCount: (post) => _getBookmarksCountFromPost(post),
    );
  }
}

/// 从 post 安全获取点赞数。
/// 仅使用 [likesCount] 或 [likes]，无数据时回退为 0。
/// 禁止使用 commentsCount 作为回退，与 getPostBookmarksCount 行为一致。
int _getLikesCountFromPost(dynamic post) {
  if (post == null || post is! Map) return 0;
  final v = post['likesCount'] ?? post['likes'];
  if (v == null) return 0;
  return (v is int) ? v : (int.tryParse(v.toString()) ?? 0);
}

/// 从 post 安全获取收藏数（仅使用 bookmarks 相关字段，回退为 0）
int _getBookmarksCountFromPost(dynamic post) {
  if (post == null || post is! Map) return 0;
  final v = post['savesCount'] ?? post['bookmarks'];
  if (v == null) return 0;
  return (v is int) ? v : (int.tryParse(v.toString()) ?? 0);
}

/// 视频查看器页面包装器
class _VideoViewerPage extends ConsumerStatefulWidget {
  final int initialIndex;
  final dynamic dataService;

  const _VideoViewerPage({
    required this.initialIndex,
    required this.dataService,
  });

  @override
  ConsumerState<_VideoViewerPage> createState() => _VideoViewerPageState();
}

class _VideoViewerPageState extends ConsumerState<_VideoViewerPage> {
  bool _isOpen = true;
  List<MediaItem> _mediaItems = [];
  List<dynamic> _posts = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    try {
      // 加载视频帖子数据
      final posts = await widget.dataService.getDataList(
        endpoint: '/posts',
        params: {'category': 'video'},
        limit: 50,
      );

      // 转换为 MediaItem 和 posts
      _mediaItems = posts.map<MediaItem>((post) {
        final videoUrl = post['videoUrl'] as String?;
        if (videoUrl != null && videoUrl.isNotEmpty) {
          return MediaItem(
            type: 'video',
            url: videoUrl,
            aspectRatio: post['videoType'] == 'vertical' ? 9 / 16 : 16 / 9,
          );
        }
        return MediaItem(
          type: 'video',
          url: 'https://flutter.github.io/assets-for-api-docs/assets/videos/butterfly.mp4',
          aspectRatio: 16 / 9,
        );
      }).toList();

      _posts = posts;
      
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    
    if (_isLoading) {
      return Scaffold(
        backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        body: Center(
          child: CircularProgressIndicator(
            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
          ),
        ),
      );
    }

    if (!_isOpen || _mediaItems.isEmpty || _posts.isEmpty) {
      return Scaffold(
        backgroundColor: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.error_outline,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                size: 48.w,
              ),
              SizedBox(height: 16.h),
              Text(
                AppStrings.unableToLoadImage, // 复用字符串常量
                style: TextStyle(
                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                  fontSize: 16.sp,
                ),
              ),
              SizedBox(height: 16.h),
              ElevatedButton(
                onPressed: () => context.pop(),
                child: Text(AppStrings.back),
              ),
            ],
          ),
        ),
      );
    }

    // 确保索引在有效范围内
    final safeIndex = widget.initialIndex >= 0 && widget.initialIndex < _posts.length
        ? widget.initialIndex
        : 0;

    return ImmersiveMediaViewer(
      isOpen: _isOpen,
      onClose: () {
        setState(() {
          _isOpen = false;
        });
        context.pop();
      },
      mediaItems: _mediaItems,
      initialIndex: safeIndex < _mediaItems.length ? safeIndex : 0,
      posts: _posts,
      initialPostIndex: safeIndex,
      onUserClick: (username) {
        context.push('/user/$username');
      },
      getPostLikesCount: (post) => _getLikesCountFromPost(post),
      getPostBookmarksCount: (post) => _getBookmarksCountFromPost(post),
    );
  }
}
