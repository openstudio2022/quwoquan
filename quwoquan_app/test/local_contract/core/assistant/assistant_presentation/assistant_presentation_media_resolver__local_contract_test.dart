// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/assistant/presentation/assistant_presentation_media_resolver.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../support/recording_content_media_facet.dart';

void main() {
  test('resolves only a publicly ready canonical image asset', () async {
    final media = RecordingContentMediaFacet(
      completedAssetAccessPolicy: MediaAssetAccessPolicy.public,
    );
    final assetId = await _completeImage(media);
    final resolver = AssistantPresentationMediaResolver(
      media: media,
      delivery: MediaDeliveryResolver(
        MediaEndpointConfig(
          avatarBaseUrl: 'https://cdn.quwoquan.test/',
          imageBaseUrl: 'https://cdn.quwoquan.test/',
          videoBaseUrl: 'https://video.quwoquan.test/',
          attachmentBaseUrl: 'https://cdn.quwoquan.test/',
        ),
      ),
    );

    final uri = await resolver.resolve(mediaAssetId: assetId);

    expect(uri.scheme, 'https');
    expect(uri.host, 'cdn.quwoquan.test');
    expect(uri.path, '/media/image/s/asset/$assetId/v1/source.jpg');
  });

  test('rejects an owner-only asset instead of exposing its URL', () async {
    final media = RecordingContentMediaFacet();
    final assetId = await _completeImage(media);
    final resolver = AssistantPresentationMediaResolver(
      media: media,
      delivery: MediaDeliveryResolver(
        MediaEndpointConfig(
          avatarBaseUrl: 'https://cdn.quwoquan.test/',
          imageBaseUrl: 'https://cdn.quwoquan.test/',
          videoBaseUrl: 'https://video.quwoquan.test/',
          attachmentBaseUrl: 'https://cdn.quwoquan.test/',
        ),
      ),
    );

    await expectLater(
      resolver.resolve(mediaAssetId: assetId),
      throwsA(isA<StateError>()),
    );
  });
}

Future<String> _completeImage(RecordingContentMediaFacet media) async {
  final init = await media.initUpload(
    InitContentMediaUploadCommand(
      mediaType: MediaType.image,
      mimeType: 'image/jpeg',
      fileSize: 4,
      expectedSha256:
          'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    ),
    const ContentMediaUploadCommandContext(idempotencyKey: 'init-image'),
  );
  final completed = await media.completeUpload(
    CompleteContentMediaUploadCommand(
      sessionId: init.sessionId,
      accessPolicy: MediaAssetAccessPolicy.public,
    ),
    const ContentMediaUploadCommandContext(idempotencyKey: 'complete-image'),
  );
  return completed.assetId!;
}
