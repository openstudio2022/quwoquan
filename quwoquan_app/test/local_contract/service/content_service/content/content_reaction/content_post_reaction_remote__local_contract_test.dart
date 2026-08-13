// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-006
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/comment-thread/spec.md#gwt-006.t2
// readiness_case: content_reaction_get_content_reaction_state_app_local
// readiness_case: content_reaction_like_post_app_local
// readiness_case: content_reaction_unlike_post_app_local
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_reaction/adapters/post_reaction_facets_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RemoteContentPostReactionFacet local contract', () {
    test('LikePost 只经 generated executor 发送 typed command', () async {
      final captured = <http.Request>[];
      var callCount = 0;
      final adapter = RemoteContentPostReactionFacet(
        client: _client((request) {
          captured.add(request);
          callCount += 1;
          return <String, Object?>{
            'reactionId': 'reaction-1',
            'postId': 'post-1',
            'version': 1,
            'liked': true,
            'changed': callCount == 1,
            'replayed': callCount > 1,
          };
        }),
        invocationContext: _context,
      );

      final result = await adapter.likePost(
        LikeContentPostCommand(postId: 'post-1'),
      );
      final replay = await adapter.likePost(
        LikeContentPostCommand(postId: 'post-1'),
      );

      expect(result.postId, 'post-1');
      expect(result.liked, isTrue);
      expect(result.changed, isTrue);
      expect(result.replayed, isFalse);
      expect(replay.reactionId, result.reactionId);
      expect(replay.version, result.version);
      expect(replay.changed, isFalse);
      expect(replay.replayed, isTrue);
      expect(captured, hasLength(2));
      for (final request in captured) {
        expect(request.method, 'POST');
        expect(request.url.path, '/content/posts/post-1/like');
        expect(request.body, isEmpty);
        expect(
          request.headers['X-Client-Page-Id'],
          ContentRequestPageIds.likePost,
        );
        expect(
          request.headers['X-Client-Operation-Id'],
          AppCloudOperationIds.contentContentReactionLikePost,
        );
        expect(request.headers['X-Client-Surface-Id'], 'homeFeed');
        expect(request.headers['Idempotency-Key'], 'post-reaction-command');
        expect(request.headers['authorization'], 'Bearer reaction-token');
      }
    });

    test('UnlikePost 使用 generated path 且严格解码结果', () async {
      final captured = <http.Request>[];
      var callCount = 0;
      final adapter = RemoteContentPostReactionFacet(
        client: _client((request) {
          captured.add(request);
          callCount += 1;
          return <String, Object?>{
            'reactionId': 'reaction-1',
            'postId': 'post-1',
            'version': 2,
            'liked': false,
            'changed': callCount == 1,
            'replayed': callCount > 1,
          };
        }),
        invocationContext: _context,
      );

      final result = await adapter.unlikePost(
        UnlikeContentPostCommand(postId: 'post-1'),
      );
      final replay = await adapter.unlikePost(
        UnlikeContentPostCommand(postId: 'post-1'),
      );

      expect(result.version, 2);
      expect(result.liked, isFalse);
      expect(result.changed, isTrue);
      expect(result.replayed, isFalse);
      expect(replay.reactionId, result.reactionId);
      expect(replay.version, result.version);
      expect(replay.changed, isFalse);
      expect(replay.replayed, isTrue);
      expect(captured, hasLength(2));
      for (final request in captured) {
        expect(request.method, 'DELETE');
        expect(request.url.path, '/content/posts/post-1/like');
        expect(request.body, isEmpty);
        expect(
          request.headers['X-Client-Page-Id'],
          ContentRequestPageIds.unlikePost,
        );
        expect(
          request.headers['X-Client-Operation-Id'],
          AppCloudOperationIds.contentContentReactionUnlikePost,
        );
        expect(request.headers['X-Client-Surface-Id'], 'homeFeed');
        expect(request.headers['Idempotency-Key'], 'post-reaction-command');
        expect(request.headers['authorization'], 'Bearer reaction-token');
      }
    });

    test('GetContentReactionState 使用 typed query 且不携带幂等键', () async {
      http.Request? captured;
      final adapter = RemoteContentPostReactionFacet(
        client: _client((request) {
          captured = request;
          return <String, Object?>{
            'found': true,
            'postId': 'post-1',
            'liked': true,
            'version': 3,
            'updatedAt': '2026-07-14T08:00:00Z',
          };
        }),
        invocationContext: _context,
      );

      final result = await adapter.getReactionState(
        GetContentPostReactionStateQuery(postId: 'post-1'),
      );
      final request = captured;
      expect(request, isNotNull);

      expect(request!.method, 'GET');
      expect(request.url.path, '/content/posts/post-1/reactions');
      expect(
        request.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.contentContentReactionGetContentReactionState,
      );
      expect(
        request.headers['X-Client-Page-Id'],
        ContentRequestPageIds.getContentReactionState,
      );
      expect(request.headers['X-Client-Surface-Id'], 'homeFeed');
      expect(request.headers['authorization'], 'Bearer reaction-token');
      expect(request.headers.containsKey('Idempotency-Key'), isFalse);
      expect(result.updatedAt, DateTime.utc(2026, 7, 14, 8));
      expect(result.liked, isTrue);
    });

    test('malformed reaction state fail-closed，不合成互动状态', () async {
      final adapter = RemoteContentPostReactionFacet(
        client: _client((_) {
          return <String, Object?>{
            'found': true,
            'postId': 'post-1',
            'liked': 'yes',
            'version': 3,
          };
        }),
        invocationContext: _context,
      );

      await expectLater(
        adapter.getReactionState(
          GetContentPostReactionStateQuery(postId: 'post-1'),
        ),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.type,
                'type',
                CloudErrorType.invalidResponse,
              )
              .having(
                (error) => error.code,
                'code',
                'APP.CONTRACT.invalid_json',
              )
              .having(
                (error) => error.sourceOperationId,
                'sourceOperationId',
                AppCloudOperationIds
                    .contentContentReactionGetContentReactionState,
              ),
        ),
      );
    });
  });
}

GeneratedCloudOperationClient _client(
  Map<String, Object?> Function(http.Request request) responseFor,
) {
  return buildGeneratedCloudOperationClient(
    httpClient: CloudHttpClient(
      client: MockClient((request) async {
        return http.Response(
          jsonEncode(responseFor(request)),
          200,
          headers: const <String, String>{'content-type': 'application/json'},
        );
      }),
      authTokenProvider: const _ReactionTokenProvider(),
    ),
    clientContextProvider: const _ReactionClientContext(),
    telemetrySink: const _NoopTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse('https://test-gateway.example.com'),
    ),
  );
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) {
  return CloudOperationInvocationContext(
    surfaceId: 'homeFeed',
    routeId: 'home',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
    idempotencyKey: command ? 'post-reaction-command' : null,
  );
}

final class _ReactionClientContext implements CloudClientContextProvider {
  const _ReactionClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'reaction-contract-session',
      deviceActorId: 'reaction-contract-device',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _NoopTelemetrySink implements CloudOperationTelemetrySink {
  const _NoopTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}

final class _ReactionTokenProvider implements CloudAuthTokenProvider {
  const _ReactionTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'reaction-token';
}
