import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/my_qr_code_page.dart';
import '../../../../../support/fakes/contact_profile_queries.dart';

const _qrCard = ProfileQrCardData(
  publicProfileUrl: 'https://app.quwoquan.com/u/current',
  qrPayload: 'https://app.quwoquan.com/u/current?qr=fixture',
  qrTokenId: 'fixture-qr',
  styleVersion: 'v1',
  avatarUrl: '',
  displayName: '当前用户',
  region: '杭州',
  shareText: 'https://app.quwoquan.com/u/current?qr=fixture',
);

void main() {
  testWidgets('我的二维码页真实渲染名片与扫码主动作', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          profileEditQueryProvider.overrideWith(
            (ref, surface) => ContactProfileEditQueryFake(qrCard: _qrCard),
          ),
        ],
        child: const CupertinoApp(home: MyQrCodePage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.editProfileQrCardTitle), findsOneWidget);
    expect(find.text(_qrCard.displayName), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text(UITextConstants.editProfileQrScanAction),
      200,
    );
    expect(find.text(UITextConstants.editProfileQrScanAction), findsOneWidget);
  });
}
