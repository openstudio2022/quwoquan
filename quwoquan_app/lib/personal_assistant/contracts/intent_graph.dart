class IntentGraph {
  const IntentGraph({
    required this.userGoal,
    required this.problemShape,
    required this.primarySkill,
    this.secondarySkills = const <String>[],
    this.globalConstraints = const <String, dynamic>{},
    this.clarificationNeeded = false,
  });

  final String userGoal;
  final String problemShape;
  final String primarySkill;
  final List<String> secondarySkills;
  final Map<String, dynamic> globalConstraints;
  final bool clarificationNeeded;

  bool get isMultiSkill =>
      problemShape == 'multi_skill' || secondarySkills.isNotEmpty;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'userGoal': userGoal,
    'problemShape': problemShape,
    'primarySkill': primarySkill,
    'secondarySkills': secondarySkills,
    'globalConstraints': globalConstraints,
    'clarificationNeeded': clarificationNeeded,
  };

  factory IntentGraph.fromJson(Map<String, dynamic> json) {
    return IntentGraph(
      userGoal: (json['userGoal'] as String?)?.trim() ?? '',
      problemShape: (json['problemShape'] as String?)?.trim() ?? 'single_skill',
      primarySkill: (json['primarySkill'] as String?)?.trim() ?? '',
      secondarySkills:
          (json['secondarySkills'] as List?)
              ?.whereType<String>()
              .map((item) => item.trim())
              .where((item) => item.isNotEmpty)
              .toList(growable: false) ??
          const <String>[],
      globalConstraints:
          (json['globalConstraints'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      clarificationNeeded: json['clarificationNeeded'] == true,
    );
  }
}
