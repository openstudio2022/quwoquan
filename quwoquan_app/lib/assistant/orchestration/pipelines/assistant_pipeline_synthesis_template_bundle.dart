class AssistantPipelineSynthesisTemplateBundle {
  const AssistantPipelineSynthesisTemplateBundle({
    required this.templateVariables,
    required this.conversationSpine,
    required this.userGoal,
    required this.understandingSnapshot,
    required this.retrievalProcessing,
    required this.sharedContext,
    required this.currentRuntimeState,
    required this.dialogueContinuity,
    required this.evidenceContext,
    required this.searchIterationState,
    required this.planViewJson,
    required this.searchPlansJson,
    required this.entityRefs,
    required this.searchPlans,
    required this.answerShape,
    required this.recentDialogueRounds,
  });

  final Map<String, dynamic> templateVariables;
  final Map<String, dynamic> conversationSpine;
  final String userGoal;
  final Map<String, dynamic> understandingSnapshot;
  final Map<String, dynamic> retrievalProcessing;
  final Map<String, dynamic> sharedContext;
  final Map<String, dynamic> currentRuntimeState;
  final Map<String, dynamic> dialogueContinuity;
  final Map<String, dynamic> evidenceContext;
  final Map<String, dynamic> searchIterationState;
  final String planViewJson;
  final List<Map<String, dynamic>> searchPlansJson;
  final List<String> entityRefs;
  final List<Map<String, dynamic>> searchPlans;
  final String answerShape;
  final List<Map<String, dynamic>> recentDialogueRounds;
}
