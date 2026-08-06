import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Resolves a server-grounded MediaAssetRef through the owning Content query.
/// Presentation never consumes a URL supplied by a model or template.
final class AssistantPresentationMediaResolver {
  const AssistantPresentationMediaResolver({
    required this.media,
    required this.delivery,
  });

  final ContentMediaFacet media;
  final MediaDeliveryResolver delivery;

  Future<Uri> resolve({required String mediaAssetId}) async {
    final normalizedAssetId = mediaAssetId.trim();
    if (normalizedAssetId.isEmpty) {
      throw ArgumentError.value(
        mediaAssetId,
        'mediaAssetId',
        'must not be blank',
      );
    }
    final asset = await media.getMediaAsset(
      GetContentMediaAssetQuery(mediaId: normalizedAssetId),
    );
    if (asset.assetId != normalizedAssetId ||
        asset.status != MediaAssetStatus.ready ||
        asset.accessPolicy != MediaAssetAccessPolicy.public ||
        asset.mediaType != MediaType.image) {
      throw StateError('Assistant presentation media is not publicly ready');
    }
    return delivery
        .resolve(
          asset.cdnUrl.toString(),
          kind: MediaDeliveryKind.image,
          assetId: asset.assetId,
          version: asset.version,
        )
        .deliveryUri;
  }
}
