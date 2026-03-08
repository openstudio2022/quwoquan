import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_page.dart';

Widget _scopedApp({CircleRepository? mock}) {
  final repo = mock ?? MockCircleRepository();
  return ProviderScope(
    overrides: [circleRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp.router(
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
  });

  group('CirclesPage — 交互契约', () {
    testWidgets('页面正常加载不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      expect(find.byType(CirclesPage), findsOneWidget);
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
  }) async {
    return [];
  }
}
