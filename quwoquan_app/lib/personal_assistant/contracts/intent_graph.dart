import 'package:quwoquan_app/personal_assistant/contracts/recall_result.dart';

class IntentGraph {
  const IntentGraph({
    required this.userGoal,
    required this.problemShape,
    required this.primarySkill,
    this.problemClass = 'general',
    this.inferredMotive = '',
    this.secondarySkills = const <String>[],
    this.globalConstraints = const <String, dynamic>{},
    this.clarificationNeeded = false,
    this.recallResult,
  });

  final String userGoal;
  final String problemShape;
  final String primarySkill;
  final String problemClass;

  /// Planner-produced one-sentence motive behind the user's query.
  final String inferredMotive;

  final List<String> secondarySkills;
  final Map<String, dynamic> globalConstraints;
  final bool clarificationNeeded;

  /// Pre-LLM recall result used to narrow skill catalog for the planner.
  final RecallResult? recallResult;

  bool get isMultiSkill =>
      problemShape == 'multi_skill' || secondarySkills.isNotEmpty;

  /// Whether the problem type allows fast convergence (skip reflection).
  bool get isFastConvergence =>
      problemClass == 'realtime_info' || problemClass == 'simple_qa';

  Map<String, dynamic> toJson() => <String, dynamic>{
    'userGoal': userGoal,
    'problemShape': problemShape,
    'primarySkill': primarySkill,
    'problemClass': problemClass,
    'inferredMotive': inferredMotive,
    'secondarySkills': secondarySkills,
    'globalConstraints': globalConstraints,
    'clarificationNeeded': clarificationNeeded,
    if (recallResult != null) 'recallResult': recallResult!.toJson(),
  };

  factory IntentGraph.fromJson(Map<String, dynamic> json) {
    return IntentGraph(
      userGoal: (json['userGoal'] as String?)?.trim() ?? '',
      problemShape: (json['problemShape'] as String?)?.trim() ?? 'single_skill',
      primarySkill: (json['primarySkill'] as String?)?.trim() ?? '',
      problemClass: (json['problemClass'] as String?)?.trim() ?? 'general',
      inferredMotive: (json['inferredMotive'] as String?)?.trim() ?? '',
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
      recallResult: json['recallResult'] is Map
          ? RecallResult.fromJson(
              (json['recallResult'] as Map).cast<String, dynamic>())
          : null,
    );
  }
}
