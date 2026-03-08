class SkillRun {
  const SkillRun({
    required this.runId,
    required this.domainId,
    required this.goal,
    required this.problemClass,
    this.shell = const <String, dynamic>{},
    this.slotState = const <String, dynamic>{},
    this.answerReady = false,
    this.stopReason = '',
    this.references = const <Map<String, dynamic>>[],
    this.resultSummary = '',
  });

  final String runId;
  final String domainId;
  final String goal;
  final String problemClass;
  final Map<String, dynamic> shell;
  final Map<String, dynamic> slotState;
  final bool answerReady;
  final String stopReason;
  final List<Map<String, dynamic>> references;
  final String resultSummary;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'runId': runId,
    'domainId': domainId,
    'goal': goal,
    'problemClass': problemClass,
    'shell': shell,
    'slotState': slotState,
    'answerReady': answerReady,
    'stopReason': stopReason,
    'references': references,
    'resultSummary': resultSummary,
  };

  factory SkillRun.fromJson(Map<String, dynamic> json) {
    return SkillRun(
      runId: (json['runId'] as String?)?.trim() ?? '',
      domainId: (json['domainId'] as String?)?.trim() ?? '',
      goal: (json['goal'] as String?)?.trim() ?? '',
      problemClass: (json['problemClass'] as String?)?.trim() ?? '',
      shell: (json['shell'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      slotState:
          (json['slotState'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      answerReady: json['answerReady'] == true,
      stopReason: (json['stopReason'] as String?)?.trim() ?? '',
      references: (json['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[],
      resultSummary: (json['resultSummary'] as String?)?.trim() ?? '',
    );
  }
}
