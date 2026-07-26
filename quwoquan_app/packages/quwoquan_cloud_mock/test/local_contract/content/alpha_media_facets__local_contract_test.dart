import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  const initContext = ContentMediaUploadCommandContext(
    idempotencyKey: 'alpha-media-init-1',
  );
  const completeContext = ContentMediaUploadCommandContext(
    idempotencyKey: 'alpha-media-complete-1',
  );

  InitContentMediaUploadCommand command() => InitContentMediaUploadCommand(
    mediaType: ContentMediaType.image,
    contentType: 'image/jpeg',
    fileSize: 3,
    expectedSha256:
        'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  );

  test('Init and Complete replay one session and processing asset', () async {
    final facet = AlphaContentMediaFacet(
      completedAssetStatus: ContentMediaProcessingStatus.processing,
    );

    final initialized = await facet.initUpload(command(), initContext);
    final replayedInit = await facet.initUpload(command(), initContext);
    expect(replayedInit.sessionId, initialized.sessionId);
    expect(replayedInit.replayed, isTrue);

    final completed = await facet.completeUpload(
      CompleteContentMediaUploadCommand(sessionId: initialized.sessionId),
      completeContext,
    );
    final replayedComplete = await facet.completeUpload(
      CompleteContentMediaUploadCommand(sessionId: initialized.sessionId),
      completeContext,
    );

    expect(
      completed.assetProcessingStatus,
      ContentMediaProcessingStatus.processing,
    );
    expect(replayedComplete.assetId, completed.assetId);
    expect(
      replayedComplete.assetProcessingStatus,
      completed.assetProcessingStatus,
    );
    expect(replayedComplete.replayed, isTrue);

    final asset = await facet.getMediaAsset(
      GetContentMediaAssetQuery(mediaId: completed.assetId!),
    );
    expect(asset.status, ContentMediaProcessingStatus.processing);
  });
}
