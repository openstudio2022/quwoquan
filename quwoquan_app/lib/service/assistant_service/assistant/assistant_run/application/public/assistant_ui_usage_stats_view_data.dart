/// 与助手消息 `uiUsageStats` 协议 Map 对齐的只读视图（Row typed 字段与
/// journey / UI 消费同源；Map 编解码只发生在 Codec 磁盘/协议边界）。
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
      totalTokens: _usageInt(m['totalTokens']),
      inputTokens: _usageInt(m['inputTokens']),
      outputTokens: _usageInt(m['outputTokens']),
      source: (m['source'] as String?)?.trim() ?? '',
      modelRef: (m['modelRef'] ?? '').toString().trim(),
    );
  }

  Map<String, dynamic> toMap() => <String, dynamic>{
        'totalTokens': totalTokens,
        'inputTokens': inputTokens,
        'outputTokens': outputTokens,
        'source': source,
        'modelRef': modelRef,
      };
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

    final runCalls = _usageInt(m['runModelCallCount']);
    final runTokens = _usageInt(m['runTotalTokens']);
    final runMax = _usageInt(m['runMaxTokensPerCall']);
    final runLedgerRaw = m['runUsageLedger'] as List? ?? const [];
    final runLedger = _parseLedger(runLedgerRaw);

    final session = (m['sessionUsageStats'] as Map?)?.cast<String, dynamic>();
    final sessionCalls = session != null
        ? _usageInt(session['modelCallCount'])
        : _usageInt(m['cumulativeModelCallCount']);
    final sessionTokens = session != null
        ? _usageInt(session['totalTokens'])
        : _usageInt(m['cumulativeTotalTokens']);
    final sessionMax = session != null
        ? _usageInt(session['maxTokensPerCall'])
        : _usageInt(m['cumulativeMaxTokensPerCall']);
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

  /// 协议 Map 序列化出口（canonical 形态；[fromProtocolMap] 可无损读回）。
  Map<String, dynamic> toProtocolMap() {
    if (isEmpty) return const <String, dynamic>{};
    return <String, dynamic>{
      'runModelCallCount': runModelCallCount,
      'runTotalTokens': runTotalTokens,
      'runMaxTokensPerCall': runMaxTokensPerCall,
      if (runLedger.isNotEmpty)
        'runUsageLedger': runLedger
            .map((entry) => entry.toMap())
            .toList(growable: false),
      'sessionUsageStats': <String, dynamic>{
        'modelCallCount': sessionModelCallCount,
        'totalTokens': sessionTotalTokens,
        'maxTokensPerCall': sessionMaxTokensPerCall,
        if (sessionLedger.isNotEmpty)
          'usageLedger': sessionLedger
              .map((entry) => entry.toMap())
              .toList(growable: false),
      },
    };
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
