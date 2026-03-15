import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/intent_bridge/assistant_intent_bridge_runtime.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skills/knowledge_qa_engine.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:quwoquan_app/assistant/tools/tool_schema.dart';

typedef SkillRemoteInvoker =
    Future<AssistantToolResult?> Function(
      String skillId,
      Map<String, dynamic> arguments,
    );

class AssistantSkillExecutor {
  AssistantSkillExecutor({
    required AssistantToolRegistry toolRegistry,
    required IOSIntentAdapter iosIntentAdapter,
    required AndroidIntentAdapter androidIntentAdapter,
    required MethodChannelAdapter methodChannelAdapter,
    AssistantCapabilityRouter? capabilityRouter,
    KnowledgeQaEngine? knowledgeQaEngine,
  }) : _toolRegistry = toolRegistry,
       _iosIntentAdapter = iosIntentAdapter,
       _androidIntentAdapter = androidIntentAdapter,
       _methodChannelAdapter = methodChannelAdapter,
       _capabilityRouter = capabilityRouter ?? const AssistantCapabilityRouter(),
       _knowledgeQaEngine =
           knowledgeQaEngine ?? KnowledgeQaEngine(toolRegistry: toolRegistry);

  final AssistantToolRegistry _toolRegistry;
  final IOSIntentAdapter _iosIntentAdapter;
  final AndroidIntentAdapter _androidIntentAdapter;
  final MethodChannelAdapter _methodChannelAdapter;
  final AssistantCapabilityRouter _capabilityRouter;
  final KnowledgeQaEngine _knowledgeQaEngine;

  Future<AssistantToolResult> execute({
    required PersonalAssistantSkillManifest skill,
    required Map<String, dynamic> arguments,
    String deviceProfile = 'mobile',
    SkillRemoteInvoker? remoteInvoker,
  }) async {
    final validationErrors = skill.validate();
    if (validationErrors.isNotEmpty) {
      return AssistantToolResult(
        success: false,
        message: 'Skill manifest invalid: ${validationErrors.join('; ')}',
        errorCode: AssistantErrorCode.invalidArguments,
        degraded: true,
      );
    }
    switch (skill.executionTargetType) {
      case SkillExecutionTarget.iosIntent:
        final result = await _iosIntentAdapter.invokeIntent(
          intentName: (arguments['intentName'] as String?) ?? skill.id,
          parameters: arguments,
        );
        if (result.containsKey('error')) {
          return AssistantToolResult(
            success: false,
            message: result['error'].toString(),
            errorCode: AssistantErrorCode.executionFailed,
            degraded: true,
          );
        }
        return AssistantToolResult(
          success: true,
          message: 'iOS intent success',
          data: result,
        );
      case SkillExecutionTarget.androidIntent:
        final result = await _androidIntentAdapter.invokeIntent(
          action:
              (arguments['action'] as String?) ?? 'android.intent.action.VIEW',
          extras: arguments,
          data: arguments['data'] as String?,
        );
        if (result.containsKey('error')) {
          return AssistantToolResult(
            success: false,
            message: result['error'].toString(),
            errorCode: AssistantErrorCode.executionFailed,
            degraded: true,
          );
        }
        return AssistantToolResult(
          success: true,
          message: 'Android intent success',
          data: result,
        );
      case SkillExecutionTarget.nativeApi:
        final result = await _methodChannelAdapter.invoke(skill.id, arguments);
        if (result.containsKey('error')) {
          return AssistantToolResult(
            success: false,
            message: result['error'].toString(),
            errorCode: AssistantErrorCode.executionFailed,
            degraded: true,
          );
        }
        return AssistantToolResult(
          success: true,
          message: 'Native API success',
          data: result,
        );
      case SkillExecutionTarget.toolChain:
      case SkillExecutionTarget.unknown:
        return _executeToolChain(
          skill: skill,
          arguments: arguments,
          deviceProfile: deviceProfile,
          remoteInvoker: remoteInvoker,
        );
    }
  }

