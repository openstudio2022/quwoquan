import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/cloud/runtime/generated/user/profile_qr_resolve_wire_dto.g.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/components/media/picker/image_pick_gateway.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/user/pages/scan_contact_qr_page.dart';
import 'package:quwoquan_app/ui/user/services/contact_qr_image_analyzer.dart';

Future<void> _pumpScanPage(
  WidgetTester tester, {
  PlatformCapabilities capabilities = CapabilityProfile.mobile,
  ImagePickGateway? imagePicker,
  ContactQrImageAnalyzer? imageAnalyzer,
  UserProfileRepository? userProfileRepository,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        platformCapabilitiesProvider.overrideWithValue(capabilities),
        if (imagePicker != null)
          imagePickGatewayProvider.overrideWithValue(imagePicker),
        if (imageAnalyzer != null)
          contactQrImageAnalyzerProvider.overrideWithValue(imageAnalyzer),
        if (userProfileRepository != null)
          userProfileRepositoryProvider.overrideWithValue(
            userProfileRepository,
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
            GoRoute(
              path: '/add-contact/confirm',
              builder: (_, state) => Text(
                'confirm:${state.uri.queryParameters['userId']}:'
                '${state.uri.queryParameters['handle']}:'
                '${state.uri.queryParameters['source']}',
              ),
            ),
          ],
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  tearDown(AppToast.dismiss);

  testWidgets('无相机能力时使用自有 iOS 错误态，不暴露 mobile_scanner 默认英文文案', (tester) async {
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
    );

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
    expect(find.text(UITextConstants.scanQrAlbum), findsOneWidget);
  });

  testWidgets('相机不可用但相册可用时，选择联系人二维码可解析到添加确认页', (tester) async {
    final analyzer = _FakeContactQrImageAnalyzer(
      raw: 'https://app.quwoquan.com/u/alice?qr=token_alice',
    );
    final repository = _ResolvingUserProfileRepository();

    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
      imagePicker: const _FakeImagePickGateway('/tmp/alice_qr.png'),
      imageAnalyzer: analyzer,
      userProfileRepository: repository,
    );

    await tester.tap(find.text(UITextConstants.scanQrAlbum));
    await tester.pumpAndSettle();

    expect(analyzer.lastPath, '/tmp/alice_qr.png');
    expect(repository.lastToken, 'token_alice');
    expect(repository.lastHandle, 'alice');
    expect(find.text('confirm:user_alice:alice:scan'), findsOneWidget);
  });

  testWidgets('从相册选择非联系人二维码时，明确提示提供联系人二维码', (tester) async {
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
      imagePicker: const _FakeImagePickGateway('/tmp/not_qr.png'),
      imageAnalyzer: const _FakeContactQrImageAnalyzer(raw: ''),
      userProfileRepository: _ResolvingUserProfileRepository(),
    );

    await tester.tap(find.text(UITextConstants.scanQrAlbum));
    await tester.pump();

    expect(find.text(UITextConstants.scanQrNoCodeFound), findsOneWidget);
    AppToast.dismiss();
    await tester.pump();
  });

  testWidgets('无相册能力时隐藏相册入口', (tester) async {
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.desktop.copyWith(camera: false),
    );

    expect(find.text(UITextConstants.scanQrAlbum), findsNothing);
  });
}

class _FakeImagePickGateway implements ImagePickGateway {
  const _FakeImagePickGateway(this.path);

  final String? path;

  @override
  Future<String?> pickImage(
    BuildContext context, {
    required ImagePickSource source,
    required String cameraRouteName,
    required String galleryRouteName,
  }) async {
    expect(source, ImagePickSource.photoLibrary);
    return path;
  }
}

class _FakeContactQrImageAnalyzer implements ContactQrImageAnalyzer {
  const _FakeContactQrImageAnalyzer({required this.raw});

  final String raw;
  static String? _lastPath;

  String? get lastPath => _lastPath;

  @override
  Future<String> analyzeImage({required String path}) async {
    _lastPath = path;
    return raw;
  }
}

class _ResolvingUserProfileRepository extends MockUserProfileRepository {
  String? lastToken;
  String? lastHandle;

  @override
  Future<ProfileQrResolveWireDto> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) async {
    lastToken = token;
    lastHandle = handle;
    return ProfileQrResolveWireDto(
      subAccountId: 'user_alice',
      userHandle: 'alice',
      publicProfileUrl: 'https://app.quwoquan.com/u/alice',
      scanStatus: 'accepted',
    );
  }
}
