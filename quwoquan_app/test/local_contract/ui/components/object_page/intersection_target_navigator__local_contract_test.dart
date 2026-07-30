import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/start_group_chat_route_extra.dart';

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

      test('objectKind gathering → routeId 反查正确，目标页未实现时优雅降级（契约占位）', () {
        // 交集行动只认 metadata 登记的 gathering 单轨对象类型；端侧只读 codegen，
        // 不保留 trip/meetup 兼容映射。
        expect(
          intersectionRouteIdForObjectKind('gathering'),
          'gatheringDetail',
        );
        expect(intersectionRouteIdForObjectKind('trip'), isEmpty);
        expect(intersectionRouteIdForObjectKind('meetup'), isEmpty);
        // gathering 详情页尚未实现：resolvePath 落入 default → null，端侧静默降级。
        expect(
          IntersectionTargetNavigator.resolvePath(
            IntersectionTarget(objectId: 'g1', objectKind: 'gathering'),
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

  group('IntersectionTargetNavigator.openActionHint（dispatch 分发 · 门交承接页）', () {
    Widget hostWith(
      void Function(BuildContext) capture, {
      void Function(Object? extra)? onStartGroupExtra,
      void Function(Object? extra)? onAssistantExtra,
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
      return MaterialApp.router(routerConfig: router);
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
        IntersectionActionHint(
          actionKey: 'ask_assistant',
          dispatch: 'assistant',
          targetAvailability: 'available',
        ),
        evidenceReason: IntersectionReason(
          kind: 'shared_followees',
          intersectionId: 'intersection-1',
          pointSummarySnapshotId: 'evidence-1',
        ),
        contextObjectTarget: IntersectionTarget(
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
        IntersectionActionHint(
          actionKey: 'open_object',
          dispatch: 'navigate',
          target: IntersectionTarget(objectId: 'u_lin', objectKind: 'person'),
          targetAvailability: 'available',
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

    testWidgets('deferred action → 不执行、不伪造成对象导航', (tester) async {
      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        IntersectionActionHint(
          actionKey: 'join_gathering',
          dispatch: 'gathering',
          targetAvailability: 'deferred',
          target: IntersectionTarget(objectId: 'u_lin', objectKind: 'person'),
        ),
      );
      await tester.pumpAndSettle();

      expect(result.status, IntersectionActionDispatchStatus.deferred);
      expect(find.text('HOME'), findsOneWidget);
      expect(find.text('USER:u_lin'), findsNothing);
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
          IntersectionActionHint(
            actionKey: 'follow_person',
            dispatch: 'navigate',
            requiredGates: <String>['login'],
            targetAvailability: 'available',
            target: IntersectionTarget(
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

    testWidgets('gathering dispatch → 进入发起群聊承接页并保留结构化上下文', (tester) async {
      IntersectionTarget? trackedTarget;
      IntersectionNavAttribution? trackedAttr;
      Object? startGroupExtra;
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
          onStartGroupExtra: (extra) => startGroupExtra = extra,
        ),
      );
      await tester.pumpAndSettle();

      final result = navigator.openActionHint(
        homeContext,
        IntersectionActionHint(
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
          targetAvailability: 'available',
          target: IntersectionTarget(
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
        evidenceReason: IntersectionReason(
          intersectionId: 'ix_wishlist',
          kind: 'coWishlistedEntity',
          primarySpans: <IntersectionTextSpan>[
            IntersectionTextSpan(text: '你和「陆衡」都想去'),
            IntersectionTextSpan(
              text: '「西湖」',
              role: 'object',
              target: IntersectionTarget(
                objectId: 'fixture_homepage_travel_photo_west_lake',
                objectKind: 'place',
              ),
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(result.status, IntersectionActionDispatchStatus.opened);
      expect(find.text('START_GROUP_CHAT'), findsOneWidget);
      expect(
        trackedTarget?.objectId,
        'fixture_homepage_travel_photo_west_lake',
      );
      expect(trackedAttr?.sourceRef, 'coWishlistedEntity');
      expect(startGroupExtra, isA<StartGroupChatRouteExtra>());
      final extra = startGroupExtra! as StartGroupChatRouteExtra;
      expect(extra.actionKey, 'start_gathering');
      expect(extra.targetObjectId, 'fixture_homepage_travel_photo_west_lake');
      expect(extra.targetObjectKind, 'place');
      // 群名要用得上的名字：书名号是主句排版，不进群名；拿不到名字时才退回成员名。
      expect(extra.targetObjectName, '西湖');
      expect(extra.intersectionId, 'ix_wishlist');
      expect(extra.dimension, 'location');
      expect(extra.sourceRef, 'coWishlistedEntity');
      expect(extra.evidenceId, 'ev_wishlist_1');
    });

    testWidgets('gathering dispatch + 无 target → 不进入普通建群', (tester) async {
      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        IntersectionActionHint(
          actionKey: 'start_gathering',
          dispatch: 'gathering',
          targetAvailability: 'available',
        ),
      );
      await tester.pumpAndSettle();

      expect(result.status, IntersectionActionDispatchStatus.missingTarget);
      expect(find.text('HOME'), findsOneWidget);
      expect(find.text('START_GROUP_CHAT'), findsNothing);
    });

    testWidgets('commerce dispatch 默认 feature flag 关闭 → 明确不可执行', (
      tester,
    ) async {
      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        IntersectionActionHint(
          actionKey: 'view_official_deals',
          dispatch: 'commerce',
          targetAvailability: 'available',
          target: IntersectionTarget(objectId: 'u_lin', objectKind: 'person'),
        ),
      );
      await tester.pumpAndSettle();

      expect(result.status, IntersectionActionDispatchStatus.featureDisabled);
      expect(find.text('HOME'), findsOneWidget);
      expect(find.text('USER:u_lin'), findsNothing);
    });

    testWidgets('commerce dispatch 显式启用 + target 可路由 → 按真实 target 导航', (
      tester,
    ) async {
      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final result =
          const IntersectionTargetNavigator(
            commerceActionsEnabled: true,
          ).openActionHint(
            homeContext,
            IntersectionActionHint(
              actionKey: 'view_official_deals',
              dispatch: 'commerce',
              targetAvailability: 'available',
              target: IntersectionTarget(
                objectId: 'u_lin',
                objectKind: 'person',
              ),
            ),
          );
      await tester.pumpAndSettle();

      expect(result.status, IntersectionActionDispatchStatus.opened);
      expect(find.text('USER:u_lin'), findsOneWidget);
    });

    testWidgets('message → 对方主页破冰承接（打招呼 / 私信兑现承诺）', (tester) async {
      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        IntersectionActionHint(
          actionKey: 'greet_person',
          dispatch: 'message',
          requiredGates: const <String>['login', 'greetPreference', 'blocked'],
          targetAvailability: 'available',
          target: IntersectionTarget(objectId: 'u_lin', objectKind: 'person'),
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
        IntersectionActionHint(
          actionKey: 'message_person',
          dispatch: 'message',
          requiredGates: const <String>['login'],
          targetAvailability: 'available',
          target: IntersectionTarget(
            objectId: 'fixture_circle_photo',
            objectKind: 'circle',
          ),
        ),
      );
      expect(result.status, IntersectionActionDispatchStatus.missingTarget);
      await tester.pumpAndSettle();
      expect(find.text('HOME'), findsOneWidget);
    });

    testWidgets('connect 无专属真实破冰状态机 → 不伪装成 target 导航', (tester) async {
      late BuildContext homeContext;
      await tester.pumpWidget(hostWith((c) => homeContext = c));
      await tester.pumpAndSettle();

      final result = const IntersectionTargetNavigator().openActionHint(
        homeContext,
        IntersectionActionHint(
          actionKey: 'join_topic_room',
          dispatch: 'connect',
          requiredGates: const <String>['login'],
          targetAvailability: 'available',
          target: IntersectionTarget(objectId: 'u_lin', objectKind: 'person'),
        ),
      );
      expect(result.status, IntersectionActionDispatchStatus.unsupported);
      await tester.pumpAndSettle();

      expect(find.text('HOME'), findsOneWidget);
      expect(find.text('USER:u_lin'), findsNothing);
    });
  });
}
