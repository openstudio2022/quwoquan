// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/providers/startup_auth_restore_gate_provider.dart';
import 'package:quwoquan_app/application/user/account/account_closure_local_data_purger.dart';
import 'package:quwoquan_app/application/user/account/account_closure_local_data_purger_provider.dart';
import 'package:quwoquan_app/core/auth/terminal_account_cleanup_receipt_store.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_consent_store.dart';
import 'package:quwoquan_app/components/comment_system/comment_draft_store.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/emoji/emoji_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/assistant_chat_store.dart';
import 'package:quwoquan_app/core/services/search_recent_history_store.dart';
import 'package:quwoquan_app/ui/content/entry/services/create_draft_local_storage.dart';
import 'package:quwoquan_app/ui/content/entry/services/post_publication_intent_local_storage.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_account_security_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_calls_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_notifications_page.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_privacy_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock_identity.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  Widget host(Widget page) {
    final settings = AlphaUserSettingsFacet();
    final credentials = AlphaCredentialBindingWriter();
    return ProviderScope(
      overrides: [
        userSettingsQueryReaderProvider.overrideWithValue(settings),
        userSettingsCommandWriterProvider.overrideWithValue(settings),
        credentialBindingQueryProvider.overrideWithValue(credentials),
        appCredentialBindingCommandWriterProvider.overrideWithValue(
          credentials,
        ),
      ],
      child: CupertinoApp(home: page),
    );
  }

  test('终态本地清理单面失败时仍启动其余隐私清理面', () async {
    final calls = <String>[];
    final purger = AccountClosureLocalDataPurger(
      clearBehaviorQueue: () {
        calls.add('behavior');
        throw StateError('queue cleanup failed');
      },
      clearTelemetryQueue: () async {
        calls.add('telemetry');
      },
      clearRebuildableUserData: () async {
        calls.add('cache');
      },
      purgePushAndIncomingCallState: () async {
        calls.add('push');
      },
      clearDraftsAndAccountPreferences: () async {
        calls.add('drafts');
      },
    );

    await expectLater(purger.purge(), throwsStateError);
    expect(
      calls,
      containsAll(<String>['behavior', 'telemetry', 'cache', 'push', 'drafts']),
    );
  });

  test('终态清理删除当前 actor 草稿与偏好但不误删其他 actor 草稿', () async {
    const actorA = 'user-terminal-a';
    const actorB = 'user-surviving-b';
    final preferences = await SharedPreferences.getInstance();
    final scopeA = CreateDraftLocalStorage.scopeKeyForUser(actorA);
    final scopeB = CreateDraftLocalStorage.scopeKeyForUser(actorB);
    await preferences.setString(
      CreateDraftLocalStorage.scopedIndexKey(scopeA),
      '[]',
    );
    await preferences.setString(
      CreateDraftLocalStorage.scopedIndexKey(scopeB),
      '[]',
    );
    await preferences.setString(
      CreateDraftLocalStorage.corruptSidelineKey(
        CreateDraftLocalStorage.scopedIndexKey(scopeA),
      ),
      'corrupt-a',
    );
    await preferences.setString(
      PostPublicationIntentLocalStorage.scopeKey(actorA),
      '[]',
    );
    await preferences.setString(
      PostPublicationIntentLocalStorage.scopeKey(actorB),
      '[]',
    );
    await CommentDraftStore.save(
      'post-a',
      actorScope: actorA,
      draft: const CommentDraft(content: '账号 A 未发评论'),
    );
    await CommentDraftStore.save(
      'post-b',
      actorScope: actorB,
      draft: const CommentDraft(content: '账号 B 未发评论'),
    );
    await AssistantConsentStore(
      actorScope: actorA,
    ).save(const <AssistantSkillConsent>[]);
    await AssistantConsentStore(
      actorScope: actorB,
    ).save(const <AssistantSkillConsent>[]);
    final emoji = EmojiRepository(preferences);
    await emoji.setLastReportDate('2026-07-24');
    AssistantChatStore.addUserMessage('账号 A 本地消息');

    final purger = AccountClosureLocalDataPurger(
      clearBehaviorQueue: () async {},
      clearTelemetryQueue: () async {},
      clearRebuildableUserData: () async {},
      purgePushAndIncomingCallState: () async {},
      clearDraftsAndAccountPreferences: () async {
        AssistantChatStore.clearForTerminalAccountClosure();
        await Future.wait<void>(<Future<void>>[
          CreateDraftLocalStorage.clearForTerminalAccountClosure(actorA),
          PostPublicationIntentLocalStorage.clearForTerminalAccountClosure(
            actorA,
          ),
          CommentDraftStore.clearForTerminalAccountClosure(actorA),
          AssistantConsentStore(
            actorScope: actorA,
          ).clearForTerminalAccountClosure(),
          emoji.clearForTerminalAccountClosure(),
        ]);
      },
    );

    await purger.purge();

    expect(
      preferences.containsKey(CreateDraftLocalStorage.scopedIndexKey(scopeA)),
      isFalse,
    );
    expect(
      preferences.containsKey(CreateDraftLocalStorage.scopedIndexKey(scopeB)),
      isTrue,
    );
    expect(
      preferences.containsKey(
        PostPublicationIntentLocalStorage.scopeKey(actorA),
      ),
      isFalse,
    );
    expect(
      preferences.containsKey(
        PostPublicationIntentLocalStorage.scopeKey(actorB),
      ),
      isTrue,
    );
    expect(await CommentDraftStore.load('post-a', actorScope: actorA), isNull);
    expect(
      (await CommentDraftStore.load('post-b', actorScope: actorB))?.content,
      '账号 B 未发评论',
    );
    expect(
      preferences.getKeys().where(
        (key) => key.startsWith('assistant_skill_consents:'),
      ),
      hasLength(1),
    );
    expect(AssistantChatStore.messages.value, isEmpty);
    expect(emoji.getLastReportDate(), isNull);
  });

  testWidgets('通知设置加载 typed 投影并可切换', (tester) async {
    await tester.pumpWidget(host(const SettingsNotificationsPage()));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.settingsEnablePush), findsOneWidget);
    expect(find.byType(CupertinoSwitch), findsNWidgets(2));
  });

  testWidgets('隐私设置展示消息、助手与可见范围', (tester) async {
    await tester.pumpWidget(host(const SettingsPrivacyPage()));
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.settingsAllowStrangerMessage),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.settingsProfileVisibilityPublic),
      findsOneWidget,
    );
  });

  testWidgets('通话设置展示铃声与三项响铃偏好', (tester) async {
    await tester.pumpWidget(host(const SettingsCallsPage()));
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.settingsCallRingtoneDefault),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.settingsEnableGroupCallRing),
      findsOneWidget,
    );
  });

  testWidgets('账号安全空凭证态来自 typed Slice', (tester) async {
    await tester.pumpWidget(host(const SettingsAccountSecurityPage()));
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.settingsCredentialEmpty), findsOneWidget);
    expect(
      find.text(UITextConstants.settingsCredentialBindPhone),
      findsOneWidget,
    );
  });

  testWidgets('账号安全页提供注销入口且确认对话完整说明删除语义（5.1.1(v)）', (tester) async {
    final lifecycle = _RecordingAccountLifecycleWriter();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          credentialBindingQueryProvider.overrideWithValue(
            AlphaCredentialBindingWriter(),
          ),
          accountLifecycleCommandWriterProvider.overrideWithValue(lifecycle),
        ],
        child: const CupertinoApp(home: SettingsAccountSecurityPage()),
      ),
    );
    await tester.pumpAndSettle();

    final closeEntry = find.text(UITextConstants.settingsCloseAccountEntry);
    await tester.scrollUntilVisible(closeEntry, 120);
    expect(closeEntry, findsOneWidget);

    await tester.tap(closeEntry);
    await tester.pumpAndSettle();

    // 确认对话必须包含不可恢复警告与数据删除时限说明，取消不得触发命令。
    expect(
      find.text(UITextConstants.settingsCloseAccountConfirmTitle),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.settingsCloseAccountConfirmMessage),
      findsOneWidget,
    );
    await tester.tap(find.text(UITextConstants.cancel));
    await tester.pumpAndSettle();
    expect(lifecycle.closeCalls, 0);
    expect(
      find.text(UITextConstants.settingsCloseAccountConfirmTitle),
      findsNothing,
    );
  });

  testWidgets('注销命令失败时保留当前会话并恢复可操作入口', (tester) async {
    final lifecycle = _RecordingAccountLifecycleWriter(
      error: StateError('close rejected'),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          credentialBindingQueryProvider.overrideWithValue(
            AlphaCredentialBindingWriter(),
          ),
          accountLifecycleCommandWriterProvider.overrideWithValue(lifecycle),
        ],
        child: const CupertinoApp(home: SettingsAccountSecurityPage()),
      ),
    );
    await tester.pumpAndSettle();

    final closeEntry = find.text(UITextConstants.settingsCloseAccountEntry);
    await tester.scrollUntilVisible(closeEntry, 120);
    await tester.tap(closeEntry);
    await tester.pumpAndSettle();
    await tester.tap(_closeAccountConfirmAction());
    await tester.pumpAndSettle();

    expect(lifecycle.closeCalls, 1);
    expect(find.byType(SettingsAccountSecurityPage), findsOneWidget);
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
    expect(find.byType(CupertinoAlertDialog), findsOneWidget);
    expect(find.text(UITextConstants.submitNotCompleted), findsOneWidget);
    expect(find.text(UITextConstants.operationFailedRetry), findsOneWidget);

    await tester.tap(find.text(UITextConstants.cancel));
    await tester.pumpAndSettle();
    expect(find.byType(CupertinoAlertDialog), findsNothing);

    await tester.tap(closeEntry);
    await tester.pumpAndSettle();
    expect(
      find.text(UITextConstants.settingsCloseAccountConfirmTitle),
      findsOneWidget,
    );
  });

  testWidgets('注销成功只提交一次命令、清除本地会话并回到首页游客态', (tester) async {
    final lifecycle = _RecordingAccountLifecycleWriter();
    final sessionStore = _TestAuthSessionStore();
    final purgeProbe = _ClosurePurgeProbe();
    final cleanupReceiptStore = _MemoryTerminalCleanupReceiptStore();
    await _seedRecentSearchCacheResidue();
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(sessionStore),
        credentialBindingQueryProvider.overrideWithValue(
          AlphaCredentialBindingWriter(),
        ),
        accountLifecycleCommandWriterProvider.overrideWithValue(lifecycle),
        accountClosureLocalDataPurgerProvider.overrideWithValue(
          purgeProbe.purger,
        ),
        terminalAccountCleanupReceiptStoreProvider.overrideWithValue(
          cleanupReceiptStore,
        ),
      ],
    );
    final router = _accountSecurityRouter();
    addTearDown(container.dispose);
    addTearDown(router.dispose);

    container.read(authSessionControllerProvider);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    final closeEntry = find.text(UITextConstants.settingsCloseAccountEntry);
    await tester.scrollUntilVisible(closeEntry, 120);
    await tester.tap(closeEntry);
    await tester.pumpAndSettle();
    await tester.tap(_closeAccountConfirmAction());
    await tester.pumpAndSettle();

    expect(lifecycle.closeCalls, 1);
    expect(sessionStore.clearCalls, 1);
    expect(sessionStore.lastManualLogout, isTrue);
    expect(purgeProbe.operationCalls, 5);
    expect(cleanupReceiptStore.saveCalls, 1);
    expect(cleanupReceiptStore.clearCalls, 1);
    expect(await cleanupReceiptStore.read(), isNull);
    expect(await _recentSearchResidualKeys(), isEmpty);
    expect(
      container.read(authSessionControllerProvider).status,
      AuthSessionStatus.guest,
    );
    expect(router.routeInformationProvider.value.uri.path, AppRoutePaths.home);
    expect(find.text('home-safe-state'), findsOneWidget);
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('云端已注销而本地存储清理失败时仍 fail-closed 到游客安全态', (tester) async {
    final lifecycle = _RecordingAccountLifecycleWriter();
    final sessionStore = _TestAuthSessionStore(failClear: true);
    final purgeProbe = _ClosurePurgeProbe();
    final cleanupReceiptStore = _MemoryTerminalCleanupReceiptStore();
    await _seedRecentSearchCacheResidue();
    final container = ProviderContainer(
      overrides: [
        startupAuthRestoreGateProvider.overrideWith(_OpenStartupAuthGate.new),
        authSessionStoreProvider.overrideWithValue(sessionStore),
        credentialBindingQueryProvider.overrideWithValue(
          AlphaCredentialBindingWriter(),
        ),
        accountLifecycleCommandWriterProvider.overrideWithValue(lifecycle),
        accountClosureLocalDataPurgerProvider.overrideWithValue(
          purgeProbe.purger,
        ),
        terminalAccountCleanupReceiptStoreProvider.overrideWithValue(
          cleanupReceiptStore,
        ),
      ],
    );
    final router = _accountSecurityRouter();
    addTearDown(container.dispose);
    addTearDown(router.dispose);

    container.read(authSessionControllerProvider);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: CupertinoApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    final closeEntry = find.text(UITextConstants.settingsCloseAccountEntry);
    await tester.scrollUntilVisible(closeEntry, 120);
    await tester.tap(closeEntry);
    await tester.pumpAndSettle();
    await tester.tap(_closeAccountConfirmAction());
    await tester.pumpAndSettle();

    expect(lifecycle.closeCalls, 1);
    expect(sessionStore.clearCalls, 1);
    expect(purgeProbe.operationCalls, 5);
    expect(cleanupReceiptStore.saveCalls, 1);
    expect(cleanupReceiptStore.clearCalls, 1);
    expect(await _recentSearchResidualKeys(), isEmpty);
    final session = container.read(authSessionControllerProvider);
    expect(session.status, AuthSessionStatus.guest);
    expect(session.accessToken, isEmpty);
    expect(session.refreshToken, isEmpty);
    expect(router.routeInformationProvider.value.uri.path, AppRoutePaths.home);
    await tester.pump(const Duration(seconds: 4));
  });
}

