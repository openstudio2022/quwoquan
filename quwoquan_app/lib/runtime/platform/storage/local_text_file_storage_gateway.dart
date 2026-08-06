import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';

/// Narrow platform boundary for append-only logs and JSON diagnostic files.
///
/// Path separators, app support/temp directories, file modes, directory
/// enumeration, and recursive deletion are owned by the platform
/// implementation. Observability code consumes only strings and typed entries.
abstract interface class LocalTextFileStorageGateway
    implements FileStorageGateway {
  /// Mirrors `Directory.systemTemp.path` on native platforms so fallback
  /// behavior remains independent from a second path-provider lookup.
  Future<String> systemTemporaryPath();

  String joinPath(String parent, String child);

  String basename(String path);

  Future<bool> directoryExists(String path);

  Future<void> appendAsString(String path, String contents);

  Future<void> deleteDirectory(String path, {required bool recursive});
}

/// Narrows the canonical [FileStorageGateway] platform composition without
/// introducing a second file adapter or factory truth source.
LocalTextFileStorageGateway requireLocalTextFileStorageGateway(
  FileStorageGateway gateway,
) {
  if (gateway case final LocalTextFileStorageGateway localTextGateway) {
    return localTextGateway;
  }
  throw StateError(
    'The platform FileStorageGateway does not provide local text storage',
  );
}
