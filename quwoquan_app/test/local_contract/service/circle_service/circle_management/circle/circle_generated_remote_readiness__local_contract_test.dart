// spec_ref: specs/feature-tree/circle-community/activity-member-governance/circle-lifecycle/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/circle-lifecycle/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/circle-lifecycle/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/activity-stream-paging/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/activity-stream-paging/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/circle-community/activity-member-governance/activity-stream-paging/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/kpi-reporting/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/kpi-reporting/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/kpi-reporting/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/circle-facet-search-and-filter/spec.md#gwt-002
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/circle-facet-search-and-filter/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/circle-facet-search-and-filter/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/circle-facet-search-and-filter/spec.md#gwt-002.t3
// spec_ref: specs/feature-tree/global-search-experience/cross-domain-search/circle-facet-search-and-filter/spec.md#gwt-002.t4
// readiness_case: circle_archive_circle_app_local
// readiness_case: circle_create_circle_app_local
// readiness_case: circle_get_circle_app_local
// readiness_case: circle_get_circle_feed_app_local
// readiness_case: circle_get_circle_impact_app_local
// readiness_case: circle_search_circles_app_local
// readiness_case: circle_update_circle_app_local
// readiness_case: circle_update_circle_sections_app_local

/// Circle 聚合 App local readiness：唯一 production composition 必须经
/// GeneratedCloudOperationClient 发出 canonical wire，解码 typed 结果，并让
/// canonical failure 与幂等重试保持 operation/intent 绑定。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

typedef _CircleRemoteFacets = ({
  CircleQueryReader query,
  CircleLifecycleCommandWriter lifecycle,
  CircleConfigurationCommandWriter configuration,
});

typedef _OperationCall = ({
  String operationId,
  bool command,
  Future<Object?> Function(_CircleRemoteFacets facets) invoke,
});

