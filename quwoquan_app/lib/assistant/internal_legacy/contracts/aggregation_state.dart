class AggregationState {
  const AggregationState({
    this.allSkillsReady = false,
    this.blockingSkills = const <String>[],
    this.blockedBy = const <String, String>{},
    this.canGivePartialAnswer = false,
    this.needExpansion = false,
    this.expansionPlan = const <String, dynamic>{},
    this.finalAnswerReady = false,
    this.finalAnswerMode = '',
    this.clarificationNeeded = false,
    this.answerOwner = '',
    this.clarificationSource = '',
    this.dependencies = const <String, List<String>>{},
  });

  final bool allSkillsReady;
  final List<String> blockingSkills;
  final Map<String, String> blockedBy;
  final bool canGivePartialAnswer;
  final bool needExpansion;
  final Map<String, dynamic> expansionPlan;
  final bool finalAnswerReady;
  final String finalAnswerMode;
  final bool clarificationNeeded;
  final String answerOwner;
  final String clarificationSource;
  final Map<String, List<String>> dependencies;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'allSkillsReady': allSkillsReady,
    'blockingSkills': blockingSkills,
    'blockedBy': blockedBy,
    'canGivePartialAnswer': canGivePartialAnswer,
    'needExpansion': needExpansion,
    'expansionPlan': expansionPlan,
    'finalAnswerReady': finalAnswerReady,
    'finalAnswerMode': finalAnswerMode,
    'clarificationNeeded': clarificationNeeded,
    'answerOwner': answerOwner,
    'clarificationSource': clarificationSource,
    'dependencies': dependencies,
  };

  factory AggregationState.fromJson(Map<String, dynamic> json) {
    return AggregationState(
      allSkillsReady: json['allSkillsReady'] == true,
      blockingSkills:
          (json['blockingSkills'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      blockedBy:
          (json['blockedBy'] as Map?)?.map(
            (key, value) =>
                MapEntry(key.toString(), value?.toString().trim() ?? ''),
          ) ??
          const <String, String>{},
      canGivePartialAnswer: json['canGivePartialAnswer'] == true,
      needExpansion: json['needExpansion'] == true,
      expansionPlan:
          (json['expansionPlan'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      finalAnswerReady: json['finalAnswerReady'] == true,
      finalAnswerMode: (json['finalAnswerMode'] as String?)?.trim() ?? '',
      clarificationNeeded: json['clarificationNeeded'] == true,
      answerOwner: (json['answerOwner'] as String?)?.trim() ?? '',
      clarificationSource:
          (json['clarificationSource'] as String?)?.trim() ?? '',
      dependencies:
          (json['dependencies'] as Map?)?.map(
            (key, value) => MapEntry(
              key.toString(),
              (value as List?)
                      ?.whereType<String>()
                      .map((item) => item.trim())
                      .where((item) => item.isNotEmpty)
                      .toList(growable: false) ??
                  const <String>[],
            ),
          ) ??
          const <String, List<String>>{},
    );
  }
}
