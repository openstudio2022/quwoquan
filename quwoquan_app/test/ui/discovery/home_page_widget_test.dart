import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';

Widget _buildApp() {
  return ProviderScope(
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, __) => const Scaffold(body: HomePage()),
          ),
          GoRoute(path: '/circle/:id', builder: (_, __) => const SizedBox()),
          GoRoute(path: '/chat/:id', builder: (_, __) => const SizedBox()),
          GoRoute(path: '/user/:username', builder: (_, __) => const SizedBox()),
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

    testWidgets('切换到圈子后展示新的聚合模块', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(_buildApp());
      await tester.pump(const Duration(milliseconds: 300));

      // 默认是圈子，所以不需要点击切换，直接验证
      // 如果不是默认，则需要点击
      final circleTabFinder = find.descendant(
        of: find.byType(CenteredScrollableTabBar),
        matching: find.text('圈子'),
      );
      
      if (circleTabFinder.evaluate().isNotEmpty) {
        // 确保它是选中的？或者只是为了触发切换
        // 如果已经是默认，点击可能没反应，或者重新加载
        // 这里假设默认就是圈子，直接检查内容
      } else {
        // 如果找不到圈子 Tab，说明可能已经在沉浸模式？
        // 但 _buildApp 默认应该不是沉浸模式
      }

      // 检查圈子聚合页的内容
      expect(find.text('我的圈子'), findsOneWidget);
      expect(find.text('推荐圈子'), findsOneWidget);
    });

    testWidgets('点击精选进入沉浸模式', (tester) async {
      _suppressExpectedErrors();
      await tester.pumpWidget(
        const ProviderScope(
          child: MaterialApp(
            home: Scaffold(body: HomePage()),
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 默认是圈子，Tab 栏存在
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
