/// Identifies the host surface that launched media capture.
enum CameraPhotoCaller { picker, create }

/// Identifies the user entry point for capture telemetry and return behavior.
enum CameraPhotoEntrySource { photoPicker, publishEntry }

extension CameraPhotoEntrySourceX on CameraPhotoEntrySource {
  String get telemetryValue {
    return switch (this) {
      CameraPhotoEntrySource.photoPicker => 'photo_picker',
      CameraPhotoEntrySource.publishEntry => 'publish_entry',
    };
  }
}

extension CameraPhotoCallerX on CameraPhotoCaller {
  String get telemetryValue {
    return switch (this) {
      CameraPhotoCaller.picker => 'picker',
      CameraPhotoCaller.create => 'create',
    };
  }
}

enum CameraCaptureModePolicy { photoOnly, videoOnly, switchable }

class VideoEditorResult {
  const VideoEditorResult({
    required this.videoPath,
    required this.originalVideoPath,
    required this.thumbnailPath,
    required this.durationMs,
    required this.trimStartMs,
    required this.trimEndMs,
    required this.coverTimeMs,
    required this.coverStrategy,
    required this.width,
    required this.height,
    required this.muted,
  });

  final String videoPath;
  final String originalVideoPath;
  final String thumbnailPath;
  final int durationMs;
  final int trimStartMs;
  final int trimEndMs;
  final int coverTimeMs;
  final String coverStrategy;
  final int width;
  final int height;
  final bool muted;
}
