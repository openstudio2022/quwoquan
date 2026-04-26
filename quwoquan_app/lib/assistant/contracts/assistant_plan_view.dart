import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/search_plan_contract.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';

class AssistantPlanView {
  const AssistantPlanView({
    required this.userGoal,
    required this.primarySkill,
    required this.problemShape,
    required this.problemClass,
    this.answerShape = AnswerShape.unspecified,
    this.requiresExternalEvidence = false,
    this.mustVerifyClaims = false,
    this.clarificationNeeded = false,
    this.entityRefs = const <String>[],
    this.constraints = const <String>[],
    this.authorityDomains = const <String>[],
    this.searchPlans = const <SearchPlanItem>[],
  });

  final String userGoal;
  final String primarySkill;
  final ProblemShape problemShape;
  final ProblemClass problemClass;
  final AnswerShape answerShape;
  final bool requiresExternalEvidence;
  final bool mustVerifyClaims;
  final bool clarificationNeeded;
  final List<String> entityRefs;
  final List<String> constraints;
  final List<String> authorityDomains;
  final List<SearchPlanItem> searchPlans;

  String get problemClassWireName => problemClass.wireName;

  String get answerShapeWireName => answerShape.wireName;

  bool get isMultiSkill => problemShape == ProblemShape.multiSkill;

  bool get isFastConvergence => false;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'userGoal': userGoal,
    'primarySkill': primarySkill,
    'problemShape': problemShape.wireName,
    'problemClass': problemClass.wireName,
    'answerShape': answerShape.wireName,
    'requiresExternalEvidence': requiresExternalEvidence,
    'mustVerifyClaims': mustVerifyClaims,
    'clarificationNeeded': clarificationNeeded,
    'entityRefs': entityRefs,
    'constraints': constraints,
    'authorityDomains': authorityDomains,
    'searchPlans': SearchPlanItem.toJsonList(searchPlans),
  };
}

AssistantPlanView? assistantPlanViewFromTypedMainline({
  required UnderstandingResult understandingResult,
  required TaskGraph taskGraph,
}) {
  if (understandingResult.intents.isEmpty) {
    return null;
  }
  final primaryIntent = understandingResult.intents.first;
  final intentType = primaryIntent.intentType.trim();
  final separatorIndex = intentType.indexOf('.');
  final primarySkill = separatorIndex > 0
      ? intentType.substring(0, separatorIndex)
      : (intentType.isNotEmpty ? intentType : 'fallback_general_search');
  final searchPlans = searchPlansFromTaskGraph(taskGraph);
  final requiresEvidence = understandingResult.intents.any(
    (intent) => intent.requiresEvidence,
  );
  return AssistantPlanView(
    userGoal: primaryIntent.goal,
    primarySkill: primarySkill,
    problemShape: understandingResult.intents.length > 1
        ? ProblemShape.multiSkill
        : ProblemShape.singleSkill,
    problemClass: ProblemClass.general,
    requiresExternalEvidence: requiresEvidence,
    mustVerifyClaims: requiresEvidence,
    clarificationNeeded:
        understandingResult.dialogueTransitionDecision.needsClarification,
    entityRefs: _entityRefLabels(primaryIntent),
    constraints: primaryIntent.constraints
        .map((item) => item.value.trim().isNotEmpty ? item.value.trim() : item.key.trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false),
    searchPlans: searchPlans,
  );
}

List<String> _entityRefLabels(IntentNode intent) {
  return intent.entityRefs
      .map(
        (ref) => ref.displayText.trim().isNotEmpty
            ? ref.displayText.trim()
            : ref.canonicalKey.trim(),
      )
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}
