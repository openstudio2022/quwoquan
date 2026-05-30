import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_paths.dart';

class AppLogWriter {
  AppLogWriter({AppLogPaths? paths, this.keepDays = 7})
    : _paths = paths ?? AppLogPaths();

  final AppLogPaths _paths;
  final int keepDays;
  DateTime? _lastPruneAt;
  Future<Directory>? _rootDirectoryFuture;
  Future<void> _writeTail = Future<void>.value();
  bool _pruneScheduled = false;

  Future<String> appendJsonLine({
    required String subDirectory,
    required String fileName,
    required Map<String, dynamic> payload,
    DateTime? at,
  }) async {
    final time = at ?? DateTime.now();
    return _enqueueWrite(() async {
      final dayDir = await _ensureDayDirectory(time);
      final subDir = Directory('${dayDir.path}/$subDirectory');
      if (!await subDir.exists()) {
        await subDir.create(recursive: true);
      }
      final file = File('${subDir.path}/$fileName');
      await file.writeAsString(
        '${jsonEncode(payload)}\n',
        mode: FileMode.append,
      );
      _schedulePruneIfNeeded();
      return file.path;
    });
  }

  Future<String> writeJsonFile({
    required String subDirectory,
    required String fileName,
    required Map<String, dynamic> payload,
    DateTime? at,
  }) async {
    final time = at ?? DateTime.now();
    return _enqueueWrite(() async {
      final dayDir = await _ensureDayDirectory(time);
      final subDir = Directory('${dayDir.path}/$subDirectory');
      if (!await subDir.exists()) {
        await subDir.create(recursive: true);
      }
      final file = File('${subDir.path}/$fileName');
      await file.writeAsString(
        const JsonEncoder.withIndent('  ').convert(payload),
      );
      _schedulePruneIfNeeded();
      return file.path;
    });
  }

  Future<Directory> _ensureDayDirectory(DateTime time) async {
    final root = await (_rootDirectoryFuture ??= _paths.rootDirectory());
    final dayDir = Directory('${root.path}/${_dayStamp(time)}');
    if (!await dayDir.exists()) {
      await dayDir.create(recursive: true);
    }
    return dayDir;
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
      if (!await root.exists()) return;
      final threshold = now.subtract(Duration(days: keepDays));
      await for (final entity in root.list()) {
        if (entity is! Directory) {
          continue;
        }
        final name = entity.uri.pathSegments.isNotEmpty
            ? entity.uri.pathSegments[entity.uri.pathSegments.length - 2]
            : '';
        final parsed = DateTime.tryParse(name);
        if (parsed == null) {
          continue;
        }
        if (parsed.isBefore(
          DateTime(threshold.year, threshold.month, threshold.day),
        )) {
          try {
            await entity.delete(recursive: true);
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
