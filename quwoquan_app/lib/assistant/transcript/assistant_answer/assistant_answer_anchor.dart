/// 助手回答的运行锚点（C3）。不等于完整持久化 turn。
class AssistantAnswerAnchor {
  const AssistantAnswerAnchor({
    this.runId = '',
    this.traceId = '',
    this.sourceQuery = '',
    this.templateVersionUsed = '',
    this.phaseOneRoutingDiagnostics = const <String, dynamic>{},
    this.degraded = false,
    this.qualityMetrics = const <String, dynamic>{},
    this.heuristicFallbackUsed = false,
    this.domainId = '',
  });

  final String runId;
  final String traceId;
  final String sourceQuery;
  final String templateVersionUsed;
  final Map<String, dynamic> phaseOneRoutingDiagnostics;
  final bool degraded;
  final Map<String, dynamic> qualityMetrics;
  final bool heuristicFallbackUsed;
  final String domainId;

  AssistantAnswerAnchor copyWith({
    String? runId,
    String? traceId,
    String? sourceQuery,
    String? templateVersionUsed,
    Map<String, dynamic>? phaseOneRoutingDiagnostics,
    bool? degraded,
    Map<String, dynamic>? qualityMetrics,
    bool? heuristicFallbackUsed,
    String? domainId,
  }) {
    return AssistantAnswerAnchor(
      runId: runId ?? this.runId,
      traceId: traceId ?? this.traceId,
      sourceQuery: sourceQuery ?? this.sourceQuery,
      templateVersionUsed: templateVersionUsed ?? this.templateVersionUsed,
      phaseOneRoutingDiagnostics:
          phaseOneRoutingDiagnostics ?? this.phaseOneRoutingDiagnostics,
      degraded: degraded ?? this.degraded,
      qualityMetrics: qualityMetrics ?? this.qualityMetrics,
      heuristicFallbackUsed:
          heuristicFallbackUsed ?? this.heuristicFallbackUsed,
      domainId: domainId ?? this.domainId,
    );
  }
}
