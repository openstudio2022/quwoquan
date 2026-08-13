// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-review-read-and-score-summary/spec.md#gwt-001
// readiness_case: homepage_review_create_homepage_review_app_api
// readiness_case: homepage_review_update_homepage_review_app_api
// readiness_case: homepage_review_delete_homepage_review_app_api
// readiness_case: homepage_review_list_homepage_reviews_app_api
// readiness_case: homepage_review_get_my_homepage_review_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/entity_api_contract_harness.dart';

EntityHomepageReviewApiActor? _authorActor;
EntityHomepageReviewApiActor? _otherActor;
late HomepageSearchItemView _publishedHomepage;

EntityHomepageReviewApiActor get _author => _authorActor!;
EntityHomepageReviewApiActor get _other => _otherActor!;

void main() {
  setUpAll(() async {
    final runId = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    final author = await EntityHomepageReviewApiActor.create(
      label: 'author',
      runId: runId,
    );
    EntityHomepageReviewApiActor? other;
    try {
      other = await EntityHomepageReviewApiActor.create(
        label: 'other',
        runId: runId,
      );
      _publishedHomepage = await author.acquirePublishedHomepage();
      _authorActor = author;
      _otherActor = other;
    } catch (_) {
      try {
        await other?.close();
      } finally {
        await author.close();
      }
      rethrow;
    }
  });

  tearDownAll(() async {
    try {
      await _otherActor?.close();
    } finally {
      await _authorActor?.close();
    }
  });

  test(
    'five production Remote operations replay and converge authoritatively',
    () async {
      final homepageId = _publishedHomepage.homepageId;
      final baselineSummary = await _author.expectSuccess(
        operationId:
            AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
        statusCode: 200,
        invoke: () => _author.homepage.getHomepageReviewSummary(homepageId),
      );
      expect(baselineSummary.ratingCount, greaterThan(0));
      expect(baselineSummary.averageRating, isNotNull);

      final createCommand = CreateHomepageReviewCommand(
        homepageId: homepageId,
        rating: 5,
        body: 'candidate-bound homepage review create',
        tagRefs: const <String>['review/api-contract'],
        authorDisplayNameSnapshot: 'API Contract Reviewer',
      );
      final created = await _author.withIdempotencyKey(
        'homepage-review-${_author.runId}-create',
        () async {
          final first = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewCreateHomepageReview,
            statusCode: 201,
            invoke: () => _author.reviews.commandWriter.create(createCommand),
          );
          final replay = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewCreateHomepageReview,
            statusCode: 201,
            invoke: () => _author.reviews.commandWriter.create(createCommand),
          );
          expect(replay.toWire(), first.toWire());
          return first;
        },
      );
      _expectActiveReview(
        created,
        homepageId: homepageId,
        authorPersonaId: _author.session.activePersona!.personaId,
        rating: 5,
        body: createCommand.body,
      );

      await _expectAuthoritativeReadback(created);
      await _author.waitForSummary(
        homepageId,
        baseline: baselineSummary,
        activeRating: 5,
      );

      await _other.withIdempotencyKey(
        'homepage-review-${_other.runId}-bola-update',
        () => _other.expectFailure(
          operationId:
              AppCloudOperationIds.entityHomepageReviewUpdateHomepageReview,
          statusCode: 403,
          code: 'ENTITY.USER.permission_denied',
          invoke: () => _other.reviews.commandWriter.update(
            UpdateHomepageReviewCommand(
              reviewId: created.id,
              rating: 1,
              body: 'non-author mutation must not commit',
            ),
          ),
        ),
      );
      await _other.withIdempotencyKey(
        'homepage-review-${_other.runId}-bola-delete',
        () => _other.expectFailure(
          operationId:
              AppCloudOperationIds.entityHomepageReviewDeleteHomepageReview,
          statusCode: 403,
          code: 'ENTITY.USER.permission_denied',
          invoke: () => _other.reviews.commandWriter.delete(
            DeleteHomepageReviewCommand(reviewId: created.id),
          ),
        ),
      );
      await _other.expectFailure(
        operationId:
            AppCloudOperationIds.entityHomepageReviewGetMyHomepageReview,
        statusCode: 404,
        code: 'ENTITY.USER.review_not_found',
        invoke: () => _other.reviews.query.getMine(
          MyHomepageReviewQuery(homepageId: homepageId),
        ),
      );
      await _expectAuthoritativeReadback(created);

      final updateCommand = UpdateHomepageReviewCommand(
        reviewId: created.id,
        rating: 4,
        body: 'candidate-bound homepage review update',
        tagRefs: const <String>['review/api-contract', 'review/scenery'],
        authorDisplayNameSnapshot: 'API Contract Reviewer',
      );
      final updated = await _author.withIdempotencyKey(
        'homepage-review-${_author.runId}-update',
        () async {
          final first = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewUpdateHomepageReview,
            statusCode: 200,
            invoke: () => _author.reviews.commandWriter.update(updateCommand),
          );
          final replay = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewUpdateHomepageReview,
            statusCode: 200,
            invoke: () => _author.reviews.commandWriter.update(updateCommand),
          );
          expect(replay.toWire(), first.toWire());
          return first;
        },
      );
      _expectActiveReview(
        updated,
        homepageId: homepageId,
        authorPersonaId: _author.session.activePersona!.personaId,
        rating: 4,
        body: updateCommand.body,
      );
      expect(updated.id, created.id);
      await _expectAuthoritativeReadback(updated);
      await _author.waitForSummary(
        homepageId,
        baseline: baselineSummary,
        activeRating: 4,
      );

      final deleteCommand = DeleteHomepageReviewCommand(reviewId: created.id);
      final deleted = await _author.withIdempotencyKey(
        'homepage-review-${_author.runId}-delete',
        () async {
          final first = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewDeleteHomepageReview,
            statusCode: 200,
            invoke: () => _author.reviews.commandWriter.delete(deleteCommand),
          );
          final replay = await _author.expectSuccess(
            operationId:
                AppCloudOperationIds.entityHomepageReviewDeleteHomepageReview,
            statusCode: 200,
            invoke: () => _author.reviews.commandWriter.delete(deleteCommand),
          );
          expect(replay.toWire(), first.toWire());
          return first;
        },
      );
      expect(deleted.id, created.id);
      expect(deleted.status, HomepageReviewStatus.deleted);

      final afterDelete = await _author.expectSuccess(
        operationId:
            AppCloudOperationIds.entityHomepageReviewListHomepageReviews,
        statusCode: 200,
        invoke: () => _author.reviews.query.listByHomepage(
          HomepageReviewListQuery(homepageId: homepageId, limit: 100),
        ),
      );
      expect(afterDelete.items.any((item) => item.id == created.id), isFalse);
      final mineAfterDelete = await _author.expectSuccess(
        operationId:
            AppCloudOperationIds.entityHomepageReviewGetMyHomepageReview,
        statusCode: 200,
        invoke: () => _author.reviews.query.getMine(
          MyHomepageReviewQuery(homepageId: homepageId),
        ),
      );
      expect(mineAfterDelete.id, created.id);
      expect(mineAfterDelete.status, HomepageReviewStatus.deleted);
      await _author.waitForSummary(homepageId, baseline: baselineSummary);
    },
  );

  test(
    'create and list preserve canonical missing-homepage failures',
    () async {
      final missingHomepageId = 'nonexistent_homepage_review_${_author.runId}';
      await _author.withIdempotencyKey(
        'homepage-review-${_author.runId}-missing-homepage',
        () => _author.expectFailure(
          operationId:
              AppCloudOperationIds.entityHomepageReviewCreateHomepageReview,
          statusCode: 404,
          code: 'ENTITY.USER.homepage_not_found',
          invoke: () => _author.reviews.commandWriter.create(
            CreateHomepageReviewCommand(
              homepageId: missingHomepageId,
              rating: 5,
            ),
          ),
        ),
      );
      await _author.expectFailure(
        operationId:
            AppCloudOperationIds.entityHomepageReviewListHomepageReviews,
        statusCode: 404,
        code: 'ENTITY.USER.homepage_not_found',
        invoke: () => _author.reviews.query.listByHomepage(
          HomepageReviewListQuery(homepageId: missingHomepageId),
        ),
      );
    },
  );
}

