import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/fixtures/intersection_fixtures.dart';

/// Canonical IntersectionReason wire contract.
///
/// The retired permissive DTO accepted partial maps and silently synthesized
/// defaults. The generated owner now rejects missing or unknown fields.
void main() {
  const pkuTarget = IntersectionTarget(
    objectType: 'homepage',
    objectId: 'homepage_pku',
    objectKind: 'school',
    routeId: 'homepageDetail',
  );

  group('IntersectionReason canonical wire', () {
    test('strict fromWire decodes the complete generated shape', () {
      final source = intersectionReasonFixture(
        dimension: 'identity',
        tagRefs: const <String>['Entity/机构/学校/北京大学'],
        displayName: '北京大学',
        totalPointCount: 3,
        strength: 0.9,
        primaryText: '推荐你了解北京大学',
        primarySpans: const <IntersectionTextSpan>[
          IntersectionTextSpan(text: '推荐你了解', role: 'plain'),
          IntersectionTextSpan(text: '北京大学', role: 'object', target: pkuTarget),
        ],
        actionType: 'view_object',
        actionTargetId: 'homepage_pku',
        source: 'entityRef',
      );

      final reason = IntersectionReason.fromWire(source.toWire());
      expect(reason.dimension, 'identity');
      expect(reason.tagRefs, <String>['Entity/机构/学校/北京大学']);
      expect(reason.displayName, '北京大学');
      expect(reason.totalPointCount, 3);
      expect(reason.strength, 0.9);
      expect(reason.primaryText, '推荐你了解北京大学');
      expect(reason.primarySpans.last.target?.objectType, 'homepage');
      expect(reason.actionType, 'view_object');
      expect(reason.source, 'entityRef');
    });

    test('missing and unknown fields fail closed', () {
      expect(
        () => IntersectionReason.fromWire(const <String, Object?>{}),
        throwsFormatException,
      );
      final wire = intersectionReasonFixture().toWire()
        ..['retiredDisplayText'] = '禁止兼容';
      expect(() => IntersectionReason.fromWire(wire), throwsFormatException);
    });

    test('five canonical dimensions round-trip without a second decoder', () {
      const dimensions = <String>{
        'identity',
        'location',
        'content',
        'interest',
        'relationship',
      };
      for (final dimension in dimensions) {
        final reason = IntersectionReason.fromWire(
          intersectionReasonFixture(dimension: dimension).toWire(),
        );
        expect(reason.dimension, dimension);
      }
    });

    test(
      'relationship identity remains relationKind plus relationObjectId',
      () {
        final reason = IntersectionReason.fromWire(
          intersectionReasonFixture(
            dimension: 'relationship',
            relationKind: 'mutual',
            relationObjectId: 'user_friend_1',
            primaryText: '你们有共同好友',
          ).toWire(),
        );
        expect(reason.relationKind, 'mutual');
        expect(reason.relationObjectId, 'user_friend_1');
      },
    );

    test('actor evidence and representative actor stay fully typed', () {
      const actorTarget = IntersectionTarget(
        objectType: 'user',
        objectId: 'u_lin',
        objectKind: 'person',
        routeId: 'userProfile',
      );
      const postTarget = IntersectionTarget(
        objectType: 'post',
        objectId: 'post_1',
        objectKind: 'post',
        routeId: 'postDetail',
      );
      final source = intersectionReasonFixture(
        primaryText: '林清越等2位联系人关注了这篇内容',
        actionTargetId: 'post_1',
        representativeActor: const IntersectionRepresentativeActor(
          actorId: 'u_lin',
          displayName: '林清越',
          avatarUrl: '',
          relationLabel: '联系人',
          privacyState: 'visible',
          target: actorTarget,
          evidenceRank: 1,
          snapshotVersion: 'snap_home_1',
        ),
        primarySpans: const <IntersectionTextSpan>[
          IntersectionTextSpan(
            text: '林清越',
            role: 'object',
            target: actorTarget,
          ),
          IntersectionTextSpan(text: '等2位联系人关注了', role: 'plain'),
          IntersectionTextSpan(
            text: '这篇内容',
            role: 'object',
            target: postTarget,
          ),
        ],
        actorEvidenceTotalCount: 2,
        actorEvidenceCompleteness: 'complete',
        actorEvidence: const <IntersectionActorEvidence>[
          IntersectionActorEvidence(
            actorId: 'u_lin',
            displayName: '林清越',
            avatarUrl: '',
            relationLabel: '联系人',
            relationSourceRef: 'contact',
            relationObjectId: '',
            relationObjectName: '',
            sourcePointId: 'p_contact',
            sourceRef: 'commonContact',
            actionSummaryText: '点赞了这条记录',
            likeCount: 1,
            commentCount: 0,
            shareCount: 0,
            privacyState: 'visible',
            target: actorTarget,
            evidenceRank: 5,
            snapshotVersion: 'snap_home_1',
            sortKey: 1,
          ),
          IntersectionActorEvidence(
            actorId: 'u_zhou',
            displayName: '周屿',
            avatarUrl: '',
            relationLabel: '你关注的人',
            relationSourceRef: 'followee',
            relationObjectId: '',
            relationObjectName: '',
            sourcePointId: 'p_followee',
            sourceRef: 'sharedFollowees',
            actionSummaryText: '评论了这条记录',
            likeCount: 0,
            commentCount: 1,
            shareCount: 0,
            privacyState: 'visible',
            evidenceRank: 10,
            snapshotVersion: 'snap_home_1',
            sortKey: 2,
          ),
        ],
      );

      final reason = IntersectionReason.fromWire(source.toWire());
      expect(reason.actorEvidence, hasLength(2));
      expect(reason.actorEvidence.first.likeCount, 1);
      expect(reason.actorEvidence.last.commentCount, 1);
      expect(reason.representativeActor?.displayName, '林清越');
      expect(
        reason.primarySpans.map((span) => span.text).join(),
        reason.primaryText,
      );
    });

    test('toWire round-trip preserves the canonical fields', () {
      final source = intersectionReasonFixture(
        dimension: 'interest',
        tagRefs: const <String>['Topic/摄影'],
        displayName: '摄影',
        primaryText: '你们都爱摄影',
        actionType: 'view_object',
        source: 'tagRef',
      );
      final restored = IntersectionReason.fromWire(source.toWire());
      expect(restored.toWire(), source.toWire());
    });
  });
}
