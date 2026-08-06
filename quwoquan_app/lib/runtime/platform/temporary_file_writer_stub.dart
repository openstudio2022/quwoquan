import 'package:quwoquan_app/runtime/platform/platform_capability_unavailable.dart';

Future<String> writePlatformTemporaryFileBytes({
  required String fileName,
  required List<int> bytes,
}) async {
  throw PlatformCapabilityUnavailableException(
    capability: 'hasLocalFileSystem',
    detail: 'temporary file writes are not available on this platform',
  );
}
