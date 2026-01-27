import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/features/home/pages/home_page.dart';
import 'package:quwoquan_app/features/search/pages/search_page.dart';
import 'package:quwoquan_app/features/create/pages/create_page.dart';
import 'package:quwoquan_app/features/chat/pages/chat_page.dart';
import 'package:quwoquan_app/features/profile/pages/my_profile_page.dart';
import 'package:quwoquan_app/features/profile/pages/user_profile_page.dart';
import 'package:quwoquan_app/features/media_viewer/pages/immersive_media_viewer_page.dart';
import 'package:quwoquan_app/features/settings/pages/settings_page.dart';
import 'package:quwoquan_app/features/video/pages/video_channel_page.dart';
import 'package:quwoquan_app/features/video/pages/video_media_viewer_page.dart';
import 'package:quwoquan_app/shared/components/immersive_media_viewer.dart';
import 'package:quwoquan_app/app/layout/main_layout.dart';

/// 路由常量
class AppRoutes {
  static const String home = '/';
  static const String search = '/search';
  static const String create = '/create';
  static const String chat = '/chat';
  static const String profile = '/profile';
  static const String settings = '/settings';
  static const String userProfile = '/user/:username';
  static const String mediaViewer = '/media-viewer/:username/:photoIndex';
  static const String videoChannel = '/video';
  static const String videoViewer = '/video-viewer/:index';
}

/// 路由参数常量
class RouteParams {
  static const String username = 'username';
  static const String photoIndex = 'photoIndex';
}

/// 应用路由配置
final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: AppRoutes.home,
    routes: [
      // 主布局路由
      ShellRoute(
        builder: (context, state, child) {
          return MainLayout(initialRoute: state.uri.path);
        },
        routes: [
          // 首页
          GoRoute(
            path: AppRoutes.home,
            builder: (context, state) {
              return const HomePage(initialTab: 'following');
            },
          ),
          
          // 搜索页
          GoRoute(
            path: AppRoutes.search,
            builder: (context, state) {
              return const SearchPage();
            },
          ),
          
          // 创作页
          GoRoute(
            path: AppRoutes.create,
            builder: (context, state) {
              return const CreatePage();
            },
          ),
          
          // 聊天页
          GoRoute(
            path: AppRoutes.chat,
            builder: (context, state) {
              return const ChatPage();
            },
          ),
          
          // 我的主页
          GoRoute(
            path: AppRoutes.profile,
            builder: (context, state) {
              return const MyProfilePage();
            },
          ),
          
          // 设置页
          GoRoute(
            path: AppRoutes.settings,
            builder: (context, state) {
              return const SettingsPage();
            },
          ),
        ],
      ),
      
      // 用户主页
      GoRoute(
        path: AppRoutes.userProfile,
        builder: (context, state) {
          final username = state.pathParameters[RouteParams.username]!;
          return UserProfilePage(username: username);
        },
      ),
      
      // 媒体查看器
      GoRoute(
        path: AppRoutes.mediaViewer,
        builder: (context, state) {
          final username = state.pathParameters[RouteParams.username]!;
          final photoIndex = int.parse(state.pathParameters[RouteParams.photoIndex]!);
          debugPrint('MediaViewer route matched: username=$username, photoIndex=$photoIndex');
          return ImmersiveMediaViewerPage(
            username: username,
            initialIndex: photoIndex,
          );
        },
      ),
      
      // 视频频道
      GoRoute(
        path: AppRoutes.videoChannel,
        builder: (context, state) {
          return const VideoChannelPage();
        },
      ),
      
      // 视频媒体查看器
      GoRoute(
        path: AppRoutes.videoViewer,
        builder: (context, state) {
          final index = int.parse(state.pathParameters['index']!);
          final extra = state.extra as Map<String, dynamic>?;
          final mediaItems = extra?['mediaItems'] as List<dynamic>? ?? [];
          final posts = extra?['posts'] as List<dynamic>? ?? [];
          
          return VideoMediaViewerPage(
            initialIndex: index,
            mediaItems: mediaItems.cast<MediaItem>(),
            posts: posts,
          );
        },
      ),
    ],
    errorBuilder: (context, state) {
      return Scaffold(
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.error_outline,
                size: 64,
                color: Colors.grey,
              ),
              const SizedBox(height: 16),
              Text(
                '页面未找到',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
              const SizedBox(height: 8),
              Text(
                '路径: ${state.uri}',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: () => context.go(AppRoutes.home),
                child: const Text('返回首页'),
              ),
            ],
          ),
        ),
      );
    },
  );
});