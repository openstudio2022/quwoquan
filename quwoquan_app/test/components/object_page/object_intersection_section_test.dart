import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
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
}) {
  return IntersectionReason(
    dimension: dimension,
    intersectionPoints: <IntersectionPoint>[
      IntersectionPoint(
        pointId: '$dimension-$label',
        pointClass: 'fact',
        dimension: dimension,
        label: label,
        displayText: label,
        count: count,
      ),
    ],
  );
}

const _query = ObjectIntersectionQuery(
  objectAId: 'me',
  objectAType: 'user',
  objectBId: 'u_lin',
  objectBType: 'user',
);

Widget _host({
  required Future<List<IntersectionReason>> Function() reasons,
}) {
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

void main() {
  testWidgets('loading → 展示骨架占位（不留白/不闪布局）', (tester) async {
    final completer = Completer<List<IntersectionReason>>();
    await tester.pumpWidget(
      _host(reasons: () => completer.future),
    );
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
    expect(
      capturedRef.read(intersectionHighlightIntentProvider),
      isNull,
    );
    expect(find.byType(ObjectIntersectionCard), findsOneWidget);
  });
}
