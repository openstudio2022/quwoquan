import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class AssistantToolRegistry {
  final Map<String, AssistantTool> _tools = <String, AssistantTool>{};

  void register(AssistantTool tool) {
    _tools[tool.name] = tool;
  }

  AssistantTool? getTool(String name) => _tools[name];

  List<AssistantTool> listTools() => _tools.values.toList(growable: false);

  Future<AssistantToolResult> execute(
    String name,
    Map<String, dynamic> arguments,
  ) async {
    final tool = _tools[name];
    if (tool == null) {
      return const AssistantToolResult(
        success: false,
        message: 'Tool not found',
        errorCode: AssistantErrorCode.toolNotFound,
        degraded: true,
      );
    }
    try {
      return await tool.execute(arguments);
    } catch (error) {
      return AssistantToolResult(
        success: false,
        message: 'Tool execution failed: $error',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
  }
}
