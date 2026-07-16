import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/content/post/post_lifecycle_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RemoteContentPostLifecycleCommandWriter local contract', () {
    test('CreatePost only uses generated operation executor', () async {
      http.Request? captured;
      final writer = RemoteContentPostLifecycleCommandWriter(
        client: _client((request) {
          captured = request;
          return <String, Object?>{
            'postId': 'post-created',
            'contentType': 'article',
            'contentIdentity': 'work',
            'title': '对象闭环',
          };
        }),
        invocationContext: _context,
      );

      final result = await writer.createPost(
        CreateContentPostCommand(
          contentType: ContentPostType.article,
          contentIdentity: ContentPostIdentity.work,
          title: '对象闭环',
          articleMarkdown: '# 对象闭环',
          articleAssetManifest:
              ContentPostStructuredObject(<String, ContentPostStructuredValue>{
                'schemaVersion': const ContentPostStructuredNumber(1),
                'assets': ContentPostStructuredArray(
                  const <ContentPostStructuredValue>[],
                ),
              }),
        ),
      );
      final request = captured;
      expect(request, isNotNull);

      expect(request!.method, 'POST');
      expect(request.url.path, '/v1/content/posts');
      expect(
        request.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.contentPostCreatePost,
      );
      expect(request.headers['X-Client-Surface-Id'], 'createWorkspace');
      expect(request.headers['Idempotency-Key'], 'post-command-contract');
      expect(request.headers['authorization'], 'Bearer post-command-token');
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body['contentType'], 'article');
      expect(body, isNot(contains('circleIds')));
      expect(body['articleAssetManifest'], <String, Object?>{
        'schemaVersion': 1,
        'assets': <Object?>[],
      });
      expect(result.post.postId, 'post-created');
    });

    test(
      'PublishPost uses typed body and never accepts circle placement',
      () async {
        http.Request? captured;
        final writer = RemoteContentPostLifecycleCommandWriter(
          client: _client((request) {
            captured = request;
            return <String, Object?>{
              'postId': 'post-created',
              'contentType': 'article',
              'contentIdentity': 'work',
              'publishedAt': '2026-07-13T10:00:00Z',
            };
          }),
          invocationContext: _context,
        );

        final result = await writer.publishPost(
          PublishContentPostCommand(
            postId: 'post-created',
            visibility: ContentPostVisibility.public,
            assistantUsePolicy: ContentPostAssistantUsePolicy.inherit,
          ),
        );
        final request = captured;
        expect(request, isNotNull);

        expect(request!.method, 'POST');
        expect(request.url.path, '/v1/content/posts/post-created/publish');
        expect(
          request.headers['X-Client-Operation-Id'],
          AppCloudOperationIds.contentPostPublishPost,
        );
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body, <String, Object?>{
          'visibility': 'public',
          'assistantUsePolicy': 'inherit',
        });
        expect(result.post.postId, 'post-created');
        expect(result.post.publishedAt, DateTime.utc(2026, 7, 13, 10));
      },
    );
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
      authTokenProvider: const _PostCommandTokenProvider(),
    ),
    clientContextProvider: const _TestCloudClientContext(),
    telemetrySink: const _NoopTelemetrySink(),
    environment: CloudRuntimeEnvironment(
      environment: CloudEnvironment.gamma,
      gatewayBaseUri: Uri.parse('https://test-gateway.example.com'),
    ),
  );
}

CloudOperationInvocationContext _context(String clientPageId) {
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.createWorkspace.id,
    routeId: AppUiSurfaces.createWorkspace.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
    idempotencyKey: 'post-command-contract',
  );
}

final class _TestCloudClientContext implements CloudClientContextProvider {
  const _TestCloudClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'post-command-contract-session',
      deviceActorId: 'post-command-contract-device',
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

final class _PostCommandTokenProvider implements CloudAuthTokenProvider {
  const _PostCommandTokenProvider();

  @override
  Future<String?> getAccessToken() async => 'post-command-token';
}
