import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_edit_query.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/image_pick_gateway.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/image_pick_source.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/transport/links/app_public_content_links.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/presentation/scan_contact_qr_page.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/contact_qr_image_analyzer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/user_service/account/user_account/user_account_profile_typed_double.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-004

final _publicLinks = PublicContentLinkBuilder(
  Uri.parse('https://quwoquan.com'),
);

Future<void> _pumpScanPage(
  WidgetTester tester, {
  PlatformCapabilities capabilities = CapabilityProfile.mobile,
  ImagePickGateway? imagePicker,
  ContactQrImageAnalyzer? imageAnalyzer,
  ProfileEditQuery? profileEditQuery,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        publicContentLinkBuilderProvider.overrideWithValue(_publicLinks),
        platformCapabilitiesProvider.overrideWithValue(capabilities),
        if (imagePicker != null)
          imagePickGatewayProvider.overrideWithValue(imagePicker),
        if (imageAnalyzer != null)
          contactQrImageAnalyzerProvider.overrideWithValue(imageAnalyzer),
        if (profileEditQuery != null)
          profileEditQueryProvider.overrideWith(
            (ref, surface) => profileEditQuery,
          ),
      ],
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/add-contact/scan',
          routes: [
            GoRoute(
              path: '/add-contact/scan',
              builder: (_, _) => ScanContactQrPage(),
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

Future<void> _pumpAsyncWork(WidgetTester tester) async {
  for (var frame = 0; frame < 8; frame += 1) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  tearDown(() {
    AppToast.dismiss();
  });

  testWidgets('无相机能力时使用自有 iOS 错误态，不暴露 mobile_scanner 默认英文文案', (tester) async {
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
    );

    expect(find.text(ContactText.scanQrCameraUnavailableTitle), findsOneWidget);
    expect(find.text(ContactText.scanQrCameraUnavailableBody), findsOneWidget);
    expect(find.textContaining('Scanning is not supported'), findsNothing);
    expect(find.textContaining('No cameras available'), findsNothing);
    expect(find.text(ContactText.scanQrAlbum), findsOneWidget);
  });

  testWidgets('相机不可用但相册可用时，选择联系人二维码可解析到添加确认页', (tester) async {
    final analyzer = _FakeContactQrImageAnalyzer(
      raw: 'https://quwoquan.com/u/alice?qr=token_alice',
    );
    final repository = _ResolvingUserProfileRepository();

    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
      imagePicker: const _FakeImagePickGateway('/tmp/alice_qr.png'),
      imageAnalyzer: analyzer,
      profileEditQuery: repository,
    );

    await tester.tap(find.text(ContactText.scanQrAlbum));
    await _pumpAsyncWork(tester);

    expect(analyzer.lastPath, '/tmp/alice_qr.png');
    expect(repository.lastToken, 'token_alice');
    expect(repository.lastHandle, 'alice');
    expect(find.text('confirm:user_alice:alice:scan'), findsOneWidget);
  });

  testWidgets('非规范 public payload 在 Remote 前拒绝', (tester) async {
    final repository = _ResolvingUserProfileRepository();
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
      imagePicker: const _FakeImagePickGateway('/tmp/untrusted_qr.png'),
      imageAnalyzer: const _FakeContactQrImageAnalyzer(
        raw: 'https://evil.example/u/alice?qr=token_alice',
      ),
      profileEditQuery: repository,
    );

    await tester.tap(find.text(ContactText.scanQrAlbum));
    await _pumpAsyncWork(tester);

    expect(repository.callCount, 0);
    expect(find.text(ContactText.scanQrInvalidCode), findsOneWidget);
    expect(find.textContaining('confirm:'), findsNothing);
    AppToast.dismiss();
    await tester.pump();
  });

  final invalidResolutions =
      <({String description, ProfileQrResolveWire resolution})>[
        (
          description: '非 accepted scanStatus',
          resolution: _resolution(scanStatus: 'rejected'),
        ),
        (description: '空 personaId', resolution: _resolution(personaId: '')),
        (
          description: '不一致 userHandle',
          resolution: _resolution(userHandle: 'mallory'),
        ),
        (
          description: '不一致 publicProfileUrl',
          resolution: _resolution(
            publicProfileUrl: 'https://quwoquan.com/u/mallory',
          ),
        ),
      ];
  for (final scenario in invalidResolutions) {
    testWidgets('Remote ${scenario.description} 时 fail-closed 且可重新尝试', (
      tester,
    ) async {
      final repository = _ResolvingUserProfileRepository(
        resolution: scenario.resolution,
      );
      await _pumpScanPage(
        tester,
        capabilities: CapabilityProfile.mobile.copyWith(camera: false),
        imagePicker: const _FakeImagePickGateway('/tmp/alice_qr.png'),
        imageAnalyzer: const _FakeContactQrImageAnalyzer(
          raw: 'https://quwoquan.com/u/alice?qr=token_alice',
        ),
        profileEditQuery: repository,
      );

      await tester.tap(find.text(ContactText.scanQrAlbum));
      await _pumpAsyncWork(tester);

      expect(repository.callCount, 1);
      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.textContaining('confirm:'), findsNothing);

      Navigator.of(tester.element(find.byType(CupertinoAlertDialog))).pop();
      await _pumpAsyncWork(tester);
      await tester.tap(find.text(ContactText.scanQrAlbum));
      await _pumpAsyncWork(tester);

      expect(repository.callCount, 2);
      expect(find.byType(CupertinoAlertDialog), findsOneWidget);
      expect(find.textContaining('confirm:'), findsNothing);
      Navigator.of(tester.element(find.byType(CupertinoAlertDialog))).pop();
      await _pumpAsyncWork(tester);
    });
  }

  testWidgets('canonical Remote failure 提供显式 retry 并在成功后唯一导航', (tester) async {
    final repository = _ResolvingUserProfileRepository(
      onResolve: (token, handle, callCount) async {
        if (callCount == 1) {
          throw StateError('canonical failure');
        }
        return _resolution();
      },
    );
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
      imagePicker: const _FakeImagePickGateway('/tmp/alice_qr.png'),
      imageAnalyzer: const _FakeContactQrImageAnalyzer(
        raw: 'https://quwoquan.com/u/alice?qr=token_alice',
      ),
      profileEditQuery: repository,
    );

    await tester.tap(find.text(ContactText.scanQrAlbum));
    await _pumpAsyncWork(tester);
    expect(find.byType(CupertinoAlertDialog), findsOneWidget);

    await tester.tap(find.byType(CupertinoDialogAction).last);
    await tester.pumpAndSettle();

    expect(repository.callCount, 2);
    expect(find.text('confirm:user_alice:alice:scan'), findsOneWidget);
  });

  testWidgets('同一进行中 attempt 忽略重复相册触发并只导航一次', (tester) async {
    final pending = Completer<ProfileQrResolveWire>();
    final repository = _ResolvingUserProfileRepository(
      onResolve: (_, _, _) => pending.future,
    );
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
      imagePicker: const _FakeImagePickGateway('/tmp/alice_qr.png'),
      imageAnalyzer: const _FakeContactQrImageAnalyzer(
        raw: 'https://quwoquan.com/u/alice?qr=token_alice',
      ),
      profileEditQuery: repository,
    );

    await tester.tap(find.text(ContactText.scanQrAlbum));
    await tester.pump();
    await tester.tap(find.text(ContactText.scanQrAlbum));
    await tester.pump();
    expect(repository.callCount, 1);

    pending.complete(_resolution());
    await tester.pumpAndSettle();

    expect(repository.callCount, 1);
    expect(find.text('confirm:user_alice:alice:scan'), findsOneWidget);
  });

  testWidgets('页面退出后的 late Remote completion 不再导航', (tester) async {
    final pending = Completer<ProfileQrResolveWire>();
    final repository = _ResolvingUserProfileRepository(
      onResolve: (_, _, _) => pending.future,
    );
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
      imagePicker: const _FakeImagePickGateway('/tmp/alice_qr.png'),
      imageAnalyzer: const _FakeContactQrImageAnalyzer(
        raw: 'https://quwoquan.com/u/alice?qr=token_alice',
      ),
      profileEditQuery: repository,
    );

    await tester.tap(find.text(ContactText.scanQrAlbum));
    await tester.pump();
    expect(repository.callCount, 1);

    await tester.pumpWidget(const MaterialApp(home: Text('replacement')));
    pending.complete(_resolution());
    await tester.pumpAndSettle();

    expect(find.text('replacement'), findsOneWidget);
    expect(find.textContaining('confirm:'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('从相册选择非联系人二维码时，明确提示提供联系人二维码', (tester) async {
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.mobile.copyWith(camera: false),
      imagePicker: const _FakeImagePickGateway('/tmp/not_qr.png'),
      imageAnalyzer: const _FakeContactQrImageAnalyzer(raw: ''),
      profileEditQuery: _ResolvingUserProfileRepository(),
    );

    await tester.tap(find.text(ContactText.scanQrAlbum));
    await tester.pump();

    expect(find.text(ContactText.scanQrNoCodeFound), findsOneWidget);
    AppToast.dismiss();
    await tester.pump();
  });

  testWidgets('无相册能力时隐藏相册入口', (tester) async {
    await _pumpScanPage(
      tester,
      capabilities: CapabilityProfile.desktop.copyWith(camera: false),
    );

    expect(find.text(ContactText.scanQrAlbum), findsNothing);
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
  _ResolvingUserProfileRepository({
    ProfileQrResolveWire? resolution,
    this.onResolve,
  }) : resolution = resolution ?? _resolution();

  final ProfileQrResolveWire resolution;
  final Future<ProfileQrResolveWire> Function(
    String token,
    String handle,
    int callCount,
  )?
  onResolve;
  String? lastToken;
  String? lastHandle;
  int callCount = 0;

  @override
  Future<ProfileQrResolveWire> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) async {
    callCount += 1;
    lastToken = token;
    lastHandle = handle;
    final handler = onResolve;
    return handler == null ? resolution : handler(token, handle, callCount);
  }
}

ProfileQrResolveWire _resolution({
  String personaId = 'user_alice',
  String userHandle = 'alice',
  String publicProfileUrl = 'https://quwoquan.com/u/alice',
  String scanStatus = 'accepted',
}) {
  return ProfileQrResolveWire(
    personaId: personaId,
    userHandle: userHandle,
    publicProfileUrl: publicProfileUrl,
    scanStatus: scanStatus,
  );
}
