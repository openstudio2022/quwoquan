/// 学习 / Dev 回放证据包（C6）。对齐 controller `_storeAssistantReplayRecord`。
class AssistantReplayRecord {
  const AssistantReplayRecord({
    required this.messageId,
    this.runId = '',
    this.traceId = '',
    this.query = '',
    this.answer = '',
    this.displayPlainText = '',
    this.runArtifacts = const <String, dynamic>{},
    this.createdAt = '',
    this.uiReferences = const <Map<String, dynamic>>[],
    this.uiUsageStats = const <String, dynamic>{},
    this.queryPlan = const <String, dynamic>{},
    this.policyDecision = const <String, dynamic>{},
    this.roundTraces = const <Map<String, dynamic>>[],
    this.webSearchDiagnostics = const <String, dynamic>{},
  });

  final String messageId;
  final String runId;
  final String traceId;
  final String query;
  final String answer;
  final String displayPlainText;
  final Map<String, dynamic> runArtifacts;
  final String createdAt;
  final List<Map<String, dynamic>> uiReferences;
  final Map<String, dynamic> uiUsageStats;
  final Map<String, dynamic> queryPlan;
  final Map<String, dynamic> policyDecision;
  final List<Map<String, dynamic>> roundTraces;
  final Map<String, dynamic> webSearchDiagnostics;

  factory AssistantReplayRecord.fromJson(Map<String, dynamic> json) {
    final refs = (json['uiReferences'] as List?)
            ?.whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final rounds = (json['roundTraces'] as List?)
            ?.whereType<Map>()
            .map((e) => e.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return AssistantReplayRecord(
      messageId: (json['messageId'] ?? '').toString(),
      runId: (json['runId'] ?? '').toString(),
      traceId: (json['traceId'] ?? '').toString(),
      query: (json['query'] ?? '').toString(),
      answer: (json['answer'] ?? '').toString(),
      displayPlainText: (json['displayPlainText'] ?? '').toString(),
      runArtifacts: (json['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      createdAt: (json['createdAt'] ?? '').toString(),
      uiReferences: refs,
      uiUsageStats:
          (json['uiUsageStats'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      queryPlan:
          (json['queryPlan'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      policyDecision:
          (json['policyDecision'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
      roundTraces: rounds,
      webSearchDiagnostics:
          (json['webSearchDiagnostics'] as Map?)?.cast<String, dynamic>() ??
              const <String, dynamic>{},
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'messageId': messageId,
      'runId': runId,
      'traceId': traceId,
      'query': query,
      'answer': answer,
      'displayPlainText': displayPlainText,
      'runArtifacts': runArtifacts,
      'createdAt': createdAt,
      'uiReferences': uiReferences,
      'uiUsageStats': uiUsageStats,
      'queryPlan': queryPlan,
      'policyDecision': policyDecision,
      'roundTraces': roundTraces,
      'webSearchDiagnostics': webSearchDiagnostics,
    };
  }
}
