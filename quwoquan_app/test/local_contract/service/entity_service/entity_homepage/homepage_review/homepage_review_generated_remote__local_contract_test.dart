// spec_ref: specs/feature-tree/shared-homepage-network/homepage-review-and-content/homepage-review-read-and-score-summary/spec.md#gwt-001
// readiness_case: homepage_review_create_homepage_review_app_local
// readiness_case: homepage_review_update_homepage_review_app_local
// readiness_case: homepage_review_delete_homepage_review_app_local
// readiness_case: homepage_review_list_homepage_reviews_app_local
// readiness_case: homepage_review_get_my_homepage_review_app_local
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/di/entity_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  group('HomepageReview production Remote generated HTTP readiness', () {
    test('五项 operation 精确读写、重放并 authoritative readback', () async {
      final requests = <CapturedRemoteApiPathRequest>[];
      final wireState = _ReviewWireState();
      final facets = _facets(requests, responseFor: wireState.respond);

      final createCommand = CreateHomepageReviewCommand(
        homepageId: _homepageId,
        rating: 5,
        body: '真实到访体验很好',
        tagRefs: const <String>['review/scenery', 'review/service'],
        authorDisplayNameSnapshot: '旅行摄影者',
        authorAvatarUrlSnapshot: 'https://media.example/reviewer.jpg',
      );
      final created = await facets.commandWriter.create(createCommand);
      final createReplay = await facets.commandWriter.create(createCommand);
      expect(created.id, _reviewId);
      expect(created.homepageId, _homepageId);
      expect(created.rating, 5);
      expect(created.status, HomepageReviewStatus.active);
      expect(created.body, '真实到访体验很好');
      expect(createReplay.toWire(), created.toWire());

      final afterCreate = await facets.query.listByHomepage(
        HomepageReviewListQuery(homepageId: _homepageId),
      );
      final mineAfterCreate = await facets.query.getMine(
        MyHomepageReviewQuery(homepageId: _homepageId),
      );
      expect(afterCreate.items, hasLength(1));
      expect(afterCreate.items.single.toWire(), created.toWire());
      expect(mineAfterCreate.toWire(), created.toWire());

      final updateCommand = UpdateHomepageReviewCommand(
        reviewId: _reviewId,
        rating: 4,
        body: '更新后仍值得推荐',
        tagRefs: const <String>['review/scenery'],
        authorDisplayNameSnapshot: '旅行摄影者',
        authorAvatarUrlSnapshot: 'https://media.example/reviewer.jpg',
      );
      final updated = await facets.commandWriter.update(updateCommand);
      final updateReplay = await facets.commandWriter.update(updateCommand);
      expect(updated.id, created.id);
      expect(updated.rating, 4);
      expect(updated.body, '更新后仍值得推荐');
      expect(updated.tagRefs, <String>['review/scenery']);
      expect(updateReplay.toWire(), updated.toWire());

      final afterUpdate = await facets.query.listByHomepage(
        HomepageReviewListQuery(homepageId: _homepageId),
      );
      final mineAfterUpdate = await facets.query.getMine(
        MyHomepageReviewQuery(homepageId: _homepageId),
      );
      expect(afterUpdate.items, hasLength(1));
      expect(afterUpdate.items.single.toWire(), updated.toWire());
      expect(mineAfterUpdate.toWire(), updated.toWire());

      final deleteCommand = DeleteHomepageReviewCommand(reviewId: _reviewId);
      final deleted = await facets.commandWriter.delete(deleteCommand);
      final deleteReplay = await facets.commandWriter.delete(deleteCommand);
      expect(deleted.id, created.id);
      expect(deleted.status, HomepageReviewStatus.deleted);
      expect(deleteReplay.toWire(), deleted.toWire());

      final afterDelete = await facets.query.listByHomepage(
        HomepageReviewListQuery(homepageId: _homepageId),
      );
      final mineAfterDelete = await facets.query.getMine(
        MyHomepageReviewQuery(homepageId: _homepageId),
      );
      expect(afterDelete.items, isEmpty);
      expect(mineAfterDelete.id, created.id);
      expect(mineAfterDelete.status, HomepageReviewStatus.deleted);

      _expectRequests(requests);
    });

    for (final failureCase in _failureCases) {
      test(
        '${failureCase.operationId} canonical 503 保留 code/status/operation',
        () async {
          final requests = <CapturedRemoteApiPathRequest>[];
          final facets = _facets(
            requests,
            responseFor: (_) => http.Response(
              jsonEncode(const <String, Object?>{
                'code': 'ENTITY.SYSTEM.internal_error',
                'message': 'homepage review dependency unavailable',
                'requestId': 'request-homepage-review-unavailable',
                'traceId': 'trace-homepage-review-unavailable',
              }),
              503,
              headers: const <String, String>{
                'content-type': 'application/json',
                'retry-after': '0',
              },
            ),
          );

          await expectLater(
            failureCase.invoke(facets),
            throwsA(
              isA<CloudException>()
                  .having(
                    (error) => error.code,
                    'code',
                    'ENTITY.SYSTEM.internal_error',
                  )
                  .having((error) => error.statusCode, 'statusCode', 503)
                  .having(
                    (error) => error.sourceOperationId,
                    'sourceOperationId',
                    failureCase.operationId,
                  ),
            ),
          );
          expect(requests, hasLength(2));
          final firstKey = _header(requests.first.headers, 'Idempotency-Key');
          final secondKey = _header(requests.last.headers, 'Idempotency-Key');
          if (failureCase.command) {
            expect(firstKey, isNotEmpty);
            expect(secondKey, firstKey);
          } else {
            expect(firstKey, isNull);
            expect(secondKey, isNull);
          }
        },
      );

      test('${failureCase.operationId} malformed 2xx fail-closed', () async {
        final requests = <CapturedRemoteApiPathRequest>[];
        final facets = _facets(
          requests,
          responseFor: (_) => remoteApiPathJsonResponse(const <String, Object?>{
            'unexpected': 'shape',
          }),
        );

        await expectLater(
          failureCase.invoke(facets),
          throwsA(
            isA<CloudException>().having(
              (error) => error.type,
              'type',
              CloudErrorType.invalidResponse,
            ),
          ),
        );
        expect(requests, hasLength(1));
      });
    }
  });
}

