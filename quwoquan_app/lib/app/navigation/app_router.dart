import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/components/author_profile.dart';
import 'package:quwoquan_app/components/media/image/viewer/immersive_image_viewer.dart';
import 'package:quwoquan_app/components/media/video/viewer/immersive_video_viewer.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/content/pages/article_detail_page.dart';
import 'package:quwoquan_app/features/circles/pages/circle_detail_page.dart';
import 'package:quwoquan_app/features/circles/pages/circle_stats_page.dart';
import 'package:quwoquan_app/features/create/components/create_entry_sheet.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/features/create/pages/create_page.dart';
import 'package:quwoquan_app/features/settings/pages/settings_page.dart';
import 'package:quwoquan_app/features/chat/pages/chat_detail_page.dart';
import 'package:quwoquan_app/features/chat/pages/chat_settings_page.dart';
import 'package:quwoquan_app/features/chat/pages/start_group_chat_page.dart';
import 'package:quwoquan_app/features/profile/pages/edit_profile_page.dart';
import 'package:quwoquan_app/features/profile/pages/persona_management_page.dart';
import 'package:quwoquan_app/features/profile/pages/profile_stats_page.dart';
import 'package:quwoquan_app/features/profile/pages/resonance_page.dart';
import 'package:quwoquan_app/features/assistant/pages/assistant_home_page.dart';
import 'package:quwoquan_app/features/assistant/pages/assistant_management_page.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      ShellRoute(
        builder: (context, state, child) {
          return MainAppShell(
            currentLocation: state.uri.path,
            child: child,
          );
        },
        routes: [
          GoRoute(
            path: '/',
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child: const SizedBox.shrink(), // DiscoveryPage 在 MainAppShell 中渲染
            ),
          ),
          GoRoute(
            path: '/circles',
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child: const SizedBox.shrink(), // CirclesPage 在 MainAppShell 中渲染
            ),
          ),
          GoRoute(
            path: '/chat',
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child: const SizedBox.shrink(), // ChatPage 在 MainAppShell 中渲染
            ),
          ),
          GoRoute(
            path: '/profile',
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child: const SizedBox.shrink(), // MyProfilePage 在 MainAppShell 中渲染
            ),
          ),
        ],
      ),
      GoRoute(
        path: '/create-entry',
        builder: (context, state) {
          return const _CreateEntryRoutePage();
        },
      ),
      GoRoute(
        path: '/create',
        builder: (context, state) {
          final typeStr = state.uri.queryParameters['type'];
          CreateEntryType? type;
          if (typeStr != null) {
            try {
              type = CreateEntryType.values
                  .firstWhere((e) => e.name == typeStr);
            } on StateError {
              type = null;
            }
          }
          return CreatePage(initialType: type);
        },
        routes: [
          GoRoute(
            path: 'edit-image',
            pageBuilder: (context, state) {
              final path = state.uri.queryParameters['path'] ?? '';
              final source = state.uri.queryParameters['source'] ?? 'moment';
              final index = int.tryParse(state.uri.queryParameters['index'] ?? '0') ?? 0;
              final total = int.tryParse(state.uri.queryParameters['total'] ?? '1') ?? 1;
              final paths = <String>[];
              for (var i = 0; i < total; i++) {
                final p = state.uri.queryParameters['path$i'];
                if (p != null && p.isNotEmpty) paths.add(p);
              }
              if (paths.isEmpty && path.isNotEmpty) paths.add(path);
              return MaterialPage<void>(
                key: state.pageKey,
                fullscreenDialog: true,
                child: ImageEditorPage(
                  initialPath: path,
                  source: source,
                  index: index,
                  total: total,
                  imagePaths: paths.isNotEmpty ? paths : null,
                ),
              );
            },
          ),
        ],
      ),
      GoRoute(
        path: '/circle/:id',
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          final roleStr = state.uri.queryParameters['role'];
          CircleRole role = CircleRole.visitor;
          if (roleStr != null) {
            switch (roleStr) {
              case 'owner':
                role = CircleRole.owner;
                break;
              case 'admin':
                role = CircleRole.admin;
                break;
              case 'member':
                role = CircleRole.member;
                break;
              default:
                role = CircleRole.visitor;
            }
          }
          return CircleDetailPage(
            circleId: id,
            initialRole: role,
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go('/circles');
              }
            },
          );
        },
        routes: [
          GoRoute(
            path: 'stats',
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              final type = state.uri.queryParameters['type'] ?? 'members';
              return CircleStatsPage(circleId: id, type: type);
            },
          ),
        ],
      ),
      GoRoute(
        path: '/article/:id',
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '0';
          return ArticleDetailPage(articleId: id);
        },
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
      GoRoute(
        path: '/assistant',
        builder: (context, state) {
          return AssistantHomePage(
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go('/chat');
              }
            },
            onManageClick: () => context.push('/assistant/management'),
          );
        },
      ),
      GoRoute(
        path: '/assistant/management',
        builder: (context, state) {
          return AssistantManagementPage(
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go('/assistant');
              }
            },
          );
        },
      ),
      GoRoute(
        path: '/settings',
        builder: (context, state) {
          return const SettingsPage();
        },
      ),
      GoRoute(
        path: '/profile/edit',
        builder: (context, state) {
          return const EditProfilePage();
        },
      ),
      GoRoute(
        path: '/profile/personas',
        builder: (context, state) {
          return const PersonaManagementPage();
        },
      ),
      GoRoute(
        path: '/profile/resonance',
        builder: (context, state) {
          return const ResonancePage();
        },
      ),
      GoRoute(
        path: '/profile/stats',
        builder: (context, state) {
          final type =
              state.uri.queryParameters['type'] ?? 'fans';
          return ProfileStatsPage(type: type);
        },
      ),
      GoRoute(
        path: '/chat/:id',
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return ChatDetailPage(
            conversationId: id,
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go('/chat');
              }
            },
          );
        },
        routes: [
          GoRoute(
            path: 'settings',
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return ChatSettingsPage(conversationId: id);
            },
          ),
          GoRoute(
            path: 'add-members',
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return StartGroupChatPage(
                conversationId: id,
                onBack: () {
                  if (context.canPop()) {
                    context.pop();
                  } else {
                    context.go('/chat');
                  }
                },
              );
            },
          ),
        ],
      ),
    ],
  );
});