final class _ClosurePurgeProbe {
  _ClosurePurgeProbe() {
    purger = AccountClosureLocalDataPurger(
      clearBehaviorQueue: _record,
      clearTelemetryQueue: _record,
      clearRebuildableUserData: () async {
        operationCalls += 1;
        await SearchRecentHistoryStore.clearAllNamespaces();
      },
      purgePushAndIncomingCallState: _record,
      clearDraftsAndAccountPreferences: _record,
    );
  }

  late final AccountClosureLocalDataPurger purger;
  int operationCalls = 0;

  Future<void> _record() async {
    operationCalls += 1;
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

Future<void> _seedRecentSearchCacheResidue() async {
  await SearchRecentHistoryStore(
    actorNamespace: 'owner-a::persona-a',
  ).save(const SearchRecentHistoryCacheSnapshot());
  await SearchRecentHistoryStore(
    actorNamespace: 'owner-b::persona-b',
  ).save(const SearchRecentHistoryCacheSnapshot());
  final preferences = await SharedPreferences.getInstance();
  await preferences.setString('global_search_recent_entries_v1', 'legacy');
}

Future<Set<String>> _recentSearchResidualKeys() async {
  final preferences = await SharedPreferences.getInstance();
  return preferences.getKeys().where((key) {
    return key == 'global_search_recent_entries_v1' ||
        key.startsWith(SearchRecentHistoryStore.storageKeyPrefix);
  }).toSet();
}

Finder _closeAccountConfirmAction() => find.descendant(
  of: find.byType(CupertinoAlertDialog),
  matching: find.text(UITextConstants.settingsCloseAccountConfirmAction),
);

GoRouter _accountSecurityRouter() => GoRouter(
  initialLocation: '/account-security-test',
  routes: <RouteBase>[
    GoRoute(
      path: '/account-security-test',
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
  _RecordingAccountLifecycleWriter({this.error});

  final Object? error;
  int closeCalls = 0;

  @override
  Future<CloseAccountResult> closeAccount(CloseAccountCommand command) async {
    closeCalls += 1;
    if (error != null) {
      throw error!;
    }
    return const CloseAccountResult(
      accountState: 'closed',
      closedAt: '2026-07-20T12:00:00Z',
      idempotentReplay: false,
    );
  }
}

final class _TestAuthSessionStore extends AuthSessionStore {
  _TestAuthSessionStore({this.failClear = false});

  final bool failClear;
  int clearCalls = 0;
  bool? lastManualLogout;
  StoredAuthSession stored = StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'owner-1',
    activeSubAccountId: 'sub-1',
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
    if (failClear) {
      throw StateError('local session cleanup failed');
    }
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
}
