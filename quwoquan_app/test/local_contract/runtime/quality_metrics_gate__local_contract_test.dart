import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/quality_metrics_gate.dart';

void main() {
  test('empty quality sample is explicitly not releasable', () {
    final result = QualityMetricsGate.evaluate(const <Map<String, dynamic>>[]);

    expect(result.totalRuns, 0);
    expect(result.renderFallbackRate, 1);
    expect(QualityMetricsGate.pass(result), isFalse);
  });

  test('quality sample aggregates optional evidence and slot dimensions', () {
    final result = QualityMetricsGate.evaluate(<Map<String, dynamic>>[
      <String, dynamic>{
        'qualityMetrics': <String, dynamic>{
          'decisionParseSuccess': true,
          'renderFallback': false,
          'heuristicFallbackUsed': false,
          'evidenceSufficient': true,
          'freshnessSatisfied': true,
          'criticalSlotsResolved': true,
        },
      },
      <String, dynamic>{'qualityMetrics': <String, dynamic>{}},
    ]);

    expect(result.totalRuns, 2);
    expect(result.decisionParseSuccessRate, 0.5);
    expect(result.evidenceSatisfiedRuns, 1);
    expect(result.evidenceSatisfiedRate, 1);
    expect(result.freshnessSatisfiedRuns, 1);
    expect(result.criticalSlotResolvedRuns, 1);
    expect(QualityMetricsGate.pass(result), isFalse);
  });

  test('fully passing samples satisfy every canonical threshold', () {
    final result = QualityMetricsGate.evaluate(<Map<String, dynamic>>[
      <String, dynamic>{
        'qualityMetrics': <String, dynamic>{
          'decisionParseSuccess': true,
          'renderFallback': false,
          'heuristicFallbackUsed': false,
        },
      },
    ]);

    expect(result.evidenceSatisfiedRate, 1);
    expect(result.freshnessSatisfiedRate, 1);
    expect(result.criticalSlotResolvedRate, 1);
    expect(QualityMetricsGate.pass(result), isTrue);
  });
}
