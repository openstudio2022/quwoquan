// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003
// readiness_case: media_original_access_fact_request_original_image_access_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_original_access_fact/adapters/media_original_access_fact_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'MediaOriginalAccessFact adapter owns the typed fact operation',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'mediaId': 'mas-1',
          'status': 'granted',
          'originalUrl': 'https://cdn.example.test/media/mas-1?t=1',
          'format': 'image/jpeg',
          'sizeBytes': 256,
          'expiresAt': '2030-01-02T03:09:05Z',
          'ttlSeconds': 300,
          'auditId': 'moa-1',
        },
      );
      final adapter = RemoteContentMediaOriginalAccessFactWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final result = await adapter.requestOriginalAccess(
        RequestContentMediaOriginalAccessCommand(
          mediaId: 'mas-1',
          purpose: MediaOriginalAccessPurpose.save,
        ),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds
            .contentMediaOriginalAccessFactRequestOriginalImageAccess,
      );
      expect(executor.context?.idempotencyKey, 'media-original-1');
      expect(executor.pathParameters, <String, String>{'mediaId': 'mas-1'});
      expect(executor.body, <String, Object?>{'purpose': 'save'});
      expect(result.auditId, 'moa-1');
      expect(result.originalUrl.host, 'cdn.example.test');
    },
  );
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: 'workBrowser',
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(personaId: 'persona-1'),
  idempotencyKey: command ? 'media-original-1' : null,
);

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    final payload = requestEncoder();
    this.operation = operation;
    this.context = context;
    pathParameters = payload.pathParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}
