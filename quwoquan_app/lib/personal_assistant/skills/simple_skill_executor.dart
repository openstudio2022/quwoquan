import 'package:quwoquan_app/personal_assistant/knowledge/knowledge_qa_engine.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

/// Pure Dart skill executor for acceptance and VM runtime checks.
/// It executes tool-chain skills without depending on Flutter platform channels.
class SimpleSkillExecutor {
  SimpleSkillExecutor(this._toolRegistry)
      : _knowledgeQaEngine = KnowledgeQaEngine(toolRegistry: _toolRegistry);

  final AssistantToolRegistry _toolRegistry;
  final KnowledgeQaEngine _knowledgeQaEngine;

  Future<AssistantToolResult> invoke({
    required PersonalAssistantSkillManifest skill,
    required Map<String, dynamic> arguments,
  }) async {
    final errors = skill.validate();
    if (errors.isNotEmpty) {
      return AssistantToolResult(
        success: false,
        message: 'Invalid skill: ${errors.join('; ')}',
        errorCode: AssistantErrorCode.invalidArguments,
        degraded: true,
      );
    }
    if (skill.executionTarget != 'tool_chain') {
      return AssistantToolResult(
        success: false,
        message: 'Unsupported execution target in VM acceptance: ${skill.executionTarget}',
        errorCode: AssistantErrorCode.unsupportedTarget,
        degraded: true,
      );
    }
    if (skill.id == 'web.quick_search' || skill.id == 'knowledge_qa') {
      final toolArgs = Map<String, dynamic>.from(arguments['toolArgs'] as Map? ?? arguments);
      final query = (toolArgs['query'] as String?)?.trim() ?? '';
      if (query.isEmpty) {
        return const AssistantToolResult(
          success: false,
          message: 'knowledge_qa query is required',
          errorCode: AssistantErrorCode.invalidArguments,
          degraded: true,
        );
      }
      final report = await _knowledgeQaEngine.run(
        query: query,
        primaryProvider: toolArgs['provider'] as String?,
        backupProviders: (toolArgs['backupProviders'] as List?)
                ?.map((e) => e.toString())
                .toList(growable: false) ??
            const <String>['brave', 'openclaw_proxy'],
        maxEvidence: (toolArgs['maxEvidence'] as int?) ?? 6,
      );
      return AssistantToolResult(
        success: true,
        message: report.answer,
        data: report.toJson(),
        degraded: report.degraded,
        errorCode: report.degraded ? AssistantErrorCode.executionFailed : AssistantErrorCode.none,
      );
    }
    final rawSteps = arguments['steps'] as List?;
    if (rawSteps != null && rawSteps.isNotEmpty) {
      for (final step in rawSteps.whereType<Map>()) {
        final map = step.cast<String, dynamic>();
        final name = (map['toolName'] as String?) ?? 'web_search';
        final args = Map<String, dynamic>.from(
          map['toolArgs'] as Map? ?? const <String, dynamic>{},
        );
        final result = await _toolRegistry.execute(name, args);
        if (!result.success) return result;
      }
      return const AssistantToolResult(success: true, message: 'Tool-chain success');
    }
    final toolName = (arguments['toolName'] as String?) ?? 'web_search';
    final toolArgs = Map<String, dynamic>.from(arguments['toolArgs'] as Map? ?? arguments);
    return _toolRegistry.execute(toolName, toolArgs);
  }
}