  Future<AssistantToolResult> _executeToolChain({
    required PersonalAssistantSkillManifest skill,
    required Map<String, dynamic> arguments,
    required String deviceProfile,
    required SkillRemoteInvoker? remoteInvoker,
  }) async {
    if (_usesKnowledgeQaPipeline(skill, arguments)) {
      return _executeKnowledgeQa(skill, arguments);
    }
    final steps = _resolveSteps(skill, arguments);
    if (steps.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'skill 缺少显式 toolName 且未声明 allowedTools',
        errorCode: AssistantErrorCode.invalidArguments,
        degraded: true,
      );
    }
    final aggregated = <Map<String, dynamic>>[];
    var context = <String, dynamic>{...arguments};

    for (final step in steps) {
      final toolName = step.$1;
      final toolArgs = <String, dynamic>{...step.$2, 'context': context};
      final decision = _capabilityRouter.decide(
        deviceProfile: deviceProfile,
        capabilityName: toolName,
      );

      AssistantToolResult? remoteResult;
      if (remoteInvoker != null &&
          (decision.mode == AssistantCapabilityMode.remotePreferred ||
              decision.mode == AssistantCapabilityMode.hybrid)) {
        remoteResult = await remoteInvoker(skill.id, toolArgs);
      }

      final AssistantToolResult result;
      if (remoteResult != null && remoteResult.success) {
        result = remoteResult;
      } else {
        final localResult = await _toolRegistry.execute(toolName, toolArgs);
        result = AssistantToolResult.fromJson(localResult.toJson());
      }
      aggregated.add(<String, dynamic>{
        'tool': toolName,
        'success': result.success,
        'message': result.message,
        'errorCode': result.errorCode.name,
        'route': decision.mode.name,
      });
      context = <String, dynamic>{
        ...context,
        'lastTool': toolName,
        'lastResult': result.toJson(),
      };
      if (!result.success) {
        return AssistantToolResult(
          success: false,
          message: 'Tool-chain stopped at $toolName: ${result.message}',
          data: <String, dynamic>{'steps': aggregated},
          errorCode: result.errorCode,
          degraded: true,
        );
      }
    }

    return AssistantToolResult(
      success: true,
      message: 'Tool-chain success',
      data: <String, dynamic>{'steps': aggregated},
    );
  }

  Future<AssistantToolResult> _executeKnowledgeQa(
    PersonalAssistantSkillManifest skill,
    Map<String, dynamic> arguments,
  ) async {
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

  List<(String, Map<String, dynamic>)> _resolveSteps(
    PersonalAssistantSkillManifest skill,
    Map<String, dynamic> arguments,
  ) {
    final rawSteps = arguments['steps'];
    if (rawSteps is List && rawSteps.isNotEmpty) {
      return rawSteps
          .whereType<Map>()
          .map((raw) {
            final map = raw.cast<String, dynamic>();
            final toolName =
                (map['toolName'] as String?)?.trim() ??
                _defaultToolForSkill(skill);
            if (toolName.trim().isEmpty) return null;
            final args = Map<String, dynamic>.from(
              map['toolArgs'] as Map? ?? const <String, dynamic>{},
            );
            return (toolName, args);
          })
          .whereType<(String, Map<String, dynamic>)>()
          .toList(growable: false);
    }
    final singleTool =
        (arguments['toolName'] as String?) ?? _defaultToolForSkill(skill);
    if (singleTool.trim().isEmpty) {
      return const <(String, Map<String, dynamic>)>[];
    }
    final singleArgs = Map<String, dynamic>.from(
      arguments['toolArgs'] as Map? ?? arguments,
    );
    return <(String, Map<String, dynamic>)>[(singleTool, singleArgs)];
  }

  String _defaultToolForSkill(PersonalAssistantSkillManifest skill) {
    if (skill.allowedTools.isNotEmpty) {
      return skill.allowedTools.first;
    }
    return '';
  }

  bool _usesKnowledgeQaPipeline(
    PersonalAssistantSkillManifest skill,
    Map<String, dynamic> arguments,
  ) {
    final toolArgs = Map<String, dynamic>.from(
      arguments['toolArgs'] as Map? ?? arguments,
    );
    final hasQuery = (toolArgs['query'] as String?)?.trim().isNotEmpty == true;
    return hasQuery &&
        skill.executionTargetType == SkillExecutionTarget.toolChain &&
        skill.toolChainProfile.trim() == 'knowledge_qa';
  }
}
