import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver_io.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver_web.dart';

typedef LocalDatabaseDirectoryLoader = Future<String> Function();

/// Typed anti-corruption boundary for resolving an app-private database path.
///
/// Business adapters provide only an optional explicit path, a stable file
/// name, and the database driver's directory loader. Platform path separators
/// and directory creation remain inside `runtime/platform`.
abstract interface class LocalDatabasePathResolver {
  Future<String> resolve({
    String? explicitPath,
    required String fileName,
    required LocalDatabaseDirectoryLoader loadDefaultDirectory,
  });
}

/// Builds the platform implementation. Native platforms preserve the existing
/// local-file behavior; web fails closed through the platform capability
/// boundary rather than importing `dart:io` into a business adapter.
LocalDatabasePathResolver createLocalDatabasePathResolver(
  FileStorageGateway fileStorageGateway,
) => createPlatformLocalDatabasePathResolver(fileStorageGateway);
