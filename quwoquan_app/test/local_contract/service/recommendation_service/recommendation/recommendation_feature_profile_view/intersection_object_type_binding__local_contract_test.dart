import 'package:flutter_test/flutter_test.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/generated/intersection_client_policy.g.dart';
import 'package:quwoquan_app/runtime/di/navigation/intersection_target_navigator.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 对象页把 objectType 翻译成 objectKind 的那段逻辑，曾经是端上一段手写 switch，
/// 只认 user / circle / homepage 三个字面量。博物馆、古镇、交通枢纽这些垂类主页
/// 落进 default：objectKind 为空、routeId 为空，交集行点不动；而云侧同名的一段
/// switch 又把它们当成人物，于是「共同点」还会说成「同好」。
///
/// 现在这层翻译只有一个真相源：intersection_kind_registry.yaml 的
/// objectTypeBindings，经 codegen 落成 [intersectionObjectKindForObjectType]。
/// 新增一个垂类主页只改注册表，端上不再需要发版。
void main() {
  // 旧 switch 一个都不认的地点类垂类；它们必须读成 place 并落主页详情。
  const placeHomepageTypes = <String>[
    'ancient_town',
    'check_in_spot',
    'city',
    'heritage_site',
    'hot_spring',
    'hotel',
    'museum',
    'natural_landscape',
    'park',
    'religious_site',
    'restaurant',
    'theme_park',
    'transport_hub',
    'sight',
    'travel_photo',
  ];

  group('objectType → objectKind（注册表 objectTypeBindings 查表）', () {
    test('垂类主页读成 place，而不是落空或被当成人物', () {
      for (final objectType in placeHomepageTypes) {
        expect(
          intersectionObjectKindForObjectType(objectType),
          IntersectionObjectKind.place,
          reason: '$objectType 应读成 place',
        );
      }
    });

    test('大学读成 school，车型读成 gear，各自保留自己的语义', () {
      expect(
        intersectionObjectKindForObjectType('university'),
        IntersectionObjectKind.school,
      );
      expect(
        intersectionObjectKindForObjectType('school'),
        IntersectionObjectKind.school,
      );
      expect(
        intersectionObjectKindForObjectType('vehicle'),
        IntersectionObjectKind.gear,
      );
      expect(
        intersectionObjectKindForObjectType('gear'),
        IntersectionObjectKind.gear,
      );
      expect(
        intersectionObjectKindForObjectType('route'),
        IntersectionObjectKind.route,
      );
      expect(
        intersectionObjectKindForObjectType('photo_spot'),
        IntersectionObjectKind.photoSpot,
      );
    });

    test('人与圈子不受影响', () {
      expect(
        intersectionObjectKindForObjectType('user'),
        IntersectionObjectKind.person,
      );
      expect(
        intersectionObjectKindForObjectType('person'),
        IntersectionObjectKind.person,
      );
      expect(
        intersectionObjectKindForObjectType('circle'),
        IntersectionObjectKind.circle,
      );
    });

    test('未登记 objectType 查空，端据此降级而不是默认当人物', () {
      for (final objectType in <String>['', '   ', 'musuem', 'not_a_type']) {
        expect(intersectionObjectKindForObjectType(objectType), isNull);
      }
    });

    test('两侧留白不影响查表', () {
      expect(
        intersectionObjectKindForObjectType('  museum  '),
        IntersectionObjectKind.place,
      );
    });
  });

  group('objectType → 可点击落点', () {
    test('垂类主页跳主页详情，不再跳个人主页', () {
      for (final objectType in placeHomepageTypes) {
        final objectKind = intersectionObjectKindForObjectType(objectType)!;
        final routeId = intersectionRouteIdForObjectKind(objectKind);
        expect(routeId, 'homepageDetail', reason: '$objectType 落点应是主页详情');

        final path = IntersectionTargetNavigator.resolvePath(
          intersectionTargetFixture(
            objectId: 'h_$objectType',
            objectKind: objectKind.wireName,
            routeId: routeId,
          ),
        );
        expect(path, isNotNull);
        expect(path, contains('h_$objectType'));
        expect(path, isNot(contains('/user/')));
      }
    });

    test('未登记 objectType 不可路由，而不是错误地跳到某个页面', () {
      final objectKind = intersectionObjectKindForObjectType('not_a_type');
      expect(objectKind, isNull);
      expect(
        IntersectionTargetNavigator.resolvePath(
          intersectionTargetFixture(
            objectId: 'h_unknown',
            objectKind: '',
            routeId: '',
          ),
        ),
        isNull,
      );
    });
  });

  group('objectTypeForTarget（导航/埋点用的粗粒度桶）', () {
    test('垂类主页统一归到 homepage 桶，人物仍是 user', () {
      expect(
        IntersectionTargetNavigator.objectTypeForTarget(
          objectKind: 'place',
          routeId: 'homepageDetail',
        ),
        'homepage',
      );
      expect(
        IntersectionTargetNavigator.objectTypeForTarget(
          objectKind: 'person',
          routeId: 'userProfile',
        ),
        'user',
      );
    });
  });
}
