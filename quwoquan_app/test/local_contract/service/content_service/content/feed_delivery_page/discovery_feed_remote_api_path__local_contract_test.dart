/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

RemoteContentDiscoveryFeedQuery _contentFeedQuery(
  List<CapturedRemoteApiPathRequest> log, {
  Future<List<String>> Function()? blockedKeywordsLoader,
}) {
  final client = buildRemoteApiPathOperationClient(
    log,
    responseFor: _responseFor,
  );
  return RemoteContentDiscoveryFeedQuery(
    client: client,
    invocationContext: (clientPageId) => CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.homeFeed.id,
      routeId: AppUiSurfaces.homeFeed.routeId,
      clientPageId: clientPageId,
      actor: const CloudOperationActorContext(personaId: 'persona-1'),
    ),
    blockedKeywordsLoader:
        blockedKeywordsLoader ?? () async => const <String>[],
  );
}

http.Response _responseFor(http.Request request) {
  if (request.method == 'GET' &&
      request.url.path ==
          canonicalRemoteApiPath(AppCloudOperationIds.contentPostGetFeed)) {
    return remoteApiPathJsonResponse({
      'items': <dynamic>[],
      'outcome': 'empty',
      'emptyReason': 'no_eligible_content',
      'feedRequestId': 'feed-request-1',
      'objectCards': <dynamic>[],
    });
  }
  return remoteApiPathJsonResponse({
    'items': <dynamic>[],
    'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
    'cursor': null,
  });
}

void main() {
  group('Content discovery feed Remote — operations.yaml 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteContentDiscoveryFeedQuery repo;

    setUp(() {
      log = [];
      repo = _contentFeedQuery(log);
    });

    test('listDiscoveryFeedPage → GET /content/feed', () async {
      await repo.listDiscoveryFeedPage(category: 'all');
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(AppCloudOperationIds.contentPostGetFeed),
      );
    });

    test('listDiscoveryFeedPage 透传 sessionId / feedRequestId', () async {
      await repo.listDiscoveryFeedPage(
        category: 'photo',
        sessionId: 'session-001',
        feedRequestId: 'feed-req-001',
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(AppCloudOperationIds.contentPostGetFeed),
      );
      expect(log.last.query['sessionId'], 'session-001');
      expect(log.last.query['feedRequestId'], 'feed-req-001');
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: ContentRequestPageIds.getFeed,
        surfaceId: AppUiSurfaces.homeFeed.id,
        operationId: AppCloudOperationIds.contentPostGetFeed,
      );
    });

    test('listDiscoveryFeedPage 以编码 header 透传账号屏蔽关键词', () async {
      final filteredRepo = _contentFeedQuery(
        log,
        blockedKeywordsLoader: () async => <String>['重复,营销', '剧透'],
      );

      await filteredRepo.listDiscoveryFeedPage(category: 'photo');

      expect(
        log.last.headers['X-Blocked-Keywords'],
        '%E9%87%8D%E5%A4%8D%2C%E8%90%A5%E9%94%80,%E5%89%A7%E9%80%8F',
      );
    });

    test('listDiscoveryFeedPage 透传 identity/type query', () async {
      await repo.listDiscoveryFeedPage(
        category: 'work',
        identity: 'work',
        type: 'article',
      );
      expect(log.last.query['identity'], 'work');
      expect(log.last.query['type'], 'article');
    });
  });
}
