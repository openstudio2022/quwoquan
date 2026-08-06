import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/generated/intersection_display_metadata.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_fact_items.dart';

import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

/// T1：交集展示的端侧单源合约。
///
/// 端侧不再合成任何交集文案——主句、称谓、维度弱标、行动标签全部由云侧按
/// `intersection_kind_registry.yaml` 渲染后逐条下发。本文件因此只证明两件事：
/// - 端侧拿到没有主句的 reason 时**不补写**，而是拒绝展示（fail-closed，不编造）；
/// - 逐 kind 的端侧本地元数据已收敛到视觉兜底（iconKey/tone），未登记 kind 返回 null。
void main() {
  IntersectionReason reason({
    required String kind,
    String dimension = 'relationship',
    required String objectName,
    String objectId = '',
    required String objectKind,
    int count = 0,
    String primaryText = '',
    String? repName,
    String? repId,
    String repPrivacy = 'visible',
    List<IntersectionTextSpan> primarySpans = const <IntersectionTextSpan>[],
  }) {
    return intersectionReasonFixture(
      kind: kind,
      dimension: dimension,
      intersectionId: 'ix_test',
      intersectionClass: 'fact',
      displayName: objectName,
      objectKind: objectKind,
      actionTargetId: objectId,
      totalPointCount: count,
      source: kind,
      primaryText: primaryText,
      primarySpans: primarySpans,
      intersectionPoints: <IntersectionPoint>[
        intersectionPointFixture(
          pointId: 'p',
          pointClass: 'fact',
          sourceRef: kind,
          count: count,
          dimension: dimension,
          label: '',
          displayText: '',
          visibility: 'public',
          sampleText: '',
          sampleAvatarUrls: const <String>[],
          sampleVisuals: const <IntersectionVisual>[],
        ),
      ],
      representativeActor: repName == null
          ? null
          : intersectionRepresentativeActorFixture(
              actorId: repId ?? '',
              displayName: repName,
              avatarUrl: '',
              relationLabel: '',
              privacyState: repPrivacy,
              target: repId == null
                  ? null
                  : intersectionTargetFixture(
                      objectType: 'user',
                      objectId: repId,
                      objectKind: 'person',
                      routeId: 'userProfile',
                    ),
              evidenceRank: 1,
              snapshotVersion: 'intersection_fixture',
            ),
    );
  }

  group('端侧不合成交集文案', () {
    test('云侧未下发主句时，端侧不补写也不展示', () {
      final r = reason(
        kind: 'sharedFollowees',
        objectName: '林清越',
        objectId: 'u_lin',
        objectKind: 'person',
        count: 4,
      );
      expect(r.primaryText, isEmpty);
      expect(displayReadyIntersectionReason(r), isNull);
    });

    test('云侧主句原样透出，端侧既不改写也不补 spans', () {
      final r = reason(
        kind: 'sharedFollowees',
        objectName: '林清越',
        objectId: 'u_lin',
        objectKind: 'person',
        count: 4,
        primaryText: '林清越也关注胶片摄影',
        repName: '林清越',
        repId: 'u_lin',
      );
      final ready = displayReadyIntersectionReason(r);
      expect(ready?.primaryText, r.primaryText);
      expect(ready?.primarySpans, isEmpty);
    });

    test('数量型主句缺代表人时 fail-closed，不靠端侧编一个出来', () {
      final r = reason(
        kind: 'sharedFollowees',
        objectName: '林清越',
        objectId: 'u_lin',
        objectKind: 'person',
        count: 4,
        primaryText: '4位你关注的人也关注了林清越',
      );
      expect(displayReadyIntersectionReason(r), isNull);
    });
  });

  group('共同点计数真相取 point.count', () {
    test('mutualCount 缺省时回退首个 point.count', () {
      final r = reason(
        kind: 'coVisitedEntity',
        dimension: 'location',
        objectName: '西湖',
        objectId: 'place_xihu',
        objectKind: 'place',
        count: 5,
      );
      expect(intersectionMutualCountOf(r), 5);
    });
  });

  group('逐 kind 端侧元数据只剩视觉兜底', () {
    test('kind → iconKey 由 codegen 单一真相源驱动', () {
      expect(IntersectionKindDisplayMetadata.of('sharedFollowees')!.iconKey, 'people');
      expect(IntersectionKindDisplayMetadata.of('commonFollower')!.iconKey, 'people');
      expect(IntersectionKindDisplayMetadata.of('coVisitedEntity')!.iconKey, 'place');
      expect(
        IntersectionKindDisplayMetadata.of('followeeVisited')!.iconKey,
        'placeHere',
      );
      expect(IntersectionKindDisplayMetadata.of('sharedCircle')!.iconKey, 'circle');
    });

    test('未登记 kind 返回 null，端据此安全降级', () {
      expect(IntersectionKindDisplayMetadata.of('unknown_future_kind'), isNull);
      // 维度名不是 kind：source 退化成维度名时不得被误当 kind 查表。
      expect(IntersectionKindDisplayMetadata.of('relationship'), isNull);
      expect(intersectionFallbackIconKeyByDimension[IntersectionDimension.relationship], isNotEmpty);
    });
  });
}
