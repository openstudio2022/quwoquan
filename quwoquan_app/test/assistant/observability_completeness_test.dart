import 'dart:io';

import 'package:test/test.dart';

void main() {
  test('phase owner observability payload includes required fields', () {
    final file = File(
      'lib/assistant/orchestration/pipelines/observability_payload_builder.dart',
    );
    expect(file.existsSync(), isTrue);
    final text = file.readAsStringSync();
    for (final key in const <String>[
      'contextSlots',
      'fillActions',
      'missingCriticalSlots',
      'answerEligibility',
      'selfCheck',
      'diagnostics',
      'webEvidencePacks',
      'webEvidenceGate',
      'webPipeline',
      'qualityMetrics',
    ]) {
      expect(
        text.contains(key),
        isTrue,
        reason: 'missing observability key: $key',
      );
    }
  });
}
