import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/settings/pages/settings_notifications_page.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock_identity.dart';

void main() {
  testWidgets('通知设置保存后重新进入仍读取对象投影', (tester) async {
    final settings = AlphaUserSettingsFacet();

    Widget app() => ProviderScope(
      overrides: [
        userSettingsQueryReaderProvider.overrideWithValue(settings),
        userSettingsCommandWriterProvider.overrideWithValue(settings),
      ],
      child: const CupertinoApp(home: SettingsNotificationsPage()),
    );

    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    final pushSwitch = find.descendant(
      of: find.ancestor(
        of: find.text(UITextConstants.settingsEnablePush),
        matching: find.byType(SettingsInsetSwitchRow),
      ),
      matching: find.byType(CupertinoSwitch),
    );
    expect(tester.widget<CupertinoSwitch>(pushSwitch).value, isTrue);

    await tester.tap(pushSwitch);
    await tester.pumpAndSettle();
    expect(tester.widget<CupertinoSwitch>(pushSwitch).value, isFalse);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    final reopenedSwitch = find.descendant(
      of: find.ancestor(
        of: find.text(UITextConstants.settingsEnablePush),
        matching: find.byType(SettingsInsetSwitchRow),
      ),
      matching: find.byType(CupertinoSwitch),
    );
    expect(tester.widget<CupertinoSwitch>(reopenedSwitch).value, isFalse);
  });
}
