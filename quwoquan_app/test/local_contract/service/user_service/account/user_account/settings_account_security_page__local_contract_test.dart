// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/auth/terminal_account_cleanup_receipt_store.dart';
import 'package:quwoquan_app/runtime/di/account_closure_local_data_dependencies.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/state/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/account_closure_local_data_purger.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/presentation/settings_account_security_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/user_service/account/credential_binding/credential_binding_typed_double.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  for (final state in <AccountState>[
    AccountState.active,
    AccountState.suspended,
  ]) {
    testWidgets('typed ${state.wireName} 结果保留会话、页面与重试入口且不启动终态清理', (
      tester,
    ) async {
      final harness = await _AccountSecurityHarness.mount(
        tester,
        resultState: state,
      );
      addTearDown(harness.dispose);

      await _confirmAccountClosure(tester);

      expect(harness.lifecycle.closeCalls, 1);
      expect(harness.sessionStore.clearCalls, 0);
      expect(harness.purgeProbe.operationCalls, 0);
      expect(harness.cleanupReceiptStore.saveCalls, 0);
      expect(harness.cleanupReceiptStore.clearCalls, 0);
      expect(
        harness.container.read(authSessionControllerProvider).status,
        AuthSessionStatus.authenticated,
      );
      expect(
        harness.router.routeInformationProvider.value.uri.path,
        _accountSecurityPath,
      );
      expect(find.byType(SettingsAccountSecurityPage), findsOneWidget);
      expect(
        find.text(SettingsText.settingsCloseAccountDoneToast),
        findsNothing,
      );
      expect(find.text(ContentText.tryAgain), findsOneWidget);

      await tester.tap(find.text(ContentText.tryAgain));
      await tester.pumpAndSettle();

      expect(harness.lifecycle.closeCalls, 1);
      expect(
        find.text(SettingsText.settingsCloseAccountConfirmTitle),
        findsOneWidget,
      );
      expect(harness.sessionStore.clearCalls, 0);
      expect(harness.purgeProbe.operationCalls, 0);
      expect(harness.cleanupReceiptStore.saveCalls, 0);
    });
  }

  testWidgets('typed closed 结果到达后才写回执、清理本地终态并进入游客安全页', (tester) async {
    final harness = await _AccountSecurityHarness.mount(
      tester,
      resultState: AccountState.closed,
    );
    addTearDown(harness.dispose);

    await _confirmAccountClosure(tester);

    expect(harness.lifecycle.closeCalls, 1);
    expect(harness.sessionStore.clearCalls, 1);
    expect(harness.sessionStore.lastManualLogout, isTrue);
    expect(harness.purgeProbe.operationCalls, 5);
    expect(harness.cleanupReceiptStore.saveCalls, 1);
    expect(harness.cleanupReceiptStore.clearCalls, 1);
    expect(await harness.cleanupReceiptStore.read(), isNull);
    expect(
      harness.container.read(authSessionControllerProvider).status,
      AuthSessionStatus.guest,
    );
    expect(
      harness.router.routeInformationProvider.value.uri.path,
      AppRoutePaths.home,
    );
    expect(find.text('home-safe-state'), findsOneWidget);
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('回执持久化失败时不清凭据且重试只恢复同一终态清理', (tester) async {
    final harness = await _AccountSecurityHarness.mount(
      tester,
      resultState: AccountState.closed,
      failReceiptSave: true,
    );
    addTearDown(harness.dispose);

    await _confirmAccountClosure(tester);

    expect(harness.lifecycle.closeCalls, 1);
    expect(harness.cleanupReceiptStore.saveCalls, 1);
    expect(harness.sessionStore.clearCalls, 0);
    expect(harness.purgeProbe.operationCalls, 0);
    expect(
      harness.router.routeInformationProvider.value.uri.path,
      _accountSecurityPath,
    );
    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(SettingsText.settingsCloseAccountDoneToast), findsNothing);

    harness.cleanupReceiptStore.failSave = false;
    await tester.tap(find.text(ContentText.tryAgain));
    await tester.pumpAndSettle();

    expect(harness.lifecycle.closeCalls, 1);
    expect(harness.cleanupReceiptStore.saveCalls, 2);
    expect(harness.cleanupReceiptStore.clearCalls, 1);
    expect(harness.sessionStore.clearCalls, 1);
    expect(harness.purgeProbe.operationCalls, 5);
    expect(
      harness.router.routeInformationProvider.value.uri.path,
      AppRoutePaths.home,
    );
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('本地清理失败时保留回执、不报成功并由恢复器重试', (tester) async {
    final harness = await _AccountSecurityHarness.mount(
      tester,
      resultState: AccountState.closed,
      failPurge: true,
    );
    addTearDown(harness.dispose);

    await _confirmAccountClosure(tester);

    expect(harness.lifecycle.closeCalls, 1);
    expect(harness.sessionStore.clearCalls, 1);
    expect(harness.purgeProbe.operationCalls, greaterThanOrEqualTo(5));
    expect(await harness.cleanupReceiptStore.read(), isNotNull);
    expect(harness.cleanupReceiptStore.clearCalls, 0);
    expect(find.text(SettingsText.settingsCloseAccountDoneToast), findsNothing);
    expect(
      harness.router.routeInformationProvider.value.uri.path,
      AppRoutePaths.home,
    );

    harness.purgeProbe.fail = false;
    await harness.container.read(accountClosureLocalCleanupRecoveryProvider)();
    expect(await harness.cleanupReceiptStore.read(), isNull);
    expect(harness.cleanupReceiptStore.clearCalls, 1);
  });
}

const _accountSecurityPath = '/account-security-test';

Future<void> _confirmAccountClosure(WidgetTester tester) async {
  final closeEntry = find.text(SettingsText.settingsCloseAccountEntry);
  await tester.scrollUntilVisible(closeEntry, 120);
  await tester.tap(closeEntry);
  await tester.pumpAndSettle();
  await tester.tap(
    find.descendant(
      of: find.byType(CupertinoAlertDialog),
      matching: find.text(SettingsText.settingsCloseAccountConfirmAction),
    ),
  );
  await tester.pumpAndSettle();
}

final class _AccountSecurityHarness {
  _AccountSecurityHarness._({
    required this.container,
    required this.router,
    required this.lifecycle,
    required this.sessionStore,
    required this.purgeProbe,
    required this.cleanupReceiptStore,
  });

  final ProviderContainer container;
  final GoRouter router;
  final _RecordingAccountLifecycleWriter lifecycle;
  final _TestAuthSessionStore sessionStore;
  final _ClosurePurgeProbe purgeProbe;
  final _MemoryTerminalCleanupReceiptStore cleanupReceiptStore;

  static Future<_AccountSecurityHarness> mount(
    WidgetTester tester, {
    required AccountState resultState,
    bool failReceiptSave = false,
    bool failPurge = false,
  }) async {
    final lifecycle = _RecordingAccountLifecycleWriter(resultState);
    final sessionStore = _TestAuthSessionStore();
    final purgeProbe = _ClosurePurgeProbe()..fail = failPurge;
    final cleanupReceiptStore = _MemoryTerminalCleanupReceiptStore()
      ..failSave = failReceiptSave;
    final container = ProviderContainer(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(sessionStore),
        credentialBindingQueryProvider.overrideWithValue(
          InMemoryCredentialBindingWriter(),
        ),
        accountLifecycleCommandWriterProvider.overrideWithValue(lifecycle),
        accountClosureLocalDataPurgerProvider.overrideWithValue(
          purgeProbe.purger,
        ),
        accountClosureLocalDataPurgerForActorProvider.overrideWith((
          ref,
          actor,
        ) {
          return purgeProbe.purger;
        }),
        terminalAccountCleanupReceiptStoreProvider.overrideWithValue(
          cleanupReceiptStore,
        ),
      ],
    );
    final router = _accountSecurityRouter();
    container.read(authSessionControllerProvider);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();
    return _AccountSecurityHarness._(
      container: container,
      router: router,
      lifecycle: lifecycle,
      sessionStore: sessionStore,
      purgeProbe: purgeProbe,
      cleanupReceiptStore: cleanupReceiptStore,
    );
  }

  void dispose() {
    router.dispose();
    container.dispose();
  }
}

GoRouter _accountSecurityRouter() => GoRouter(
  initialLocation: _accountSecurityPath,
  routes: <RouteBase>[
    GoRoute(
      path: _accountSecurityPath,
      builder: (_, _) => const SettingsAccountSecurityPage(),
    ),
    GoRoute(
      path: AppRoutePaths.home,
      builder: (_, _) => const CupertinoPageScaffold(
        child: Center(child: Text('home-safe-state')),
      ),
    ),
  ],
);

final class _OpenStartupAuthGate extends StartupAuthRestoreGateNotifier {
  @override
  bool build() => true;
}

final class _RecordingAccountLifecycleWriter
    implements AccountLifecycleCommandWriter {
  _RecordingAccountLifecycleWriter(this.resultState);

  final AccountState resultState;
  int closeCalls = 0;

  @override
  Future<CloseAccountResultWire> closeAccount(
    CloseAccountCommand command,
  ) async {
    closeCalls += 1;
    return CloseAccountResultWire(
      accountState: resultState,
      closedAt: DateTime.utc(2026, 8, 8, 12),
      idempotentReplay: false,
    );
  }
}

final class _ClosurePurgeProbe {
  _ClosurePurgeProbe() {
    purger = AccountClosureLocalDataPurger(
      clearBehaviorQueue: _record,
      clearTelemetryQueue: _record,
      clearRebuildableUserData: _record,
      purgePushAndIncomingCallState: _record,
      clearDraftsAndAccountPreferences: _record,
    );
  }

  late final AccountClosureLocalDataPurger purger;
  int operationCalls = 0;
  bool fail = false;

  Future<void> _record() async {
    operationCalls += 1;
    if (fail) {
      throw StateError('terminal cleanup failure');
    }
  }
}

final class _MemoryTerminalCleanupReceiptStore
    implements TerminalAccountCleanupReceiptStore {
  TerminalAccountCleanupReceipt? receipt;
  int saveCalls = 0;
  int clearCalls = 0;
  bool failSave = false;

  @override
  Future<TerminalAccountCleanupReceipt?> read() async => receipt;

  @override
  Future<void> save(TerminalAccountCleanupReceipt receipt) async {
    saveCalls += 1;
    if (failSave) {
      throw StateError('terminal cleanup receipt persistence failure');
    }
    this.receipt = receipt;
  }

  @override
  Future<void> clear() async {
    clearCalls += 1;
    receipt = null;
  }
}

final class _TestAuthSessionStore extends AuthSessionStore {
  int clearCalls = 0;
  bool? lastManualLogout;
  StoredAuthSession stored = StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'owner-1',
    activePersonaId: 'persona-1',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: DateTime.now().millisecondsSinceEpoch,
    lastForegroundAuthCheckAtEpochMs: DateTime.now().millisecondsSinceEpoch,
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );

  @override
  Future<StoredAuthSession> read() async => stored;

  @override
  Future<void> clearSession({required bool manualLogout}) async {
    clearCalls += 1;
    lastManualLogout = manualLogout;
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
}
