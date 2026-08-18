import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:fluentui_system_icons/fluentui_system_icons.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/incoming_call_coordinator.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/runtime/transport/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/design_system/icons/app_custom_icons.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/shell/bottom_navigation.dart';
import 'package:quwoquan_app/runtime/shell/main_app_shell.dart';
import 'package:quwoquan_app/runtime/shell/web_app_install_banner.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/platform/web_install_context.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/web_main_app_shell_dependencies.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_app/design_system/layout/app_terminal_viewport.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/presentation/chat_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_actions_discovery_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_featured_immersive_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_page.dart';
import 'package:quwoquan_app/runtime/shell/interest_match/interest_match_page.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/presentation/login_page.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/my_profile_page.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_flower_mark.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../support/service/notification_service/notification_delivery/notification/app_message_typed_double.dart';
import '../../../support/service/user_service/relationship/greeting_request/user_typed_facet_test_support.dart';
import '../../../support/service/user_service/account/user_account/user_account_profile_typed_double.dart';

/// 壳只需要「相交」读面存在且为空：这里给对象级最小 typed double，
/// 不承载任何业务数据集合。
final class _EmptyIntersectionRepository implements IntersectionRepository {
  const _EmptyIntersectionRepository();

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async =>
      const IntersectionInboxSummary(
        totalCount: 0,
        totalNewCount: 0,
        dimensions: <IntersectionDimensionTally>[],
        generatedAt: '2026-08-07T00:00:00Z',
        totalStrengthenedCount: 0,
        totalReactivatedCount: 0,
      );

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  }) async => const <IntersectionReason>[];

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  }) async => const <IntersectionReason>[];
}

List<Override> _shellTestOverrides({
  required bool authenticated,
  AuthSessionStore? store,
  bool flippable = false,
  VisitRecorderService? visitRecorderService,
}) {
  final contentStore = InMemoryContentPostStore(
    posts: [
      ...contentPostListBuilder(
        contentType: 'image',
        count: 2,
        idPrefix: 'shell-image',
      ),
      ...contentPostListBuilder(
        contentType: 'video',
        count: 2,
        idPrefix: 'shell-video',
      ),
      ...contentPostListBuilder(
        contentType: 'article',
        count: 2,
        idPrefix: 'shell-article',
      ),
    ],
  );
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    visitRecorderServiceProvider.overrideWithValue(
      visitRecorderService ?? VisitRecorderService(),
    ),
    ...mockContentFacetOverrides(store: contentStore),
    // 壳会把 /chat 与 /profile 页签一起挂进 IndexedStack：这两条对象级 typed port
    // 必须显式给出，否则 provider 图会一路走到被封死的 generated client。
    ...chatTestRepositoryOverrides(),
    appMessageQueryProvider.overrideWithValue(
      const EmptyAppMessageQueryDouble(),
    ),
    greetingRepositoryProvider.overrideWithValue(alphaGreetingRepository()),
    authorImpactQueryProvider(AppUiSurfaces.profileHome)
        .overrideWithValue(const MockUserProfileRepository()),
    profileQueryProvider(AppUiSurfaces.profileHome)
        .overrideWithValue(const MockUserProfileRepository()),
    intersectionRepositoryProvider.overrideWithValue(
      const _EmptyIntersectionRepository(),
    ),
    if (store != null) authSessionStoreProvider.overrideWithValue(store),
    authSessionControllerProvider.overrideWith(
      flippable
          ? _FlippableShellAuthSession.new
          : () => _StaticShellAuthSession(authenticated),
    ),
    activePersonaContextProvider.overrideWith(
      (ref) async => ActivePersonaContextViewData(
        personaId: 'user_001',
        ownerUserId: 'user_001',
        subjectType: 'person',
        displayName: '测试用户',
        avatarUrl: 'media/avatar/s/asset/test-user/v1/source.webp',
        isPrimary: true,
      ),
    ),
    incomingCallCoordinatorProvider.overrideWith(
      _NoopIncomingCallCoordinator.new,
    ),
    behaviorReporterProvider.overrideWithValue(_NoopBehaviorReporter()),
  ];
}

Widget _buildShell(String location, {bool authenticated = true}) {
  return ScreenUtilInit(
    designSize: const Size(393, 852),
    child: ProviderScope(
      overrides: [..._shellTestOverrides(authenticated: authenticated)],
      child: MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
        home: MainAppShell(
          currentLocation: location,
          child: const SizedBox.shrink(),
        ),
      ),
    ),
  );
}

final class _StaticShellAuthSession extends AuthSessionController {
  _StaticShellAuthSession(this.authenticated);

  final bool authenticated;

  @override
  AuthSessionState build() {
    if (!authenticated) {
      return const AuthSessionState(
        status: AuthSessionStatus.guest,
        installId: 'install-id',
      );
    }
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      ownerId: 'user_001',
      activePersonaId: 'user_001',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'install-id',
    );
  }
}

final class _FlippableShellAuthSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.guest,
    installId: 'install-id',
  );
}

final class _NoopIncomingCallCoordinator extends IncomingCallCoordinator {
  _NoopIncomingCallCoordinator(Ref ref)
    : super(
        ref: ref,
        readRouter: () => throw UnimplementedError(
          'incoming-call routing is outside the shell widget contract',
        ),
        firebaseRuntime: ref.read(firebaseIncomingCallRuntimeProvider),
        nativeBridge: ref.read(incomingCallNativeBridgeProvider),
      );

  @override
  void start(String userId) {}

  @override
  void stop({bool removePushEndpoints = true}) {}

  @override
  void dispose() {}
}

final class _NoopBehaviorReporter implements BehaviorReporter {
  @override
  Future<void> reportEvents({required List<BehaviorEvent> events}) async {}
}

