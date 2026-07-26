import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/settings/pages/blocked_keywords_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'fixture_user_current',
    activeSubAccountId: 'fixture_user_current',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
  );
}

void main() {
  testWidgets('用户可查看、移除并新增屏蔽关键词', (tester) async {
    final facet = AlphaUserSettingsFacet(userId: 'fixture_user_current');
    await facet.updatePrivacySettings(
      UpdatePrivacySettingsCommand(blockedKeywords: <String>['广告']),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(
            _AuthenticatedSessionController.new,
          ),
          userSettingsQueryReaderProvider.overrideWithValue(facet),
          userSettingsCommandWriterProvider.overrideWithValue(facet),
        ],
        child: const CupertinoApp(home: BlockedKeywordsPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('广告'), findsOneWidget);
    await tester.tap(find.text(UITextConstants.blockedKeywordsRemove));
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.blockedKeywordsRemove).last);
    await tester.pumpAndSettle();
    expect(
      find.text(UITextConstants.blockedKeywordsEmptyTitle),
      findsOneWidget,
    );

    await tester.tap(find.text(UITextConstants.blockedKeywordsAdd));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(CupertinoTextField), '重复营销');
    await tester.tap(find.text(UITextConstants.done));
    await tester.pumpAndSettle();

    expect(find.text('重复营销'), findsOneWidget);
    expect((await facet.getPrivacySettings()).blockedKeywords, <String>[
      '重复营销',
    ]);
    await tester.pump(const Duration(seconds: 4));
  });
}
