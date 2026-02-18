class AssistentCostRecord {
  const AssistentCostRecord({
    required this.runId,
    required this.traceId,
    required this.provider,
    required this.modelRef,
    required this.tokenUsage,
    required this.estimatedCostUsd,
    required this.timestamp,
  });

  final String runId;
  final String traceId;
  final String provider;
  final String modelRef;
  final int tokenUsage;
  final double estimatedCostUsd;
  final DateTime timestamp;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'runId': runId,
      'traceId': traceId,
      'provider': provider,
      'modelRef': modelRef,
      'tokenUsage': tokenUsage,
      'estimatedCostUsd': estimatedCostUsd,
      'timestamp': timestamp.toIso8601String(),
    };
  }
}

class AssistentCostSummary {
  const AssistentCostSummary({
    required this.totalRuns,
    required this.totalTokens,
    required this.totalCostUsd,
    required this.providerBreakdown,
  });

  final int totalRuns;
  final int totalTokens;
  final double totalCostUsd;
  final Map<String, double> providerBreakdown;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'totalRuns': totalRuns,
      'totalTokens': totalTokens,
      'totalCostUsd': totalCostUsd,
      'providerBreakdown': providerBreakdown,
    };
  }
}

class AssistentCostLedger {
  final List<AssistentCostRecord> _records = <AssistentCostRecord>[];

  Future<void> append(AssistentCostRecord record) async {
    _records.add(record);
  }

  Future<List<AssistentCostRecord>> listRecent({int limit = 100}) async {
    if (_records.length <= limit) {
      return List<AssistentCostRecord>.from(_records.reversed);
    }
    final start = _records.length - limit;
    return _records.sublist(start).reversed.toList(growable: false);
  }

  Future<AssistentCostSummary> summary() async {
    var tokens = 0;
    var cost = 0.0;
    final providers = <String, double>{};
    for (final record in _records) {
      tokens += record.tokenUsage;
      cost += record.estimatedCostUsd;
      providers[record.provider] = (providers[record.provider] ?? 0) + record.estimatedCostUsd;
    }
    return AssistentCostSummary(
      totalRuns: _records.length,
      totalTokens: tokens,
      totalCostUsd: cost,
      providerBreakdown: providers,
    );
  }
}

