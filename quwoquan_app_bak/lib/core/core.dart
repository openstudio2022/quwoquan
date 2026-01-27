// Core types and utilities

/// Media item model
class MediaItem {
  final String type; // 'image' or 'video'
  final String url;
  final String? thumbnailUrl;
  final double? aspectRatio;
  
  const MediaItem({
    required this.type,
    required this.url,
    this.thumbnailUrl,
    this.aspectRatio,
  });
}

