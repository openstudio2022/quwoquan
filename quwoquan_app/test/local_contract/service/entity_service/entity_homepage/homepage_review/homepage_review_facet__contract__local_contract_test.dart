/// L1a Entity/HomepageReview：alpha facet 行为与 api_integration 验证的
/// 服务端语义同构（一人一评、软删复活、作者独占、摘要真实重算）。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_review/application/public/homepage_review_operation_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage_review/homepage_review_facets_typed_double.dart';
import '../../../../../support/service/user_service/relationship/subject_follow/subject_follow_typed_double.dart';

void main() {
  group('InMemoryHomepageReviewFacet — 服务端同构合同', () {
    test('创建后进入列表且摘要真实重算', () async {
      final facet = InMemoryHomepageReviewFacet();
      final created = await facet.create(
        CreateHomepageReviewCommand(
          homepageId: 'hp-1',
          rating: 5,
          body: '很棒',
          tagRefs: const <String>['publish/tags/scenery'],
        ),
      );
      expect(created.status, HomepageReviewStatus.active);
      expect(created.rating, 5);

      final page = await facet.listByHomepage(
        HomepageReviewListQuery(homepageId: 'hp-1'),
      );
      expect(page.items, hasLength(1));
      expect(page.items.single.id, created.id);

      final summary = facet.summarize('hp-1');
      expect(summary.averageRating, 5.0);
      expect(summary.ratingCount, 1);
      expect(summary.highlightTags, contains('publish/tags/scenery'));
    });

    test('同一 persona 重复创建 active 评价被拒（引导走更新）', () async {
      final facet = InMemoryHomepageReviewFacet();
      await facet.create(
        CreateHomepageReviewCommand(homepageId: 'hp-1', rating: 5),
      );
      await expectLater(
        facet.create(
          CreateHomepageReviewCommand(homepageId: 'hp-1', rating: 2),
        ),
        throwsStateError,
      );
    });

    test('更新覆盖内容，删除后列表隐藏、mine 保留供复活预填', () async {
      final facet = InMemoryHomepageReviewFacet();
      final created = await facet.create(
        CreateHomepageReviewCommand(homepageId: 'hp-1', rating: 5, body: '一开始'),
      );
      final updated = await facet.update(
        UpdateHomepageReviewCommand(
          reviewId: created.id,
          rating: 3,
          body: '后来觉得一般',
        ),
      );
      expect(updated.rating, 3);

      await facet.delete(DeleteHomepageReviewCommand(reviewId: created.id));
      final page = await facet.listByHomepage(
        HomepageReviewListQuery(homepageId: 'hp-1'),
      );
      expect(page.items, isEmpty);

      final mine = await facet.getMine(
        MyHomepageReviewQuery(homepageId: 'hp-1'),
      );
      expect(mine.status, HomepageReviewStatus.deleted);

      final summary = facet.summarize('hp-1');
      expect(summary.ratingCount, 0);
      expect(summary.averageRating, isNull);
    });

    test('软删后再次创建复活同一聚合（id 不变、状态回 active）', () async {
      final facet = InMemoryHomepageReviewFacet();
      final created = await facet.create(
        CreateHomepageReviewCommand(homepageId: 'hp-1', rating: 5),
      );
      await facet.delete(DeleteHomepageReviewCommand(reviewId: created.id));
      final revived = await facet.create(
        CreateHomepageReviewCommand(homepageId: 'hp-1', rating: 4, body: '再评'),
      );
      expect(revived.id, created.id);
      expect(revived.status, HomepageReviewStatus.active);
      expect(revived.rating, 4);
    });

    test('从未评价过 getMine 抛出 not found 语义', () async {
      final facet = InMemoryHomepageReviewFacet();
      await expectLater(
        facet.getMine(MyHomepageReviewQuery(homepageId: 'hp-none')),
        throwsA(isA<HomepageReviewNotFoundException>()),
      );
    });
  });

  group('SubjectFollowTypedDouble — set/unset 幂等', () {
    test('follow set 语义与重复 replay', () async {
      final facet = SubjectFollowTypedDouble();
      final first = await facet.follow(
        FollowSubjectCommand(
          subjectType: SubjectFollowTargetKind.homepage,
          subjectId: 'hp-1',
        ),
      );
      expect(first.state, SubjectFollowState.following);
      expect(first.idempotentReplay, isFalse);

      final replay = await facet.follow(
        FollowSubjectCommand(
          subjectType: SubjectFollowTargetKind.homepage,
          subjectId: 'hp-1',
        ),
      );
      expect(replay.idempotentReplay, isTrue);

      final unfollow = await facet.unfollow(
        UnfollowSubjectCommand(
          subjectType: SubjectFollowTargetKind.homepage,
          subjectId: 'hp-1',
        ),
      );
      expect(unfollow.state, SubjectFollowState.unfollowed);
      expect(
        facet.isFollowing(SubjectFollowTargetKind.homepage, 'hp-1'),
        isFalse,
      );
    });
  });

  group('HomepageReview pure contracts — wire 形状', () {
    test('create 命令 encode 只输出 request entity body fields', () {
      final payload =
          encodeEntityHomepageReviewCreateHomepageReviewGeneratedRequest(
            CreateHomepageReviewCommand(
              homepageId: 'hp-1',
              rating: 5,
              body: '很棒',
              tagRefs: const <String>['publish/tags/scenery'],
              authorDisplayNameSnapshot: '趣友甲',
            ),
          );
      expect(payload.pathParameters, {'homepageId': 'hp-1'});
      expect(payload.body, {
        'rating': 5,
        'body': '很棒',
        'tagRefs': ['publish/tags/scenery'],
        'authorDisplayNameSnapshot': '趣友甲',
      });
      // 幂等身份只来自 Idempotency-Key header：body 不携带版本或幂等键。
      expect(payload.body, isNot(contains('idempotencyKey')));
      expect(payload.body, isNot(contains('version')));
    });

    test('view decode 校验 rating 边界与状态枚举', () {
      expect(
        () => decodeHomepageReviewView(<Object?, Object?>{
          'id': 'r1',
          'homepageId': 'hp-1',
          'authorPersonaId': 'p1',
          'rating': 9,
          'status': 'active',
          'createdAt': '2026-07-19T10:00:00Z',
          'updatedAt': '2026-07-19T10:00:00Z',
        }),
        throwsFormatException,
      );
      final view = decodeHomepageReviewView(<Object?, Object?>{
        'id': 'r1',
        'homepageId': 'hp-1',
        'authorPersonaId': 'p1',
        'rating': 4,
        'status': 'deleted',
        'createdAt': '2026-07-19T10:00:00Z',
        'updatedAt': '2026-07-19T10:05:00Z',
      });
      expect(view.status, HomepageReviewStatus.deleted);
    });
  });
}