void main() {
  group('circle.circle production Remote generated contract', () {
    test('exact wire decodes typed Circle results and receipts', () async {
      final log = <CapturedRemoteApiPathRequest>[];
      final facets = _facets(log, responseFor: _successResponse);

      final created = await facets.lifecycle.createCircle(
        CreateCircleCommand(
          name: '摄影同行圈',
          description: '真实 Circle 聚合根',
          tags: const <String>['travel', 'photography'],
          visibility: 'public',
          joinPolicy: 'approval',
          kind: 'interest',
          displaySubjectType: 'circle',
          followEnabled: true,
          autoSyncChat: true,
        ),
      );
      final circle = await facets.query.get(
        CircleDetailQuery(circleId: 'circle-1'),
      );
      final updated = await facets.lifecycle.updateCircle(
        UpdateCircleCommand(
          circleId: 'circle-1',
          name: '摄影同行圈·杭州',
          description: '已由 owner 更新',
          tags: const <String>['travel', 'photography', 'hangzhou'],
          followEnabled: false,
        ),
      );
      final feed = await facets.query.feed(
        CircleFeedQuery(
          circleId: 'circle-1',
          identity: 'works',
          type: 'image',
          cursor: 'feed-cursor',
          limit: 7,
          sort: 'latest',
        ),
      );
      final impact = await facets.query.impact(
        CircleImpactQuery(circleId: 'circle-1'),
      );
      final configured = await facets.configuration.updateCircleSections(
        UpdateCircleSectionsCommand(
          circleId: 'circle-1',
          sections: const <CircleSectionConfig>[
            CircleSectionConfig(
              sectionType: CircleSectionType.works,
              visible: true,
              order: 0,
            ),
            CircleSectionConfig(
              sectionType: CircleSectionType.members,
              visible: true,
              order: 1,
            ),
          ],
        ),
      );
      final archived = await facets.lifecycle.archiveCircle(
        ArchiveCircleCommand(circleId: 'circle-1'),
      );

      expect(created.circleId, 'circle-1');
      expect(created.version, 1);
      expect(created.status, CircleStatus.active);
      expect(circle.id, 'circle-1');
      expect(circle.name, '摄影同行圈');
      expect(circle.sectionConfig?.single.sectionType, CircleSectionType.works);
      expect(updated.version, 2);
      expect(updated.status, CircleStatus.active);
      expect(feed.items.single.placementId, 'placement-1');
      expect(feed.items.single.postId, 'post-1');
      expect(feed.cursor, 'feed-next');
      expect(impact.circleId, 'circle-1');
      expect(impact.total, 1);
      expect(impact.items.single.impactId, 'impact-1');
      expect(configured.version, 4);
      expect(archived.version, 3);
      expect(archived.status, CircleStatus.archived);

      _expectCommand(
        log,
        operationId: AppCloudOperationIds.circleCircleCreateCircle,
        clientPageId: CircleRequestPageIds.createCircle,
        surface: AppUiSurfaces.circlesList,
        method: 'POST',
        body: const <String, Object?>{
          'name': '摄影同行圈',
          'description': '真实 Circle 聚合根',
          'tags': <String>['travel', 'photography'],
          'visibility': 'public',
          'joinPolicy': 'approval',
          'kind': 'interest',
          'displaySubjectType': 'circle',
          'followEnabled': true,
          'autoSyncChat': true,
        },
      );
      _expectQuery(
        log,
        operationId: AppCloudOperationIds.circleCircleGetCircle,
        clientPageId: CircleRequestPageIds.getCircle,
        surface: AppUiSurfaces.circleDetail,
        pathParameters: const <String, String>{'circleId': 'circle-1'},
      );
      _expectCommand(
        log,
        operationId: AppCloudOperationIds.circleCircleUpdateCircle,
        clientPageId: CircleRequestPageIds.updateCircle,
        surface: AppUiSurfaces.circleDetail,
        method: 'PATCH',
        pathParameters: const <String, String>{'circleId': 'circle-1'},
        body: const <String, Object?>{
          'name': '摄影同行圈·杭州',
          'description': '已由 owner 更新',
          'tags': <String>['travel', 'photography', 'hangzhou'],
          'followEnabled': false,
        },
      );
      _expectQuery(
        log,
        operationId: AppCloudOperationIds.circleCircleGetCircleFeed,
        clientPageId: CircleRequestPageIds.getCircleFeed,
        surface: AppUiSurfaces.circleDetail,
        pathParameters: const <String, String>{'circleId': 'circle-1'},
        query: const <String, String>{
          'identity': 'works',
          'type': 'image',
          'cursor': 'feed-cursor',
          'limit': '7',
          'sort': 'latest',
        },
      );
      _expectQuery(
        log,
        operationId: AppCloudOperationIds.circleCircleGetCircleImpact,
        clientPageId: CircleRequestPageIds.getCircleImpact,
        surface: AppUiSurfaces.circleDetail,
        pathParameters: const <String, String>{'circleId': 'circle-1'},
      );
      _expectCommand(
        log,
        operationId: AppCloudOperationIds.circleCircleUpdateCircleSections,
        clientPageId: CircleRequestPageIds.updateCircleSections,
        surface: AppUiSurfaces.circleDetail,
        method: 'PATCH',
        pathParameters: const <String, String>{'circleId': 'circle-1'},
        body: const <String, Object?>{
          'sections': <Object?>[
            <String, Object?>{
              'sectionType': 'works',
              'visible': true,
              'order': 0,
            },
            <String, Object?>{
              'sectionType': 'members',
              'visible': true,
              'order': 1,
            },
          ],
        },
      );
      _expectCommand(
        log,
        operationId: AppCloudOperationIds.circleCircleArchiveCircle,
        clientPageId: CircleRequestPageIds.archiveCircle,
        surface: AppUiSurfaces.circleDetail,
        method: 'DELETE',
        pathParameters: const <String, String>{'circleId': 'circle-1'},
      );
    });

    test(
      'SearchCircles preserves filters and decodes stable public pages',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final facets = _facets(log, responseFor: _searchSuccessResponse);

        final first = await facets.query.search(
          const CircleSearchQuery(
            query: '摄影 同行',
            categoryId: 'travel',
            subCategory: 'photography',
            limit: 2,
          ),
        );
        final second = await facets.query.search(
          CircleSearchQuery(
            query: '摄影 同行',
            categoryId: 'travel',
            subCategory: 'photography',
            cursor: first.cursor,
            limit: 2,
          ),
        );

        expect(first.items, isNotNull);
        expect(first.items, isNotEmpty);
        expect(first.cursor, 'search-cursor-2');
        expect(first.facetBuckets, isNotNull);
        expect(first.facetBuckets!.single.facetKey, 'travel/photography');
        expect(first.facetBuckets!.single.facetCount, 3);
        expect(second.items, isNotNull);
        expect(second.items, isNotEmpty);
        expect(second.cursor, isNull);

        final orderedIds = <String>[
          ...first.items!.map((item) => item.circleId),
          ...second.items!.map((item) => item.circleId),
        ];
        expect(orderedIds, const <String>[
          'circle-public-1',
          'circle-public-2',
          'circle-public-3',
        ]);
        expect(orderedIds.toSet().length, orderedIds.length);
        expect(orderedIds, isNot(contains('circle-private-hidden')));
        expect(orderedIds, isNot(contains('circle-archived-hidden')));

        final requests = log
            .where(
              (request) =>
                  request.headers['X-Client-Operation-Id'] ==
                  AppCloudOperationIds.circleCircleSearchCircles,
            )
            .toList(growable: false);
        expect(requests, hasLength(2));
        _expectSearchRequest(requests.first, const <String, String>{
          'query': '摄影 同行',
          'categoryId': 'travel',
          'subCategory': 'photography',
          'limit': '2',
        });
        _expectSearchRequest(requests.last, const <String, String>{
          'query': '摄影 同行',
          'categoryId': 'travel',
          'subCategory': 'photography',
          'cursor': 'search-cursor-2',
          'limit': '2',
        });
      },
    );

    test(
      'SearchCircles cursor probing fails with canonical identity',
      () async {
        final log = <CapturedRemoteApiPathRequest>[];
        final facets = _facets(
          log,
          responseFor: (request) =>
              remoteApiPathJsonResponse(const <String, Object?>{
                'code': 'CIRCLE.USER.invalid_argument',
                'message': 'invalid search cursor',
              }, statusCode: 400),
        );

        await expectLater(
          facets.query.search(
            const CircleSearchQuery(
              query: '摄影 同行',
              categoryId: 'travel',
              subCategory: 'photography',
              cursor: 'circle-private-hidden',
              limit: 2,
            ),
          ),
          throwsA(
            isA<CloudException>()
                .having(
                  (failure) => failure.code,
                  'code',
                  'CIRCLE.USER.invalid_argument',
                )
                .having(
                  (failure) => failure.sourceOperationId,
                  'sourceOperationId',
                  AppCloudOperationIds.circleCircleSearchCircles,
                ),
          ),
        );
        expect(log, hasLength(1));
        _expectSearchRequest(log.single, const <String, String>{
          'query': '摄影 同行',
          'categoryId': 'travel',
          'subCategory': 'photography',
          'cursor': 'circle-private-hidden',
          'limit': '2',
        });
      },
    );

    test(
      'canonical failures preserve operation identity and retry intent',
      () async {
        for (final call in _operationCalls) {
          final log = <CapturedRemoteApiPathRequest>[];
          final facets = _facets(log, responseFor: _failureResponse);

          await expectLater(
            call.invoke(facets),
            throwsA(
              isA<CloudException>()
                  .having(
                    (failure) => failure.code,
                    'code',
                    call.command
                        ? 'CIRCLE.SYSTEM.circle_storage_write_failed'
                        : 'CIRCLE.SYSTEM.internal_error',
                  )
                  .having(
                    (failure) => failure.sourceOperationId,
                    'sourceOperationId',
                    call.operationId,
                  ),
            ),
          );

          final attempts = log
              .where(
                (request) =>
                    request.headers['X-Client-Operation-Id'] ==
                    call.operationId,
              )
              .toList(growable: false);
          expect(attempts.length, 2);
          if (call.operationId ==
              AppCloudOperationIds.circleCircleSearchCircles) {
            expect(
              attempts.map((request) => request.query),
              everyElement(
                equals(const <String, String>{
                  'query': '摄影 同行',
                  'categoryId': 'travel',
                  'subCategory': 'photography',
                  'cursor': 'search-retry-cursor',
                  'limit': '2',
                }),
              ),
            );
          }
          if (call.command) {
            expect(
              attempts.map((request) => request.headers['Idempotency-Key']),
              everyElement(
                '${attempts.first.headers['X-Client-Page-Id']}-intent',
              ),
            );
          }
        }
      },
    );

    test(
      'malformed success payloads fail closed for every operation',
      () async {
        for (final call in _operationCalls) {
          final log = <CapturedRemoteApiPathRequest>[];
          final facets = _facets(
            log,
            responseFor: (request) => remoteApiPathJsonResponse(
              request.headers['X-Client-Operation-Id'] ==
                      AppCloudOperationIds.circleCircleSearchCircles
                  ? const <String, Object?>{
                      'items': <Object?>[
                        <String, Object?>{
                          'circleId': 'missing-required-fields',
                        },
                      ],
                    }
                  : const <String, Object?>{},
            ),
          );

          await expectLater(
            call.invoke(facets),
            throwsA(anyOf(isA<FormatException>(), isA<CloudException>())),
            reason: '${call.operationId} must not synthesize a typed success',
          );
          expect(log, isNotEmpty);
        }
      },
    );
  });
}

