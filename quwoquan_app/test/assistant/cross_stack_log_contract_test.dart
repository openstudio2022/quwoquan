import 'dart:io';

import 'package:test/test.dart';

void main() {
  test('cross-stack log envelope includes canonical routing fields', () {
    final models = File(
      'lib/assistant/observability/logging/app_log_models.dart',
    );
    expect(models.existsSync(), isTrue);
    final text = models.readAsStringSync();
    for (final key in const <String>[
      'sourceDomain',
      'sourceService',
      'component',
      'target',
      'action',
      'sessionId',
      'pageVisitId',
      'traceId',
      'requestId',
      'turnId',
    ]) {
      expect(
        text.contains(key),
        isTrue,
        reason: 'missing canonical field: $key',
      );
    }
  });

  test(
    'app log context supports minimum cross-stack correlation identifiers',
    () {
      final service = File(
        'lib/assistant/observability/logging/app_log_service.dart',
      );
      expect(service.existsSync(), isTrue);
      final text = service.readAsStringSync();
      for (final key in const <String>[
        'sourceDomain',
        'sourceService',
        'component',
        'target',
        'action',
        'sessionId',
        'pageVisitId',
        'traceId',
        'requestId',
        '_defaultComponentFor',
        '_defaultTargetFor',
      ]) {
        expect(
          text.contains(key),
          isTrue,
          reason: 'missing context mapping: $key',
        );
      }
    },
  );

  test('new app log schema does not write removed current identifiers', () {
    final files = <File>[
      File('lib/assistant/observability/logging/app_log_models.dart'),
      File('lib/assistant/observability/logging/app_log_service.dart'),
      File('lib/assistant/observability/logging/app_trace_context_store.dart'),
    ];
    final text = files.map((file) => file.readAsStringSync()).join('\n');
    for (final key in const <String>[
      'currentLogType',
      'cloudRequestId',
      'journeyId',
      'spanId',
      'parentSpanId',
      'correlationId',
      'pythonJobId',
    ]) {
      expect(
        text.contains(key),
        isFalse,
        reason: 'removed field still exists: $key',
      );
    }
  });
}