/// 创作入口抽屉的独立路由页（避免在 Shell 内 setState 导致 build scope 断言）
class _CreateEntryRoutePage extends ConsumerWidget {
  const _CreateEntryRoutePage();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Material(
      color: Colors.transparent,
      child: CreateEntrySheet(
        isOpen: true,
        onClose: () => context.pop(),
        onSelect: (CreateEntryType type) {
          // 用 go 替换当前路由，避免先 pop 再 push 导致 CreateEntrySheet 卸载时触发 Element 依赖断言
          context.go('/create?type=${type.name}');
        },
      ),
    );
  }
}

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

    final homeState = ref.watch(homeStateProvider);
    return ImmersiveImageViewer(
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
      onAssistantClick: () => context.push('/assistant'),
      likedPosts: homeState.likedPosts,
      savedPosts: homeState.savedPosts,
      getPostLikesCount: (post) {
        final id = post['id']?.toString() ?? '';
        final n = homeState.getPostLikesCount(id);
        if (n > 0) return n;
        return _getLikesCountFromPost(post);
      },
      getPostBookmarksCount: (post) {
        final id = post['id']?.toString() ?? '';
        final n = homeState.getPostBookmarksCount(id);
        if (n > 0) return n;
        return _getBookmarksCountFromPost(post);
      },
      onLikeClick: (post) {
        final id = post['id']?.toString() ?? '';
        ref.read(homeStateProvider).toggleLike(id);
      },
      onSaveClick: (post) {
        final id = post['id']?.toString() ?? '';
        ref.read(homeStateProvider).toggleSave(id);
      },
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

    final homeState = ref.watch(homeStateProvider);
    return ImmersiveVideoViewer(
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
      onAssistantClick: () => context.push('/assistant'),
      likedPosts: homeState.likedPosts,
      savedPosts: homeState.savedPosts,
      getPostLikesCount: (post) {
        final id = post['id']?.toString() ?? '';
        final n = homeState.getPostLikesCount(id);
        if (n > 0) return n;
        return _getLikesCountFromPost(post);
      },
      getPostBookmarksCount: (post) {
        final id = post['id']?.toString() ?? '';
        final n = homeState.getPostBookmarksCount(id);
        if (n > 0) return n;
        return _getBookmarksCountFromPost(post);
      },
      onLikeClick: (post) {
        final id = post['id']?.toString() ?? '';
        ref.read(homeStateProvider).toggleLike(id);
      },
      onSaveClick: (post) {
        final id = post['id']?.toString() ?? '';
        ref.read(homeStateProvider).toggleSave(id);
      },
    );
  }
}
