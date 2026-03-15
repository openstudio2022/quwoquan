import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/internal_legacy/observability/logging/app_log_exporter.dart';
import 'package:quwoquan_app/assistant/internal_legacy/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/internal_legacy/observability/logging/app_log_paths.dart';
import 'package:quwoquan_app/assistant/internal_legacy/observability/logging/app_log_policy.dart';
import 'package:quwoquan_app/assistant/internal_legacy/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/internal_legacy/observability/logging/app_log_writer.dart';
import 'package:test/test.dart';

void main() {
  group('Observability log pipeline', () {
    late Directory tempRoot;
    late _TestAppLogPaths testPaths;
    late AppLogService service;

    setUp(() async {
      tempRoot = await Directory.systemTemp.createTemp('quwoquan_log_test_');
      // 使用当前日期，避免 keepDays 剪枝删除测试写入的文件
      testPaths = _TestAppLogPaths(
        rootPath: '${tempRoot.path}/quwoquan_logs',
        day: DateTime.now(),
      );
      service = AppLogService.forTesting(
        writer: AppLogWriter(paths: testPaths, keepDays: 7),
        policy: AppLogPolicy(isRelease: false),
      );
    });

    tearDown(() async {
      if (tempRoot.existsSync()) {
        await tempRoot.delete(recursive: true);
      }
    });

    test('商用态策略支持成功摘要、失败全量与动态提级', () {
      final policy = AppLogPolicy(isRelease: true, successSampleRate: 0.0);
      const sessionId = 'sess_a';
      const runId = 'run_a';

      expect(
        policy.shouldEmitSuccessLog(
          sessionId: sessionId,
          runId: runId,
          type: AppLogType.llm,
        ),
        isFalse,
      );
      expect(
        policy.shouldIncludeFullPayload(
          sessionId: sessionId,
          runId: runId,
          hasError: false,
          type: AppLogType.llm,
        ),
        isFalse,
      );
      expect(
        policy.shouldIncludeFullPayload(
          sessionId: sessionId,
          runId: runId,
          hasError: true,
          type: AppLogType.llm,
        ),
        isTrue,
      );

      policy.boostSession(sessionId);
      expect(
        policy.shouldEmitSuccessLog(
          sessionId: sessionId,
          runId: runId,
          type: AppLogType.search,
        ),
        isTrue,
      );
      expect(
        policy.shouldIncludeFullPayload(
          sessionId: sessionId,
          runId: runId,
          hasError: false,
          type: AppLogType.search,
        ),
        isTrue,
      );

      policy.clearBoosts();
      policy.boostRun(runId);
      expect(
        policy.shouldEmitSuccessLog(
          sessionId: sessionId,
          runId: runId,
          type: AppLogType.cloudApi,
        ),
        isTrue,
      );
    });

    test('日志写入失败不阻断（fail-open）', () async {
      final failingService = AppLogService.forTesting(
        writer: _ThrowingWriter(),
        policy: AppLogPolicy(isRelease: false),
      );

      final eventResult = await failingService.writeEvent(
        logType: AppLogType.llm,
        level: AppLogLevel.info,
        payload: <String, dynamic>{
          'kind': 'llm',
          'request': <String, dynamic>{'body': 'hello'},
        },
        context: const AppLogContext(sessionId: 'sess_fail', runId: 'run_fail'),
      );
      final runFileResult = await failingService.writeRunFile(
        runId: 'run_fail',
        payload: <String, dynamic>{'output': 'ok'},
      );

      expect(eventResult, isNull);
      expect(runFileResult, isNull);
    });

    test('导出结果包含路径、run 数量与时间范围摘要', () async {
      final dayDir = await testPaths.dayDirectory(DateTime.now());
      final agentDir = Directory('${dayDir.path}/agent');
      final integrationDir = Directory('${dayDir.path}/integrations');
      agentDir.createSync(recursive: true);
      integrationDir.createSync(recursive: true);

      File('${agentDir.path}/run_1001.json').writeAsStringSync('{"ok":true}');
      File('${agentDir.path}/run_1002.json').writeAsStringSync('{"ok":true}');
      File(
        '${integrationDir.path}/llm.jsonl',
      ).writeAsStringSync('{"kind":"llm"}\n');

      final exporter = AppLogExporter(paths: testPaths);
      final result = await exporter.exportToWorkspace(
        targetDirectory: '${tempRoot.path}/workspace_export',
      );

      expect(result.exportDirectory, contains('workspace_export/export_'));
      expect(result.copiedFileCount, greaterThanOrEqualTo(3));
      expect(result.runFileCount, equals(2));
      expect(result.timeRangeStartIso, isNotEmpty);
      expect(result.timeRangeEndIso, isNotEmpty);
      expect(result.firstRunId, equals('1001'));
      expect(result.lastRunId, equals('1002'));
      expect(result.summary, contains('runs=2'));
    });

    test('天气问答链路可按 runId 串联到 run 文件与 integrations', () async {
      const runId = 'weather_run_001';
      const sessionId = 'session_weather_001';
      const traceId = 'trace_weather_001';

      await service.writeEvent(
        logType: AppLogType.llm,
        level: AppLogLevel.info,
        context: const AppLogContext(
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
        ),
        payload: <String, dynamic>{
          'kind': 'llm',
          'request': <String, dynamic>{'body': '深圳天气怎样'},
          'response': <String, dynamic>{'statusCode': 200},
        },
      );
      await service.writeEvent(
        logType: AppLogType.search,
        level: AppLogLevel.info,
        context: const AppLogContext(
          sessionId: sessionId,
          runId: runId,
          traceId: traceId,
        ),
        payload: <String, dynamic>{
          'kind': 'search',
          'request': <String, dynamic>{'query': '深圳天气怎样'},
          'response': <String, dynamic>{'statusCode': 200},
        },
      );
      await service.writeRunFile(
        runId: runId,
        payload: <String, dynamic>{
          'meta': <String, dynamic>{
            'runId': runId,
            'traceId': traceId,
            'sessionId': sessionId,
          },
          'input': <String, dynamic>{'userMessage': '深圳天气怎样'},
          'interactions': <Map<String, dynamic>>[
            <String, dynamic>{
              'kind': 'llm',
              'request': <String, dynamic>{'body': '深圳天气怎样'},
              'response': <String, dynamic>{'statusCode': 200},
            },
            <String, dynamic>{
              'kind': 'search',
              'request': <String, dynamic>{'query': '深圳天气怎样'},
              'response': <String, dynamic>{'statusCode': 200},
            },
          ],
          'output': <String, dynamic>{'finalText': '深圳当前天气晴，气温 22C。'},
        },
      );

      final root = await testPaths.rootDirectory();
      final now = DateTime.now();
      final today =
          '${now.year.toString().padLeft(4, '0')}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')}';
      final runFile = File('${root.path}/$today/agent/run_$runId.json');
      final llmLogFile = File('${root.path}/$today/integrations/llm.jsonl');
      final searchLogFile = File(
        '${root.path}/$today/integrations/search.jsonl',
      );

      expect(runFile.existsSync(), isTrue);
      expect(llmLogFile.existsSync(), isTrue);
      expect(searchLogFile.existsSync(), isTrue);

      final runJson = jsonDecode(await runFile.readAsString()) as Map;
      final interactions =
          (runJson['interactions'] as List?) ?? const <dynamic>[];
      final kinds = interactions
          .whereType<Map>()
          .map((item) => item['kind']?.toString() ?? '')
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
      expect(kinds.contains('llm'), isTrue);
      expect(kinds.contains('search'), isTrue);
      expect((runJson['output'] as Map?)?['finalText'], isNotEmpty);
      expect((runJson['meta'] as Map?)?['runId'], equals(runId));

      final llmLines = await _readJsonLines(llmLogFile);
      final searchLines = await _readJsonLines(searchLogFile);
      expect(
        llmLines.any((line) => line['runId']?.toString() == runId),
        isTrue,
      );
      expect(
        searchLines.any((line) => line['runId']?.toString() == runId),
        isTrue,
      );
    });
  });
}

