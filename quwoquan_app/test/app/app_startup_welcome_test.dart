import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/app/shell/main_app_shell.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/quwoquan_app_shell.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';
import 'package:quwoquan_app/ui/welcome/pages/welcome_screen.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

void main() {
  testWidgets('启动首帧直接展示欢迎页，不等待认证恢复完成', (tester) async {
    final blockingStore = _BlockingAuthSessionStore();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appDataSourceModeProvider.overrideWith(_StartupMockDataSource.new),
          authSessionStoreProvider.overrideWithValue(blockingStore),
        ],
        child: const QuWoQuanAppRoot(),
      ),
    );

    expect(blockingStore.readStarted, isTrue);
    expect(blockingStore.readCompleted, isFalse);
    expect(find.text(UITextConstants.welcomeTitle), findsOneWidget);
    expect(find.text(UITextConstants.welcomeMainSlogan), findsOneWidget);
    expect(find.byType(WelcomeFlowerMark), findsOneWidget);

    await tester.pump();

    expect(blockingStore.readStarted, isTrue);
    expect(blockingStore.readCompleted, isFalse);
    expect(find.text(UITextConstants.welcomeTitle), findsOneWidget);
    expect(find.byType(WelcomeFlowerMark), findsOneWidget);

    await tester.pump(const Duration(seconds: 16));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('Web 启动先出内容壳，再叠欢迎层且不显示登录 prompt', (tester) async {
    final blockingStore = _BlockingAuthSessionStore();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          appDataSourceModeProvider.overrideWith(_StartupMockDataSource.new),
          authSessionStoreProvider.overrideWithValue(blockingStore),
          platformTargetProvider.overrideWithValue(AppPlatform.web),
          platformCapabilitiesProvider.overrideWithValue(CapabilityProfile.web),
        ],
        child: const QuWoQuanAppRoot(),
      ),
    );

    expect(blockingStore.readStarted, isTrue);
    expect(find.byType(MainAppShell), findsOneWidget);
    expect(find.byType(WelcomeScreen), findsOneWidget);
    expect(find.text(UITextConstants.welcomeLoginPromptTitle), findsNothing);
    expect(find.byType(LoginPage), findsNothing);

    await tester.pump();
    await tester.pump(const Duration(seconds: 3));

    expect(find.byType(MainAppShell), findsOneWidget);
    expect(find.byType(WelcomeScreen), findsOneWidget);
    expect(find.byType(LoginPage), findsNothing);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(milliseconds: 50));
  });

  testWidgets('长期未回访的已登录会话会在恢复时静默 refresh，尽量免登录', (tester) async {
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
      ProviderScope(
        overrides: [
          appDataSourceModeProvider.overrideWith(_StartupMockDataSource.new),
          authSessionStoreProvider.overrideWithValue(store),
          authSessionRefreshExecutorProvider.overrideWithValue((
            refreshToken,
          ) async {
            expect(refreshToken, 'stale-refresh');
            return AuthLoginResultDto.fromMap(<String, dynamic>{
              'accessToken': 'fresh-access',
              'refreshToken': 'fresh-refresh',
            });
          }),
        ],
        child: const QuWoQuanAppRoot(),
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
      ProviderScope(
        overrides: [
          appDataSourceModeProvider.overrideWith(_StartupMockDataSource.new),
          authSessionStoreProvider.overrideWithValue(store),
          authSessionRefreshExecutorProvider.overrideWithValue((_) async {
            throw CloudException(
              type: CloudErrorType.unauthorized,
              message: 'expired',
              statusCode: 401,
            );
          }),
        ],
        child: const QuWoQuanAppRoot(),
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
