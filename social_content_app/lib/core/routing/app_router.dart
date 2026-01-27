import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

// 导入页面
import '../../features/auth/pages/login_page.dart';
import '../../features/auth/pages/register_page.dart';
import '../../features/profile/pages/profile_page.dart';
import '../../features/profile/pages/edit_profile_page.dart';
import '../../features/feed/pages/feed_page.dart';
import '../../features/content_creation/pages/create_post_page.dart';
import '../../features/content_creation/pages/camera_page.dart';
import '../../features/chat/pages/chat_list_page.dart';
import '../../features/chat/pages/chat_detail_page.dart';
import '../../features/discovery/pages/discovery_page.dart';
import '../widgets/main_navigation.dart';

// 路由配置
final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/login',
    debugLogDiagnostics: true,
    routes: [
      // 认证路由
      GoRoute(
        path: '/login',
        name: 'login',
        builder: (context, state) => const LoginPage(),
      ),
      GoRoute(
        path: '/register',
        name: 'register',
        builder: (context, state) => const RegisterPage(),
      ),
      
      // 主应用路由
      ShellRoute(
        builder: (context, state, child) => MainNavigation(child: child),
        routes: [
          // 首页/动态
          GoRoute(
            path: '/feed',
            name: 'feed',
            builder: (context, state) => const FeedPage(),
          ),
          
          // 发现
          GoRoute(
            path: '/discovery',
            name: 'discovery',
            builder: (context, state) => const DiscoveryPage(),
          ),
          
          // 内容创作
          GoRoute(
            path: '/create',
            name: 'create',
            builder: (context, state) => const CreatePostPage(),
          ),
          
          // 聊天
          GoRoute(
            path: '/chat',
            name: 'chat',
            builder: (context, state) => const ChatListPage(),
          ),
          
          // 个人资料
          GoRoute(
            path: '/profile',
            name: 'profile',
            builder: (context, state) => const ProfilePage(),
          ),
        ],
      ),
      
      // 独立页面路由
      GoRoute(
        path: '/camera',
        name: 'camera',
        builder: (context, state) => const CameraPage(),
      ),
      
      GoRoute(
        path: '/chat/:chatId',
        name: 'chat-detail',
        builder: (context, state) {
          final chatId = state.pathParameters['chatId']!;
          return ChatDetailPage(chatId: chatId);
        },
      ),
      
      GoRoute(
        path: '/profile/edit',
        name: 'edit-profile',
        builder: (context, state) => const EditProfilePage(),
      ),
      
      GoRoute(
        path: '/user/:userId',
        name: 'user-profile',
        builder: (context, state) {
          final userId = state.pathParameters['userId']!;
          return ProfilePage(userId: userId);
        },
      ),
    ],
    
    // 重定向逻辑
    redirect: (context, state) {
      // 这里可以添加认证检查逻辑
      // 例如：如果用户未登录，重定向到登录页面
      return null;
    },
    
    // 错误处理
    errorBuilder: (context, state) => Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(
              Icons.error_outline,
              size: 64,
              color: Colors.red,
            ),
            const SizedBox(height: 16),
            Text(
              '页面未找到',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            Text(
              state.error?.toString() ?? '未知错误',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () => context.go('/feed'),
              child: const Text('返回首页'),
            ),
          ],
        ),
      ),
    ),
  );
});

// 路由扩展方法
extension AppRouterExtension on BuildContext {
  void goToLogin() => go('/login');
  void goToRegister() => go('/register');
  void goToFeed() => go('/feed');
  void goToDiscovery() => go('/discovery');
  void goToCreate() => go('/create');
  void goToChat() => go('/chat');
  void goToProfile() => go('/profile');
  void goToCamera() => go('/camera');
  void goToEditProfile() => go('/profile/edit');
  void goToUserProfile(String userId) => go('/user/$userId');
  void goToChatDetail(String chatId) => go('/chat/$chatId');
  
  void pushLogin() => push('/login');
  void pushRegister() => push('/register');
  void pushCreate() => push('/create');
  void pushCamera() => push('/camera');
  void pushEditProfile() => push('/profile/edit');
  void pushUserProfile(String userId) => push('/user/$userId');
  void pushChatDetail(String chatId) => push('/chat/$chatId');
}

