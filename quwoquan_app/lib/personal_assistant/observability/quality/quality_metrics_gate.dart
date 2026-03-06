class QualityMetricsGateResult {
  const QualityMetricsGateResult({
    required this.totalRuns,
    required this.decisionParseSuccessRate,
    required this.renderFallbackRate,
    required this.heuristicFallbackRatio,
  });

  final int totalRuns;
  final double decisionParseSuccessRate;
  final double renderFallbackRate;
  final double heuristicFallbackRatio;
}

class QualityMetricsGate {
  const QualityMetricsGate._();

  static const double decisionParseSuccessThreshold = 0.995;
  static const double renderFallbackRateMax = 0.01;
  static const double heuristicFallbackRatioMax = 0.01;

  static QualityMetricsGateResult evaluate(
    List<Map<String, dynamic>> structuredResponses,
  ) {
    if (structuredResponses.isEmpty) {
      return const QualityMetricsGateResult(
        totalRuns: 0,
        decisionParseSuccessRate: 0,
        renderFallbackRate: 1,
        heuristicFallbackRatio: 1,
      );
    }
    var parseSuccess = 0;
    var renderFallback = 0;
    var heuristicFallback = 0;
    for (final item in structuredResponses) {
      final quality =
          (item['qualityMetrics'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{};
      if (quality['decisionParseSuccess'] == true) parseSuccess += 1;
      if (quality['renderFallback'] == true) renderFallback += 1;
      if (quality['heuristicFallbackUsed'] == true) heuristicFallback += 1;
    }
    final total = structuredResponses.length.toDouble();
    return QualityMetricsGateResult(
      totalRuns: structuredResponses.length,
      decisionParseSuccessRate: parseSuccess / total,
      renderFallbackRate: renderFallback / total,
      heuristicFallbackRatio: heuristicFallback / total,
    );
  }

  static bool pass(QualityMetricsGateResult result) {
    return result.totalRuns > 0 &&
        result.decisionParseSuccessRate >= decisionParseSuccessThreshold &&
        result.renderFallbackRate < renderFallbackRateMax &&
        result.heuristicFallbackRatio < heuristicFallbackRatioMax;
  }
}
