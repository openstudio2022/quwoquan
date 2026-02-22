import 'package:quwoquan_app/personal_assistant/app/assistant_runtime.dart';
import 'package:quwoquan_app/personal_assistant/observability/logging/app_log_exporter.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class AssistantGateway {
  AssistantGateway(this._runtime);

  final AssistantRuntime _runtime;

  Future<AssistantRunResponse> run(AssistantRunRequest request) async {
    return _runtime.agentLoop.run(request);
  }

  Future<String> classifyDomain(
    String query,
    Map<String, dynamic> contextScopeHint,
  ) async {
    return _runtime.agentLoop.classifyDomain(query, contextScopeHint);
  }

  Future<AssistantRunResponse> runWithTraceStream(
    AssistantRunRequest request, {
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    return _runtime.agentLoop.run(request, onTraceEvent: onTraceEvent);
  }

  Future<AppLogExportResult> exportLogsToWorkspace({
    String targetDirectory = AppLogExporter.defaultWorkspaceTarget,
  }) {
    final exporter = AppLogExporter();
    return exporter.exportToWorkspace(targetDirectory: targetDirectory);
  }

  Future<List<PersonalAssistantSkillInfo>> listSkills() {
    return _runtime.skillMarketService.listSkills();
  }

  Future<List<PersonalAssistantSkillInfo>> listSkillsByChannel(
    String channel,
  ) async {
    final skills = await _runtime.skillMarketService.listSkills();
    return skills
        .where((s) => s.manifest.channelScopes.contains(channel))
        .toList(growable: false);
  }

  Future<void> setSkillEnabled(String skillId, bool enabled) {
    return _runtime.skillMarketService.setSkillEnabled(skillId, enabled);
  }

  List<String> listAvailableModels() => _runtime.listAvailableModels();

  String? currentModel() => _runtime.currentModel();

  bool switchModel(String modelRef) => _runtime.switchModel(modelRef);

  Future<List<Map<String, dynamic>>> listSessions() async {
    return _runtime.agentLoop.listSessions();
  }

  Future<Map<String, dynamic>?> sessionDetail(String sessionId) async {
    return _runtime.agentLoop.sessionDetail(sessionId);
  }

  Future<AssistantToolResult> invokeSkill({
    required String skillId,
    required Map<String, dynamic> arguments,
    String deviceProfile = 'mobile',
    String channel = 'app',
  }) async {
    final marketSkills = await _runtime.skillMarketService.listSkills();
    PersonalAssistantSkillInfo? skillInfo;
    for (final item in marketSkills) {
      if (item.manifest.id == skillId) {
        skillInfo = item;
        break;
      }
    }
    if (skillInfo == null) {
      return const AssistantToolResult(
        success: false,
        message: 'Skill not found',
        errorCode: AssistantErrorCode.skillNotFound,
        degraded: true,
      );
    }
    if (!skillInfo.enabled && !skillInfo.isDefaultFree) {
      return const AssistantToolResult(
        success: false,
        message: 'Skill requires subscription',
        errorCode: AssistantErrorCode.permissionDenied,
        degraded: true,
      );
    }
    if (!skillInfo.manifest.channelScopes.contains(channel)) {
      return AssistantToolResult(
        success: false,
        message: 'Skill unavailable on channel: $channel',
        errorCode: AssistantErrorCode.permissionDenied,
        degraded: true,
      );
    }
    if (!skillInfo.manifest.deviceScopes.contains(deviceProfile)) {
      return AssistantToolResult(
        success: false,
        message: 'Skill unavailable on device profile: $deviceProfile',
        errorCode: AssistantErrorCode.permissionDenied,
        degraded: true,
      );
    }

    final skills = await _runtime.skillLoader.loadBundledSkills();
    final skill = skills.firstWhere(
      (s) => s.id == skillId,
      orElse: () => const PersonalAssistantSkillManifest(
        id: '',
        name: '',
        description: '',
        version: '1.0.0',
        executionTarget: 'tool_chain',
        parametersSchema: <String, dynamic>{},
      ),
    );
    if (skill.id.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: 'Skill not found',
        errorCode: AssistantErrorCode.skillNotFound,
        degraded: true,
      );
    }
    return _runtime.skillExecutor.execute(
      skill: skill,
      arguments: arguments,
      deviceProfile: deviceProfile,
    );
  }
}
