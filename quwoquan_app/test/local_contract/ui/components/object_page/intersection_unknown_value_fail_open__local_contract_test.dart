import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_fact_items.dart';
import 'package:quwoquan_app/components/object_page/intersection_entity.dart';
import 'package:quwoquan_app/components/object_page/intersection_statement_row.dart';
import 'package:quwoquan_app/components/object_page/object_intersection_card.dart';

/// T2：零发版判据 —— 完全未登记的交集仍必须带着云侧文案正常渲染。
///
/// 这是「新增 kind / objectKind / dispatch / iconKey / 垂类不需要发端」这条产品承诺的
/// 持续证明。历史上端侧有四处 fail-closed（objectType 白名单、未知 binding 归 hidden、
/// 未知 dispatch 的行动 pill 永不渲染、未知 objectKind 当人物头像），它们的共同后果是
/// 云侧登记新值后旧版本上内容**静默消失或张冠李戴**，而不是优雅降级。
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

  final objectTarget = IntersectionTarget(
    objectType: unknownObjectType,
    objectId: 'obj_unknown_1',
    objectKind: unknownObjectKind,
    routeId: 'starshipDetail',
  );
  return IntersectionReason(
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
      IntersectionTextSpan(text: '林清越', role: 'actor'),
      IntersectionTextSpan(text: '也停靠过', role: 'plain'),
      IntersectionTextSpan(
        text: '星港七号',
        role: 'object',
        target: objectTarget,
      ),
    ],
    totalPointCount: 1,
    factPointCount: 1,
    dimensionPointSummary: <IntersectionDimensionTally>[
      IntersectionDimensionTally(
        dimension: 'relationship',
        label: '关系',
        count: 1,
      ),
    ],
    intersectionPoints: <IntersectionPoint>[
      IntersectionPoint(
        pointId: 'p1',
        sourceRef: unknownKind,
        dimension: 'relationship',
        label: '共同停靠的星港',
        displayText: '1个共同停靠的星港',
        count: 1,
      ),
    ],
    actionHints: <IntersectionActionHint>[
      IntersectionActionHint(
        actionKey: 'dock_together',
        label: '一起停靠',
        dispatch: dispatch,
        targetAvailability: 'available',
        target: objectTarget,
        isPrimary: true,
      ),
    ],
    actorEvidenceTotalCount: 1,
    actorEvidenceCompleteness: 'complete',
    representativeActor: withRepresentative
        ? IntersectionRepresentativeActor(
            actorId: 'u_lin',
            displayName: '林清越',
            relationLabel: '同航线的人',
            privacyState: 'visible',
            target: IntersectionTarget(
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
  group('未登记 kind / objectKind / dispatch / iconKey 仍可渲染', () {
    test('展示合同放行：objectType 不在任何端侧白名单里也不丢句子', () {
      final reason = _unregisteredReason();
      expect(displayReadyIntersectionReason(reason)?.primaryText, reason.primaryText);
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

    test('未知 dispatch + 有落点 → 行动 pill 照常渲染', () {
      final hint = _unregisteredReason().actionHints.single;
      expect(isDisplayableIntersectionActionHint(hint), isTrue);
    });

    testWidgets('整卡渲染：主句、行动 pill 与共同点计数全部来自云侧字段', (tester) async {
      final card = ObjectIntersectionCard.fromReasons(
        title: '你和这里的交集',
        reasons: <IntersectionReason>[_unregisteredReason()],
        isDark: false,
      );
      expect(card, isNotNull);
      await _pump(tester, card!);

      expect(find.text('林清越也停靠过星港七号'), findsOneWidget);
      expect(find.text('一起停靠'), findsOneWidget);
    });

    testWidgets('宿主 objectType 未登记（objectKind 查表落空）也不清空整张卡', (tester) async {
      // 对象页把自身 objectType 经注册表 objectTypeBindings 收成 objectKind；未登记时
      // 得到空 objectKind / 空 routeId。宿主身份的判定必须回落到 objectId，
      // 而不是因为查表落空就把整张卡的 reason 全部判为不可展示。
      final hostTarget = IntersectionTarget(
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
        IntersectionEntity(
          reason: _unregisteredReason(),
          isDark: false,
        ),
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
