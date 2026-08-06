/// Public typed seam for resolving immutable media asset manifests at App
/// presentation boundaries. Concrete CDN/runtime configuration stays in the
/// media-asset adapter installed by composition.
abstract interface class MediaAssetUrlResolver {
  Map<String, String> resolveManifestUrls(Map<String, Object?>? manifest);

  String resolveAssetRowUrl(Map<String, Object?> row);
}
