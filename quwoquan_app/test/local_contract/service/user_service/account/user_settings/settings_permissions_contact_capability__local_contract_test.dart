import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/shell/settings/settings_permissions_page.dart';

void main() {
  testWidgets('Web 无通讯录能力时展示不可用且不保留对象权限占位', (tester) async {
    await _pump(tester, CapabilityProfile.web);

    expect(find.text(SettingsText.settingsContactsPermission), findsOneWidget);
    expect(
      find.text(SettingsText.settingsPermissionUnavailable),
      findsOneWidget,
    );
    expect(find.text(FoundationText.openSettings), findsNothing);
  });

  testWidgets('Mobile 有通讯录能力时提供系统设置动作', (tester) async {
    await _pump(tester, CapabilityProfile.mobile);

    expect(find.text(FoundationText.openSettings), findsOneWidget);
    expect(find.text(SettingsText.settingsPermissionUnavailable), findsNothing);
  });
}

Future<void> _pump(
  WidgetTester tester,
  PlatformCapabilities capabilities,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [platformCapabilitiesProvider.overrideWithValue(capabilities)],
      child: const CupertinoApp(home: SettingsPermissionsPage()),
    ),
  );
  await tester.pump();
}
