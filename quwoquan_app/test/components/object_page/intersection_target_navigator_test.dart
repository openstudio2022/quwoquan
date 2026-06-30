import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';

void main() {
  group(
    'IntersectionTargetNavigator.resolvePath（云侧 routeId 闭集 → codegen 路由）',
    () {
      test('routeId 闭集映射到对应 codegen 路由', () {
        expect(
          IntersectionTargetNavigator.resolvePath(
            IntersectionTarget(objectId: 'u1', routeId: 'userProfile'),
          ),
          contains('u1'),
        );
        expect(
          IntersectionTargetNavigator.resolvePath(
            IntersectionTarget(objectId: 'c1', routeId: 'circleDetail'),
          ),
          contains('c1'),
        );
        expect(
          IntersectionTargetNavigator.resolvePath(
            IntersectionTarget(objectId: 'h1', routeId: 'homepageDetail'),
          ),
          contains('h1'),
        );
      });

      test('myIntersections 维度下钻附加 sourceRef 过滤', () {
        final path = IntersectionTargetNavigator.resolvePath(
          IntersectionTarget(
            objectId: 'relationship',
            routeId: 'myIntersections',
          ),
          sourceRef: 'commonContact',
        );
        expect(path, contains('relationship'));
        expect(path, contains('commonContact'));
      });

      test('routeId 缺省 → 回退 objectKind 兜底映射', () {
        expect(
          IntersectionTargetNavigator.resolvePath(
            IntersectionTarget(objectId: 'u1', objectKind: 'person'),
          ),
          contains('u1'),
        );
      });

      test('target 缺省 / objectId 空 / 未知 kind → 不可路由（null，优雅降级）', () {
        expect(IntersectionTargetNavigator.resolvePath(null), isNull);
        expect(
          IntersectionTargetNavigator.resolvePath(
            IntersectionTarget(objectId: '  ', routeId: 'userProfile'),
          ),
          isNull,
        );
        expect(
          IntersectionTargetNavigator.resolvePath(
            IntersectionTarget(objectId: 'x', objectKind: 'alien'),
          ),
          isNull,
        );
      });

      test('新增 objectKind trip/meetup → routeId 反查正确，目标页未实现时优雅降级（契约占位）', () {
        // 交集行动深化：registry.objectKinds 已登记 trip/meetup，codegen objectKind→routeId
        // 闭集随之含 tripDetail/meetupDetail（端侧只读分发，不硬编码）。
        expect(intersectionRouteIdForObjectKind('trip'), 'tripDetail');
        expect(intersectionRouteIdForObjectKind('meetup'), 'meetupDetail');
        // 结伴/线下局详情页尚未实现：resolvePath 落入 default → null，端侧静默降级（不崩溃）。
        // 实现 tripDetail/meetupDetail 页后，需在 resolvePath switch 增补对应 case，
        // 并把下面两条断言改为 contains(objectId)，本测试即为该实现的提醒式契约。
        expect(
          IntersectionTargetNavigator.resolvePath(
            IntersectionTarget(objectId: 't1', objectKind: 'trip'),
          ),
          isNull,
        );
        expect(
          IntersectionTargetNavigator.resolvePath(
            IntersectionTarget(objectId: 'm1', objectKind: 'meetup'),
          ),
          isNull,
        );
      });
    },
  );

  group('IntersectionTargetNavigator.open（路由 + 埋点）', () {
    Widget hostWith(void Function(BuildContext) capture) {
      final router = GoRouter(
        initialLocation: '/',
        routes: <RouteBase>[
          GoRoute(
            path: '/',
            builder: (context, _) {
              capture(context);
              return const Text('HOME');
            },
          ),
          GoRoute(
            path: '/user/:username',
            builder: (_, state) =>
                Text('USER:${state.pathParameters['username']}'),
          ),
        ],
      );
      return MaterialApp.router(routerConfig: router);
    }

    testWidgets(
      '可路由 target → context.push 跳转并上报 onTrack（target + attribution）',
      (tester) async {
        IntersectionTarget? trackedTarget;
        IntersectionNavAttribution? trackedAttr;
        final navigator = IntersectionTargetNavigator(
          onTrack: (target, attribution) {
            trackedTarget = target;
            trackedAttr = attribution;
          },
        );

        late BuildContext homeContext;
        await tester.pumpWidget(hostWith((c) => homeContext = c));
        await tester.pumpAndSettle();

        final ok = navigator.open(
          homeContext,
          IntersectionTarget(
            objectId: 'u_lin',
            objectKind: 'person',
            routeId: 'userProfile',
          ),
          attribution: const IntersectionNavAttribution(
            dimension: 'relationship',
            sourceRef: 'commonContact',
          ),
        );
        await tester.pumpAndSettle();

        expect(ok, isTrue);
        expect(find.text('USER:u_lin'), findsOneWidget);
        expect(trackedTarget?.objectId, 'u_lin');
        expect(trackedAttr?.dimension, 'relationship');
        expect(trackedAttr?.sourceRef, 'commonContact');
      },
    );

    testWidgets('不可路由 target → 不跳转、不上报、返回 false', (tester) async {
      var tracked = 0;
      final navigator = IntersectionTargetNavigator(
        onTrack: (_, _) => tracked++,
      );

      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final ok = navigator.open(
        homeContext,
        IntersectionTarget(objectId: '', routeId: 'userProfile'),
        attribution: const IntersectionNavAttribution(),
      );
      await tester.pumpAndSettle();

      expect(ok, isFalse);
      expect(find.text('HOME'), findsOneWidget);
      expect(tracked, 0);
    });

    testWidgets('无 GoRouter 宿主 → 不抛错、不上报、返回 false', (tester) async {
      var tracked = 0;
      late BuildContext plainContext;
      final navigator = IntersectionTargetNavigator(
        onTrack: (_, _) => tracked++,
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) {
              plainContext = context;
              return const Text('PLAIN');
            },
          ),
        ),
      );
      await tester.pump();

      final ok = navigator.open(
        plainContext,
        IntersectionTarget(
          objectId: 'u_lin',
          objectKind: 'person',
          routeId: 'userProfile',
        ),
        attribution: const IntersectionNavAttribution(),
      );
      await tester.pump();

      expect(ok, isFalse);
      expect(find.text('PLAIN'), findsOneWidget);
      expect(tracked, 0);
    });
  });
}
