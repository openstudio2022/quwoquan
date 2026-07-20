import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/user/contact_discovery_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_edit_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/add_contact_page.dart';
import '../../../../support/fakes/contact_profile_queries.dart';

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
  testWidgets('添加联系人主页真实承载搜索、扫码、通讯录与二维码入口', (tester) async {
    final router = GoRouter(
      initialLocation: '/add-contact',
      routes: <RouteBase>[
        GoRoute(
          path: '/add-contact',
          builder: (_, _) => const AddContactPage(),
        ),
        GoRoute(
          path: '/add-contact/search',
          builder: (_, _) => const Text('search-destination'),
        ),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          platformCapabilitiesProvider.overrideWithValue(
            CapabilityProfile.mobile,
          ),
          profileEditQueryProvider.overrideWith(
            (ref, surface) => ContactProfileEditQueryFake(qrCard: _qrCard),
          ),
          contactDiscoveryRepositoryProvider.overrideWith(
            (ref) => _EmptyContactDiscoveryRepository(),
          ),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.addContactSearchHubPlaceholder),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.editProfileQrScanAction), findsOneWidget);
    expect(
      find.text(UITextConstants.addContactPhoneEntryTitle),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.editProfileQrCardHeading), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey<String>('add-contact-search-entry')),
    );
    await tester.pumpAndSettle();
    expect(find.text('search-destination'), findsOneWidget);
  });
}

final class _EmptyContactDiscoveryRepository
    implements ContactDiscoveryRepository {
  @override
  Future<void> dismiss(String id) async {}

  @override
  Future<ContactDiscoveryResultView?> getLatest() async => null;

  @override
  Future<ContactDiscoveryResultView> initiate(List<String> hashedPhones) async {
    return ContactDiscoveryResultView.empty;
  }
}
