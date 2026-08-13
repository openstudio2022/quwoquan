// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/settings-audit/spec.md#gwt-001
//
// 铃声设置与官方铃声目录同源契约：
// 设置页可选项、持久化 ID 与 CallKit 呈现资源必须共用
// OfficialCallRingtoneCatalog 这一个真相源，防止页面硬编码 ID
// 偏离目录后铃声选择静默失效（选中 ID resolve 不到资源回退默认铃）。
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/official_call_ringtone_catalog.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/presentation/settings_calls_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/user_service/account/credential_binding/credential_binding_typed_double.dart';

void main() {
  Widget host({
    UserSettingsQueryReader? reader,
    UserSettingsCommandWriter? writer,
  }) {
    final settings = InMemoryUserSettingsFacet();
    return ProviderScope(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        userSettingsQueryReaderProvider.overrideWithValue(reader ?? settings),
        userSettingsCommandWriterProvider.overrideWithValue(
          writer ?? settings,
        ),
      ],
      child: const CupertinoApp(home: SettingsCallsPage()),
    );
  }

  test('官方铃声目录 ID 满足云端 official 命名空间契约且资源可解析', () {
    expect(OfficialCallRingtoneCatalog.items, isNotEmpty);
    expect(
      OfficialCallRingtoneCatalog.items
          .map((ringtone) => ringtone.id)
          .toSet()
          .length,
      OfficialCallRingtoneCatalog.items.length,
      reason: '目录内铃声 ID 不得重复',
    );
    for (final ringtone in OfficialCallRingtoneCatalog.items) {
      // 与云端 ParseOfficialRingtoneID 校验同语义：official. 前缀 + <=64。
      expect(ringtone.id, startsWith('official.'));
      expect(ringtone.id.length, lessThanOrEqualTo(64));
      expect(ringtone.id.trim(), ringtone.id);
      expect(OfficialCallRingtoneCatalog.contains(ringtone.id), isTrue);
      expect(
        OfficialCallRingtoneCatalog.resolveCallkitPath(ringtone.id),
        isNotEmpty,
      );
      expect(ringtone.label.trim(), isNotEmpty);
    }
    expect(
      OfficialCallRingtoneCatalog.contains(OfficialCallRingtoneCatalog.defaultId),
      isTrue,
    );
  });

  testWidgets('设置页铃声选项与官方铃声目录逐条同源', (tester) async {
    await tester.pumpWidget(host());
    await tester.pumpAndSettle();

    final rows = tester
        .widgetList<SettingsInsetChoiceRow>(
          find.byType(SettingsInsetChoiceRow),
        )
        .toList(growable: false);
    expect(
      rows,
      hasLength(OfficialCallRingtoneCatalog.items.length),
      reason: '铃声可选行必须与目录条目一一对应，禁止页面另造第二套 ID',
    );
    for (
      var index = 0;
      index < OfficialCallRingtoneCatalog.items.length;
      index++
    ) {
      expect(rows[index].label, OfficialCallRingtoneCatalog.items[index].label);
    }
  });

  testWidgets('点击任一铃声行提交目录内 ID 并可解析 CallKit 资源', (tester) async {
    final settings = InMemoryUserSettingsFacet();
    await tester.pumpWidget(host(reader: settings, writer: settings));
    await tester.pumpAndSettle();

    for (final ringtone in OfficialCallRingtoneCatalog.items) {
      await tester.tap(find.text(ringtone.label));
      await tester.pumpAndSettle();

      final saved = await settings.getCallSettings();
      expect(saved.defaultIncomingCallRingtoneId, ringtone.id);
      expect(
        OfficialCallRingtoneCatalog.contains(
          saved.defaultIncomingCallRingtoneId,
        ),
        isTrue,
        reason: '设置页保存的铃声 ID 必须能被来电呈现链路 resolve',
      );
      expect(
        OfficialCallRingtoneCatalog.resolveCallkitPath(
          saved.defaultIncomingCallRingtoneId,
        ),
        isNotEmpty,
      );
    }
  });

  testWidgets('未设置铃声时默认铃声行呈选中态', (tester) async {
    final settings = InMemoryUserSettingsFacet();
    await tester.pumpWidget(
      host(
        reader: _NullRingtoneReader(settings),
        writer: settings,
      ),
    );
    await tester.pumpAndSettle();

    final rows = tester
        .widgetList<SettingsInsetChoiceRow>(
          find.byType(SettingsInsetChoiceRow),
        )
        .toList(growable: false);
    for (var index = 0; index < rows.length; index++) {
      final isDefault =
          OfficialCallRingtoneCatalog.items[index].id ==
          OfficialCallRingtoneCatalog.defaultId;
      expect(rows[index].isSelected, isDefault);
    }
  });
}

/// 只改写「铃声未设置」这一个读面，其余委托共享 typed double。
final class _NullRingtoneReader implements UserSettingsQueryReader {
  _NullRingtoneReader(this._inner);

  final InMemoryUserSettingsFacet _inner;

  @override
  Future<CallSettingsView> getCallSettings() async {
    final base = await _inner.getCallSettings();
    return CallSettingsView(
      userId: base.userId,
      defaultIncomingCallRingtoneId: null,
      allowCallerRingtoneOverride: base.allowCallerRingtoneOverride,
      enableCallVibration: base.enableCallVibration,
      enableGroupCallRing: base.enableGroupCallRing,
      version: base.version,
      updatedAt: base.updatedAt,
    );
  }

  @override
  Future<NotificationSettingsView> getNotificationSettings() =>
      _inner.getNotificationSettings();

  @override
  Future<PrivacySettingsView> getPrivacySettings() =>
      _inner.getPrivacySettings();

  @override
  Future<AppearanceSettingsView> getAppearanceSettings() =>
      _inner.getAppearanceSettings();
}
