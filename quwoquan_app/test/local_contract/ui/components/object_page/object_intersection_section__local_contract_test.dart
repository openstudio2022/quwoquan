import 'dart:async';
import '../../../../support/fixtures/intersection_fixtures.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/object_intersection_card.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/object_intersection_card_skeleton.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_section.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/cloud_services/behavior_repository_double.dart';

/// T2：对象页交集 section 统一 async 三态 + 旅程一次性消费（V4 · 商用完整态）。
IntersectionReason _reason({
  required String dimension,
  required String label,
  required int count,
  String actionTargetId = '',
  String objectKind = 'person',
  String source = 'sharedFollowees',
  List<IntersectionActionHint> actionHints = const <IntersectionActionHint>[],
  String displayBinding = 'explicit_link',
}) {
  final targetId = actionTargetId.trim().isEmpty
      ? 'u_zhou'
      : actionTargetId.trim();
  final kind = objectKind.trim().isEmpty ? 'person' : objectKind.trim();
  final primary = '$label $count';
  final objectTarget = _targetFor(kind, targetId);
  return intersectionReasonFixture(
    source: source,
    dimension: dimension,
    actionTargetId: targetId,
    objectKind: kind,
    displayBinding: displayBinding,
    primaryText: primary,
    primarySpans: <IntersectionTextSpan>[
      intersectionTextSpanFixture(
        text: primary,
        role: 'object',
        target: objectTarget,
      ),
    ],
    actorEvidenceTotalCount: 1,
    actorEvidenceCompleteness: 'complete',
    representativeActor: intersectionRepresentativeActorFixture(
      actorId: 'u_lin',
      displayName: '林清越',
      relationLabel: '联系人',
      privacyState: 'visible',
      target: _targetFor('person', 'u_lin'),
    ),
    actionHints: actionHints,
  );
}

IntersectionReason _hostPlainSelfReason() {
  final actorTarget = _targetFor('person', 'u_zhou');
  return intersectionReasonFixture(
    source: 'sharedFollowees',
    dimension: 'relationship',
    actionTargetId: 'u_lin',
    objectKind: 'person',
    displayBinding: 'host_plain',
    primaryText: '联系人周屿也关注了林清越',
    primarySpans: <IntersectionTextSpan>[
      intersectionTextSpanFixture(text: '联系人', role: 'plain'),
      intersectionTextSpanFixture(
        text: '周屿',
        role: 'object',
        target: actorTarget,
      ),
      intersectionTextSpanFixture(text: '也关注了林清越', role: 'plain'),
    ],
    actorEvidenceTotalCount: 1,
    actorEvidenceCompleteness: 'complete',
    representativeActor: intersectionRepresentativeActorFixture(
      actorId: 'u_zhou',
      displayName: '周屿',
      relationLabel: '联系人',
      privacyState: 'visible',
      target: actorTarget,
    ),
    sampleVisuals: const [],
  );
}

IntersectionTarget _targetFor(String objectKind, String objectId) {
  final kind = objectKind.trim();
  switch (kind) {
    case 'circle':
      return intersectionTargetFixture(
        objectType: 'circle',
        objectId: objectId,
        objectKind: kind,
        routeId: 'circleDetail',
      );
    case 'content':
      return intersectionTargetFixture(
        objectType: 'post',
        objectId: objectId,
        objectKind: kind,
        routeId: 'workBrowser',
      );
    case 'place':
    case 'school':
    case 'enterprise':
    case 'route':
    case 'photo_spot':
    case 'gear':
      return intersectionTargetFixture(
        objectType: 'homepage',
        objectId: objectId,
        objectKind: kind,
        routeId: 'homepageDetail',
      );
    case 'person':
    default:
      return intersectionTargetFixture(
        objectType: 'user',
        objectId: objectId,
        objectKind: 'person',
        routeId: 'userProfile',
      );
  }
}

const _query = ObjectIntersectionQuery(
  objectAId: 'me',
  objectAType: 'user',
  objectBId: 'u_lin',
  objectBType: 'user',
);

