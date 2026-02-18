class AssistentInteractionEvent {
  const AssistentInteractionEvent({
    required this.eventId,
    required this.runId,
    required this.traceId,
    required this.userId,
    required this.sessionId,
    required this.pageType,
    required this.domainId,
    required this.queryText,
    required this.answerText,
    required this.userTags,
    required this.durationMs,
    required this.explicitThumb,
    required this.explicitReasonCodes,
    required this.copiedAnswer,
    required this.sharedAnswer,
    required this.favoritedAnswer,
    required this.interrupted,
    required this.createdAt,
    this.feedbackTargetMessageId = '',
    this.correctionText = '',
  });

  final String eventId;
  final String runId;
  final String traceId;
  final String userId;
  final String sessionId;
  final String pageType;
  final String domainId;
  final String queryText;
  final String answerText;
  final List<String> userTags;
  final int durationMs;
  final String explicitThumb;
  final List<String> explicitReasonCodes;
  final bool copiedAnswer;
  final bool sharedAnswer;
  final bool favoritedAnswer;
  final bool interrupted;
  final DateTime createdAt;
  final String feedbackTargetMessageId;
  final String correctionText;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'eventId': eventId,
      'runId': runId,
      'traceId': traceId,
      'userId': userId,
      'sessionId': sessionId,
      'pageType': pageType,
      'domainId': domainId,
      'queryText': queryText,
      'answerText': answerText,
      'userTags': userTags,
      'durationMs': durationMs,
      'explicitThumb': explicitThumb,
      'explicitReasonCodes': explicitReasonCodes,
      'copiedAnswer': copiedAnswer,
      'sharedAnswer': sharedAnswer,
      'favoritedAnswer': favoritedAnswer,
      'interrupted': interrupted,
      'createdAt': createdAt.toIso8601String(),
      'feedbackTargetMessageId': feedbackTargetMessageId,
      'correctionText': correctionText,
    };
  }

  factory AssistentInteractionEvent.fromJson(Map<String, dynamic> json) {
    return AssistentInteractionEvent(
      eventId: (json['eventId'] as String?) ?? '',
      runId: (json['runId'] as String?) ?? '',
      traceId: (json['traceId'] as String?) ?? '',
      userId: (json['userId'] as String?) ?? '',
      sessionId: (json['sessionId'] as String?) ?? '',
      pageType: (json['pageType'] as String?) ?? 'chat',
      domainId: (json['domainId'] as String?) ?? 'general',
      queryText: (json['queryText'] as String?) ?? '',
      answerText: (json['answerText'] as String?) ?? '',
      userTags: (json['userTags'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      durationMs: (json['durationMs'] as int?) ?? 0,
      explicitThumb: (json['explicitThumb'] as String?) ?? 'none',
      explicitReasonCodes: (json['explicitReasonCodes'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      copiedAnswer: json['copiedAnswer'] == true,
      sharedAnswer: json['sharedAnswer'] == true,
      favoritedAnswer: json['favoritedAnswer'] == true,
      interrupted: json['interrupted'] == true,
      createdAt: DateTime.tryParse((json['createdAt'] as String?) ?? '') ?? DateTime.now(),
      feedbackTargetMessageId: (json['feedbackTargetMessageId'] as String?) ?? '',
      correctionText: (json['correctionText'] as String?) ?? '',
    );
  }
}

class AssistentInteractionMetricScore {
  const AssistentInteractionMetricScore({
    required this.scoreId,
    required this.eventId,
    required this.userId,
    required this.domainId,
    required this.metricId,
    required this.scoreValue,
    required this.scoreSource,
    required this.createdAt,
  });

  final String scoreId;
  final String eventId;
  final String userId;
  final String domainId;
  final String metricId;
  final double scoreValue;
  final String scoreSource;
  final DateTime createdAt;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'scoreId': scoreId,
      'eventId': eventId,
      'userId': userId,
      'domainId': domainId,
      'metricId': metricId,
      'scoreValue': scoreValue,
      'scoreSource': scoreSource,
      'createdAt': createdAt.toIso8601String(),
    };
  }

  factory AssistentInteractionMetricScore.fromJson(Map<String, dynamic> json) {
    return AssistentInteractionMetricScore(
      scoreId: (json['scoreId'] as String?) ?? '',
      eventId: (json['eventId'] as String?) ?? '',
      userId: (json['userId'] as String?) ?? '',
      domainId: (json['domainId'] as String?) ?? 'general',
      metricId: (json['metricId'] as String?) ?? '',
      scoreValue: (json['scoreValue'] as num?)?.toDouble() ?? 0.0,
      scoreSource: (json['scoreSource'] as String?) ?? 'implicit',
      createdAt: DateTime.tryParse((json['createdAt'] as String?) ?? '') ?? DateTime.now(),
    );
  }
}

class AssistentScoreAggregate {
  const AssistentScoreAggregate({
    required this.bucketDate,
    required this.scopeId,
    required this.domainId,
    required this.metricId,
    required this.scoreAvg,
    required this.sampleCount,
  });

  final String bucketDate;
  final String scopeId;
  final String domainId;
  final String metricId;
  final double scoreAvg;
  final int sampleCount;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'bucketDate': bucketDate,
      'scopeId': scopeId,
      'domainId': domainId,
      'metricId': metricId,
      'scoreAvg': scoreAvg,
      'sampleCount': sampleCount,
    };
  }

  factory AssistentScoreAggregate.fromJson(Map<String, dynamic> json) {
    return AssistentScoreAggregate(
      bucketDate: (json['bucketDate'] as String?) ?? '',
      scopeId: (json['scopeId'] as String?) ?? '',
      domainId: (json['domainId'] as String?) ?? 'general',
      metricId: (json['metricId'] as String?) ?? '',
      scoreAvg: (json['scoreAvg'] as num?)?.toDouble() ?? 0.0,
      sampleCount: (json['sampleCount'] as int?) ?? 0,
    );
  }
}

