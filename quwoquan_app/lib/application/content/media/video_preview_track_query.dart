import 'package:flutter/foundation.dart';

import 'package:quwoquan_app/core/media/media_delivery_reference.dart';

@immutable
final class VideoPreviewTrackDescriptor {
  const VideoPreviewTrackDescriptor({
    required this.assetId,
    required this.assetVersion,
    required this.trackVersion,
    required this.manifestReference,
  });

  final String assetId;
  final int assetVersion;
  final int trackVersion;
  final MediaDeliveryReference manifestReference;
}

@immutable
final class VideoPreviewTrackSprite {
  const VideoPreviewTrackSprite({
    required this.spriteId,
    required this.reference,
    required this.sha256,
    required this.width,
    required this.height,
  });

  final String spriteId;
  final MediaDeliveryReference reference;
  final String sha256;
  final int width;
  final int height;
}

@immutable
final class VideoPreviewTrackFrame {
  const VideoPreviewTrackFrame({
    required this.timeMs,
    required this.sprite,
    required this.x,
    required this.y,
    required this.width,
    required this.height,
  });

  final int timeMs;
  final VideoPreviewTrackSprite sprite;
  final int x;
  final int y;
  final int width;
  final int height;
}

@immutable
final class VideoPreviewTrackManifest {
  VideoPreviewTrackManifest({
    required this.assetId,
    required this.assetVersion,
    required this.trackVersion,
    required this.processorProfile,
    required this.accessPolicy,
    required this.frameIntervalMs,
    required List<VideoPreviewTrackSprite> sprites,
    required List<VideoPreviewTrackFrame> frames,
  }) : sprites = List<VideoPreviewTrackSprite>.unmodifiable(sprites),
       frames = List<VideoPreviewTrackFrame>.unmodifiable(frames);

  final String assetId;
  final int assetVersion;
  final int trackVersion;
  final String processorProfile;
  final String accessPolicy;
  final int frameIntervalMs;
  final List<VideoPreviewTrackSprite> sprites;
  final List<VideoPreviewTrackFrame> frames;

  VideoPreviewTrackFrame frameFor(Duration target) {
    final targetMs = target.inMilliseconds.clamp(0, 3600000);
    var selected = frames.first;
    for (final frame in frames) {
      if (frame.timeMs > targetMs) {
        break;
      }
      selected = frame;
    }
    return selected;
  }
}

abstract interface class VideoPreviewTrackQuery {
  Future<VideoPreviewTrackManifest> loadManifest(
    VideoPreviewTrackDescriptor descriptor,
  );
}
