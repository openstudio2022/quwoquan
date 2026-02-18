import 'package:quwoquan_app/personal_assistant/engine/device_capability.dart';
import 'package:quwoquan_app/personal_assistant/intent_bridge/android_intent_adapter.dart';
import 'package:quwoquan_app/personal_assistant/intent_bridge/ios_intent_adapter.dart';
import 'package:quwoquan_app/personal_assistant/intent_bridge/method_channel_adapter.dart';
import 'package:quwoquan_app/personal_assistant/knowledge/knowledge_qa_engine.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

typedef SkillRemoteInvoker =
    Future<AssistantToolResult?> Function(String skillId, Map<String, dynamic> arguments);

class PersonalAssistantSkillExecutor {
  PersonalAssistantSkillExecutor({
    required AssistantToolRegistry toolRegistry,
    required IOSIntentAdapter iosIntentAdapter,
    required AndroidIntentAdapter androidIntentAdapter,
    required MethodChannelAdapter methodChannelAdapter,
    AssistantCapabilityRouter? capabilityRouter,
    KnowledgeQaEngine? knowledgeQaEngine,
  })  : _toolRegistry = toolRegistry,
        _iosIntentAdapter = iosIntentAdapter,
        _androidIntentAdapter = androidIntentAdapter,
        _methodChannelAdapter = methodChannelAdapter,
        _capabilityRouter = capabilityRouter ?? const AssistantCapabilityRouter(),
        _knowledgeQaEngine = knowledgeQaEngine ?? KnowledgeQaEngine(toolRegistry: toolRegistry);

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
    switch (skill.executionTarget) {
      case 'ios_intent':
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
        return AssistantToolResult(success: true, message: 'iOS intent success', data: result);
      case 'android_intent':
        final result = await _androidIntentAdapter.invokeIntent(
          action: (arguments['action'] as String?) ?? 'android.intent.action.VIEW',
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
        return AssistantToolResult(success: true, message: 'Android intent success', data: result);
      case 'native_api':
        final result = await _methodChannelAdapter.invoke(skill.id, arguments);
        if (result.containsKey('error')) {
          return AssistantToolResult(
            success: false,
            message: result['error'].toString(),
            errorCode: AssistantErrorCode.executionFailed,
            degraded: true,
          );
        }
        return AssistantToolResult(success: true, message: 'Native API success', data: result);
      case 'tool_chain':
      default:
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
    if (skill.id == 'web.quick_search' || skill.id == 'knowledge_qa') {
      return _executeKnowledgeQa(skill, arguments);
    }
    final steps = _resolveSteps(skill.id, arguments);
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

      final result =
          (remoteResult == null || !remoteResult.success) ? await _toolRegistry.execute(toolName, toolArgs) : remoteResult;
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

  List<(String, Map<String, dynamic>)> _resolveSteps(
    String skillId,
    Map<String, dynamic> arguments,
  ) {
    final rawSteps = arguments['steps'];
    if (rawSteps is List && rawSteps.isNotEmpty) {
      return rawSteps.whereType<Map>().map((raw) {
        final map = raw.cast<String, dynamic>();
        final toolName = (map['toolName'] as String?)?.trim() ?? _defaultToolBySkillId(skillId);
        final args = Map<String, dynamic>.from(
          map['toolArgs'] as Map? ?? const <String, dynamic>{},
        );
        return (toolName, args);
      }).toList(growable: false);
    }
    final singleTool = (arguments['toolName'] as String?) ?? _defaultToolBySkillId(skillId);
    final singleArgs = Map<String, dynamic>.from(arguments['toolArgs'] as Map? ?? arguments);
    return <(String, Map<String, dynamic>)>[(singleTool, singleArgs)];
  }

  String _defaultToolBySkillId(String skillId) {
    if (skillId.contains('search')) return 'web_search';
    if (skillId.contains('photo') || skillId.contains('gallery')) return 'media_gallery';
    return 'local_context';
  }
}
