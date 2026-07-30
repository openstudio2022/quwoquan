// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004
// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-005

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:quwoquan_app/application/user/account/account_closure_local_data_purger.dart';
import 'package:quwoquan_app/application/user/account/account_closure_local_data_purger_provider.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/auth/terminal_account_cleanup_receipt_store.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show accountSessionLifecycleCommandWriterProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../support/runtime_failure_fixtures.dart';

AccountSessionLifecycleCommandWriter _lifecycleWriter(
  Future<TokenRefreshGrant> Function(RefreshTokenCommand command) refresh,
) => _StubAccountSessionLifecycleWriter(refresh);

void main() {
  test('账号注销本地清理回执加密持久化并在成功后物理删除', () async {
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
    const store = SecureTerminalAccountCleanupReceiptStore();
    const receipt = TerminalAccountCleanupReceipt(
      accountId: 'owner-recovery',
      personaId: 'persona-recovery',
      installId: 'install-recovery',
    );

    await store.save(receipt);
    final restored = await store.read();
    expect(restored?.accountId, receipt.accountId);
    expect(restored?.personaId, receipt.personaId);

    await store.clear();
    expect(await store.read(), isNull);
  });

  test('终态本地清理三次失败保留回执，后续恢复成功才删除', () async {
    final receiptStore = _MemoryTerminalCleanupReceiptStore()
      ..receipt = const TerminalAccountCleanupReceipt(
        accountId: 'owner-recovery',
        personaId: 'persona-recovery',
        installId: 'install-recovery',
      );
    var shouldFail = true;
    var purgeCalls = 0;
    final container = ProviderContainer(
      overrides: [
        terminalAccountCleanupReceiptStoreProvider.overrideWithValue(
          receiptStore,
        ),
        accountClosureLocalDataPurgerForActorProvider.overrideWith((
          ref,
          actor,
        ) {
          return AccountClosureLocalDataPurger(
            clearBehaviorQueue: () async {
              purgeCalls += 1;
              if (shouldFail) {
                throw StateError('transient cleanup failure');
              }
            },
            clearTelemetryQueue: () async {},
            clearRebuildableUserData: () async {},
            purgePushAndIncomingCallState: () async {},
            clearDraftsAndAccountPreferences: () async {},
          );
        }),
      ],
    );
    addTearDown(container.dispose);
    final recover = container.read(accountClosureLocalCleanupRecoveryProvider);

    await recover();
    expect(purgeCalls, 3);
    expect(await receiptStore.read(), isNotNull);
    expect(receiptStore.clearCalls, 0);

    shouldFail = false;
    await recover();
    expect(purgeCalls, 4);
    expect(await receiptStore.read(), isNull);
    expect(receiptStore.clearCalls, 1);
  });

  test('restore 遇到陈旧会话时静默 refresh 成功并保留 owner/persona 快照', () async {
    final store = _MemoryAuthSessionStore(
      stored: const StoredAuthSession(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
        ownerId: 'owner-1',
        activePersonaId: 'sub-1',
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
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((command) async {
            expect(command.refreshToken, 'old-refresh');
            return const TokenRefreshGrant(
              accessToken: 'new-access',
              refreshToken: 'new-refresh',
              sessionRememberTtlSeconds: 0,
            );
          }),
        ),
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
    expect(refreshed.activePersonaId, 'sub-1');
  });

  test('静默 refresh 返回 401 时清理会话并进入 sessionExpired', () async {
    final store = _MemoryAuthSessionStore(stored: _currentStoredSession());
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) async {
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

  test('静默 refresh 返回 account_suspended 时清除凭证并保留受限原因', () async {
    final store = _MemoryAuthSessionStore(stored: _currentStoredSession());
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) async {
            throw CloudException(
              type: CloudErrorType.forbidden,
              message: 'account restricted',
              code: UserErrorCode.accountSuspended.code,
              statusCode: 403,
              runtimeFailure: testRuntimeFailure(
                code: UserErrorCode.accountSuspended.code,
                kind: RuntimeFailureKind.auth,
              ),
            );
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final refreshed = await container
        .read(authSessionControllerProvider.notifier)
        .refreshSessionIfNeeded(force: true);

    expect(refreshed, isFalse);
    final state = container.read(authSessionControllerProvider);
    expect(state.isAuthenticated, isFalse);
    expect(state.promptReason, AuthPromptReason.accountSuspended);
    expect(state.errorMessage, isNotEmpty);
    final persisted = await store.read();
    expect(persisted.accessToken, isEmpty);
    expect(persisted.refreshToken, isEmpty);
  });

  test('generated 403 按实际旧 bearer 立即清凭证，关闭说明后仍不恢复旧 token', () async {
    final store = _MemoryAuthSessionStore(stored: _currentStoredSession());
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) async => throw StateError('not expected')),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    await notifier.handleAuthoritativeSessionFailure(
      _accountSuspendedFailure(),
      presentedAccessToken: 'access-token',
    );

    var state = container.read(authSessionControllerProvider);
    expect(state.isAuthenticated, isFalse);
    expect(state.promptReason, AuthPromptReason.accountSuspended);
    expect(state.accessToken, isEmpty);
    expect(state.refreshToken, isEmpty);
    expect((await store.read()).hasValidQuickLoginCredential, isFalse);

    notifier.acknowledgeAccountRestrictionNotice();
    state = container.read(authSessionControllerProvider);
    expect(state.promptReason, isNull);
    expect(state.hasTrustedSession, isFalse);
    expect((await store.read()).accessToken, isEmpty);
    expect((await store.read()).refreshToken, isEmpty);
  });

  test('同一 bearer 的并发 authoritative 403 在会话串行边界只清理一次', () async {
    final store = _MemoryAuthSessionStore(stored: _currentStoredSession());
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) async => throw StateError('not expected')),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    await Future.wait<void>(<Future<void>>[
      notifier.handleAuthoritativeSessionFailure(
        _accountSuspendedFailure(),
        presentedAccessToken: 'access-token',
      ),
      notifier.handleAuthoritativeSessionFailure(
        _accountSuspendedFailure(),
        presentedAccessToken: 'access-token',
      ),
    ]);

    final state = container.read(authSessionControllerProvider);
    expect(state.isAuthenticated, isFalse);
    expect(state.promptReason, AuthPromptReason.accountSuspended);
    expect(store.clearSessionCalls, 1);
  });

  test('旧 refresh 的迟到 account_suspended 不会清除已经换发的新会话', () async {
    final store = _MemoryAuthSessionStore(stored: _currentStoredSession());
    final refreshStarted = Completer<void>();
    final delayedRefresh = Completer<TokenRefreshGrant>();
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) {
            refreshStarted.complete();
            return delayedRefresh.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    final oldRefresh = notifier.refreshSessionIfNeeded(force: true);
    await refreshStarted.future;
    await notifier.applyRefreshGrant(
      const TokenRefreshGrant(
        accessToken: 'new-session-access',
        refreshToken: 'new-session-refresh',
        sessionRememberTtlSeconds: 2592000,
      ),
    );
    delayedRefresh.completeError(_accountSuspendedFailure());

    expect(await oldRefresh, isFalse);
    final state = container.read(authSessionControllerProvider);
    expect(state.isAuthenticated, isTrue);
    expect(state.accessToken, 'new-session-access');
    expect(state.refreshToken, 'new-session-refresh');
    expect(state.promptReason, isNull);
  });

  test('静默 refresh 返回 account_deleted 410 时清除本地可换发凭证', () async {
    final store = _MemoryAuthSessionStore.authenticated();
    final cleanupReceiptStore = _MemoryTerminalCleanupReceiptStore();
    var localPurgeCalls = 0;
    AccountClosureLocalActorContext? purgedActor;
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        terminalAccountCleanupReceiptStoreProvider.overrideWithValue(
          cleanupReceiptStore,
        ),
        accountClosureLocalDataPurgerForActorProvider.overrideWith((
          ref,
          actor,
        ) {
          purgedActor = actor;
          return AccountClosureLocalDataPurger(
            clearBehaviorQueue: () async {
              localPurgeCalls += 1;
            },
            clearTelemetryQueue: () async {},
            clearRebuildableUserData: () async {},
            purgePushAndIncomingCallState: () async {},
            clearDraftsAndAccountPreferences: () async {},
          );
        }),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) async {
            throw CloudException(
              type: CloudErrorType.unknown,
              message: 'account deleted',
              code: UserErrorCode.accountDeleted.code,
              statusCode: 410,
              runtimeFailure: testRuntimeFailure(
                code: UserErrorCode.accountDeleted.code,
                kind: RuntimeFailureKind.auth,
              ),
            );
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    container.read(accountClosureLocalCleanupLifecycleProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final refreshed = await container
        .read(authSessionControllerProvider.notifier)
        .refreshSessionIfNeeded(force: true);

    expect(refreshed, isFalse);
    final state = container.read(authSessionControllerProvider);
    expect(state.isAuthenticated, isFalse);
    expect(state.promptReason, AuthPromptReason.accountClosed);
    final persisted = await store.read();
    expect(persisted.accessToken, isEmpty);
    expect(persisted.refreshToken, isEmpty);
    expect(persisted.manualLoggedOut, isTrue);
    await Future<void>.delayed(Duration.zero);
    expect(localPurgeCalls, 1);
    expect(purgedActor?.accountId, 'owner-1');
    expect(purgedActor?.personaId, 'sub-1');
    expect(cleanupReceiptStore.saveCalls, 1);
    expect(cleanupReceiptStore.clearCalls, 1);
    expect(await cleanupReceiptStore.read(), isNull);
  });

  test('静默 refresh 网络失败时保留登录态，避免误登出', () async {
    final store = _MemoryAuthSessionStore.authenticated();
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) async {
            throw CloudException(
              type: CloudErrorType.network,
              message: 'offline',
              runtimeFailure: testRuntimeFailure(
                code: 'APP.NETWORK.offline',
                kind: RuntimeFailureKind.network,
                nature: RuntimeFailureNature.transient,
              ),
            );
          }),
        ),
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

  test('普通请求在 access token 到期前主动单飞 refresh', () async {
    final now = DateTime.now();
    final store = _MemoryAuthSessionStore(
      stored: _currentStoredSession(
        accessToken: _schedulingJwt(now.add(const Duration(seconds: 30))),
      ),
    );
    var refreshCalls = 0;
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) async {
            refreshCalls += 1;
            return const TokenRefreshGrant(
              accessToken: 'refreshed-access',
              refreshToken: 'rotated-refresh',
              sessionRememberTtlSeconds: 0,
            );
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final token = await container
        .read(authSessionControllerProvider.notifier)
        .accessTokenForRequest();

    expect(token, 'refreshed-access');
    expect(refreshCalls, 1);
    expect(store.stored.refreshToken, 'rotated-refresh');
  });

  test('并发 force refresh 也只旋转一次 refresh token', () async {
    final store = _MemoryAuthSessionStore(stored: _currentStoredSession());
    final refreshStarted = Completer<void>();
    final delayedResult = Completer<TokenRefreshGrant>();
    var refreshCalls = 0;
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) {
            refreshCalls += 1;
            if (!refreshStarted.isCompleted) {
              refreshStarted.complete();
            }
            return delayedResult.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    final first = notifier.refreshSessionIfNeeded(force: true);
    await refreshStarted.future;
    final second = notifier.refreshSessionIfNeeded(force: true);
    delayedResult.complete(
      const TokenRefreshGrant(
        accessToken: 'refreshed-access',
        refreshToken: 'rotated-refresh',
        sessionRememberTtlSeconds: 0,
      ),
    );

    expect(await Future.wait(<Future<bool>>[first, second]), <bool>[
      true,
      true,
    ]);
    expect(refreshCalls, 1);
  });

  test('首个等待者取消不会退休仍在执行的 refresh singleflight', () async {
    final store = _MemoryAuthSessionStore(stored: _currentStoredSession());
    final refreshStarted = Completer<void>();
    final delayedResult = Completer<TokenRefreshGrant>();
    final abortFirstWaiter = Completer<void>();
    var refreshCalls = 0;
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((command) {
            refreshCalls += 1;
            expect(command.refreshToken, 'refresh-token');
            if (!refreshStarted.isCompleted) {
              refreshStarted.complete();
            }
            return delayedResult.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    final first = notifier.refreshSessionIfNeeded(
      force: true,
      abortTrigger: abortFirstWaiter.future,
    );
    await refreshStarted.future;
    final second = notifier.refreshSessionIfNeeded(force: true);
    abortFirstWaiter.complete();
    expect(await first, isFalse);

    final third = notifier.refreshSessionIfNeeded(force: true);
    expect(refreshCalls, 1);
    delayedResult.complete(
      const TokenRefreshGrant(
        accessToken: 'refreshed-access',
        refreshToken: 'rotated-refresh',
        sessionRememberTtlSeconds: 0,
      ),
    );

    expect(await Future.wait(<Future<bool>>[second, third]), <bool>[
      true,
      true,
    ]);
    expect(refreshCalls, 1);
    expect(store.stored.refreshToken, 'rotated-refresh');
  });

  test('不可解析的旧 access token 不触发推测性 refresh', () async {
    final store = _MemoryAuthSessionStore(stored: _currentStoredSession());
    var refreshCalls = 0;
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) async {
            refreshCalls += 1;
            return const TokenRefreshGrant(
              accessToken: 'unused',
              refreshToken: 'unused',
              sessionRememberTtlSeconds: 0,
            );
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final token = await container
        .read(authSessionControllerProvider.notifier)
        .accessTokenForRequest();

    expect(token, 'access-token');
    expect(refreshCalls, 0);
  });

  test('操作取消只停止等待且会采纳同一会话迟到的 rotated token', () async {
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final store = _MemoryAuthSessionStore(
      stored: StoredAuthSession(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
        ownerId: 'owner-1',
        activePersonaId: 'sub-1',
        accountState: 'active',
        identityOrigin: 'phone',
        installId: 'install-id',
        lastRefreshAtEpochMs: nowMs,
        lastForegroundAuthCheckAtEpochMs: nowMs,
        manualLoggedOut: false,
        launchPromptDismissed: true,
      ),
    );
    final refreshStarted = Completer<void>();
    final delayedResult = Completer<TokenRefreshGrant>();
    final cancellation = Completer<void>();
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) {
            refreshStarted.complete();
            return delayedResult.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    final refresh = notifier.refreshSessionIfNeeded(
      force: true,
      abortTrigger: cancellation.future,
    );
    await refreshStarted.future;
    cancellation.complete();

    expect(await refresh, isFalse);
    expect(
      container.read(authSessionControllerProvider).accessToken,
      'old-access',
    );
    delayedResult.complete(
      const TokenRefreshGrant(
        accessToken: 'late-access',
        refreshToken: 'late-refresh',
        sessionRememberTtlSeconds: 0,
      ),
    );
    await Future<void>.delayed(Duration.zero);

    expect(
      container.read(authSessionControllerProvider).accessToken,
      'late-access',
    );
    expect(store.stored.refreshToken, 'late-refresh');
  });

  test('退出登录胜出时迟到的 refresh grant 不会复活旧会话', () async {
    final store = _MemoryAuthSessionStore(stored: _currentStoredSession());
    final refreshStarted = Completer<void>();
    final delayedResult = Completer<TokenRefreshGrant>();
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter((_) {
            refreshStarted.complete();
            return delayedResult.future;
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(authSessionControllerProvider);
    await Future<void>.delayed(const Duration(milliseconds: 10));
    final notifier = container.read(authSessionControllerProvider.notifier);
    final refresh = notifier.refreshSessionIfNeeded(force: true);
    await refreshStarted.future;
    await notifier.hardLogout();
    delayedResult.complete(
      const TokenRefreshGrant(
        accessToken: 'late-access',
        refreshToken: 'late-refresh',
        sessionRememberTtlSeconds: 0,
      ),
    );

    expect(await refresh, isFalse);
    final session = container.read(authSessionControllerProvider);
    expect(session.hasTrustedSession, isFalse);
    expect(session.accessToken, isEmpty);
    expect(session.refreshToken, isEmpty);
    expect(store.stored.refreshToken, isEmpty);
  });

  test(
    'softLogout 置 guest+manualLoggedOut，分槽保留 remembered credential 与摘要',
    () async {
      final nowMs = DateTime.now().millisecondsSinceEpoch;
      final store = _MemoryAuthSessionStore(
        stored: StoredAuthSession(
          accessToken: 'access-token',
          refreshToken: 'refresh-token',
          ownerId: 'owner-1',
          activePersonaId: 'sub-1',
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
          startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
          authSessionStoreProvider.overrideWithValue(store),
          accountSessionLifecycleCommandWriterProvider.overrideWithValue(
            _lifecycleWriter(
              (_) async => const TokenRefreshGrant(
                accessToken: 'unused-access',
                refreshToken: 'unused-refresh',
                sessionRememberTtlSeconds: 0,
              ),
            ),
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
      expect(stored.refreshToken, isEmpty);
      expect(stored.rememberedRefreshToken, 'refresh-token');
      expect(stored.quickLoginRefreshToken, 'refresh-token');
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
        activePersonaId: 'sub-1',
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
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(store),
        accountSessionLifecycleCommandWriterProvider.overrideWithValue(
          _lifecycleWriter(
            (_) async => const TokenRefreshGrant(
              accessToken: 'unused-access',
              refreshToken: 'unused-refresh',
              sessionRememberTtlSeconds: 0,
            ),
          ),
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

final class _OpenStartupAuthGate extends StartupAuthRestoreGateNotifier {
  @override
  bool build() => true;
}

final class _StubAccountSessionLifecycleWriter
    implements AccountSessionLifecycleCommandWriter {
  const _StubAccountSessionLifecycleWriter(this._refresh);

  final Future<TokenRefreshGrant> Function(RefreshTokenCommand command)
  _refresh;

  @override
  Future<TokenRefreshGrant> refreshToken(RefreshTokenCommand command) {
    return _refresh(command);
  }

  @override
  Future<LogoutAck> logout(LogoutCommand command) async {
    return const LogoutAck(revoked: true);
  }
}

final class _MemoryTerminalCleanupReceiptStore
    implements TerminalAccountCleanupReceiptStore {
  TerminalAccountCleanupReceipt? receipt;
  int saveCalls = 0;
  int clearCalls = 0;

  @override
  Future<TerminalAccountCleanupReceipt?> read() async => receipt;

  @override
  Future<void> save(TerminalAccountCleanupReceipt receipt) async {
    saveCalls += 1;
    this.receipt = receipt;
  }

  @override
  Future<void> clear() async {
    clearCalls += 1;
    receipt = null;
  }
}

final class _MemoryAuthSessionStore implements AuthSessionStore {
  _MemoryAuthSessionStore({required this.stored});

  factory _MemoryAuthSessionStore.authenticated() {
    return _MemoryAuthSessionStore(
      stored: const StoredAuthSession(
        accessToken: 'access-token',
        refreshToken: 'refresh-token',
        ownerId: 'owner-1',
        activePersonaId: 'sub-1',
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
  int clearSessionCalls = 0;

  @override
  Future<StoredAuthSession> read() async => stored;

  @override
  Future<void> saveLoginGrant(
    AuthSessionGrant result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshGrant(TokenRefreshGrant result) async {
    stored = StoredAuthSession(
      accessToken: result.accessToken,
      refreshToken: result.refreshToken,
      ownerId: stored.ownerId,
      activePersonaId: stored.activePersonaId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      lastRefreshAtEpochMs: DateTime.now().millisecondsSinceEpoch,
      lastForegroundAuthCheckAtEpochMs: DateTime.now().millisecondsSinceEpoch,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedLoginIdentifier: stored.rememberedLoginIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedNicknameCustomized: stored.rememberedNicknameCustomized,
      sessionRememberTtlSeconds: result.sessionRememberTtlSeconds,
      manualLoggedOut: false,
      launchPromptDismissed: false,
    );
  }

  @override
  Future<void> saveRefreshedAccountHint(
    AccountHintSnapshot? accountHint,
  ) async {}

  @override
  Future<void> updateActivePersona(String personaId) async {
    stored = StoredAuthSession(
      accessToken: stored.accessToken,
      refreshToken: stored.refreshToken,
      ownerId: stored.ownerId,
      activePersonaId: personaId,
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
    clearSessionCalls += 1;
    stored = StoredAuthSession(
      accessToken: '',
      refreshToken: '',
      ownerId: '',
      activePersonaId: '',
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
      refreshToken: '',
      ownerId: stored.ownerId,
      activePersonaId: stored.activePersonaId,
      accountState: stored.accountState,
      identityOrigin: stored.identityOrigin,
      installId: stored.installId,
      lastRefreshAtEpochMs: stored.lastRefreshAtEpochMs,
      lastForegroundAuthCheckAtEpochMs: stored.lastForegroundAuthCheckAtEpochMs,
      rememberedLoginMethod: stored.rememberedLoginMethod,
      rememberedLoginMaskedIdentifier: stored.rememberedLoginMaskedIdentifier,
      rememberedDisplayName: stored.rememberedDisplayName,
      rememberedAvatarUrl: stored.rememberedAvatarUrl,
      rememberedRefreshToken: stored.refreshToken,
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
      activePersonaId: stored.activePersonaId,
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
      activePersonaId: stored.activePersonaId,
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

StoredAuthSession _currentStoredSession({String accessToken = 'access-token'}) {
  final nowMs = DateTime.now().millisecondsSinceEpoch;
  return StoredAuthSession(
    accessToken: accessToken,
    refreshToken: 'refresh-token',
    ownerId: 'owner-1',
    activePersonaId: 'sub-1',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: nowMs,
    lastForegroundAuthCheckAtEpochMs: nowMs,
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );
}

String _schedulingJwt(DateTime expiry) {
  String encode(Object value) =>
      base64Url.encode(utf8.encode(jsonEncode(value))).replaceAll('=', '');
  return '${encode(<String, String>{'alg': 'none'})}.'
      '${encode(<String, int>{'exp': expiry.millisecondsSinceEpoch ~/ 1000})}.'
      'test-signature';
}

CloudException _accountSuspendedFailure() {
  return CloudException(
    type: CloudErrorType.forbidden,
    message: 'authoritative account restriction',
    code: UserErrorCode.accountSuspended.code,
    statusCode: 403,
    runtimeFailure: testRuntimeFailure(
      code: UserErrorCode.accountSuspended.code,
      kind: RuntimeFailureKind.auth,
    ),
  );
}
