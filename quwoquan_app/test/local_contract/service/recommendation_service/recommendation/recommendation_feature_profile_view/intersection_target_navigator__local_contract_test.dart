import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/generated/intersection_client_policy.g.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/gathering_create_navigation_request.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/runtime/di/global_surface_action_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group(
    'IntersectionTargetNavigator.resolvePath（云侧 routeId 闭集 → codegen 路由）',
    () {
      test('routeId 闭集映射到对应 codegen 路由', () {
        expect(
          IntersectionTargetNavigator.resolvePath(
            intersectionTargetFixture(objectId: 'u1', routeId: 'userProfile'),
          ),
          contains('u1'),
        );
        expect(
          IntersectionTargetNavigator.resolvePath(
            intersectionTargetFixture(objectId: 'c1', routeId: 'circleDetail'),
          ),
          contains('c1'),
        );
        expect(
          IntersectionTargetNavigator.resolvePath(
            intersectionTargetFixture(
              objectId: 'h1',
              routeId: 'homepageDetail',
            ),
          ),
          contains('h1'),
        );
      });

      test('myIntersections 维度下钻附加 sourceRef 过滤', () {
        final path = IntersectionTargetNavigator.resolvePath(
          intersectionTargetFixture(
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
            intersectionTargetFixture(objectId: 'u1', objectKind: 'person'),
          ),
          contains('u1'),
        );
      });

      test('target 缺省 / objectId 空 / 未知 kind → 不可路由（null，优雅降级）', () {
        expect(IntersectionTargetNavigator.resolvePath(null), isNull);
        expect(
          IntersectionTargetNavigator.resolvePath(
            intersectionTargetFixture(objectId: '  ', routeId: 'userProfile'),
          ),
          isNull,
        );
        expect(
          IntersectionTargetNavigator.resolvePath(
            intersectionTargetFixture(objectId: 'x', objectKind: 'alien'),
          ),
          isNull,
        );
      });

      test('objectKind gathering → 现有 generated gatheringDetail 路由', () {
        // 交集行动只认 metadata 登记的 gathering 单轨对象类型；端侧只读 codegen，
        // 不保留 trip/meetup 兼容映射。
        expect(
          intersectionRouteIdForObjectKind(IntersectionObjectKind.gathering),
          'gatheringDetail',
        );
        expect(
          IntersectionObjectKind.values.map((kind) => kind.wireName),
          isNot(contains('trip')),
        );
        expect(
          IntersectionObjectKind.values.map((kind) => kind.wireName),
          isNot(contains('meetup')),
        );
        expect(
          IntersectionTargetNavigator.resolvePath(
            intersectionTargetFixture(objectId: 'g1', objectKind: 'gathering'),
          ),
          AppRoutePaths.gatheringDetail(id: 'g1'),
        );
      });

      test('首页/Post/视频/实体/圈子展示位复用同一 Gathering target', () {
        const placements = <String>[
          'home_feed',
          'post_cta',
          'video_cta',
          'entity_homepage',
          'circle_homepage',
        ];
        for (final placement in placements) {
          final target = intersectionTargetFixture(
            objectId: 'gathering-shared-001',
            objectKind: 'gathering',
          );
          expect(
            IntersectionTargetNavigator.resolvePath(target),
            AppRoutePaths.gatheringDetail(id: 'gathering-shared-001'),
            reason: '$placement 不得另建 Gathering 模型或垂类路由',
          );
          expect(target.objectKind, 'gathering');
          expect(target.objectId, 'gathering-shared-001');
        }
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
            path: '/user/:userHandle',
            builder: (_, state) =>
                Text('USER:${state.pathParameters['userHandle']}'),
          ),
          GoRoute(
            path: '/chat/start-group',
            builder: (_, _) => const Text('START_GROUP_CHAT'),
          ),
          GoRoute(
            path: '/chat/:id',
            builder: (_, state) => Text('CHAT:${state.pathParameters['id']}'),
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
          intersectionTargetFixture(
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
        intersectionTargetFixture(objectId: '', routeId: 'userProfile'),
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
        intersectionTargetFixture(
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

  group('IntersectionTargetNavigator.openActionHint（dispatch 分发 · 门交承接页）', () {
    Widget hostWith(
      void Function(BuildContext) capture, {
      void Function(Object? extra)? onStartGroupExtra,
      void Function(Object? extra)? onAssistantExtra,
      GatheringCreateNavigationBinding? gatheringBinding,
      bool disableGatheringBinding = false,
    }) {
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
            path: '/user/:userHandle',
            builder: (_, state) =>
                Text('USER:${state.pathParameters['userHandle']}'),
          ),
          GoRoute(
            path: '/chat/start-group',
            builder: (_, state) {
              onStartGroupExtra?.call(state.extra);
              return const Text('START_GROUP_CHAT');
            },
          ),
          GoRoute(
            path: AppRoutePaths.assistantPersonal,
            builder: (_, state) {
              onAssistantExtra?.call(state.extra);
              return const Text('ASSISTANT_PERSONAL');
            },
          ),
          GoRoute(
            path: '/chat/:id',
            builder: (_, state) => Text('CHAT:${state.pathParameters['id']}'),
          ),
        ],
      );
      return ProviderScope(
        overrides: [
          if (disableGatheringBinding)
            startGatheringNavigationBindingProvider.overrideWithValue(null)
          else if (gatheringBinding != null)
            startGatheringNavigationBindingProvider.overrideWithValue(
              gatheringBinding,
            ),
        ],
        child: MaterialApp.router(routerConfig: router),
      );
    }

    testWidgets('assistant dispatch → 打开小艺会话真实路由', (tester) async {
      late BuildContext homeContext;
      Object? assistantExtra;
      await tester.pumpWidget(
        hostWith(
          (c) => homeContext = c,
          onAssistantExtra: (extra) => assistantExtra = extra,
        ),
      );
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        intersectionActionHintFixture(
          actionKey: 'ask_assistant',
          dispatch: 'assistant',
        ),
        evidenceReason: intersectionReasonFixture(
          kind: 'shared_followees',
          intersectionId: 'intersection-1',
          pointSummarySnapshotId: 'evidence-1',
        ),
        contextObjectTarget: intersectionTargetFixture(
          objectType: 'user',
          objectId: 'u_lin',
          objectKind: 'person',
          routeId: 'userProfile',
        ),
      );
      await tester.pumpAndSettle();

      expect(result.didOpen, isTrue);
      expect(find.text('ASSISTANT_PERSONAL'), findsOneWidget);
      expect(assistantExtra, isA<AssistantOpenContext>());
    });

    testWidgets('navigate dispatch + 无 gates → 按 target 真实导航并上报', (
      tester,
    ) async {
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

      final result = navigator.openActionHint(
        homeContext,
        intersectionActionHintFixture(
          actionKey: 'open_object',
          dispatch: 'navigate',
          target: intersectionTargetFixture(
            objectId: 'u_lin',
            objectKind: 'person',
          ),
        ),
        attribution: const IntersectionNavAttribution(
          intersectionId: 'ix1',
          dimension: 'relationship',
        ),
      );
      await tester.pumpAndSettle();

      expect(result.didOpen, isTrue);
      expect(find.text('USER:u_lin'), findsOneWidget);
      expect(trackedTarget?.objectId, 'u_lin');
      expect(trackedAttr?.intersectionId, 'ix1');
    });

    testWidgets(
      'navigate + login 门 → 导航到承接页（门交承接页 + AuthContinuation 续接，不在本层隐藏）',
      (tester) async {
        late BuildContext homeContext;
        await tester.pumpWidget(hostWith((c) => homeContext = c));
        await tester.pumpAndSettle();

        // 关注等轻行动带 login 门，但 dispatch=navigate。登录门不在交集组件拦截：
        // 导航到 userProfile 承接页，由承接页复用既有 gate + AuthContinuation 续接完成
        // 关注（§15 无死循环）。若在本层因 login 隐藏/拦截，已登录用户也会失去入口。
        final result = const IntersectionTargetNavigator().openActionHint(
          homeContext,
          intersectionActionHintFixture(
            actionKey: 'follow_person',
            dispatch: 'navigate',
            requiredGates: <String>['login'],
            target: intersectionTargetFixture(
              objectId: 'u_lin',
              objectKind: 'person',
              routeId: 'userProfile',
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(result.status, IntersectionActionDispatchStatus.opened);
        expect(find.text('USER:u_lin'), findsOneWidget);
      },
    );

    testWidgets('gathering dispatch → typed binding 保留来源、交集、证据且绝不发起普通群聊', (
      tester,
    ) async {
      IntersectionTarget? trackedTarget;
      IntersectionNavAttribution? trackedAttr;
      GatheringCreateNavigationRequest? createRequest;
      var startGroupVisited = 0;
      final navigator = IntersectionTargetNavigator(
        onTrack: (target, attribution) {
          trackedTarget = target;
          trackedAttr = attribution;
        },
      );
      late BuildContext homeContext;
      await tester.pumpWidget(
        hostWith(
          (c) => homeContext = c,
          onStartGroupExtra: (_) => startGroupVisited += 1,
          gatheringBinding: (context, [request]) async =>
              createRequest = request,
        ),
      );
      await tester.pumpAndSettle();

      final result = navigator.openActionHint(
        homeContext,
        intersectionActionHintFixture(
          actionKey: 'start_gathering',
          dispatch: 'gathering',
          // start_gathering 是「公开约伴邀约」，发起环节安全门不含 mutualConsent
          // （双向同意属响应/建联阶段，由群聊自身 gate 承接）；与 registry.actionKeyMeta 对齐。
          requiredGates: const <String>[
            'login',
            'realName',
            'minorMode',
            'blocked',
            'rateLimit',
          ],
          target: intersectionTargetFixture(
            objectId: 'fixture_homepage_travel_photo_west_lake',
            objectKind: 'place',
          ),
        ),
        attribution: const IntersectionNavAttribution(
          intersectionId: 'ix_wishlist',
          dimension: 'location',
          intersectionClass: 'fact',
          sourceRef: 'coWishlistedEntity',
          evidenceId: 'ev_wishlist_1',
        ),
        // 对象名只能取自云侧主句 span：承接页要用它命名约伴群。
        evidenceReason: intersectionReasonFixture(
          intersectionId: 'ix_wishlist',
          kind: 'coWishlistedEntity',
          primarySpans: <IntersectionTextSpan>[
            intersectionTextSpanFixture(text: '你和「陆衡」都想去'),
            intersectionTextSpanFixture(
              text: '「西湖」',
              role: 'object',
              target: intersectionTargetFixture(
                objectId: 'fixture_homepage_travel_photo_west_lake',
                objectKind: 'place',
              ),
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(result.status, IntersectionActionDispatchStatus.opened);
      expect(find.text('START_GROUP_CHAT'), findsNothing);
      expect(find.text('HOME'), findsOneWidget);
      expect(startGroupVisited, 0);
      expect(
        trackedTarget?.objectId,
        'fixture_homepage_travel_photo_west_lake',
      );
      expect(trackedAttr?.sourceRef, 'coWishlistedEntity');
      expect(createRequest, isNotNull);
      expect(createRequest!.actionKey, 'start_gathering');
      expect(
        createRequest!.targetObject.objectId,
        'fixture_homepage_travel_photo_west_lake',
      );
      expect(createRequest!.targetObject.objectKind, 'place');
      expect(createRequest!.targetObject.objectName, '西湖');
      expect(createRequest!.intersection.intersectionId, 'ix_wishlist');
      expect(createRequest!.intersection.dimension, 'location');
      expect(createRequest!.sourceRefs.single.sourceRef, 'coWishlistedEntity');
      expect(createRequest!.evidence.evidenceId, 'ev_wishlist_1');
      expect(createRequest!.referralSource, ReferralSource.myIntersections);
    });

    testWidgets('gathering dispatch + 无 target → 不调用 typed binding', (
      tester,
    ) async {
      late BuildContext homeContext;
      var invocationCount = 0;
      await tester.pumpWidget(
        hostWith(
          (c) => homeContext = c,
          gatheringBinding: (context, [request]) async => invocationCount += 1,
        ),
      );
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        intersectionActionHintFixture(
          actionKey: 'start_gathering',
          dispatch: 'gathering',
        ),
      );
      await tester.pumpAndSettle();

      expect(result.status, IntersectionActionDispatchStatus.missingTarget);
      expect(invocationCount, 0);
      expect(find.text('HOME'), findsOneWidget);
      expect(find.text('START_GROUP_CHAT'), findsNothing);
    });

    testWidgets('gathering dispatch + binding 未绑定 → 结构化 unavailable 且不进入普通群聊', (
      tester,
    ) async {
      late BuildContext homeContext;
      var startGroupVisited = 0;
      await tester.pumpWidget(
        hostWith(
          (c) => homeContext = c,
          onStartGroupExtra: (_) => startGroupVisited += 1,
          disableGatheringBinding: true,
        ),
      );
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        intersectionActionHintFixture(
          actionKey: 'start_gathering',
          dispatch: 'gathering',
          target: intersectionTargetFixture(
            objectId: 'fixture_homepage_travel_photo_west_lake',
            objectKind: 'place',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(result.status, IntersectionActionDispatchStatus.unavailable);
      expect(
        result.unavailableReason,
        IntersectionActionUnavailableReason
            .startGatheringNavigationBindingMissing,
      );
      expect(startGroupVisited, 0);
      expect(find.text('START_GROUP_CHAT'), findsNothing);
      expect(find.text('HOME'), findsOneWidget);
    });

    testWidgets('message → 对方主页破冰承接（打招呼 / 私信兑现承诺）', (tester) async {
      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        intersectionActionHintFixture(
          actionKey: 'greet_person',
          dispatch: 'message',
          requiredGates: const <String>['login', 'greetPreference', 'blocked'],
          target: intersectionTargetFixture(
            objectId: 'u_lin',
            objectKind: 'person',
          ),
        ),
      );
      expect(result.status, IntersectionActionDispatchStatus.opened);
      await tester.pumpAndSettle();
      expect(find.text('USER:u_lin'), findsOneWidget);
    });

    testWidgets('message 的 target 不是 person → 不伪装成对象下钻', (tester) async {
      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        intersectionActionHintFixture(
          actionKey: 'message_person',
          dispatch: 'message',
          requiredGates: const <String>['login'],
          target: intersectionTargetFixture(
            objectId: 'fixture_circle_photo',
            objectKind: 'circle',
          ),
        ),
      );
      expect(result.status, IntersectionActionDispatchStatus.missingTarget);
      await tester.pumpAndSettle();
      expect(find.text('HOME'), findsOneWidget);
    });

    testWidgets('未登记 dispatch → fail-closed', (tester) async {
      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        intersectionActionHintFixture(
          actionKey: 'unknown_action',
          dispatch: 'unknown',
          target: intersectionTargetFixture(
            objectId: 'u_lin',
            objectKind: 'person',
          ),
        ),
      );
      expect(result.status, IntersectionActionDispatchStatus.unsupported);
      await tester.pumpAndSettle();

      expect(find.text('HOME'), findsOneWidget);
      expect(find.text('USER:u_lin'), findsNothing);
    });
  });
}
