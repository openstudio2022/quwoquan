import 'dart:async';
import 'dart:developer' as developer;
import 'dart:io';

import 'package:quwoquan_app/assistant/observability/logging/app_log_paths.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';

/// Periodically uploads local delimited log files to the OpsEvent backend.
///
/// Strategy:
/// - Scans day directories for *.log files.
/// - Reads up to [maxLinesPerBatch] records per flush cycle.
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

      final dayDirs = root.listSync().whereType<Directory>().toList(
        growable: false,
      )..sort((a, b) => a.path.compareTo(b.path));

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
        if (entity is File && entity.path.endsWith('.log')) {
          files.add(entity);
        }
      }
    } catch (_) {
      /* best-effort: 日志目录可能不存在或不可读，扫描失败时返回已收集到的文件，下次再试 */
    }
    files.sort((a, b) => a.path.compareTo(b.path));
    return files;
  }

  Future<int> _uploadFile(File file, int maxLines) async {
    List<String> records;
    try {
      records = _readRecords(file);
    } catch (_) {
      return 0;
    }
    if (records.isEmpty) {
      try {
        file.deleteSync();
      } catch (_) {
        /* best-effort: 删除空日志文件失败可忽略，下次扫描会再次尝试清理 */
      }
      return 0;
    }

    final batch = records.take(maxLines).toList(growable: false);
    final events = <OpsEventRecordInput>[];
    final trace = AppTraceContextStore.instance;
    final now = DateTime.now().toUtc().toIso8601String();
    final kind = _kindFor(file);

    for (final record in batch) {
      final parsed = _parseRecord(kind, record);
      if (parsed == null) continue;
      events.add(
        OpsEventRecordInput(
          eventId: trace.newRequestId(),
          eventType: 'app_log',
          eventName: (parsed['event'] ?? parsed['msg'] ?? 'unknown').toString(),
          occurredAt: (parsed['ts'] ?? now).toString(),
          clientSentAt: now,
          sessionId: trace.sessionId,
          requestId: (parsed['req'] ?? '').toString(),
          producer: 'app.log_uploader',
          source: 'app_log',
          payload: parsed,
        ),
      );
    }

    if (events.isEmpty) return 0;

    try {
      await eventRepository.reportEventBatch(events: events);
    } catch (e) {
      developer.log('AppLogUploader upload failed: $e', name: 'obs');
      return 0;
    }

    if (batch.length >= records.length) {
      try {
        file.deleteSync();
      } catch (_) {
        /* best-effort: 全量上传后删除日志文件失败可忽略，残留文件会在后续轮次重传去重 */
      }
    } else {
      final remaining = '${records.sublist(batch.length).join('\n')}\n';
      try {
        file.writeAsStringSync(remaining);
      } catch (_) {
        /* best-effort: 回写剩余日志失败时保留原文件，下轮重传依赖服务端去重避免重复 */
      }
    }
    return batch.length;
  }

  List<String> _readRecords(File file) {
    final records = <String>[];
    final current = StringBuffer();
    for (final line in file.readAsLinesSync()) {
      if (line.trim().isEmpty) continue;
      if (line.startsWith(' ') || line.startsWith('\t')) {
        if (current.isNotEmpty) {
          current.write('\n${line.trimLeft()}');
        }
        continue;
      }
      if (current.isNotEmpty) {
        records.add(current.toString());
        current.clear();
      }
      current.write(line);
    }
    if (current.isNotEmpty) {
      records.add(current.toString());
    }
    return records;
  }

  String _kindFor(File file) {
    final name = file.uri.pathSegments.isNotEmpty
        ? file.uri.pathSegments.last
        : file.path;
    return name.endsWith('.log') ? name.substring(0, name.length - 4) : name;
  }

  Map<String, dynamic>? _parseRecord(String kind, String record) {
    final lines = record.split('\n');
    final first = lines.first;
    final fields = switch (kind) {
      'access' => const [
        'ts',
        'level',
        'method',
        'route',
        'status',
        'durMs',
        'req',
        'trace',
        'msg',
      ],
      'exception' => const ['ts', 'level', 'err', 'req', 'trace', 'msg'],
      'event' => const [
        'ts',
        'level',
        'event',
        'result',
        'req',
        'trace',
        'msg',
      ],
      _ => const ['ts', 'level', 'msg'],
    };
    final values = _splitFixed(first, fields.length);
    if (values.length != fields.length) return null;
    final parsed = <String, dynamic>{};
    for (var i = 0; i < fields.length; i += 1) {
      parsed[fields[i]] = values[i];
    }
    if (lines.length > 1) {
      parsed['msg'] = '${parsed['msg']}\n${lines.skip(1).join('\n')}';
    }
    return parsed;
  }

  List<String> _splitFixed(String line, int count) {
    final values = <String>[];
    var start = 0;
    for (var i = 0; i < count - 1; i += 1) {
      final index = line.indexOf(',', start);
      if (index < 0) return const <String>[];
      values.add(line.substring(start, index));
      start = index + 1;
    }
    values.add(line.substring(start));
    return values;
  }
}
