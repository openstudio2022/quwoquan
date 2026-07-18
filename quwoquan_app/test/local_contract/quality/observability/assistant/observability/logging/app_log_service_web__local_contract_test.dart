import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_policy.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_writer.dart';

class _MemoryAppLogWriter extends AppLogWriter {
  String? lastLine;

  @override
  Future<String> appendLogLine({
    required String subDirectory,
    required String fileName,
    required String line,
    DateTime? at,
  }) async {
    lastLine = line;
    return 'memory://$subDirectory/$fileName';
  }
}

void main() {
  test(
    'writeEvent resolves platform without touching dart:io on web',
    () async {
      final writer = _MemoryAppLogWriter();
      final service = AppLogService.forTesting(
        writer: writer,
        policy: AppLogPolicy(),
      );

      final path = await service.writeEvent(
        logType: AppLogType.error,
        level: AppLogLevel.error,
        payload: const <String, dynamic>{'event': 'web_smoke'},
        context: const AppLogContext(sessionId: 'session_web_smoke'),
        hasError: true,
      );

      expect(path, 'memory://app/exception.log');
      expect(writer.lastLine, matches(RegExp(r'^\d{4}-\d{2}-\d{2}T')));
      expect(writer.lastLine, contains(',ERROR,app exception,,'));
      expect(writer.lastLine, isNot(contains('schema')));
      expect(writer.lastLine, isNot(contains('sessionId')));
    },
  );

  test(
    'default writer no-ops on web instead of touching dart:io namespace',
    () async {
      final path = await AppLogWriter().appendLogLine(
        subDirectory: 'app',
        fileName: 'event.log',
        line: '2026-07-08T10:00:00Z,INFO,web_writer_smoke,ok,web smoke',
      );

      if (kIsWeb) {
        expect(path, 'web://app-log/app/event.log');
      }
    },
  );

  test('access logs use short request fields', () async {
    final writer = _MemoryAppLogWriter();
    final service = AppLogService.forTesting(
      writer: writer,
      policy: AppLogPolicy(isRelease: false),
    );

    final path = await service.writeEvent(
      logType: AppLogType.cloudApi,
      level: AppLogLevel.info,
      payload: const <String, dynamic>{
        'method': 'GET',
        'route': '/search',
        'status': 200,
        'durationMs': 17,
      },
      context: const AppLogContext(requestId: 'req-1', traceId: 'trace-1'),
    );

    expect(path, 'memory://app/access.log');
    expect(
      writer.lastLine,
      endsWith('GET,/search,200,17,req-1,trace-1,cloud api request'),
    );
    expect(writer.lastLine, isNot(contains('action')));
    expect(writer.lastLine, isNot(contains('target')));
    expect(writer.lastLine, isNot(contains('requestId')));
    expect(writer.lastLine, isNot(contains('traceId')));
  });

  test('perf logs stay in event stream with required event fields', () async {
    final writer = _MemoryAppLogWriter();
    final service = AppLogService.forTesting(
      writer: writer,
      policy: AppLogPolicy(isRelease: false),
    );

    final path = await service.writeEvent(
      logType: AppLogType.perf,
      level: AppLogLevel.info,
      payload: const <String, dynamic>{'durationMs': 16},
      context: const AppLogContext(),
    );

    expect(path, 'memory://app/event.log');
    expect(writer.lastLine, endsWith(',perf_sample,ok,,,performance sample'));
    expect(writer.lastLine, isNot(contains('metric')));
  });

  test('message commas stay in the final delimited field', () async {
    final writer = _MemoryAppLogWriter();
    final service = AppLogService.forTesting(
      writer: writer,
      policy: AppLogPolicy(isRelease: false),
    );

    await service.writeEvent(
      logType: AppLogType.pageAccess,
      level: AppLogLevel.info,
      payload: const <String, dynamic>{'msg': 'open, with comma'},
      context: const AppLogContext(),
    );

    expect(writer.lastLine, endsWith(',page_access,ok,,,open, with comma'));
  });
}
