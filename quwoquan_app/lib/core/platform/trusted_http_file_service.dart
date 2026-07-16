import 'package:flutter_cache_manager/flutter_cache_manager.dart';

import 'trusted_http_file_service_stub.dart'
    if (dart.library.io) 'trusted_http_file_service_io.dart';

/// Creates the cache transport appropriate for the current platform.
///
/// Native targets bind to the shared trust context after local development TLS
/// setup. Other targets use the package default transport.
HttpFileService createTrustedHttpFileService() =>
    createPlatformTrustedHttpFileService();
