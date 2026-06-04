import 'package:quwoquan_app/core/platform/file_storage_gateway_io.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/core/platform/file_storage_gateway_web.dart';

/// Anti-corruption boundary for local file / path / directory access.
///
/// This is the single "choke point" that the ~32 existing `dart:io` call sites
/// are expected to migrate behind over time. New business code MUST go through
/// this gateway (resolved via `fileStorageGatewayProvider`) instead of
/// importing `dart:io` directly, so that web (no file system) and HarmonyOS
/// can supply their own implementations.
///
/// Methods throw [PlatformCapabilityUnavailableException] when
/// [isSupported] is false (e.g. on web).
abstract interface class FileStorageGateway {
  /// Whether a local random-access file system is available.
  bool get isSupported;

  /// App-private support directory (persistent).
  Future<String> applicationSupportPath();

  /// App temporary/cache directory (may be cleared by the OS).
  Future<String> temporaryPath();

  Future<bool> exists(String path);

  Future<String> readAsString(String path);

  Future<void> writeAsString(String path, String contents);

  Future<List<int>> readAsBytes(String path);

  Future<void> writeAsBytes(String path, List<int> bytes);

  Future<void> delete(String path);

  /// Ensures a directory (recursively) exists.
  Future<void> ensureDirectory(String path);
}

/// Builds the platform-appropriate gateway (io on mobile/desktop/ohos, web stub
/// on web). Selected at compile time via conditional import.
FileStorageGateway createFileStorageGateway() =>
    createPlatformFileStorageGateway();
