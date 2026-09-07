// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003.t1
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003.t3
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/immersive_intersection_statement.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

/// 交集行动后置（intersection-unified-experience REQ-009）：
/// 沉浸首屏只渲染一条交集主句，不论 reason 是否携带 typed action hints。
/// 行动只能在用户主动展开证据半屏后，由统一 resolver 选择最多一个 CTA。
Widget _wrap(Widget child) {
  return CupertinoApp(
    home: CupertinoPageScaffold(child: Center(child: child)),
  );
}

const String _primaryText = '你和林清越都想去黄龙风景名胜区';

IntersectionReason _reason({
  List<IntersectionActionHint> actionHints = const <IntersectionActionHint>[],
}) {
  return intersectionReasonFixture(
    kind: 'coWishlistedEntity',
    dimension: 'location',
    primaryText: _primaryText,
    displayBinding: 'host_plain',
    actionHints: actionHints,
  );
}

IntersectionActionHint _gatheringHint({
  String label = '发起聚集',
  bool isPrimary = true,
  int priority = 1,
}) {
  return intersectionActionHintFixture(
    actionKey: 'start_gathering',
    label: label,
    dispatch: 'gathering',
    isPrimary: isPrimary,
    priority: priority,
    target: intersectionTargetFixture(
      objectType: 'homepage',
      objectId: 'hp_huanglong',
      objectKind: 'place',
      routeId: 'homepageDetail',
    ),
  );
}

void main() {
  testWidgets('携带 gathering 主行动的 reason 在首屏仍只显示主句', (tester) async {
    await tester.pumpWidget(
      _wrap(
        ImmersiveIntersectionStatement(
          reason: _reason(actionHints: [_gatheringHint()]),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('immersive-intersection-action')),
      findsNothing,
    );
    expect(find.textContaining(_primaryText), findsOneWidget);
    expect(find.text('发起聚集'), findsNothing);
  });

  testWidgets('无可渲染 hint（navigate 缺 target）→ 只有单句，无 pill', (tester) async {
    await tester.pumpWidget(
      _wrap(
        ImmersiveIntersectionStatement(
          reason: _reason(
            actionHints: [
              intersectionActionHintFixture(
                actionKey: 'open_object',
                label: '查看对象',
                dispatch: 'navigate',
              ),
            ],
          ),
        ),
      ),
    );
    expect(
      find.byKey(const ValueKey('immersive-intersection-action')),
      findsNothing,
    );
    expect(find.textContaining(_primaryText), findsOneWidget);
  });

  testWidgets('多个可渲染 hint 也不会在沉浸首屏提前暴露行动', (tester) async {
    await tester.pumpWidget(
      _wrap(
        ImmersiveIntersectionStatement(
          reason: _reason(
            actionHints: [
              intersectionActionHintFixture(
                actionKey: 'follow_object',
                label: '关注对象',
                dispatch: 'navigate',
                isPrimary: false,
                priority: 0,
                target: intersectionTargetFixture(
                  objectType: 'homepage',
                  objectId: 'hp_huanglong',
                  objectKind: 'place',
                  routeId: 'homepageDetail',
                ),
              ),
              _gatheringHint(),
            ],
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('immersive-intersection-action')),
      findsNothing,
    );
    expect(find.textContaining(_primaryText), findsOneWidget);
    expect(find.text('发起聚集'), findsNothing);
    expect(find.text('关注对象'), findsNothing);
  });
}
