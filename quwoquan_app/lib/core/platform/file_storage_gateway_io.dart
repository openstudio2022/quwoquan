import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:quwoquan_app/core/platform/file_storage_gateway.dart';

/// `dart:io`-backed implementation for mobile / desktop / HarmonyOS.
///
/// This file is allowlisted for direct `dart:io` usage because it IS the
/// anti-corruption boundary (see verify_lib_dart_io_budget.py).
class IoFileStorageGateway implements FileStorageGateway {
  const IoFileStorageGateway();

  @override
  bool get isSupported => true;

  @override
  Future<String> applicationSupportPath() async {
    final dir = await getApplicationSupportDirectory();
    return dir.path;
  }

  @override
  Future<String> temporaryPath() async {
    final dir = await getTemporaryDirectory();
    return dir.path;
  }

  @override
  Future<bool> exists(String path) => File(path).exists();

  @override
  Future<String> readAsString(String path) => File(path).readAsString();

  @override
  Future<void> writeAsString(String path, String contents) async {
    await File(path).writeAsString(contents);
  }

  @override
  Future<List<int>> readAsBytes(String path) => File(path).readAsBytes();

  @override
  Future<void> writeAsBytes(String path, List<int> bytes) async {
    await File(path).writeAsBytes(bytes);
  }

  @override
  Future<void> delete(String path) async {
    final file = File(path);
    if (await file.exists()) {
      await file.delete();
    }
  }

  @override
  Future<void> ensureDirectory(String path) async {
    await Directory(path).create(recursive: true);
  }

  @override
  Future<List<FileSystemEntry>> listDirectory(String path) async {
    final dir = Directory(path);
    if (!await dir.exists()) {
      return const <FileSystemEntry>[];
    }
    final entries = <FileSystemEntry>[];
    await for (final entity in dir.list(followLinks: false)) {
      entries.add(
        FileSystemEntry(
          path: entity.path,
          isDirectory: entity is Directory,
        ),
      );
    }
    return entries;
  }
}

FileStorageGateway createPlatformFileStorageGateway() =>
    const IoFileStorageGateway();
