/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/footprint_query_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.contentPostGetMyFootprint,
          )) {
    return remoteApiPathJsonResponse('{"items":[]}');
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.contentPostListUserPosts,
            pathParameters: const <String, String>{'personaId': 'author-1'},
          )) {
    return remoteApiPathJsonResponse('{"items":[],"hasMore":false}');
  }
  return remoteApiPathJsonResponse({
    'items': <dynamic>[],
    'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
    'cursor': null,
  });
}

void main() {
  group('Content post query adapters — generated operation 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteFootprintRepository footprintAdapter;
    late RemoteContentPostReaderAdapter workBrowserReader;
    late GeneratedCloudOperationClient client;

    setUp(() {
      log = [];
      client = buildRemoteApiPathOperationClient(
        log,
        responseFor: _responseFor,
      );
      footprintAdapter = RemoteFootprintRepository(
        client: client,
        invocationContext: (clientPageId) {
          return CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.myFootprint.id,
            routeId: AppUiSurfaces.myFootprint.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
          );
        },
      );
      workBrowserReader = RemoteContentPostReaderAdapter(
        client: client,
        invocationContext: (clientPageId) {
          return CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.workBrowser.id,
            routeId: AppUiSurfaces.workBrowser.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(),
          );
        },
      );
    });

    test('getMyFootprint → GET /content/footprint', () async {
      await footprintAdapter.getMyFootprint(
        type: 'viewed',
        cursor: '2026-07-13T09:00:00Z',
        limit: 9,
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(AppCloudOperationIds.contentPostGetMyFootprint),
      );
      expect(log.last.query['type'], 'viewed');
      expect(log.last.query['cursor'], '2026-07-13T09:00:00Z');
      expect(log.last.query['limit'], '9');
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: ContentRequestPageIds.getMyFootprint,
        surfaceId: AppUiSurfaces.myFootprint.id,
        operationId: AppCloudOperationIds.contentPostGetMyFootprint,
      );
    });

    test('getPost → GET /content/posts/{postId}', () async {
      try {
        await workBrowserReader.getPost(postId: 'p1');
      } catch (_) {
        // 捕获器只返回通用空 body；路径与 header 契约在此测试中仍已落盘。
      }
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.contentPostGetPost,
          pathParameters: const <String, String>{'postId': 'p1'},
        ),
      );
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: ContentRequestPageIds.getPost,
        surfaceId: AppUiSurfaces.workBrowser.id,
        operationId: AppCloudOperationIds.contentPostGetPost,
      );
    });

    test('listUserPosts → GET author path with typed query', () async {
      final reader = RemoteContentPostReaderAdapter(
        client: client,
        invocationContext: (clientPageId) {
          return CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.userProfile.id,
            routeId: AppUiSurfaces.userProfile.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(),
          );
        },
      );
      await reader.listUserPosts(
        userId: 'author-1',
        identity: 'work',
        type: 'article',
        visibility: 'public',
        cursor: 'cursor-1',
        limit: 9,
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        canonicalRemoteApiPath(
          AppCloudOperationIds.contentPostListUserPosts,
          pathParameters: const <String, String>{'personaId': 'author-1'},
        ),
      );
      expect(log.last.query, <String, String>{
        'identity': 'work',
        'type': 'article',
        'visibility': 'public',
        'cursor': 'cursor-1',
        'limit': '9',
      });
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: ContentRequestPageIds.listUserPosts,
        surfaceId: AppUiSurfaces.userProfile.id,
        operationId: AppCloudOperationIds.contentPostListUserPosts,
      );
    });
  });
}
