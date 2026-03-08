import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/ui/user/pages/other_profile_page.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/pages/article_detail_page.dart';
import 'package:quwoquan_app/ui/content/pages/photo_detail_page.dart';
import 'package:quwoquan_app/ui/content/pages/video_detail_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_stats_page.dart';
import 'package:quwoquan_app/features/create/components/create_entry_sheet.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/features/create/pages/create_page.dart';
import 'package:quwoquan_app/features/settings/pages/developer_settings_page.dart';
import 'package:quwoquan_app/features/settings/pages/settings_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_detail_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_settings_page.dart';
import 'package:quwoquan_app/ui/chat/pages/start_group_chat_page.dart';
import 'package:quwoquan_app/ui/user/pages/edit_profile_page.dart';
import 'package:quwoquan_app/ui/user/pages/persona_management_page.dart';
import 'package:quwoquan_app/ui/user/pages/profile_stats_page.dart';
import 'package:quwoquan_app/ui/user/pages/resonance_page.dart';
import 'package:quwoquan_app/features/assistant/context/assistant_open_context.dart';
import 'package:quwoquan_app/features/assistant/pages/assistant_home_page.dart';
import 'package:quwoquan_app/features/assistant/pages/assistant_management_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_center_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/outgoing_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/incoming_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/voice_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/video_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/call_participant_picker_page.dart';

String _routeFromMainTabIndex(int index) {
  switch (index) {
    case 0:
      return '/';
    case 1:
      return '/circles';
    case 3:
      return '/chat';
    case 4:
      return '/profile';
    default:
      return '/chat';
  }
}

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
          return CircleDetailPage(
            circleId: id,
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
          final extra = state.extra is UserProfileRouteExtra
              ? state.extra! as UserProfileRouteExtra
              : null;
          return OtherProfilePage(
            username: username,
            initialAvatarUrl: extra?.safeAvatar,
            initialDisplayName: extra?.safeDisplayName,
            initialBackgroundImageUrl: extra?.safeBackgroundImage,
            onBack: () {
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
          final extra = state.extra is MediaViewerExtra
              ? state.extra! as MediaViewerExtra
              : null;
          final dataService = ref.read(dataServiceProvider);

          return PhotoDetailPage(
            category: category,
            initialIndex: index,
            dataService: dataService,
            initialExtra: extra,
          );
        },
      ),
      GoRoute(
        path: '/video-viewer/:index',
        builder: (context, state) {
          final indexStr = state.pathParameters['index'] ?? '0';
          final index = int.tryParse(indexStr) ?? 0;
          final extra = state.extra is MediaViewerExtra
              ? state.extra! as MediaViewerExtra
              : null;
          final dataService = ref.read(dataServiceProvider);

          return VideoDetailPage(
            initialIndex: index,
            dataService: dataService,
            initialExtra: extra,
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
        path: '/assistant/skills',
        builder: (context, state) {
          return AssistantSkillCenterPage(
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
        routes: [
          GoRoute(
            path: 'developer',
            builder: (context, state) {
              return const DeveloperSettingsPage();
            },
          ),
        ],
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
          final assistantOpenContext = state.extra is AssistantOpenContext
              ? state.extra as AssistantOpenContext
              : null;
          final isAssistant =
              id == AppConceptConstants.assistantConversationId;
          return ChatDetailPage(
            conversationId: id,
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else if (isAssistant) {
                final lastTab =
                    ref.read(lastMainTabBeforeAssistantProvider);
                ref.read(lastMainTabBeforeAssistantProvider.notifier)
                    .set(null);
                final route = lastTab != null
                    ? _routeFromMainTabIndex(lastTab)
                    : '/chat';
                context.go(route);
              } else {
                context.go('/chat');
              }
            },
            assistantOpenContext: assistantOpenContext,
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
      GoRoute(
        path: '/rtc/outgoing/:callId',
        builder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return OutgoingCallPage(callId: callId);
        },
      ),
      GoRoute(
        path: '/rtc/incoming/:callId',
        builder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return IncomingCallPage(callId: callId);
        },
      ),
      GoRoute(
        path: '/rtc/voice/:callId',
        builder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return VoiceCallPage(callId: callId);
        },
      ),
      GoRoute(
        path: '/rtc/video/:callId',
        builder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return VideoCallPage(callId: callId);
        },
      ),
      GoRoute(
        path: '/rtc/pick-participants',
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>?;
          return CallParticipantPickerPage(
            callId: extra?['callId'] as String?,
            maxParticipants: extra?['maxParticipants'] as int? ?? 32,
          );
        },
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

