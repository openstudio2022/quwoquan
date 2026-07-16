import 'package:quwoquan_app/core/platform/local_file_byte_source.dart';
import 'package:quwoquan_app/core/platform/platform_capability_unavailable.dart';

Future<LocalFileByteSource> preparePlatformLocalFileByteSource(
  String localPath,
) async {
  throw PlatformCapabilityUnavailableException(
    capability: 'hasLocalFileSystem',
    detail: 'local file streaming is not available on this platform',
  );
}
