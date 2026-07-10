import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

void main() {
  test('restore 遇到陈旧会话时静默 refresh 成功并保留 owner/sub 快照', () async {
    final store = _MemoryAuthSessionStore(
      stored: const StoredAuthSession(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
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
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(_MockRemoteMode.new),
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        authSessionRefreshExecutorProvider.overrideWithValue((
          refreshToken,
        ) async {
          expect(refreshToken, 'old-refresh');
          return AuthLoginResultDto.fromMap(<String, dynamic>{
            'accessToken': 'new-access',
            'refreshToken': 'new-refresh',
          });
        }),
      ],
    );
    addTearDown(container.dispose);

    final state = container.read(authSessionControllerProvider);
    expect(state.status, AuthSessionStatus.restoring);
    await Future<void>.delayed(const Duration(milliseconds: 10));

    final refreshed = container.read(authSessionControllerProvider);
    expect(refreshed.isAuthenticated, isTrue);
    expect(refreshed.accessToken, 'new-access');
    expect(refreshed.refreshToken, 'new-refresh');
    expect(refreshed.ownerId, 'owner-1');
    expect(refreshed.activeSubAccountId, 'sub-1');
  });

  test('静默 refresh 返回 401 时清理会话并进入 sessionExpired', () async {
    final store = _MemoryAuthSessionStore.authenticated();
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(_MockRemoteMode.new),
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        authSessionRefreshExecutorProvider.overrideWithValue((_) async {
          throw CloudException(
            type: CloudErrorType.unauthorized,
            message: 'expired',
            statusCode: 401,
          );
        }),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    final refreshed = await notifier.refreshSessionIfNeeded(force: true);

    expect(refreshed, isFalse);
    final state = container.read(authSessionControllerProvider);
    expect(state.isAuthenticated, isFalse);
    expect(state.promptReason, AuthPromptReason.sessionExpired);
  });

  test('静默 refresh 网络失败时保留登录态，避免误登出', () async {
    final store = _MemoryAuthSessionStore.authenticated();
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(_MockRemoteMode.new),
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        authSessionRefreshExecutorProvider.overrideWithValue((_) async {
          throw CloudException(
            type: CloudErrorType.network,
            message: 'offline',
          );
        }),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    final refreshed = await notifier.refreshSessionIfNeeded(force: true);

    expect(refreshed, isFalse);
    final state = container.read(authSessionControllerProvider);
    expect(state.isAuthenticated, isTrue);
    expect(state.promptReason, isNull);
    expect(state.errorMessage, isNotNull);
  });

  test(
    'softLogout 置 guest+manualLoggedOut，保留 refreshToken 与 remembered 摘要',
    () async {
      final nowMs = DateTime.now().millisecondsSinceEpoch;
      final store = _MemoryAuthSessionStore(
        stored: StoredAuthSession(
          accessToken: 'access-token',
          refreshToken: 'refresh-token',
          ownerId: 'owner-1',
          activeSubAccountId: 'sub-1',
          accountState: 'active',
          identityOrigin: 'phone',
          installId: 'install-id',
          lastRefreshAtEpochMs: nowMs,
          lastForegroundAuthCheckAtEpochMs: nowMs,
          rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
          rememberedLoginMaskedIdentifier: '138****0001',
          rememberedDisplayName: '趣友A',
          manualLoggedOut: false,
          launchPromptDismissed: true,
        ),
      );
      final container = ProviderContainer(
        overrides: [
          appDataSourceModeProvider.overrideWith(_MockRemoteMode.new),
          startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
          authSessionStoreProvider.overrideWithValue(store),
          authSessionRefreshExecutorProvider.overrideWithValue(
            (_) async => AuthLoginResultDto(),
          ),
        ],
      );
      addTearDown(container.dispose);

      container.read(authSessionControllerProvider);
      await Future<void>.delayed(const Duration(milliseconds: 10));
      final notifier = container.read(authSessionControllerProvider.notifier);
      await notifier.softLogout();

      final state = container.read(authSessionControllerProvider);
      expect(state.isAuthenticated, isFalse);
      expect(state.status, AuthSessionStatus.guest);
      expect(state.promptReason, AuthPromptReason.manualLoggedOut);
      expect(state.rememberedLoginMethod, AuthRememberedLoginMethod.phoneOtp);

      final stored = await store.read();
      expect(stored.accessToken, isEmpty);
      expect(stored.refreshToken, 'refresh-token');
      expect(stored.manualLoggedOut, isTrue);
      expect(stored.hasValidQuickLoginCredential, isTrue);
    },
  );

  test('hardLogout 清除 refreshToken，下次登录无可用快速登录凭证', () async {
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final store = _MemoryAuthSessionStore(
      stored: StoredAuthSession(
        accessToken: 'access-token',
        refreshToken: 'refresh-token',
        ownerId: 'owner-1',
        activeSubAccountId: 'sub-1',
        accountState: 'active',
        identityOrigin: 'phone',
        installId: 'install-id',
        lastRefreshAtEpochMs: nowMs,
        lastForegroundAuthCheckAtEpochMs: nowMs,
        manualLoggedOut: false,
        launchPromptDismissed: true,
      ),
    );
    final container = ProviderContainer(
      overrides: [
        appDataSourceModeProvider.overrideWith(_MockRemoteMode.new),
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        authSessionRefreshExecutorProvider.overrideWithValue(
          (_) async => AuthLoginResultDto(),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    await notifier.hardLogout();

    final state = container.read(authSessionControllerProvider);
    expect(state.isAuthenticated, isFalse);
    expect(state.status, AuthSessionStatus.guest);
    expect(state.promptReason, AuthPromptReason.manualLoggedOut);

    final stored = await store.read();
    expect(stored.refreshToken, isEmpty);
    expect(stored.hasValidQuickLoginCredential, isFalse);
  });
}

final class _MockRemoteMode extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.remote;
}

final class _OpenStartupAuthGate extends StartupAuthRestoreGateNotifier {
  @override
  bool build() => true;
}

final class _MemoryAuthSessionStore implements AuthSessionStore {
  _MemoryAuthSessionStore({required this.stored});

  factory _MemoryAuthSessionStore.authenticated() {
    return _MemoryAuthSessionStore(
      stored: const StoredAuthSession(
        accessToken: 'access-token',
        refreshToken: 'refresh-token',
        ownerId: 'owner-1',
        activeSubAccountId: 'sub-1',
        accountState: 'active',
        identityOrigin: 'phone',
        installId: 'install-id',
        lastRefreshAtEpochMs: 0,
        lastForegroundAuthCheckAtEpochMs: 0,
        manualLoggedOut: false,
        launchPromptDismissed: true,
      ),
    );
  }

  StoredAuthSession stored;

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
    final expiresAtMs =
        DateTime.now().millisecondsSinceEpoch +
        kDefaultSessionRememberTtlSeconds * 1000;
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
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      quickLoginExpiresAtEpochMs: expiresAtMs,
      sessionRememberTtlSeconds: stored.sessionRememberTtlSeconds,
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