Widget _buildDarkShell(String location, {bool authenticated = true}) {
  return ScreenUtilInit(
    designSize: const Size(393, 852),
    child: ProviderScope(
      overrides: [
        isDarkProvider.overrideWith((ref) => true),
        ..._shellTestOverrides(authenticated: authenticated),
      ],
      child: MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
        home: MainAppShell(
          currentLocation: location,
          child: const SizedBox.shrink(),
        ),
      ),
    ),
  );
}

Widget _buildShellRouter({required bool authenticated}) {
  final visitRecorderService = VisitRecorderService();
  return ScreenUtilInit(
    designSize: const Size(393, 852),
    child: ProviderScope(
      overrides: [
        ..._shellTestOverrides(
          authenticated: authenticated,
          visitRecorderService: visitRecorderService,
        ),
      ],
      child: MaterialApp.router(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
        routerConfig: GoRouter(
          initialLocation: AppRoutePaths.home,
          routes: [
            GoRoute(
              path: AppRoutePaths.home,
              builder: (context, state) => MainAppShell(
                currentLocation: state.uri.path,
                child: const SizedBox.shrink(),
              ),
            ),
            GoRoute(
              path: AppRoutePaths.loginPathTemplate,
              builder: (context, state) => LoginPage(
                reason: state.uri.queryParameters['reason'],
                redirect: state.uri.queryParameters['redirect'],
                dismissFallback:
                    state.uri.queryParameters[loginDismissFallbackQueryParam],
                dismissPolicy: loginDismissPolicyFromQuery(
                  state.uri.queryParameters[loginGuestDismissPopQueryParam],
                ),
              ),
            ),
            GoRoute(
              path: AppRoutePaths.createPathTemplate,
              builder: (context, state) {
                if (!authenticated) {
                  return LoginPage(
                    reason: AuthGateReason.createPost.name,
                    redirect: state.uri.toString(),
                    dismissFallback: AppRoutePaths.home,
                    dismissPolicy: LoginDismissPolicy.safeFallback,
                  );
                }
                return const Scaffold(body: Center(child: Text('CREATE_PAGE')));
              },
            ),
            GoRoute(
              path: AppRoutePaths.interestMatch,
              builder: (context, state) =>
                  InterestMatchPage(visitRecorderService: visitRecorderService),
            ),
          ],
        ),
      ),
    ),
  );
}

