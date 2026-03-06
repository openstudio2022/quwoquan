import 'dart:io';

import 'package:test/test.dart';

void main() {
  test('cross-stack log envelope includes canonical routing fields', () {
    final models = File(
      'lib/personal_assistant/observability/logging/app_log_models.dart',
    );
    expect(models.existsSync(), isTrue);
    final text = models.readAsStringSync();
    for (final key in const <String>[
      'legacyLogType',
      'sourceDomain',
      'sourceService',
      'component',
      'target',
      'action',
      'parentSpanId',
      'cloudRequestId',
      'pythonJobId',
      'correlationId',
      'turnId',
    ]) {
      expect(text.contains(key), isTrue, reason: 'missing canonical field: $key');
    }
  });

  test('app log context supports cross-stack correlation identifiers', () {
    final service = File(
      'lib/personal_assistant/observability/logging/app_log_service.dart',
    );
    expect(service.existsSync(), isTrue);
    final text = service.readAsStringSync();
    for (final key in const <String>[
      'sourceDomain',
      'sourceService',
      'component',
      'target',
      'action',
      'correlationId',
      'parentSpanId',
      'cloudRequestId',
      'pythonJobId',
      '_defaultComponentFor',
      '_defaultTargetFor',
    ]) {
      expect(text.contains(key), isTrue, reason: 'missing context mapping: $key');
    }
  });
}
