import 'package:flutter/cupertino.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/state/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../support/service/user_service/account/account_session/test_auth_facets.dart';

class _TestAuthSessionStore implements AuthSessionStore {
  _TestAuthSessionStore({required this.authenticated});

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
      launchPromptDismissed: true,
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

void main() {
  late bool executed;

  setUp(() {
    executed = false;
    AuthGate.resetDebounce();
  });

  Widget buildApp({required bool authenticated}) {
    final authFacets = TestAuthFacets();
    final router = GoRouter(
      initialLocation: '/',
      routes: <RouteBase>[
        GoRoute(
          path: '/',
          builder: (context, state) => Consumer(
            builder: (context, ref, _) {
              // 主动 watch 让 session 在 pump 期间完成 hydrate（与真实 shell 一致），
              // 否则 provider 会在点击时才惰性构建并停留在 restoring 态。
              ref.watch(authSessionControllerProvider);
              return CupertinoButton(
                key: const Key('act-button'),
                onPressed: () => runWhenLoggedIn(
                  ref,
                  context,
                  // 评论提交仍需登录，用作「通用受限写动作」门控样例；
                  // 点赞/分享已下放为游客设备态可写，不再适合作为门控样例。
                  AuthGateReason.comment,
                  () => executed = true,
                ),
                child: const Text('act'),
              );
            },
          ),
        ),
        GoRoute(
          path: '/login',
          builder: (context, state) =>
              const Text('LOGIN_PAGE', textDirection: TextDirection.ltr),
        ),
      ],
    );

    return ProviderScope(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(
          _TestAuthSessionStore(authenticated: authenticated),
        ),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          authFacets,
        ),
        activePersonaContextProvider.overrideWith(
          (_) async => ActivePersonaContextViewData.fallback(
            personaId: authenticated ? 'user_001' : '',
            ownerUserId: authenticated ? 'user_001' : '',
            displayName: authenticated ? '测试用户' : '',
            avatarUrl: '',
          ),
        ),
      ],
      child: CupertinoApp.router(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
        ],
        supportedLocales: const [Locale('zh', 'CN'), Locale('en', 'US')],
        routerConfig: router,
      ),
    );
  }

  testWidgets('游客触发写动作：不执行原动作，进入登录页', (tester) async {
    await tester.pumpWidget(buildApp(authenticated: false));
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.byKey(const Key('act-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(executed, isFalse);
    expect(find.text('LOGIN_PAGE'), findsOneWidget);

    // 让 toast 的 3s 定时器自然结束，避免 pending timer。
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('已登录触发写动作：直接执行原动作，不跳登录页', (tester) async {
    await tester.pumpWidget(buildApp(authenticated: true));
    await tester.pump(const Duration(milliseconds: 300));

    await tester.tap(find.byKey(const Key('act-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(executed, isTrue);
    expect(find.text('LOGIN_PAGE'), findsNothing);
    expect(find.byKey(const Key('act-button')), findsOneWidget);
  });
}

final class _OpenStartupAuthGate extends StartupAuthRestoreGateNotifier {
  @override
  bool build() => true;
}
