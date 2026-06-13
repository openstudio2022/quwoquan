import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_page.dart';
import 'package:quwoquan_app/ui/user/pages/login_page.dart';

class _AssistantRepo implements AssistantRepository {
  _AssistantRepo(this._granted);

  bool _granted;

  @override
  Future<AssistantPolicyView> getPolicySnapshot({
    String policyVersionHint = '',
  }) async => AssistantPolicyView(
    version: policyVersionHint.isEmpty ? 'test' : policyVersionHint,
    values: <String, dynamic>{
      'grantedScopes': _granted
          ? const <String>[kPersonalContentAccessSkillId]
          : const <String>[],
    },
  );

  @override
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  }) async => AssistantInteractionReportBatchAck(
    accepted: true,
    count: events.length,
    resource: 'interaction_event_batch',
  );

  @override
  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  }) async => AssistantScorecardReportBatchAck(
    accepted: true,
    count: scorecards.length,
    resource: 'scorecard_batch',
  );

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  }) async {
    _granted = true;
    return AssistantSkillConsent(
      skillId: skillId,
      grantedScope: grantedScope,
      granted: true,
      updatedAt: DateTime.utc(2026, 3, 12, 10),
    );
  }

  @override
  Future<List<AssistantSkillConsent>> listConsents() async {
    if (!_granted) {
      return const <AssistantSkillConsent>[];
    }
    return <AssistantSkillConsent>[
      AssistantSkillConsent(
        skillId: kPersonalContentAccessSkillId,
        grantedScope: kPersonalContentAccessSkillId,
        granted: true,
        updatedAt: DateTime.utc(2026, 3, 12, 9),
      ),
    ];
  }

  @override
  Future<void> revokeSkillConsent({required String skillId}) async {
    _granted = false;
  }

  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
    Map<String, dynamic>? contextSnapshot,
  }) async {
    return AssistantSearchResultView(
      queryEcho: query,
      searchIntensity: searchIntensity,
    );
  }

  @override
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = 32,
    String? status,
  }) async => const <AssistantUserTaskView>[];

  @override
  Future<List<AssistantUserMemoryView>> listAssistantMemories({
    int limit = 32,
  }) async => const <AssistantUserMemoryView>[];

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = 64,
  }) async => const <AssistantSkillCatalogItemView>[];

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SettingsPage 外观与字号', () {
    testWidgets('切换深色主题会更新全局运行时', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appearanceSettingsRepositoryProvider.overrideWithValue(
              MockAppearanceSettingsRepository(),
            ),
          ],
          child: const MaterialApp(home: SettingsPage()),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('外观与字号'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('深色'));
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(SettingsPage)),
      );
      expect(
        container.read(themeProvider).themeModeSetting,
        AppThemeModeSetting.dark,
      );
      expect(
        container.read(appearanceSettingsControllerProvider).snapshot.themeMode,
        AppearanceThemeMode.dark,
      );
    });

    testWidgets('关闭同步所有账号后仅写当前子账号覆盖', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appearanceSettingsRepositoryProvider.overrideWithValue(
              MockAppearanceSettingsRepository(),
            ),
          ],
          child: const MaterialApp(home: SettingsPage()),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('外观与字号'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('同步到所有账号'),
        200,
        scrollable: find.byType(Scrollable).last,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('同步到所有账号'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('特大'),
        -200,
        scrollable: find.byType(Scrollable).last,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('特大'));
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(SettingsPage)),
      );
      final state = container.read(appearanceSettingsControllerProvider);
      expect(state.snapshot.source, AppearanceSettingsSource.subOverride);
      expect(state.snapshot.hasSubAccountOverride, isTrue);
      expect(
        container.read(accessibilityProvider).fontSizePreset,
        AppFontSizePreset.xl,
      );
      expect(find.text('恢复继承 Owner 默认'), findsOneWidget);
    });

    testWidgets('私助读取创作内容行展示真实授权状态并支持关闭', (tester) async {
      final assistantRepo = _AssistantRepo(true);
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appearanceSettingsRepositoryProvider.overrideWithValue(
              MockAppearanceSettingsRepository(),
            ),
            assistantRepositoryProvider.overrideWithValue(assistantRepo),
          ],
          child: const MaterialApp(home: SettingsPage()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('私助读取创作内容'), findsOneWidget);
      expect(find.text('已允许'), findsOneWidget);

      await tester.tap(find.text('私助读取创作内容'));
      await tester.pumpAndSettle();
      expect(find.text('关闭'), findsOneWidget);

      await tester.tap(find.text('关闭'));
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
        tester.element(find.byType(SettingsPage)),
      );
      expect(container.read(personalContentAccessProvider).granted, isFalse);
      expect(find.text('未允许'), findsOneWidget);
    });

    testWidgets('设置页展示用户与分身入口', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appearanceSettingsRepositoryProvider.overrideWithValue(
              MockAppearanceSettingsRepository(),
            ),
          ],
          child: const MaterialApp(home: SettingsPage()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.personaSettingsEntry), findsOneWidget);
    });

    testWidgets('分身管理开关关闭时隐藏设置入口', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appearanceSettingsRepositoryProvider.overrideWithValue(
              MockAppearanceSettingsRepository(),
            ),
            personaManagementFeatureFlagProvider.overrideWith((ref) => false),
          ],
          child: const MaterialApp(home: SettingsPage()),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.personaSettingsEntry), findsNothing);
    });

    testWidgets('登录态展示账号安全与隐私商用收口区块', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appearanceSettingsRepositoryProvider.overrideWithValue(
              MockAppearanceSettingsRepository(),
            ),
            authSessionStoreProvider.overrideWithValue(
              const _AuthenticatedStore(),
            ),
          ],
          child: const MaterialApp(home: SettingsPage()),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(UITextConstants.accountCommercialSectionTitle),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.accountCommercialCredentials),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.accountCommercialDevices),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.accountCommercialDelete),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.accountCommercialDataRights),
        findsOneWidget,
      );
      expect(
        find.text(UITextConstants.accountCommercialDevicesBlocked),
        findsWidgets,
      );
    });

    testWidgets('游客态账号安全入口复用 settingsAccount 登录门', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appearanceSettingsRepositoryProvider.overrideWithValue(
              MockAppearanceSettingsRepository(),
            ),
            authSessionStoreProvider.overrideWithValue(const _GuestStore()),
          ],
          child: MaterialApp.router(
            routerConfig: GoRouter(
              initialLocation: AppRoutePaths.settings,
              routes: [
                GoRoute(
                  path: AppRoutePaths.settings,
                  builder: (context, state) => const SettingsPage(),
                ),
                GoRoute(
                  path: AppRoutePaths.loginPathTemplate,
                  builder: (context, state) => LoginPage(
                    reason: state.uri.queryParameters['reason'],
                    redirect: state.uri.queryParameters['redirect'],
                    dismissFallback: state
                        .uri
                        .queryParameters[loginDismissFallbackQueryParam],
                    allowGuestDismissPop: loginGuestDismissCanPopFromQuery(
                      state.uri.queryParameters[loginGuestDismissPopQueryParam],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.text(UITextConstants.accountCommercialLoginRequired),
        findsOneWidget,
      );
      await tester.tap(
        find.text(UITextConstants.accountCommercialLoginRequired),
      );
      await tester.pumpAndSettle();

      expect(find.text(AuthGateReason.settingsAccount.title), findsOneWidget);
    });
  });
}

class _GuestStore implements AuthSessionStore {
  const _GuestStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: '',
    refreshToken: '',
    ownerId: '',
    activeSubAccountId: '',
    accountState: '',
    identityOrigin: '',
    installId: 'install-id',
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );

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

class _AuthenticatedStore extends _GuestStore {
  const _AuthenticatedStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'owner-id',
    activeSubAccountId: 'sub-id',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );
}
