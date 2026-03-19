import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/ui/user/pages/other_profile_page.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/pages/article_detail_page.dart';
import 'package:quwoquan_app/ui/content/pages/photo_detail_page.dart';
import 'package:quwoquan_app/ui/content/pages/unified_media_viewer_page.dart';
import 'package:quwoquan_app/ui/content/pages/video_detail_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_stats_page.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_entry_sheet.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/settings/pages/developer_settings_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_detail_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_settings_page.dart';
import 'package:quwoquan_app/ui/chat/pages/group_manage_page.dart';
import 'package:quwoquan_app/ui/chat/pages/transfer_ownership_page.dart';
import 'package:quwoquan_app/ui/chat/pages/group_admins_page.dart';
import 'package:quwoquan_app/ui/chat/pages/start_group_chat_page.dart';
import 'package:quwoquan_app/ui/user/pages/edit_profile_page.dart';
import 'package:quwoquan_app/ui/user/pages/persona_management_page.dart';
import 'package:quwoquan_app/ui/user/pages/profile_comments_page.dart';
import 'package:quwoquan_app/ui/user/pages/profile_stats_page.dart';
import 'package:quwoquan_app/ui/user/pages/resonance_page.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_management_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_center_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/outgoing_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/incoming_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/voice_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/video_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/call_participant_picker_page.dart';

String _routeFromMainTabIndex(int index) {
  switch (index) {
    case 0:
      return AppRoutePaths.home;
    case 1:
      return AppRoutePaths.assistant;
    case 2:
      return AppRoutePaths.chat;
    case 3:
      return AppRoutePaths.profile;
    default:
      return AppRoutePaths.chat;
  }
}

final appRouterProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: AppRoutePaths.home,
    routes: [
      ShellRoute(
        builder: (context, state, child) {
          return MainAppShell(currentLocation: state.uri.path, child: child);
        },
        routes: [
          GoRoute(
            path: AppRoutePaths.home,
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child:
                  const SizedBox.shrink(), // DiscoveryPage 在 MainAppShell 中渲染
            ),
          ),
          GoRoute(
            path: AppRoutePaths.circles,
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child: const SizedBox.shrink(), // CirclesPage 在 MainAppShell 中渲染
            ),
          ),
          GoRoute(
            path: AppRoutePaths.chat,
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child: const SizedBox.shrink(), // ChatPage 在 MainAppShell 中渲染
            ),
          ),
          GoRoute(
            path: AppRoutePaths.profile,
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child:
                  const SizedBox.shrink(), // MyProfilePage 在 MainAppShell 中渲染
            ),
          ),
          GoRoute(
            path: AppRoutePaths.assistant,
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child:
                  const SizedBox.shrink(), // AssistantHomePage 在 MainAppShell 中渲染
            ),
          ),
        ],
      ),
      GoRoute(
        path: AppRoutePaths.createEntry,
        builder: (context, state) {
          return const _CreateEntryRoutePage();
        },
      ),
      GoRoute(
        path: AppRoutePaths.createPathTemplate,
        builder: (context, state) {
          final typeStr = state.uri.queryParameters['type'];
          final initialTabKey = state.uri.queryParameters['tab'];
          EditorStartAction? action;
          if (typeStr != null) {
            try {
              action = EditorStartAction.values.firstWhere(
                (e) => e.name == typeStr,
              );
            } on StateError {
              action = null;
            }
          }
          return CreatePage(
            initialAction: action,
            initialTabKey: initialTabKey,
          );
        },
        routes: [
          GoRoute(
            path: AppRoutePaths.createEditImageSegment,
            pageBuilder: (context, state) {
              final path = state.uri.queryParameters['path'] ?? '';
              final source = state.uri.queryParameters['source'] ?? 'moment';
              final index =
                  int.tryParse(state.uri.queryParameters['index'] ?? '0') ?? 0;
              final total =
                  int.tryParse(state.uri.queryParameters['total'] ?? '1') ?? 1;
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
        path: AppRoutePaths.circleDetailPathTemplate.replaceAll('{id}', ':id'),
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return CircleDetailPage(
            circleId: id,
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go(AppRoutePaths.circles);
              }
            },
          );
        },
        routes: [
          GoRoute(
            path: AppRoutePaths.circleStatsSegment,
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              final type = state.uri.queryParameters['type'] ?? 'members';
              return CircleStatsPage(circleId: id, type: type);
            },
          ),
        ],
      ),
      GoRoute(
        path: AppRoutePaths.articleDetailPathTemplate.replaceAll('{id}', ':id'),
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '0';
          return ArticleDetailPage(articleId: id);
        },
      ),
      GoRoute(
        path: AppRoutePaths.userProfilePathTemplate.replaceAll(
          '{username}',
          ':username',
        ),
        builder: (context, state) {
          final username = state.pathParameters['username'] ?? '';
          final currentUser = ref.read(userDataProvider);
          final isSelf =
              currentUser != null &&
              (username == currentUser.id ||
                  (currentUser.username != null &&
                      username == currentUser.username));
          void onBack() {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go(AppRoutePaths.home);
            }
          }

          if (isSelf) {
            return MyProfilePage(onBack: onBack);
          }
          UserProfileRouteExtra? extra;
          if (state.extra is UserProfileRouteExtra) {
            extra = state.extra! as UserProfileRouteExtra;
          } else if (state.extra is Map) {
            final m = state.extra! as Map;
            extra = UserProfileRouteExtra(
              profileSubjectId: m['profileSubjectId']?.toString(),
              avatar: m['avatar']?.toString(),
              displayName: m['displayName']?.toString(),
              backgroundImage: m['backgroundImage']?.toString(),
            );
          }
          return OtherProfilePage(
            username: username,
            profileSubjectId: extra?.safeProfileSubjectId,
            initialAvatarUrl: extra?.safeAvatar,
            initialDisplayName: extra?.safeDisplayName,
            initialBackgroundImageUrl: extra?.safeBackgroundImage,
            onBack: onBack,
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.mediaViewerPathTemplate
            .replaceAll('{category}', ':category')
            .replaceAll('{index}', ':index'),
        builder: (context, state) {
          final category = state.pathParameters['category'] ?? 'images';
          final indexStr = state.pathParameters['index'] ?? '0';
          final index = int.tryParse(indexStr) ?? 0;
          final extra = state.extra is MediaViewerExtra
              ? state.extra! as MediaViewerExtra
              : null;
          final dataService = ref.read(dataServiceProvider);

          if (extra != null && extra.dtoPosts.isNotEmpty) {
            return UnifiedMediaViewerPage(extra: extra);
          }

          return PhotoDetailPage(
            category: category,
            initialIndex: index,
            dataService: dataService,
            initialExtra: extra,
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.videoViewerPathTemplate.replaceAll(
          '{index}',
          ':index',
        ),
        builder: (context, state) {
          final indexStr = state.pathParameters['index'] ?? '0';
          final index = int.tryParse(indexStr) ?? 0;
          final extra = state.extra is MediaViewerExtra
              ? state.extra! as MediaViewerExtra
              : null;
          final dataService = ref.read(dataServiceProvider);

          if (extra != null && extra.dtoPosts.isNotEmpty) {
            return UnifiedMediaViewerPage(extra: extra);
          }

          return VideoDetailPage(
            initialIndex: index,
            dataService: dataService,
            initialExtra: extra,
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.assistantManagement,
        builder: (context, state) {
          return AssistantManagementPage(
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go(AppRoutePaths.assistant);
              }
            },
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.assistantSkills,
        builder: (context, state) {
          return AssistantSkillCenterPage(
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go(AppRoutePaths.assistant);
              }
            },
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.settings,
        builder: (context, state) {
          return const SettingsPage();
        },
        routes: [
          GoRoute(
            path: AppRoutePaths.settingsDeveloperSegment,
            builder: (context, state) {
              return const DeveloperSettingsPage();
            },
          ),
        ],
      ),
      GoRoute(
        path: AppRoutePaths.profileEdit,
        builder: (context, state) {
          return const EditProfilePage();
        },
      ),
      GoRoute(
        path: AppRoutePaths.profilePersonas,
        builder: (context, state) {
          return const PersonaManagementPage();
        },
      ),
      GoRoute(
        path: AppRoutePaths.profileComments,
        builder: (context, state) {
          return const ProfileCommentsPage();
        },
      ),
      GoRoute(
        path: AppRoutePaths.profileResonance,
        builder: (context, state) {
          return const ResonancePage();
        },
      ),
      GoRoute(
        path: AppRoutePaths.profileStatsPathTemplate,
        builder: (context, state) {
          final type = state.uri.queryParameters['type'] ?? 'fans';
          final userId = state.uri.queryParameters['userId'] ?? '';
          return ProfileStatsPage(type: type, userId: userId);
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatDetailPathTemplate.replaceAll('{id}', ':id'),
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          final assistantOpenContext = state.extra is AssistantOpenContext
              ? state.extra as AssistantOpenContext
              : null;
          final isAssistant = id == AppConceptConstants.assistantConversationId;
          return ChatDetailPage(
            conversationId: id,
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else if (isAssistant) {
                final lastTab = ref.read(lastMainTabBeforeAssistantProvider);
                ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
                final route = lastTab != null
                    ? _routeFromMainTabIndex(lastTab)
                    : '/chat';
                context.go(route);
              } else {
                context.go(AppRoutePaths.chat);
              }
            },
            assistantOpenContext: assistantOpenContext,
          );
        },
        routes: [
          GoRoute(
            path: AppRoutePaths.chatSettingsSegment,
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return ChatSettingsPage(conversationId: id);
            },
          ),
          GoRoute(
            path: AppRoutePaths.chatAddMembersSegment,
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return StartGroupChatPage(
                conversationId: id,
                onBack: () {
                  if (context.canPop()) {
                    context.pop();
                  } else {
                    context.go(AppRoutePaths.chat);
                  }
                },
              );
            },
          ),
          GoRoute(
            path: 'manage',
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return GroupManagePage(conversationId: id);
            },
          ),
          GoRoute(
            path: 'transfer-ownership',
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return TransferOwnershipPage(conversationId: id);
            },
          ),
          GoRoute(
            path: 'admins',
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return GroupAdminsPage(conversationId: id);
            },
          ),
        ],
      ),
      GoRoute(
        path: AppRoutePaths.rtcOutgoingPathTemplate.replaceAll(
          '{callId}',
          ':callId',
        ),
        builder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return OutgoingCallPage(callId: callId);
        },
      ),
      GoRoute(
        path: AppRoutePaths.rtcIncomingPathTemplate.replaceAll(
          '{callId}',
          ':callId',
        ),
        builder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return IncomingCallPage(callId: callId);
        },
      ),
      GoRoute(
        path: AppRoutePaths.rtcVoicePathTemplate.replaceAll(
          '{callId}',
          ':callId',
        ),
        builder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return VoiceCallPage(callId: callId);
        },
      ),
      GoRoute(
        path: AppRoutePaths.rtcVideoPathTemplate.replaceAll(
          '{callId}',
          ':callId',
        ),
        builder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return VideoCallPage(callId: callId);
        },
      ),
      GoRoute(
        path: AppRoutePaths.rtcPickParticipants,
        builder: (context, state) {
          final extra = state.extra as Map<String, dynamic>?;
          return CallParticipantPickerPage(
            callId: extra?['callId'] as String?,
            maxParticipants: extra?['maxParticipants'] as int? ?? 32,
            conversationId: extra?['conversationId'] as String?,
            defaultSelectAll: extra?['defaultSelectAll'] as bool? ?? false,
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
        onSelect: (EditorStartAction action) {
          context.go(AppRoutePaths.create(type: action.name));
        },
      ),
    );
  }
}
