class AggregationState {
  const AggregationState({
    this.allSkillsReady = false,
    this.blockingSkills = const <String>[],
    this.canGivePartialAnswer = false,
    this.needExpansion = false,
    this.expansionPlan = const <String, dynamic>{},
    this.finalAnswerReady = false,
    this.finalAnswerMode = '',
    this.clarificationNeeded = false,
  });

  final bool allSkillsReady;
  final List<String> blockingSkills;
  final bool canGivePartialAnswer;
  final bool needExpansion;
  final Map<String, dynamic> expansionPlan;
  final bool finalAnswerReady;
  final String finalAnswerMode;
  final bool clarificationNeeded;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'allSkillsReady': allSkillsReady,
    'blockingSkills': blockingSkills,
    'canGivePartialAnswer': canGivePartialAnswer,
    'needExpansion': needExpansion,
    'expansionPlan': expansionPlan,
    'finalAnswerReady': finalAnswerReady,
    'finalAnswerMode': finalAnswerMode,
    'clarificationNeeded': clarificationNeeded,
  };

  factory AggregationState.fromJson(Map<String, dynamic> json) {
    return AggregationState(
      allSkillsReady: json['allSkillsReady'] == true,
      blockingSkills: (json['blockingSkills'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      canGivePartialAnswer: json['canGivePartialAnswer'] == true,
      needExpansion: json['needExpansion'] == true,
      expansionPlan:
          (json['expansionPlan'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      finalAnswerReady: json['finalAnswerReady'] == true,
      finalAnswerMode: (json['finalAnswerMode'] as String?)?.trim() ?? '',
      clarificationNeeded: json['clarificationNeeded'] == true,
    );
  }
}
