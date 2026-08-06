import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/presentation/phone_contacts_page.dart';

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

    expect(find.text(ContactText.addContactPhoneEntryTitle), findsOneWidget);
    expect(find.text(ContactText.phoneContactsUnavailable), findsOneWidget);
    expect(find.text(ContactText.phoneContactsPermissionCta), findsNothing);
  });
}
