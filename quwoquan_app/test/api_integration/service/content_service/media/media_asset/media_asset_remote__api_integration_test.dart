// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-001
// readiness_case: media_asset_get_media_asset_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/content_api_contract_harness.dart';

void main() {
  late ContentApiContractHarness harness;

  setUpAll(() async => harness = await ContentApiContractHarness.create());
  tearDownAll(() => harness.close());

  test('release-bound image feed 可由 production GetMediaAsset 完整回读', () async {
    final feed = await harness.feed.listDiscoveryFeedPage(
      category: 'photo',
      type: 'image',
      limit: 20,
    );
    final item = feed.items.firstWhere(
      (candidate) => (candidate.mediaAssetId?.trim() ?? '').isNotEmpty,
      orElse: () => throw StateError(
        'CONTENT_EXPERIENCE_BLOCK: image feed has no canonical mediaAssetId',
      ),
    );
    final mediaId = item.mediaAssetId!.trim();
    final asset = await harness.mediaAssets.getMediaAsset(
      GetContentMediaAssetQuery(mediaId: mediaId),
    );

    expect(asset.assetId, mediaId);
    expect(asset.mediaType, MediaType.image);
    expect(asset.status, MediaAssetStatus.ready);
    expect(asset.version, greaterThan(0));
    expect(asset.fileSize, greaterThan(0));
    expect(asset.mimeType, startsWith('image/'));
    expect(asset.cdnUrl.scheme, 'https');
    final telemetry = await harness.telemetry.waitForEvents(minimumCount: 1);
    expect(
      telemetry.any(
        (event) =>
            event.succeeded && event.canonicalOperationId == 'GetMediaAsset',
      ),
      isTrue,
    );
  });
}
