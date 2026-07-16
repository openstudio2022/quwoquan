import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reader_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RemoteContentPostReaderAdapter local contract', () {
    test('GetPost 经 generated client 使用 workBrowser surface', () async {
      late http.Request captured;
      final adapter = RemoteContentPostReaderAdapter(
        client: _client((request) {
          captured = request;
          return <String, Object?>{
            'postId': 'post-1',
            'contentType': 'article',
            'title': '正文标题',
            'body': '正文',
            'articleMarkdown': '# 正文标题',
          };
        }),
        invocationContext: _contextFor(AppUiSurfaces.workBrowser),
      );

      final result = await adapter.getPost(postId: 'post-1');

      expect(captured.method, 'GET');
      expect(captured.url.path, '/v1/content/posts/post-1');
      expect(captured.headers['X-Client-Page-Id'], 'content.post.get');
      expect(
        captured.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.contentPostGetPost,
      );
      expect(
        captured.headers['X-Client-Surface-Id'],
        AppUiSurfaces.workBrowser.id,
      );
      expect(result.post.id, 'post-1');
      expect(result.detailWire.articleMarkdown, '# 正文标题');
    });

    test('ListUserPosts 经 generated client 使用 userProfile surface', () async {
      late http.Request captured;
      final adapter = RemoteContentPostReaderAdapter(
        client: _client((request) {
          captured = request;
          return <String, Object?>{
            'items': <Object?>[
              <String, Object?>{
                'postId': 'post-1',
                'contentType': 'image',
                'authorId': 'author-1',
                'imageUrls': <String>['https://example.test/p.jpg'],
              },
            ],
            'nextCursor': 'cursor-2',
          };
        }),
        invocationContext: _contextFor(AppUiSurfaces.userProfile),
      );

      final result = await adapter.listUserPosts(
        userId: 'author-1',
        identity: 'work',
        type: 'image',
        visibility: 'public',
        cursor: 'cursor-1',
        limit: 10,
      );

      expect(captured.method, 'GET');
      expect(captured.url.path, '/v1/content/sub-accounts/author-1/posts');
      expect(captured.url.queryParameters, <String, String>{
        'identity': 'work',
        'type': 'image',
        'visibility': 'public',
        'cursor': 'cursor-1',
        'limit': '10',
      });
      expect(captured.headers['X-Client-Page-Id'], 'content.user.posts');
      expect(
        captured.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.contentPostListUserPosts,
      );
      expect(
        captured.headers['X-Client-Surface-Id'],
        AppUiSurfaces.userProfile.id,
      );
      expect(result.items.single.id, 'post-1');
      expect(result.nextCursor, 'cursor-2');
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
    ),
    clientContextProvider: const _TestCloudClientContext(),
    telemetrySink: const _NoopTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse('https://test-gateway.example.com'),
    ),
  );
}

ContentPostReaderInvocationContextFactory _contextFor(AppUiSurface surface) {
  return (clientPageId) => CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(),
  );
}

final class _TestCloudClientContext implements CloudClientContextProvider {
  const _TestCloudClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'post-reader-contract-session',
      deviceActorId: 'post-reader-contract-device',
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