const _homepageId = 'homepage-1';
const _reviewId = 'review-1';
const _accountId = 'account-1';
const _personaId = 'persona-1';

AppProductionHomepageReviewFacets _facets(
  List<CapturedRemoteApiPathRequest> requests, {
  required RemoteApiPathResponseFactory responseFor,
}) {
  return EntityProductionComposition.homepageReviewFacets(
    client: buildRemoteApiPathOperationClient(
      requests,
      responseFor: responseFor,
    ),
    invocationContext: (clientPageId, {required command}) =>
        CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.homepageDetail.id,
          routeId: AppUiSurfaces.homepageDetail.routeId,
          clientPageId: clientPageId,
          idempotencyKey: command
              ? 'homepage-review-$clientPageId-intent'
              : null,
          actor: const CloudOperationActorContext(
            accountId: _accountId,
            personaId: _personaId,
          ),
        ),
  );
}

final List<_ReviewFailureCase> _failureCases = <_ReviewFailureCase>[
  _ReviewFailureCase(
    operationId: AppCloudOperationIds.entityHomepageReviewCreateHomepageReview,
    command: true,
    invoke: (facets) => facets.commandWriter.create(
      CreateHomepageReviewCommand(homepageId: _homepageId, rating: 5),
    ),
  ),
  _ReviewFailureCase(
    operationId: AppCloudOperationIds.entityHomepageReviewUpdateHomepageReview,
    command: true,
    invoke: (facets) => facets.commandWriter.update(
      UpdateHomepageReviewCommand(reviewId: _reviewId, rating: 4),
    ),
  ),
  _ReviewFailureCase(
    operationId: AppCloudOperationIds.entityHomepageReviewDeleteHomepageReview,
    command: true,
    invoke: (facets) => facets.commandWriter.delete(
      DeleteHomepageReviewCommand(reviewId: _reviewId),
    ),
  ),
  _ReviewFailureCase(
    operationId: AppCloudOperationIds.entityHomepageReviewListHomepageReviews,
    command: false,
    invoke: (facets) => facets.query.listByHomepage(
      HomepageReviewListQuery(homepageId: _homepageId),
    ),
  ),
  _ReviewFailureCase(
    operationId: AppCloudOperationIds.entityHomepageReviewGetMyHomepageReview,
    command: false,
    invoke: (facets) =>
        facets.query.getMine(MyHomepageReviewQuery(homepageId: _homepageId)),
  ),
];

