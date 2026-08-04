import 'package:flutter/cupertino.dart';
import '../../../../support/fixtures/intersection_fixtures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/domain/intersection_fact_items.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/intersection_entity.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/intersection_statement_row.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/object_intersection_card.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// T2：未知展示值可降级，但未登记 action dispatch 必须 fail-closed。
///
/// 未知 kind/objectKind/iconKey 不应让可信主句消失；但行动必须来自当前生成闭集，
/// 未登记 dispatch 不能渲染成不可兑现的入口。
IntersectionReason _unregisteredReason({
  String displayBinding = '',
  String dispatch = 'teleport_v9',
  bool withRepresentative = true,
}) {
  // 以下取值在注册表与端侧 codegen 里全部不存在。
  const unknownKind = 'quantumEntangledWith';
  const unknownObjectKind = 'starship';
  const unknownObjectType = 'orbital_station';
  const unknownIconKey = 'wormhole';

  final objectTarget = intersectionTargetFixture(
    objectType: unknownObjectType,
    objectId: 'obj_unknown_1',
    objectKind: unknownObjectKind,
    routeId: 'starshipDetail',
  );
  return intersectionReasonFixture(
    intersectionId: 'ix_unknown_1',
    kind: unknownKind,
    source: unknownKind,
    dimension: 'relationship',
    intersectionClass: 'fact',
    displayName: '星港七号',
    objectKind: unknownObjectKind,
    actionTargetId: 'obj_unknown_1',
    iconKey: unknownIconKey,
    displayBinding: displayBinding,
    primaryText: '林清越也停靠过星港七号',
    primarySpans: <IntersectionTextSpan>[
      intersectionTextSpanFixture(text: '林清越', role: 'actor'),
      intersectionTextSpanFixture(text: '也停靠过', role: 'plain'),
      intersectionTextSpanFixture(
        text: '星港七号',
        role: 'object',
        target: objectTarget,
      ),
    ],
    totalPointCount: 1,
    factPointCount: 1,
    dimensionPointSummary: <IntersectionDimensionTally>[
      intersectionDimensionTallyFixture(
        dimension: 'relationship',
        label: '关系',
        count: 1,
      ),
    ],
    intersectionPoints: <IntersectionPoint>[
      intersectionPointFixture(
        pointId: 'p1',
        sourceRef: unknownKind,
        dimension: 'relationship',
        label: '共同停靠的星港',
        displayText: '1个共同停靠的星港',
        count: 1,
      ),
    ],
    actionHints: <IntersectionActionHint>[
      intersectionActionHintFixture(
        actionKey: 'dock_together',
        label: '一起停靠',
        dispatch: dispatch,
        target: objectTarget,
        isPrimary: true,
      ),
    ],
    actorEvidenceTotalCount: 1,
    actorEvidenceCompleteness: 'complete',
    representativeActor: withRepresentative
        ? intersectionRepresentativeActorFixture(
            actorId: 'u_lin',
            displayName: '林清越',
            relationLabel: '同航线的人',
            privacyState: 'visible',
            target: intersectionTargetFixture(
              objectType: 'user',
              objectId: 'u_lin',
              objectKind: 'person',
              routeId: 'userProfile',
            ),
          )
        : null,
  );
}

Future<void> _pump(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(
    CupertinoApp(
      home: CupertinoPageScaffold(child: SafeArea(child: child)),
    ),
  );
  await tester.pump(const Duration(milliseconds: 300));
}

void main() {
  group('未知展示值降级与 action 闭集', () {
    test('展示合同放行：objectType 不在任何端侧白名单里也不丢句子', () {
      final reason = _unregisteredReason();
      expect(
        displayReadyIntersectionReason(reason)?.primaryText,
        reason.primaryText,
      );
      expect(isDisplayableIntersectionReason(reason), isTrue);
    });

    test('未知 displayBinding 不等于 hidden', () {
      final reason = _unregisteredReason(displayBinding: 'quantum_link_v2');
      expect(isDisplayableIntersectionReason(reason), isTrue);
    });

    test('显式 hidden 仍然隐藏（fail-open 不等于失去隐藏能力）', () {
      final reason = _unregisteredReason(displayBinding: 'hidden');
      expect(isDisplayableIntersectionReason(reason), isFalse);
    });

    test('未知 dispatch + 有落点 → 行动仍 fail-closed', () {
      final hint = _unregisteredReason().actionHints.single;
      expect(isDisplayableIntersectionActionHint(hint), isFalse);
    });

    testWidgets('整卡渲染可信主句，但不渲染未知行动', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '你和这里的交集',
        reasons: <IntersectionReason>[_unregisteredReason()],
        isDark: false,
      );
      expect(card, isNotNull);
      await _pump(tester, card!);

      expect(find.text('林清越也停靠过星港七号'), findsOneWidget);
      expect(find.text('一起停靠'), findsNothing);
    });

    testWidgets('宿主 objectType 未登记（objectKind 查表落空）也不清空整张卡', (tester) async {
      // 对象页把自身 objectType 经注册表 objectTypeBindings 收成 objectKind；未登记时
      // 得到空 objectKind / 空 routeId。宿主身份的判定必须回落到 objectId，
      // 而不是因为查表落空就把整张卡的 reason 全部判为不可展示。
      final hostTarget = intersectionTargetFixture(
        objectType: '',
        objectId: 'host_orbital_1',
        objectKind: '',
        routeId: '',
      );
      final card = ObjectIntersectionCard.fromReasons(
        title: '你和这里的交集',
        reasons: <IntersectionReason>[_unregisteredReason()],
        isDark: false,
        contextObjectTarget: hostTarget,
      );
      expect(card, isNotNull);
      await _pump(tester, card!);
      expect(find.text('林清越也停靠过星港七号'), findsOneWidget);
    });

    testWidgets('未知 objectKind 不得渲染成人物头像', (tester) async {
      await _pump(
        tester,
        IntersectionEntity(reason: _unregisteredReason(), isDark: false),
      );
      final icons = tester.widgetList<Icon>(find.byType(Icon)).toList();
      expect(
        icons.any((i) => i.icon == CupertinoIcons.person_crop_circle_fill),
        isFalse,
        reason: '未知 objectKind 回落成 person 会把星港说成是个人',
      );
    });
  });
}
