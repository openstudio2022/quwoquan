class ReactPlanStep {
  const ReactPlanStep({
    required this.id,
    required this.description,
    required this.toolName,
    required this.arguments,
    this.toolCallId = '',
  });

  final String id;
  final String description;
  final String toolName;
  final Map<String, dynamic> arguments;

  /// OpenAI function calling 协议的 tool_call id，用于构建 tool result message。
  final String toolCallId;
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
  bool forceAnswerOnly = false;

  /// Tracks consecutive iterations where the model produced no text and no
  /// tool calls.  Used as a deadlock safety valve: if this reaches the
  /// threshold the loop force-exits.
  int consecutiveEmptyIterations = 0;

  bool get shouldStopByBudget => usedTools >= toolBudget && !forceAnswerOnly;
  bool get shouldStopByIteration => iteration >= maxIterations;
}
