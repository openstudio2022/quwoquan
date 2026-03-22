import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/navigation/home_primary_tab_strip.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_hub_page.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/discovery/widgets/moment_social_feed.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';
import 'package:shared_preferences/shared_preferences.dart';

Widget _buildApp() {
  return ProviderScope(
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (context, state) =>
                  const Scaffold(body: HomePage(routeLocation: '/')),
            ),
            GoRoute(
              path: '/circles',
              builder: (context, state) => const Scaffold(body: CirclesPage()),
            ),
            GoRoute(
              path: '/circle/:id',
              builder: (context, state) => const SizedBox(),
            ),
            GoRoute(
              path: '/chat/:id',
              builder: (context, state) => const SizedBox(),
            ),
            GoRoute(
              path: '/user/:username',
              builder: (context, state) => const SizedBox(),
            ),
          ],
        ),
      ),
    ),
  );
}

void _suppressExpectedErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (details) {
    final message = details.exceptionAsString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException') ||
        message.contains('overflowed')) {
      return;
    }
    original?.call(details);
  };
}

void _setPhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1179, 2556);
  tester.view.devicePixelRatio = 3.0;
}

void _setWideSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(2048, 2732);
  tester.view.devicePixelRatio = 2.0;
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  group('HomePage', () {
    testWidgets('展示 关注/精选/圈子 与搜索加号入口', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(HomePage), findsOneWidget);
      expect(find.text('关注'), findsWidgets);
      expect(find.text('精选'), findsWidgets);
      expect(find.text('圈子'), findsWidgets);
      expect(find.byIcon(CupertinoIcons.search), findsAtLeastNWidgets(1));
      expect(find.byIcon(CupertinoIcons.add), findsAtLeastNWidgets(1));
    });

    testWidgets('关注态右侧入口与内容卡更多按钮右缘对齐', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final addIcon = find.byIcon(CupertinoIcons.add).first;
      final moreIcon = find.byIcon(Icons.more_horiz_rounded).first;
      final page = find.byType(HomePage);
      final screenWidth = tester.getSize(page).width;
      final addRightInset = screenWidth - tester.getTopRight(addIcon).dx;
      final expectedInset = AppSpacing.topBarTrailingVisualInset(
        tester.element(page),
      );

      expect(
        tester.getTopRight(addIcon).dx,
        closeTo(tester.getTopRight(moreIcon).dx, 2.0),
      );
      expect(addRightInset, closeTo(expectedInset, 2.0));
    });

    testWidgets('圈子态右侧入口与频道管理按钮右缘对齐', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.circlesTabId),
        ),
      );
      await tester.pumpAndSettle();

      final addIcon = find.byIcon(CupertinoIcons.add).first;
      final channelIcon = find.byIcon(
        CupertinoIcons.line_horizontal_3_decrease,
      );

      expect(channelIcon, findsOneWidget);
      expect(
        tester.getTopRight(addIcon).dx,
        closeTo(tester.getTopRight(channelIcon).dx, 2.0),
      );
    });

    testWidgets('默认停留在关注信息流', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(MomentSocialFeed), findsOneWidget);
      expect(find.byType(HomePrimaryTabStrip), findsOneWidget);
    });

    testWidgets('关注流手机端首条 post 占满屏宽', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final cardFinder = find.byKey(
        const ValueKey<String>('moment-feed-card-0'),
      );
      final screenWidth =
          tester.view.physicalSize.width / tester.view.devicePixelRatio;

      expect(cardFinder, findsOneWidget);
      expect(tester.getSize(cardFinder).width, closeTo(screenWidth, 1.0));
      expect(
        find.descendant(
          of: cardFinder,
          matching: find.byIcon(CupertinoIcons.ellipsis_circle),
        ),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey<String>('moment-feed-more-0')),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: cardFinder,
          matching: find.byIcon(Icons.more_horiz_rounded),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: cardFinder,
          matching: find.byIcon(CupertinoIcons.arrowshape_turn_up_right),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: cardFinder,
          matching: find.byIcon(CupertinoIcons.arrow_2_squarepath),
        ),
        findsNothing,
      );
    });

    testWidgets('关注流宽屏下首条 post 收敛到最大宽度', (tester) async {
      _suppressExpectedErrors();
      _setWideSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final cardFinder = find.byKey(
        const ValueKey<String>('moment-feed-card-0'),
      );
      final screenWidth =
          tester.view.physicalSize.width / tester.view.devicePixelRatio;

      expect(cardFinder, findsOneWidget);
      expect(tester.getSize(cardFinder).width, lessThan(screenWidth));
      expect(tester.getSize(cardFinder).width, closeTo(720.0, 1.0));
    });

    testWidgets('关注流更多菜单不显示分享和查看原图', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(const ValueKey<String>('moment-feed-more-0')),
      );
      await tester.pumpAndSettle();

      final page = find.byType(HomePage);
      final panel = find.byKey(TestKeys.modalBottomSheetPanel);

      expect(find.byKey(TestKeys.modalBottomSheetPanel), findsOneWidget);
      expect(tester.getTopLeft(panel).dy, greaterThan(0));
      expect(
        tester.getBottomRight(panel).dy,
        closeTo(tester.getSize(page).height, 2.0),
      );
      expect(find.text('打赏'), findsOneWidget);
      expect(find.text('保存'), findsOneWidget);
      expect(find.text('私信'), findsOneWidget);
      expect(find.text('复制链接'), findsOneWidget);
      expect(find.text('字体设置'), findsOneWidget);
      expect(find.text('取消'), findsOneWidget);
      expect(find.text('分享'), findsNothing);
      expect(find.text('查看原图'), findsNothing);

      await tester.drag(find.byType(ListView).last, const Offset(-320, 0));
      await tester.pumpAndSettle();

      expect(find.text('功能反馈'), findsOneWidget);
    });

    testWidgets('全局搜索以全屏面板呈现', (tester) async {
      _suppressExpectedErrors();
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(CupertinoIcons.search).first);
      await tester.pumpAndSettle();

      final page = find.byType(HomePage);
      final searchPanel = find.byKey(TestKeys.fullscreenModalSurface);

      expect(searchPanel, findsOneWidget);
      expect(tester.getSize(searchPanel), equals(tester.getSize(page)));
    });

    testWidgets('点击圈子切换到首页内整合的圈子页', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.circlesTabId),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(CirclesHubPage), findsOneWidget);
    });

    testWidgets('点击精选进入沉浸模式且保留稳定主 tab', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(
        const ProviderScope(
          child: MaterialApp(home: Scaffold(body: HomePage())),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(HomePrimaryTabStrip), findsOneWidget);

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.featuredTabId),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(HomePrimaryTabStrip), findsOneWidget);
      expect(find.byType(WorksImmersiveViewer), findsOneWidget);
    });

    testWidgets('横滑关注内容可切到精选', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final firstCard = find.byKey(
        const ValueKey<String>('moment-feed-card-0'),
      );
      expect(firstCard, findsOneWidget);

      await tester.flingFrom(
        tester.getCenter(firstCard),
        const Offset(-320, 0),
        1400,
      );
      await tester.pumpAndSettle();

      expect(find.byType(WorksImmersiveViewer), findsOneWidget);
    });

    testWidgets('切到精选后主 tab 位置保持稳定', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final followingBefore = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.followingTabId),
        ),
      );
      final featuredBefore = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.featuredTabId),
        ),
      );
      final circlesBefore = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.circlesTabId),
        ),
      );

      await tester.tap(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.featuredTabId),
        ),
      );
      await tester.pumpAndSettle();

      final followingAfter = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.followingTabId),
        ),
      );
      final featuredAfter = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.featuredTabId),
        ),
      );
      final circlesAfter = tester.getCenter(
        find.byKey(
          HomePrimaryTabStrip.tabKey(HomePrimaryTabStrip.circlesTabId),
        ),
      );

      expect(followingAfter.dx, closeTo(followingBefore.dx, 0.1));
      expect(featuredAfter.dx, closeTo(featuredBefore.dx, 0.1));
      expect(circlesAfter.dx, closeTo(circlesBefore.dx, 0.1));
    });
  });
}
