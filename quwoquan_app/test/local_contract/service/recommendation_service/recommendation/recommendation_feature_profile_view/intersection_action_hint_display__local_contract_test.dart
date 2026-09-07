// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003.t3
import 'package:flutter_test/flutter_test.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_reason_selection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// T2：`isDisplayableIntersectionActionHint` 诚实红线判据契约（§24.10 + M0.7 dispatch）。
///
/// 这是「哪些行动会渲染成可点 pill」的唯一真相源，必须与
/// `IntersectionTargetNavigator.openActionHint` 的分发能力口径一致，且只认
/// generated registry 里登记的 actionKey / dispatch / objectKind / routeId：
/// - assistant / navigate / gathering：端侧有真实承接 → 可渲染；
/// - message：承接是主页上的打招呼→同意→私信状态机（POST /user/greeting-request
///   → reply 升级为正式会话），target 是真实 person 时可渲染；非 person 不渲染，
///   避免「打招呼」退化成对象下钻；
/// - 未登记 actionKey/dispatch、dispatch 与注册表不符、空 label、无 target
///   （navigate/gathering）：不渲染。
const _actionKeyByDispatch = <String, String>{
  'assistant': 'ask_assistant',
  'navigate': 'open_object',
  'gathering': 'start_gathering',
  'message': 'message_person',
};

IntersectionActionHint _hint({
  required String dispatch,
  String label = '行动',
  bool withTarget = true,
  String objectKind = 'place',
  String? actionKey,
}) {
  final isPerson = objectKind == 'person';
  return intersectionActionHintFixture(
    actionKey: actionKey ?? _actionKeyByDispatch[dispatch] ?? '${dispatch}_key',
    label: label,
    dispatch: dispatch,
    target: withTarget
        ? intersectionTargetFixture(
            objectType: isPerson ? 'user' : 'homepage',
            objectId: 'p_west_lake',
            objectKind: objectKind,
            routeId: isPerson ? 'userProfile' : 'homepageDetail',
          )
        : null,
  );
}

void main() {
  group('isDisplayableIntersectionActionHint · 可执行 pill 渲染闸', () {
    test('assistant → 只在证据快照与上下文对象齐备时渲染（与 navigator 前置条件同源）', () {
      final hint = _hint(dispatch: 'assistant', withTarget: false);
      final host = intersectionTargetFixture(
        objectType: 'post',
        objectId: 'post-1',
        objectKind: 'content',
        routeId: 'workBrowser',
      );
      final withEvidence = intersectionReasonFixture(
        kind: 'followeeViewing',
        intersectionId: 'ix-1',
        pointSummarySnapshotId: 'snap-1',
      );
      // 有宿主 + 有证据快照 → 渲染。
      expect(
        isDisplayableIntersectionActionHint(
          hint,
          contextObjectTarget: host,
          evidenceReason: withEvidence,
        ),
        isTrue,
      );
      // 无宿主（收件箱）时以 reason 自身对象作上下文：对象非空即可渲染。
      expect(
        isDisplayableIntersectionActionHint(
          hint,
          evidenceReason: intersectionReasonFixture(
            kind: 'followeeViewing',
            intersectionId: 'ix-1',
            pointSummarySnapshotId: 'snap-1',
            objectKind: 'content',
            actionTargetId: 'post-9',
          ),
        ),
        isTrue,
      );
      // 缺证据快照 → navigator 会返回 missingTarget，展示门同样 fail-closed。
      expect(
        isDisplayableIntersectionActionHint(
          hint,
          contextObjectTarget: host,
          evidenceReason: intersectionReasonFixture(
            kind: 'followeeViewing',
            intersectionId: 'ix-1',
          ),
        ),
        isFalse,
      );
      // 没有 reason → 不渲染。
      expect(isDisplayableIntersectionActionHint(hint), isFalse);
    });

    test('navigate + target → 渲染；无 target → 不渲染', () {
      expect(
        isDisplayableIntersectionActionHint(_hint(dispatch: 'navigate')),
        isTrue,
      );
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'navigate', withTarget: false),
        ),
        isFalse,
      );
    });

    test('gathering + target → 渲染「发起结伴」（C0 北极星闭环）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'gathering', label: '发起结伴'),
        ),
        isTrue,
      );
    });

    test('gathering + 无 target → 不渲染（无约伴对象上下文，不做空发起）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'gathering', withTarget: false),
        ),
        isFalse,
      );
    });

    test('message + person target → 渲染（承接是主页打招呼→同意→私信状态机）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'message', label: '打招呼', objectKind: 'person'),
        ),
        isTrue,
      );
    });

    test('message + 非 person target → 不渲染（打招呼不得退化成对象下钻）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'message', label: '打招呼'),
        ),
        isFalse,
      );
    });

    test('未登记 dispatch → 不渲染', () {
      expect(
        isDisplayableIntersectionActionHint(_hint(dispatch: 'unknown')),
        isFalse,
      );
    });

    test('空 label → 不渲染（无可读行动文案）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'assistant', label: '   '),
        ),
        isFalse,
      );
    });
  });
}
