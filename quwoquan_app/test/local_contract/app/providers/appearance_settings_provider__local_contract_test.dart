import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/models/appearance_settings_models.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AppearanceSettingsController', () {
    test('ensureLoaded 会拉取快照并应用到运行时', () async {
      final facet = AlphaUserSettingsFacet(
        initialUpdatedAt: DateTime.utc(2026, 3, 12, 8),
      );
      await facet.updateAppearanceSettings(
        const contracts.UpdateAppearanceSettingsCommand(
          themeMode: contracts.ThemeModeSetting.dark,
          fontSizePreset: contracts.FontSizePreset.lg,
          applyScope: contracts.AppearanceApplyScope.allAccounts,
        ),
      );
      final container = ProviderContainer(
        overrides: [
          userSettingsQueryReaderProvider.overrideWithValue(facet),
          userSettingsCommandWriterProvider.overrideWithValue(facet),
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
      final facet = AlphaUserSettingsFacet(
        initialUpdatedAt: DateTime.utc(2026, 3, 12, 8),
      );
      final writer = _ControlledUserSettingsCommandWriter(
        delegate: facet,
        remainingAppearanceFailures: 1,
      );
      final container = ProviderContainer(
        overrides: [
          userSettingsQueryReaderProvider.overrideWithValue(facet),
          userSettingsCommandWriterProvider.overrideWithValue(writer),
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
      final facet = AlphaUserSettingsFacet(
        initialUpdatedAt: DateTime.utc(2026, 3, 12, 8),
        now: () => DateTime.utc(2026, 3, 12, 9),
      );
      final writer = _ControlledUserSettingsCommandWriter(
        delegate: facet,
        remainingAppearanceFailures: 1,
      );
      final container = ProviderContainer(
        overrides: [
          userSettingsQueryReaderProvider.overrideWithValue(facet),
          userSettingsCommandWriterProvider.overrideWithValue(writer),
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
      expect(state.snapshot.version, greaterThan(1));
      expect(state.snapshot.source, AppearanceSettingsSource.subOverride);
      expect(state.snapshot.themeMode, AppearanceThemeMode.dark);
      expect(state.snapshot.fontSizePreset, AppearanceFontSizePreset.lg);
      expect(writer.appearanceAttempts, 2);
    });
  });
}

final class _ControlledUserSettingsCommandWriter
    implements contracts.UserSettingsCommandWriter {
  _ControlledUserSettingsCommandWriter({
    required this.delegate,
    required this.remainingAppearanceFailures,
  });

  final contracts.UserSettingsCommandWriter delegate;
  int remainingAppearanceFailures;
  int appearanceAttempts = 0;

  @override
  Future<contracts.UserSettingsCommandResult> updateNotificationSettings(
    contracts.UpdateNotificationSettingsCommand command,
  ) {
    return delegate.updateNotificationSettings(command);
  }

  @override
  Future<contracts.UserSettingsCommandResult> updatePrivacySettings(
    contracts.UpdatePrivacySettingsCommand command,
  ) {
    return delegate.updatePrivacySettings(command);
  }

  @override
  Future<contracts.UserSettingsCommandResult> updateCallSettings(
    contracts.UpdateCallSettingsCommand command,
  ) {
    return delegate.updateCallSettings(command);
  }

  @override
  Future<contracts.AppearanceSettingsView> updateAppearanceSettings(
    contracts.UpdateAppearanceSettingsCommand command,
  ) {
    appearanceAttempts += 1;
    if (remainingAppearanceFailures > 0) {
      remainingAppearanceFailures -= 1;
      throw StateError('offline');
    }
    return delegate.updateAppearanceSettings(command);
  }
}
