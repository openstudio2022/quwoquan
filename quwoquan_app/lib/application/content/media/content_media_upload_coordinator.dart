import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentMediaObjectUpload =
    Future<void> Function(
      Uri uploadUri,
      List<int> bytes, {
      required String contentType,
      required String expectedSha256,
    });

typedef ContentMediaStreamObjectUpload =
    Future<void> Function(
      Uri uploadUri,
      Stream<List<int>> bytes, {
      required int contentLength,
      required String contentType,
      required String expectedSha256,
    });

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
    required this.cdnUrl,
  });

  final String sessionId;
  final String assetId;
  final Uri? cdnUrl;
}

/// Application coordinator for the upload-session aggregate and its external
/// object-storage grant. It computes the immutable byte contract before
/// opening the session and aborts the authoritative session on every failure.
final class ContentMediaUploadCoordinator {
  const ContentMediaUploadCoordinator({
    required this.media,
    required this.fileStorage,
    required this.uploadObject,
  });

  final ContentMediaFacet media;
  final FileStorageGateway fileStorage;
  final ContentMediaObjectUpload uploadObject;

  Future<UploadedContentMedia> uploadLocalPath({
    required String localPath,
    required ContentMediaType mediaType,
    ContentMediaAccessPolicy accessPolicy = ContentMediaAccessPolicy.ownerOnly,
  }) async {
    final path = localPath.trim();
    if (path.isEmpty) throw StateError('media source path is empty');
    final bytes = await fileStorage.readAsBytes(path);
    if (bytes.isEmpty) throw StateError('media source is empty');
    return uploadBytes(
      bytes: bytes,
      mediaType: mediaType,
      contentType: contentMediaTypeForPath(path, mediaType),
      accessPolicy: accessPolicy,
    );
  }

  Future<UploadedContentMedia> uploadBytes({
    required List<int> bytes,
    required ContentMediaType mediaType,
    required String contentType,
    ContentMediaAccessPolicy accessPolicy = ContentMediaAccessPolicy.ownerOnly,
  }) async {
    if (bytes.isEmpty) throw StateError('media source is empty');
    return _upload(
      mediaType: mediaType,
      contentType: contentType,
      fileSize: bytes.length,
      expectedSha256: sha256.convert(bytes).toString(),
      accessPolicy: accessPolicy,
      writeObject: (uploadUrl, digest) => uploadObject(
        uploadUrl,
        bytes,
        contentType: contentType,
        expectedSha256: digest,
      ),
    );
  }

  Future<UploadedContentMedia> uploadPreparedSource({
    required PreparedContentMediaSource source,
    required ContentMediaType mediaType,
    required String contentType,
    required ContentMediaStreamObjectUpload uploadStream,
    ContentMediaAccessPolicy accessPolicy = ContentMediaAccessPolicy.ownerOnly,
  }) async {
    if (source.fileSize <= 0) throw StateError('media source is empty');
    return _upload(
      mediaType: mediaType,
      contentType: contentType,
      fileSize: source.fileSize,
      expectedSha256: source.sha256Digest,
      accessPolicy: accessPolicy,
      writeObject: (uploadUrl, digest) => uploadStream(
        uploadUrl,
        source.openRead(),
        contentLength: source.fileSize,
        contentType: contentType,
        expectedSha256: digest,
      ),
    );
  }

  Future<UploadedContentMedia> _upload({
    required ContentMediaType mediaType,
    required String contentType,
    required int fileSize,
    required String expectedSha256,
    required ContentMediaAccessPolicy accessPolicy,
    required Future<void> Function(Uri uploadUrl, String expectedSha256)
    writeObject,
  }) async {
    final init = await media.initUpload(
      InitContentMediaUploadCommand(
        mediaType: mediaType,
        contentType: contentType,
        fileSize: fileSize,
        expectedSha256: expectedSha256,
      ),
    );
    final sessionId = init.sessionId.trim();
    if (sessionId.isEmpty) throw StateError('media upload session is missing');
    try {
      final uploadUrl = init.uploadUrl;
      if (uploadUrl == null) {
        throw StateError('media upload session is missing object upload URL');
      }
      await writeObject(uploadUrl, expectedSha256);
      final completed = await media.completeUpload(
        CompleteContentMediaUploadCommand(
          sessionId: sessionId,
          accessPolicy: accessPolicy,
        ),
      );
      final assetId = (completed.assetId ?? '').trim();
      if (assetId.isEmpty) {
        throw StateError('completed media upload is missing assetId');
      }
      return UploadedContentMedia(
        sessionId: sessionId,
        assetId: assetId,
        cdnUrl: completed.cdnUrl,
      );
    } catch (_) {
      await media.abortUpload(
        AbortContentMediaUploadCommand(sessionId: sessionId),
      );
      rethrow;
    }
  }
}

String contentMediaTypeForPath(String path, ContentMediaType mediaType) {
  final lower = path.toLowerCase();
  return switch (mediaType) {
    ContentMediaType.image when lower.endsWith('.png') => 'image/png',
    ContentMediaType.image when lower.endsWith('.gif') => 'image/gif',
    ContentMediaType.image when lower.endsWith('.webp') => 'image/webp',
    ContentMediaType.image
        when lower.endsWith('.heic') || lower.endsWith('.heif') =>
      'image/heic',
    ContentMediaType.image => 'image/jpeg',
    ContentMediaType.video when lower.endsWith('.mov') => 'video/quicktime',
    ContentMediaType.video when lower.endsWith('.m4v') => 'video/x-m4v',
    ContentMediaType.video when lower.endsWith('.webm') => 'video/webm',
    ContentMediaType.video => 'video/mp4',
    ContentMediaType.audio when lower.endsWith('.wav') => 'audio/wav',
    ContentMediaType.audio when lower.endsWith('.aac') => 'audio/aac',
    ContentMediaType.audio => 'audio/mpeg',
    ContentMediaType.file => 'application/octet-stream',
  };
}