final List<_OperationCall> _operationCalls = <_OperationCall>[
  (
    operationId: AppCloudOperationIds.circleCircleCreateCircle,
    command: true,
    invoke: (facets) =>
        facets.lifecycle.createCircle(CreateCircleCommand(name: '摄影同行圈')),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleGetCircle,
    command: false,
    invoke: (facets) =>
        facets.query.get(CircleDetailQuery(circleId: 'circle-1')),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleSearchCircles,
    command: false,
    invoke: (facets) => facets.query.search(
      const CircleSearchQuery(
        query: '摄影 同行',
        categoryId: 'travel',
        subCategory: 'photography',
        cursor: 'search-retry-cursor',
        limit: 2,
      ),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleUpdateCircle,
    command: true,
    invoke: (facets) => facets.lifecycle.updateCircle(
      UpdateCircleCommand(circleId: 'circle-1', name: '更新后圈子'),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleArchiveCircle,
    command: true,
    invoke: (facets) => facets.lifecycle.archiveCircle(
      ArchiveCircleCommand(circleId: 'circle-1'),
    ),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleGetCircleFeed,
    command: false,
    invoke: (facets) =>
        facets.query.feed(CircleFeedQuery(circleId: 'circle-1')),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleGetCircleImpact,
    command: false,
    invoke: (facets) =>
        facets.query.impact(CircleImpactQuery(circleId: 'circle-1')),
  ),
  (
    operationId: AppCloudOperationIds.circleCircleUpdateCircleSections,
    command: true,
    invoke: (facets) => facets.configuration.updateCircleSections(
      UpdateCircleSectionsCommand(
        circleId: 'circle-1',
        sections: const <CircleSectionConfig>[
          CircleSectionConfig(
            sectionType: CircleSectionType.works,
            visible: true,
            order: 0,
          ),
        ],
      ),
    ),
  ),
];

_CircleRemoteFacets _facets(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
}) {
  final client = buildRemoteApiPathOperationClient(
    log,
    responseFor: responseFor,
  );
  final query = CircleProductionComposition.generatedAdapter<CircleQueryReader>(
    CircleProductionAdapter.query,
    client: client,
    invocationContext: _context,
  );
  final lifecycleObject = CircleProductionComposition.generatedAdapter<Object>(
    CircleProductionAdapter.lifecycle,
    client: client,
    invocationContext: _context,
  );
  return (
    query: query,
    lifecycle: lifecycleObject as CircleLifecycleCommandWriter,
    configuration: lifecycleObject as CircleConfigurationCommandWriter,
  );
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) {
  final surface =
      clientPageId == CircleRequestPageIds.createCircle ||
          clientPageId == CircleRequestPageIds.searchCircles
      ? AppUiSurfaces.circlesList
      : AppUiSurfaces.circleDetail;
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    idempotencyKey: command ? '$clientPageId-intent' : null,
    actor: const CloudOperationActorContext(
      accountId: 'account-actor',
      personaId: 'persona-actor',
    ),
  );
}

