import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/components/object_page/intersection_statement_row.dart';

/// T2：`isDisplayableIntersectionActionHint` 诚实红线判据契约（§24.10 + M0.7 dispatch）。
///
/// 这是「哪些行动会渲染成可点 pill」的唯一真相源，必须与
/// `IntersectionTargetNavigator.openActionHint` 的分发能力口径一致：
/// - assistant / navigate / companion：端侧有真实承接 → 可渲染；
/// - commerce：默认 feature flag 关闭不渲染；显式开启且有 target 才可渲染；
/// - message：承接是主页上的打招呼→同意→私信状态机（POST /user/greeting-request
///   → reply 升级为正式会话），target 是真实 person 时可渲染；非 person 不渲染，
///   避免「打招呼」退化成对象下钻；
/// - connect：话题房 / 语音房没有落地页，注册表里该类别成员全是 deferred，
///   端对无落点的 dispatch fail-closed → 不渲染；
/// - deferred / 空 label / 无 target（navigate/companion/commerce）：不渲染（优雅降级）。
IntersectionActionHint _hint({
  required String dispatch,
  String label = '行动',
  String targetAvailability = 'available',
  bool withTarget = true,
  String objectKind = 'place',
}) {
  return IntersectionActionHint(
    actionKey: '${dispatch}_key',
    label: label,
    dispatch: dispatch,
    targetAvailability: targetAvailability,
    target: withTarget
        ? IntersectionTarget(objectId: 'p_west_lake', objectKind: objectKind)
        : null,
  );
}

void main() {
  group('isDisplayableIntersectionActionHint · 可执行 pill 渲染闸', () {
    test('assistant → 渲染（打开小艺，无需 target）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'assistant', withTarget: false),
        ),
        isTrue,
      );
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

    test('gathering + available + target → 渲染「发起结伴」（C0 北极星闭环）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'gathering', label: '发起结伴'),
        ),
        isTrue,
      );
    });

    test('gathering + deferred → 不渲染（承接未就绪，不伪造成行）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'gathering', targetAvailability: 'deferred'),
        ),
        isFalse,
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

    test('connect → 不渲染（话题房/语音房无落地页，端对无落点 dispatch fail-closed）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'connect', label: '进话题群'),
        ),
        isFalse,
      );
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'connect', label: '进话题群', objectKind: 'person'),
        ),
        isFalse,
      );
    });

    test('commerce 默认不渲染；显式开启且有 target 才渲染', () {
      final hint = _hint(dispatch: 'commerce', label: '看官方优惠');
      expect(isDisplayableIntersectionActionHint(hint), isFalse);
      expect(
        isDisplayableIntersectionActionHint(hint, commerceActionsEnabled: true),
        isTrue,
      );
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'commerce', withTarget: false),
          commerceActionsEnabled: true,
        ),
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

    test('deferred 优先于 dispatch：assistant + deferred 也不渲染', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'assistant', targetAvailability: 'deferred'),
        ),
        isFalse,
      );
    });
  });
}
