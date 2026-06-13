import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/auth/one_tap_login_channel.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';

/// Web 宽屏壳测试通用脚手架：固定宽屏视口 + Web 能力 + 可控登录态，
/// 复用同一 [MainAppShell] 入口，避免每个用例各自拼装第二套壳。
class WebShellTestHarness {
  static const Size wideViewport = Size(1280, 900);

  static void useWideViewport(WidgetTester tester) {
    tester.view.physicalSize = wideViewport;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  static Widget build({required bool authenticated, GoRouter? router}) {
    final effectiveRouter = router ?? _defaultRouter();
    return ProviderScope(
      overrides: [
        platformCapabilitiesProvider.overrideWithValue(CapabilityProfile.web),
        oneTapLoginClientProvider.overrideWithValue(
          const _UnavailableOneTapLoginClient(),
        ),
        authSessionStoreProvider.overrideWithValue(
          _TestAuthSessionStore(authenticated: authenticated),
        ),
      ],
      child: MaterialAppRouterHost(router: effectiveRouter),
    );
  }

  static GoRouter _defaultRouter() {
    return GoRouter(
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
    );
  }

  /// 滚出欢迎页、吸顶工具栏，使五个一级入口（web-primary-*）可点。
  static Future<void> enterToolbar(WidgetTester tester) async {
    await tester.pump(const Duration(milliseconds: 300));
    await tester.drag(
      find.byKey(const ValueKey<String>('web-shell-scroll')),
      const Offset(0, -260),
    );
    await tester.pump(const Duration(milliseconds: 300));
  }

  static Future<void> tapPrimary(WidgetTester tester, String routeName) async {
    await tester.tap(find.byKey(ValueKey<String>('web-primary-$routeName')));
    await tester.pump(const Duration(milliseconds: 300));
  }

  static void suppressExpectedErrors() {
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
}

class MaterialAppRouterHost extends StatelessWidget {
  const MaterialAppRouterHost({super.key, required this.router});

  final GoRouter router;

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      routerConfig: router,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
    );
  }
}

class _UnavailableOneTapLoginClient implements OneTapLoginClient {
  const _UnavailableOneTapLoginClient();

  @override
  Future<bool> isAvailable() async => false;

  @override
  Future<OneTapLoginResult> requestLoginToken() {
    throw UnimplementedError('one tap login is unavailable in web shell tests');
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
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}
