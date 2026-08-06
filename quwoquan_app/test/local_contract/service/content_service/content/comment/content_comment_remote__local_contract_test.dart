import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/service/content_service/content/comment/adapters/comment_facets_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'RemoteContentCommentFacet 只经 generated executor 返回 typed page',
    () async {
      late http.Request captured;
      final adapter = RemoteContentCommentFacet(
        client: _client((request) {
          captured = request;
          return <String, Object?>{
            'items': <Object?>[],
            'nextCursor': null,
            'total': 0,
          };
        }),
        invocationContext: _context,
      );

      final page = await adapter.listComments(postId: 'post-1');

      expect(captured.method, 'GET');
      expect(captured.url.path, '/content/posts/post-1/comments');
      expect(
        captured.url.queryParameters['limit'],
        '${ListContentCommentsQuery.defaultLimit}',
      );
      expect(
        captured.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.contentCommentListComments,
      );
      expect(
        captured.headers['authorization'],
        'Bearer comment-contract-token',
      );
      expect(page.items, isEmpty);
      expect(page.total, 0);
      expect(page.nextCursor, isNull);
    },
  );
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
      authTokenProvider: const _CommentTokenProvider(),
    ),
    clientContextProvider: const _CommentClientContext(),
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
    surfaceId: 'workBrowser',
    routeId: 'workBrowser',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
    idempotencyKey: command ? 'comment-command-contract' : null,
  );
}

final class _CommentClientContext implements CloudClientContextProvider {
  const _CommentClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'comment-contract-session',
      deviceActorId: 'comment-contract-device',
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

final class _CommentTokenProvider implements CloudAuthTokenProvider {
  const _CommentTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'comment-contract-token';
}
