import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/models/circle_detail_payload.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/circle/pages/circles_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';

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
          GoRoute(
            path: '/circle/:id',
            builder: (context, state) => Scaffold(
              body: CircleDetailPage(
                circleId: state.pathParameters['id'] ?? '',
                onBack: () => context.go('/circles'),
              ),
            ),
          ),
          GoRoute(
            path: '/circle/:id/stats',
            builder: (_, _) => const Scaffold(body: Center(child: Text('Stats'))),
          ),
          GoRoute(
            path: '/article/:id',
            builder: (_, _) => const Scaffold(body: Center(child: Text('Article'))),
          ),
          GoRoute(
            path: '/chat/:id',
            builder: (_, _) => const Scaffold(body: Center(child: Text('Chat'))),
          ),
        ],
      ),
    ),
  );
}

void main() {
  group('旅程正常路径', () {
    testWidgets('旅程 A1：圈子列表页正常加载', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      expect(find.byType(CirclesPage), findsOneWidget);
      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('旅程 A2：从列表页导航到详情页', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final router = GoRouter.of(tester.element(find.byType(CirclesPage)));
      router.push('/circle/circle_photo_01');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });
  });

  group('旅程错误路径', () {
    testWidgets('旅程 B1：Repository 异常时列表页降级', (tester) async {
      await tester.pumpWidget(_scopedApp(mock: _ErrorCircleRepository()));
      await tester.pumpAndSettle();

      expect(find.byType(CirclesPage), findsOneWidget);
    });

    testWidgets('旅程 B2：加入不存在的圈子时页面不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final router = GoRouter.of(tester.element(find.byType(CirclesPage)));
      router.push('/circle/nonexistent_circle_id');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });
  });

  group('旅程边界/幂等', () {
    testWidgets('旅程 C1：快速切换页面不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final router = GoRouter.of(tester.element(find.byType(CirclesPage)));

      router.push('/circle/circle_photo_01');
      await tester.pump(const Duration(milliseconds: 200));
      router.go('/circles');
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('旅程 C2：空数据状态安全渲染', (tester) async {
      await tester.pumpWidget(_scopedApp(mock: _EmptyCircleRepository()));
      await tester.pumpAndSettle();

      expect(find.byType(CirclesPage), findsOneWidget);
    });
  });
}

class _ErrorCircleRepository extends MockCircleRepository {
  @override
  Future<List<CircleDto>> listCircles({
    String? category,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
    String? subCategory,
  }) async {
    throw Exception('Network error');
  }
}

class _EmptyCircleRepository extends MockCircleRepository {
  @override
  Future<List<CircleDto>> listCircles({
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

  @override
  Future<CircleDetailPayload> getCircle(String circleId) async {
    return Future.error(Exception('Circle not found'));
  }
}
