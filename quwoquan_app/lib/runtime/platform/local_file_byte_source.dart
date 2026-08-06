import 'local_file_byte_source_stub.dart'
    if (dart.library.io) 'local_file_byte_source_io.dart';

/// A reopenable local-file stream with its immutable upload identity.
///
/// The platform boundary owns file-system access so cloud adapters stay portable
/// across mobile, desktop, web, and HarmonyOS targets.
final class LocalFileByteSource {
  const LocalFileByteSource({
    required this.fileSize,
    required this.sha256Digest,
    required this.openRead,
  });

  final int fileSize;
  final String sha256Digest;
  final Stream<List<int>> Function() openRead;
}

Future<LocalFileByteSource> prepareLocalFileByteSource(String localPath) =>
    preparePlatformLocalFileByteSource(localPath);
