class AssistantSubagentRunRecord {
  const AssistantSubagentRunRecord({
    required this.version,
    required this.subagentId,
    required this.domainId,
    required this.status,
    required this.goal,
    required this.mode,
    required this.problemClass,
    required this.shell,
    required this.stopPolicy,
    required this.searchIntensity,
    required this.providerPolicy,
    required this.freshnessHoursMax,
    required this.answerThreshold,
    required this.summary,
    required this.userMarkdown,
    required this.result,
    required this.answerReady,
    required this.references,
    this.acceptedEvidence = const <Map<String, dynamic>>[],
    this.rejectedEvidence = const <Map<String, dynamic>>[],
    this.nextAction = '',
    this.missingSlots = const <String>[],
    this.failureReason = '',
    required this.toolCallCount,
    required this.modelCallCount,
    required this.totalTokens,
    required this.maxTokensPerCall,
    required this.tokenSource,
    required this.tokenSampleCount,
    this.inputTokens = 0,
    this.outputTokens = 0,
    this.usageLedger = const <Map<String, dynamic>>[],
    this.errorClass = '',
    this.errorMessage = '',
  });

  factory AssistantSubagentRunRecord.success({
    required String subagentId,
    required String domainId,
    required String goal,
    required String mode,
    required String problemClass,
    required Map<String, dynamic> shell,
    required String stopPolicy,
    required String searchIntensity,
    required String providerPolicy,
    required int freshnessHoursMax,
    required double answerThreshold,
    required String summary,
    required String userMarkdown,
    required Map<String, dynamic> result,
    required bool answerReady,
    required List<Map<String, dynamic>> references,
    required List<Map<String, dynamic>> acceptedEvidence,
    required List<Map<String, dynamic>> rejectedEvidence,
    required String nextAction,
    required List<String> missingSlots,
    required String failureReason,
    required int toolCallCount,
    required int modelCallCount,
    required int totalTokens,
    required int maxTokensPerCall,
    required String tokenSource,
    required int tokenSampleCount,
    required int inputTokens,
    required int outputTokens,
    required List<Map<String, dynamic>> usageLedger,
  }) {
    return AssistantSubagentRunRecord(
      version: 'subagent_result',
      subagentId: subagentId,
      domainId: domainId,
      status: 'success',
      goal: goal,
      mode: mode,
      problemClass: problemClass,
      shell: shell,
      stopPolicy: stopPolicy,
      searchIntensity: searchIntensity,
      providerPolicy: providerPolicy,
      freshnessHoursMax: freshnessHoursMax,
      answerThreshold: answerThreshold,
      summary: summary,
      userMarkdown: userMarkdown,
      result: result,
      answerReady: answerReady,
      references: references,
      acceptedEvidence: acceptedEvidence,
      rejectedEvidence: rejectedEvidence,
      nextAction: nextAction,
      missingSlots: missingSlots,
      failureReason: failureReason,
      toolCallCount: toolCallCount,
      modelCallCount: modelCallCount,
      totalTokens: totalTokens,
      maxTokensPerCall: maxTokensPerCall,
      tokenSource: tokenSource,
      tokenSampleCount: tokenSampleCount,
      inputTokens: inputTokens,
      outputTokens: outputTokens,
      usageLedger: usageLedger,
    );
  }

