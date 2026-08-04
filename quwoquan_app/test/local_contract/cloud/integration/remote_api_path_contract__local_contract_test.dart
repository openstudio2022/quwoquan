/// L1a+ 端云集成契约测试：Remote Repository URL 路径与 metadata operations.yaml 对齐
///
/// 通过注入 mock HTTP client 捕获实际请求的 URL，验证：
/// 1. HTTP 方法正确（GET/POST/PATCH/DELETE）
/// 2. URL 路径与 operations.yaml 定义一致
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
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/remote/circle/circle/circle_lifecycle_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/circle/circle_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/profile_interaction/profile_interaction_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona/persona_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/user_settings/user_settings_remote.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/content/remote/discovery_feed_query_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/footprint_query_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reaction_facets_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reader_remote.dart';
import 'package:quwoquan_app/cloud/remote/search/search_query_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/report_command_remote.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/integration/remote/location_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona/persona_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/profile_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/user_profile_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';
import '../../../support/homepage_remote_test_support.dart';

const _baseUrl = 'https://test-gateway.example.com';

const _personaManagementItem = <String, Object?>{
  'personaId': 'persona_1',
  'displayName': '摄影分身',
  'userHandle': 'photo-persona',
  'isolationLevel': 'open',
  'profileVisibility': 'public',
  'isPrimary': false,
  'isActive': false,
  'status': 'active',
  'inheritsProfileFromOwner': true,
  'overriddenProfileFields': <String>[],
  'updatedAt': '2026-07-20T00:00:00Z',
};

const _personaProfile = <String, Object?>{
  'personaId': 'u1',
  'subjectType': 'persona',
  'userHandle': 'u1',
  'displayName': 'User One',
  'nicknameCustomized': false,
  'followerCount': 0,
  'followingCount': 0,
  'postCount': 0,
  'circleCount': 0,
  'likeCount': 0,
  'profileVisibility': 'public',
  'isolationLevel': 'open',
  'inheritsFromOwner': true,
  'updatedAt': '2026-07-20T00:00:00Z',
};

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

