/// 从 timeline 消息松散字段解析 `uiUsageStats`（供页面壳使用，避免在扫描路径内写 `Map<String, dynamic>`）。
Map<String, dynamic> assistantUiUsageStatsMapFromMessageField(Object? raw) {
  if (raw is! Map) {
    return const <String, dynamic>{};
  }
  return Map<String, dynamic>.from(
    raw.map((k, v) => MapEntry(k.toString(), v)),
  );
}

/// 与助手消息 `uiUsageStats` 协议 Map 对齐的只读视图（用于 journey / UI，不参与持久化编码）。
final class AssistantUsageLedgerEntryViewData {
  const AssistantUsageLedgerEntryViewData({
    this.totalTokens = 0,
    this.inputTokens = 0,
    this.outputTokens = 0,
    this.source = '',
    this.modelRef = '',
  });

  final int totalTokens;
  final int inputTokens;
  final int outputTokens;
  final String source;
  final String modelRef;

  factory AssistantUsageLedgerEntryViewData.fromMap(Map<String, dynamic> m) {
    return AssistantUsageLedgerEntryViewData(
      totalTokens: _usageInt(m['totalTokens'] ?? m['tokenUsage']),
      inputTokens: _usageInt(m['inputTokens']),
      outputTokens: _usageInt(m['outputTokens']),
      source: (m['source'] as String?)?.trim() ?? '',
      modelRef: (m['modelRef'] ?? m['model'] ?? '').toString().trim(),
    );
  }
}

final class AssistantUiUsageStatsViewData {
  const AssistantUiUsageStatsViewData({
    this.runModelCallCount = 0,
    this.runTotalTokens = 0,
    this.runMaxTokensPerCall = 0,
    this.sessionModelCallCount = 0,
    this.sessionTotalTokens = 0,
    this.sessionMaxTokensPerCall = 0,
    this.runLedger = const <AssistantUsageLedgerEntryViewData>[],
    this.sessionLedger = const <AssistantUsageLedgerEntryViewData>[],
  });

  final int runModelCallCount;
  final int runTotalTokens;
  final int runMaxTokensPerCall;
  final int sessionModelCallCount;
  final int sessionTotalTokens;
  final int sessionMaxTokensPerCall;
  final List<AssistantUsageLedgerEntryViewData> runLedger;
  final List<AssistantUsageLedgerEntryViewData> sessionLedger;

  static const AssistantUiUsageStatsViewData empty =
      AssistantUiUsageStatsViewData();

  bool get isEmpty =>
      runModelCallCount == 0 &&
      runTotalTokens == 0 &&
      runMaxTokensPerCall == 0 &&
      sessionModelCallCount == 0 &&
      sessionTotalTokens == 0 &&
      sessionMaxTokensPerCall == 0 &&
      runLedger.isEmpty &&
      sessionLedger.isEmpty;

  factory AssistantUiUsageStatsViewData.fromProtocolMap(
    Map<String, dynamic> m,
  ) {
    if (m.isEmpty) return AssistantUiUsageStatsViewData.empty;

    final runCalls = _usageInt(
      m['runModelCallCount'] ?? m['modelCallCount'],
    );
    final runTokens = _usageInt(m['runTotalTokens'] ?? m['totalTokens']);
    final runMax = _usageInt(
      m['runMaxTokensPerCall'] ?? m['maxTokensPerCall'],
    );
    final runLedgerRaw =
        (m['runUsageLedger'] ?? m['usageLedger']) as List? ?? const [];
    final runLedger = _parseLedger(runLedgerRaw);

    final session = (m['sessionUsageStats'] as Map?)?.cast<String, dynamic>();
    final sessionCalls = session != null
        ? _usageInt(session['modelCallCount'])
        : _usageInt(
            m['cumulativeModelCallCount'] ?? m['sessionModelCallCount'],
          );
    final sessionTokens = session != null
        ? _usageInt(session['totalTokens'])
        : _usageInt(m['cumulativeTotalTokens'] ?? m['sessionTotalTokens']);
    final sessionMax = session != null
        ? _usageInt(session['maxTokensPerCall'])
        : _usageInt(
            m['cumulativeMaxTokensPerCall'] ?? m['sessionMaxTokensPerCall'],
          );
    final sessionLedgerRaw = session != null
        ? (session['usageLedger'] as List? ?? const [])
        : (m['cumulativeUsageLedger'] as List? ?? const []);
    final sessionLedger = _parseLedger(sessionLedgerRaw);

    return AssistantUiUsageStatsViewData(
      runModelCallCount: runCalls,
      runTotalTokens: runTokens,
      runMaxTokensPerCall: runMax,
      sessionModelCallCount: sessionCalls,
      sessionTotalTokens: sessionTokens,
      sessionMaxTokensPerCall: sessionMax,
      runLedger: runLedger,
      sessionLedger: sessionLedger,
    );
  }
}

List<AssistantUsageLedgerEntryViewData> _parseLedger(List<dynamic> raw) {
  return raw
      .whereType<Map>()
      .map(
        (e) => AssistantUsageLedgerEntryViewData.fromMap(
          e.cast<String, dynamic>(),
        ),
      )
      .toList(growable: false);
}

int _usageInt(Object? value) {
  if (value is num) {
    final n = value.toInt();
    return n < 0 ? 0 : n;
  }
  final parsed = int.tryParse(value?.toString() ?? '');
  if (parsed == null || parsed < 0) return 0;
  return parsed;
}
