import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/platform_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/platform/storage/media_cache_file_storage_gateway.dart';

/// Web stub: there is no local random-access file system on the web.
///
/// Every operation throws [PlatformCapabilityUnavailableException]; callers are
/// expected to gate on `PlatformCapabilities.hasLocalFileSystem` and degrade
/// (e.g. use in-memory / IndexedDB-backed stores) BEFORE reaching here. A
/// future IndexedDB-backed implementation can replace this stub without
/// touching business code.
class WebFileStorageGateway implements MediaCacheFileStorageGateway {
  const WebFileStorageGateway();

  @override
  bool get isSupported => false;

  Never _unavailable(String op) => throw PlatformCapabilityUnavailableException(
    capability: 'hasLocalFileSystem',
    detail: 'FileStorageGateway.$op is not available on web',
  );

  @override
  Future<String> applicationSupportPath() async =>
      _unavailable('applicationSupportPath');

  @override
  Future<String> temporaryPath() async => _unavailable('temporaryPath');

  @override
  Future<String> systemTemporaryPath() async =>
      _unavailable('systemTemporaryPath');

  @override
  String joinPath(String parent, String child) => _unavailable('joinPath');

  @override
  String basename(String path) => _unavailable('basename');

  @override
  Future<bool> exists(String path) async => false;

  @override
  Future<bool> directoryExists(String path) async =>
      _unavailable('directoryExists');

  @override
  bool fileExistsSync(String path) => _unavailable('fileExistsSync');

  @override
  int fileLengthSync(String path) => _unavailable('fileLengthSync');

  @override
  Future<String> readAsString(String path) async =>
      _unavailable('readAsString');

  @override
  Future<void> writeAsString(String path, String contents) async =>
      _unavailable('writeAsString');

  @override
  Future<void> appendAsString(String path, String contents) async =>
      _unavailable('appendAsString');

  @override
  Future<List<int>> readAsBytes(String path) async =>
      _unavailable('readAsBytes');

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) async =>
      _unavailable('writeAsBytes');

  @override
  Future<void> delete(String path) async {
    // No-op on web: nothing persisted to delete.
  }

  @override
  void deleteFileSync(String path) => _unavailable('deleteFileSync');

  @override
  Future<void> deleteDirectory(String path, {required bool recursive}) async =>
      _unavailable('deleteDirectory');

  @override
  Future<void> ensureDirectory(String path) async =>
      _unavailable('ensureDirectory');

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      _unavailable('listDirectory');
}

FileStorageGateway createPlatformFileStorageGateway() =>
    const WebFileStorageGateway();
