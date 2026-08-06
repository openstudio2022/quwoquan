import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/runtime/observability/app_log_paths.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_app/runtime/platform/storage/local_text_file_storage_gateway.dart';

class AppLogWriter {
  AppLogWriter({
    AppLogPaths? paths,
    LocalTextFileStorageGateway? storageGateway,
    this.keepDays = 7,
  }) : _storageGateway = _resolveStorageGateway(paths, storageGateway),
       _paths = paths ?? AppLogPaths(storageGateway: storageGateway);

  final AppLogPaths _paths;
  final LocalTextFileStorageGateway _storageGateway;
  final int keepDays;
  DateTime? _lastPruneAt;
  Future<AppLogDirectoryPath>? _rootDirectoryFuture;
  Future<void> _writeTail = Future<void>.value();
  bool _pruneScheduled = false;

  static LocalTextFileStorageGateway _resolveStorageGateway(
    AppLogPaths? paths,
    LocalTextFileStorageGateway? storageGateway,
  ) {
    if (paths != null &&
        storageGateway != null &&
        !identical(paths.storageGateway, storageGateway)) {
      throw ArgumentError(
        'AppLogPaths and AppLogWriter must use the same storage gateway',
      );
    }
    return storageGateway ??
        paths?.storageGateway ??
        requireLocalTextFileStorageGateway(createFileStorageGateway());
  }

  Future<String> appendLogLine({
    required String subDirectory,
    required String fileName,
    required String line,
    DateTime? at,
  }) async {
    if (!_storageGateway.isSupported) {
      return 'web://app-log/$subDirectory/$fileName';
    }
    final time = at ?? DateTime.now();
    return _enqueueWrite(() async {
      final dayDir = await _ensureDayDirectory(time);
      final subDirectoryPath = _storageGateway.joinPath(
        dayDir.path,
        subDirectory,
      );
      if (!await _storageGateway.directoryExists(subDirectoryPath)) {
        await _storageGateway.ensureDirectory(subDirectoryPath);
      }
      final filePath = _storageGateway.joinPath(subDirectoryPath, fileName);
      await _storageGateway.appendAsString(filePath, '$line\n');
      _schedulePruneIfNeeded();
      return filePath;
    });
  }

  Future<String> writeJsonFile({
    required String subDirectory,
    required String fileName,
    required Map<String, dynamic> payload,
    DateTime? at,
  }) async {
    if (!_storageGateway.isSupported) {
      return 'web://app-log/$subDirectory/$fileName';
    }
    final time = at ?? DateTime.now();
    return _enqueueWrite(() async {
      final dayDir = await _ensureDayDirectory(time);
      final subDirectoryPath = _storageGateway.joinPath(
        dayDir.path,
        subDirectory,
      );
      if (!await _storageGateway.directoryExists(subDirectoryPath)) {
        await _storageGateway.ensureDirectory(subDirectoryPath);
      }
      final filePath = _storageGateway.joinPath(subDirectoryPath, fileName);
      await _storageGateway.writeAsString(
        filePath,
        const JsonEncoder.withIndent('  ').convert(payload),
      );
      _schedulePruneIfNeeded();
      return filePath;
    });
  }

  Future<AppLogDirectoryPath> _ensureDayDirectory(DateTime time) async {
    final root = await (_rootDirectoryFuture ??= _paths.rootDirectory());
    final dayDirectory = AppLogDirectoryPath(
      _storageGateway.joinPath(root.path, _dayStamp(time)),
    );
    if (!await _storageGateway.directoryExists(dayDirectory.path)) {
      await _storageGateway.ensureDirectory(dayDirectory.path);
    }
    return dayDirectory;
  }

  Future<T> _enqueueWrite<T>(Future<T> Function() action) {
    final completer = Completer<T>();
    final previous = _writeTail;
    final next = Completer<void>();
    _writeTail = next.future;
    unawaited(() async {
      try {
        await previous;
        completer.complete(await action());
      } catch (error, stackTrace) {
        completer.completeError(error, stackTrace);
      } finally {
        if (!next.isCompleted) {
          next.complete();
        }
      }
    }());
    return completer.future;
  }

  void _schedulePruneIfNeeded() {
    final now = DateTime.now();
    if (_pruneScheduled ||
        (_lastPruneAt != null && now.difference(_lastPruneAt!).inHours < 12)) {
      return;
    }
    _lastPruneAt = now;
    _pruneScheduled = true;
    unawaited(_pruneDirectories(now));
  }

  Future<void> _pruneDirectories(DateTime now) async {
    try {
      final root = await (_rootDirectoryFuture ??= _paths.rootDirectory());
      if (!await _storageGateway.directoryExists(root.path)) return;
      final threshold = now.subtract(Duration(days: keepDays));
      final entries = await _storageGateway.listDirectory(root.path);
      for (final entry in entries) {
        if (!entry.isDirectory) {
          continue;
        }
        final parsed = DateTime.tryParse(_storageGateway.basename(entry.path));
        if (parsed == null) {
          continue;
        }
        if (parsed.isBefore(
          DateTime(threshold.year, threshold.month, threshold.day),
        )) {
          try {
            await _storageGateway.deleteDirectory(entry.path, recursive: true);
          } catch (error) {
            if (kDebugMode) {
              debugPrint('[AppLogWriter] prune failed: $error');
            }
          }
        }
      }
    } catch (error) {
      if (kDebugMode) {
        debugPrint('[AppLogWriter] prune exception: $error');
      }
    } finally {
      _pruneScheduled = false;
    }
  }

  String _dayStamp(DateTime time) {
    final y = time.year.toString().padLeft(4, '0');
    final m = time.month.toString().padLeft(2, '0');
    final d = time.day.toString().padLeft(2, '0');
    return '$y-$m-$d';
  }
}