CapturedRemoteApiPathRequest _requestFor(
  List<CapturedRemoteApiPathRequest> log,
  String operationId,
) => log.singleWhere(
  (request) => request.headers['X-Client-Operation-Id'] == operationId,
);

void _expectQuery(
  List<CapturedRemoteApiPathRequest> log, {
  required String operationId,
  required String clientPageId,
  required AppUiSurface surface,
  Map<String, String> pathParameters = const <String, String>{},
  Map<String, String> query = const <String, String>{},
}) {
  final request = _requestFor(log, operationId);
  expect(request.method, 'GET');
  expect(
    request.path,
    canonicalRemoteApiPath(operationId, pathParameters: pathParameters),
  );
  expect(request.query, query);
  expect(request.body, isEmpty);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: surface.id,
    operationId: operationId,
  );
}

void _expectCommand(
  List<CapturedRemoteApiPathRequest> log, {
  required String operationId,
  required String clientPageId,
  required AppUiSurface surface,
  required String method,
  Map<String, String> pathParameters = const <String, String>{},
  Map<String, Object?> body = const <String, Object?>{},
}) {
  final request = _requestFor(log, operationId);
  expect(request.method, method);
  expect(
    request.path,
    canonicalRemoteApiPath(operationId, pathParameters: pathParameters),
  );
  expect(request.query, isEmpty);
  expect(request.body, body);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers['Idempotency-Key'], '$clientPageId-intent');
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: surface.id,
    operationId: operationId,
  );
}