void _expectRequests(List<CapturedRemoteApiPathRequest> requests) {
  final cases = <_ReviewRequestCase>[
    _ReviewRequestCase(
      operationId:
          AppCloudOperationIds.entityHomepageReviewCreateHomepageReview,
      clientPageId: EntityRequestPageIds.createHomepageReview,
      method: 'POST',
      path: '/homepages/$_homepageId/reviews',
      expectedCount: 2,
      body: const <String, Object?>{
        'rating': 5,
        'body': '真实到访体验很好',
        'tagRefs': <String>['review/scenery', 'review/service'],
        'authorDisplayNameSnapshot': '旅行摄影者',
        'authorAvatarUrlSnapshot': 'https://media.example/reviewer.jpg',
      },
      command: true,
    ),
    _ReviewRequestCase(
      operationId:
          AppCloudOperationIds.entityHomepageReviewUpdateHomepageReview,
      clientPageId: EntityRequestPageIds.updateHomepageReview,
      method: 'PATCH',
      path: '/homepage-reviews/$_reviewId',
      expectedCount: 2,
      body: const <String, Object?>{
        'rating': 4,
        'body': '更新后仍值得推荐',
        'tagRefs': <String>['review/scenery'],
        'authorDisplayNameSnapshot': '旅行摄影者',
        'authorAvatarUrlSnapshot': 'https://media.example/reviewer.jpg',
      },
      command: true,
    ),
    _ReviewRequestCase(
      operationId:
          AppCloudOperationIds.entityHomepageReviewDeleteHomepageReview,
      clientPageId: EntityRequestPageIds.deleteHomepageReview,
      method: 'DELETE',
      path: '/homepage-reviews/$_reviewId',
      expectedCount: 2,
      command: true,
    ),
    _ReviewRequestCase(
      operationId: AppCloudOperationIds.entityHomepageReviewListHomepageReviews,
      clientPageId: EntityRequestPageIds.listHomepageReviews,
      method: 'GET',
      path: '/homepages/$_homepageId/reviews',
      expectedCount: 3,
      query: const <String, String>{'limit': '20'},
      command: false,
    ),
    _ReviewRequestCase(
      operationId: AppCloudOperationIds.entityHomepageReviewGetMyHomepageReview,
      clientPageId: EntityRequestPageIds.getMyHomepageReview,
      method: 'GET',
      path: '/homepages/$_homepageId/reviews/mine',
      expectedCount: 3,
      command: false,
    ),
  ];

  for (final requestCase in cases) {
    final matching = requests
        .where(
          (request) =>
              _header(request.headers, 'X-Client-Operation-Id') ==
              requestCase.operationId,
        )
        .toList(growable: false);
    expect(
      matching,
      hasLength(requestCase.expectedCount),
      reason: requestCase.operationId,
    );
    for (final request in matching) {
      expect(request.method, requestCase.method);
      expect(request.path, requestCase.path);
      expect(request.query, requestCase.query);
      expect(request.body, requestCase.body);
      expectRemoteApiPathHeaders(
        request.headers,
        clientPageId: requestCase.clientPageId,
        surfaceId: AppUiSurfaces.homepageDetail.id,
        operationId: requestCase.operationId,
      );
      expect(
        _header(request.headers, 'Authorization'),
        'Bearer integration-contract-token',
      );
      expect(_header(request.headers, 'X-Client-Attempt'), '1');
      if (requestCase.command) {
        expect(
          _header(request.headers, 'Idempotency-Key'),
          'homepage-review-${requestCase.clientPageId}-intent',
        );
      } else {
        expect(
          request.headers.keys.any(
            (name) => name.toLowerCase() == 'idempotency-key',
          ),
          isFalse,
        );
      }
    }
  }
}

