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
    required this.intentGraphJson,
    required this.queryTasksJson,
    required this.entityAnchors,
    required this.queryTasks,
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
  final String intentGraphJson;
  final List<Map<String, dynamic>> queryTasksJson;
  final List<String> entityAnchors;
  final List<Map<String, dynamic>> queryTasks;
  final String answerShape;
  final List<Map<String, dynamic>> recentDialogueRounds;
}