Widget _host({
  required Future<List<IntersectionReason>> Function() reasons,
  List<Override> overrides = const <Override>[],
}) {
  return ProviderScope(
    overrides: [
      ...overrides,
      behaviorReporterProvider.overrideWithValue(MockBehaviorRepository()),
      objectSharedReasonsProvider(_query).overrideWith((_) => reasons()),
    ],
    child: const CupertinoApp(
      home: CupertinoPageScaffold(
        child: ObjectIntersectionSection(
          query: _query,
          title: '你们的交集',
          isDark: false,
        ),
      ),
    ),
  );
}

/// N4（断点2）：未传 onReasonTap 时 section 内部默认走统一 navigator 下钻，
/// GoRouter host 验证整行对象级可达；`/user/:userHandle` 复用 resolvePath(person) 的
/// codegen 路由（userProfile）。
Widget _routerHost({
  required List<IntersectionReason> reasons,
  void Function(IntersectionReason reason)? onReasonTap,
}) {
  final router = GoRouter(
    initialLocation: '/',
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (_, _) => CupertinoPageScaffold(
          child: ObjectIntersectionSection(
            query: _query,
            title: '你们的交集',
            isDark: false,
            onReasonTap: onReasonTap,
          ),
        ),
      ),
      GoRoute(
        path: '/user/:userHandle',
        builder: (_, state) =>
            Text('USER:${state.pathParameters['userHandle']}'),
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      behaviorReporterProvider.overrideWithValue(MockBehaviorRepository()),
      objectSharedReasonsProvider(_query).overrideWith((_) async => reasons),
    ],
    child: CupertinoApp.router(routerConfig: router),
  );
}

/// C0：交集卡渲染 gathering「发起结伴」pill，点击经统一 navigator._openGathering 进
/// 发起群聊承接页（最薄真实约伴闭环）。router 含 /chat/start-group 与 /user/:userHandle。
Widget _companionHost({required List<IntersectionReason> reasons}) {
  final router = GoRouter(
    initialLocation: '/',
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (_, _) => CupertinoPageScaffold(
          child: ObjectIntersectionSection(
            query: _query,
            title: '你们的交集',
            isDark: false,
          ),
        ),
      ),
      GoRoute(
        path: '/chat/start-group',
        builder: (_, _) => const Text('START_GROUP_CHAT'),
      ),
      GoRoute(
        path: '/user/:userHandle',
        builder: (_, state) =>
            Text('USER:${state.pathParameters['userHandle']}'),
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      behaviorReporterProvider.overrideWithValue(MockBehaviorRepository()),
      objectSharedReasonsProvider(_query).overrideWith((_) async => reasons),
    ],
    child: CupertinoApp.router(routerConfig: router),
  );
}

Future<void> _tapIntersectionRowContaining(
  WidgetTester tester,
  String text,
) async {
  final rowButton = find
      .ancestor(
        of: find.textContaining(text),
        matching: find.byWidgetPredicate(
          (widget) => widget is GestureDetector && widget.onTap != null,
          description: 'tappable intersection statement row',
        ),
      )
      .first;
  final rect = tester.getRect(rowButton);
  await tester.tapAt(Offset(rect.right - 12, rect.center.dy));
}

