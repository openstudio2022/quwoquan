/// A media entry rendered by the legacy video viewer surface.
final class MediaItem {
  const MediaItem({
    required this.type,
    required this.url,
    this.thumbnailUrl,
    this.aspectRatio,
  });

  final String type;
  final String url;
  final String? thumbnailUrl;
  final double? aspectRatio;
}
