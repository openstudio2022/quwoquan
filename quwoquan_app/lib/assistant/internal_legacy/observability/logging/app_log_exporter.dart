import 'dart:io';

import 'package:quwoquan_app/assistant/internal_legacy/observability/logging/app_log_paths.dart';

class AppLogExportResult {
  const AppLogExportResult({
    required this.exportDirectory,
    required this.copiedFileCount,
    required this.runFileCount,
    this.timeRangeStartIso = '',
    this.timeRangeEndIso = '',
    this.firstRunId = '',
    this.lastRunId = '',
  });

  final String exportDirectory;
  final int copiedFileCount;
  final int runFileCount;
  final String timeRangeStartIso;
  final String timeRangeEndIso;
  final String firstRunId;
  final String lastRunId;

  String get summary {
    final timeRange = timeRangeStartIso.isNotEmpty && timeRangeEndIso.isNotEmpty
        ? '$timeRangeStartIso ~ $timeRangeEndIso'
        : 'N/A';
    final runRange = firstRunId.isNotEmpty && lastRunId.isNotEmpty
        ? '$firstRunId ~ $lastRunId'
        : 'N/A';
    return 'path=$exportDirectory, files=$copiedFileCount, runs=$runFileCount, timeRange=$timeRange, runRange=$runRange';
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'exportDirectory': exportDirectory,
      'copiedFileCount': copiedFileCount,
      'runFileCount': runFileCount,
      'timeRange': <String, dynamic>{
        'start': timeRangeStartIso,
        'end': timeRangeEndIso,
      },
      'runRange': <String, dynamic>{'first': firstRunId, 'last': lastRunId},
      'summary': summary,
    };
  }
}

class AppLogExporter {
  AppLogExporter({AppLogPaths? paths}) : _paths = paths ?? AppLogPaths();

  static const String defaultWorkspaceTarget =
      '/Users/zhaoyuxi/Projects/quwoquan/quwoquan_app/app_log';
  final AppLogPaths _paths;

  Future<AppLogExportResult> exportToWorkspace({
    String targetDirectory = defaultWorkspaceTarget,
  }) async {
    final sourceRoot = await _paths.rootDirectory();
    final source = Directory(sourceRoot.path);
    final stats = _collectStats(source);
    if (!source.existsSync()) {
      final target = Directory(targetDirectory);
      if (!target.existsSync()) {
        target.createSync(recursive: true);
      }
      return AppLogExportResult(
        exportDirectory: target.path,
        copiedFileCount: 0,
        runFileCount: 0,
      );
    }
    final targetRoot = Directory(targetDirectory);
    if (!targetRoot.existsSync()) {
      targetRoot.createSync(recursive: true);
    }
    final destination = _buildDestinationDirectory(
      targetRoot: targetRoot,
      stats: stats,
    );
    destination.createSync(recursive: true);

    final copied = _copyRecursively(source, destination);
    return AppLogExportResult(
      exportDirectory: destination.path,
      copiedFileCount: copied,
      runFileCount: stats.runFileCount,
      timeRangeStartIso: stats.timeRangeStartIso,
      timeRangeEndIso: stats.timeRangeEndIso,
      firstRunId: stats.firstRunId,
      lastRunId: stats.lastRunId,
    );
  }

  int _copyRecursively(Directory source, Directory destination) {
    var count = 0;
    final entities = source.listSync(recursive: true, followLinks: false);
    for (final entity in entities) {
      final relative = entity.path
          .substring(source.path.length)
          .replaceFirst(RegExp(r'^/'), '');
      final targetPath = '${destination.path}/$relative';
      if (entity is Directory) {
        final dir = Directory(targetPath);
        if (!dir.existsSync()) {
          dir.createSync(recursive: true);
        }
        continue;
      }
      if (entity is File) {
        final targetDir = Directory(File(targetPath).parent.path);
        if (!targetDir.existsSync()) {
          targetDir.createSync(recursive: true);
        }
        entity.copySync(targetPath);
        count += 1;
      }
    }
    return count;
  }

  _AppLogExportStats _collectStats(Directory source) {
    if (!source.existsSync()) {
      return const _AppLogExportStats();
    }
    DateTime? earliest;
    DateTime? latest;
    final runIds = <String>[];
    final entities = source.listSync(recursive: true, followLinks: false);
    for (final entity in entities) {
      if (entity is! File) {
        continue;
      }
      try {
        final modified = entity.lastModifiedSync();
        if (earliest == null || modified.isBefore(earliest)) {
          earliest = modified;
        }
        if (latest == null || modified.isAfter(latest)) {
          latest = modified;
        }
      } catch (_) {
        // ignore metadata read failures
      }
      final fileName = _fileNameOf(entity.path);
      if (!fileName.startsWith('run_') || !fileName.endsWith('.json')) {
        continue;
      }
      final runId = fileName.substring(4, fileName.length - 5).trim();
      if (runId.isNotEmpty) {
        runIds.add(runId);
      }
    }
    runIds.sort();
    return _AppLogExportStats(
      runFileCount: runIds.length,
      timeRangeStartIso: earliest?.toIso8601String() ?? '',
      timeRangeEndIso: latest?.toIso8601String() ?? '',
      firstRunId: runIds.isEmpty ? '' : runIds.first,
      lastRunId: runIds.isEmpty ? '' : runIds.last,
    );
  }

  Directory _buildDestinationDirectory({
    required Directory targetRoot,
    required _AppLogExportStats stats,
  }) {
    final start = _formatDirStamp(
      stats.timeRangeStartIso.isNotEmpty
          ? DateTime.tryParse(stats.timeRangeStartIso) ?? DateTime.now()
          : DateTime.now(),
    );
    final end = _formatDirStamp(
      stats.timeRangeEndIso.isNotEmpty
          ? DateTime.tryParse(stats.timeRangeEndIso) ?? DateTime.now()
          : DateTime.now(),
    );
    final baseName = 'export_${start}_${end}_runs_${stats.runFileCount}';
    var candidate = Directory('${targetRoot.path}/$baseName');
    var suffix = 1;
    while (candidate.existsSync()) {
      candidate = Directory('${targetRoot.path}/${baseName}_$suffix');
      suffix += 1;
    }
    return candidate;
  }

  String _formatDirStamp(DateTime value) {
    final y = value.year.toString().padLeft(4, '0');
    final m = value.month.toString().padLeft(2, '0');
    final d = value.day.toString().padLeft(2, '0');
    final hh = value.hour.toString().padLeft(2, '0');
    final mm = value.minute.toString().padLeft(2, '0');
    final ss = value.second.toString().padLeft(2, '0');
    return '$y$m${d}_$hh$mm$ss';
  }

  String _fileNameOf(String path) {
    final normalized = path.replaceAll('\\', '/');
    final index = normalized.lastIndexOf('/');
    if (index < 0) {
      return normalized;
    }
    return normalized.substring(index + 1);
  }
}

class _AppLogExportStats {
  const _AppLogExportStats({
    this.runFileCount = 0,
    this.timeRangeStartIso = '',
    this.timeRangeEndIso = '',
    this.firstRunId = '',
    this.lastRunId = '',
  });

  final int runFileCount;
  final String timeRangeStartIso;
  final String timeRangeEndIso;
  final String firstRunId;
  final String lastRunId;
}
