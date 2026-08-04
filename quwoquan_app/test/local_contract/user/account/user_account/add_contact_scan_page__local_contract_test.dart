import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/user/account/user_account/presentation/scan_contact_qr_page.dart';

void main() {
  testWidgets('扫码页真实呈现无相机降级并保留相册恢复动作', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile.copyWith(camera: false),
          ),
        ],
        child: const CupertinoApp(home: ScanContactQrPage()),
      ),
    );
    await tester.pump();

    expect(find.text(ContactText.scanQrCameraUnavailableTitle), findsOneWidget);
    expect(find.text(ContactText.scanQrCameraUnavailableBody), findsOneWidget);
    expect(find.text(ContactText.scanQrAlbum), findsOneWidget);
  });
}