String? _header(Map<String, String> headers, String name) {
  final normalized = name.toLowerCase();
  for (final entry in headers.entries) {
    if (entry.key.toLowerCase() == normalized) {
      return entry.value;
    }
  }
  return null;
}

final class _ReviewWireState {
  var _created = false;
  var _status = HomepageReviewStatus.active;
  var _rating = 5;
  var _body = '真实到访体验很好';
  var _tagRefs = const <String>['review/scenery', 'review/service'];

  http.Response respond(http.Request request) {
    final operationId = _header(request.headers, 'X-Client-Operation-Id');
    switch (operationId) {
      case AppCloudOperationIds.entityHomepageReviewCreateHomepageReview:
        _created = true;
        _status = HomepageReviewStatus.active;
        _rating = 5;
        _body = '真实到访体验很好';
        _tagRefs = const <String>['review/scenery', 'review/service'];
        return remoteApiPathJsonResponse(_view());
      case AppCloudOperationIds.entityHomepageReviewUpdateHomepageReview:
        _created = true;
        _status = HomepageReviewStatus.active;
        _rating = 4;
        _body = '更新后仍值得推荐';
        _tagRefs = const <String>['review/scenery'];
        return remoteApiPathJsonResponse(_view(updated: true));
      case AppCloudOperationIds.entityHomepageReviewDeleteHomepageReview:
        _created = true;
        _status = HomepageReviewStatus.deleted;
        return remoteApiPathJsonResponse(_view(updated: true));
      case AppCloudOperationIds.entityHomepageReviewListHomepageReviews:
        return remoteApiPathJsonResponse(<String, Object?>{
          'items': _created && _status == HomepageReviewStatus.active
              ? <Object?>[_view(updated: _rating == 4)]
              : <Object?>[],
          'nextCursor': null,
        });
      case AppCloudOperationIds.entityHomepageReviewGetMyHomepageReview:
        if (_created) {
          return remoteApiPathJsonResponse(_view(updated: _rating == 4));
        }
        return remoteApiPathJsonResponse(const <String, Object?>{
          'code': 'ENTITY.USER.review_not_found',
          'message': 'review not found',
        }, statusCode: 404);
      default:
        return remoteApiPathJsonResponse(const <String, Object?>{
          'code': 'ENTITY.SYSTEM.internal_error',
          'message': 'unexpected homepage review operation',
        }, statusCode: 500);
    }
  }

  Map<String, Object?> _view({bool updated = false}) => <String, Object?>{
    'id': _reviewId,
    'homepageId': _homepageId,
    'authorPersonaId': _personaId,
    'rating': _rating,
    'status': _status.wireName,
    'createdAt': '2026-08-09T00:00:00Z',
    'updatedAt': updated ? '2026-08-09T00:05:00Z' : '2026-08-09T00:00:00Z',
    'authorDisplayNameSnapshot': '旅行摄影者',
    'authorAvatarUrlSnapshot': 'https://media.example/reviewer.jpg',
    'body': _body,
    'tagRefs': _tagRefs,
  };
}

final class _ReviewFailureCase {
  const _ReviewFailureCase({
    required this.operationId,
    required this.command,
    required this.invoke,
  });

  final String operationId;
  final bool command;
  final Future<Object> Function(AppProductionHomepageReviewFacets facets)
  invoke;
}

final class _ReviewRequestCase {
  const _ReviewRequestCase({
    required this.operationId,
    required this.clientPageId,
    required this.method,
    required this.path,
    required this.expectedCount,
    required this.command,
    this.query = const <String, String>{},
    this.body = const <String, Object?>{},
  });

  final String operationId;
  final String clientPageId;
  final String method;
  final String path;
  final int expectedCount;
  final bool command;
  final Map<String, String> query;
  final Map<String, Object?> body;
}
