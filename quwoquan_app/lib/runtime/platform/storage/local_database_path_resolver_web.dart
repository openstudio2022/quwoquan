import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/platform_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver.dart';

final class WebLocalDatabasePathResolver implements LocalDatabasePathResolver {
  const WebLocalDatabasePathResolver();

  @override
  Future<String> resolve({
    String? explicitPath,
    required String fileName,
    required LocalDatabaseDirectoryLoader loadDefaultDirectory,
  }) async {
    throw PlatformCapabilityUnavailableException(
      capability: 'hasLocalFileSystem',
      detail: 'Local SQLite database paths are not available on web',
    );
  }
}

LocalDatabasePathResolver createPlatformLocalDatabasePathResolver(
  FileStorageGateway fileStorageGateway,
) => const WebLocalDatabasePathResolver();
