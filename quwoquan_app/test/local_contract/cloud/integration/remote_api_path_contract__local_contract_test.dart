/// L1a+ 端云集成契约测试：Remote Repository URL 路径与 metadata service.yaml 对齐
///
/// 通过注入 mock HTTP client 捕获实际请求的 URL，验证：
/// 1. HTTP 方法正确（GET/POST/PATCH/DELETE）
/// 2. URL 路径与 service.yaml 定义一致
/// 3. CloudRequestHeaders 正确注入
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/content/remote/footprint_query_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_query_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reaction_facets_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reader_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/report_command_remote.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/integration/remote/location_query_remote.dart';
import 'package:quwoquan_app/cloud/services/user/block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';
import '../../../support/homepage_remote_test_support.dart';

const _baseUrl = 'https://test-gateway.example.com';

typedef _CapturedRequest = ({
  String method,
  String path,
  Map<String, String> query,
  Map<String, String> headers,
  Map<String, dynamic> body,
});

MockClient _captureClient(List<_CapturedRequest> log) {
  return MockClient((request) async {
    final decodedRequestBody = request.body.isEmpty
        ? const <String, dynamic>{}
        : jsonDecode(request.body);
    log.add((
      method: request.method,
      path: request.url.path,
      query: request.url.queryParameters,
      headers: Map<String, String>.from(request.headers),
      body: decodedRequestBody is Map
          ? Map<String, dynamic>.from(decodedRequestBody)
          : const <String, dynamic>{},
    ));

    final path = request.url.path;
    if (request.method == 'GET' &&
        path == EntityApiMetadata.getHomepageShellPath(homepageId: 'hp1')) {
      return http.Response(
        json.encode({
          'homepage': {
            'homepageId': 'hp1',
            'homepageType': 'sight',
            'title': '测试主页',
          },
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == EntityApiMetadata.getObjectPageBundlePath(homepageId: 'hp1')) {
      return http.Response(
        json.encode({
          'objectType': 'homepage',
          'objectId': 'hp1',
          'canonicalEntityId': 'entity:hp1',
          'title': '测试主页',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path ==
            EntityApiMetadata.getHomepageReviewSummaryPath(homepageId: 'hp1')) {
      return http.Response(
        '{"ratingCount":0}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path ==
            EntityApiMetadata.getHomepageRelatedGroupsPath(homepageId: 'hp1')) {
      return http.Response(
        '{"groups":[]}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'POST' &&
        path == ContentApiMetadata.createReportPath) {
      return http.Response('', 204);
    }
    if (request.method == 'GET' &&
        path == ContentApiMetadata.getContentReactionStatePath(postId: 'p1')) {
      return http.Response(
        json.encode({
          'found': false,
          'postId': 'p1',
          'liked': false,
          'version': 0,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
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
      return http.Response(
        '{}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }

    final body = json.encode({
      'items': <dynamic>[],
      'data': <String, dynamic>{'id': 'mock_id', 'type': 'mock'},
      'cursor': null,
    });
    return http.Response(
      body,
      200,
      headers: {'content-type': 'application/json'},
    );
  });
}

final class _TestCloudClientContext implements CloudClientContextProvider {
  const _TestCloudClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'integration-contract-session',
      deviceActorId: 'integration-contract-device',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _TestAuthTokenProvider implements CloudAuthTokenProvider {
  const _TestAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'integration-contract-token';
}

void _expectPageHeaders(Map<String, String> headers, {required String pageId}) {
  expect(headers['X-Client-Page-Id'], pageId);
  expect(headers['X-Trace-Id'], contains(pageId));
  expect(headers['X-Request-Id'], contains(pageId));
}

void _expectSurfaceOperationHeaders(
  Map<String, String> headers, {
  required String clientPageId,
  required String surfaceId,
  required String operationId,
}) {
  expect(headers['X-Client-Page-Id'], clientPageId);
  expect(headers['X-Client-Surface-Id'], surfaceId);
  expect(headers['X-Client-Operation-Id'], operationId);
  expect(headers['X-Trace-Id'], contains(surfaceId));
  expect(headers['X-Trace-Id'], contains(operationId));
  expect(headers['X-Request-Id'], contains(surfaceId));
  expect(headers['X-Request-Id'], contains(operationId));
}

void main() {
  group('CircleRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteCircleRepository repo;

    setUp(() {
      log = [];
      repo = RemoteCircleRepository(
        httpClient: CloudHttpClient(client: _captureClient(log)),
        baseUrl: _baseUrl,
      );
    });

    test('listCircles → GET /circles', () async {
      try {
        await repo.listCircles();
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.listCirclesPath);
    });

    test('searchCircles → GET /circles/search', () async {
      await repo.searchCircles(
        query: '摄影',
        categoryId: 'art',
        subCategory: 'photo',
        limit: 6,
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.searchCirclesPath);
      expect(log.last.query['query'], '摄影');
      expect(log.last.query['categoryId'], 'art');
      expect(log.last.query['subCategory'], 'photo');
      expect(log.last.query['limit'], '6');
      _expectPageHeaders(
        log.last.headers,
        pageId: CircleRequestPageIds.searchCircles,
      );
    });

    test('getCircle → GET /circles/{circleId}', () async {
      try {
        await repo.getCircle('c1');
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.getCirclePath(circleId: 'c1'));
    });

    test('createCircle → POST /circles', () async {
      await repo.createCircle(CircleCreateWireDto.fromMap({'name': 'test'}));
      expect(log.last.method, 'POST');
      expect(log.last.path, CircleApiMetadata.createCirclePath);
    });

    test('updateCircle → PATCH /circles/{circleId}', () async {
      await repo.updateCircle(
        'c1',
        CircleUpdateWireDto.fromMap({'name': 'updated'}),
      );
      expect(log.last.method, 'PATCH');
      expect(log.last.path, CircleApiMetadata.updateCirclePath(circleId: 'c1'));
    });

    test('archiveCircle → DELETE /circles/{circleId}', () async {
      await repo.archiveCircle('c1');
      expect(log.last.method, 'DELETE');
      expect(
        log.last.path,
        CircleApiMetadata.archiveCirclePath(circleId: 'c1'),
      );
    });

    test('getCircleFeed → GET /circles/{circleId}/feed', () async {
      try {
        await repo.getCircleFeed('c1');
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        CircleApiMetadata.getCircleFeedPath(circleId: 'c1'),
      );
    });

    test('getCircleFeed 透传 identity/type query', () async {
      try {
        await repo.getCircleFeed('c1', identity: 'work', type: 'article');
      } catch (_) {}
      expect(log.last.query['identity'], 'work');
      expect(log.last.query['type'], 'article');
    });

    test('getCircleStats → GET /circles/{circleId}/stats', () async {
      await repo.getCircleStats('c1');
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        CircleApiMetadata.getCircleStatsPath(circleId: 'c1'),
      );
    });

    test('updateSections → PATCH /circles/{circleId}/sections', () async {
      await repo.updateSections('c1', []);
      expect(log.last.method, 'PATCH');
      expect(
        log.last.path,
        CircleApiMetadata.updateCircleSectionsPath(circleId: 'c1'),
      );
    });
  });

  group('Content facets Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteContentRepository repo;
    late RemoteContentPostReactionFacet reactions;

    setUp(() {
      log = [];
      repo = RemoteContentRepository(
        httpClient: CloudHttpClient(client: _captureClient(log)),
      );
      reactions = RemoteContentPostReactionFacet(
        client: buildGeneratedCloudOperationClient(
          httpClient: CloudHttpClient(
            client: _captureClient(log),
            authTokenProvider: const _TestAuthTokenProvider(),
          ),
          clientContextProvider: const _TestCloudClientContext(),
          telemetrySink: RecordingCloudOperationTelemetrySink(),
          environment: CloudRuntimeEnvironment(
            environment: CloudEnvironment.gamma,
            gatewayBaseUri: Uri.parse(_baseUrl),
          ),
        ),
        invocationContext: (clientPageId, {required command}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.homeFeed.id,
              routeId: AppUiSurfaces.homeFeed.routeId,
              clientPageId: clientPageId,
              idempotencyKey: command ? 'content-reaction-path-contract' : null,
              actor: const CloudOperationActorContext(personaId: 'persona-1'),
            ),
      );
    });

    test('listDiscoveryFeed → GET /content/feed', () async {
      await repo.listDiscoveryFeed(category: 'all');
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.getFeedPath);
    });

    test('listDiscoveryFeedPage 透传 sessionId / feedRequestId', () async {
      await repo.listDiscoveryFeedPage(
        category: 'photo',
        sessionId: 'session-001',
        feedRequestId: 'feed-req-001',
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.getFeedPath);
      expect(log.last.query['sessionId'], 'session-001');
      expect(log.last.query['feedRequestId'], 'feed-req-001');
      _expectPageHeaders(
        log.last.headers,
        pageId: ContentRequestPageIds.getFeed,
      );
    });

    test('listDiscoveryFeed 透传 identity/type query', () async {
      await repo.listDiscoveryFeed(
        category: 'work',
        identity: 'work',
        type: 'article',
      );
      expect(log.last.query['identity'], 'work');
      expect(log.last.query['type'], 'article');
    });

    test(
      'updatePostSettings → PATCH /content/posts/{postId}/settings',
      () async {
        try {
          await repo.updatePostSettings(
            postId: 'p1',
            body: UpdatePostSettingsRequestWire.fromMap({
              'assistantUsePolicy': 'exclude',
            }),
          );
        } catch (_) {}
        expect(log.last.method, 'PATCH');
        expect(
          log.last.path,
          ContentApiMetadata.updatePostSettingsPath(postId: 'p1'),
        );
      },
    );

    test(
      'promotePostToWork → POST /content/posts/{postId}:promoteToWork',
      () async {
        try {
          await repo.promotePostToWork(
            postId: 'p1',
            body: PromotePostToWorkRequestWire.fromMap({
              'contentType': 'image',
            }),
          );
        } catch (_) {}
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          ContentApiMetadata.promotePostToWorkPath(postId: 'p1'),
        );
      },
    );

    test('likePost → POST /content/posts/{postId}/like', () async {
      try {
        await reactions.likePost(LikeContentPostCommand(postId: 'p1'));
      } catch (_) {}
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.likePostPath(postId: 'p1'));
    });

    test('unlikePost → DELETE /content/posts/{postId}/like', () async {
      try {
        await reactions.unlikePost(UnlikeContentPostCommand(postId: 'p1'));
      } catch (_) {}
      expect(log.last.method, 'DELETE');
      expect(log.last.path, ContentApiMetadata.unlikePostPath(postId: 'p1'));
    });

    test('reportBehaviors → POST /content/behaviors', () async {
      await repo.reportBehaviors(events: []);
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.reportBehaviorsPath);
    });

    test('getCounters → GET /content/posts/{postId}/counters', () async {
      await repo.getCounters(postId: 'p1');
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.getCountersPath(postId: 'p1'));
    });
  });

  group('RemoteContentReportAdapter — generated operation 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteContentReportAdapter adapter;

    setUp(() {
      log = [];
      final client = buildGeneratedCloudOperationClient(
        httpClient: CloudHttpClient(
          client: _captureClient(log),
          authTokenProvider: const _TestAuthTokenProvider(),
        ),
        clientContextProvider: const _TestCloudClientContext(),
        telemetrySink: RecordingCloudOperationTelemetrySink(),
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_baseUrl),
        ),
      );
      adapter = RemoteContentReportAdapter(
        client: client,
        invocationContext: (clientPageId) {
          return CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.homeFeed.id,
            routeId: AppUiSurfaces.homeFeed.routeId,
            clientPageId: clientPageId,
            idempotencyKey: 'report-path-contract-idempotency-key',
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
          );
        },
      );
    });

    test('createReport → POST /content/reports', () async {
      await adapter.createReport(
        CreateContentReportCommand(
          targetId: 'p1',
          targetType: ContentReportTargetType.post,
          reason: ContentReportReason.spam,
        ),
      );
      expect(log.last.method, 'POST');
      expect(log.last.path, ContentApiMetadata.createReportPath);
      expect(
        log.last.headers['Idempotency-Key'],
        'report-path-contract-idempotency-key',
      );
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: ContentRequestPageIds.createReport,
        surfaceId: AppUiSurfaces.homeFeed.id,
        operationId: AppCloudOperationIds.contentReportCreateReport,
      );
    });
  });

  group('Content Post query adapters — generated operation 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteContentPostSearchAdapter searchAdapter;
    late RemoteFootprintRepository footprintAdapter;
    late RemoteContentPostReaderAdapter workBrowserReader;
    late GeneratedCloudOperationClient client;

    setUp(() {
      log = [];
      client = buildGeneratedCloudOperationClient(
        httpClient: CloudHttpClient(
          client: _captureClient(log),
          authTokenProvider: const _TestAuthTokenProvider(),
        ),
        clientContextProvider: const _TestCloudClientContext(),
        telemetrySink: RecordingCloudOperationTelemetrySink(),
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_baseUrl),
        ),
      );
      searchAdapter = RemoteContentPostSearchAdapter(
        client: client,
        invocationContext: (clientPageId) {
          return CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
            routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
          );
        },
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

    test('searchPosts → GET /content/posts/search', () async {
      await searchAdapter.searchPosts(
        query: '摄影',
        identity: 'work',
        type: 'article',
        categoryId: 'art',
        subCategory: 'photo',
        limit: 9,
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.searchPostsPath);
      expect(log.last.query['query'], '摄影');
      expect(log.last.query['identity'], 'work');
      expect(log.last.query['type'], 'article');
      expect(log.last.query['categoryId'], 'art');
      expect(log.last.query['subCategory'], 'photo');
      expect(log.last.query['limit'], '9');
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: ContentRequestPageIds.searchPosts,
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        operationId: AppCloudOperationIds.contentPostSearchPosts,
      );
    });

    test('getMyFootprint → GET /content/footprint', () async {
      await footprintAdapter.getMyFootprint(
        type: 'viewed',
        cursor: '2026-07-13T09:00:00Z',
        limit: 9,
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, ContentApiMetadata.getMyFootprintPath);
      expect(log.last.query['type'], 'viewed');
      expect(log.last.query['cursor'], '2026-07-13T09:00:00Z');
      expect(log.last.query['limit'], '9');
      _expectSurfaceOperationHeaders(
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
      expect(log.last.path, ContentApiMetadata.getPostPath(postId: 'p1'));
      _expectSurfaceOperationHeaders(
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
        ContentApiMetadata.listUserPostsPath(subAccountId: 'author-1'),
      );
      expect(log.last.query, <String, String>{
        'identity': 'work',
        'type': 'article',
        'visibility': 'public',
        'cursor': 'cursor-1',
        'limit': '9',
      });
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: ContentRequestPageIds.listUserPosts,
        surfaceId: AppUiSurfaces.userProfile.id,
        operationId: AppCloudOperationIds.contentPostListUserPosts,
      );
    });
  });

  group('UserRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteUserRepository repo;

    setUp(() {
      log = [];
      repo = RemoteUserRepository(
        httpClient: CloudHttpClient(client: _captureClient(log)),
        baseUrl: _baseUrl,
      );
    });

    test('listPersonas → GET /user/personas', () async {
      await repo.listPersonas();
      expect(log.last.method, 'GET');
      expect(log.last.path, UserApiMetadata.listPersonasPath);
    });

    test('getPersonaManagementSummary → GET /user/personas/summary', () async {
      await repo.getPersonaManagementSummary();
      expect(log.last.method, 'GET');
      expect(log.last.path, UserApiMetadata.getPersonaManagementSummaryPath);
    });

    test('getActivePersonaContext → GET /user/personas/active', () async {
      await repo.getActivePersonaContext();
      expect(log.last.method, 'GET');
      expect(log.last.path, UserApiMetadata.getActivePersonaContextPath);
    });

    test('createPersona → POST /user/personas', () async {
      await repo.createPersona(displayName: '摄影分身');
      expect(log.last.method, 'POST');
      expect(log.last.path, UserApiMetadata.createPersonaPath);
    });

    test('updatePersona → PATCH /user/personas/{id}', () async {
      await repo.updatePersona('persona_1', displayName: '新分身名');
      expect(log.last.method, 'PATCH');
      expect(
        log.last.path,
        UserApiMetadata.updatePersonaPath(subAccountId: 'persona_1'),
      );
    });

    test('activatePersona → POST /user/personas/{id}/activate', () async {
      await repo.activatePersona('persona_1');
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        UserApiMetadata.activatePersonaPath(subAccountId: 'persona_1'),
      );
    });

    test(
      'deleteEmptyPersona → DELETE /user/personas/{id}:delete-empty',
      () async {
        await repo.deleteEmptyPersona('persona_1');
        expect(log.last.method, 'DELETE');
        expect(
          log.last.path,
          UserApiMetadata.deleteEmptyPersonaPath(subAccountId: 'persona_1'),
        );
      },
    );

    test(
      'applyPersonaProfileSync → POST /user/personas/{id}/profile-sync',
      () async {
        await repo.applyPersonaProfileSync(
          'persona_1',
          fieldsMask: const <String>['phone', 'email'],
        );
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          UserApiMetadata.applyPersonaProfileSyncPath(
            subAccountId: 'persona_1',
          ),
        );
      },
    );

    test(
      'getPersonaLifecycleGuard → GET /user/personas/{id}/lifecycle-guard',
      () async {
        await repo.getPersonaLifecycleGuard('persona_1');
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          UserApiMetadata.getPersonaLifecycleGuardPath(
            subAccountId: 'persona_1',
          ),
        );
      },
    );

    test('retirePersona → POST /user/personas/{id}/retire', () async {
      await repo.retirePersona('persona_1');
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        UserApiMetadata.retirePersonaPath(subAccountId: 'persona_1'),
      );
    });

    test(
      'getNotificationSettings → GET /user/settings/notifications',
      () async {
        await repo.getNotificationSettings();
        expect(log.last.method, 'GET');
        expect(log.last.path, UserApiMetadata.getNotificationSettingsPath);
      },
    );

    test('getPrivacySettings → GET /user/settings/privacy', () async {
      await repo.getPrivacySettings();
      expect(log.last.method, 'GET');
      expect(log.last.path, UserApiMetadata.getPrivacySettingsPath);
    });
  });

  group('BlockRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteBlockRepository repo;

    setUp(() {
      log = [];
      repo = RemoteBlockRepository(
        httpClient: CloudHttpClient(client: _captureClient(log)),
        baseUrl: _baseUrl,
      );
    });

    test(
      'blockUser → POST /user/sub-accounts/{targetSubAccountId}/block',
      () async {
        await repo.blockUser('u1');
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          UserApiMetadata.blockUserPath(targetSubAccountId: 'u1'),
        );
      },
    );

    test(
      'unblockUser → DELETE /user/sub-accounts/{targetSubAccountId}/block',
      () async {
        await repo.unblockUser('u1');
        expect(log.last.method, 'DELETE');
        expect(
          log.last.path,
          UserApiMetadata.unblockUserPath(targetSubAccountId: 'u1'),
        );
      },
    );
  });

  group('UserProfileRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteUserProfileRepository repo;

    setUp(() {
      log = [];
      repo = RemoteUserProfileRepository(
        httpClient: CloudHttpClient(client: _captureClient(log)),
      );
    });

    test('getUserStats → GET /user/profile/{userId}/stats', () async {
      try {
        await repo.getUserStats('u1');
      } catch (_) {}
      expect(log.isNotEmpty, isTrue);
      expect(log.last.method, 'GET');
    });
  });

  group('HomepageRepository Remote — service.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteHomepageRepository repo;

    setUp(() {
      log = [];
      repo = buildRemoteHomepageRepositoryForTest(
        httpClient: CloudHttpClient(client: _captureClient(log)),
        baseUrl: _baseUrl,
      );
    });

    test('searchHomepages → GET /homepages/search', () async {
      await repo.searchHomepages(
        query: '书店',
        homepageType: 'storefront',
        city: '深圳',
        status: 'published',
        limit: 7,
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, EntityApiMetadata.searchHomepagesPath);
      expect(log.last.query['query'], '书店');
      expect(log.last.query['homepageType'], 'storefront');
      expect(log.last.query['city'], '深圳');
      expect(log.last.query['status'], 'published');
      expect(log.last.query['limit'], '7');
      _expectSurfaceOperationHeaders(
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
        EntityApiMetadata.getHomepageShellPath(homepageId: 'hp1'),
      );
      _expectSurfaceOperationHeaders(
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
          EntityApiMetadata.getObjectPageBundlePath(homepageId: 'hp1'),
        );
        expect(log.last.query['referralSource'], 'entity_page');
        expect(log.last.query['feedRequestId'], 'feed-1');
        expect(log.last.query['recommendationTraceId'], 'trace-1');
        expect(log.last.query['experimentBucket'], 'A');
        expect(log.last.query['rolloutCohort'], 'city-hz');
        _expectSurfaceOperationHeaders(
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
          EntityApiMetadata.getHomepageReviewSummaryPath(homepageId: 'hp1'),
        );
        _expectSurfaceOperationHeaders(
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
          EntityApiMetadata.getHomepageRelatedGroupsPath(homepageId: 'hp1'),
        );
        _expectSurfaceOperationHeaders(
          log.last.headers,
          clientPageId: EntityRequestPageIds.getHomepageRelatedGroups,
          surfaceId: AppUiSurfaces.homepageDetail.id,
          operationId:
              AppCloudOperationIds.entityHomepageGetHomepageRelatedGroups,
        );
      },
    );
  });

  group('RemoteLocationQueryAdapter — generated operation 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteLocationQueryAdapter adapter;

    setUp(() {
      log = [];
      final client = buildGeneratedCloudOperationClient(
        httpClient: CloudHttpClient(client: _captureClient(log)),
        clientContextProvider: const _TestCloudClientContext(),
        telemetrySink: RecordingCloudOperationTelemetrySink(),
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_baseUrl),
        ),
      );
      adapter = RemoteLocationQueryAdapter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
          routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
      );
    });

    test('getNearbyLocations → GET /integration/location/nearby', () async {
      await adapter.getNearbyLocations(
        const NearbyLocationQueryParams(
          latitude: 30.2431,
          longitude: 120.1500,
          radiusMeters: 2000,
          limit: 8,
        ),
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, IntegrationApiMetadata.getNearbyLocationsPath);
      expect(log.last.query['lat'], '30.2431');
      expect(log.last.query['lng'], '120.15');
      expect(log.last.query['radiusMeters'], '2000');
      expect(log.last.query['limit'], '8');
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: IntegrationRequestPageIds.getNearbyLocations,
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        operationId: AppCloudOperationIds.integrationLocationGetNearbyLocations,
      );
    });

    test('searchLocations → GET /integration/location/search', () async {
      await adapter.searchLocations(
        const LocationSearchQueryParams(
          query: '西湖',
          cityCode: '330100',
          latitude: 30.2431,
          longitude: 120.1500,
          limit: 12,
        ),
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, IntegrationApiMetadata.searchLocationsPath);
      expect(log.last.query['q'], '西湖');
      expect(log.last.query['cityCode'], '330100');
      expect(log.last.query['lat'], '30.2431');
      expect(log.last.query['lng'], '120.15');
      expect(log.last.query['limit'], '12');
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: IntegrationRequestPageIds.searchLocations,
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        operationId: AppCloudOperationIds.integrationLocationSearchLocations,
      );
    });
  });
}
