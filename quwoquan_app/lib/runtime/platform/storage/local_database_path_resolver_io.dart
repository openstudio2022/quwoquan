import 'dart:io';

import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver.dart';

final class IoLocalDatabasePathResolver implements LocalDatabasePathResolver {
  const IoLocalDatabasePathResolver(this._fileStorageGateway);

  final FileStorageGateway _fileStorageGateway;

  @override
  Future<String> resolve({
    String? explicitPath,
    required String fileName,
    required LocalDatabaseDirectoryLoader loadDefaultDirectory,
  }) async {
    final normalizedExplicitPath = explicitPath?.trim() ?? '';
    if (normalizedExplicitPath.isNotEmpty) {
      final lastSeparator = normalizedExplicitPath.lastIndexOf(
        Platform.pathSeparator,
      );
      if (lastSeparator > 0) {
        await _fileStorageGateway.ensureDirectory(
          normalizedExplicitPath.substring(0, lastSeparator),
        );
      }
      return normalizedExplicitPath;
    }

    final basePath = await loadDefaultDirectory();
    await _fileStorageGateway.ensureDirectory(basePath);
    return '$basePath${Platform.pathSeparator}$fileName';
  }
}

LocalDatabasePathResolver createPlatformLocalDatabasePathResolver(
  FileStorageGateway fileStorageGateway,
) => IoLocalDatabasePathResolver(fileStorageGateway);