Widget _buildShellRouterWithStore(AuthSessionStore store) {
  return ScreenUtilInit(
    designSize: const Size(393, 852),
    child: ProviderScope(
      overrides: [
        ..._shellTestOverrides(
          authenticated: false,
          store: store,
          flippable: true,
        ),
      ],
      child: MaterialApp.router(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
        routerConfig: GoRouter(
          initialLocation: AppRoutePaths.home,
          routes: [
            GoRoute(
              path: AppRoutePaths.home,
              builder: (context, state) => MainAppShell(
                currentLocation: state.uri.path,
                child: const SizedBox.shrink(),
              ),
            ),
            GoRoute(
              path: AppRoutePaths.loginPathTemplate,
              builder: (context, state) => LoginPage(
                reason: state.uri.queryParameters['reason'],
                redirect: state.uri.queryParameters['redirect'],
                dismissFallback:
                    state.uri.queryParameters[loginDismissFallbackQueryParam],
                dismissPolicy: loginDismissPolicyFromQuery(
                  state.uri.queryParameters[loginGuestDismissPopQueryParam],
                ),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

/// 复刻生产路由守卫的「受限直达路由 → 登录」逻辑，用于回归「深链进入受限路由
/// 后关闭登录页又被守卫立刻弹出」的死循环。守卫触发的登录必须使用 safeFallback。
Widget _buildGuardedRouter({
  required bool authenticated,
  required String initialLocation,
}) {
  return ScreenUtilInit(
    designSize: const Size(393, 852),
    child: ProviderScope(
      overrides: [..._shellTestOverrides(authenticated: authenticated)],
      child: _GuardedRouterHost(initialLocation: initialLocation),
    ),
  );
}

class _GuardedRouterHost extends ConsumerStatefulWidget {
  const _GuardedRouterHost({required this.initialLocation});

  final String initialLocation;

  @override
  ConsumerState<_GuardedRouterHost> createState() => _GuardedRouterHostState();
}

class _GuardedRouterHostState extends ConsumerState<_GuardedRouterHost> {
  late final ValueNotifier<int> _refresh;
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _refresh = ValueNotifier<int>(0);
    _router = GoRouter(
      initialLocation: widget.initialLocation,
      refreshListenable: _refresh,
      redirect: (context, state) {
        final auth = ref.read(authSessionControllerProvider);
        final loc = state.matchedLocation;
        if (loc == AppRoutePaths.loginPathTemplate) {
          return null;
        }
        if (auth.status != AuthSessionStatus.restoring) {
          final gate = requiredRouteGateForLocation(loc);
          if (gate != null && !auth.isAuthenticated) {
            return buildLoginRouteLocation(
              reasonName: gate.name,
              redirect: state.uri.toString(),
              dismissFallback: AppRoutePaths.home,
              dismissPolicy: LoginDismissPolicy.safeFallback,
            );
          }
        }
        return null;
      },
      routes: [
        GoRoute(
          path: AppRoutePaths.home,
          builder: (context, state) => MainAppShell(
            currentLocation: state.uri.path,
            child: const SizedBox.shrink(),
          ),
        ),
        GoRoute(
          path: AppRoutePaths.chat,
          builder: (context, state) =>
              const Scaffold(body: Center(child: Text('CHAT_PAGE'))),
        ),
        GoRoute(
          path: AppRoutePaths.createEntry,
          builder: (context, state) =>
              const Scaffold(body: Center(child: Text('CREATE_ENTRY_PAGE'))),
        ),
        GoRoute(
          path: AppRoutePaths.createPathTemplate,
          builder: (context, state) =>
              const Scaffold(body: Center(child: Text('CREATE_PAGE'))),
        ),
        GoRoute(
          path: AppRoutePaths.gatheringCreate,
          builder: (context, state) => const Scaffold(
            body: Center(child: Text('GATHERING_CREATE_PAGE')),
          ),
        ),
        GoRoute(
          path: AppRoutePaths.loginPathTemplate,
          builder: (context, state) => LoginPage(
            reason: state.uri.queryParameters['reason'],
            redirect: state.uri.queryParameters['redirect'],
            dismissFallback:
                state.uri.queryParameters[loginDismissFallbackQueryParam],
            dismissPolicy: loginDismissPolicyFromQuery(
              state.uri.queryParameters[loginGuestDismissPopQueryParam],
            ),
          ),
        ),
      ],
    );
  }

  @override
  void dispose() {
    _router.dispose();
    _refresh.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AuthSessionState>(authSessionControllerProvider, (_, _) {
      _refresh.value++;
    });
    return MaterialApp.router(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
      routerConfig: _router,
    );
  }
}

class _MutableAuthSessionStore implements AuthSessionStore {
  bool authenticated = false;

  @override
  Future<StoredAuthSession> read() async {
    return StoredAuthSession(
      accessToken: authenticated ? 'access-token' : '',
      refreshToken: authenticated ? 'refresh-token' : '',
      ownerId: authenticated ? 'user_001' : '',
      activePersonaId: authenticated ? 'user_001' : '',
      accountState: authenticated ? 'active' : '',
      identityOrigin: authenticated ? 'phone' : '',
      installId: 'install-id',
      lastRefreshAtEpochMs: 0,
      lastForegroundAuthCheckAtEpochMs: 0,
      manualLoggedOut: false,
      launchPromptDismissed: !authenticated,
    );
  }

  @override
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {
    authenticated = true;
  }

  @override
  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {
    authenticated = true;
  }

  @override
  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {}

  @override
  Future<void> updateActivePersona(String personaId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {
    authenticated = false;
  }

  @override
  Future<void> softLogout() async {
    authenticated = false;
  }

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

String _activeHomeChannel(WidgetTester tester) {
  return tester
      .widget<HomePrimaryTabStrip>(find.byType(HomePrimaryTabStrip))
      .activeChannelId;
}

void _suppressExpectedErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (details) {
    final message = details.exceptionAsString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException') ||
        message.contains('overflowed')) {
      return;
    }
    original?.call(details);
  };
}

Future<void> _pumpRouteTransition(WidgetTester tester) async {
  // Route completion and Riverpod invalidation can be queued on adjacent
  // frames. Advance them in bounded increments instead of pumpAndSettle:
  // the shell intentionally owns continuous animations, so settling the
  // whole tree would never be a valid completion signal.
  for (var frame = 0; frame < 12; frame++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('MainAppShell', () {
    testWidgets('移动端壳不初始化未使用的 Web 依赖图', (tester) async {
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(393, 852),
          child: ProviderScope(
            overrides: [
              ..._shellTestOverrides(authenticated: true),
              webMainAppShellDependenciesProvider.overrideWith(
                (ref) => throw StateError('Web dependencies must stay lazy'),
              ),
            ],
            child: const MaterialApp(
              home: MainAppShell(
                currentLocation: AppRoutePaths.home,
                child: SizedBox.shrink(),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(MainAppShell), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('壳卸载后认证状态更新不读取已卸载的 ref', (tester) async {
      final store = _MutableAuthSessionStore();
      final container = ProviderContainer(
        overrides: _shellTestOverrides(
          authenticated: false,
          store: store,
          flippable: true,
        ),
      );

      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(393, 852),
          child: UncontrolledProviderScope(
            container: container,
            child: MaterialApp(
              localizationsDelegates: const [
                AppLocalizations.delegate,
                GlobalMaterialLocalizations.delegate,
                GlobalWidgetsLocalizations.delegate,
                GlobalCupertinoLocalizations.delegate,
              ],
              supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
              home: const MainAppShell(
                currentLocation: AppRoutePaths.home,
                child: SizedBox.shrink(),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.pumpWidget(const SizedBox.shrink());
      await container
          .read(authSessionControllerProvider.notifier)
          .applyLoginGrant(
            const AuthSessionGrant(
              accessToken: 'access-token',
              refreshToken: 'refresh-token',
              ownerId: 'user_001',
              accountState: 'active',
              identityOrigin: 'phone',
              activePersona: ActivePersonaEnvelope(personaId: 'user_001'),
              logicalShard: 0,
              anonymousRetentionPolicy: '',
              personaCount: 1,
              sessionRememberTtlSeconds: 0,
            ),
          );
      await tester.pump();

      expect(tester.takeException(), isNull);
      container.dispose();
    });

    testWidgets(
      // spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-001.t6
      'outbox 终态失败经壳层弹统一警示轻提示并一次性消费信号',
      (tester) async {
        await tester.pumpWidget(_buildShell(AppRoutePaths.home));
        await tester.pump(const Duration(milliseconds: 300));
        final container = ProviderScope.containerOf(
          tester.element(find.byType(MainAppShell)),
        );

        container
            .read(clientStateSyncTerminalFailureProvider.notifier)
            .publish(
              ClientStateSyncOutboxEntry(
                coalesceKey: 'post:like:post-terminal',
                objectType: 'post',
                objectId: 'post-terminal',
                intentType: 'like',
                desiredBoolValue: true,
                confirmedBoolValue: false,
                nextFlushAt: DateTime.now().toUtc(),
                firstQueuedAt: DateTime.now().toUtc().subtract(
                  const Duration(hours: 73),
                ),
              ),
            );
        await tester.pump();
        await tester.pump();

        // 统一恢复语义文案（恢复组，无新增字面量）+ 警示 tone 圆点。
        expect(
          find.text(SearchText.recoveryServiceUnavailableMessage),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey<String>('app-toast-tone-dot')),
          findsOneWidget,
        );
        // 一次性消费：信号被壳层清空，不会重复提示。
        expect(container.read(clientStateSyncTerminalFailureProvider), isNull);

        // 主动收起 toast 清理自动消失计时器（避免长推帧引入 shell 周期任务）。
        AppToast.dismiss();
        await tester.pump();
        expect(
          find.text(SearchText.recoveryServiceUnavailableMessage),
          findsNothing,
        );
      },
    );

    testWidgets('底部导航展示五栏，行动（线下行动与发现）成为独立一级入口', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('首页'), findsWidgets);
      expect(find.text(AppConceptConstants.offlineActions), findsWidgets);
      expect(find.text('我'), findsWidgets);
      expect(find.text(FoundationText.bottomNavGuestProfile), findsNothing);
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(ChatText.chatPrimaryContacts),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(AppConceptConstants.chat),
        ),
        findsNothing,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(AppConceptConstants.offlineActions),
        ),
        findsOneWidget,
      );
      // 视频书属于首页文本频道，不占底栏，也不保留独立图标入口。
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text('视频书'),
        ),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('home-featured-entry')),
        findsNothing,
      );
      expect(
        find.byKey(HomePrimaryTabStrip.channelKey('featured')),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(AppConceptConstants.interestMatch),
        ),
        findsNothing,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text('精品'),
        ),
        findsNothing,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.byIcon(CupertinoIcons.plus),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text('创作'),
        ),
        findsNothing,
      );
      final navContext = tester.element(find.byType(BottomNavigationWidget));
      final obstructionScope = tester.widget<AppViewportObstructionScope>(
        find.byType(AppViewportObstructionScope),
      );
      expect(
        obstructionScope.obstruction.bottom,
        AppSpacing.bottomNavBarHeight(navContext) +
            MediaQuery.viewPaddingOf(navContext).bottom,
      );
    });

    testWidgets('从首页视频书文本 Tab 进入沉浸正文，不切换壳层目的地', (tester) async {
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pump(const Duration(milliseconds: 300));

      await tester.tap(find.byKey(HomePrimaryTabStrip.channelKey('featured')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(tester.takeException(), isNull);
      expect(find.byType(HomeFeaturedImmersivePage), findsOneWidget);
      expect(find.byType(BottomNavigationWidget), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('home-featured-entry')),
        findsNothing,
      );
    });

    testWidgets('底栏「行动」进入线下行动与发现页，游客可浏览且保留底栏', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(
        _buildShell(AppRoutePaths.home, authenticated: false),
      );
      await tester.pump(const Duration(milliseconds: 300));

      await tester.tap(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(AppConceptConstants.offlineActions),
        ),
      );
      await tester.pump();
      await tester.pump();

      expect(tester.takeException(), isNull);
      expect(find.byType(GatheringActionsDiscoveryPage), findsOneWidget);
      // 游客可浏览：不弹登录门，底栏保持可见（登录入口无死循环宪法）。
      expect(find.byType(BottomNavigationWidget), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('actions-guest-login')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('actions-discover-interest')),
        findsOneWidget,
      );
    });

    testWidgets('圈子路由归并到首页频道', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.circles));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(HomePage), findsOneWidget);
    });

    testWidgets('首页初次进入只构建首页页签，非首页页签延后到首次访问', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(HomePage), findsOneWidget);
      expect(find.byType(HomeFeaturedImmersivePage), findsNothing);
      expect(find.byType(ChatPage), findsNothing);
      expect(find.byType(MyProfilePage), findsNothing);
    });

    testWidgets('深色模式下底部导航仍展示五栏', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildDarkShell(AppRoutePaths.home));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(BottomNavigationWidget), findsOneWidget);
      expect(find.text('首页'), findsWidgets);
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(AppConceptConstants.offlineActions),
        ),
        findsOneWidget,
      );
    });

    testWidgets('未登录时底部我的栏显示未登录', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(
        _buildShell(AppRoutePaths.home, authenticated: false),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(FoundationText.bottomNavGuestProfile),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(AppConceptConstants.profile),
        ),
        findsNothing,
      );
    });

    testWidgets('底部中间加号打开统一动作面板', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pumpAndSettle();

      await tester.tap(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.byIcon(CupertinoIcons.plus),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(TestKeys.createActionPublishContent), findsOneWidget);
      expect(find.byKey(TestKeys.createActionStartGathering), findsOneWidget);
      expect(find.byKey(TestKeys.createActionStartGroupChat), findsOneWidget);
      expect(find.byKey(TestKeys.createActionGallery), findsNothing);
      expect(find.byKey(TestKeys.createActionCapture), findsNothing);
      expect(find.byKey(TestKeys.createActionWrite), findsNothing);
      expect(find.text(CreationText.createActionAddContactShort), findsNothing);
      expect(
        find.text(CreationText.createActionCreateCircleShort),
        findsNothing,
      );
      expect(
        find.text(CreationText.createActionInterestMatchShort),
        findsNothing,
      );
    });

    testWidgets('加号面板发内容后展示照片视频文字二级入口', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShellRouter(authenticated: true));
      await tester.pumpAndSettle();

      await tester.tap(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.byIcon(CupertinoIcons.plus),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(TestKeys.createActionPublishContent));
      await tester.pumpAndSettle();

      expect(find.byKey(TestKeys.createActionPublishContent), findsNothing);
      expect(find.byKey(TestKeys.createActionStartGathering), findsNothing);
      expect(find.byKey(TestKeys.createActionStartGroupChat), findsNothing);
      expect(find.byKey(TestKeys.createActionGallery), findsOneWidget);
      expect(find.byKey(TestKeys.createActionCapture), findsOneWidget);
      expect(find.byKey(TestKeys.createActionWrite), findsOneWidget);
    });

    testWidgets('游客点加号先开动作面板（不弹登录），后置到具体动作再拦截', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShellRouter(authenticated: false));
      await tester.pumpAndSettle();

      await tester.tap(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.byIcon(CupertinoIcons.plus),
        ),
      );
      await tester.pumpAndSettle();

      // 加号后置登录：先出现动作面板，不弹登录页。
      expect(find.byType(LoginPage), findsNothing);
      expect(find.byKey(TestKeys.createActionPublishContent), findsOneWidget);
      expect(find.byKey(TestKeys.createActionStartGathering), findsOneWidget);
      expect(find.byKey(TestKeys.createActionStartGroupChat), findsOneWidget);

      // 展开内容类型也不登录，直到选择具体创作动作才拦截。
      await tester.tap(find.byKey(TestKeys.createActionPublishContent));
      await tester.pumpAndSettle();
      expect(find.byType(LoginPage), findsNothing);
      expect(find.byKey(TestKeys.createActionWrite), findsOneWidget);

      // 选具体创作动作时才触发登录。
      await tester.tap(find.byKey(TestKeys.createActionWrite));
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsNothing);
      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(HomePage), findsOneWidget);
      expect(find.byType(BottomNavigationWidget), findsOneWidget);
      expect(find.text('Page Not Found'), findsNothing);

      // 再 pump 确认关闭登录后停留安全首页，不回到入口重复弹登录。
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(LoginPage), findsNothing);
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('游客点击首页关注 tab 关闭登录页后回首页且不回环', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShellRouter(authenticated: false));
      await _pumpRouteTransition(tester);
      expect(
        _activeHomeChannel(tester),
        HomePrimaryTabStrip.recommendedChannelId,
      );

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.channelKey(
            HomePrimaryTabStrip.followingChannelId,
          ),
        ),
      );
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsNothing);
      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(HomePage), findsOneWidget);
      expect(
        _activeHomeChannel(tester),
        HomePrimaryTabStrip.recommendedChannelId,
      );
      expect(find.byType(BottomNavigationWidget), findsOneWidget);
      expect(find.text('Page Not Found'), findsNothing);

      // 再 pump 一帧确认没有重新弹回登录页，避免「关闭→回关注态→再次登录」回环。
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(LoginPage), findsNothing);
      expect(
        _activeHomeChannel(tester),
        HomePrimaryTabStrip.recommendedChannelId,
      );
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('游客点击首页关注 tab 登录成功后进入关注频道目标态', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      final store = _MutableAuthSessionStore();
      await tester.pumpWidget(_buildShellRouterWithStore(store));
      await _pumpRouteTransition(tester);
      expect(
        _activeHomeChannel(tester),
        HomePrimaryTabStrip.recommendedChannelId,
      );

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.channelKey(
            HomePrimaryTabStrip.followingChannelId,
          ),
        ),
      );
      await _pumpRouteTransition(tester);
      expect(find.byType(LoginPage), findsOneWidget);

      final loginContext = tester.element(find.byType(LoginPage));
      final container = ProviderScope.containerOf(loginContext);
      final router = GoRouter.of(loginContext);
      await container
          .read(authSessionControllerProvider.notifier)
          .applyLoginGrant(
            const AuthSessionGrant(
              accessToken: 'access-token',
              refreshToken: 'refresh-token',
              ownerId: 'user_001',
              accountState: 'active',
              identityOrigin: 'phone',
              activePersona: ActivePersonaEnvelope(personaId: 'user_001'),
              logicalShard: 0,
              anonymousRetentionPolicy: '',
              personaCount: 1,
              sessionRememberTtlSeconds: 0,
            ),
          );
      // Let the auth-state invalidation finish before replacing the login
      // route. Production does this across the awaited login command; keeping
      // the same frame boundary avoids rebuilding a defunct feed element.
      await tester.pump();
      router.go(AppRoutePaths.home);
      await _pumpRouteTransition(tester);

      expect(
        _activeHomeChannel(tester),
        HomePrimaryTabStrip.followingChannelId,
      );
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('游客点「我」弹登录，关闭回首页且不回环（强登录入口）', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShellRouter(authenticated: false));
      await _pumpRouteTransition(tester);

      await tester.tap(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.byType(AppProfilePersonIcon),
        ),
      );
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsNothing);
      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(HomePage), findsOneWidget);
      expect(find.text('Page Not Found'), findsNothing);

      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('游客点底栏「联系」仍走现有聊天登录门，关闭回首页且不回环', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShellRouter(authenticated: false));
      await _pumpRouteTransition(tester);

      await tester.tap(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(ChatText.chatPrimaryContacts),
        ),
      );
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsOneWidget);
      expect(find.text('CHAT_PAGE'), findsNothing);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsNothing);
      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(HomePage), findsOneWidget);
      expect(find.text('Page Not Found'), findsNothing);

      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(LoginPage), findsNothing);
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('游客深链直达 /chat 被守卫拦截，关闭登录页后回首页且不死循环', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(
        _buildGuardedRouter(
          authenticated: false,
          initialLocation: AppRoutePaths.chat,
        ),
      );
      await _pumpRouteTransition(tester);

      // 守卫应把 /chat 直达重定向到登录页，而非展示受限的会话页。
      expect(find.byType(LoginPage), findsOneWidget);
      expect(find.text('CHAT_PAGE'), findsNothing);

      // 关闭登录页：必须 go 到安全兜底（首页），禁止 pop 回 /chat 再次命中守卫。
      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsNothing);
      expect(find.text('CHAT_PAGE'), findsNothing);
      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.text('Page Not Found'), findsNothing);

      // 再 pump 一帧确认守卫没有把登录页二次弹出（无死循环）。
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(LoginPage), findsNothing);
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('游客直达发起活动，关闭登录回安全首页且不回环', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(
        _buildGuardedRouter(
          authenticated: false,
          initialLocation: AppRoutePaths.gatheringCreate,
        ),
      );
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsOneWidget);
      expect(find.text('GATHERING_CREATE_PAGE'), findsNothing);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsNothing);
      expect(find.text('GATHERING_CREATE_PAGE'), findsNothing);
      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.text('Page Not Found'), findsNothing);

      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(LoginPage), findsNothing);
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('游客直达 createEntry 显示动作面板入口，不被创作路由门提前拦截', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(
        _buildGuardedRouter(
          authenticated: false,
          initialLocation: AppRoutePaths.createEntry,
        ),
      );
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsNothing);
      expect(find.text('CREATE_ENTRY_PAGE'), findsOneWidget);
    });

    testWidgets('游客直达 /create 具体创作页仍被路由门拦截，关闭回首页', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(
        _buildGuardedRouter(
          authenticated: false,
          initialLocation: AppRoutePaths.create(type: 'write'),
        ),
      );
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsOneWidget);
      expect(find.text('CREATE_PAGE'), findsNothing);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await _pumpRouteTransition(tester);

      expect(find.byType(LoginPage), findsNothing);
      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.text('Page Not Found'), findsNothing);
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('底部导航上下留白对称且使用统一语义 token', (tester) async {
      _suppressExpectedErrors();
      tester.view.physicalSize = const Size(1179, 2556);
      tester.view.devicePixelRatio = 3.0;
      tester.view.viewPadding = const FakeViewPadding(bottom: 34);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.view.resetViewPadding);

      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pumpAndSettle();

      final navFinder = find.byType(BottomNavigationWidget);
      final navElement = tester.element(navFinder);
      final navSize = tester.getSize(navFinder);
      final bottomInset =
          tester.view.viewPadding.bottom / tester.view.devicePixelRatio;
      final navHeight = AppSpacing.bottomNavBarHeight(navElement);
      final expectedIconSize = AppSpacing.bottomNavBarItemIconSize(navElement);
      final inactiveColor = AppColors.iosSecondaryLabel(navElement);
      final expectedHeight = navHeight + bottomInset;
      final homeIcon = find.descendant(
        of: navFinder,
        matching: find.byIcon(FluentIcons.home_24_filled),
      );
      final actionsIcon = find.descendant(
        of: navFinder,
        matching: find.byIcon(FluentIcons.people_community_24_regular),
      );
      final contactsIcon = find.descendant(
        of: navFinder,
        matching: find.byIcon(FluentIcons.chat_multiple_24_regular),
      );
      final profileIcon = find.descendant(
        of: navFinder,
        matching: find.byType(AppProfilePersonIcon),
      );
      final navTop = tester.getTopLeft(navFinder).dy;
      final iconTop = tester.getTopLeft(homeIcon).dy;
      final iconCenterY = tester.getCenter(homeIcon).dy;

      expect(navSize.height, closeTo(expectedHeight, 0.5));
      expect(tester.widget<Icon>(actionsIcon).size, expectedIconSize);
      expect(tester.widget<Icon>(actionsIcon).color, inactiveColor);
      expect(tester.widget<Icon>(contactsIcon).size, expectedIconSize);
      expect(tester.widget<Icon>(contactsIcon).color, inactiveColor);
      expect(
        tester.widget<AppProfilePersonIcon>(profileIcon).size,
        expectedIconSize,
      );
      expect(tester.widget<AppProfilePersonIcon>(profileIcon).filled, isFalse);
      expect(
        tester.widget<AppProfilePersonIcon>(profileIcon).color,
        inactiveColor,
      );
      final iconToTop = iconTop - navTop;
      expect(iconToTop, greaterThanOrEqualTo(0));
      expect(iconToTop, lessThan(navHeight / 2));
      expect(
        (tester.getCenter(actionsIcon).dy - iconCenterY).abs(),
        lessThan(1),
      );
      expect(
        (tester.getCenter(contactsIcon).dy - iconCenterY).abs(),
        lessThan(1),
      );
      expect(
        (tester.getCenter(profileIcon).dy - iconCenterY).abs(),
        lessThan(1),
      );
    });

    testWidgets('底部导航图标尺寸按手机、平板、Web 高保规格响应式适配', (tester) async {
      _suppressExpectedErrors();

      Future<double> iconSizeForLogicalWidth(double width) async {
        tester.view.physicalSize = Size(width * 3, 2556);
        tester.view.devicePixelRatio = 3.0;
        late double resolvedSize;
        await tester.pumpWidget(
          MediaQuery(
            data: MediaQueryData(size: Size(width, 852)),
            child: Directionality(
              textDirection: TextDirection.ltr,
              child: Builder(
                builder: (context) {
                  resolvedSize = AppSpacing.bottomNavBarItemIconSize(context);
                  return const SizedBox.shrink();
                },
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        return resolvedSize;
      }

      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      expect(await iconSizeForLogicalWidth(390), 28.0);
      expect(await iconSizeForLogicalWidth(820), 32.0);
      expect(await iconSizeForLogicalWidth(1200), 40.0);
    });

    testWidgets('底部导航自绘图标选中态使用主蓝并保持语义形态', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.chat));
      await tester.pumpAndSettle();

      final navFinder = find.byType(BottomNavigationWidget);
      final navElement = tester.element(navFinder);
      final expectedIconSize = AppSpacing.bottomNavBarItemIconSize(navElement);
      final inactiveColor = AppColors.iosSecondaryLabel(navElement);
      final actionsIcon = find.descendant(
        of: navFinder,
        matching: find.byIcon(FluentIcons.people_community_24_regular),
      );
      final contactsIcon = find.descendant(
        of: navFinder,
        matching: find.byIcon(FluentIcons.chat_multiple_24_regular),
      );
      final profileIcon = find.descendant(
        of: navFinder,
        matching: find.byType(AppProfilePersonIcon),
      );

      final actions = tester.widget<Icon>(actionsIcon);
      final contacts = tester.widget<Icon>(contactsIcon);
      final profile = tester.widget<AppProfilePersonIcon>(profileIcon);

      expect(actions.size, expectedIconSize);
      expect(contacts.size, expectedIconSize);
      expect(profile.size, expectedIconSize);
      expect(profile.filled, isFalse);
      expect(actions.color, inactiveColor);
      expect(contacts.color, AppColors.primaryColor);
      expect(profile.color, inactiveColor);
      expect(
        (tester.getCenter(actionsIcon).dy - tester.getCenter(contactsIcon).dy)
            .abs(),
        lessThan(1),
      );
      expect(
        (tester.getCenter(profileIcon).dy - tester.getCenter(contactsIcon).dy)
            .abs(),
        lessThan(1),
      );

      await tester.pumpWidget(_buildShell(AppRoutePaths.profile));
      await tester.pumpAndSettle();

      final profileNavFinder = find.byType(BottomNavigationWidget);
      final selectedProfile = tester.widget<AppProfilePersonIcon>(
        find.descendant(
          of: profileNavFinder,
          matching: find.byType(AppProfilePersonIcon),
        ),
      );

      expect(selectedProfile.filled, isTrue);
      expect(selectedProfile.color, AppColors.primaryColor);
    });

    testWidgets('底部导航背景与 post 表面色一致', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pumpAndSettle();

      final navDecoration = tester.widget<DecoratedBox>(
        find
            .descendant(
              of: find.byType(BottomNavigationWidget),
              matching: find.byType(DecoratedBox),
            )
            .first,
      );
      final decoration = navDecoration.decoration as BoxDecoration;
      expect(
        decoration.color,
        SettingsSemanticConstants.conversationSheetCardSurface(false),
      );
      expect(decoration.border, isNull);
    });

    testWidgets('Web 能力下顶部展示安装提示，移动宽度提供下载与分享', (tester) async {
      _suppressExpectedErrors();
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final router = GoRouter(
        initialLocation: AppRoutePaths.home,
        routes: [
          GoRoute(
            path: AppRoutePaths.home,
            builder: (context, state) => MainAppShell(
              currentLocation: state.uri.path,
              child: const SizedBox.shrink(),
            ),
          ),
        ],
      );
      addTearDown(router.dispose);

      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(393, 852),
          child: ProviderScope(
            overrides: [
              platformCapabilitiesProvider.overrideWithValue(
                CapabilityProfile.web,
              ),
              webInstallContextProvider.overrideWithValue(
                const WebInstallContext(
                  recommendation: WebInstallRecommendation.android,
                  isStandalone: false,
                  dismissedForSession: false,
                ),
              ),
              ..._shellTestOverrides(authenticated: true),
            ],
            child: MaterialApp.router(
              localizationsDelegates: const [
                AppLocalizations.delegate,
                GlobalMaterialLocalizations.delegate,
                GlobalWidgetsLocalizations.delegate,
                GlobalCupertinoLocalizations.delegate,
              ],
              supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
              routerConfig: router,
            ),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.text(FoundationText.webInstallBannerAndroidTitle),
        findsOneWidget,
      );
      expect(
        find.text(FoundationText.webInstallBannerDownload),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-install-dismiss')),
        findsOneWidget,
      );
    });

    testWidgets('Web 宽屏展示欢迎页，进入后使用五入口与上下文 tabs', (tester) async {
      _suppressExpectedErrors();
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final router = GoRouter(
        initialLocation: AppRoutePaths.home,
        routes: [
          GoRoute(
            path: AppRoutePaths.home,
            builder: (context, state) => MainAppShell(
              currentLocation: state.uri.path,
              child: const SizedBox.shrink(),
            ),
          ),
        ],
      );
      addTearDown(router.dispose);

      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(393, 852),
          child: ProviderScope(
            overrides: [
              platformCapabilitiesProvider.overrideWithValue(
                CapabilityProfile.web,
              ),
              webInstallContextProvider.overrideWithValue(
                const WebInstallContext(
                  recommendation: WebInstallRecommendation.desktop,
                  isStandalone: false,
                  dismissedForSession: false,
                ),
              ),
              ..._shellTestOverrides(authenticated: true),
            ],
            child: MaterialApp.router(
              localizationsDelegates: const [
                AppLocalizations.delegate,
                GlobalMaterialLocalizations.delegate,
                GlobalWidgetsLocalizations.delegate,
                GlobalCupertinoLocalizations.delegate,
              ],
              supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
              routerConfig: router,
            ),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text(DiscoveryText.webPcWelcomeHeadline), findsNothing);
      expect(find.text(DiscoveryText.webPcWelcomeSubtitle), findsNothing);
      expect(find.text(DiscoveryText.webPcWelcomeScrollHint), findsNothing);
      expect(find.text(DiscoveryText.webPcBrandName), findsOneWidget);
      expect(find.text(DiscoveryText.webPcWelcomeContinue), findsNothing);
      expect(find.text(DiscoveryText.webPcWelcomeDownload), findsNothing);
      expect(find.text(DiscoveryText.webPcWelcomeLogin), findsNothing);
      expect(find.byType(WelcomeFlowerMark), findsOneWidget);
      expect(find.byType(WebAppInstallBanner), findsOneWidget);
      expect(
        find.text(FoundationText.webInstallBannerAndroidPackage),
        findsOneWidget,
      );
      expect(
        find.text(FoundationText.webInstallBannerIosPackage),
        findsOneWidget,
      );

      final recommendedTab = find.text(DiscoveryText.homeTabRecommended).first;
      final tabLeftBeforePinned = tester.getTopLeft(recommendedTab).dx;

      await tester.drag(
        find.byKey(const ValueKey<String>('web-shell-scroll')),
        const Offset(0, -260),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.byKey(const ValueKey<String>('web-primary-home')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-primary-featured')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('web-primary-create')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-primary-chat')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('web-primary-profile')),
        findsOneWidget,
      );
      expect(
        tester.getSize(find.byKey(const ValueKey<String>('web-primary-home'))),
        tester.getSize(
          find.byKey(const ValueKey<String>('web-primary-create')),
        ),
      );
      // 首页内容流复用 HomeMultiFormFeed 后，「关注」既是频道页签也是卡片关注按钮文案，
      // 与「推荐」一致允许多处出现（频道页签仍在其中）。
      expect(find.text(DiscoveryText.homeTabFollowing), findsWidgets);
      expect(find.text(DiscoveryText.homeTabRecommended), findsWidgets);
      expect(find.text(DiscoveryText.webPcSearchHintHome), findsOneWidget);
      expect(find.text(DiscoveryText.globalXiaoquSearchAsk), findsNothing);
      // 首页内容流复用移动端 HomeMultiFormFeed（多列 + 同源埋点），而非 Web 自绘卡片。
      expect(
        find.byKey(const ValueKey<String>('web-content-feed-recommend')),
        findsOneWidget,
      );

      final scrollView = tester.widget<CustomScrollView>(
        find.byKey(const ValueKey<String>('web-shell-scroll')),
      );
      scrollView.controller!.jumpTo(0);
      await tester.pump(const Duration(milliseconds: 120));
      expect(find.text(DiscoveryText.webPcBrandName), findsWidgets);
      scrollView.controller!.jumpTo(AppSpacing.webPcWelcomeHeroHeight);
      await tester.pump(const Duration(milliseconds: 120));
      expect(
        find.byKey(const ValueKey<String>('web-toolbar-brand')),
        findsOneWidget,
      );
      expect(tester.getTopLeft(recommendedTab).dx, tabLeftBeforePinned);

      expect(find.text(DiscoveryText.homeTabFeatured), findsOneWidget);
      expect(find.text(DiscoveryText.webPcSearchHintFeatured), findsNothing);

      await tester.tap(
        find.byKey(const ValueKey<String>('web-primary-create')),
      );
      await tester.pump(const Duration(milliseconds: 300));

      // 添加入口是动作工作台：顶部不再挂上下文 tab，首层固定三个动作卡片。
      expect(
        find.byKey(TestKeys.webCreateActionPublishContent),
        findsOneWidget,
      );
      expect(
        find.byKey(TestKeys.webCreateActionStartGathering),
        findsOneWidget,
      );
      expect(
        find.byKey(TestKeys.webCreateActionStartGroupChat),
        findsOneWidget,
      );
      expect(find.text(DiscoveryText.webPcCreateTabGallery), findsNothing);
      expect(find.text(DiscoveryText.webPcSearchHintCreate), findsOneWidget);
    });

    testWidgets('Web 宽屏未登录点创作主入口先进入创建工作台，不直接登录', (tester) async {
      _suppressExpectedErrors();
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final router = GoRouter(
        initialLocation: AppRoutePaths.home,
        routes: [
          GoRoute(
            path: AppRoutePaths.home,
            builder: (context, state) => MainAppShell(
              currentLocation: state.uri.path,
              child: const SizedBox.shrink(),
            ),
          ),
          GoRoute(
            path: AppRoutePaths.loginPathTemplate,
            builder: (context, state) => LoginPage(),
          ),
        ],
      );
      addTearDown(router.dispose);

      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(393, 852),
          child: ProviderScope(
            overrides: [
              platformCapabilitiesProvider.overrideWithValue(
                CapabilityProfile.web,
              ),
              ..._shellTestOverrides(authenticated: false),
            ],
            child: MaterialApp.router(
              localizationsDelegates: const [
                AppLocalizations.delegate,
                GlobalMaterialLocalizations.delegate,
                GlobalWidgetsLocalizations.delegate,
                GlobalCupertinoLocalizations.delegate,
              ],
              supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
              routerConfig: router,
            ),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));

      await tester.drag(
        find.byKey(const ValueKey<String>('web-shell-scroll')),
        const Offset(0, -260),
      );
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(
        find.byKey(const ValueKey<String>('web-primary-create')),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(WebInlineLoginSurface), findsNothing);
      expect(find.byType(LoginPage), findsNothing);
      // 游客先看到创建工作台的动作面板，登录拦截下沉到具体账号态动作。
      expect(
        find.byKey(TestKeys.webCreateActionPublishContent),
        findsOneWidget,
      );
      expect(
        find.byKey(TestKeys.webCreateActionStartGathering),
        findsOneWidget,
      );
      expect(
        find.byKey(TestKeys.webCreateActionStartGroupChat),
        findsOneWidget,
      );
      await tester.pump(const Duration(milliseconds: 1200));
    });
  });
}