  factory AssistantSubagentRunRecord.timeout({
    required String subagentId,
    required String domainId,
    required String goal,
    required String mode,
    required String problemClass,
    required Map<String, dynamic> shell,
    required String stopPolicy,
    required String searchIntensity,
    required String providerPolicy,
    required int freshnessHoursMax,
    required double answerThreshold,
    required List<String> missingSlots,
  }) {
    return AssistantSubagentRunRecord(
      version: 'subagent_result',
      subagentId: subagentId,
      domainId: domainId,
      status: 'timeout',
      goal: goal,
      mode: mode,
      problemClass: problemClass,
      shell: shell,
      stopPolicy: stopPolicy,
      searchIntensity: searchIntensity,
      providerPolicy: providerPolicy,
      freshnessHoursMax: freshnessHoursMax,
      answerThreshold: answerThreshold,
      summary: '',
      userMarkdown: '',
      result: const <String, dynamic>{},
      answerReady: false,
      references: const <Map<String, dynamic>>[],
      acceptedEvidence: const <Map<String, dynamic>>[],
      rejectedEvidence: const <Map<String, dynamic>>[],
      nextAction: 'timeout',
      missingSlots: missingSlots,
      failureReason: 'timeout',
      toolCallCount: 0,
      modelCallCount: 0,
      totalTokens: 0,
      maxTokensPerCall: 0,
      tokenSource: '',
      tokenSampleCount: 0,
      errorClass: 'timeout',
      errorMessage: '',
    );
  }

  factory AssistantSubagentRunRecord.failure({
    required String subagentId,
    required String domainId,
    required String goal,
    required String mode,
    required String problemClass,
    required Map<String, dynamic> shell,
    required String stopPolicy,
    required String searchIntensity,
    required String providerPolicy,
    required int freshnessHoursMax,
    required double answerThreshold,
    required List<String> missingSlots,
    required String failureReason,
    required String errorMessage,
  }) {
    return AssistantSubagentRunRecord(
      version: 'subagent_result',
      subagentId: subagentId,
      domainId: domainId,
      status: 'failed',
      goal: goal,
      mode: mode,
      problemClass: problemClass,
      shell: shell,
      stopPolicy: stopPolicy,
      searchIntensity: searchIntensity,
      providerPolicy: providerPolicy,
      freshnessHoursMax: freshnessHoursMax,
      answerThreshold: answerThreshold,
      summary: '',
      userMarkdown: '',
      result: const <String, dynamic>{},
      answerReady: false,
      references: const <Map<String, dynamic>>[],
      acceptedEvidence: const <Map<String, dynamic>>[],
      rejectedEvidence: const <Map<String, dynamic>>[],
      nextAction: 'failed',
      missingSlots: missingSlots,
      failureReason: failureReason,
      toolCallCount: 0,
      modelCallCount: 0,
      totalTokens: 0,
      maxTokensPerCall: 0,
      tokenSource: '',
      tokenSampleCount: 0,
      errorClass: 'execution_failed',
      errorMessage: errorMessage,
    );
  }