Future<List<Map<String, dynamic>>> _readJsonLines(File file) async {
  final content = await file.readAsString();
  final out = <Map<String, dynamic>>[];
  final lines = const LineSplitter().convert(content);
  for (final line in lines) {
    final trimmed = line.trim();
    if (trimmed.isEmpty) {
      continue;
    }
    final decoded = jsonDecode(trimmed);
    if (decoded is Map) {
      out.add(decoded.cast<String, dynamic>());
    }
  }
  return out;
}

class _ThrowingWriter extends AppLogWriter {
  _ThrowingWriter()
    : super(
        paths: _TestAppLogPaths(
          rootPath:
              '${Directory.systemTemp.path}/quwoquan_log_test_throwing_writer',
          day: DateTime(2026, 2, 18, 12, 0, 0),
        ),
      );

  @override
  Future<String> appendJsonLine({
    required String subDirectory,
    required String fileName,
    required Map<String, dynamic> payload,
    DateTime? at,
  }) async {
    throw Exception('append failed');
  }

  @override
  Future<String> writeJsonFile({
    required String subDirectory,
    required String fileName,
    required Map<String, dynamic> payload,
    DateTime? at,
  }) async {
    throw Exception('write file failed');
  }
}

class _TestAppLogPaths extends AppLogPaths {
  _TestAppLogPaths({required this.rootPath, required this.day})
    : super(rootDirName: 'ignored_for_test');

  final String rootPath;
  final DateTime day;

  @override
  Future<Directory> rootDirectory() async {
    return Directory(rootPath);
  }

  @override
  Future<Directory> dayDirectory(DateTime time) async {
    final y = day.year.toString().padLeft(4, '0');
    final m = day.month.toString().padLeft(2, '0');
    final d = day.day.toString().padLeft(2, '0');
    return Directory('$rootPath/$y-$m-$d');
  }
}
