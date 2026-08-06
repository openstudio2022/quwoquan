import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_text_file_storage_gateway.dart';

/// Synchronous file probes required by the public `MediaDownloadCache.isCached`
/// contract. The capability is implemented by the same canonical
/// [FileStorageGateway] adapter; it is not a second filesystem implementation.
abstract interface class MediaCacheFileStorageGateway
    implements LocalTextFileStorageGateway {
  bool fileExistsSync(String path);

  int fileLengthSync(String path);

  void deleteFileSync(String path);
}

MediaCacheFileStorageGateway requireMediaCacheFileStorageGateway(
  FileStorageGateway gateway,
) {
  if (gateway case final MediaCacheFileStorageGateway mediaCacheGateway) {
    return mediaCacheGateway;
  }
  throw StateError(
    'The platform FileStorageGateway does not provide media cache storage',
  );
}
