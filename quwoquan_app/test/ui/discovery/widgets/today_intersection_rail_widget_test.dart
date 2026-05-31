import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/ui/discovery/widgets/today_intersection_rail.dart';
import 'package:quwoquan_app/ui/discovery/widgets/unified_object_card.dart';

/// V1-D/A2：今日交集顶部流以统一对象卡承载，只读消费 IntersectionReason。
///
/// 特性树：home-intersection-rail
Widget _wrap(Widget child) {
  return CupertinoApp(home: CupertinoPageScaffold(child: child));
}

IntersectionReason _objectReason({
  required String dimension,
  required String relationKind,
  required String displayText,
  required String actionTargetId,
  String actionType = 'view',
}) {
  return IntersectionReason(
    dimension: dimension,
    relationKind: relationKind,
    displayText: displayText,
    actionType: actionType,
    actionTargetId: actionTargetId,
    tagRefs: const <String>['x/y/z'],
    sharedCount: 3,
    source: dimension,
  );
}

void main() {
  testWidgets('rail 以统一对象卡渲染各对象理由的 displayText（只读）', (tester) async {
    final reasons = <IntersectionReason>[
      _objectReason(
        dimension: 'identity',
        relationKind: 'person',
        displayText: '你和 TA 都来自同一校园',
        actionTargetId: 'u1',
        actionType: 'follow',
      ),
      _objectReason(
        dimension: 'location',
        relationKind: 'place',
        displayText: '你和 TA 都去过 西湖',
        actionTargetId: 'hp_west_lake',
      ),
    ];
    await tester.pumpWidget(
      _wrap(TodayIntersectionRail(reasons: reasons, isDark: false)),
    );

    expect(find.byKey(TodayIntersectionRail.railKey), findsOneWidget);
    expect(find.byType(UnifiedObjectCard), findsNWidgets(2));
    expect(find.text('你和 TA 都来自同一校园'), findsOneWidget);
    expect(find.text('你和 TA 都去过 西湖'), findsOneWidget);
  });

  testWidgets('无交集理由时整条不展示', (tester) async {
    await tester.pumpWidget(
      _wrap(
        const TodayIntersectionRail(
          reasons: <IntersectionReason>[],
          isDark: false,
        ),
      ),
    );

    expect(find.byKey(TodayIntersectionRail.railKey), findsNothing);
  });

  testWidgets('仅有非对象理由（无 actionTargetId）时整条不展示', (tester) async {
    final reasons = <IntersectionReason>[
      IntersectionReason(
        dimension: 'content',
        displayText: '你们都在看 黄金投资',
        sharedCount: 2,
        source: 'content',
      ),
    ];
    await tester.pumpWidget(
      _wrap(TodayIntersectionRail(reasons: reasons, isDark: false)),
    );

    expect(find.byKey(TodayIntersectionRail.railKey), findsNothing);
  });

  testWidgets('点击对象卡卡体回流到 onReasonTap', (tester) async {
    IntersectionReason? tapped;
    final reasons = <IntersectionReason>[
      _objectReason(
        dimension: 'interest',
        relationKind: 'circle',
        displayText: '你们都在关注 黄金投资',
        actionTargetId: 'circle_gold',
        actionType: 'join',
      ),
    ];
    await tester.pumpWidget(
      _wrap(
        TodayIntersectionRail(
          reasons: reasons,
          isDark: true,
          onReasonTap: (reason) => tapped = reason,
        ),
      ),
    );

    await tester.tap(find.text('你们都在关注 黄金投资'));
    await tester.pump();

    expect(tapped, isNotNull);
    expect(tapped!.relationKind, 'circle');
  });

  testWidgets('点击对象卡行动按钮回流到 onReasonAction', (tester) async {
    IntersectionReason? acted;
    final reasons = <IntersectionReason>[
      _objectReason(
        dimension: 'identity',
        relationKind: 'person',
        displayText: '你和 TA 都来自同一校园',
        actionTargetId: 'u1',
        actionType: 'follow',
      ),
    ];
    await tester.pumpWidget(
      _wrap(
        TodayIntersectionRail(
          reasons: reasons,
          isDark: false,
          onReasonAction: (reason) => acted = reason,
        ),
      ),
    );

    await tester.tap(find.text('关注'));
    await tester.pump();

    expect(acted, isNotNull);
    expect(acted!.actionType, 'follow');
  });
}
