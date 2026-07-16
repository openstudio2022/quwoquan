import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/core/platform/local_file_byte_source.dart';

/// Infrastructure adapter for a stable local-file byte contract. The digest
/// is completed before the authoritative upload session is opened; the body is
/// then re-opened as a stream so large Chat media is never buffered in memory.
final class LocalContentMediaSourceReader implements ContentMediaSourceReader {
  const LocalContentMediaSourceReader();

  @override
  Future<PreparedContentMediaSource> prepare(String localPath) async {
    final source = await prepareLocalFileByteSource(localPath);
    return PreparedContentMediaSource(
      fileSize: source.fileSize,
      sha256Digest: source.sha256Digest,
      openRead: source.openRead,
    );
  }
}
