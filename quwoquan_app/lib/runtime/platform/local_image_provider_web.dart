import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/runtime/platform/platform_capability_unavailable.dart';

ImageProvider<Object> createLocalFileImageProvider(String path) {
  throw PlatformCapabilityUnavailableException(
    capability: 'hasLocalFileSystem',
    detail: 'local file images are not available on web',
  );
}
