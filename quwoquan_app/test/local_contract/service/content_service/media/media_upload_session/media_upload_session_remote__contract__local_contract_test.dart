// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001
// readiness_case: media_upload_session_init_media_upload_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/media_upload_session_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('MediaUploadSession adapter owns the typed init operation', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'sessionId': 'mus-1',
        'status': 'pending',
        'uploadUrl': 'https://upload.example.test/mus-1',
        'expiresAt': '2030-01-02T03:19:05Z',
        'replayed': false,
      },
    );
    final adapter = RemoteContentMediaUploadSessionAdapter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: _context,
    );

    final result = await adapter.initUpload(
      InitContentMediaUploadCommand(
        mediaType: MediaType.image,
        mimeType: 'image/jpeg',
        fileSize: 256,
        expectedSha256:
            'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      ),
      const ContentMediaUploadCommandContext(idempotencyKey: 'media-init-1'),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.contentMediaUploadSessionInitMediaUpload,
    );
    expect(executor.operation?.commercialStatus, 'ready');
    expect(executor.context?.idempotencyKey, 'media-init-1');
    expect(executor.body, <String, Object?>{
      'mediaType': 'image',
      'mimeType': 'image/jpeg',
      'fileSize': 256,
      'expectedSha256':
          'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    });
    expect(result.sessionId, 'mus-1');
    expect(result.uploadUrl?.host, 'upload.example.test');
  });

  test('completed session decoder preserves recovery asset identity', () {
    final session = decodeMediaUploadSessionSlice(<String, Object?>{
      'sessionId': 'mus-1',
      'version': 2,
      'assetId': 'mas-1',
      'mediaType': 'video',
      'mimeType': 'video/mp4',
      'fileSize': 256,
      'status': 'completed',
      'createdAt': '2030-01-02T03:04:05Z',
      'updatedAt': '2030-01-02T03:05:05Z',
      'expiresAt': '2030-01-02T03:19:05Z',
    });

    expect(session.sessionId, 'mus-1');
    expect(session.status, MediaUploadSessionStatus.completed);
    expect(session.assetId, 'mas-1');
  });
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  required bool command,
}) => CloudOperationInvocationContext(
  surfaceId: 'createWorkspace',
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(personaId: 'persona-1'),
  idempotencyKey: command ? 'composition-key' : null,
);

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
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
    body = payload.body;
    return responseDecoder(response);
  }
}
