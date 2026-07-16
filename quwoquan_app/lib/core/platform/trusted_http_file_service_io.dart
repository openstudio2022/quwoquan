import 'dart:io';

import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:http/io_client.dart';

HttpFileService createPlatformTrustedHttpFileService() {
  return HttpFileService(
    httpClient: IOClient(HttpClient(context: SecurityContext.defaultContext)),
  );
}
