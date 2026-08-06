import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/runtime/platform/local_image_provider_io.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/runtime/platform/local_image_provider_web.dart';

ImageProvider<Object> localFileImageProvider(String path) {
  return createLocalFileImageProvider(path);
}
