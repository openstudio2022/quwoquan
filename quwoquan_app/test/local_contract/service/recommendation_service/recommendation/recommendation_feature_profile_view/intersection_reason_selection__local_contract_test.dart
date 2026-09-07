// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-003.t2
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/home-recommend-intersection-redesign/spec.md#gwt-001.t3
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_reason_selection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

void main() {
  final postTarget = intersectionTargetFixture(
    objectType: 'post',
    objectId: 'post-1',
    objectKind: 'content',
    routeId: 'workBrowser',
  );
  final placeTarget = intersectionTargetFixture(
    objectType: 'homepage',
    objectId: 'place-1',
    objectKind: 'place',
    routeId: 'homepageDetail',
  );

  IntersectionReason reason({
    required String id,
    String text = '你们都想去西湖',
    String expiresAt = '',
    List<IntersectionActionHint> hints = const <IntersectionActionHint>[],
  }) => intersectionReasonFixture(
    intersectionId: id,
    kind: 'coWishlistedEntity',
    dimension: 'location',
    objectKind: 'place',
    actionTargetId: 'place-1',
    primaryText: text,
    primarySpans: <IntersectionTextSpan>[
      intersectionTextSpanFixture(
        text: text,
        role: 'object',
        target: placeTarget,
      ),
    ],
    expiresAt: expiresAt,
    actionHints: hints,
  );

  test('坏第一条会跳过并选择有效第二条', () {
    final resolution = resolveIntersectionDisplay(<IntersectionReason>[
      reason(id: 'bad', text: ''),
      reason(id: 'good'),
    ]);
    expect(resolution?.reason.intersectionId, 'good');
  });

  test('过期 reason、未知 dispatch 与缺 target 不会暴露 action', () {
    final expired = resolveIntersectionDisplay(<IntersectionReason>[
      reason(id: 'expired', expiresAt: '2026-01-01T00:00:00Z'),
      reason(
        id: 'active',
        hints: <IntersectionActionHint>[
          intersectionActionHintFixture(
            actionKey: 'start_gathering',
            label: '一起去看看',
            isPrimary: true,
            dispatch: 'unknown',
          ),
          intersectionActionHintFixture(
            actionKey: 'start_gathering',
            label: '一起去看看',
            priority: 2,
            dispatch: 'gathering',
          ),
        ],
      ),
    ], now: DateTime.utc(2026, 9, 5));
    expect(expired?.reason.intersectionId, 'active');
    expect(expired?.primaryHint, isNull);
  });

  test('自宿主 open_content 被拒绝，唯一有效 typed action 胜出', () {
    final resolution = resolveIntersectionDisplay(<IntersectionReason>[
      reason(
        id: 'mixed',
        hints: <IntersectionActionHint>[
          intersectionActionHintFixture(
            actionKey: 'open_content',
            label: '查看内容',
            target: postTarget,
            isPrimary: true,
            dispatch: 'navigate',
          ),
          intersectionActionHintFixture(
            actionKey: 'start_gathering',
            label: '一起去看看',
            target: placeTarget,
            priority: 2,
            dispatch: 'gathering',
          ),
        ],
      ),
    ], contextObjectTarget: postTarget);
    expect(resolution?.primaryHint?.actionKey, 'start_gathering');
    expect(resolution?.primaryHint?.target?.objectId, 'place-1');
  });
  test('route/objectKind 漂移与缺 objectType 会 fail-closed', () {
    final resolution = resolveIntersectionDisplay(<IntersectionReason>[
      reason(
        id: 'drift',
        hints: <IntersectionActionHint>[
          intersectionActionHintFixture(
            actionKey: 'start_gathering',
            label: '错误路线',
            isPrimary: true,
            dispatch: 'gathering',
            target: intersectionTargetFixture(
              objectType: 'homepage',
              objectId: 'place-1',
              objectKind: 'place',
              routeId: 'userProfile',
            ),
          ),
          intersectionActionHintFixture(
            actionKey: 'open_object',
            label: '缺类型',
            dispatch: 'navigate',
            priority: 1,
            target: intersectionTargetFixture(
              objectId: 'place-1',
              objectKind: 'place',
              routeId: 'homepageDetail',
            ),
          ),
        ],
      ),
    ]);
    expect(resolution?.primaryHint, isNull);
  });

  test('school/route/gear 等收口到 homepage 的 canonical target 不被误拒', () {
    // objectTypeBindings 是多对一（homepage → place），不能反查判等；kind → wire objectType
    // 才是单射。云侧按注册表下发 {objectType: homepage, objectKind: school} 必须可执行。
    for (final kind in <String>['school', 'enterprise', 'route', 'photo_spot', 'gear', 'entity']) {
      final resolution = resolveIntersectionDisplay(<IntersectionReason>[
        reason(
          id: 'canonical-$kind',
          hints: <IntersectionActionHint>[
            intersectionActionHintFixture(
              actionKey: 'start_gathering',
              label: '一起去',
              isPrimary: true,
              dispatch: 'gathering',
              target: intersectionTargetFixture(
                objectType: 'homepage',
                objectId: 'hp-$kind',
                objectKind: kind,
                routeId: 'homepageDetail',
              ),
            ),
          ],
        ),
      ], contextObjectTarget: postTarget);
      expect(resolution?.primaryHint?.actionKey, 'start_gathering', reason: kind);
      expect(resolution?.primaryHint?.target?.objectKind, kind);
    }
    // objectType 与 kind 登记不符（person 却写 homepage）仍 fail-closed。
    final drift = resolveIntersectionDisplay(<IntersectionReason>[
      reason(
        id: 'type-drift',
        hints: <IntersectionActionHint>[
          intersectionActionHintFixture(
            actionKey: 'message_person',
            label: '打招呼',
            isPrimary: true,
            dispatch: 'message',
            target: intersectionTargetFixture(
              objectType: 'homepage',
              objectId: 'u-1',
              objectKind: 'person',
              routeId: 'userProfile',
            ),
          ),
        ],
      ),
    ], contextObjectTarget: postTarget);
    expect(drift?.primaryHint, isNull);
  });

  test('message 分发的人对象也要通过注册表路由校验，routeId 冒充 userProfile 被拒', () {
    final drift = resolveIntersectionDisplay(<IntersectionReason>[
      reason(
        id: 'message-route-drift',
        hints: <IntersectionActionHint>[
          intersectionActionHintFixture(
            actionKey: 'message_person',
            label: '打招呼',
            isPrimary: true,
            dispatch: 'message',
            target: intersectionTargetFixture(
              objectType: 'circle',
              objectId: 'c-1',
              objectKind: 'circle',
              routeId: 'userProfile',
            ),
          ),
        ],
      ),
    ], contextObjectTarget: postTarget);
    expect(drift?.primaryHint, isNull);
    final person = resolveIntersectionDisplay(<IntersectionReason>[
      reason(
        id: 'message-person',
        hints: <IntersectionActionHint>[
          intersectionActionHintFixture(
            actionKey: 'message_person',
            label: '打招呼',
            isPrimary: true,
            dispatch: 'message',
            target: intersectionTargetFixture(
              objectType: 'user',
              objectId: 'u-1',
              objectKind: 'person',
              routeId: 'userProfile',
            ),
          ),
        ],
      ),
    ], contextObjectTarget: postTarget);
    expect(person?.primaryHint?.actionKey, 'message_person');
  });
}
