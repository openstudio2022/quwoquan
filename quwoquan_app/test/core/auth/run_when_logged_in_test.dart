import 'package:flutter/cupertino.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/l10n.dart';

class _TestAuthSessionStore implements AuthSessionStore {
  _TestAuthSessionStore({required this.authenticated});

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
      manualLoggedOut: false,
      launchPromptDismissed: true,
    );
  }

  @override
  Future<void> saveLoginResult(AuthLoginResultDto result) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}
}

void main() {
  late bool executed;

  setUp(() {
    executed = false;
    AuthGate.resetDebounce();
  });

  Widget buildApp({required bool authenticated}) {
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
                  AuthGateReason.like,
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
        authSessionStoreProvider.overrideWithValue(
          _TestAuthSessionStore(authenticated: authenticated),
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
