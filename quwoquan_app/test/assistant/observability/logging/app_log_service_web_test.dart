import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_models.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_policy.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_service.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_log_writer.dart';

class _MemoryAppLogWriter extends AppLogWriter {
  Map<String, dynamic>? lastPayload;

  @override
  Future<String> appendJsonLine({
    required String subDirectory,
    required String fileName,
    required Map<String, dynamic> payload,
    DateTime? at,
  }) async {
    lastPayload = payload;
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

      expect(path, 'memory://errors/errors.jsonl');
      final platform = writer.lastPayload?['platform'];
      expect(platform, isNotEmpty);
      if (kIsWeb) {
        expect(platform, 'web');
      }
    },
  );

  test(
    'default writer no-ops on web instead of touching dart:io namespace',
    () async {
      final path = await AppLogWriter().appendJsonLine(
        subDirectory: 'errors',
        fileName: 'events.jsonl',
        payload: const <String, dynamic>{'event': 'web_writer_smoke'},
      );

      if (kIsWeb) {
        expect(path, 'web://app-log/errors/events.jsonl');
      }
    },
  );
}