void _expectSearchRequest(
  CapturedRemoteApiPathRequest request,
  Map<String, String> query,
) {
  expect(request.method, 'GET');
  expect(
    request.path,
    canonicalRemoteApiPath(AppCloudOperationIds.circleCircleSearchCircles),
  );
  expect(request.query, query);
  expect(request.body, isEmpty);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: CircleRequestPageIds.searchCircles,
    surfaceId: AppUiSurfaces.circlesList.id,
    operationId: AppCloudOperationIds.circleCircleSearchCircles,
  );
}

http.Response _successResponse(http.Request request) {
  final operationId = request.headers['X-Client-Operation-Id'];
  final Object body = switch (operationId) {
    AppCloudOperationIds.circleCircleCreateCircle => _commandResult(
      version: 1,
      status: 'active',
    ),
    AppCloudOperationIds.circleCircleGetCircle => _circle,
    AppCloudOperationIds.circleCircleUpdateCircle => _commandResult(
      version: 2,
      status: 'active',
    ),
    AppCloudOperationIds.circleCircleArchiveCircle => _commandResult(
      version: 3,
      status: 'archived',
    ),
    AppCloudOperationIds.circleCircleGetCircleFeed => _feed,
    AppCloudOperationIds.circleCircleGetCircleImpact => _impact,
    AppCloudOperationIds.circleCircleUpdateCircleSections => _commandResult(
      version: 4,
      status: 'active',
    ),
    _ => throw StateError('unexpected circle operation: $operationId'),
  };
  return remoteApiPathJsonResponse(body);
}

http.Response _failureResponse(http.Request request) {
  final operationId = request.headers['X-Client-Operation-Id'];
  final command = <String>{
    AppCloudOperationIds.circleCircleCreateCircle,
    AppCloudOperationIds.circleCircleUpdateCircle,
    AppCloudOperationIds.circleCircleArchiveCircle,
    AppCloudOperationIds.circleCircleUpdateCircleSections,
  }.contains(operationId);
  return remoteApiPathJsonResponse(<String, Object?>{
    'code': command
        ? 'CIRCLE.SYSTEM.circle_storage_write_failed'
        : 'CIRCLE.SYSTEM.internal_error',
    'message': 'canonical circle failure',
  }, statusCode: 503);
}

http.Response _searchSuccessResponse(http.Request request) {
  final cursor = request.url.queryParameters['cursor'];
  final body = switch (cursor) {
    null => _searchPageOne,
    'search-cursor-2' => _searchPageTwo,
    _ => throw StateError('unexpected SearchCircles cursor: $cursor'),
  };
  return remoteApiPathJsonResponse(body);
}

Map<String, Object?> _commandResult({
  required int version,
  required String status,
}) => <String, Object?>{
  'circleId': 'circle-1',
  'version': version,
  'status': status,
  'idempotentReplay': false,
};

