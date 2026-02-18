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
  });

  final String query;
  final List<String> requestedCapabilities;
  final Map<String, dynamic> contextScopeHint;
  final String privacyProfile;
  final Map<String, dynamic> privacyPolicy;
  final String? providerHint;
  final int round;
  final int maxItems;
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

