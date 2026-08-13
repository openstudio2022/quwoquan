// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-entry-and-preview/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-overview-and-module-shell/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/object-homepage-gamma-real-data-closure/spec.md#gwt-002
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/entity-homepage-intersection-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-review-read-and-score-summary/spec.md#gwt-001
// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/missing-homepage-suggestion-and-review/spec.md#gwt-001
// readiness_case: homepage_get_entity_impact_app_api
// readiness_case: homepage_get_homepage_detail_app_api
// readiness_case: homepage_get_homepage_introduction_app_api
// readiness_case: homepage_get_homepage_related_groups_app_api
// readiness_case: homepage_get_homepage_review_summary_app_api
// readiness_case: homepage_get_homepage_shell_app_api
// readiness_case: homepage_get_object_page_bundle_app_api
// readiness_case: homepage_suggest_homepage_candidate_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/entity_api_contract_harness.dart';

EntityApiContractHarness? _harness;
late HomepageSearchItemView _publishedHomepage;

EntityApiContractHarness get _api => _harness!;

void main() {
  setUpAll(() async {
    _harness = await EntityApiContractHarness.create();
    _publishedHomepage = await _api.acquirePublishedHomepage();
  });
  tearDownAll(() => _harness?.close());

  test(
    'GetHomepageDetail returns authoritative detail and canonical failure',
    () async {
      await _verifyRead(
        operationId: AppCloudOperationIds.entityHomepageGetHomepageDetail,
        invoke: _api.query.getHomepageDetail,
        verify: (result) {
          expect(result.homepageId, _publishedHomepage.homepageId);
          expect(result.title, isNotEmpty);
          expect(result.homepageType, isNotEmpty);
          expect(result.status, HomepageStatus.published.wireName);
        },
      );
    },
  );

  test(
    'GetHomepageShell returns authoritative populated shell and failure',
    () async {
      await _verifyRead(
        operationId: AppCloudOperationIds.entityHomepageGetHomepageShell,
        invoke: _api.query.getHomepageShell,
        verify: (result) {
          expect(result.homepage.homepageId, _publishedHomepage.homepageId);
          expect(result.homepage.title, isNotEmpty);
          expect(result.homepage.homepageType, isNotEmpty);
          expect(
            result.reviewSummary != null ||
                (result.contentPreview?.isNotEmpty ?? false) ||
                (result.relatedGroups?.isNotEmpty ?? false),
            isTrue,
            reason: 'published shell must expose an authoritative value slice',
          );
        },
      );
    },
  );

  test(
    'GetHomepageIntroduction returns real sections and canonical failure',
    () async {
      await _verifyRead(
        operationId: AppCloudOperationIds.entityHomepageGetHomepageIntroduction,
        invoke: _api.introduction.getHomepageIntroduction,
        verify: (result) {
          expect(result.homepageId, _publishedHomepage.homepageId);
          expect(result.displayName, isNotEmpty);
          expect(result.summary, isNotEmpty);
          expect(result.sections, isNotEmpty);
          expect(
            result.sections.every((section) => section.title.isNotEmpty),
            isTrue,
          );
          expect(result.sourceUrls, isNotEmpty);
        },
      );
    },
  );

  test(
    'GetObjectPageBundle returns authoritative object slices and failure',
    () async {
      await _verifyRead(
        operationId: AppCloudOperationIds.entityHomepageGetObjectPageBundle,
        invoke: (homepageId) => _api.query.getObjectPageBundle(
          HomepageObjectPageBundleQuery(
            homepageId: homepageId,
            referralSource: 'api-integration',
            feedRequestId: 'entity-homepage-api-feed',
            recommendationTraceId: 'entity-homepage-api-trace',
            experimentBucket: 'contract',
            rolloutCohort: 'gamma',
          ),
        ),
        verify: (result) {
          expect(result.objectType, 'homepage');
          expect(result.objectId, _publishedHomepage.homepageId);
          expect(result.canonicalEntityId, isNotEmpty);
          expect(result.title, isNotEmpty);
          expect(result.tagRefs, isNotEmpty);
          expect(result.highlightItems, isNotEmpty);
          expect(result.relatedObjects, isNotEmpty);
        },
      );
    },
  );

  test('GetEntityImpact returns authoritative fact rows and failure', () async {
    await _verifyRead(
      operationId: AppCloudOperationIds.entityHomepageGetEntityImpact,
      invoke: _api.query.getEntityImpact,
      verify: (result) {
        expect(result.homepageId, _publishedHomepage.homepageId);
        expect(result.total, greaterThan(0));
        expect(result.items, isNotEmpty);
        expect(result.items.every((item) => item.impactId.isNotEmpty), isTrue);
        expect(
          result.items.every((item) => item.primaryText.isNotEmpty),
          isTrue,
        );
        expect(
          result.items.every((item) => item.evidenceSnapshotId.isNotEmpty),
          isTrue,
        );
      },
    );
  });

  test(
    'GetHomepageReviewSummary returns real aggregation and failure',
    () async {
      await _verifyRead(
        operationId:
            AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
        invoke: _api.query.getHomepageReviewSummary,
        verify: (result) {
          expect(result.averageRating, isNotNull);
          expect(result.ratingCount, greaterThan(0));
          expect(result.highlightTags, isNotNull);
          expect(result.highlightTags, isNotEmpty);
        },
      );
    },
  );

  test(
    'GetHomepageRelatedGroups returns authoritative groups and failure',
    () async {
      await _verifyRead(
        operationId:
            AppCloudOperationIds.entityHomepageGetHomepageRelatedGroups,
        invoke: _api.query.getHomepageRelatedGroups,
        verify: (result) {
          expect(result.groups, isNotNull);
          expect(result.groups, isNotEmpty);
          final group = result.groups!.first;
          expect(group.circleId, isNotEmpty);
          expect(group.name, isNotEmpty);
          expect(group.memberCount, greaterThan(0));
          expect(group.evidenceSnapshotId, isNotEmpty);
        },
      );
    },
  );

  test(
    'SuggestHomepageCandidate replays one candidate and stays private',
    () async {
      final suffix = _api.session.ownerId.replaceAll('-', '');
      final command = SuggestHomepageCandidateCommand(
        title: 'API候选主页${suffix.substring(0, 8)}',
        homepageType: HomepageType.sight.wireName,
        subtitle: 'candidate-bound API integration evidence',
        categoryTags: const <String>['travel', 'api-contract'],
        city: '杭州',
        sourcePlaceId: 'entity-homepage-api-$suffix',
        location: const HomepageGeoPointInput(lat: 30.25, lng: 120.15),
      );
      final idempotencyKey = 'entity-homepage-suggest-$suffix';

      final created = await _api.withIdempotencyKey(
        idempotencyKey,
        () => _api.candidateWriter.suggest(command),
      );
      expect(created.homepageId, isNotEmpty);
      expect(created.title, command.title);
      expect(created.status, HomepageStatus.candidate);
      await _api.expectTelemetry(
        AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
        succeeded: true,
        statusCode: 201,
      );

      final replayed = await _api.withIdempotencyKey(
        idempotencyKey,
        () => _api.candidateWriter.suggest(command),
      );
      expect(replayed.homepageId, created.homepageId);
      expect(replayed.toWire(), created.toWire());
      await _api.expectTelemetry(
        AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
        succeeded: true,
        statusCode: 201,
      );

      await _expectCanonicalFailure(
        operationId:
            AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
        statusCode: 400,
        code: 'ENTITY.USER.invalid_homepage_type',
        invoke: () => _api.withIdempotencyKey(
          '$idempotencyKey-invalid',
          () => _api.candidateWriter.suggest(
            SuggestHomepageCandidateCommand(
              title: '${command.title}非法类型',
              homepageType: 'invalid-homepage-type',
            ),
          ),
        ),
      );

      final publicResults = await _api.query.searchHomepages(
        HomepageSearchQuery(
          query: command.title,
          status: HomepageStatus.published.wireName,
          limit: 20,
        ),
      );
      expect(
        publicResults.items.any(
          (item) => item.homepageId == created.homepageId,
        ),
        isFalse,
      );
      await _api.expectTelemetry(
        AppCloudOperationIds.entityHomepageSearchHomepages,
        succeeded: true,
        statusCode: 200,
      );
    },
  );
}