  final String version;
  final String subagentId;
  final String domainId;
  final String status;
  final String goal;
  final String mode;
  final String problemClass;
  final Map<String, dynamic> shell;
  final String stopPolicy;
  final String searchIntensity;
  final String providerPolicy;
  final int freshnessHoursMax;
  final double answerThreshold;
  final String summary;
  final String userMarkdown;
  final Map<String, dynamic> result;
  final bool answerReady;
  final List<Map<String, dynamic>> references;
  final List<Map<String, dynamic>> acceptedEvidence;
  final List<Map<String, dynamic>> rejectedEvidence;
  final String nextAction;
  final List<String> missingSlots;
  final String failureReason;
  final int toolCallCount;
  final int modelCallCount;
  final int totalTokens;
  final int maxTokensPerCall;
  final String tokenSource;
  final int tokenSampleCount;
  final int inputTokens;
  final int outputTokens;
  final List<Map<String, dynamic>> usageLedger;
  final String errorClass;
  final String errorMessage;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'version': version,
    'subagentId': subagentId,
    'domainId': domainId,
    'status': status,
    'goal': goal,
    'mode': mode,
    'problemClass': problemClass,
    'shell': shell,
    'stopPolicy': stopPolicy,
    'searchIntensity': searchIntensity,
    'providerPolicy': providerPolicy,
    'freshnessHoursMax': freshnessHoursMax,
    'answerThreshold': answerThreshold,
    'summary': summary,
    'userMarkdown': userMarkdown,
    'result': result,
    'answerReady': answerReady,
    'references': references,
    'acceptedEvidence': acceptedEvidence,
    'rejectedEvidence': rejectedEvidence,
    'nextAction': nextAction,
    'missingSlots': missingSlots,
    'failureReason': failureReason,
    'toolCallCount': toolCallCount,
    'modelCallCount': modelCallCount,
    'totalTokens': totalTokens,
    'maxTokensPerCall': maxTokensPerCall,
    'tokenSource': tokenSource,
    'tokenSampleCount': tokenSampleCount,
    'inputTokens': inputTokens,
    'outputTokens': outputTokens,
    'usageLedger': usageLedger,
    'errorClass': errorClass,
    'errorMessage': errorMessage,
  };

  Map<String, dynamic> toModelJson() => <String, dynamic>{
    'subagentId': subagentId,
    'domainId': domainId,
    'status': status,
    'goal': goal,
    'problemClass': problemClass,
    'userMarkdown': userMarkdown,
    'result': result,
    'summary': summary,
    'references': references,
    'acceptedEvidence': acceptedEvidence,
    'rejectedEvidence': rejectedEvidence,
    'nextAction': nextAction,
    'missingSlots': missingSlots,
    'failureReason': failureReason,
  };

  factory AssistantSubagentRunRecord.fromJson(Map<String, dynamic> json) {
    return AssistantSubagentRunRecord(
      version: (json['version'] as String?)?.trim() ?? 'subagent_result',
      subagentId: (json['subagentId'] as String?)?.trim() ?? '',
      domainId: (json['domainId'] as String?)?.trim() ?? '',
      status: (json['status'] as String?)?.trim() ?? '',
      goal: (json['goal'] as String?)?.trim() ?? '',
      mode: (json['mode'] as String?)?.trim() ?? '',
      problemClass: (json['problemClass'] as String?)?.trim() ?? '',
      shell: (json['shell'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      stopPolicy: (json['stopPolicy'] as String?)?.trim() ?? '',
      searchIntensity: (json['searchIntensity'] as String?)?.trim() ?? '',
      providerPolicy: (json['providerPolicy'] as String?)?.trim() ?? '',
      freshnessHoursMax: (json['freshnessHoursMax'] as num?)?.toInt() ?? 0,
      answerThreshold: (json['answerThreshold'] as num?)?.toDouble() ?? 0.0,
      summary: (json['summary'] as String?)?.trim() ?? '',
      userMarkdown: (json['userMarkdown'] as String?)?.trim() ?? '',
      result: (json['result'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      answerReady: json['answerReady'] == true,
      references:
          (json['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      acceptedEvidence:
          (json['acceptedEvidence'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      rejectedEvidence:
          (json['rejectedEvidence'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      nextAction: (json['nextAction'] as String?)?.trim() ?? '',
      missingSlots:
          (json['missingSlots'] as List?)
              ?.map((item) => item.toString().trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      failureReason: (json['failureReason'] as String?)?.trim() ?? '',
      toolCallCount: (json['toolCallCount'] as num?)?.toInt() ?? 0,
      modelCallCount: (json['modelCallCount'] as num?)?.toInt() ?? 0,
      totalTokens: (json['totalTokens'] as num?)?.toInt() ?? 0,
      maxTokensPerCall: (json['maxTokensPerCall'] as num?)?.toInt() ?? 0,
      tokenSource: (json['tokenSource'] as String?)?.trim() ?? '',
      tokenSampleCount: (json['tokenSampleCount'] as num?)?.toInt() ?? 0,
      inputTokens: (json['inputTokens'] as num?)?.toInt() ?? 0,
      outputTokens: (json['outputTokens'] as num?)?.toInt() ?? 0,
      usageLedger:
          (json['usageLedger'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      errorClass: (json['errorClass'] as String?)?.trim() ?? '',
      errorMessage: (json['errorMessage'] as String?)?.trim() ?? '',
    );
  }

  String get localSummary => summary;
  bool get hasFailure => failureReason.trim().isNotEmpty || errorClass.trim().isNotEmpty;

}