void main() {
  testWidgets('loading → 展示骨架占位（不留白/不闪布局）', (tester) async {
    final completer = Completer<List<IntersectionReason>>();
    var displayConfigReads = 0;
    await tester.pumpWidget(
      _host(
        reasons: () => completer.future,
        overrides: <Override>[
          intersectionDisplayConfigProvider.overrideWith((ref) {
            displayConfigReads += 1;
            return ref.watch(contentRuntimeConfigProvider).intersectionDisplay;
          }),
        ],
      ),
    );
    await tester.pump();

    expect(displayConfigReads, greaterThanOrEqualTo(1));
    final readsBeforeData = displayConfigReads;
    expect(find.byType(ObjectIntersectionCardSkeleton), findsOneWidget);
    expect(find.byType(ObjectIntersectionCard), findsNothing);

    completer.complete(const <IntersectionReason>[]);
    await tester.pumpAndSettle();
    expect(
      displayConfigReads,
      readsBeforeData,
      reason: 'data 回包不得首次建立或重复建立配置依赖',
    );
  });

  testWidgets('data 有交集 → 展示交集卡，骨架消失', (tester) async {
    await tester.pumpWidget(
      _host(
        reasons: () async => <IntersectionReason>[
          _reason(dimension: 'relationship', label: '共同关注', count: 4),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ObjectIntersectionCardSkeleton), findsNothing);
    expect(find.byType(ObjectIntersectionCard), findsOneWidget);
    expect(find.text('你们的交集'), findsOneWidget);
  });

  testWidgets('data 为空 → 展示克制空态，不编造交集事实', (tester) async {
    await tester.pumpWidget(
      _host(reasons: () async => const <IntersectionReason>[]),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ObjectIntersectionCard), findsNothing);
    expect(find.byType(ObjectIntersectionCardSkeleton), findsNothing);
    expect(find.text('暂时没有可展示的交集'), findsOneWidget);
    expect(find.textContaining('成为第一个'), findsNothing);
  });

  testWidgets('error → 收起（交集是增强位，不以错误噪声打断主体验）', (tester) async {
    await tester.pumpWidget(
      _host(reasons: () async => throw StateError('boom')),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ObjectIntersectionCard), findsNothing);
    expect(find.byType(ObjectIntersectionCardSkeleton), findsNothing);
  });

  testWidgets('旅程高亮：命中后自动消费意图（一次性，避免再进同页强展开）', (tester) async {
    late WidgetRef capturedRef;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          objectSharedReasonsProvider(_query).overrideWith(
            (_) async => <IntersectionReason>[
              _reason(dimension: 'relationship', label: '共同关注', count: 4),
            ],
          ),
        ],
        child: CupertinoApp(
          home: Consumer(
            builder: (context, ref, _) {
              capturedRef = ref;
              return const CupertinoPageScaffold(
                child: ObjectIntersectionSection(
                  query: _query,
                  title: '你们的交集',
                  isDark: false,
                ),
              );
            },
          ),
        ),
      ),
    );
    // 设置高亮意图（对象匹配被看用户）。
    capturedRef
        .read(intersectionHighlightIntentProvider.notifier)
        .set(
          const IntersectionHighlightIntent(
            objectId: 'u_lin',
            kind: 'sharedFollowees',
          ),
        );
    await tester.pumpAndSettle();

    // 命中后首帧消费：意图被清空（一次性语义）。
    expect(capturedRef.read(intersectionHighlightIntentProvider), isNull);
    expect(find.byType(ObjectIntersectionCard), findsOneWidget);
  });

  testWidgets('N4 未传 onReasonTap（用户/圈子主页）→ 点击交集行统一 navigator 下钻对象页', (
    tester,
  ) async {
    await tester.pumpWidget(
      _routerHost(
        reasons: <IntersectionReason>[
          _reason(
            dimension: 'relationship',
            label: '共同关注',
            count: 4,
            actionTargetId: 'u_zhou',
            objectKind: 'person',
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ObjectIntersectionCard), findsOneWidget);
    // 整行可下钻：消除「整行仅 track 不可达」断点；归一 target → userProfile 路由。
    await _tapIntersectionRowContaining(tester, '共同关注');
    await tester.pumpAndSettle();

    expect(find.text('USER:u_zhou'), findsOneWidget);
  });

  testWidgets('host_plain 当前主页作为宾语时展示但不点击 self-target', (tester) async {
    await tester.pumpWidget(
      _routerHost(reasons: <IntersectionReason>[_hostPlainSelfReason()]),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ObjectIntersectionCard), findsOneWidget);
    expect(find.textContaining('林清越'), findsOneWidget);

    await _tapIntersectionRowContaining(tester, '林清越');
    await tester.pumpAndSettle();

    expect(find.text('USER:u_lin'), findsNothing);
  });

  testWidgets('N4 传入 onReasonTap（实体页自定义）→ 调用方优先，不叠加默认下钻（不双跳）', (tester) async {
    IntersectionReason? tapped;
    await tester.pumpWidget(
      _routerHost(
        reasons: <IntersectionReason>[
          _reason(
            dimension: 'relationship',
            label: '共同关注',
            count: 4,
            actionTargetId: 'u_zhou',
            objectKind: 'person',
          ),
        ],
        onReasonTap: (r) => tapped = r,
      ),
    );
    await tester.pumpAndSettle();

    await _tapIntersectionRowContaining(tester, '共同关注');
    await tester.pumpAndSettle();

    // 调用方语义优先：内部不再叠加统一下钻（仍停留对象页，未跳 USER 路由）。
    expect(tapped, isNotNull);
    expect(find.text('USER:u_lin'), findsNothing);
  });

  testWidgets('C0：gathering actionHint → 渲染可点「发起结伴」pill，点击进发起群聊承接页（北极星闭环）', (
    tester,
  ) async {
    await tester.pumpWidget(
      _companionHost(
        reasons: <IntersectionReason>[
          _reason(
            dimension: 'interest',
            label: '你们都想去西湖',
            count: 1,
            actionTargetId: 'p_west_lake',
            objectKind: 'place',
            source: 'coWishlistedEntity',
            actionHints: <IntersectionActionHint>[
              intersectionActionHintFixture(
                actionKey: 'start_gathering',
                label: '发起结伴',
                dispatch: 'gathering',
                isPrimary: true,
                target: intersectionTargetFixture(
                  objectId: 'p_west_lake',
                  objectKind: 'place',
                ),
              ),
            ],
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    // 约伴入口在真实 UI 可见可达（可点 pill），而非仅展示型「有人同行」徽标。
    expect(find.text('发起结伴'), findsOneWidget);

    await tester.tap(find.text('发起结伴'));
    await tester.pumpAndSettle();

    // 点击 → navigator._openGathering → 真实发起群聊承接页（不 fallback 对象下钻）。
    expect(find.text('START_GROUP_CHAT'), findsOneWidget);
  });

  testWidgets('message dispatch actionHint 渲染可点 pill，落到对方主页的破冰承接', (
    tester,
  ) async {
    await tester.pumpWidget(
      _companionHost(
        reasons: <IntersectionReason>[
          _reason(
            dimension: 'relationship',
            label: '你们的共同联系人',
            count: 1,
            actionTargetId: 'u_zhou',
            objectKind: 'person',
            source: 'commonContact',
            actionHints: <IntersectionActionHint>[
              intersectionActionHintFixture(
                actionKey: 'message_person',
                label: '私信',
                dispatch: 'message',
                isPrimary: true,
                target: intersectionTargetFixture(
                  objectId: 'u_zhou',
                  objectKind: 'person',
                ),
              ),
            ],
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    // 私信 / 打招呼有真实承接（对方主页的 greeting 破冰状态机）→ 渲染可点 pill。
    expect(find.text('私信'), findsOneWidget);

    // 点击 pill → navigator._openMessage → 对方主页承接页（不 fallback 成普通下钻）。
    await tester.tap(find.text('私信'));
    await tester.pumpAndSettle();
    expect(find.text('USER:u_zhou'), findsOneWidget);
  });

  testWidgets('message dispatch 的 target 不是 person 时不渲染 pill', (tester) async {
    await tester.pumpWidget(
      _companionHost(
        reasons: <IntersectionReason>[
          _reason(
            dimension: 'relationship',
            label: '你们的共同联系人',
            count: 1,
            actionTargetId: 'fixture_circle_photo',
            objectKind: 'circle',
            source: 'commonContact',
            actionHints: <IntersectionActionHint>[
              intersectionActionHintFixture(
                actionKey: 'message_person',
                label: '私信',
                dispatch: 'message',
                isPrimary: true,
                target: intersectionTargetFixture(
                  objectId: 'fixture_circle_photo',
                  objectKind: 'circle',
                ),
              ),
            ],
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    // 无真实 person 承接对象时不渲染「私信」，避免退化成对象下钻（§24.10 诚实红线）。
    expect(find.text('私信'), findsNothing);
  });
}
