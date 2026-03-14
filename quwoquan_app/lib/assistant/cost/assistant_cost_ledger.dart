class AssistantCostRecord {
  const AssistantCostRecord({
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

class AssistantCostSummary {
  const AssistantCostSummary({
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

class AssistantCostLedger {
  final List<AssistantCostRecord> _records = <AssistantCostRecord>[];

  Future<void> append(AssistantCostRecord record) async {
    _records.add(record);
  }

  Future<List<AssistantCostRecord>> listRecent({int limit = 100}) async {
    if (_records.length <= limit) {
      return List<AssistantCostRecord>.from(_records.reversed);
    }
    final start = _records.length - limit;
    return _records.sublist(start).reversed.toList(growable: false);
  }

  Future<AssistantCostSummary> summary() async {
    var tokens = 0;
    var cost = 0.0;
    final providers = <String, double>{};
    for (final record in _records) {
      tokens += record.tokenUsage;
      cost += record.estimatedCostUsd;
      providers[record.provider] =
          (providers[record.provider] ?? 0) + record.estimatedCostUsd;
    }
    return AssistantCostSummary(
      totalRuns: _records.length,
      totalTokens: tokens,
      totalCostUsd: cost,
      providerBreakdown: providers,
    );
  }
}

class AssistantTokenUsage {
  const AssistantTokenUsage({
    required this.promptTokens,
    required this.completionTokens,
  });

  final int promptTokens;
  final int completionTokens;

  int get totalTokens => promptTokens + completionTokens;
}

class AssistantTokenMeter {
  const AssistantTokenMeter();

  AssistantTokenUsage estimate({
    required String inputText,
    required String outputText,
  }) {
    final prompt = _estimateTextTokens(inputText);
    final completion = _estimateTextTokens(outputText);
    return AssistantTokenUsage(
      promptTokens: prompt,
      completionTokens: completion,
    );
  }

  int _estimateTextTokens(String text) {
    final cleaned = text.trim();
    if (cleaned.isEmpty) return 0;
    final estimated = (cleaned.length / 4).ceil();
    return estimated < 1 ? 1 : estimated;
  }
}
