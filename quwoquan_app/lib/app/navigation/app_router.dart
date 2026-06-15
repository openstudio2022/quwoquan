import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/app/navigation/app_page_access_navigator_observer.dart';
import 'package:quwoquan_app/app/navigation/native_back_navigation.dart';
import 'package:quwoquan_app/app/providers/welcome_state_provider.dart';
import 'package:quwoquan_app/app/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/ui/user/pages/other_profile_page.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource, ReferralSourceExt;
import 'package:quwoquan_app/ui/content/models/content_route_models.dart';
import 'package:quwoquan_app/ui/content/pages/unified_media_viewer_page.dart';
import 'package:quwoquan_app/ui/content/pages/work_browser_entry_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_stats_page.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_draft_picker_flow.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/create_entry_sheet.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_entry_arguments.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/ui/content/entry/pages/create_page.dart';
import 'package:quwoquan_app/ui/settings/pages/developer_settings_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_page.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_conversation_page.dart';
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
import 'package:quwoquan_app/ui/entity/pages/homepage_introduction_page.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_maintenance_page.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_picker_page.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_status_report_page.dart';
import 'package:quwoquan_app/ui/entity/pages/suggest_homepage_page.dart';
import 'package:quwoquan_app/ui/intersection/pages/object_intersection_list_page.dart';
import 'package:quwoquan_app/ui/user/pages/edit_profile_page.dart';
import 'package:quwoquan_app/ui/user/pages/legal_document_page.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:quwoquan_app/ui/user/pages/persona_management_page.dart';
import 'package:quwoquan_app/ui/user/pages/profile_comments_page.dart';
import 'package:quwoquan_app/ui/user/pages/my_footprint_page.dart';
import 'package:quwoquan_app/ui/user/pages/my_intersection_inbox_page.dart';
import 'package:quwoquan_app/ui/user/pages/profile_stats_page.dart';
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

