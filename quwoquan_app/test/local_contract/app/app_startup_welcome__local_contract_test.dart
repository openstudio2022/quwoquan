import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/app/navigation/app_router_module.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import 'package:quwoquan_app/quwoquan_app_shell.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../support/runtime_failure_fixtures.dart';

AuthSessionRefreshExecutor _refreshExecutor(
  Future<AuthLoginResultDto> Function(
    String refreshToken,
    Future<void>? abortTrigger,
  )
  run,
) {
  return (String refreshToken, {Future<void>? abortTrigger}) =>
      run(refreshToken, abortTrigger);
}

void main() {
  setUpAll(() async {
    await ensureAppRouterLibraryLoaded();
  });

  Widget wrapRoot(Widget child) {
    return ScreenUtilInit(designSize: const Size(393, 852), child: child);
  }

  void suppressExpectedErrors() {
    final original = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('overflowed') ||
          message.contains('HTTP request failed') ||
          message.contains('NetworkImageLoadException')) {
        return;
      }
      original?.call(details);
    };
  }

  List<Override> startupOverrides({
    required AuthSessionStore authStore,
    List<Override> extra = const [],
  }) {
    return [
      appDataSourceModeProvider.overrideWith(_StartupMockDataSource.new),
      authSessionStoreProvider.overrideWithValue(authStore),
      opsEventRepositoryProvider.overrideWithValue(MockOpsEventRepository()),
      ...extra,
    ];
  }

  testWidgets('启动首帧直接展示欢迎页，不等待认证恢复完成', (tester) async {
    suppressExpectedErrors();
    final blockingStore = _BlockingAuthSessionStore();

    await tester.pumpWidget(
      wrapRoot(
        ProviderScope(
          overrides: startupOverrides(authStore: blockingStore),
          child: const QuWoQuanAppRoot(),
        ),
      ),
    );

    // pumpWidget 已提交 Flutter 首帧；认证从此刻开始并行，但不阻塞品牌终态。
    expect(blockingStore.readStarted, isTrue);
    expect(find.text(UITextConstants.welcomeTitle), findsOneWidget);

    await tester.pump();

    expect(blockingStore.readStarted, isTrue);
    expect(find.text(UITextConstants.welcomeTitle), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  Future<void> pumpStartupThroughWelcome(WidgetTester tester) async {
    // 正常路径一轮约 1.04s；3s 内应进入主壳，6s 仅是异常硬门。
    for (var i = 0; i < 60; i++) {
      await tester.pump(const Duration(milliseconds: 50));
      if (find.byType(MainAppShell).evaluate().isNotEmpty) {
        break;
      }
    }
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 20));
      if (find.byType(WelcomeScreen).evaluate().isEmpty) {
        break;
      }
    }
    await tester.pump();
  }

  testWidgets('欢迎序列结束但认证仍未恢复时也进入主壳，由页面承接加载态', (tester) async {
    suppressExpectedErrors();
    final blockingStore = _BlockingAuthSessionStore();

    await tester.pumpWidget(
      wrapRoot(
        ProviderScope(
          overrides: startupOverrides(authStore: blockingStore),
          child: const QuWoQuanAppRoot(),
        ),
      ),
    );

    await pumpStartupThroughWelcome(tester);

    expect(find.byType(WelcomeScreen), findsNothing);
    expect(find.byType(MainAppShell), findsOneWidget);
    expect(find.text(UITextConstants.startupStillStartingInline), findsNothing);
    expect(find.text('正在进入趣我圈'), findsNothing);
    expect(find.text('恢复账号状态'), findsNothing);

    await tester.pump(const Duration(seconds: 16));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('debug 环境前置任务未完成也不触发欢迎重放或阻断安全主壳', (tester) async {
    suppressExpectedErrors();
    final prerequisites = Completer<void>();
    final store = _BlockingAuthSessionStore();

    await tester.pumpWidget(
      wrapRoot(
        ProviderScope(
          overrides: startupOverrides(authStore: store),
          child: QuWoQuanAppRoot(startupPrerequisites: prerequisites.future),
        ),
      ),
    );

    await pumpStartupThroughWelcome(tester);

    expect(prerequisites.isCompleted, isFalse);
    expect(find.byType(WelcomeScreen), findsNothing);
    expect(find.byType(MainAppShell), findsOneWidget);
    expect(find.text(UITextConstants.startupStillStartingInline), findsNothing);

    prerequisites.complete();
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('启动条件满足后，欢迎页在并行动效序列后进入主壳首页', (tester) async {
    suppressExpectedErrors();
    final store = _ImmediateAuthSessionStore(
      stored: const StoredAuthSession(
        accessToken: '',
        refreshToken: '',
        ownerId: '',
        activeSubAccountId: '',
        accountState: '',
        identityOrigin: '',
        installId: 'install-id',
        lastRefreshAtEpochMs: 0,
        lastForegroundAuthCheckAtEpochMs: 0,
        manualLoggedOut: false,
        launchPromptDismissed: true,
      ),
    );

    await tester.pumpWidget(
      wrapRoot(
        ProviderScope(
          overrides: startupOverrides(authStore: store),
          child: const QuWoQuanAppRoot(),
        ),
      ),
    );

    await pumpStartupThroughWelcome(tester);

    expect(find.byType(WelcomeScreen), findsNothing);
    expect(find.byType(MainAppShell), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('Web 启动欢迎期不构建 GoRouter，欢迎结束后进入主壳', (tester) async {
    suppressExpectedErrors();
    final blockingStore = _BlockingAuthSessionStore();

    await tester.pumpWidget(
      wrapRoot(
        ProviderScope(
          overrides: startupOverrides(
            authStore: blockingStore,
            extra: [
              platformTargetProvider.overrideWithValue(AppPlatform.web),
              platformCapabilitiesProvider.overrideWithValue(
                CapabilityProfile.web,
              ),
            ],
          ),
          child: const QuWoQuanAppRoot(),
        ),
      ),
    );

    expect(blockingStore.readStarted, isTrue);
    expect(find.byType(MainAppShell), findsNothing);
    expect(find.byType(WelcomeScreen), findsOneWidget);
    expect(find.textContaining('登录后，趣我圈'), findsNothing);
    expect(find.textContaining('先不登录'), findsNothing);
    expect(find.byType(LoginPage), findsNothing);

    await tester.pump();
    expect(blockingStore.readStarted, isTrue);
    await pumpStartupThroughWelcome(tester);

    expect(find.byType(MainAppShell), findsOneWidget);
    expect(find.byType(WelcomeScreen), findsNothing);
    expect(find.byType(LoginPage), findsNothing);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('长期未回访的已登录会话会在恢复时静默 refresh，尽量免登录', (tester) async {
    suppressExpectedErrors();
    final store = _ImmediateAuthSessionStore(
      stored: const StoredAuthSession(
        accessToken: 'stale-access',
        refreshToken: 'stale-refresh',
        ownerId: 'owner-1',
        activeSubAccountId: 'sub-1',
        accountState: 'active',
        identityOrigin: 'phone',
        installId: 'install-id',
        lastRefreshAtEpochMs: 1,
        lastForegroundAuthCheckAtEpochMs: 1,
        manualLoggedOut: false,
        launchPromptDismissed: true,
      ),
    );

    await tester.pumpWidget(
      wrapRoot(
        ProviderScope(
          overrides: startupOverrides(
            authStore: store,
            extra: [
              authSessionRefreshExecutorProvider.overrideWithValue(
                _refreshExecutor((refreshToken, _) async {
                  expect(refreshToken, 'stale-refresh');
                  return AuthLoginResultDto.fromMap(<String, dynamic>{
                    'accessToken': 'fresh-access',
                    'refreshToken': 'fresh-refresh',
                  });
                }),
              ),
            ],
          ),
          child: const QuWoQuanAppRoot(),
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(store.savedRefreshAccessToken, 'fresh-access');
    expect(store.savedRefreshToken, 'fresh-refresh');
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('静默 refresh 判定为 token 失效时，清理会话进入重登态', (tester) async {
    suppressExpectedErrors();
    final store = _ImmediateAuthSessionStore(
      stored: const StoredAuthSession(
        accessToken: 'stale-access',
        refreshToken: 'expired-refresh',
        ownerId: 'owner-1',
        activeSubAccountId: 'sub-1',
        accountState: 'active',
        identityOrigin: 'phone',
        installId: 'install-id',
        lastRefreshAtEpochMs: 1,
        lastForegroundAuthCheckAtEpochMs: 1,
        manualLoggedOut: false,
        launchPromptDismissed: true,
      ),
    );

    await tester.pumpWidget(
      wrapRoot(
        ProviderScope(
          overrides: startupOverrides(
            authStore: store,
            extra: [
              authSessionRefreshExecutorProvider.overrideWithValue(
                _refreshExecutor((_, _) async {
                  throw CloudException(
                    type: CloudErrorType.unauthorized,
                    message: 'expired',
                    statusCode: 401,
                    runtimeFailure: testRuntimeFailure(
                      code: 'USER.AUTH.session_expired',
                      kind: RuntimeFailureKind.auth,
                    ),
                  );
                }),
              ),
            ],
          ),
          child: const QuWoQuanAppRoot(),
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(seconds: 4));

    expect(store.stored.accessToken, isEmpty);
    expect(store.stored.refreshToken, isEmpty);
    expect(store.stored.manualLoggedOut, isFalse);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });
}

final class _StartupMockDataSource extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;
}

final class _BlockingAuthSessionStore implements AuthSessionStore {
  final Completer<StoredAuthSession> _readCompleter =
      Completer<StoredAuthSession>();

  bool readStarted = false;
  bool readCompleted = false;

  @override
  Future<StoredAuthSession> read() async {
    readStarted = true;
    final stored = await _readCompleter.future;
    readCompleted = true;
    return stored;
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
  Future<void> saveRefreshedAccountHint(
    Map<String, dynamic>? accountHint,
  ) async {}

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

final class _ImmediateAuthSessionStore implements AuthSessionStore {
  _ImmediateAuthSessionStore({required this.stored});

  StoredAuthSession stored;
  String? savedRefreshAccessToken;
  String? savedRefreshToken;

  @override
  Future<StoredAuthSession> read() async => stored;

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
  }) async {
    savedRefreshAccessToken = accessToken;
    savedRefreshToken = refreshToken;
    stored = StoredAuthSession(
      accessToken: accessToken,
      refreshToken: refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: stored.activeSubAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      lastRefreshAtEpochMs: DateTime.now().millisecondsSinceEpoch,
      lastForegroundAuthCheckAtEpochMs: DateTime.now().millisecondsSinceEpoch,
      manualLoggedOut: false,
      launchPromptDismissed: false,
    );
  }

  @override
  Future<void> saveRefreshedAccountHint(
    Map<String, dynamic>? accountHint,
  ) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {
    stored = StoredAuthSession(
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: subAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      lastRefreshAtEpochMs: stored.lastRefreshAtEpochMs,
      lastForegroundAuthCheckAtEpochMs: stored.lastForegroundAuthCheckAtEpochMs,
      manualLoggedOut: stored.manualLoggedOut,
      launchPromptDismissed: stored.launchPromptDismissed,
    );
  }

  @override
  Future<void> clearSession({required bool manualLogout}) async {
    stored = StoredAuthSession(
      accessToken: '',
      refreshToken: '',
      ownerId: '',
      activeSubAccountId: '',
      accountState: '',
      identityOrigin: '',
      installId: stored.installId,
      lastRefreshAtEpochMs: 0,
      lastForegroundAuthCheckAtEpochMs: 0,
      manualLoggedOut: manualLogout,
      launchPromptDismissed: false,
    );
  }

  @override
  Future<void> softLogout() async {
    stored = StoredAuthSession(
      accessToken: '',
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: stored.activeSubAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      lastRefreshAtEpochMs: stored.lastRefreshAtEpochMs,
      lastForegroundAuthCheckAtEpochMs: stored.lastForegroundAuthCheckAtEpochMs,
      manualLoggedOut: true,
      launchPromptDismissed: false,
    );
  }

  @override
  Future<void> markLaunchPromptDismissed() async {
    stored = StoredAuthSession(
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: stored.activeSubAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      lastRefreshAtEpochMs: stored.lastRefreshAtEpochMs,
      lastForegroundAuthCheckAtEpochMs: stored.lastForegroundAuthCheckAtEpochMs,
      manualLoggedOut: stored.manualLoggedOut,
      launchPromptDismissed: true,
    );
  }

  @override
  Future<void> markForegroundAuthCheckNow() async {
    stored = StoredAuthSession(
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activeSubAccountId: stored.activeSubAccountId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      lastRefreshAtEpochMs: stored.lastRefreshAtEpochMs,
      lastForegroundAuthCheckAtEpochMs: DateTime.now().millisecondsSinceEpoch,
      manualLoggedOut: stored.manualLoggedOut,
      launchPromptDismissed: stored.launchPromptDismissed,
    );
  }
}
