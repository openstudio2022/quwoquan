import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_page.dart';

class _AssistantRepo implements AssistantRepository {
  _AssistantRepo(this._granted);

  bool _granted;

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
  }) async =>
      const <AssistantUserTaskView>[];

  @override
  Future<List<AssistantUserMemoryView>> listAssistantMemories({
    int limit = 32,
  }) async =>
      const <AssistantUserMemoryView>[];

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = 64,
  }) async =>
      const <AssistantSkillCatalogItemView>[];
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
  });
}
