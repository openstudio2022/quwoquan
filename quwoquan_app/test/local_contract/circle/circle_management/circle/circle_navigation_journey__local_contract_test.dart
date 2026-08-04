import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';
import 'package:quwoquan_app/ui/circle/pages/home_circles_hub_page.dart';
import 'package:quwoquan_app/ui/circle/pages/circle_detail_page.dart';

import '../../../../support/circle/circle_management/circle/typed_circle_query_test_double.dart';

class _NoopCircleBehaviorFactWriter implements CircleBehaviorFactWriter {
  @override
  Future<void> append(AppendCircleBehaviorFactCommand command) async {}
}

Widget _scopedApp({CircleQueryReader? circleQuery}) {
  final alphaQueries = AlphaCircleQueryReader();
  final query = circleQuery ?? alphaQueries;
  final CircleDiscoveryFeedQueryReader discoveryQuery =
      query is CircleDiscoveryFeedQueryReader
      ? query as CircleDiscoveryFeedQueryReader
      : CircleDiscoveryFeedQueryTestDouble(
          (CircleDiscoveryFeedQuery query) => CircleDiscoveryFeedPageSlice(
            circles: const <Circle>[],
            items: const <CircleFeedItemView>[],
          ),
        );
  return ProviderScope(
    overrides: [
      circlesListQueryProvider.overrideWithValue(query),
      circleDetailQueryProvider.overrideWithValue(query),
      circleDetailFeedQueryProvider.overrideWithValue(query),
      circlesListDiscoveryFeedQueryProvider.overrideWithValue(discoveryQuery),
      // 游客态：对象行为信号守卫短路；页面遥测走 Mock 上报。
      resolvedOwnerUserIdProvider.overrideWithValue(''),
      circleDetailBehaviorFactWriterProvider.overrideWithValue(
        _NoopCircleBehaviorFactWriter(),
      ),
      behaviorRepositoryProvider.overrideWithValue(MockBehaviorRepository()),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/circles',
        routes: [
          GoRoute(
            path: '/circles',
            builder: (_, _) => const Scaffold(body: CirclesHubPage()),
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
            builder: (_, _) =>
                const Scaffold(body: Center(child: Text('Stats'))),
          ),
          GoRoute(
            path: '/works/browser/:workId',
            builder: (_, _) =>
                const Scaffold(body: Center(child: Text('Work Browser'))),
          ),
          GoRoute(
            path: '/chat/:id',
            builder: (_, _) =>
                const Scaffold(body: Center(child: Text('Chat'))),
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

      expect(find.byType(CirclesHubPage), findsOneWidget);
      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('旅程 A2：从列表页导航到详情页', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final router = GoRouter.of(tester.element(find.byType(CirclesHubPage)));
      router.push('/circle/fixture_circle_photo');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(CircleDetailPage), findsOneWidget);
    });
  });

  group('旅程错误路径', () {
    testWidgets('旅程 B1：Repository 异常时列表页降级', (tester) async {
      await tester.pumpWidget(_scopedApp(circleQuery: _ErrorCircleQuery()));
      await tester.pumpAndSettle();

      expect(find.byType(CirclesHubPage), findsOneWidget);
    });

    testWidgets('旅程 B2：加入不存在的圈子时页面不崩溃', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pumpAndSettle();

      final router = GoRouter.of(tester.element(find.byType(CirclesHubPage)));
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

      final router = GoRouter.of(tester.element(find.byType(CirclesHubPage)));

      router.push('/circle/fixture_circle_photo');
      await tester.pump(const Duration(milliseconds: 200));
      router.go('/circles');
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.byType(Scaffold), findsWidgets);
    });

    testWidgets('旅程 C2：空数据状态安全渲染', (tester) async {
      await tester.pumpWidget(_scopedApp(circleQuery: _EmptyCircleQuery()));
      await tester.pumpAndSettle();

      expect(find.byType(CirclesHubPage), findsOneWidget);
    });
  });
}

class _ErrorCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<CirclePageSlice> list(CircleListQuery query) async {
    throw Exception('Network error');
  }
}

class _EmptyCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<CirclePageSlice> list(CircleListQuery query) async =>
      CirclePageSlice(items: const <Circle>[]);

  @override
  Future<Circle> get(CircleDetailQuery query) async {
    return Future.error(Exception('Circle not found'));
  }
}
