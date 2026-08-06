// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-001
// readiness_case: media_asset_discard_media_asset_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/media_asset_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'MediaAsset adapter owns the typed DELETE operation and deleted-only result',
    () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'mediaId': 'mas-1',
          'status': 'deleted',
          'replayed': false,
        },
      );
      final adapter = RemoteContentMediaAssetAdapter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _context,
      );

      final result = await adapter.discardMediaAsset(
        DiscardContentMediaAssetCommand(mediaId: 'mas-1'),
        const ContentMediaAssetCommandContext(
          idempotencyKey: 'media-discard-1',
        ),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.contentMediaAssetDiscardMediaAsset,
      );
      expect(executor.operation?.method, 'DELETE');
      expect(executor.context?.idempotencyKey, 'media-discard-1');
      expect(executor.pathParameters, <String, String>{'mediaId': 'mas-1'});
      expect(executor.body, isNull);
      expect(result.status, MediaAssetDiscardStatus.deleted);
      expect(
        () => decodeMediaAssetDiscardResult(<String, Object?>{
          'mediaId': 'mas-1',
          'status': 'ready',
          'replayed': false,
        }),
        throwsFormatException,
      );
    },
  );

  test('media decoder rejects a malformed relative delivery URL', () {
    expect(
      () => decodeMediaAssetSlice(<String, Object?>{
        'assetId': 'mas-1',
        'version': 1,
        'mediaType': 'image',
        'mimeType': 'image/jpeg',
        'fileSize': 256,
        'status': 'ready',
        'accessPolicy': 'owner_only',
        'cdnUrl': '/relative/path',
      }),
      throwsFormatException,
    );
  });

  test('ready image slice preserves processor-owned delivery descriptor', () {
    final media = decodeMediaAssetSlice(<String, Object?>{
      'assetId': 'mas-1',
      'version': 2,
      'mediaType': 'image',
      'mimeType': 'image/jpeg',
      'fileSize': 256,
      'status': 'ready',
      'accessPolicy': 'public',
      'cdnUrl': 'https://cdn.example.test/media/mas-1',
      'imageWidth': 960,
      'imageHeight': 640,
      'imageDeliveryMimeType': 'image/jpeg',
      'imageDominantColor': '#1A2B3C',
      'imageLqip': 'data:image/jpeg;base64,/9j/2Q==',
      'imageContentProfile': 'photographic',
      'imageDerivativePolicyVersion': 1,
    });

    expect(media.imageWidth, 960);
    expect(media.imageHeight, 640);
    expect(media.imageDominantColor, '#1A2B3C');
    expect(media.imageLqip, 'data:image/jpeg;base64,/9j/2Q==');
    expect(media.imageContentProfile, 'photographic');
    expect(media.imageDerivativePolicyVersion, 1);
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
