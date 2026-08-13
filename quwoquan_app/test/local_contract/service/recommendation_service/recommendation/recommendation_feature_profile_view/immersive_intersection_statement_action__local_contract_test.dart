import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/immersive_intersection_statement.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

/// 交集 CTA 一级化（intersection-unified-experience REQ-009 · 牵线搭桥 UX 总纲）：
/// 沉浸单句尾部最多渲染一个主行动 pill——
/// - 主行动选择走七触点共用口径 `primaryDisplayableIntersectionActionHint`
///   （isPrimary 优先，其次 priority 最小；不可渲染 hint 全部丢弃）；
/// - pill 文案只用云侧 `hint.label`，端不造行动文案；
/// - 未提供 onActionHintTap（旧触点）或无可渲染 hint 时不出现 pill，
///   保持「一句主句 + 一个主动作」上限，禁止第二动作。
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
  testWidgets('gathering 主行动 → 单句尾部渲染一个可点 pill，文案为云侧 label', (
    tester,
  ) async {
    IntersectionActionHint? tapped;
    await tester.pumpWidget(
      _wrap(
        ImmersiveIntersectionStatement(
          reason: _reason(actionHints: [_gatheringHint()]),
          onActionHintTap: (hint) => tapped = hint,
        ),
      ),
    );
    expect(
      find.byKey(const ValueKey('immersive-intersection-action')),
      findsOneWidget,
    );
    expect(find.text('发起聚集'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('immersive-intersection-action')),
    );
    expect(tapped, isNotNull);
    expect(tapped!.actionKey, 'start_gathering');
  });

  testWidgets('未接 onActionHintTap 的旧触点 → 不渲染 pill', (tester) async {
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
          onActionHintTap: (_) {},
        ),
      ),
    );
    expect(
      find.byKey(const ValueKey('immersive-intersection-action')),
      findsNothing,
    );
    expect(find.textContaining(_primaryText), findsOneWidget);
  });

  testWidgets('多个可渲染 hint → 只渲染一个主行动（isPrimary 优先）', (tester) async {
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
          onActionHintTap: (_) {},
        ),
      ),
    );
    expect(
      find.byKey(const ValueKey('immersive-intersection-action')),
      findsOneWidget,
    );
    expect(find.text('发起聚集'), findsOneWidget);
    expect(find.text('关注对象'), findsNothing);
  });
}
