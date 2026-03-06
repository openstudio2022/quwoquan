import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_paths.dart';

class AppLogWriter {
  AppLogWriter({AppLogPaths? paths, this.keepDays = 7})
    : _paths = paths ?? AppLogPaths();

  final AppLogPaths _paths;
  final int keepDays;
  DateTime? _lastPruneAt;

  Future<String> appendJsonLine({
    required String subDirectory,
    required String fileName,
    required Map<String, dynamic> payload,
    DateTime? at,
  }) async {
    final time = at ?? DateTime.now();
    final dayDir = await _ensureDayDirectory(time);
    final subDir = Directory('${dayDir.path}/$subDirectory');
    if (!subDir.existsSync()) {
      subDir.createSync(recursive: true);
    }
    final file = File('${subDir.path}/$fileName');
    file.writeAsStringSync(
      '${jsonEncode(payload)}\n',
      mode: FileMode.append,
      flush: true,
    );
    await _pruneIfNeeded();
    return file.path;
  }

  Future<String> writeJsonFile({
    required String subDirectory,
    required String fileName,
    required Map<String, dynamic> payload,
    DateTime? at,
  }) async {
    final time = at ?? DateTime.now();
    final dayDir = await _ensureDayDirectory(time);
    final subDir = Directory('${dayDir.path}/$subDirectory');
    if (!subDir.existsSync()) {
      subDir.createSync(recursive: true);
    }
    final file = File('${subDir.path}/$fileName');
    file.writeAsStringSync(
      const JsonEncoder.withIndent('  ').convert(payload),
      flush: true,
    );
    await _pruneIfNeeded();
    return file.path;
  }

  Future<Directory> _ensureDayDirectory(DateTime time) async {
    final dayDir = await _paths.dayDirectory(time);
    if (!dayDir.existsSync()) {
      dayDir.createSync(recursive: true);
    }
    return dayDir;
  }

  Future<void> _pruneIfNeeded() async {
    final now = DateTime.now();
    if (_lastPruneAt != null && now.difference(_lastPruneAt!).inHours < 12) {
      return;
    }
    _lastPruneAt = now;
    try {
      final root = await _paths.rootDirectory();
      if (!root.existsSync()) return;
      final threshold = now.subtract(Duration(days: keepDays));
      final entries = root.listSync().whereType<Directory>().toList(
        growable: false,
      );
      for (final dir in entries) {
        final name = dir.uri.pathSegments.isNotEmpty
            ? dir.uri.pathSegments[dir.uri.pathSegments.length - 2]
            : '';
        final parsed = DateTime.tryParse(name);
        if (parsed == null) continue;
        if (parsed.isBefore(
          DateTime(threshold.year, threshold.month, threshold.day),
        )) {
          try {
            dir.deleteSync(recursive: true);
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
    }
  }
}
