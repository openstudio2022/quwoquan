import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/transport/links/app_public_content_links.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/presentation/my_qr_card.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/presentation/my_qr_code_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/user_service/persona_management/persona/contact_profile_queries.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-004

const _qrCard = ProfileQrCardData(
  publicProfileUrl: 'https://quwoquan.com/u/current',
  qrPayload: 'https://quwoquan.com/u/current?qr=fixture',
  qrTokenId: 'fixture-qr',
  avatarUrl: '',
  displayName: '当前用户',
  region: '杭州',
  shareText: 'https://quwoquan.com/u/current?qr=fixture',
);

const _untrustedQrCard = ProfileQrCardData(
  publicProfileUrl: 'https://evil.example/u/current',
  qrPayload: 'https://evil.example/u/current?qr=fixture',
  qrTokenId: 'fixture-qr',
  avatarUrl: '',
  displayName: '当前用户',
  region: '杭州',
  shareText: 'https://evil.example/u/current?qr=fixture',
);

final _publicLinks = PublicContentLinkBuilder(
  Uri.parse('https://quwoquan.com'),
);

Future<void> _ignoreQrShare(
  BuildContext context,
  ProfileQrShareRequest request,
) async {}

void main() {
  test('ProfileQrCard wire只接受自洽公开主页且拒绝过期卡片', () {
    final now = DateTime.utc(2026, 8, 9, 10);
    final card = ProfileQrCardData.fromWire(
      ProfileQrCardWire(
        publicProfileUrl: 'https://quwoquan.com/u/current',
        qrPayload: 'https://quwoquan.com/u/current?qr=fixture',
        qrTokenId: 'fixture-qr',
        displayName: '当前用户',
        expiresAt: now.add(const Duration(minutes: 1)),
      ),
      now: now,
    );
    expect(card.publicProfileUrl, 'https://quwoquan.com/u/current');

    expect(
      () => ProfileQrCardData.fromWire(
        ProfileQrCardWire(
          publicProfileUrl: 'https://quwoquan.com/u/other',
          qrPayload: 'https://quwoquan.com/u/current?qr=fixture',
          qrTokenId: 'fixture-qr',
          displayName: '当前用户',
        ),
        now: now,
      ),
      throwsStateError,
    );
    expect(
      () => ProfileQrCardData.fromWire(
        ProfileQrCardWire(
          publicProfileUrl: 'https://quwoquan.com/u/current',
          qrPayload: 'https://quwoquan.com/u/current?qr=fixture',
          qrTokenId: 'fixture-qr',
          displayName: '当前用户',
          expiresAt: now,
        ),
        now: now,
      ),
      throwsStateError,
    );
  });

  testWidgets('我的二维码页真实渲染名片与扫码主动作', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          publicContentLinkBuilderProvider.overrideWithValue(_publicLinks),
          profileEditQueryProvider.overrideWith(
            (ref, surface) => ContactProfileEditQueryFake(qrCard: _qrCard),
          ),
        ],
        child: const CupertinoApp(
          home: MyQrCodePage(sharePresenter: _ignoreQrShare),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(ProfileText.editProfileQrCardTitle), findsOneWidget);
    expect(find.text(_qrCard.displayName), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text(ProfileText.editProfileQrScanAction),
      200,
    );
    expect(find.text(ProfileText.editProfileQrScanAction), findsOneWidget);
  });

  testWidgets('运行包origin不匹配时不渲染服务端二维码', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          publicContentLinkBuilderProvider.overrideWithValue(_publicLinks),
          profileEditQueryProvider.overrideWith(
            (ref, surface) =>
                ContactProfileEditQueryFake(qrCard: _untrustedQrCard),
          ),
        ],
        child: const CupertinoApp(
          home: MyQrCodePage(sharePresenter: _ignoreQrShare),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(_untrustedQrCard.displayName), findsNothing);
  });

  testWidgets('展示后过期的二维码在分享前再次fail-closed', (tester) async {
    var now = DateTime.utc(2026, 8, 9, 10);
    var shareCalls = 0;
    final card = ProfileQrCardData(
      publicProfileUrl: 'https://quwoquan.com/u/current',
      qrPayload: 'https://quwoquan.com/u/current?qr=fixture',
      qrTokenId: 'fixture-qr',
      avatarUrl: '',
      displayName: '当前用户',
      region: '杭州',
      shareText: 'https://quwoquan.com/u/current?qr=fixture',
      expiresAt: now.add(const Duration(minutes: 1)),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          publicContentLinkBuilderProvider.overrideWithValue(_publicLinks),
          profileEditQueryProvider.overrideWith(
            (ref, surface) => ContactProfileEditQueryFake(qrCard: card),
          ),
        ],
        child: CupertinoApp(
          home: MyQrCodePage(
            clock: () => now,
            sharePresenter: (context, request) async {
              shareCalls += 1;
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(
      find.text(ProfileText.editProfileQrShareAction),
      200,
    );
    now = now.add(const Duration(minutes: 2));
    await tester.tap(find.text(ProfileText.editProfileQrShareAction));
    await tester.pumpAndSettle();

    expect(shareCalls, 0);
    expect(find.byType(CupertinoAlertDialog), findsOneWidget);
  });
}
