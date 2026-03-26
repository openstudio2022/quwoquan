import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_page.dart';

Widget _scopedApp({CircleRepository? mock, double textScaleFactor = 1.0}) {
  final repo = mock ?? MockCircleRepository();
  return ProviderScope(
    overrides: [circleRepositoryProvider.overrideWithValue(repo)],
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
            builder: (_, _) => const Scaffold(body: CirclesPage()),
          ),
          GoRoute(path: '/circle/:id', builder: (_, _) => const SizedBox()),
          GoRoute(path: '/article/:id', builder: (_, _) => const SizedBox()),
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

    testWidgets('展示圈子广场标题与左侧分类菜单', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      expect(find.text(UITextConstants.circlesDirectoryTitle), findsOneWidget);
      expect(find.text(UITextConstants.homeCirclesMy), findsOneWidget);
      expect(find.text('推荐'), findsOneWidget);
      expect(find.text('遇见'), findsOneWidget);
    });
  });

  group('CirclesPage — 交互契约', () {
    testWidgets('页面正常加载不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

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
        await tester.pumpAndSettle();
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
      await tester.pumpWidget(_scopedApp(mock: _EmptyCircleRepository()));
      await tester.pump();

      expect(find.byType(CirclesPage), findsOneWidget);
    });
  });
}

class _EmptyCircleRepository extends MockCircleRepository {
  @override
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
    String? subCategory,
  }) async {
    return [];
  }
}
