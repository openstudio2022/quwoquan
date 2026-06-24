import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/ui/user/pages/scan_contact_qr_page.dart';

Future<void> _pumpScanPageWithoutCamera(WidgetTester tester) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        platformCapabilitiesProvider.overrideWithValue(
          CapabilityProfile.mobile.copyWith(camera: false),
        ),
      ],
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/add-contact/scan',
          routes: [
            GoRoute(
              path: '/add-contact/scan',
              builder: (_, _) => const ScanContactQrPage(),
            ),
          ],
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('无相机能力时使用自有 iOS 错误态，不暴露 mobile_scanner 默认英文文案', (tester) async {
    await _pumpScanPageWithoutCamera(tester);

    expect(
      find.text(UITextConstants.scanQrCameraUnavailableTitle),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.scanQrCameraUnavailableBody),
      findsOneWidget,
    );
    expect(find.textContaining('Scanning is not supported'), findsNothing);
    expect(find.textContaining('No cameras available'), findsNothing);
  });
}
