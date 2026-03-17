import 'package:quwoquan_app/assistant/observability/quality/quality_metrics_gate.dart';
import 'package:test/test.dart';

void main() {
  group('Quality metrics gate', () {
    test('passes when parse/fallback/evidence/freshness/slots all meet thresholds', () {
      final responses = List<Map<String, dynamic>>.generate(
        1000,
        (_) => <String, dynamic>{
          'qualityMetrics': <String, dynamic>{
            'decisionParseSuccess': true,
            'renderFallback': false,
            'heuristicFallbackUsed': false,
            'evidenceSufficient': true,
            'freshnessSatisfied': true,
            'criticalSlotsResolved': true,
          },
        },
      );
      responses[0]['qualityMetrics'] = <String, dynamic>{
        'decisionParseSuccess': false,
        'renderFallback': false,
        'heuristicFallbackUsed': false,
        'evidenceSufficient': true,
        'freshnessSatisfied': true,
        'criticalSlotsResolved': true,
      };

      final result = QualityMetricsGate.evaluate(responses);

      expect(
        result.decisionParseSuccessRate,
        greaterThanOrEqualTo(QualityMetricsGate.decisionParseSuccessThreshold),
      );
      expect(
        result.renderFallbackRate,
        lessThan(QualityMetricsGate.renderFallbackRateMax),
      );
      expect(
        result.heuristicFallbackRatio,
        lessThan(QualityMetricsGate.heuristicFallbackRatioMax),
      );
      expect(
        result.evidenceSatisfiedRate,
        greaterThanOrEqualTo(QualityMetricsGate.evidenceSatisfiedRateMin),
      );
      expect(
        result.freshnessSatisfiedRate,
        greaterThanOrEqualTo(QualityMetricsGate.freshnessSatisfiedRateMin),
      );
      expect(
        result.criticalSlotResolvedRate,
        greaterThanOrEqualTo(QualityMetricsGate.criticalSlotResolvedRateMin),
      );
      expect(QualityMetricsGate.pass(result), isTrue);
    });

    test('fails when fallback ratio exceeds threshold', () {
      final responses = List<Map<String, dynamic>>.generate(
        100,
        (index) => <String, dynamic>{
          'qualityMetrics': <String, dynamic>{
            'decisionParseSuccess': true,
            'renderFallback': index < 2,
            'heuristicFallbackUsed': false,
            'evidenceSufficient': true,
            'freshnessSatisfied': true,
            'criticalSlotsResolved': true,
          },
        },
      );

      final result = QualityMetricsGate.evaluate(responses);

      expect(
        result.renderFallbackRate,
        greaterThanOrEqualTo(QualityMetricsGate.renderFallbackRateMax),
      );
      expect(QualityMetricsGate.pass(result), isFalse);
    });

    test('fails when evidence or freshness quality regresses', () {
      final responses = List<Map<String, dynamic>>.generate(
        100,
        (index) => <String, dynamic>{
          'qualityMetrics': <String, dynamic>{
            'decisionParseSuccess': true,
            'renderFallback': false,
            'heuristicFallbackUsed': false,
            'evidenceSufficient': index >= 10,
            'freshnessSatisfied': index >= 10,
            'criticalSlotsResolved': true,
          },
        },
      );

      final result = QualityMetricsGate.evaluate(responses);

      expect(
        result.evidenceSatisfiedRate,
        lessThan(QualityMetricsGate.evidenceSatisfiedRateMin),
      );
      expect(
        result.freshnessSatisfiedRate,
        lessThan(QualityMetricsGate.freshnessSatisfiedRateMin),
      );
      expect(QualityMetricsGate.pass(result), isFalse);
    });
  });
}
