import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:fluentui_system_icons/fluentui_system_icons.dart';
import 'package:quwoquan_app/core/design_system/icons/app_custom_icons.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/app/shell/bottom_navigation.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/app/shell/web_app_install_banner.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/chat/pages/chat_page.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:quwoquan_app/ui/user/pages/my_profile_page.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';
import 'package:shared_preferences/shared_preferences.dart';

dynamic _openStartupAuthGateOverride() {
  return startupAuthRestoreGateProvider.overrideWith(
    () => _OpenStartupAuthGate(),
  );
}

Widget _buildShell(String location, {bool authenticated = true}) {
  return ScreenUtilInit(
    designSize: const Size(393, 852),
    child: ProviderScope(
      overrides: [
        _openStartupAuthGateOverride(),
        authSessionStoreProvider.overrideWithValue(
          _TestAuthSessionStore(authenticated: authenticated),
        ),
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

class _OpenStartupAuthGate extends StartupAuthRestoreGateNotifier {
  @override
  bool build() => true;
}

Widget _buildDarkShell(String location, {bool authenticated = true}) {
  return ScreenUtilInit(
    designSize: const Size(393, 852),
    child: ProviderScope(
      overrides: [
        isDarkProvider.overrideWith((ref) => true),
        _openStartupAuthGateOverride(),
        authSessionStoreProvider.overrideWithValue(
          _TestAuthSessionStore(authenticated: authenticated),
        ),
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
  return ScreenUtilInit(
    designSize: const Size(393, 852),
    child: ProviderScope(
      overrides: [
        _openStartupAuthGateOverride(),
        authSessionStoreProvider.overrideWithValue(
          _TestAuthSessionStore(authenticated: authenticated),
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
                allowGuestDismissPop: loginGuestDismissCanPopFromQuery(
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
                    allowGuestDismissPop: false,
                  );
                }
                return const Scaffold(body: Center(child: Text('CREATE_PAGE')));
              },
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
        _openStartupAuthGateOverride(),
        authSessionStoreProvider.overrideWithValue(store),
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
                allowGuestDismissPop: loginGuestDismissCanPopFromQuery(
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
/// 后关闭登录页又被守卫立刻弹出」的死循环。守卫触发的登录必须 allowGuestDismissPop=false。
Widget _buildGuardedRouter({
  required bool authenticated,
  required String initialLocation,
}) {
  return ScreenUtilInit(
    designSize: const Size(393, 852),
    child: ProviderScope(
      overrides: [
        _openStartupAuthGateOverride(),
        authSessionStoreProvider.overrideWithValue(
          _TestAuthSessionStore(authenticated: authenticated),
        ),
      ],
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
              allowGuestDismissPop: false,
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
          path: AppRoutePaths.loginPathTemplate,
          builder: (context, state) => LoginPage(
            reason: state.uri.queryParameters['reason'],
            redirect: state.uri.queryParameters['redirect'],
            dismissFallback:
                state.uri.queryParameters[loginDismissFallbackQueryParam],
            allowGuestDismissPop: loginGuestDismissCanPopFromQuery(
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

class _TestAuthSessionStore implements AuthSessionStore {
  const _TestAuthSessionStore({required this.authenticated});

  final bool authenticated;

  @override
  Future<StoredAuthSession> read() async {
    return StoredAuthSession(
      accessToken: authenticated ? 'access-token' : '',
      refreshToken: authenticated ? 'refresh-token' : '',
      ownerId: authenticated ? 'user_001' : '',
      activeSubAccountId: authenticated ? 'user_001' : '',
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
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

class _MutableAuthSessionStore implements AuthSessionStore {
  bool authenticated = false;

  @override
  Future<StoredAuthSession> read() async {
    return StoredAuthSession(
      accessToken: authenticated ? 'access-token' : '',
      refreshToken: authenticated ? 'refresh-token' : '',
      ownerId: authenticated ? 'user_001' : '',
      activeSubAccountId: authenticated ? 'user_001' : '',
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
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {
    authenticated = true;
  }

  @override
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    authenticated = true;
  }

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

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

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('MainAppShell', () {
    testWidgets('底部导航展示五栏，精品成为独立一级入口', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShell(AppRoutePaths.home));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('首页'), findsWidgets);
      expect(find.text('精品'), findsWidgets);
      expect(find.text('我'), findsWidgets);
      expect(find.text(UITextConstants.bottomNavGuestProfile), findsNothing);
      expect(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(UITextConstants.chatPrimaryContacts),
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
          matching: find.text('精品'),
        ),
        findsOneWidget,
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
          matching: find.text('精品'),
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
          matching: find.text(UITextConstants.bottomNavGuestProfile),
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

      expect(find.text('发布'), findsNothing);
      expect(find.text('互动'), findsNothing);
      expect(find.text(UITextConstants.createActionWriteLong), findsOneWidget);
      expect(
        find.text(UITextConstants.createActionPostPhotoShort),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.createActionCameraSubtitle),
        findsOneWidget,
      );
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
      expect(find.text(UITextConstants.createActionWriteLong), findsOneWidget);
      expect(
        find.text(UITextConstants.createActionAddContactShort),
        findsNothing,
      );

      // 选具体创作动作时才触发登录。
      await tester.tap(find.text(UITextConstants.createActionWriteLong));
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsNothing);
      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.byType(HomePage), findsOneWidget);
      expect(find.byType(BottomNavigationWidget), findsOneWidget);
      expect(find.text('Page Not Found'), findsNothing);

      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('游客点击首页关注 tab 关闭登录页后回首页且不回环', (tester) async {
      AuthGate.resetDebounce();
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildShellRouter(authenticated: false));
      await tester.pumpAndSettle();
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
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await tester.pumpAndSettle();

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
      await tester.pumpAndSettle();
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
      await tester.pumpAndSettle();
      expect(find.byType(LoginPage), findsOneWidget);

      final loginContext = tester.element(find.byType(LoginPage));
      final container = ProviderScope.containerOf(loginContext);
      await container
          .read(authSessionControllerProvider.notifier)
          .applyLoginResult(
            AuthLoginResultDto(
              accessToken: 'access-token',
              refreshToken: 'refresh-token',
              ownerId: 'user_001',
              accountState: 'active',
              identityOrigin: 'phone',
              activeSub: const <String, dynamic>{'id': 'user_001'},
            ),
          );
      GoRouter.of(loginContext).go(AppRoutePaths.home);
      await tester.pumpAndSettle();

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
      await tester.pumpAndSettle();

      await tester.tap(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.byType(AppProfilePersonIcon),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsOneWidget);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await tester.pumpAndSettle();

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
      await tester.pumpAndSettle();

      await tester.tap(
        find.descendant(
          of: find.byType(BottomNavigationWidget),
          matching: find.text(UITextConstants.chatPrimaryContacts),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsOneWidget);
      expect(find.text('CHAT_PAGE'), findsNothing);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await tester.pumpAndSettle();

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
      await tester.pumpAndSettle();

      // 守卫应把 /chat 直达重定向到登录页，而非展示受限的会话页。
      expect(find.byType(LoginPage), findsOneWidget);
      expect(find.text('CHAT_PAGE'), findsNothing);

      // 关闭登录页：必须 go 到安全兜底（首页），禁止 pop 回 /chat 再次命中守卫。
      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsNothing);
      expect(find.text('CHAT_PAGE'), findsNothing);
      expect(find.byType(MainAppShell), findsOneWidget);
      expect(find.text('Page Not Found'), findsNothing);

      // 再 pump 一帧确认守卫没有把登录页二次弹出（无死循环）。
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
      await tester.pumpAndSettle();

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
      await tester.pumpAndSettle();

      expect(find.byType(LoginPage), findsOneWidget);
      expect(find.text('CREATE_PAGE'), findsNothing);

      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      await tester.pumpAndSettle();

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
      final premiumIcon = find.descendant(
        of: navFinder,
        matching: find.byType(AppOpenWindowIcon),
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
      expect(
        tester.widget<AppOpenWindowIcon>(premiumIcon).size,
        expectedIconSize,
      );
      expect(tester.widget<AppOpenWindowIcon>(premiumIcon).filled, isFalse);
      expect(
        tester.widget<AppOpenWindowIcon>(premiumIcon).color,
        inactiveColor,
      );
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
        (tester.getCenter(premiumIcon).dy - iconCenterY).abs(),
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
      final premiumIcon = find.descendant(
        of: navFinder,
        matching: find.byType(AppOpenWindowIcon),
      );
      final contactsIcon = find.descendant(
        of: navFinder,
        matching: find.byIcon(FluentIcons.chat_multiple_24_regular),
      );
      final profileIcon = find.descendant(
        of: navFinder,
        matching: find.byType(AppProfilePersonIcon),
      );

      final premium = tester.widget<AppOpenWindowIcon>(premiumIcon);
      final contacts = tester.widget<Icon>(contactsIcon);
      final profile = tester.widget<AppProfilePersonIcon>(profileIcon);

      expect(premium.size, expectedIconSize);
      expect(contacts.size, expectedIconSize);
      expect(profile.size, expectedIconSize);
      expect(premium.filled, isFalse);
      expect(profile.filled, isFalse);
      expect(premium.color, inactiveColor);
      expect(contacts.color, AppColors.primaryColor);
      expect(profile.color, inactiveColor);
      expect(
        (tester.getCenter(premiumIcon).dy - tester.getCenter(contactsIcon).dy)
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
              _openStartupAuthGateOverride(),
              authSessionStoreProvider.overrideWithValue(
                const _TestAuthSessionStore(authenticated: true),
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
              routerConfig: router,
            ),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text(UITextConstants.webInstallBannerTitle), findsOneWidget);
      expect(
        find.text(UITextConstants.webInstallBannerDownloadApp),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(WebAppInstallBanner),
          matching: find.text(UITextConstants.share),
        ),
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
              _openStartupAuthGateOverride(),
              authSessionStoreProvider.overrideWithValue(
                const _TestAuthSessionStore(authenticated: true),
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
              routerConfig: router,
            ),
          ),
        ),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text(UITextConstants.webPcWelcomeHeadline), findsNothing);
      expect(find.text(UITextConstants.webPcWelcomeSubtitle), findsNothing);
      expect(find.text(UITextConstants.webPcWelcomeScrollHint), findsNothing);
      expect(find.text(UITextConstants.webPcBrandName), findsOneWidget);
      expect(find.text(UITextConstants.webPcWelcomeContinue), findsNothing);
      expect(find.text(UITextConstants.webPcWelcomeDownload), findsNothing);
      expect(find.text(UITextConstants.webPcWelcomeLogin), findsNothing);
      expect(find.byType(WelcomeFlowerMark), findsOneWidget);
      expect(find.byType(WebAppInstallBanner), findsNothing);

      final recommendedTab = find
          .text(UITextConstants.homeTabRecommended)
          .first;
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
        findsOneWidget,
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
      expect(find.text(UITextConstants.homeTabFollowing), findsWidgets);
      expect(find.text(UITextConstants.homeTabRecommended), findsWidgets);
      expect(find.text(UITextConstants.webPcSearchHintHome), findsOneWidget);
      expect(find.text(UITextConstants.globalXiaoquSearchAsk), findsNothing);
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
      expect(find.text(UITextConstants.webPcBrandName), findsOneWidget);
      scrollView.controller!.jumpTo(AppSpacing.webPcWelcomeHeroHeight);
      await tester.pump(const Duration(milliseconds: 120));
      expect(
        find.byKey(const ValueKey<String>('web-toolbar-brand')),
        findsOneWidget,
      );
      expect(tester.getTopLeft(recommendedTab).dx, tabLeftBeforePinned);

      await tester.tap(
        find.byKey(const ValueKey<String>('web-primary-featured')),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text(UITextConstants.workFormatFilterAll), findsWidgets);
      expect(find.text(UITextConstants.workFormatFilterVideo), findsWidgets);
      expect(find.text(UITextConstants.workFormatFilterImage), findsOneWidget);
      expect(
        find.text(UITextConstants.workFormatFilterArticle),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.webPcSearchHintFeatured),
        findsOneWidget,
      );

      await tester.tap(
        find.byKey(const ValueKey<String>('web-primary-create')),
      );
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text(UITextConstants.webPcCreateTabGallery), findsOneWidget);
      expect(find.text(UITextConstants.webPcCreateTabText), findsOneWidget);
      expect(find.text(UITextConstants.webPcCreateTabDrafts), findsOneWidget);
      expect(find.text(UITextConstants.webPcSearchHintCreate), findsOneWidget);
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
            builder: (context, state) => const LoginPage(),
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
              _openStartupAuthGateOverride(),
              authSessionStoreProvider.overrideWithValue(
                const _TestAuthSessionStore(authenticated: false),
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
      expect(find.text(UITextConstants.webPcCreateTabGallery), findsOneWidget);
      expect(find.text(UITextConstants.webPcCreateTabText), findsOneWidget);
      expect(find.text(UITextConstants.webPcCreateTabDrafts), findsOneWidget);
      await tester.pump(const Duration(milliseconds: 1200));
    });
  });
}
