import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/content/post/post_publication_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RemoteContentPostPublicationWriter local contract', () {
    test('atomic publication uses one operation and stable intent key', () async {
      http.Request? captured;
      final writer = RemoteContentPostPublicationWriter(
        client: _client((request) {
          captured = request;
          return <String, Object?>{
            'publishIntentId': 'publish-draft-1',
            'localDraftId': 'draft-1',
            'postId': 'post-created',
            'state': 'published',
            'committedVersion': 1,
            'acceptedAt': '2026-07-13T10:00:00Z',
          };
        }),
        invocationContext: _context,
      );

      final result = await writer.submitPostPublication(
        SubmitContentPostPublicationCommand(
          publishIntentId: 'publish-draft-1',
          localDraftId: 'draft-1',
          contentType: ContentPostType.article,
          contentIdentity: ContentPostIdentity.work,
          title: '对象闭环',
          articleMarkdown: '# 对象闭环',
          mediaAssetIds: const <String>['asset-1'],
          visibility: ContentPostVisibility.public,
        ),
      );
      final request = captured;
      expect(request, isNotNull);

      expect(request!.method, 'POST');
      expect(request.url.path, '/content/posts:publish');
      expect(
        request.headers['X-Client-Operation-Id'],
        AppCloudOperationIds.contentPostSubmitPostPublication,
      );
      expect(request.headers['X-Client-Surface-Id'], 'createWorkspace');
      expect(request.headers['Idempotency-Key'], 'publish-draft-1');
      expect(request.headers['authorization'], 'Bearer post-command-token');
      final body = jsonDecode(request.body) as Map<String, dynamic>;
      expect(body['publishIntentId'], 'publish-draft-1');
      expect(body['localDraftId'], 'draft-1');
      expect(body['mediaAssetIds'], <Object?>['asset-1']);
      expect(body, isNot(contains('circleIds')));
      expect(result.postId, 'post-created');
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

CloudOperationInvocationContext _context(
  String clientPageId,
  String idempotencyKey,
) {
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.createWorkspace.id,
    routeId: AppUiSurfaces.createWorkspace.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
    idempotencyKey: idempotencyKey,
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
