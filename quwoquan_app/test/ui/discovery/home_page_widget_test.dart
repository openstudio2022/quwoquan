import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/circle/pages/home_circles_hub_page.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/ui/discovery/widgets/moment_social_feed.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';
import 'package:shared_preferences/shared_preferences.dart';

Widget _buildApp() {
  return ProviderScope(
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
            builder: (context, state) =>
                const Scaffold(body: HomePage(routeLocation: '/circles')),
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

    testWidgets('默认停留在关注信息流', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(MomentSocialFeed), findsOneWidget);
      expect(find.byType(CenteredScrollableTabBar), findsOneWidget);
    });

    testWidgets('点击圈子切换到首页内整合的圈子页', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pumpAndSettle();

      final circlesTabFinder = find.descendant(
        of: find.byType(CenteredScrollableTabBar),
        matching: find.text('圈子'),
      );
      await tester.tap(circlesTabFinder);
      await tester.pumpAndSettle();

      expect(find.byType(HomeCirclesHubPage), findsOneWidget);
    });

    testWidgets('点击精选进入沉浸模式', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(
        const ProviderScope(
          child: MaterialApp(home: Scaffold(body: HomePage())),
        ),
      );
      await tester.pumpAndSettle();

      // 默认是关注，Tab 栏存在
      expect(find.byType(CenteredScrollableTabBar), findsOneWidget);

      // 点击精选
      final featuredTabFinder = find.descendant(
        of: find.byType(CenteredScrollableTabBar),
        matching: find.text('精选'),
      );
      await tester.tap(featuredTabFinder);
      await tester.pumpAndSettle();

      // Tab 栏应该消失 (进入沉浸模式)
      expect(find.byType(CenteredScrollableTabBar), findsNothing);

      // WorksImmersiveViewer 应该存在
      expect(find.byType(WorksImmersiveViewer), findsOneWidget);
    });
  });
}
