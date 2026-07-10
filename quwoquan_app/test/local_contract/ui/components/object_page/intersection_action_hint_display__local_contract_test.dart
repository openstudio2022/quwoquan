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
/// - message / connect：端侧尚无真实私信/心动破冰状态机 → 不渲染（不伪造重社交行动）；
/// - deferred / 空 label / 无 target（navigate/companion/commerce）：不渲染（优雅降级）。
IntersectionActionHint _hint({
  required String dispatch,
  String label = '行动',
  String targetAvailability = 'available',
  bool withTarget = true,
}) {
  return IntersectionActionHint(
    actionKey: '${dispatch}_key',
    label: label,
    dispatch: dispatch,
    targetAvailability: targetAvailability,
    target: withTarget
        ? IntersectionTarget(objectId: 'p_west_lake', objectKind: 'place')
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

    test('companion + available + target → 渲染「发起结伴」（C0 北极星闭环）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'companion', label: '发起结伴'),
        ),
        isTrue,
      );
    });

    test('companion + deferred → 不渲染（承接未就绪，不伪造成行）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'companion', targetAvailability: 'deferred'),
        ),
        isFalse,
      );
    });

    test('companion + 无 target → 不渲染（无约伴对象上下文，不做空发起）', () {
      expect(
        isDisplayableIntersectionActionHint(
          _hint(dispatch: 'companion', withTarget: false),
        ),
        isFalse,
      );
    });

    test('message / connect → 不渲染（端无真实破冰 handler，诚实红线）', () {
      for (final dispatch in <String>['message', 'connect']) {
        expect(
          isDisplayableIntersectionActionHint(_hint(dispatch: dispatch)),
          isFalse,
          reason: '$dispatch 不得渲染成可点 pill',
        );
      }
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
