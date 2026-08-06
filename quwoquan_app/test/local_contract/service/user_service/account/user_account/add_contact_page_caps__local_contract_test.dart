import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/presentation/add_contact_page.dart';

Future<void> _pumpAddContactPage(
  WidgetTester tester,
  PlatformCapabilities profile,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [platformCapabilitiesProvider.overrideWithValue(profile)],
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/add-contact',
          routes: [
            GoRoute(
              path: '/add-contact',
              builder: (_, _) => AddContactPage(),
            ),
          ],
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump();
}

void main() {
  group('AddContactPage 能力位降级（R-XP1/R-XP9 差异边界）', () {
    testWidgets('mobile：扫一扫 + 手机联系人入口均可见', (tester) async {
      await _pumpAddContactPage(tester, CapabilityProfile.mobile);

      expect(find.text(ProfileText.editProfileQrScanAction), findsOneWidget);
      expect(find.text(ContactText.addContactPhoneEntryTitle), findsOneWidget);
    });

    testWidgets('web：无系统通讯录，手机联系人入口隐藏、扫一扫保留', (tester) async {
      await _pumpAddContactPage(tester, CapabilityProfile.web);

      expect(find.text(ProfileText.editProfileQrScanAction), findsOneWidget);
      expect(find.text(ContactText.addContactPhoneEntryTitle), findsNothing);
    });

    testWidgets('ohos：能力位为 false 时同样隐藏手机联系人入口', (tester) async {
      await _pumpAddContactPage(tester, CapabilityProfile.ohos);

      expect(find.text(ContactText.addContactPhoneEntryTitle), findsNothing);
    });
  });
}
