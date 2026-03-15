import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skills/knowledge_qa_engine.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:quwoquan_app/assistant/tools/tool_schema.dart';

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
    if (skill.executionTargetType != SkillExecutionTarget.toolChain) {
      return AssistantToolResult(
        success: false,
        message:
            'Unsupported execution target in VM acceptance: ${skill.executionTarget}',
        errorCode: AssistantErrorCode.unsupportedTarget,
        degraded: true,
      );
    }
    if (_usesKnowledgeQaPipeline(skill, arguments)) {
      final toolArgs = Map<String, dynamic>.from(
        arguments['toolArgs'] as Map? ?? arguments,
      );
      final query = (toolArgs['query'] as String?)?.trim() ?? '';
      if (query.isEmpty) {
        return const AssistantToolResult(
          success: false,
          message: '缺少知识问答所需的 query 参数',
          errorCode: AssistantErrorCode.invalidArguments,
          degraded: true,
        );
      }
      final retrievalToolName =
          (arguments['toolName'] as String?)?.trim().isNotEmpty == true
          ? (arguments['toolName'] as String).trim()
          : (skill.allowedTools.isNotEmpty ? skill.allowedTools.first : '');
      final report = await _knowledgeQaEngine.run(
        query: query,
        domainId: skill.domainId,
        retrievalToolName: retrievalToolName,
        primaryProvider: toolArgs['provider'] as String?,
        backupProviders:
            (toolArgs['backupProviders'] as List?)
                ?.map((item) => item.toString())
                .toList(growable: false) ??
            const <String>[],
        maxEvidence: (toolArgs['maxEvidence'] as int?) ?? 6,
      );
      return AssistantToolResult(
        success: true,
        message: report.answer,
        data: report.toJson(),
        degraded: report.degraded,
        errorCode: report.degraded
            ? AssistantErrorCode.executionFailed
            : AssistantErrorCode.none,
      );
    }
    final rawSteps = arguments['steps'] as List?;
    if (rawSteps != null && rawSteps.isNotEmpty) {
      for (final step in rawSteps.whereType<Map>()) {
        final map = step.cast<String, dynamic>();
        final name =
            (map['toolName'] as String?) ??
            (skill.allowedTools.isNotEmpty ? skill.allowedTools.first : '');
        if (name.trim().isEmpty) {
          return const AssistantToolResult(
            success: false,
            message: 'tool-chain step 缺少 toolName 且 skill 未声明 allowedTools',
            errorCode: AssistantErrorCode.invalidArguments,
            degraded: true,
          );
        }
        final args = Map<String, dynamic>.from(
          map['toolArgs'] as Map? ?? const <String, dynamic>{},
        );
        final result = await _toolRegistry.execute(name, args);
        if (!result.success) return result;
      }
      return const AssistantToolResult(
        success: true,
        message: 'Tool-chain success',
      );
    }
    final toolName =
        (arguments['toolName'] as String?) ??
        (skill.allowedTools.isNotEmpty ? skill.allowedTools.first : '');
    if (toolName.trim().isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'skill 缺少显式 toolName 且未声明 allowedTools',
        errorCode: AssistantErrorCode.invalidArguments,
        degraded: true,
      );
    }
    final toolArgs = Map<String, dynamic>.from(
      arguments['toolArgs'] as Map? ?? arguments,
    );
    return _toolRegistry.execute(toolName, toolArgs);
  }

  bool _usesKnowledgeQaPipeline(
    PersonalAssistantSkillManifest skill,
    Map<String, dynamic> arguments,
  ) {
    final toolArgs = Map<String, dynamic>.from(
      arguments['toolArgs'] as Map? ?? arguments,
    );
    final hasQuery = (toolArgs['query'] as String?)?.trim().isNotEmpty == true;
    return hasQuery && skill.toolChainProfile.trim() == 'knowledge_qa';
  }
}
