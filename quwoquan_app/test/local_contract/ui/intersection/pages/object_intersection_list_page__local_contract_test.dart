/// N1 标准化（断点4）：对象页交集全量列表行点击统一经 IntersectionTargetNavigator，
/// 端不再手写 `switch(kind) → context.push(AppRoutePaths.*)` 复制导航逻辑
/// （消除第二导航真相源 · §20.7 统一交互子契约）。
///
/// 覆盖：
/// - IntersectionTargetNavigator.targetForReason：actionTargetId/objectKind 归一为统一 target；
/// - §23 去桥接：objectKind 一等字段为对象类型唯一真相源，relationKind 旧词桥接已删除，
///   objectKind 缺省时不再回写对象类型（优雅降级为不可路由，而非伪造闭集值）；
/// - 归一 target 经 IntersectionTargetNavigator.resolvePath 命中正确 codegen 路由
///   （person→userProfile / circle→circleDetail / place|school|enterprise→homepageDetail），
///   证明删手写 switch 后导航行为零回归。
library;

import 'package:flutter_test/flutter_test.dart';
import '../../../../support/fixtures/intersection_fixtures.dart';
import 'package:quwoquan_app/recommendation/recommendation/recommendation_feature_profile_view/presentation/intersection_target_navigator.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('IntersectionTargetNavigator.targetForReason（交集行 → 统一导航 target）', () {
    test('objectKind 闭集直出（person/circle/place）', () {
      final person = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(
          actionTargetId: 'u_lin',
          objectKind: 'person',
        ),
      );
      expect(person.objectId, 'u_lin');
      expect(person.objectKind, 'person');

      final circle = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(
          actionTargetId: 'c_ride',
          objectKind: 'circle',
        ),
      );
      expect(circle.objectKind, 'circle');

      final place = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(
          actionTargetId: 'p_west',
          objectKind: 'place',
        ),
      );
      expect(place.objectKind, 'place');
    });

    test('objectKind 缺省 → 不再 relationKind 桥接（对象类型为空，优雅降级不误路由）', () {
      // §23 去桥接：relationKind 不再回写对象类型；objectKind 缺省即保持空，
      // 由 resolvePath 判定不可路由（优雅降级），不再伪造 person/place/enterprise。
      final viaRelationKind = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(actionTargetId: 'u1', relationKind: 'mutual'),
      );
      expect(viaRelationKind.objectKind, '');
      expect(IntersectionTargetNavigator.resolvePath(viaRelationKind), isNull);
    });

    test('actionTargetId 两端空白裁剪', () {
      final t = IntersectionTargetNavigator.targetForReason(
        intersectionReasonFixture(
          actionTargetId: '  u2  ',
          objectKind: 'person',
        ),
      );
      expect(t.objectId, 'u2');
    });
  });

  group('归一 target 经统一导航器命中正确 codegen 路由（删手写 switch 零回归）', () {
    String? pathFor(IntersectionReason reason) =>
        IntersectionTargetNavigator.resolvePath(
          IntersectionTargetNavigator.targetForReason(reason),
        );

    test('person → userProfile', () {
      expect(
        pathFor(
          intersectionReasonFixture(
            actionTargetId: 'u_lin',
            objectKind: 'person',
          ),
        ),
        contains('u_lin'),
      );
    });

    test('circle → circleDetail', () {
      expect(
        pathFor(
          intersectionReasonFixture(
            actionTargetId: 'c_ride',
            objectKind: 'circle',
          ),
        ),
        contains('c_ride'),
      );
    });

    test('place/school/enterprise → homepageDetail', () {
      for (final kind in const <String>['place', 'school', 'enterprise']) {
        expect(
          pathFor(
            intersectionReasonFixture(
              actionTargetId: 'h_$kind',
              objectKind: kind,
            ),
          ),
          contains('h_$kind'),
          reason: '$kind 应映射到实体主页路由',
        );
      }
    });

    test('actionTargetId 空 → 不可路由（优雅降级，不跳转）', () {
      expect(
        pathFor(
          intersectionReasonFixture(actionTargetId: '', objectKind: 'person'),
        ),
        isNull,
      );
    });
  });
}
