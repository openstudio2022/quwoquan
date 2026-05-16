import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/app_page_access_navigator_observer.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/ui/user/pages/other_profile_page.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/ui/content/models/content_route_models.dart';
import 'package:quwoquan_app/ui/content/pages/article_detail_page.dart';
import 'package:quwoquan_app/ui/content/pages/photo_detail_page.dart';
import 'package:quwoquan_app/ui/content/pages/unified_media_viewer_page.dart';
import 'package:quwoquan_app/ui/content/pages/video_detail_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_stats_page.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_draft_picker_flow.dart';
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
import 'package:quwoquan_app/ui/chat/pages/group_member_search_page.dart';
import 'package:quwoquan_app/ui/chat/pages/start_group_chat_page.dart';
import 'package:quwoquan_app/ui/search/pages/global_search_page.dart';
import 'package:quwoquan_app/ui/search/pages/search_network_results_page.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_claim_page.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_detail_page.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_maintenance_page.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_picker_page.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_status_report_page.dart';
import 'package:quwoquan_app/ui/entity/pages/suggest_homepage_page.dart';
import 'package:quwoquan_app/ui/user/pages/edit_profile_page.dart';
import 'package:quwoquan_app/ui/user/pages/persona_management_page.dart';
import 'package:quwoquan_app/ui/user/pages/profile_comments_page.dart';
import 'package:quwoquan_app/ui/user/pages/profile_stats_page.dart';
import 'package:quwoquan_app/ui/user/pages/resonance_page.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_management_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_center_page.dart';
import 'package:quwoquan_app/ui/assistant/pages/personal_assistant_conversation_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/outgoing_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/incoming_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/voice_call_page.dart';
import 'package:quwoquan_app/ui/rtc/pages/video_call_page.dart';
import 'package:quwoquan_app/ui/rtc/models/call_participant_picker_route_extra.dart';
import 'package:quwoquan_app/ui/rtc/pages/call_participant_picker_page.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final refreshListenable = ValueNotifier<int>(0);
  AppPageAccessNavigatorObserver.instance.attachVisitRecorder(
    ref.read(visitRecorderServiceProvider),
  );
  AppPageAccessNavigatorObserver.instance.attachEventReporter(
    repository: ref.read(opsEventRepositoryProvider),
    currentUserId: ref.read(currentUserIdProvider),
    experimentBucket: ref.read(contentRuntimeConfigProvider).experimentBucket,
  );
  ref.listen<bool>(welcomeCompletedProvider, (Object? previous, bool next) {
    refreshListenable.value++;
  });

  return GoRouter(
    refreshListenable: refreshListenable,
    observers: <NavigatorObserver>[AppPageAccessNavigatorObserver.instance],
    initialLocation: ref.read(welcomeCompletedProvider)
        ? AppRoutePaths.home
        : AppRoutePaths.welcome,
    redirect: (BuildContext context, GoRouterState state) {
      final done = ref.read(welcomeCompletedProvider);
      final loc = state.matchedLocation;
      if (!done && loc != AppRoutePaths.welcome) {
        return AppRoutePaths.welcome;
      }
      if (done && loc == AppRoutePaths.welcome) {
        return AppRoutePaths.home;
      }
      return null;
    },
    routes: [
      GoRoute(
        path: AppRoutePaths.welcome,
        pageBuilder: (context, state) => NoTransitionPage<void>(
          key: state.pageKey,
          child: WelcomeScreen(
            onFinish: () {
              ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
            },
          ),
        ),
      ),
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
              child: const SizedBox.shrink(), // 圈子独立列表页在 MainAppShell 中渲染
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
        path: AppRoutePaths.startGroupChat,
        pageBuilder: (context, state) => MaterialPage<void>(
          key: state.pageKey,
          fullscreenDialog: true,
          child: StartGroupChatPage(
            onBack: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go(AppRoutePaths.chat);
              }
            },
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.globalSearch,
        pageBuilder: (context, state) {
          final launchContext = state.extra is SearchLaunchContext
              ? state.extra! as SearchLaunchContext
              : SearchLaunchContext(entrySurfaceId: AppRoutePaths.globalSearch);
          return CustomTransitionPage<void>(
            key: state.pageKey,
            child: GlobalSearchPage(launchContext: launchContext),
            transitionDuration: const Duration(milliseconds: 220),
            reverseTransitionDuration: const Duration(milliseconds: 180),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
                  final curved = CurvedAnimation(
                    parent: animation,
                    curve: Curves.easeOutCubic,
                    reverseCurve: Curves.easeInCubic,
                  );
                  return FadeTransition(
                    opacity: curved,
                    child: SlideTransition(
                      position: Tween<Offset>(
                        begin: const Offset(0, -0.02),
                        end: Offset.zero,
                      ).animate(curved),
                      child: child,
                    ),
                  );
                },
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.globalSearchNetworkResultsPathTemplate,
        pageBuilder: (context, state) {
          final extraLaunchContext = state.extra is SearchLaunchContext
              ? state.extra! as SearchLaunchContext
              : null;
          final query =
              state.uri.queryParameters['query'] ??
              extraLaunchContext?.prefilledQuery ??
              '';
          final initialTabId =
              state.uri.queryParameters['tab'] ??
              extraLaunchContext?.initialNetworkTabId;
          final launchContext =
              (extraLaunchContext ??
                      const SearchLaunchContext(
                        entrySurfaceId: 'globalSearchNetworkResults',
                      ))
                  .copyWith(
                    prefilledQuery: query,
                    initialNetworkTabId: initialTabId,
                    restoreState: false,
                  );
          return CustomTransitionPage<void>(
            key: state.pageKey,
            child: SearchNetworkResultsPage(launchContext: launchContext),
            transitionDuration: const Duration(milliseconds: 220),
            reverseTransitionDuration: const Duration(milliseconds: 180),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
                  final curved = CurvedAnimation(
                    parent: animation,
                    curve: Curves.easeOutCubic,
                    reverseCurve: Curves.easeInCubic,
                  );
                  return FadeTransition(
                    opacity: curved,
                    child: SlideTransition(
                      position: Tween<Offset>(
                        begin: const Offset(0, -0.02),
                        end: Offset.zero,
                      ).animate(curved),
                      child: child,
                    ),
                  );
                },
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.homepagePickerPathTemplate,
        pageBuilder: (context, state) {
          final extra = state.extra is HomepagePickerPageRouteExtra
              ? state.extra! as HomepagePickerPageRouteExtra
              : null;
          final query = state.uri.queryParameters['query'] ?? '';
          return CustomTransitionPage<HomepagePickerSelectionResult>(
            key: state.pageKey,
            child: HomepagePickerPage(
              initialQuery: query,
              initialSelection: extra?.initialSelection,
            ),
            transitionDuration: const Duration(milliseconds: 220),
            reverseTransitionDuration: const Duration(milliseconds: 180),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
                  final curved = CurvedAnimation(
                    parent: animation,
                    curve: Curves.easeOutCubic,
                    reverseCurve: Curves.easeInCubic,
                  );
                  return FadeTransition(
                    opacity: curved,
                    child: SlideTransition(
                      position: Tween<Offset>(
                        begin: const Offset(0, 0.02),
                        end: Offset.zero,
                      ).animate(curved),
                      child: child,
                    ),
                  );
                },
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.suggestHomepagePathTemplate,
        pageBuilder: (context, state) {
          final query = state.uri.queryParameters['query'] ?? '';
          return MaterialPage<void>(
            key: state.pageKey,
            fullscreenDialog: true,
            child: SuggestHomepagePage(initialQuery: query),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.homepageDetailPathTemplate.replaceAll(
          '{id}',
          ':id',
        ),
        builder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          final extra = state.extra is HomepageDetailPageRouteExtra
              ? state.extra! as HomepageDetailPageRouteExtra
              : null;
          return HomepageDetailPage(
            homepageId: id,
            selectionMode: extra?.selectionMode ?? false,
            initialSummary: extra?.initialSummary,
            referralSource: extra?.referralSource ?? ReferralSource.entityPage,
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.homepageClaimPathTemplate.replaceAll('{id}', ':id'),
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return MaterialPage<void>(
            key: state.pageKey,
            fullscreenDialog: true,
            child: HomepageClaimPage(homepageId: id),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.homepageMaintenancePathTemplate.replaceAll(
          '{id}',
          ':id',
        ),
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return MaterialPage<void>(
            key: state.pageKey,
            fullscreenDialog: true,
            child: HomepageMaintenancePage(homepageId: id),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.homepageStatusReportPathTemplate.replaceAll(
          '{id}',
          ':id',
        ),
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return MaterialPage<void>(
            key: state.pageKey,
            fullscreenDialog: true,
            child: HomepageStatusReportPage(homepageId: id),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.createEntry,
        pageBuilder: (context, state) {
          return CustomTransitionPage<void>(
            key: state.pageKey,
            opaque: false,
            barrierColor: Colors.transparent,
            child: const _CreateEntryRoutePage(),
            transitionDuration: const Duration(milliseconds: 280),
            reverseTransitionDuration: const Duration(milliseconds: 220),
            transitionsBuilder:
                (context, animation, secondaryAnimation, child) {
                  final curved = CurvedAnimation(
                    parent: animation,
                    curve: Curves.easeOutCubic,
                    reverseCurve: Curves.easeInCubic,
                  );
                  return SlideTransition(
                    position: Tween<Offset>(
                      begin: const Offset(0, 1),
                      end: Offset.zero,
                    ).animate(curved),
                    child: child,
                  );
                },
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.createPathTemplate,
        builder: (context, state) {
          final typeStr = state.uri.queryParameters['type'];
          final initialTabKey = state.uri.queryParameters['tab'];
          final initialHomepage = state.extra is HomepageCanonicalReference
              ? state.extra! as HomepageCanonicalReference
              : null;
          final draftIdRaw = state.uri.queryParameters['draftId']?.trim();
          final initialDraftId = draftIdRaw != null && draftIdRaw.isNotEmpty
              ? draftIdRaw
              : null;
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
            initialHomepage: initialHomepage,
            initialDraftId: initialDraftId,
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
          final circleExtra = state.extra is CircleDetailPageRouteExtra
              ? state.extra! as CircleDetailPageRouteExtra
              : null;
          return CircleDetailPage(
            circleId: id,
            referralSource: circleExtra?.referralSource ?? ReferralSource.organicFeed,
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
          final extra = state.extra is ArticleDetailPageRouteExtra
              ? state.extra! as ArticleDetailPageRouteExtra
              : null;
          return ArticleDetailPage(
            articleId: id,
            referralSource: extra?.referralSource ?? ReferralSource.organicFeed,
            feedRequestId: extra?.feedRequestId,
          );
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
          ReferralSource profileReferralSource = ReferralSource.authorProfile;
          if (state.extra is OtherProfilePageRouteExtra) {
            final profileExtra = state.extra! as OtherProfilePageRouteExtra;
            profileReferralSource = profileExtra.referralSource ?? ReferralSource.authorProfile;
            extra = UserProfileRouteExtra(
              subAccountId: profileExtra.subAccountId,
              avatar: profileExtra.avatar,
              displayName: profileExtra.displayName,
              backgroundImage: profileExtra.backgroundImage,
            );
          } else if (state.extra is UserProfileRouteExtra) {
            extra = state.extra! as UserProfileRouteExtra;
          } else if (state.extra is Map) {
            final m = state.extra! as Map;
            extra = UserProfileRouteExtra(
              subAccountId:
                  (m['subAccountId'] ?? m['profileSubjectId'])?.toString(),
              avatar: m['avatar']?.toString(),
              displayName: m['displayName']?.toString(),
              backgroundImage: m['backgroundImage']?.toString(),
            );
          }
          return OtherProfilePage(
            username: username,
            subAccountId: extra?.safeSubAccountId,
            initialAvatarUrl: extra?.safeAvatar,
            initialDisplayName: extra?.safeDisplayName,
            initialBackgroundImageUrl: extra?.safeBackgroundImage,
            referralSource: profileReferralSource,
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

          if (extra != null && extra.dtoPosts.isNotEmpty) {
            return UnifiedMediaViewerPage(extra: extra);
          }

          return PhotoDetailPage(
            category: category,
            initialIndex: index,
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

          if (extra != null && extra.dtoPosts.isNotEmpty) {
            return UnifiedMediaViewerPage(extra: extra);
          }

          return VideoDetailPage(initialIndex: index, initialExtra: extra);
        },
      ),
      GoRoute(
        path: AppRoutePaths.assistantPersonal,
        builder: (context, state) {
          final assistantOpenContext = state.extra is AssistantOpenContext
              ? state.extra as AssistantOpenContext
              : null;
          return PersonalAssistantConversationPage(
            assistantOpenContext: assistantOpenContext,
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
          final searchAnchorContext =
              state.extra is SearchConversationAnchorContext
              ? state.extra as SearchConversationAnchorContext
              : null;
          final isAssistant = id == AppConceptConstants.assistantConversationId;
          void handleBack() {
            if (context.canPop()) {
              context.pop();
            } else if (isAssistant) {
              final lastTab = ref.read(lastMainTabBeforeAssistantProvider);
              ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
              final route = lastTab?.routePath ?? AppRoutePaths.chat;
              context.go(route);
            } else {
              context.go(AppRoutePaths.chat);
            }
          }

          if (isAssistant) {
            return PersonalAssistantConversationPage(
              onBack: handleBack,
              assistantOpenContext: assistantOpenContext,
            );
          }
          return ChatDetailPage(
            conversationId: id,
            onBack: handleBack,
            assistantOpenContext: assistantOpenContext,
            searchAnchorContext: searchAnchorContext,
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
            path: AppRoutePaths.chatMemberSearchSegment,
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return GroupMemberSearchPage(conversationId: id);
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
            path: AppRoutePaths.chatManageSegment,
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return GroupManagePage(conversationId: id);
            },
          ),
          GoRoute(
            path: AppRoutePaths.chatTransferOwnershipSegment,
            builder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return TransferOwnershipPage(conversationId: id);
            },
          ),
          GoRoute(
            path: AppRoutePaths.chatAdminsSegment,
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
          final extra = CallParticipantPickerRouteExtra.fromRouter(state.extra);
          return CallParticipantPickerPage(
            callId: extra.callId,
            maxParticipants: extra.maxParticipants,
            conversationId: extra.conversationId,
            defaultSelectAll: extra.defaultSelectAll,
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
    return CreateEntrySheet(
      isOpen: true,
      onClose: () => context.pop(),
      onSelect: (EditorStartAction action) {
        context.pop();
        context.go(AppRoutePaths.create(type: action.name));
      },
      onContinueFromDraft: () {
        final router = GoRouter.of(context);
        context.pop();
        WidgetsBinding.instance.addPostFrameCallback((_) {
          final navContext = router.routerDelegate.navigatorKey.currentContext;
          if (navContext != null) {
            unawaited(presentCreateDraftPickerAndGo(navContext, router));
          }
        });
      },
    );
  }
}
