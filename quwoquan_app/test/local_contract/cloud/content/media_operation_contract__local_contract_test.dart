import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('blocked media operation still has typed generated ABI', () async {
    final executor = _MediaRecordingExecutor(
      response: <String, Object?>{
        'sessionId': 'mus-1',
        'status': 'pending',
        'objectKey': 'uploads/mus-1.jpg',
        'uploadUrl': 'https://upload.example.test/mus-1',
        'expiresAt': '2030-01-02T03:19:05Z',
        'replayed': false,
      },
    );
    final client = GeneratedCloudOperationClient(executor);

    final result = await client.contentMediaUploadSessionInitMediaUpload(
      InitContentMediaUploadCommand(
        mediaType: ContentMediaType.image,
        contentType: 'image/jpeg',
        fileSize: 256,
        expectedSha256:
            'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      ),
      context: _context(
        surfaceId: 'createWorkspace',
        idempotencyKey: 'media-init-1',
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.contentMediaUploadSessionInitMediaUpload,
    );
    expect(executor.body, <String, Object?>{
      'mediaType': 'image',
      'contentType': 'image/jpeg',
      'fileSize': 256,
      'expectedSha256':
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    });
    expect(result.sessionId, 'mus-1');
    expect(result.uploadUrl?.host, 'upload.example.test');
  });

  test('original access uses typed fact operation and strict result', () async {
    final executor = _MediaRecordingExecutor(
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
    final client = GeneratedCloudOperationClient(executor);

    final result = await client
        .contentMediaOriginalAccessFactRequestOriginalImageAccess(
          RequestContentMediaOriginalAccessCommand(
            mediaId: 'mas-1',
            purpose: ContentMediaOriginalAccessPurpose.save,
          ),
          context: _context(
            surfaceId: 'workBrowser',
            idempotencyKey: 'media-original-1',
          ),
        );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds
          .contentMediaOriginalAccessFactRequestOriginalImageAccess,
    );
    expect(executor.pathParameters, <String, String>{'mediaId': 'mas-1'});
    expect(executor.body, <String, Object?>{'purpose': 'save'});
    expect(result.auditId, 'moa-1');
    expect(result.originalUrl.host, 'cdn.example.test');
  });

  test('media decoder rejects dynamic or malformed business response', () {
    expect(
      () => decodeContentMediaAssetSlice(<String, Object?>{
        'assetId': 'mas-1',
        'version': 1,
        'mediaType': 'image',
        'contentType': 'image/jpeg',
        'fileSize': 256,
        'status': 'ready',
        'accessPolicy': 'owner_only',
        'cdnUrl': '/relative/path',
      }),
      throwsFormatException,
    );
  });

  test(
    'post media binding deduplicates typed asset ids before transport',
    () async {
      final executor = _MediaRecordingExecutor(
        response: <String, Object?>{
          'postId': 'post-1',
          'boundAssetIds': <String>['mas-1'],
          'boundCount': 1,
        },
      );
      final client = GeneratedCloudOperationClient(executor);

      final result = await client.contentPostBindMediaAssetsToPost(
        BindContentPostMediaAssetsCommand(
          postId: 'post-1',
          assetIds: const <String>['mas-1', 'mas-1'],
        ),
        context: _context(
          surfaceId: 'createWorkspace',
          idempotencyKey: 'media-bind-1',
        ),
      );

      expect(executor.pathParameters, <String, String>{'postId': 'post-1'});
      expect(executor.body, <String, Object?>{
        'assetIds': <String>['mas-1'],
      });
      expect(result.boundCount, 1);
    },
  );
}

CloudOperationInvocationContext _context({
  required String surfaceId,
  required String idempotencyKey,
}) => CloudOperationInvocationContext(
  surfaceId: surfaceId,
  clientPageId: 'content.media.contract',
  actor: const CloudOperationActorContext(personaId: 'persona-1'),
  idempotencyKey: idempotencyKey,
);

final class _MediaRecordingExecutor implements CloudOperationExecutor {
  _MediaRecordingExecutor({this.response});

  final Object? response;
  CloudOperationContract? operation;
  Map<String, String> pathParameters = const <String, String>{};
  Map<String, String> queryParameters = const <String, String>{};
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
    pathParameters = payload.pathParameters;
    queryParameters = payload.queryParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}
