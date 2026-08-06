import 'dart:async';

import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/content_media_preparation_checkpoint.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentMediaStreamObjectUpload =
    Future<void> Function(
      Uri uploadUri,
      Stream<List<int>> bytes, {
      required int contentLength,
      required String mimeType,
      required String expectedSha256,
      Future<void>? abortTrigger,
    });

typedef ContentMediaUploadProgressCallback =
    void Function(int uploadedBytes, int totalBytes);

final class ContentMediaUploadCancellationSignal {
  final Completer<void> _cancelled = Completer<void>();

  bool get isCancelled => _cancelled.isCompleted;
  Future<void> get whenCancelled => _cancelled.future;

  void cancel() {
    if (!_cancelled.isCompleted) {
      _cancelled.complete();
    }
  }

  void throwIfCancelled() {
    if (isCancelled) {
      throw const ContentMediaUploadCancelledException();
    }
  }

  Future<void> waitOrCancel(Duration duration) async {
    throwIfCancelled();
    await Future.any<void>(<Future<void>>[
      Future<void>.delayed(duration),
      whenCancelled,
    ]);
    throwIfCancelled();
  }
}

final class ContentMediaUploadCancelledException implements Exception {
  const ContentMediaUploadCancelledException();
}

final class PreparedContentMediaSource {
  const PreparedContentMediaSource({
    required this.fileSize,
    required this.sha256Digest,
    required this.openRead,
  });

  final int fileSize;
  final String sha256Digest;
  final Stream<List<int>> Function() openRead;
}

abstract interface class ContentMediaSourceReader {
  Future<PreparedContentMediaSource> prepare(String localPath);
}

final class UploadedContentMedia {
  const UploadedContentMedia({
    required this.sessionId,
    required this.assetId,
    required this.assetProcessingStatus,
  });

  final String sessionId;
  final String assetId;
  final MediaAssetStatus? assetProcessingStatus;
}

abstract interface class ContentMediaUploadService {
  Future<PreparedContentMediaSource> prepareSource({
    required int fileSize,
    required Stream<List<int>> Function() openRead,
  });

  ContentMediaPreparationCheckpoint createPreparationCheckpoint({
    required String preparationIdentity,
    required String slot,
    required MediaType mediaType,
    required String sha256Digest,
    int attempt = 0,
  });

  Future<UploadedContentMedia> uploadPreparedSource({
    required PreparedContentMediaSource source,
    required MediaType mediaType,
    required String mimeType,
    required ContentMediaStreamObjectUpload uploadStream,
    MediaAssetAccessPolicy accessPolicy = MediaAssetAccessPolicy.ownerOnly,
    MediaCaptureMetadata? captureMetadata,
    ContentMediaUploadProgressCallback? onProgress,
    ContentMediaUploadCancellationSignal? cancellationSignal,
    ContentMediaPreparationCheckpoint? checkpoint,
    Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
    onCheckpoint,
  });

  Future<ContentMediaPreparationCheckpoint> cancelPreparedCheckpoint(
    ContentMediaPreparationCheckpoint checkpoint, {
    Future<void> Function(ContentMediaPreparationCheckpoint checkpoint)?
    onCheckpoint,
  });
}

String contentMediaMimeTypeForPath(String path, MediaType mediaType) {
  final lower = path.toLowerCase();
  return switch (mediaType) {
    MediaType.image when lower.endsWith('.png') => 'image/png',
    MediaType.image when lower.endsWith('.gif') => 'image/gif',
    MediaType.image when lower.endsWith('.webp') => 'image/webp',
    MediaType.image when lower.endsWith('.heic') || lower.endsWith('.heif') =>
      'image/heic',
    MediaType.image => 'image/jpeg',
    MediaType.video when lower.endsWith('.mov') => 'video/quicktime',
    MediaType.video when lower.endsWith('.m4v') => 'video/x-m4v',
    MediaType.video => 'video/mp4',
    MediaType.audio when lower.endsWith('.aac') => 'audio/aac',
    MediaType.audio when lower.endsWith('.m4a') => 'audio/x-m4a',
    MediaType.audio when lower.endsWith('.mp4') => 'audio/mp4',
    MediaType.audio => 'audio/mpeg',
    MediaType.file => 'application/octet-stream',
  };
}
