/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

// spec_ref: specs/feature-tree/circle-community/circle-management-and-stats/kpi-reporting/spec.md#gwt-001
// readiness_case: circle_get_circle_stats_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/circle_lifecycle_remote.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/circle_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.circleCircleSearchCircles,
          )) {
    return remoteApiPathJsonResponse('{"items":[],"facetBuckets":[]}');
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.circleCircleGetCircleStats,
            pathParameters: const <String, String>{'circleId': 'c1'},
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'circleId': 'c1',
      'memberCount': 0,
      'postCount': 0,
      'discussionCount': 0,
      'weeklyActiveCount': 0,
      'likeCount': 0,
      'storageUsedBytes': 0,
      'storageQuotaBytes': 0,
    });
  }
  final isWrite =
      request.method == 'POST' ||
      request.method == 'PATCH' ||
      request.method == 'DELETE';
  final isVoid =
      isWrite &&
      !path.endsWith('/posts') &&
      !path.endsWith('/circles') &&
      !path.endsWith('/comments') &&
      !path.endsWith('/files');
  if (isVoid) {
    return remoteApiPathJsonResponse('{}');
  }
  return remoteApiPathJsonResponse({
    'items': <dynamic>[],
    'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
    'cursor': null,
  });
}

void main() {
  group('CircleQueryReader Remote — operations.yaml 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteCircleQueryReader repo;
    late RemoteCircleLifecycleFacet lifecycle;

    setUp(() {
      log = [];
      final client = buildRemoteApiPathOperationClient(
        log,
        responseFor: _responseFor,
      );
      repo = RemoteCircleQueryReader(
        client: client,
        invocationContext: (clientPageId, {required command}) {
          final surface =
              clientPageId == CircleRequestPageIds.listCircles ||
                  clientPageId == CircleRequestPageIds.searchCircles ||
                  clientPageId == CircleRequestPageIds.listCircleDiscoveryFeed
              ? AppUiSurfaces.circlesList
              : AppUiSurfaces.circleDetail;
          return CloudOperationInvocationContext(
            surfaceId: surface.id,
            routeId: surface.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(
              accountId: 'account-1',
              personaId: 'persona-1',
            ),
          );
        },
      );
      lifecycle = RemoteCircleLifecycleFacet(
        client: client,
        invocationContext: (clientPageId, {required command}) =>
            CloudOperationInvocationContext(
              surfaceId: clientPageId == CircleRequestPageIds.createCircle
                  ? AppUiSurfaces.circlesList.id
                  : AppUiSurfaces.circleDetail.id,
              routeId: clientPageId == CircleRequestPageIds.createCircle
                  ? AppUiSurfaces.circlesList.routeId
                  : AppUiSurfaces.circleDetail.routeId,
              clientPageId: clientPageId,
              idempotencyKey: command ? 'circle-lifecycle-path-contract' : null,
              actor: const CloudOperationActorContext(
                accountId: 'account-1',
                personaId: 'persona-1',
              ),
            ),
      );
    });

    test('listCircles → GET /circles', () async {
      try {
        await repo.list(CircleListQuery());
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(AppCloudOperationIds.circleCircleListCircles),
      );
    });

    test('searchCircles → GET /circles/search', () async {
      await repo.search(
        CircleSearchQuery(
          query: '摄影',
          categoryId: 'art',
          subCategory: 'photo',
          limit: 6,
        ),
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(AppCloudOperationIds.circleCircleSearchCircles),
      );
      expect(log.last.query['query'], '摄影');
      expect(log.last.query['categoryId'], 'art');
      expect(log.last.query['subCategory'], 'photo');
      expect(log.last.query['limit'], '6');
      expect(
        log.last.headers['X-Client-Page-Id'],
        CircleRequestPageIds.searchCircles,
      );
    });

    test('getCircle → GET /circles/{circleId}', () async {
      try {
        await repo.get(CircleDetailQuery(circleId: 'c1'));
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.circleCircleGetCircle,
          pathParameters: const <String, String>{'circleId': 'c1'},
        ),
      );
    });

    test('createCircle → POST /circles', () async {
      try {
        await lifecycle.createCircle(CreateCircleCommand(name: 'test'));
      } on CloudException {
        // 路径契约只验证已发出的请求；响应 fixture 不承担业务 DTO 验证。
      }
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        canonicalRemoteApiPath(AppCloudOperationIds.circleCircleCreateCircle),
      );
    });

    test('updateCircle → PATCH /circles/{circleId}', () async {
      try {
        await lifecycle.updateCircle(
          UpdateCircleCommand(circleId: 'c1', name: 'updated'),
        );
      } catch (_) {}
      expect(log.last.method, 'PATCH');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.circleCircleUpdateCircle,
          pathParameters: const <String, String>{'circleId': 'c1'},
        ),
      );
    });

    test('archiveCircle → DELETE /circles/{circleId}', () async {
      try {
        await lifecycle.archiveCircle(ArchiveCircleCommand(circleId: 'c1'));
      } catch (_) {}
      expect(log.last.method, 'DELETE');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.circleCircleArchiveCircle,
          pathParameters: const <String, String>{'circleId': 'c1'},
        ),
      );
    });

    test('getCircleFeed → GET /circles/{circleId}/feed', () async {
      try {
        await repo.feed(CircleFeedQuery(circleId: 'c1'));
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.circleCircleGetCircleFeed,
          pathParameters: const <String, String>{'circleId': 'c1'},
        ),
      );
    });

    test('getCircleFeed 透传 identity/type query', () async {
      try {
        await repo.feed(
          CircleFeedQuery(
            circleId: 'c1',
            identity: 'work',
            type: 'article',
          ),
        );
      } catch (_) {}
      expect(log.last.query['identity'], 'work');
      expect(log.last.query['type'], 'article');
    });

    test('getCircleStats → GET /circles/{circleId}/stats', () async {
      final stats = await repo.stats(CircleStatsQuery(circleId: 'c1'));
      expect(stats.circleId, 'c1');
      expect(stats.memberCount, 0);
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.circleCircleGetCircleStats,
          pathParameters: const <String, String>{'circleId': 'c1'},
        ),
      );
    });

    test('updateSections → PATCH /circles/{circleId}/sections', () async {
      try {
        await lifecycle.updateCircleSections(
          UpdateCircleSectionsCommand(
            circleId: 'c1',
            sections: [
              CircleSectionConfig(
                sectionType: CircleSectionType.works,
                visible: true,
                order: 0,
              ),
            ],
          ),
        );
      } catch (_) {}
      expect(log.last.method, 'PATCH');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.circleCircleUpdateCircleSections,
          pathParameters: const <String, String>{'circleId': 'c1'},
        ),
      );
    });
  });
}
