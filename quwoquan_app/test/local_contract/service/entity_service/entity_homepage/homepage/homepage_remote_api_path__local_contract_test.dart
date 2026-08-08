/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-search-and-picker/spec.md#gwt-001
// readiness_case: homepage_search_homepages_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/adapters/homepage_facet_projection_adapter.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_remote_test_support.dart';

const _homepageDetail = <String, Object?>{
  'homepageId': 'hp1',
  'title': '测试主页',
  'homepageType': 'sight',
  'status': 'published',
  'claimStatus': 'unclaimed',
  'categoryTags': <String>[],
  'viewerFollow': <String, Object?>{
    'viewerFollowsHomepage': false,
    'followerCount': 0,
  },
  'verified': false,
  'ratingCount': 0,
  'contentPreview': <Object?>[],
  'questionPreview': <Object?>[],
  'relatedGroups': <Object?>[],
  'relationEdges': <Object?>[],
  'introductionAssets': <Object?>[],
  'sourceUrls': <String>[],
  'createdAt': '2026-07-20T00:00:00Z',
  'updatedAt': '2026-07-20T00:00:00Z',
};

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageShell,
            pathParameters: const <String, String>{'homepageId': 'hp1'},
          )) {
    return remoteApiPathJsonResponse({'homepage': _homepageDetail});
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetObjectPageBundle,
            pathParameters: const <String, String>{'homepageId': 'hp1'},
          )) {
    return remoteApiPathJsonResponse({
      'objectType': 'homepage',
      'objectId': 'hp1',
      'canonicalEntityId': 'entity:hp1',
      'title': '测试主页',
      'objectPageTemplate': 'homepage',
      'tagRefs': <String>[],
      'stats': <String, Object?>{},
      'intersectionReasons': <Object?>[],
      'highlightItems': <Object?>[],
      'contentSections': <String, Object?>{},
      'relatedObjects': <Object?>[],
      'relationEdges': <Object?>[],
    });
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
            pathParameters: const <String, String>{'homepageId': 'hp1'},
          )) {
    return remoteApiPathJsonResponse('{"ratingCount":0}');
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageRelatedGroups,
            pathParameters: const <String, String>{'homepageId': 'hp1'},
          )) {
    return remoteApiPathJsonResponse('{"groups":[]}');
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageSearchHomepages,
          )) {
    return remoteApiPathJsonResponse({
      'items': <Object?>[
        <String, Object?>{
          'homepageId': 'hp-search-1',
          'canonicalEntityId': 'entity:hp-search-1',
          'title': '深圳实验学校',
          'homepageType': 'school',
          'city': '深圳',
          'status': 'published',
          'averageRating': 4.8,
          'ratingCount': 128,
        },
      ],
    });
  }
  return remoteApiPathJsonResponse({
    'items': <dynamic>[],
    'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
    'cursor': null,
  });
}

void main() {
  group('HomepageFacetSet Remote — operations.yaml 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late HomepageFacetProjectionAdapter repo;

    setUp(() {
      log = [];
      repo = buildRemoteHomepageRepositoryForTest(
        httpClient: buildRemoteApiPathHttpClient(
          log,
          responseFor: _responseFor,
          authenticated: false,
        ),
        baseUrl: remoteApiPathTestBaseUrl,
      );
    });

    test('searchHomepages → GET /homepages/search', () async {
      final results = await repo.searchHomepages(
        query: '书店',
        homepageType: 'school',
        city: '深圳',
        status: 'published',
        limit: 7,
      );
      expect(results.single.title, '深圳实验学校');
      expect(results.single.homepageType, 'school');
      expect(results.single.city, '深圳');
      expect(results.single.averageRating, 4.8);
      expect(results.single.ratingCount, 128);
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.entityHomepageSearchHomepages,
        ),
      );
      expect(log.last.query['query'], '书店');
      expect(log.last.query['homepageType'], 'school');
      expect(log.last.query['city'], '深圳');
      expect(log.last.query['status'], 'published');
      expect(log.last.query['limit'], '7');
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: EntityRequestPageIds.searchHomepages,
        surfaceId: AppUiSurfaces.homepagePicker.id,
        operationId: AppCloudOperationIds.entityHomepageSearchHomepages,
      );
    });

    test('getHomepageShell → GET /homepages/{homepageId}/shell', () async {
      await repo.getHomepageShell('hp1');
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.entityHomepageGetHomepageShell,
          pathParameters: const <String, String>{'homepageId': 'hp1'},
        ),
      );
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: EntityRequestPageIds.getHomepageShell,
        surfaceId: AppUiSurfaces.homepageDetail.id,
        operationId: AppCloudOperationIds.entityHomepageGetHomepageShell,
      );
    });

    test(
      'getObjectPageBundle → GET /homepages/{homepageId}/object-page-bundle',
      () async {
        await repo.getObjectPageBundle(
          'hp1',
          referralSource: 'entity_page',
          feedRequestId: 'feed-1',
          recommendationTraceId: 'trace-1',
          experimentBucket: 'A',
          rolloutCohort: 'city-hz',
        );
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetObjectPageBundle,
            pathParameters: const <String, String>{'homepageId': 'hp1'},
          ),
        );
        expect(log.last.query['referralSource'], 'entity_page');
        expect(log.last.query['feedRequestId'], 'feed-1');
        expect(log.last.query['recommendationTraceId'], 'trace-1');
        expect(log.last.query['experimentBucket'], 'A');
        expect(log.last.query['rolloutCohort'], 'city-hz');
        expectRemoteApiPathHeaders(
          log.last.headers,
          clientPageId: EntityRequestPageIds.getObjectPageBundle,
          surfaceId: AppUiSurfaces.homepageDetail.id,
          operationId: AppCloudOperationIds.entityHomepageGetObjectPageBundle,
        );
      },
    );

    test(
      'getHomepageReviewSummary → GET /homepages/{homepageId}/review-summary',
      () async {
        await repo.getHomepageReviewSummary('hp1');
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
            pathParameters: const <String, String>{'homepageId': 'hp1'},
          ),
        );
        expectRemoteApiPathHeaders(
          log.last.headers,
          clientPageId: EntityRequestPageIds.getHomepageReviewSummary,
          surfaceId: AppUiSurfaces.homepageDetail.id,
          operationId:
              AppCloudOperationIds.entityHomepageGetHomepageReviewSummary,
        );
      },
    );

    test(
      'getHomepageRelatedGroups → GET /homepages/{homepageId}/related-groups',
      () async {
        await repo.getHomepageRelatedGroups('hp1');
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          canonicalRemoteApiPath(
            AppCloudOperationIds.entityHomepageGetHomepageRelatedGroups,
            pathParameters: const <String, String>{'homepageId': 'hp1'},
          ),
        );
        expectRemoteApiPathHeaders(
          log.last.headers,
          clientPageId: EntityRequestPageIds.getHomepageRelatedGroups,
          surfaceId: AppUiSurfaces.homepageDetail.id,
          operationId:
              AppCloudOperationIds.entityHomepageGetHomepageRelatedGroups,
        );
      },
    );
  });
}
