import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/core/platform/platform_capability_unavailable.dart';

/// Web stub: there is no local random-access file system on the web.
///
/// Every operation throws [PlatformCapabilityUnavailableException]; callers are
/// expected to gate on `PlatformCapabilities.hasLocalFileSystem` and degrade
/// (e.g. use in-memory / IndexedDB-backed stores) BEFORE reaching here. A
/// future IndexedDB-backed implementation can replace this stub without
/// touching business code.
class WebFileStorageGateway implements FileStorageGateway {
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
  Future<bool> exists(String path) async => false;

  @override
  Future<String> readAsString(String path) async =>
      _unavailable('readAsString');

  @override
  Future<void> writeAsString(String path, String contents) async =>
      _unavailable('writeAsString');

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
  Future<void> ensureDirectory(String path) async =>
      _unavailable('ensureDirectory');

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async =>
      _unavailable('listDirectory');
}

FileStorageGateway createPlatformFileStorageGateway() =>
    const WebFileStorageGateway();
