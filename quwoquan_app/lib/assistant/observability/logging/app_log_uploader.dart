import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:io';

import 'package:quwoquan_app/assistant/observability/logging/app_log_paths.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';

/// Periodically uploads local JSON-line log files to the OpsEvent backend.
///
/// Strategy:
/// - Scans day directories for *.ndjson files.
/// - Reads up to [maxLinesPerBatch] lines per flush cycle.
/// - Converts each line to an [OpsEventRecordInput] with eventType = 'app_log'.
/// - Deletes fully uploaded files; truncates partially consumed files.
/// - Upload failures are silently logged; the file will be retried next cycle.
class AppLogUploader {
  AppLogUploader({
    required this.eventRepository,
    AppLogPaths? paths,
    this.maxLinesPerBatch = 100,
    this.flushInterval = const Duration(minutes: 5),
  }) : _paths = paths ?? AppLogPaths();

  final OpsEventRepository eventRepository;
  final AppLogPaths _paths;
  final int maxLinesPerBatch;
  final Duration flushInterval;
  Timer? _timer;

  void start() {
    _timer?.cancel();
    _timer = Timer.periodic(flushInterval, (_) => flush());
  }

  void dispose() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> flush() async {
    try {
      final root = await _paths.rootDirectory();
      if (!root.existsSync()) return;

      final dayDirs = root
          .listSync()
          .whereType<Directory>()
          .toList(growable: false)
        ..sort((a, b) => a.path.compareTo(b.path));

      var totalSent = 0;
      for (final dayDir in dayDirs) {
        if (totalSent >= maxLinesPerBatch) break;
        final files = _collectLogFiles(dayDir);
        for (final file in files) {
          if (totalSent >= maxLinesPerBatch) break;
          totalSent += await _uploadFile(file, maxLinesPerBatch - totalSent);
        }
      }
    } catch (e) {
      developer.log('AppLogUploader.flush error: $e', name: 'obs');
    }
  }

  List<File> _collectLogFiles(Directory dir) {
    final files = <File>[];
    try {
      for (final entity in dir.listSync(recursive: true)) {
        if (entity is File && entity.path.endsWith('.ndjson')) {
          files.add(entity);
        }
      }
    } catch (_) {}
    files.sort((a, b) => a.path.compareTo(b.path));
    return files;
  }

  Future<int> _uploadFile(File file, int maxLines) async {
    List<String> lines;
    try {
      lines = file
          .readAsLinesSync()
          .where((line) => line.trim().isNotEmpty)
          .toList(growable: false);
    } catch (_) {
      return 0;
    }
    if (lines.isEmpty) {
      try {
        file.deleteSync();
      } catch (_) {}
      return 0;
    }

    final batch = lines.take(maxLines).toList(growable: false);
    final events = <OpsEventRecordInput>[];
    final trace = AppTraceContextStore.instance;
    final now = DateTime.now().toUtc().toIso8601String();

    for (final line in batch) {
      try {
        final json = jsonDecode(line);
        if (json is! Map<String, dynamic>) continue;
        events.add(OpsEventRecordInput(
          eventId: trace.newRequestId(),
          eventType: 'app_log',
          eventName: (json['logType'] ?? 'unknown').toString(),
          occurredAt: (json['timestamp'] ?? now).toString(),
          clientSentAt: now,
          sessionId: (json['sessionId'] ?? trace.sessionId).toString(),
          pageVisitId: (json['pageVisitId'] ?? '').toString(),
          requestId: (json['requestId'] ?? '').toString(),
          producer: 'app.log_uploader',
          source: 'app_log',
          payload: json,
        ));
      } catch (_) {
        // Skip malformed lines
      }
    }

    if (events.isEmpty) return 0;

    try {
      await eventRepository.reportEventBatch(events: events);
    } catch (e) {
      developer.log('AppLogUploader upload failed: $e', name: 'obs');
      return 0;
    }

    if (batch.length >= lines.length) {
      try {
        file.deleteSync();
      } catch (_) {}
    } else {
      final remaining = '${lines.sublist(batch.length).join('\n')}\n';
      try {
        file.writeAsStringSync(remaining);
      } catch (_) {}
    }
    return batch.length;
  }
}