Future<void> _expectAuthoritativeReadback(HomepageReviewView expected) async {
  final page = await _author.expectSuccess(
    operationId: AppCloudOperationIds.entityHomepageReviewListHomepageReviews,
    statusCode: 200,
    invoke: () => _author.reviews.query.listByHomepage(
      HomepageReviewListQuery(homepageId: expected.homepageId, limit: 100),
    ),
  );
  expect(page.items, isNotEmpty);
  final matching = page.items
      .where((item) => item.id == expected.id)
      .toList(growable: false);
  expect(matching, hasLength(1));
  expect(matching.single.toWire(), expected.toWire());

  final mine = await _author.expectSuccess(
    operationId: AppCloudOperationIds.entityHomepageReviewGetMyHomepageReview,
    statusCode: 200,
    invoke: () => _author.reviews.query.getMine(
      MyHomepageReviewQuery(homepageId: expected.homepageId),
    ),
  );
  expect(mine.toWire(), expected.toWire());
}

void _expectActiveReview(
  HomepageReviewView value, {
  required String homepageId,
  required String authorPersonaId,
  required int rating,
  required String? body,
}) {
  expect(value.id, isNotEmpty);
  expect(value.homepageId, homepageId);
  expect(value.authorPersonaId, authorPersonaId);
  expect(value.rating, rating);
  expect(value.status, HomepageReviewStatus.active);
  expect(value.body, body);
  expect(value.createdAt.isUtc, isTrue);
  expect(value.updatedAt.isUtc, isTrue);
}
