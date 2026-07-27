import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/settings/pages/blocked_keywords_page.dart';
import 'package:quwoquan_app/ui/settings/pages/my_reports_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

class _AuthenticatedSessionController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'visual-access',
    refreshToken: 'visual-refresh',
    ownerId: 'visual-owner',
    activeSubAccountId: 'visual-persona',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'visual-install',
  );
}

void main() {
  setUp(() {
    TestWidgetsFlutterBinding.ensureInitialized();
  });

  testWidgets('我的举报浅色 iOS 页面视觉基线', (tester) async {
    await _setPhoneSurface(tester);
    // 固定为跨年历史日期，避免测试运行日跨过相对时间阈值后污染 golden。
    final now = DateTime.utc(2024, 7, 20);
    final query = AlphaContentReportQueryAdapter(<ContentMyReportItem>[
      ContentMyReportItem(
        id: 'report-1',
        targetType: ContentReportTargetType.post,
        targetId: 'post-1',
        reason: ContentReportReason.spam,
        description: '重复营销内容',
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
          isDarkProvider.overrideWithValue(false),
          myReportsContentReportQueryProvider.overrideWithValue(query),
        ],
        child: const CupertinoApp(
          theme: CupertinoThemeData(brightness: Brightness.light),
          home: RepaintBoundary(child: MyReportsPage()),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(MyReportsPage),
      matchesGoldenFile('goldens/my_reports_light.png'),
    );
  });

  testWidgets('屏蔽关键词深色 iOS 页面视觉基线', (tester) async {
    await _setPhoneSurface(tester);
    final settings = AlphaUserSettingsFacet(userId: 'visual-owner');
    await settings.updatePrivacySettings(
      UpdatePrivacySettingsCommand(blockedKeywords: <String>['重复营销', '剧透']),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authSessionControllerProvider.overrideWith(
            _AuthenticatedSessionController.new,
          ),
          isDarkProvider.overrideWithValue(true),
          userSettingsQueryReaderProvider.overrideWithValue(settings),
          userSettingsCommandWriterProvider.overrideWithValue(settings),
        ],
        child: const CupertinoApp(
          theme: CupertinoThemeData(brightness: Brightness.dark),
          home: RepaintBoundary(child: BlockedKeywordsPage()),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await expectLater(
      find.byType(BlockedKeywordsPage),
      matchesGoldenFile('goldens/blocked_keywords_dark.png'),
    );
  });
}

Future<void> _setPhoneSurface(WidgetTester tester) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = const Size(390, 844);
  addTearDown(tester.view.resetDevicePixelRatio);
  addTearDown(tester.view.resetPhysicalSize);
}
