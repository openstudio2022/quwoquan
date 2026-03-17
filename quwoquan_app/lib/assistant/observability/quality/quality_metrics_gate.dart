class QualityMetricsGateResult {
  const QualityMetricsGateResult({
    required this.totalRuns,
    required this.decisionParseSuccessRate,
    required this.renderFallbackRate,
    required this.heuristicFallbackRatio,
    required this.evidenceSatisfiedRuns,
    required this.evidenceSatisfiedRate,
    required this.freshnessSatisfiedRuns,
    required this.freshnessSatisfiedRate,
    required this.criticalSlotResolvedRuns,
    required this.criticalSlotResolvedRate,
  });

  final int totalRuns;
  final double decisionParseSuccessRate;
  final double renderFallbackRate;
  final double heuristicFallbackRatio;
  final int evidenceSatisfiedRuns;
  final double evidenceSatisfiedRate;
  final int freshnessSatisfiedRuns;
  final double freshnessSatisfiedRate;
  final int criticalSlotResolvedRuns;
  final double criticalSlotResolvedRate;
}

class QualityMetricsGate {
  const QualityMetricsGate._();

  static const double decisionParseSuccessThreshold = 0.995;
  static const double renderFallbackRateMax = 0.01;
  static const double heuristicFallbackRatioMax = 0.01;
  static const double evidenceSatisfiedRateMin = 0.95;
  static const double freshnessSatisfiedRateMin = 0.95;
  static const double criticalSlotResolvedRateMin = 0.95;

  static QualityMetricsGateResult evaluate(
    List<Map<String, dynamic>> structuredResponses,
  ) {
    if (structuredResponses.isEmpty) {
      return const QualityMetricsGateResult(
        totalRuns: 0,
        decisionParseSuccessRate: 0,
        renderFallbackRate: 1,
        heuristicFallbackRatio: 1,
        evidenceSatisfiedRuns: 0,
        evidenceSatisfiedRate: 1,
        freshnessSatisfiedRuns: 0,
        freshnessSatisfiedRate: 1,
        criticalSlotResolvedRuns: 0,
        criticalSlotResolvedRate: 1,
      );
    }
    var parseSuccess = 0;
    var renderFallback = 0;
    var heuristicFallback = 0;
    var evidenceSatisfied = 0;
    var freshnessSatisfied = 0;
    var criticalSlotResolved = 0;
    var evidenceObservedRuns = 0;
    var freshnessObservedRuns = 0;
    var slotObservedRuns = 0;
    for (final item in structuredResponses) {
      final quality =
          (item['qualityMetrics'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{};
      if (quality['decisionParseSuccess'] == true) parseSuccess += 1;
      if (quality['renderFallback'] == true) renderFallback += 1;
      if (quality['heuristicFallbackUsed'] == true) heuristicFallback += 1;
      if (quality.containsKey('evidenceSufficient')) {
        evidenceObservedRuns += 1;
        if (quality['evidenceSufficient'] == true) evidenceSatisfied += 1;
      }
      if (quality.containsKey('freshnessSatisfied')) {
        freshnessObservedRuns += 1;
        if (quality['freshnessSatisfied'] == true) freshnessSatisfied += 1;
      }
      if (quality.containsKey('criticalSlotsResolved')) {
        slotObservedRuns += 1;
        if (quality['criticalSlotsResolved'] == true) criticalSlotResolved += 1;
      }
    }
    final total = structuredResponses.length.toDouble();
    return QualityMetricsGateResult(
      totalRuns: structuredResponses.length,
      decisionParseSuccessRate: parseSuccess / total,
      renderFallbackRate: renderFallback / total,
      heuristicFallbackRatio: heuristicFallback / total,
      evidenceSatisfiedRuns: evidenceObservedRuns,
      evidenceSatisfiedRate: evidenceObservedRuns == 0
          ? 1
          : evidenceSatisfied / evidenceObservedRuns,
      freshnessSatisfiedRuns: freshnessObservedRuns,
      freshnessSatisfiedRate: freshnessObservedRuns == 0
          ? 1
          : freshnessSatisfied / freshnessObservedRuns,
      criticalSlotResolvedRuns: slotObservedRuns,
      criticalSlotResolvedRate: slotObservedRuns == 0
          ? 1
          : criticalSlotResolved / slotObservedRuns,
    );
  }

  static bool pass(QualityMetricsGateResult result) {
    return result.totalRuns > 0 &&
        result.decisionParseSuccessRate >= decisionParseSuccessThreshold &&
        result.renderFallbackRate < renderFallbackRateMax &&
        result.heuristicFallbackRatio < heuristicFallbackRatioMax &&
        (result.evidenceSatisfiedRuns == 0 ||
            result.evidenceSatisfiedRate >= evidenceSatisfiedRateMin) &&
        (result.freshnessSatisfiedRuns == 0 ||
            result.freshnessSatisfiedRate >= freshnessSatisfiedRateMin) &&
        (result.criticalSlotResolvedRuns == 0 ||
            result.criticalSlotResolvedRate >= criticalSlotResolvedRateMin);
  }
}
