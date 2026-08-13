/// 隐私设置读取的断连降级与恢复契约（typed fault 注入 → 整页错误态 → 恢复重试成功）。
///
/// 故障 profile 消费测试树共享闭集（disconnect），与环境边缘 harness 契约
/// 同源；断言遵循「故障时整页错误态且不展示默认设置、恢复后主动作重试
/// 取回权威快照」。
///
/// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_privacy_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/fault/typed_fault_injection.dart';

/// 组合共享 TypedFaultInjector 的设置读 double：故障态由测试切换。
final class _FaultInjectingSettingsReader
    implements contracts.UserSettingsQueryReader {
  _FaultInjectingSettingsReader(this.injector);

  final TypedFaultInjector injector;

  @override
  Future<contracts.NotificationSettingsView> getNotificationSettings() {
    return injector.guard(
      () async => contracts.NotificationSettingsView(
        userId: 'settings-owner',
        enablePush: true,
        enableMarketing: false,
        version: 1,
        updatedAt: DateTime.utc(2026, 8, 12, 1),
      ),
    );
  }

  @override
  Future<contracts.PrivacySettingsView> getPrivacySettings() {
    return injector.guard(
      () async => contracts.PrivacySettingsView(
        userId: 'settings-owner',
        allowStrangerMsg: true,
        profileVisibility: contracts.ProfileVisibility.public,
        assistantEnabled: true,
        blockedKeywords: const <String>[],
        version: 1,
        updatedAt: DateTime.utc(2026, 8, 12, 1),
      ),
    );
  }

  @override
  Future<contracts.CallSettingsView> getCallSettings() {
    return injector.guard(
      () async => contracts.CallSettingsView(
        userId: 'settings-owner',
        defaultIncomingCallRingtoneId: 'official.default',
        allowCallerRingtoneOverride: true,
        enableCallVibration: true,
        enableGroupCallRing: true,
        version: 1,
        updatedAt: DateTime.utc(2026, 8, 12, 1),
      ),
    );
  }

  @override
  Future<contracts.AppearanceSettingsView> getAppearanceSettings() {
    return injector.guard(
      () async => contracts.AppearanceSettingsView(
        themeMode: contracts.ThemeModeSetting.system,
        fontSizePreset: contracts.FontSizePreset.lg,
        source: contracts.AppearanceSource.ownerDefault,
        ownerDefaultThemeMode: contracts.ThemeModeSetting.system,
        ownerDefaultFontSizePreset: contracts.FontSizePreset.lg,
        hasPersonaOverride: false,
        version: 1,
        updatedAt: DateTime.utc(2026, 8, 12, 2),
      ),
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('断连故障下隐私设置整页错误态且不展示默认值，恢复后重试取回权威快照', (
    tester,
  ) async {
    final injector = TypedFaultInjector();
    injector.activate(TypedFaultProfile.disconnect);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ...sealedCloudBoundaryOverrides(),
          userSettingsQueryReaderProvider.overrideWithValue(
            _FaultInjectingSettingsReader(injector),
          ),
        ],
        child: const CupertinoApp(home: SettingsPrivacyPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.byType(AppPageErrorState),
      findsOneWidget,
      reason: '断连必须进入整页错误态',
    );
    expect(
      find.text(SettingsText.settingsAllowStrangerMessage),
      findsNothing,
      reason: '故障期间不得用默认设置伪装成功',
    );

    injector.deactivate();
    final errorState = tester.widget<AppPageErrorState>(
      find.byType(AppPageErrorState),
    );
    final action = errorState.semantic.primaryAction;
    expect(action, isNotNull, reason: '可恢复故障必须提供主恢复动作');
    expect(action!.type, UiErrorActionType.retry);
    await tester.tap(find.text(action.label));
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsNothing);
    expect(
      find.text(SettingsText.settingsAllowStrangerMessage),
      findsOneWidget,
      reason: '恢复后重试必须取回权威隐私快照',
    );
  });
}