const _activePersonaContext = <String, Object?>{
  'ownerUserId': 'account-1',
  'personaId': 'persona_1',
  'subjectType': 'persona',
  'displayName': '摄影分身',
  'avatarUrl': '',
  'avatarVersion': 0,
  'isPrimary': false,
  'isolationLevel': 'open',
  'profileVisibility': 'public',
  'contextVersion': 1,
  'personaSnapshotVersion': 1,
  'sourceSurfaceId': 'profilePersonas',
  'explicitOverride': false,
  'switchedAt': '2026-07-20T12:00:00Z',
};

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
        json.encode({'homepage': _homepageDetail}),
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
          'objectPageTemplate': 'homepage',
          'tagRefs': <String>[],
          'stats': <String, Object?>{},
          'intersectionReasons': <Object?>[],
          'highlightItems': <Object?>[],
          'contentSections': <String, Object?>{},
          'relatedObjects': <Object?>[],
          'relationEdges': <Object?>[],
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
      return http.Response(
        'null',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'POST' && path == SearchApiMetadata.searchPath) {
      return http.Response(
        json.encode({
          'hits': <dynamic>[],
          'citations': <dynamic>[],
          'facets': <dynamic>[],
          'requestId': 'search-request-1',
          'relatedTerms': <String>[],
          'degradeSignals': <dynamic>[],
          'provenance': <String, dynamic>{
            'provider': 'elasticsearch',
            'generatedAt': '2026-07-31T00:00:00Z',
          },
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == UserApiMetadata.getNotificationSettingsPath) {
      return http.Response(
        json.encode({
          'userId': 'user-1',
          'enablePush': true,
          'enableMarketing': false,
          'quietHoursStart': null,
          'quietHoursEnd': null,
          'version': 1,
          'updatedAt': '2026-07-20T00:00:00Z',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == UserApiMetadata.getPrivacySettingsPath) {
      return http.Response(
        json.encode({
          'userId': 'user-1',
          'allowStrangerMsg': true,
          'profileVisibility': 'public',
          'contentLanguage': null,
          'feedPreference': null,
          'assistantEnabled': true,
          'blockedKeywords': <Object?>[],
          'version': 1,
          'updatedAt': '2026-07-20T00:00:00Z',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == UserApiMetadata.getPersonaProfilePath(personaId: 'u1')) {
      return http.Response(
        json.encode(_personaProfile),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'POST' &&
        path ==
            ContentApiMetadata.updateProfileInteractionStatePath(
              personaId: 'persona-1',
              interactionId: 'activity-1',
            )) {
      return http.Response(
        json.encode({
          'factId': 'fact-1',
          'activityId': 'activity-1',
          'state': 'read',
          'occurredAt': '2026-07-19T00:00:00Z',
          'replayed': false,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
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
    if (request.method == 'GET' && path == UserApiMetadata.listPersonasPath) {
      return http.Response(
        json.encode(<String, Object?>{
          'items': <Object?>[_personaManagementItem],
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == UserApiMetadata.getPersonaManagementSummaryPath) {
      return http.Response(
        json.encode(<String, Object?>{
          'items': <Object?>[_personaManagementItem],
          'quota': <String, Object?>{
            'ownerUserId': 'account-1',
            'totalCount': 1,
            'quotaLimit': 5,
            'remainingCount': 4,
            'activePersonaId': 'persona_1',
            'primaryPersonaId': 'persona_1',
          },
          'activeContext': _activePersonaContext,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == UserApiMetadata.getActivePersonaContextPath) {
      return http.Response(
        json.encode(_activePersonaContext),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path ==
            UserApiMetadata.getPersonaLifecycleGuardPath(
              personaId: 'persona_1',
            )) {
      return http.Response(
        json.encode(<String, Object?>{
          'personaId': 'persona_1',
          'requestedAction': 'retire',
          'allowed': true,
          'reason': 'allowed',
          'requiresSuccessor': false,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'POST' && path == UserApiMetadata.createPersonaPath) {
      return http.Response(
        json.encode(<String, Object?>{
          ..._personaManagementItem,
          'displayName': request.body.isEmpty
              ? ''
              : (jsonDecode(request.body)
                    as Map<String, dynamic>)['displayName'],
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'PATCH' &&
        path == UserApiMetadata.updatePersonaPath(personaId: 'persona_1')) {
      return http.Response(
        json.encode(<String, Object?>{
          ..._personaManagementItem,
          'displayName': '新分身名',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'POST' &&
        path == UserApiMetadata.activatePersonaPath(personaId: 'persona_1')) {
      return http.Response(
        json.encode(_activePersonaContext),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'POST' &&
        path ==
            UserApiMetadata.applyPersonaProfileSyncPath(
              personaId: 'persona_1',
            )) {
      return http.Response(
        json.encode({
          'status': 'ok',
          'appliedCount': 1,
          'fieldsMask': <String>['phone', 'email'],
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'POST' &&
        path == UserApiMetadata.retirePersonaPath(personaId: 'persona_1')) {
      return http.Response(
        json.encode({
          'personaId': 'persona_1',
          'requestedAction': 'retire',
          'allowed': true,
          'reason': 'allowed',
          'requiresSuccessor': false,
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

    if (request.method == 'GET' && path == ContentApiMetadata.getFeedPath) {
      return http.Response(
        json.encode({
          'items': <dynamic>[],
          'outcome': 'empty',
          'emptyReason': 'no_eligible_content',
          'feedRequestId': 'feed-request-1',
          'objectCards': <dynamic>[],
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }

    if (request.method == 'GET' &&
        path == CircleApiMetadata.searchCirclesPath) {
      return http.Response(
        '{"items":[],"facetBuckets":[]}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == CircleApiMetadata.getCircleStatsPath(circleId: 'c1')) {
      return http.Response(
        json.encode(<String, Object?>{
          'circleId': 'c1',
          'memberCount': 0,
          'postCount': 0,
          'discussionCount': 0,
          'weeklyActiveCount': 0,
          'likeCount': 0,
          'storageUsedBytes': 0,
          'storageQuotaBytes': 0,
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == ContentApiMetadata.getMyFootprintPath) {
      return http.Response(
        '{"items":[]}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == ContentApiMetadata.listUserPostsPath(personaId: 'author-1')) {
      return http.Response(
        '{"items":[],"hasMore":false}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        (path ==
                ContentApiMetadata.listProfileInteractionActivitiesReceivedPath(
                  personaId: 'persona-1',
                ) ||
            path ==
                ContentApiMetadata.listProfileInteractionActivitiesSentPath(
                  personaId: 'persona-1',
                ))) {
      return http.Response(
        '{"items":[],"hasMore":false}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        path == EntityApiMetadata.searchHomepagesPath) {
      return http.Response(
        '{"items":[]}',
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    if (request.method == 'GET' &&
        (path == IntegrationApiMetadata.getNearbyLocationsPath ||
            path == IntegrationApiMetadata.searchLocationsPath)) {
      return http.Response(
        '{"items":[]}',
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

RemoteContentRepository _contentRepository(
  List<_CapturedRequest> log, {
  Future<List<String>> Function()? blockedKeywordsLoader,
}) {
  final httpClient = CloudHttpClient(
    client: _captureClient(log),
    authTokenProvider: const _TestAuthTokenProvider(),
  );
  final client = buildGeneratedCloudOperationClient(
    httpClient: httpClient,
    clientContextProvider: const _TestCloudClientContext(),
    telemetrySink: RecordingCloudOperationTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse(_baseUrl),
    ),
  );
  return RemoteContentRepository(
    discoveryFeedQuery: RemoteContentDiscoveryFeedQuery(
      client: client,
      invocationContext: (clientPageId) => CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.homeFeed.id,
        routeId: AppUiSurfaces.homeFeed.routeId,
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(personaId: 'persona-1'),
      ),
      blockedKeywordsLoader:
          blockedKeywordsLoader ?? () async => const <String>[],
    ),
  );
}

void main() {
  group('CircleQueryReader Remote — operations.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteCircleQueryReader repo;
    late RemoteCircleLifecycleFacet lifecycle;

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
        await repo.list(const CircleListQuery());
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.listCirclesPath);
    });

    test('searchCircles → GET /circles/search', () async {
      await repo.search(
        const CircleSearchQuery(
          query: '摄影',
          categoryId: 'art',
          subCategory: 'photo',
          limit: 6,
        ),
      );
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.searchCirclesPath);
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
        await repo.get(const CircleDetailQuery(circleId: 'c1'));
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(log.last.path, CircleApiMetadata.getCirclePath(circleId: 'c1'));
    });

    test('createCircle → POST /circles', () async {
      try {
        await lifecycle.createCircle(CreateCircleCommand(name: 'test'));
      } on CloudException {
        // 路径契约只验证已发出的请求；响应 fixture 不承担业务 DTO 验证。
      }
      expect(log.last.method, 'POST');
      expect(log.last.path, CircleApiMetadata.createCirclePath);
    });

    test('updateCircle → PATCH /circles/{circleId}', () async {
      try {
        await lifecycle.updateCircle(
          UpdateCircleCommand(circleId: 'c1', name: 'updated'),
        );
      } catch (_) {}
      expect(log.last.method, 'PATCH');
      expect(log.last.path, CircleApiMetadata.updateCirclePath(circleId: 'c1'));
    });

    test('archiveCircle → DELETE /circles/{circleId}', () async {
      try {
        await lifecycle.archiveCircle(ArchiveCircleCommand(circleId: 'c1'));
      } catch (_) {}
      expect(log.last.method, 'DELETE');
      expect(
        log.last.path,
        CircleApiMetadata.archiveCirclePath(circleId: 'c1'),
      );
    });

    test('getCircleFeed → GET /circles/{circleId}/feed', () async {
      try {
        await repo.feed(const CircleFeedQuery(circleId: 'c1'));
      } catch (_) {}
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        CircleApiMetadata.getCircleFeedPath(circleId: 'c1'),
      );
    });

    test('getCircleFeed 透传 identity/type query', () async {
      try {
        await repo.feed(
          const CircleFeedQuery(
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
      await repo.stats(const CircleStatsQuery(circleId: 'c1'));
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        CircleApiMetadata.getCircleStatsPath(circleId: 'c1'),
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
        CircleApiMetadata.updateCircleSectionsPath(circleId: 'c1'),
      );
    });
  });

  group('Content facets Remote — operations.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteContentRepository repo;
    late RemoteContentPostReactionFacet reactions;

    setUp(() {
      log = [];
      repo = _contentRepository(log);
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
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: ContentRequestPageIds.getFeed,
        surfaceId: AppUiSurfaces.homeFeed.id,
        operationId: AppCloudOperationIds.contentPostGetFeed,
      );
    });

    test('listDiscoveryFeedPage 以编码 header 透传账号屏蔽关键词', () async {
      final filteredRepo = _contentRepository(
        log,
        blockedKeywordsLoader: () async => <String>['重复,营销', '剧透'],
      );

      await filteredRepo.listDiscoveryFeedPage(category: 'photo');

      expect(
        log.last.headers['X-Blocked-Keywords'],
        '%E9%87%8D%E5%A4%8D%2C%E8%90%A5%E9%94%80,%E5%89%A7%E9%80%8F',
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
          targetType: ReportTargetType.post,
          reason: ReportReason.spam,
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

  group('Search 与 Content query adapters — generated operation 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteCanonicalSearchQuery searchAdapter;
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
      searchAdapter = RemoteCanonicalSearchQuery(
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

    test('canonical search → POST /search generated operation', () async {
      await searchAdapter.search(
        CanonicalSearchQuery(
          query: '摄影',
          objectTypes: const <String>['article'],
          limit: 9,
        ),
      );
      expect(log.last.method, 'POST');
      expect(log.last.path, SearchApiMetadata.searchPath);
      expect(log.last.body['query'], '摄影');
      expect(log.last.body['objectTypes'], const <String>['article']);
      expect(log.last.body['limit'], 9);
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: SearchRequestPageIds.search,
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        operationId: AppCloudOperationIds.searchSearchIndexViewSearch,
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
        ContentApiMetadata.listUserPostsPath(personaId: 'author-1'),
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

  group('Profile interaction adapters — generated operation 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteProfileInteractionAdapter adapter;

    setUp(() {
      log = [];
      adapter = RemoteProfileInteractionAdapter(
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
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.profileHome.id,
          routeId: AppUiSurfaces.profileHome.routeId,
          clientPageId: clientPageId,
          idempotencyKey:
              clientPageId ==
                  ContentRequestPageIds.updateProfileInteractionState
              ? 'profile-interaction-path-contract'
              : null,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
        ),
      );
    });

    test('received activities → canonical received path', () async {
      await adapter.listActivities(
        ContentProfileInteractionPageQuery(
          personaId: 'persona-1',
          type: InteractionActivityType.share,
          limit: 9,
        ),
        direction: InteractionDirection.received,
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        ContentApiMetadata.listProfileInteractionActivitiesReceivedPath(
          personaId: 'persona-1',
        ),
      );
    });

    test('sent activities → canonical sent path', () async {
      await adapter.listActivities(
        ContentProfileInteractionPageQuery(
          personaId: 'persona-1',
          type: InteractionActivityType.comment,
        ),
        direction: InteractionDirection.sent,
      );
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        ContentApiMetadata.listProfileInteractionActivitiesSentPath(
          personaId: 'persona-1',
        ),
      );
    });

    test('append read fact → canonical mutation path', () async {
      await adapter.appendReadFact(
        AppendContentProfileInteractionReadFactCommand(
          personaId: 'persona-1',
          activityId: 'activity-1',
          state: ProfileInteractionReadState.read,
        ),
      );
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        ContentApiMetadata.updateProfileInteractionStatePath(
          personaId: 'persona-1',
          interactionId: 'activity-1',
        ),
      );
    });
  });

  group('PersonaQuery Remote — operations.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemotePersonaQuery repo;
    late RemotePersonaCommandWriter personaWriter;

    setUp(() {
      log = [];
      final generatedClient = buildGeneratedCloudOperationClient(
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
      final userProfileQuery = RemoteUserProfileQueryFacet(
        client: generatedClient,
        invocationContext: (clientPageId, _) {
          final surface =
              clientPageId == UserRequestPageIds.getActivePersonaContext
              ? AppUiSurfaces.appShell
              : AppUiSurfaces.profilePersonas;
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
      repo = RemotePersonaQuery(
        managementQuery: userProfileQuery,
        publicProfileQuery: userProfileQuery,
      );
      personaWriter = RemotePersonaCommandWriter(
        client: generatedClient,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.profilePersonas.id,
          routeId: AppUiSurfaces.profilePersonas.routeId,
          clientPageId: clientPageId,
          idempotencyKey: 'persona-path-contract-idempotency-key',
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
        ),
      );
    });

    test('listPersonas → GET /user/persona/personas', () async {
      await repo.listPersonas();
      expect(log.last.method, 'GET');
      expect(log.last.path, UserApiMetadata.listPersonasPath);
    });

    test(
      'getPersonaManagementSummary → GET /user/persona/personas/summary',
      () async {
        await repo.getPersonaManagementSummary();
        expect(log.last.method, 'GET');
        expect(log.last.path, UserApiMetadata.getPersonaManagementSummaryPath);
      },
    );

    test(
      'getActivePersonaContext → GET /user/persona/personas/active',
      () async {
        await repo.getActivePersonaContext();
        expect(log.last.method, 'GET');
        expect(log.last.path, UserApiMetadata.getActivePersonaContextPath);
      },
    );

    test('createPersona → POST /user/persona/personas', () async {
      final result = await personaWriter.createPersona(
        CreatePersonaCommand(displayName: '摄影分身'),
      );
      expect(result.personaId, 'persona_1');
      expect(log.last.method, 'POST');
      expect(log.last.path, UserApiMetadata.createPersonaPath);
      expect(log.last.body['displayName'], '摄影分身');
    });

    test('updatePersona → PATCH /user/persona/personas/{id}', () async {
      final result = await personaWriter.updatePersona(
        UpdatePersonaCommand(personaId: 'persona_1', displayName: '新分身名'),
      );
      expect(result.displayName, '新分身名');
      expect(log.last.method, 'PATCH');
      expect(
        log.last.path,
        UserApiMetadata.updatePersonaPath(personaId: 'persona_1'),
      );
    });

    test(
      'activatePersona → POST /user/persona/personas/{id}/activate',
      () async {
        final result = await personaWriter.activatePersona(
          ActivatePersonaCommand(personaId: 'persona_1'),
        );
        expect(result.personaId, 'persona_1');
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          UserApiMetadata.activatePersonaPath(personaId: 'persona_1'),
        );
      },
    );

    test('Persona 移除单轨为 retire，不生成硬删除命令', () {
      final personaCommands = appCloudOperationContracts.values.where(
        (operation) =>
            operation.objectId == 'user.persona' && operation.kind == 'command',
      );
      expect(
        personaCommands.where((operation) => operation.method == 'DELETE'),
        isEmpty,
      );
      final retireOperation =
          appCloudOperationContracts[AppCloudOperationIds
              .userPersonaRetirePersona];
      expect(retireOperation, isNotNull);
      expect(
        retireOperation!.pathTemplate,
        UserApiMetadata.retirePersonaPathTemplate,
      );
    });

    test(
      'applyPersonaProfileSync → POST /user/persona/personas/{id}/profile-sync',
      () async {
        final result = await personaWriter.applyPersonaProfileSync(
          ApplyPersonaProfileSyncCommand(
            personaId: 'persona_1',
            applyScope: 'selected',
            fieldsMask: const <String>['phone', 'email'],
          ),
        );
        expect(result.appliedCount, 1);
        expect(log.last.method, 'POST');
        expect(
          log.last.path,
          UserApiMetadata.applyPersonaProfileSyncPath(personaId: 'persona_1'),
        );
      },
    );

    test(
      'getPersonaLifecycleGuard → GET /user/persona/personas/{id}/lifecycle-guard',
      () async {
        await repo.getPersonaLifecycleGuard('persona_1');
        expect(log.last.method, 'GET');
        expect(
          log.last.path,
          UserApiMetadata.getPersonaLifecycleGuardPath(personaId: 'persona_1'),
        );
      },
    );

    test('retirePersona → POST /user/persona/personas/{id}/retire', () async {
      final result = await personaWriter.retirePersona(
        RetirePersonaCommand(personaId: 'persona_1'),
      );
      expect(result.requestedAction, PersonaLifecycleAction.retire);
      expect(result.allowed, isTrue);
      expect(result.reason, PersonaLifecycleGuardReason.allowed);
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        UserApiMetadata.retirePersonaPath(personaId: 'persona_1'),
      );
    });
  });

  group('UserSettingsQuery Remote — operations.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteUserSettingsQueryReader settingsQuery;

    setUp(() {
      log = [];
      settingsQuery = RemoteUserSettingsQueryReader(
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
        invocationContext: (clientPageId) {
          final surface =
              clientPageId == UserRequestPageIds.getNotificationSettings
              ? AppUiSurfaces.settingsNotifications
              : AppUiSurfaces.settingsPrivacy;
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
    });

    test(
      'getNotificationSettings → GET /user/settings/notifications',
      () async {
        await settingsQuery.getNotificationSettings();
        expect(log.last.method, 'GET');
        expect(log.last.path, UserApiMetadata.getNotificationSettingsPath);
        _expectSurfaceOperationHeaders(
          log.last.headers,
          clientPageId: UserRequestPageIds.getNotificationSettings,
          surfaceId: AppUiSurfaces.settingsNotifications.id,
          operationId:
              AppCloudOperationIds.userUserSettingsGetNotificationSettings,
        );
      },
    );

    test('getPrivacySettings → GET /user/settings/privacy', () async {
      await settingsQuery.getPrivacySettings();
      expect(log.last.method, 'GET');
      expect(log.last.path, UserApiMetadata.getPrivacySettingsPath);
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: UserRequestPageIds.getPrivacySettings,
        surfaceId: AppUiSurfaces.settingsPrivacy.id,
        operationId: AppCloudOperationIds.userUserSettingsGetPrivacySettings,
      );
    });
  });

  group('ProfileQuery Remote — operations.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late RemoteProfileQuery query;

    setUp(() {
      log = [];
      final httpClient = CloudHttpClient(
        client: _captureClient(log),
        authTokenProvider: const _TestAuthTokenProvider(),
      );
      final userProfileQuery = RemoteUserProfileQueryFacet(
        client: buildGeneratedCloudOperationClient(
          httpClient: httpClient,
          clientContextProvider: const _TestCloudClientContext(),
          telemetrySink: RecordingCloudOperationTelemetrySink(),
          environment: CloudRuntimeEnvironment(
            environment: CloudEnvironment.gamma,
            gatewayBaseUri: Uri.parse(_baseUrl),
          ),
        ),
        invocationContext: (clientPageId, _) {
          final surface = clientPageId == UserRequestPageIds.getMeProfile
              ? AppUiSurfaces.profileHome
              : AppUiSurfaces.userProfile;
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
      query = RemoteProfileQuery(
        publicProfileQuery: userProfileQuery,
        userHomepageQuery: userProfileQuery,
      );
    });

    test('getUserProfile → GET generated persona profile path', () async {
      final profile = await query.getUserProfile('u1');

      expect(profile.personaId, 'u1');
      expect(log.last.method, 'GET');
      expect(
        log.last.path,
        UserApiMetadata.getPersonaProfilePath(personaId: 'u1'),
      );
      _expectSurfaceOperationHeaders(
        log.last.headers,
        clientPageId: UserRequestPageIds.getPersonaProfile,
        surfaceId: AppUiSurfaces.userProfile.id,
        operationId: AppCloudOperationIds.userUserAccountGetPersonaProfile,
      );
    });
  });

  group('HomepageFacetSet Remote — operations.yaml 路径对齐', () {
    late List<_CapturedRequest> log;
    late HomepageFacetProjectionAdapter repo;

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
        operationId:
            AppCloudOperationIds.entityHomepageSearchItemViewSearchHomepages,
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
          surfaceId: AppUiSurfaces.createWorkspace.id,
          routeId: AppUiSurfaces.createWorkspace.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
      );
    });

    test(
      'getNearbyLocations → GET /integration/external_integration/location/nearby',
      () async {
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
          surfaceId: AppUiSurfaces.createWorkspace.id,
          operationId:
              AppCloudOperationIds.integrationLocationGetNearbyLocations,
        );
      },
    );

    test(
      'searchLocations → GET /integration/external_integration/location/search',
      () async {
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
          surfaceId: AppUiSurfaces.createWorkspace.id,
          operationId: AppCloudOperationIds.integrationLocationSearchLocations,
        );
      },
    );
  });
}
