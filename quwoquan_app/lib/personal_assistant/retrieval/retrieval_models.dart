class AssistentRetrievalRequest {
  const AssistentRetrievalRequest({
    required this.query,
    this.requestedCapabilities = const <String>[],
    this.contextScopeHint = const <String, dynamic>{},
    this.privacyProfile = 'default',
    this.privacyPolicy = const <String, dynamic>{},
    this.providerHint,
    this.round = 1,
    this.maxItems = 6,
    this.queryVariants = const <String>[],
    this.previousRoundTraces = const <Map<String, dynamic>>[],
    this.inputIssues = const <String>[],
  });

  final String query;
  final List<String> requestedCapabilities;
  final Map<String, dynamic> contextScopeHint;
  final String privacyProfile;
  final Map<String, dynamic> privacyPolicy;
  final String? providerHint;
  final int round;
  final int maxItems;
  /// Layer 1 LLM 生成的多路查询变体，供 retrieval_service 并发执行
  final List<String> queryVariants;
  /// 历史轮次结果，供 Layer 3 反思重写时追溯失败原因
  final List<Map<String, dynamic>> previousRoundTraces;
  /// Layer 1 诊断的输入问题类型（pinyin_input/no_location 等）
  final List<String> inputIssues;
}

class AssistentRetrievalItem {
  const AssistentRetrievalItem({
    required this.content,
    required this.sourceType,
    required this.sourceId,
    this.relevance = 0.0,
    this.timestamp,
    this.metadata = const <String, dynamic>{},
  });

  final String content;
  final String sourceType;
  final String sourceId;
  final double relevance;
  final DateTime? timestamp;
  final Map<String, dynamic> metadata;
}

class AssistentRetrievalResult {
  const AssistentRetrievalResult({
    required this.success,
    required this.message,
    this.items = const <AssistentRetrievalItem>[],
    this.providersUsed = const <String>[],
    this.coverageScore = 0.0,
    this.conflictScore = 0.0,
    this.degraded = false,
    this.errorCode = '',
    this.nextRoundRecommended = false,
    this.queryPlan = const <String, dynamic>{},
    this.policyDecision = const <String, dynamic>{},
    this.roundTraces = const <Map<String, dynamic>>[],
    this.qualityScore = 0.0,
    this.authorityScore = 0.0,
    this.authoritativeCount = 0,
    this.totalReferencesSearched = 0,
    this.allReferences = const <Map<String, dynamic>>[],
  });

  final bool success;
  final String message;
  final List<AssistentRetrievalItem> items;
  final List<String> providersUsed;
  final double coverageScore;
  final double conflictScore;
  final bool degraded;
  final String errorCode;
  final bool nextRoundRecommended;
  final Map<String, dynamic> queryPlan;
  final Map<String, dynamic> policyDecision;
  final List<Map<String, dynamic>> roundTraces;
  /// Layer 3 综合质量评分（权威0.4 + 时效0.35 + 覆盖0.25）
  final double qualityScore;
  /// 权威性得分
  final double authorityScore;
  /// 命中权威域的结果数量
  final int authoritativeCount;
  /// 本次搜索总资料数（含非权威）
  final int totalReferencesSearched;
  /// 全量参考资料列表（含 cited 标记），供 Layer 5 展示
  final List<Map<String, dynamic>> allReferences;

  String toAnswerSummary() {
    if (items.isEmpty) return message;
    final lines = items
        .take(3)
        .map((item) => '[${item.sourceType}] ${item.content}')
        .join('\n');
    return '检索结果：$lines';
  }
}

class AssistentRetrievalRouteDecision {
  const AssistentRetrievalRouteDecision({
    required this.providerSequence,
    required this.capabilitySequence,
    required this.maxRounds,
    this.decisionReasons = const <String, dynamic>{},
  });

  final List<String> providerSequence;
  final List<String> capabilitySequence;
  final int maxRounds;
  final Map<String, dynamic> decisionReasons;
}

