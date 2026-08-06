import 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver.dart';

/// Test-only path resolver that requires every local-contract store to declare
/// its database path explicitly. It never reads a platform directory.
final class ExplicitTestLocalDatabasePathResolver
    implements LocalDatabasePathResolver {
  const ExplicitTestLocalDatabasePathResolver();

  @override
  Future<String> resolve({
    String? explicitPath,
    required String fileName,
    required LocalDatabaseDirectoryLoader loadDefaultDirectory,
  }) async {
    final normalizedPath = explicitPath?.trim() ?? '';
    if (normalizedPath.isEmpty) {
      throw StateError('local-contract databasePath must be explicit');
    }
    return normalizedPath;
  }
}