part 'app_router_create_entry_route.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final refreshListenable = ValueNotifier<int>(0);
  AppPageAccessNavigatorObserver.instance.attachVisitRecorder(
    ref.read(visitRecorderServiceProvider),
  );
  AppPageAccessNavigatorObserver.instance.attachEventReporter(
    repository: ref.read(opsEventRepositoryProvider),
    currentUserId: ref.read(currentUserIdProvider),
    experimentBucket: '',
  );
  ref.listen<bool>(welcomeCompletedProvider, (Object? previous, bool next) {
    refreshListenable.value++;
  });
  ref.listen<AuthSessionState>(authSessionControllerProvider, (
    Object? previous,
    AuthSessionState next,
  ) {
    refreshListenable.value++;
  });

  return GoRouter(
    refreshListenable: refreshListenable,
    observers: <NavigatorObserver>[
      AppPageAccessNavigatorObserver.instance,
      chatRouteObserver,
    ],
    initialLocation: ref.read(welcomeCompletedProvider)
        ? AppRoutePaths.home
        : AppRoutePaths.welcome,
    redirect: (BuildContext context, GoRouterState state) {
      final done = ref.read(welcomeCompletedProvider);
      final auth = ref.read(authSessionControllerProvider);
      final loc = state.matchedLocation;
      if (!done && loc != AppRoutePaths.welcome) {
        return AppRoutePaths.welcome;
      }
      if (done && loc == AppRoutePaths.welcome) {
        return AppRoutePaths.home;
      }
      if (done &&
          auth.isAuthenticated &&
          loc == AppRoutePaths.loginPathTemplate) {
        return AppRoutePaths.home;
      }
      // 防自重定向：登录页本身永不再被路由守卫拦截，否则 login→login 死循环。
      if (done && loc == AppRoutePaths.loginPathTemplate) {
        return null;
      }
      // 受限路由守卫：未登录直达需要账号身份的页面时跳全屏登录并带回源。
      // 会话恢复中（restoring）暂不拦截，避免已登录用户出现误跳闪烁。
      if (done && auth.status != AuthSessionStatus.restoring) {
        final gate = requiredRouteGateForLocation(loc);
        if (gate != null && !auth.isAuthenticated) {
          // 路由守卫触发的登录：关闭必须 go 到安全兜底，禁止 pop 回到受限路由，
          // 否则守卫会立刻再次命中、形成「关闭→又弹登录」死循环（消息/创作深链尤甚）。
          return buildLoginRouteLocation(
            reasonName: gate.name,
            redirect: state.uri.toString(),
            dismissFallback: AppRoutePaths.home,
            allowGuestDismissPop: false,
          );
        }
      }
      return null;
    },
    routes: [
      GoRoute(
        path: AppRoutePaths.welcome,
        pageBuilder: (context, state) => NoTransitionPage<void>(
          key: state.pageKey,
          child: Consumer(
            builder: (context, ref, _) => WelcomeScreen(
              loginPrompt: _welcomeLoginPromptConfig(context, ref),
              onFinish: () {
                _completeWelcome(ref);
              },
            ),
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.loginPathTemplate,
        pageBuilder: (context, state) => CupertinoPage<void>(
          key: state.pageKey,
          fullscreenDialog: true,
          child: LoginPage(
            reason: state.uri.queryParameters['reason'],
            redirect: state.uri.queryParameters['redirect'],
            dismissFallback:
                state.uri.queryParameters[loginDismissFallbackQueryParam],
            allowGuestDismissPop: loginGuestDismissCanPopFromQuery(
              state.uri.queryParameters[loginGuestDismissPopQueryParam],
            ),
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.legalUserAgreement,
        pageBuilder: (context, state) => CupertinoPage<void>(
          key: state.pageKey,
          child: const LegalDocumentPage(
            title: UITextConstants.userAgreement,
            url: AuthLegalConfig.userAgreementUrl,
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.legalPrivacyPolicy,
        pageBuilder: (context, state) => CupertinoPage<void>(
          key: state.pageKey,
          child: const LegalDocumentPage(
            title: UITextConstants.privacyPolicy,
            url: AuthLegalConfig.privacyPolicyUrl,
          ),
        ),
      ),
      ShellRoute(
        builder: (context, state, child) {
          return AppNativeBackScope(
            router: GoRouter.of(context),
            child: MainAppShell(currentLocation: state.uri.path, child: child),
          );
        },
        routes: [
          GoRoute(
            path: AppRoutePaths.home,
            pageBuilder: (context, state) => NoTransitionPage(
              key: state.pageKey,
              child:
                  const SizedBox.shrink(), // HomePage 由 MainAppShell 的 IndexedStack 承载渲染
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
            redirect: (context, state) => AppRoutePaths.assistantPersonal,
          ),
        ],
      ),
      GoRoute(
        path: AppRoutePaths.startGroupChat,
        pageBuilder: (context, state) => appRoutePage<void>(
          state: state,
          kind: AppRoutePageKind.fullscreenDialog,
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
          return appRoutePage<void>(
            state: state,
            child: GlobalSearchPage(launchContext: launchContext),
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
          return appRoutePage<void>(
            state: state,
            child: SearchNetworkResultsPage(launchContext: launchContext),
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
          return appRoutePage<HomepagePickerSelectionResult>(
            state: state,
            child: HomepagePickerPage(
              initialQuery: query,
              initialSelection: extra?.initialSelection,
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.suggestHomepagePathTemplate,
        pageBuilder: (context, state) {
          final query = state.uri.queryParameters['query'] ?? '';
          return appRoutePage<void>(
            state: state,
            kind: AppRoutePageKind.fullscreenDialog,
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
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          final extra = state.extra is HomepageDetailPageRouteExtra
              ? state.extra! as HomepageDetailPageRouteExtra
              : null;
          return appRoutePage<void>(
            state: state,
            child: HomepageDetailPage(
              homepageId: id,
              selectionMode: extra?.selectionMode ?? false,
              initialSummary: extra?.initialSummary,
              referralSource:
                  extra?.referralSource ?? ReferralSource.entityPage,
              feedRequestId: extra?.feedRequestId ?? '',
              recommendationTraceId: extra?.recommendationTraceId ?? '',
              experimentBucket: extra?.experimentBucket ?? '',
              rolloutCohort: extra?.rolloutCohort ?? '',
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.homepageIntroductionPathTemplate.replaceAll(
          '{id}',
          ':id',
        ),
        pageBuilder: (context, state) {
          final homepageId = state.pathParameters['id'] ?? '';
          final source = state.uri.queryParameters['source'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: HomepageIntroductionPage(
              homepageId: homepageId,
              referralSource: _referralSourceFromRoute(source),
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.homepageClaimPathTemplate.replaceAll('{id}', ':id'),
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return appRoutePage<void>(
            state: state,
            kind: AppRoutePageKind.fullscreenDialog,
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
          return appRoutePage<void>(
            state: state,
            kind: AppRoutePageKind.fullscreenDialog,
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
          return appRoutePage<void>(
            state: state,
            kind: AppRoutePageKind.fullscreenDialog,
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
        pageBuilder: (context, state) {
          final typeStr = state.uri.queryParameters['type'];
          final initialTabKey = state.uri.queryParameters['tab'];
          final entryArgs = state.extra is CreateEntryArguments
              ? state.extra! as CreateEntryArguments
              : null;
          final initialHomepage = state.extra is HomepageCanonicalReference
              ? state.extra! as HomepageCanonicalReference
              : entryArgs?.homepage;
          final initialCircleId = entryArgs?.circleId;
          final initialCircleName = entryArgs?.circleName;
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
          return appRoutePage<void>(
            state: state,
            child: CreatePage(
              initialAction: action,
              initialTabKey: initialTabKey,
              initialHomepage: initialHomepage,
              initialCircleId: initialCircleId,
              initialCircleName: initialCircleName,
              initialDraftId: initialDraftId,
            ),
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
              return appRoutePage<void>(
                state: state,
                kind: AppRoutePageKind.fullscreenDialog,
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
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          final circleExtra = state.extra is CircleDetailPageRouteExtra
              ? state.extra! as CircleDetailPageRouteExtra
              : null;
          return appRoutePage<void>(
            state: state,
            child: CircleDetailPage(
              circleId: id,
              referralSource:
                  circleExtra?.referralSource ?? ReferralSource.organicFeed,
              onBack: () {
                if (context.canPop()) {
                  context.pop();
                } else {
                  context.go(AppRoutePaths.circles);
                }
              },
            ),
          );
        },
        routes: [
          GoRoute(
            path: AppRoutePaths.circleStatsSegment,
            pageBuilder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              final type = state.uri.queryParameters['type'] ?? 'members';
              return appRoutePage<void>(
                state: state,
                child: CircleStatsPage(circleId: id, type: type),
              );
            },
          ),
        ],
      ),
      GoRoute(
        path: AppRoutePaths.userProfilePathTemplate.replaceAll(
          '{username}',
          ':username',
        ),
        pageBuilder: (context, state) {
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
            return appRoutePage<void>(
              state: state,
              child: MyProfilePage(onBack: onBack),
            );
          }
          UserProfileRouteExtra? extra;
          ReferralSource profileReferralSource = ReferralSource.authorProfile;
          if (state.extra is OtherProfilePageRouteExtra) {
            final profileExtra = state.extra! as OtherProfilePageRouteExtra;
            profileReferralSource =
                profileExtra.referralSource ?? ReferralSource.authorProfile;
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
              subAccountId: (m['subAccountId'] ?? m['profileSubjectId'])
                  ?.toString(),
              avatar: m['avatar']?.toString(),
              displayName: m['displayName']?.toString(),
              backgroundImage: m['backgroundImage']?.toString(),
            );
          }
          return appRoutePage<void>(
            state: state,
            child: OtherProfilePage(
              username: username,
              subAccountId: extra?.safeSubAccountId,
              initialAvatarUrl: extra?.safeAvatar,
              initialDisplayName: extra?.safeDisplayName,
              initialBackgroundImageUrl: extra?.safeBackgroundImage,
              referralSource: profileReferralSource,
              onBack: onBack,
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.workBrowserPathTemplate.replaceAll(
          '{workId}',
          ':workId',
        ),
        pageBuilder: (context, state) {
          final commentContext = MediaViewerCommentContext.fromQueryParameters(
            state.uri.queryParameters,
          );
          final extra = state.extra is MediaViewerExtra
              ? state.extra! as MediaViewerExtra
              : null;

          if (extra != null &&
              (extra.dtoPosts.isNotEmpty || extra.posts.isNotEmpty)) {
            return appRoutePage<void>(
              state: state,
              child: UnifiedMediaViewerPage(
                extra: extra.copyWith(commentContext: commentContext),
              ),
            );
          }

          // 直达 / 深链 / 评论跳原文：只有 :workId、无预置列表。按 id 直拉该帖
          // 组装单帖 viewer，避免丢弃 workId 回退到发现页推荐流（先前断点）。
          final workId = Uri.decodeComponent(
            state.pathParameters['workId'] ?? '',
          );
          return appRoutePage<void>(
            state: state,
            child: WorkBrowserEntryPage(
              workId: workId,
              source: state.uri.queryParameters['source'] ?? 'workBrowser',
              commentContext: commentContext,
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.assistantPersonal,
        pageBuilder: (context, state) {
          final assistantOpenContext = state.extra is AssistantOpenContext
              ? state.extra as AssistantOpenContext
              : null;
          return appRoutePage<void>(
            state: state,
            child: PersonalAssistantConversationPage(
              assistantOpenContext: assistantOpenContext,
              onBack: () {
                if (context.canPop()) {
                  context.pop();
                } else {
                  context.go(AppRoutePaths.home);
                }
              },
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.assistantManagement,
        pageBuilder: (context, state) {
          return appRoutePage<void>(
            state: state,
            child: AssistantManagementPage(
              onBack: () {
                if (context.canPop()) {
                  context.pop();
                } else {
                  context.go(AppRoutePaths.assistantPersonal);
                }
              },
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.assistantSkills,
        pageBuilder: (context, state) {
          return appRoutePage<void>(
            state: state,
            child: AssistantSkillCenterPage(
              onBack: () {
                if (context.canPop()) {
                  context.pop();
                } else {
                  context.go(AppRoutePaths.assistantPersonal);
                }
              },
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.settings,
        pageBuilder: (context, state) {
          return appRoutePage<void>(state: state, child: const SettingsPage());
        },
        routes: [
          GoRoute(
            path: AppRoutePaths.settingsDeveloperSegment,
            pageBuilder: (context, state) {
              return appRoutePage<void>(
                state: state,
                child: const DeveloperSettingsPage(),
              );
            },
          ),
        ],
      ),
      GoRoute(
        path: AppRoutePaths.profileEdit,
        pageBuilder: (context, state) =>
            appRoutePage<void>(state: state, child: const EditProfilePage()),
      ),
      GoRoute(
        path: AppRoutePaths.profilePersonas,
        pageBuilder: (context, state) => appRoutePage<void>(
          state: state,
          child: const PersonaManagementPage(),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.profileComments,
        pageBuilder: (context, state) => appRoutePage<void>(
          state: state,
          child: const ProfileCommentsPage(),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.profileStatsPathTemplate,
        pageBuilder: (context, state) {
          final type = state.uri.queryParameters['type'] ?? 'fans';
          final userId = state.uri.queryParameters['userId'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: ProfileStatsPage(type: type, userId: userId),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.myIntersectionsPathTemplate,
        pageBuilder: (context, state) => appRoutePage<void>(
          state: state,
          child: MyIntersectionInboxPage(
            dimension: state.uri.queryParameters['dimension'] ?? '',
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.objectIntersectionsPathTemplate,
        pageBuilder: (context, state) => appRoutePage<void>(
          state: state,
          child: ObjectIntersectionListPage(
            objectId: state.uri.queryParameters['objectId'] ?? '',
            objectType: state.uri.queryParameters['objectType'] ?? '',
            title: state.uri.queryParameters['title'] ?? '',
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.myFootprintPathTemplate,
        pageBuilder: (context, state) => appRoutePage<void>(
          state: state,
          child: MyFootprintPage(type: state.uri.queryParameters['type'] ?? ''),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.chatDetailPathTemplate.replaceAll('{id}', ':id'),
        pageBuilder: (context, state) {
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
            return appRoutePage<void>(
              state: state,
              child: PersonalAssistantConversationPage(
                onBack: handleBack,
                assistantOpenContext: assistantOpenContext,
              ),
            );
          }
          return appRoutePage<void>(
            state: state,
            child: ChatDetailPage(
              conversationId: id,
              onBack: handleBack,
              assistantOpenContext: assistantOpenContext,
              searchAnchorContext: searchAnchorContext,
            ),
          );
        },
        routes: [
          GoRoute(
            path: AppRoutePaths.chatSettingsSegment,
            pageBuilder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return appRoutePage<void>(
                state: state,
                child: ChatSettingsPage(conversationId: id),
              );
            },
          ),
          GoRoute(
            path: AppRoutePaths.chatMemberSearchSegment,
            pageBuilder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return appRoutePage<void>(
                state: state,
                child: GroupMemberSearchPage(conversationId: id),
              );
            },
          ),
          GoRoute(
            path: AppRoutePaths.chatAddMembersSegment,
            pageBuilder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return appRoutePage<void>(
                state: state,
                child: StartGroupChatPage(
                  conversationId: id,
                  onBack: () {
                    if (context.canPop()) {
                      context.pop();
                    } else {
                      context.go(AppRoutePaths.chat);
                    }
                  },
                ),
              );
            },
          ),
          GoRoute(
            path: AppRoutePaths.chatManageSegment,
            pageBuilder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return appRoutePage<void>(
                state: state,
                child: GroupManagePage(conversationId: id),
              );
            },
          ),
          GoRoute(
            path: AppRoutePaths.chatTransferOwnershipSegment,
            pageBuilder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return appRoutePage<void>(
                state: state,
                child: TransferOwnershipPage(conversationId: id),
              );
            },
          ),
          GoRoute(
            path: AppRoutePaths.chatAdminsSegment,
            pageBuilder: (context, state) {
              final id = state.pathParameters['id'] ?? '';
              return appRoutePage<void>(
                state: state,
                child: GroupAdminsPage(conversationId: id),
              );
            },
          ),
        ],
      ),
      GoRoute(
        path: AppRoutePaths.rtcOutgoingPathTemplate.replaceAll(
          '{callId}',
          ':callId',
        ),
        pageBuilder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: OutgoingCallPage(callId: callId),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.rtcIncomingPathTemplate.replaceAll(
          '{callId}',
          ':callId',
        ),
        pageBuilder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: IncomingCallPage(callId: callId),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.rtcVoicePathTemplate.replaceAll(
          '{callId}',
          ':callId',
        ),
        pageBuilder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: VoiceCallPage(callId: callId),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.rtcVideoPathTemplate.replaceAll(
          '{callId}',
          ':callId',
        ),
        pageBuilder: (context, state) {
          final callId = state.pathParameters['callId'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: VideoCallPage(callId: callId),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.rtcPickParticipants,
        pageBuilder: (context, state) {
          final extra = CallParticipantPickerRouteExtra.fromRouter(state.extra);
          return appRoutePage<void>(
            state: state,
            child: CallParticipantPickerPage(
              callId: extra.callId,
              maxParticipants: extra.maxParticipants,
              conversationId: extra.conversationId,
              defaultSelectAll: extra.defaultSelectAll,
            ),
          );
        },
      ),
    ],
  );
});

WelcomeLoginPromptConfig? _welcomeLoginPromptConfig(
  BuildContext context,
  WidgetRef ref,
) {
  final auth = ref.read(authSessionControllerProvider);
  final reason = auth.promptReason;
  if (auth.status != AuthSessionStatus.guest ||
      reason == null ||
      reason == AuthPromptReason.actionRequired ||
      reason == AuthPromptReason.sessionExpired) {
    return null;
  }
  return WelcomeLoginPromptConfig(
    title: UITextConstants.welcomeLoginPromptTitle,
    subtitle: UITextConstants.welcomeLoginPromptSubtitle,
    onLogin: () {
      _completeWelcome(ref);
      if (!context.mounted) {
        return;
      }
      openLoginPage(
        context,
        reasonName: reason.name,
        replace: true,
        allowGuestDismissPop: false,
      );
    },
    onContinueAsGuest: () async {
      await ref.read(authSessionControllerProvider.notifier).continueAsGuest();
      if (!context.mounted) {
        return;
      }
      _completeWelcome(ref);
    },
  );
}

void _completeWelcome(WidgetRef ref) {
  ref.read(welcomeCompletedProvider.notifier).setCompleted(true);
  AppStartupRuntime.instance.scheduleHomeReadyReport(
    (provider) => ref.read(provider),
  );
}

ReferralSource _referralSourceFromRoute(String value) {
  if (value.trim().isEmpty) {
    return ReferralSource.deepLink;
  }
  for (final source in ReferralSource.values) {
    if (source.value == value) {
      return source;
    }
  }
  return ReferralSource.deepLink;
}
