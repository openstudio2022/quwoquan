class ReactPlanStep {
  const ReactPlanStep({
    required this.id,
    required this.description,
    required this.toolName,
    required this.arguments,
  });

  final String id;
  final String description;
  final String toolName;
  final Map<String, dynamic> arguments;
}

class ReactRunState {
  ReactRunState({
    required this.goal,
    required this.maxIterations,
    required this.toolBudget,
  });

  final String goal;
  final int maxIterations;
  final int toolBudget;
  final List<ReactPlanStep> plan = <ReactPlanStep>[];
  final List<Map<String, dynamic>> evidences = <Map<String, dynamic>>[];
  final List<String> openQuestions = <String>[];

  int iteration = 0;
  int usedTools = 0;
  String? stopReason;

  bool get shouldStopByBudget => usedTools >= toolBudget;
  bool get shouldStopByIteration => iteration >= maxIterations;
}

