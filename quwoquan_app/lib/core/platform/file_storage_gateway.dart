import 'package:quwoquan_app/core/platform/file_storage_gateway_io.dart'
    if (dart.library.js_interop) 'package:quwoquan_app/core/platform/file_storage_gateway_web.dart';

/// 目录子项（路径 + 是否目录）。供能力位为本机文件系统的平台（桌面 / 移动 / 鸿蒙）
/// 在防腐层内做目录遍历，业务层据此聚合本地相册等，无需直接 import `dart:io`。
class FileSystemEntry {
  const FileSystemEntry({required this.path, required this.isDirectory});

  final String path;
  final bool isDirectory;
}

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

  /// 列出 [path] 目录下的直接子项（不递归）。递归与上限由调用方控制，
  /// 防腐层只暴露单层枚举，便于测试注入与性能管控。
  /// 当 [isSupported] 为 false（如 web）时抛 [PlatformCapabilityUnavailableException]。
  Future<List<FileSystemEntry>> listDirectory(String path);
}

/// Builds the platform-appropriate gateway (io on mobile/desktop/ohos, web stub
/// on web). Selected at compile time via conditional import.
FileStorageGateway createFileStorageGateway() =>
    createPlatformFileStorageGateway();
