import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_category_tab_defaults.dart';
import 'package:quwoquan_app/design_system/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circles_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/typed_circle_query_test_double.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_contract_test_builders.dart';

const Duration _kCirclesPageSettleTimeout = Duration(seconds: 1);

/// 墙钟上界 1s：用有限次 [pump] 代替 [pumpAndSettle]，避免永不 settle 或与 fake clock 交织时长时间挂起。
Future<void> _circlesPumpSettled(WidgetTester tester) async {
  final deadline = DateTime.now().add(_kCirclesPageSettleTimeout);
  while (DateTime.now().isBefore(deadline)) {
    await tester.pump(const Duration(milliseconds: 16));
    if (!tester.binding.hasScheduledFrame) return;
  }
}

CircleDiscoveryFeedPageSlice _circlesPageFixture() {
  return CircleDiscoveryFeedPageSlice(
    circles: <Circle>[
      buildCircleContract(
        circleId: 'fixture-circle-campus',
        name: '校园同行',
        ownerId: 'owner-campus',
        category: 'campus',
        subCategory: '母校',
        memberCount: 12,
      ),
    ],
    items: const <CircleFeedItemView>[],
  );
}

Widget _scopedApp({
  CircleDiscoveryFeedQueryReader? discoveryFeedQuery,
  double textScaleFactor = 1.0,
}) {
  return ProviderScope(
    overrides: [
      resolvedOwnerUserIdProvider.overrideWithValue(''),
      circlesListDiscoveryFeedQueryProvider.overrideWithValue(
        discoveryFeedQuery ??
            CircleDiscoveryFeedQueryTestDouble((_) => _circlesPageFixture()),
      ),
    ],
    child: MaterialApp.router(
      builder: (context, child) {
        final mediaQuery = MediaQuery.of(context);
        return MediaQuery(
          data: mediaQuery.copyWith(
            textScaler: TextScaler.linear(textScaleFactor),
          ),
          child: child ?? const SizedBox.shrink(),
        );
      },
      routerConfig: GoRouter(
        initialLocation: '/circles',
        routes: [
          GoRoute(
            path: '/circles',
            // 名实一致：挂载路由真实入口 CirclesPage（CirclesHubPage 的薄别名），
            // 保证本套件真正覆盖 circles_page.dart 而非只测底层 hub。
            builder: (_, _) => const Scaffold(body: CirclesPage()),
          ),
          GoRoute(path: '/circle/:id', builder: (_, _) => const SizedBox()),
          GoRoute(
            path: '/works/browser/:workId',
            builder: (_, _) => const SizedBox(),
          ),
        ],
      ),
    ),
  );
}

void main() {
  group('CirclesPage — 渲染契约', () {
    testWidgets('正常渲染圈子列表页', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(CirclesPage), findsOneWidget);
    });

    testWidgets('Tab 导航栏存在', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();

      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('展示圈子搜索、小趣与实体主页入口', (tester) async {
      final cfg = CircleCategoryTabDefaults.remoteStyleFallback;
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await _circlesPumpSettled(tester);

      expect(find.text(CommunityText.circlesSearchHint), findsOneWidget);
      expect(find.byType(CenteredScrollableTabBar), findsOneWidget);
      expect(
        find.text(CommunityText.circlesEntitySectionTitle),
        findsOneWidget,
      );
      expect(
        find.text(CommunityText.circlesRecommendedTitle),
        findsOneWidget,
      );
      expect(find.byIcon(CupertinoIcons.search), findsAtLeastNWidgets(1));
      expect(find.byIcon(CupertinoIcons.sparkles), findsAtLeastNWidgets(1));
      expect(
        find.text(cfg['campus']?.subCategories.first ?? '母校'),
        findsOneWidget,
      );
      expect(find.text(DiscoveryText.homeTabCircles), findsNothing);
      expect(find.text(CommunityText.circlesDirectoryTitle), findsNothing);
    });

    testWidgets('展示五个固定业务垂类并隐藏频道管理入口', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await _circlesPumpSettled(tester);

      expect(
        find.byIcon(CupertinoIcons.line_horizontal_3_decrease),
        findsNothing,
      );
      for (final label in <String>['校园', '旅行', '摄影', '科技', '车之家']) {
        expect(find.text(label), findsOneWidget);
      }
      for (final removed in <String>['遇见', '人文', '生活', '运动', '美食']) {
        expect(find.text(removed), findsNothing);
      }
    });
  });

  group('CirclesPage — 交互契约', () {
    testWidgets('页面正常加载不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await _circlesPumpSettled(tester);

      expect(find.byType(CirclesPage), findsOneWidget);
    });

    testWidgets('窄屏大字号下保持自适应不溢出', (tester) async {
      tester.view.physicalSize = const Size(320, 690);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final capturedErrors = <FlutterErrorDetails>[];
      final originalOnError = FlutterError.onError;
      FlutterError.onError = (details) {
        capturedErrors.add(details);
      };
      try {
        await tester.pumpWidget(_scopedApp(textScaleFactor: 1.4));
        await _circlesPumpSettled(tester);
      } finally {
        FlutterError.onError = originalOnError;
      }

      final overflowErrors = capturedErrors
          .map((details) => details.exceptionAsString())
          .where((message) => message.contains('A RenderFlex overflowed'))
          .toList(growable: false);

      expect(overflowErrors, isEmpty);
    });
  });

  group('CirclesPage — 错误态渲染', () {
    testWidgets('Repository 返回空列表时安全渲染', (tester) async {
      await tester.pumpWidget(
        _scopedApp(
          discoveryFeedQuery: CircleDiscoveryFeedQueryTestDouble(
            (_) => CircleDiscoveryFeedPageSlice(
              circles: const <Circle>[],
              items: const <CircleFeedItemView>[],
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(CirclesPage), findsOneWidget);
    });
  });
}