Future<void> _verifyRead<T>({
  required String operationId,
  required Future<T> Function(String homepageId) invoke,
  required void Function(T result) verify,
}) async {
  final result = await invoke(_publishedHomepage.homepageId);
  verify(result);
  await _api.expectTelemetry(operationId, succeeded: true, statusCode: 200);
  await _expectCanonicalFailure(
    operationId: operationId,
    statusCode: 404,
    code: 'ENTITY.USER.homepage_not_found',
    invoke: () => invoke('${_publishedHomepage.homepageId}-missing'),
  );
}

Future<void> _expectCanonicalFailure({
  required String operationId,
  required int statusCode,
  required String code,
  required Future<Object?> Function() invoke,
}) async {
  CloudException? captured;
  try {
    await invoke();
  } on CloudException catch (error) {
    captured = error;
  }
  expect(captured, isNotNull, reason: '$operationId must fail canonically');
  expect(captured!.statusCode, statusCode);
  expect(captured.code, code);
  expect(captured.requestId, isNotEmpty);
  expect(captured.traceId, isNotEmpty);
  expect(captured.sourceOperationId, operationId);
  final event = await _api.expectTelemetry(
    operationId,
    succeeded: false,
    statusCode: statusCode,
  );
  expect(event.requestId, captured.requestId);
  expect(event.traceId, captured.traceId);
}
