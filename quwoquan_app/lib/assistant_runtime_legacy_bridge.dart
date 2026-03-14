import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_runtime.dart';
import 'package:quwoquan_app/assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/assistant/tools/tool_schema.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_runtime.dart'
    as legacy_runtime;
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart'
    as legacy_request;
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart'
    as legacy_skill;

AssistantRuntime createAssistantRuntimeLegacyBridge({String? storagePath}) {
  final legacy = storagePath == null
      ? legacy_runtime.AssistantRuntime.createDefault()
      : legacy_runtime.AssistantRuntime.createForTest(storagePath: storagePath);
  final skillLoader = const PersonalAssistantSkillLoader();
  final skillMarketService = AssistantSkillMarketService(loader: skillLoader);

  return AssistantRuntime(
    skillMarketService: skillMarketService,
    skillLoader: skillLoader,
    runHandler: (request, {onTraceEvent}) async {
      final response = await legacy.agentLoop.run(
        legacy_request.AssistantRunRequest.fromJson(request.toJson()),
        onTraceEvent: onTraceEvent == null
            ? null
            : (legacyTraceEvent) => onTraceEvent(
                AssistantTraceEvent.fromJson(legacyTraceEvent.toJson()),
              ),
      );
      return AssistantRunResponse.fromJson(response.toJson());
    },
    classifyDomainHandler: (query, contextScopeHint) {
      return legacy.agentLoop.classifyDomain(query, contextScopeHint);
    },
    listSessionsHandler: () async {
      final sessions = await legacy.agentLoop.listSessions();
      return sessions
          .map((item) => Map<String, dynamic>.from(item))
          .toList(growable: false);
    },
    sessionDetailHandler: (sessionId) async {
      final detail = await legacy.agentLoop.sessionDetail(sessionId);
      if (detail == null) return null;
      return Map<String, dynamic>.from(detail);
    },
    switchSessionHandler: legacy.agentLoop.switchSession,
    invokeSkillHandler: ({
      required PersonalAssistantSkillManifest skill,
      required Map<String, dynamic> arguments,
      String deviceProfile = 'mobile',
    }) async {
      final result = await legacy.skillExecutor.execute(
        skill: legacy_skill.PersonalAssistantSkillManifest.fromMap(
          _toLegacySkillManifestMap(skill),
        ),
        arguments: arguments,
        deviceProfile: deviceProfile,
      );
      return AssistantToolResult.fromJson(result.toJson());
    },
    ensureRemoteConfigLoadedHandler: legacy.ensureRemoteConfigLoaded,
    switchModelHandler: legacy.switchModel,
    listAvailableModelsHandler: legacy.listAvailableModels,
    selectedModelsHandler: legacy.selectedModels,
    setSelectedModelsHandler: legacy.setSelectedModels,
    currentModelHandler: legacy.currentModel,
  );
}

Map<String, dynamic> _toLegacySkillManifestMap(
  PersonalAssistantSkillManifest skill,
) {
  return <String, dynamic>{
    'id': skill.id,
    'name': skill.name,
    'description': skill.description,
    'version': skill.version,
    'executionTarget': skill.executionTarget,
    'parametersSchema': skill.parametersSchema,
    'permissions': skill.permissions,
    'visibility': skill.visibility,
    'category': skill.category,
    'tier': skill.tier,
    'channelScopes': skill.channelScopes,
    'deviceScopes': skill.deviceScopes,
    'versionPolicy': skill.versionPolicy,
    'permissionScopes': skill.permissionScopes,
    'defaultEnabled': skill.defaultEnabled,
    'allowedTools': skill.allowedTools,
    'triggerKeywords': skill.triggerKeywords,
    'domainId': skill.domainId,
    'toolChainProfile': skill.toolChainProfile,
    'skillInstructionMarkdown': skill.skillInstructionMarkdown,
    'frontmatter': skill.frontmatter,
    'retrievalPolicy': skill.retrievalPolicy,
    'executionShell': skill.executionShell.toJson(),
  };
}