const Map<String, Object?> _circle = <String, Object?>{
  'id': 'circle-1',
  'name': '摄影同行圈',
  'description': '真实 typed Circle',
  'ownerId': 'persona-owner',
  'ownerDisplayNameSnapshot': '摄影主理人',
  'category': 'travel',
  'subCategory': 'photography',
  'tags': <String>['travel', 'photography'],
  'memberCount': 42,
  'postCount': 18,
  'weeklyActiveCount': 9,
  'version': 7,
  'status': 'active',
  'visibility': 'public',
  'joinPolicy': 'approval',
  'kind': 'interest',
  'displaySubjectType': 'circle',
  'followEnabled': true,
  'autoSyncChat': true,
  'sectionConfig': <Object?>[
    <String, Object?>{'sectionType': 'works', 'visible': true, 'order': 0},
  ],
  'storageUsedBytes': 1024,
  'storageQuotaBytes': 1048576,
  'createdAt': '2026-08-08T08:00:00Z',
  'updatedAt': '2026-08-08T09:00:00Z',
};

const Map<String, Object?> _feed = <String, Object?>{
  'items': <Object?>[
    <String, Object?>{
      'circleId': 'circle-1',
      'placementId': 'placement-1',
      'postId': 'post-1',
      'contentType': 'image',
      'authorId': 'persona-author',
      'authorDisplayName': '摄影者',
      'authorVerified': true,
      'title': '西湖日出',
      'imageUrls': <String>['https://media.example/post-1.jpg'],
      'likeCount': 12,
      'commentCount': 3,
      'shareCount': 2,
      'publishedAt': '2026-08-08T09:00:00Z',
      'pinned': false,
      'featured': true,
    },
  ],
  'cursor': 'feed-next',
};

const Map<String, Object?> _impact = <String, Object?>{
  'circleId': 'circle-1',
  'total': 1,
  'items': <Object?>[
    <String, Object?>{
      'helpType': 'shared_interest',
      'action': 'view_circle',
      'intersectionDimension': 'photography',
      'tagRef': 'photography',
      'source': 'canonical_projection',
      'count': 12,
      'primaryText': '12 位摄影爱好者共同参与',
      'subtitleText': '查看共同记录',
      'impactId': 'impact-1',
      'primarySpans': <Object?>[],
      'sampleVisuals': <Object?>[],
      'actionHints': <Object?>[],
      'evidenceSnapshotId': 'impact:circle-1:photography',
      'countObjectKind': 'persona',
      'iconKey': 'camera',
    },
  ],
};

const Map<String, Object?> _searchPageOne = <String, Object?>{
  'items': <Object?>[
    <String, Object?>{
      'circleId': 'circle-public-1',
      'name': '杭州旅行摄影',
      'description': '公开可搜索 Circle',
      'categoryId': 'travel',
      'subCategory': 'photography',
      'kind': 'interest',
      'displaySubjectType': 'circle',
      'memberCount': 42,
      'postCount': 18,
      'highlightText': '旅行摄影',
      'matchedField': 'name',
    },
    <String, Object?>{
      'circleId': 'circle-public-2',
      'name': '城市摄影同行',
      'description': '公开可搜索 Circle',
      'categoryId': 'travel',
      'subCategory': 'photography',
      'kind': 'interest',
      'displaySubjectType': 'circle',
      'memberCount': 31,
      'postCount': 12,
      'highlightText': '摄影同行',
      'matchedField': 'name',
    },
  ],
  'facetBuckets': <Object?>[
    <String, Object?>{
      'facetKey': 'travel/photography',
      'label': '旅行摄影',
      'categoryId': 'travel',
      'subCategory': 'photography',
      'facetCount': 3,
    },
  ],
  'cursor': 'search-cursor-2',
};

const Map<String, Object?> _searchPageTwo = <String, Object?>{
  'items': <Object?>[
    <String, Object?>{
      'circleId': 'circle-public-3',
      'name': '周末摄影同好',
      'description': '公开可搜索 Circle',
      'categoryId': 'travel',
      'subCategory': 'photography',
      'kind': 'interest',
      'displaySubjectType': 'circle',
      'memberCount': 19,
      'postCount': 7,
      'highlightText': '摄影',
      'matchedField': 'name',
    },
  ],
  'facetBuckets': <Object?>[
    <String, Object?>{
      'facetKey': 'travel/photography',
      'label': '旅行摄影',
      'categoryId': 'travel',
      'subCategory': 'photography',
      'facetCount': 3,
    },
  ],
};
