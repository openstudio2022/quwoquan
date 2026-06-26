import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card_skeleton.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_provider.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_section.dart';

/// T2：对象页交集 section 统一 async 三态 + 旅程一次性消费（V4 · 商用完整态）。
IntersectionReason _reason({
  required String dimension,
  required String label,
  required int count,
  String actionTargetId = '',
  String objectKind = '',
}) {
  return IntersectionReason(
    dimension: dimension,
    actionTargetId: actionTargetId,
    objectKind: objectKind,
    primaryText: '$label $count',
  );
}

const _query = ObjectIntersectionQuery(
  objectAId: 'me',
  objectAType: 'user',
  objectBId: 'u_lin',
  objectBType: 'user',
);

Widget _host({required Future<List<IntersectionReason>> Function() reasons}) {
  return ProviderScope(
    overrides: [
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
/// GoRouter host 验证整行对象级可达；`/user/:username` 复用 resolvePath(person) 的
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
        path: '/user/:username',
        builder: (_, state) => Text('USER:${state.pathParameters['username']}'),
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      objectSharedReasonsProvider(_query).overrideWith((_) async => reasons),
    ],
    child: CupertinoApp.router(routerConfig: router),
  );
}

void main() {
  testWidgets('loading → 展示骨架占位（不留白/不闪布局）', (tester) async {
    final completer = Completer<List<IntersectionReason>>();
    await tester.pumpWidget(_host(reasons: () => completer.future));
    await tester.pump();

    expect(find.byType(ObjectIntersectionCardSkeleton), findsOneWidget);
    expect(find.byType(ObjectIntersectionCard), findsNothing);

    completer.complete(const <IntersectionReason>[]);
    await tester.pumpAndSettle();
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

  testWidgets('data 为空 → 收起（不占位，G2 不造假）', (tester) async {
    await tester.pumpWidget(
      _host(reasons: () async => const <IntersectionReason>[]),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ObjectIntersectionCard), findsNothing);
    expect(find.byType(ObjectIntersectionCardSkeleton), findsNothing);
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
            actionTargetId: 'u_lin',
            objectKind: 'person',
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ObjectIntersectionCard), findsOneWidget);
    // 整行可下钻：消除「整行仅 track 不可达」断点；归一 target → userProfile 路由。
    await tester.tap(find.textContaining('共同关注'));
    await tester.pumpAndSettle();

    expect(find.text('USER:u_lin'), findsOneWidget);
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
            actionTargetId: 'u_lin',
            objectKind: 'person',
          ),
        ],
        onReasonTap: (r) => tapped = r,
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.textContaining('共同关注'));
    await tester.pumpAndSettle();

    // 调用方语义优先：内部不再叠加统一下钻（仍停留对象页，未跳 USER 路由）。
    expect(tapped, isNotNull);
    expect(find.text('USER:u_lin'), findsNothing);
  });
}
