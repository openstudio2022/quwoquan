// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/notification-privacy-settings/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/settings-audit/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/appearance-accessibility-settings/spec.md#gwt-001
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/shell/settings/appearance_settings_models.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_calls_page.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_dark_mode_page.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_notifications_page.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_privacy_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  final sectionCases = <_SectionCase>[
    _SectionCase(
      name: '通知设置',
      page: const SettingsNotificationsPage(),
      switchLabel: SettingsText.settingsEnableMarketing,
      initialValue: false,
      refreshedValue: true,
    ),
    _SectionCase(
      name: '隐私设置',
      page: const SettingsPrivacyPage(),
      switchLabel: SettingsText.settingsAllowStrangerMessage,
      initialValue: true,
      refreshedValue: false,
    ),
    _SectionCase(
      name: '通话设置',
      page: const SettingsCallsPage(),
      switchLabel: SettingsText.settingsEnableCallVibration,
      initialValue: true,
      refreshedValue: false,
    ),
  ];

  for (final section in sectionCases) {
    testWidgets('${section.name}重入失败不回落旧快照，重试安装权威读回', (tester) async {
      final reader = _ScriptedSettingsQueryReader(failSettingsRound: 2);
      final visible = ValueNotifier<bool>(true);
      addTearDown(visible.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: <Override>[
            ...sealedCloudBoundaryOverrides(),
            userSettingsQueryReaderProvider.overrideWithValue(reader),
          ],
          child: CupertinoApp(
            home: ValueListenableBuilder<bool>(
              valueListenable: visible,
              builder: (context, isVisible, child) =>
                  isVisible ? section.page : const SizedBox.shrink(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(reader.settingsRound, 1);
      expect(_switchValue(tester, section.switchLabel), section.initialValue);

      visible.value = false;
      await tester.pump();
      visible.value = true;
      await tester.pumpAndSettle();

      expect(reader.settingsRound, 2);
      expect(find.byType(AppPageErrorState), findsOneWidget);
      expect(find.text(section.switchLabel), findsNothing);

      await _tapPrimaryRecovery(tester);
      await tester.pumpAndSettle();

      expect(reader.settingsRound, 3);
      expect(find.byType(AppPageErrorState), findsNothing);
      expect(_switchValue(tester, section.switchLabel), section.refreshedValue);
    });
  }

  testWidgets('外观初读失败不展示默认设置，显式重试后才展示Remote快照', (tester) async {
    final reader = _ScriptedSettingsQueryReader(failFirstAppearance: true);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ...sealedCloudBoundaryOverrides(),
          userSettingsQueryReaderProvider.overrideWithValue(reader),
        ],
        child: const CupertinoApp(home: SettingsDarkModePage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(reader.appearanceAttempts, 1);
    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.byType(SettingsInsetChoiceRow), findsNothing);

    await _tapPrimaryRecovery(tester);
    await tester.pumpAndSettle();

    expect(reader.appearanceAttempts, 2);
    expect(find.byType(AppPageErrorState), findsNothing);
    expect(
      tester
          .widget<SettingsInsetChoiceRow>(
            find.byKey(
              const ValueKey<AppearanceThemeMode>(AppearanceThemeMode.dark),
            ),
          )
          .isSelected,
      isTrue,
    );
  });

  testWidgets('外观页面重入强制Remote刷新并替换已确认快照', (tester) async {
    final reader = _ScriptedSettingsQueryReader();
    final visible = ValueNotifier<bool>(true);
    addTearDown(visible.dispose);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ...sealedCloudBoundaryOverrides(),
          userSettingsQueryReaderProvider.overrideWithValue(reader),
        ],
        child: CupertinoApp(
          home: ValueListenableBuilder<bool>(
            valueListenable: visible,
            builder: (context, isVisible, child) => isVisible
                ? const SettingsDarkModePage()
                : const SizedBox.shrink(),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(reader.appearanceAttempts, 1);
    expect(_switchValue(tester, SettingsText.settingsDarkModeSystem), isTrue);

    visible.value = false;
    await tester.pump();
    visible.value = true;
    await tester.pumpAndSettle();

    expect(reader.appearanceAttempts, 2);
    expect(_appearanceChoice(tester, AppearanceThemeMode.dark), isTrue);
  });
}

bool _switchValue(WidgetTester tester, String label) => tester
    .widget<CupertinoSwitch>(
      find.descendant(
        of: find.ancestor(
          of: find.text(label),
          matching: find.byType(SettingsInsetSwitchRow),
        ),
        matching: find.byType(CupertinoSwitch),
      ),
    )
    .value;

bool _appearanceChoice(WidgetTester tester, AppearanceThemeMode mode) => tester
    .widget<SettingsInsetChoiceRow>(
      find.byKey(ValueKey<AppearanceThemeMode>(mode)),
    )
    .isSelected;

Future<void> _tapPrimaryRecovery(WidgetTester tester) async {
  final state = tester.widget<AppPageErrorState>(
    find.byType(AppPageErrorState),
  );
  final action = state.semantic.primaryAction;
  expect(action, isNotNull);
  await tester.tap(find.text(action!.label));
}

final class _SectionCase {
  const _SectionCase({
    required this.name,
    required this.page,
    required this.switchLabel,
    required this.initialValue,
    required this.refreshedValue,
  });

  final String name;
  final Widget page;
  final String switchLabel;
  final bool initialValue;
  final bool refreshedValue;
}

final class _ScriptedSettingsQueryReader
    implements contracts.UserSettingsQueryReader {
  _ScriptedSettingsQueryReader({
    this.failSettingsRound,
    this.failFirstAppearance = false,
  });

  final int? failSettingsRound;
  final bool failFirstAppearance;
  int settingsRound = 0;
  int appearanceAttempts = 0;

  @override
  Future<contracts.NotificationSettingsView> getNotificationSettings() async {
    settingsRound += 1;
    _throwForSettingsRound();
    return contracts.NotificationSettingsView(
      userId: 'settings-owner',
      enablePush: true,
      enableMarketing: settingsRound >= 3,
      version: settingsRound,
      updatedAt: DateTime.utc(2026, 8, 9, 1, settingsRound),
    );
  }

  @override
  Future<contracts.PrivacySettingsView> getPrivacySettings() async {
    _throwForSettingsRound();
    return contracts.PrivacySettingsView(
      userId: 'settings-owner',
      allowStrangerMsg: settingsRound < 3,
      profileVisibility: contracts.ProfileVisibility.public,
      assistantEnabled: true,
      blockedKeywords: const <String>[],
      version: settingsRound,
      updatedAt: DateTime.utc(2026, 8, 9, 1, settingsRound),
    );
  }

  @override
  Future<contracts.CallSettingsView> getCallSettings() async {
    _throwForSettingsRound();
    return contracts.CallSettingsView(
      userId: 'settings-owner',
      defaultIncomingCallRingtoneId: 'official.default',
      allowCallerRingtoneOverride: true,
      enableCallVibration: settingsRound < 3,
      enableGroupCallRing: true,
      version: settingsRound,
      updatedAt: DateTime.utc(2026, 8, 9, 1, settingsRound),
    );
  }

  @override
  Future<contracts.AppearanceSettingsView> getAppearanceSettings() async {
    appearanceAttempts += 1;
    if (failFirstAppearance && appearanceAttempts == 1) {
      throw StateError('appearance Remote unavailable');
    }
    final isFirstSuccessfulAttempt = appearanceAttempts == 1;
    return contracts.AppearanceSettingsView(
      themeMode: isFirstSuccessfulAttempt
          ? contracts.ThemeModeSetting.system
          : contracts.ThemeModeSetting.dark,
      fontSizePreset: contracts.FontSizePreset.lg,
      source: contracts.AppearanceSource.ownerDefault,
      ownerDefaultThemeMode: isFirstSuccessfulAttempt
          ? contracts.ThemeModeSetting.system
          : contracts.ThemeModeSetting.dark,
      ownerDefaultFontSizePreset: contracts.FontSizePreset.lg,
      hasPersonaOverride: false,
      version: appearanceAttempts,
      updatedAt: DateTime.utc(2026, 8, 9, 2, appearanceAttempts),
    );
  }

  void _throwForSettingsRound() {
    if (settingsRound == failSettingsRound) {
      throw StateError('settings Remote unavailable');
    }
  }
}
