import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_asset_manifest_resolver.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';

/// Runtime-configured media reference adapter for the pure manifest resolver.
final class AssetUrlResolver extends MediaAssetManifestResolver {
  const AssetUrlResolver({
    super.gatewayBaseUrl,
    super.imageCdnBaseUrl,
    super.videoCdnBaseUrl,
  }) : super(resolveReference: _resolveMediaAssetReference);
}

String _resolveMediaAssetReference(
  String raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) => resolveContentMediaUrl(
  raw,
  gatewayBaseUrl: gatewayBaseUrl,
  imageCdnBaseUrl: imageCdnBaseUrl,
  videoCdnBaseUrl: videoCdnBaseUrl,
);
