import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/settings/pages/my_reports_page.dart';
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
  testWidgets('举报人可查看自己举报的完整公开生命周期', (tester) async {
    final now = DateTime.utc(2026, 7, 20);
    final query = AlphaContentReportQueryAdapter(<ContentMyReportItem>[
      ContentMyReportItem(
        id: 'report-1',
        targetType: ContentReportTargetType.post,
        targetId: 'post-1',
        reason: ContentReportReason.spam,
        status: ContentReportStatus.reviewing,
        createdAt: now,
        updatedAt: now,
      ),
      ContentMyReportItem(
        id: 'report-2',
        targetType: ContentReportTargetType.user,
        targetId: 'user-2',
        reason: ContentReportReason.harassment,
        status: ContentReportStatus.dismissed,
        createdAt: now,
        updatedAt: now,
        resolvedAt: now,
      ),
    ]);

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(
            _AuthenticatedSessionController.new,
          ),
          myReportsContentReportQueryProvider.overrideWithValue(query),
        ],
        child: const CupertinoApp(home: MyReportsPage()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text(UITextConstants.myReportsTitle), findsOneWidget);
    expect(find.text(UITextConstants.reportStatusReviewing), findsOneWidget);
    expect(find.text(UITextConstants.reportStatusDismissed), findsOneWidget);
    expect(
      find.textContaining(UITextConstants.reportTargetPost),
      findsOneWidget,
    );
    expect(
      find.textContaining(UITextConstants.reportTargetUser),
      findsOneWidget,
    );
  });
}
