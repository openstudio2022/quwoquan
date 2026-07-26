import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/phone_contacts_page.dart';

void main() {
  testWidgets('通讯录页真实呈现能力不可用终态且不请求系统权限', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          platformCapabilitiesProvider.overrideWithValue(CapabilityProfile.web),
        ],
        child: const CupertinoApp(home: PhoneContactsPage()),
      ),
    );
    await tester.pump();

    expect(
      find.text(UITextConstants.addContactPhoneEntryTitle),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.phoneContactsUnavailable), findsOneWidget);
    expect(find.text(UITextConstants.phoneContactsPermissionCta), findsNothing);
  });
}
