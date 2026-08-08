import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/main_app_shell.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/incoming_call_coordinator.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/one_tap_login_native_bridge.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/presentation/login_page.dart';
import 'package:quwoquan_app/runtime/models/visit_models.dart';
import 'package:quwoquan_app/runtime/services/visit_recorder_service.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../cloud_boundary_test_scope.dart';

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

  static Widget build({
    required bool authenticated,
    required List<Override> businessOverrides,
    GoRouter? router,
  }) {
    final effectiveRouter = router ?? _defaultRouter();
    return ProviderScope(
      overrides: [
        // 先封死 App↔Cloud 边界，再叠加壳自身依赖的对象级 typed port，
        // 保证 Web 壳测试永远不构造真实 generated operation client。
        ...sealedCloudBoundaryOverrides(),
        ...businessOverrides,
        visitRecorderServiceProvider.overrideWithValue(
          _NoopVisitRecorderService(),
        ),
        platformCapabilitiesProvider.overrideWithValue(CapabilityProfile.web),
        oneTapLoginClientProvider.overrideWithValue(
          const _UnavailableOneTapLoginClient(),
        ),
        authSessionStoreProvider.overrideWithValue(
          _TestAuthSessionStore(authenticated: authenticated),
        ),
        incomingCallCoordinatorProvider.overrideWith(
          _NoopIncomingCallCoordinator.new,
        ),
        if (authenticated)
          authSessionControllerProvider.overrideWith(
            _AuthenticatedTestAuthSession.new,
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
          path: AppRoutePaths.chat,
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

final class _NoopVisitRecorderService extends VisitRecorderService {
  @override
  Future<void> recordVisit(VisitTarget target) async {}
}

class _UnavailableOneTapLoginClient implements OneTapLoginClient {
  const _UnavailableOneTapLoginClient();

  @override
  Future<bool> isAvailable() async => false;

  @override
  Future<OneTapLoginProbe> probe() async => const OneTapLoginProbe(
    availability: OneTapAvailability.unsupportedPlatform,
  );

  @override
  Future<OneTapLoginResult> requestLoginToken() {
    throw UnimplementedError('one tap login is unavailable in web shell tests');
  }
}

class _AuthenticatedTestAuthSession extends AuthSessionController {
  @override
  AuthSessionState build() {
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

class _NoopIncomingCallCoordinator extends IncomingCallCoordinator {
  _NoopIncomingCallCoordinator(Ref ref)
    : super(
        ref: ref,
        readRouter: () => throw UnimplementedError(
          'incoming call routing is disabled in web shell tests',
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

class _TestAuthSessionStore implements AuthSessionStore {
  const _TestAuthSessionStore({required this.authenticated});

  final bool authenticated;

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
  }) async {}

  @override
  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {}

  @override
  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {}

  @override
  Future<void> updateActivePersona(String personaId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}
