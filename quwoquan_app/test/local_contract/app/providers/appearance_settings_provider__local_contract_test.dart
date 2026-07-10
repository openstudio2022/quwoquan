import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AppearanceSettingsController', () {
    test('ensureLoaded 会拉取快照并应用到运行时', () async {
      final container = ProviderContainer(
        overrides: [
          appearanceSettingsRepositoryProvider.overrideWithValue(
            _FakeAppearanceSettingsRepository(
              getHandler: () async => AppearanceSettingsSnapshot(
                themeMode: AppearanceThemeMode.dark,
                fontSizePreset: AppearanceFontSizePreset.lg,
                source: AppearanceSettingsSource.ownerDefault,
                ownerDefaultThemeMode: AppearanceThemeMode.dark,
                ownerDefaultFontSizePreset: AppearanceFontSizePreset.lg,
                hasSubAccountOverride: false,
                version: 3,
                updatedAt: DateTime.utc(2026, 3, 12, 8),
              ),
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      await container
          .read(appearanceSettingsControllerProvider.notifier)
          .ensureLoaded();

      final state = container.read(appearanceSettingsControllerProvider);
      expect(state.hasLoaded, isTrue);
      expect(state.snapshot.themeMode, AppearanceThemeMode.dark);
      expect(state.snapshot.fontSizePreset, AppearanceFontSizePreset.lg);
      expect(
        container.read(themeProvider).themeModeSetting,
        AppThemeModeSetting.dark,
      );
      expect(
        container.read(accessibilityProvider).fontSizePreset,
        AppFontSizePreset.lg,
      );
    });

    test('updateSettings 失败时保留本地乐观结果并标记待同步', () async {
      final repo = _FakeAppearanceSettingsRepository(
        getHandler: () async => AppearanceSettingsSnapshot(
          themeMode: AppearanceThemeMode.system,
          fontSizePreset: AppearanceFontSizePreset.md,
          source: AppearanceSettingsSource.ownerDefault,
          ownerDefaultThemeMode: AppearanceThemeMode.system,
          ownerDefaultFontSizePreset: AppearanceFontSizePreset.md,
          hasSubAccountOverride: false,
          version: 1,
          updatedAt: DateTime.utc(2026, 3, 12, 8),
        ),
        updateHandler: (_) async => throw Exception('offline'),
      );
      final container = ProviderContainer(
        overrides: [
          appearanceSettingsRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);

      await container
          .read(appearanceSettingsControllerProvider.notifier)
          .ensureLoaded();
      await container
          .read(appearanceSettingsControllerProvider.notifier)
          .updateSettings(
            themeMode: AppearanceThemeMode.dark,
            fontSizePreset: AppearanceFontSizePreset.xl,
            applyScope: AppearanceApplyScope.currentSubAccount,
          );

      final state = container.read(appearanceSettingsControllerProvider);
      expect(state.hasPendingSync, isTrue);
      expect(state.pendingMutation, isNotNull);
      expect(state.snapshot.themeMode, AppearanceThemeMode.dark);
      expect(state.snapshot.fontSizePreset, AppearanceFontSizePreset.xl);
      expect(state.snapshot.source, AppearanceSettingsSource.subOverride);
      expect(
        container.read(themeProvider).themeModeSetting,
        AppThemeModeSetting.dark,
      );
      expect(
        container.read(accessibilityProvider).fontSizePreset,
        AppFontSizePreset.xl,
      );
    });

    test('syncPending 成功后会清空待同步并收敛到远端结果', () async {
      var updateAttempts = 0;
      final repo = _FakeAppearanceSettingsRepository(
        getHandler: () async => AppearanceSettingsSnapshot(
          themeMode: AppearanceThemeMode.system,
          fontSizePreset: AppearanceFontSizePreset.md,
          source: AppearanceSettingsSource.ownerDefault,
          ownerDefaultThemeMode: AppearanceThemeMode.system,
          ownerDefaultFontSizePreset: AppearanceFontSizePreset.md,
          hasSubAccountOverride: false,
          version: 1,
          updatedAt: DateTime.utc(2026, 3, 12, 8),
        ),
        updateHandler: (mutation) async {
          updateAttempts += 1;
          if (updateAttempts == 1) {
            throw Exception('offline');
          }
          return AppearanceSettingsSnapshot(
            themeMode: mutation.themeMode,
            fontSizePreset: mutation.fontSizePreset,
            source: AppearanceSettingsSource.subOverride,
            ownerDefaultThemeMode: AppearanceThemeMode.system,
            ownerDefaultFontSizePreset: AppearanceFontSizePreset.md,
            hasSubAccountOverride: true,
            version: 9,
            updatedAt: DateTime.utc(2026, 3, 12, 9),
          );
        },
      );
      final container = ProviderContainer(
        overrides: [
          appearanceSettingsRepositoryProvider.overrideWithValue(repo),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        appearanceSettingsControllerProvider.notifier,
      );
      await notifier.ensureLoaded();
      await notifier.updateSettings(
        themeMode: AppearanceThemeMode.dark,
        fontSizePreset: AppearanceFontSizePreset.lg,
        applyScope: AppearanceApplyScope.currentSubAccount,
      );
      expect(
        container.read(appearanceSettingsControllerProvider).hasPendingSync,
        isTrue,
      );

      await notifier.syncPending();

      final state = container.read(appearanceSettingsControllerProvider);
      expect(state.hasPendingSync, isFalse);
      expect(state.snapshot.version, 9);
      expect(state.snapshot.source, AppearanceSettingsSource.subOverride);
      expect(state.snapshot.themeMode, AppearanceThemeMode.dark);
      expect(state.snapshot.fontSizePreset, AppearanceFontSizePreset.lg);
    });
  });
}

class _FakeAppearanceSettingsRepository implements AppearanceSettingsRepository {
  _FakeAppearanceSettingsRepository({
    required this.getHandler,
    this.updateHandler,
  });

  final Future<AppearanceSettingsSnapshot> Function() getHandler;
  final Future<AppearanceSettingsSnapshot> Function(
    AppearanceSettingsMutation mutation,
  )? updateHandler;

  @override
  Future<AppearanceSettingsSnapshot> getAppearanceSettings() => getHandler();

  @override
  Future<AppearanceSettingsSnapshot> updateAppearanceSettings(
    AppearanceSettingsMutation mutation,
  ) {
    return updateHandler?.call(mutation) ??
        Future<AppearanceSettingsSnapshot>.value(
          AppearanceSettingsSnapshot(
            themeMode: mutation.themeMode,
            fontSizePreset: mutation.fontSizePreset,
            source: mutation.applyScope == AppearanceApplyScope.currentSubAccount
                ? AppearanceSettingsSource.subOverride
                : AppearanceSettingsSource.ownerDefault,
            ownerDefaultThemeMode: mutation.applyScope ==
                    AppearanceApplyScope.currentSubAccount
                ? AppearanceThemeMode.system
                : mutation.themeMode,
            ownerDefaultFontSizePreset: mutation.applyScope ==
                    AppearanceApplyScope.currentSubAccount
                ? AppearanceFontSizePreset.md
                : mutation.fontSizePreset,
            hasSubAccountOverride:
                mutation.applyScope == AppearanceApplyScope.currentSubAccount,
            version: 2,
            updatedAt: DateTime.utc(2026, 3, 12, 9),
          ),
        );
  }
}
