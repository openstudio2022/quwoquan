import 'package:quwoquan_app/assistant/observability/logging/app_log_exporter.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/assistant/tools/tool_schema.dart';

class AssistantGateway {
  AssistantGateway(this._runtime);

  final AssistantRuntime _runtime;

  Future<AssistantRunResponse> run(AssistantRunRequest request) async {
    return _runtime.run(request);
  }

  Future<String> classifyDomain(
    String query,
    Map<String, dynamic> contextScopeHint,
  ) async {
    return _runtime.classifyDomain(query, contextScopeHint);
  }

  Future<AssistantRunResponse> runWithTraceStream(
    AssistantRunRequest request, {
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    return _runtime.run(request, onTraceEvent: onTraceEvent);
  }

  Future<AppLogExportResult> exportLogsToWorkspace({
    String targetDirectory = AppLogExporter.defaultWorkspaceTarget,
  }) {
    final exporter = AppLogExporter();
    return exporter.exportToWorkspace(targetDirectory: targetDirectory);
  }

  Future<List<PersonalAssistantSkillInfo>> listSkills() {
    return _runtime.listSkills();
  }

  Future<List<PersonalAssistantSkillInfo>> listSkillsByChannel(
    String channel,
  ) async {
    final skills = await _runtime.listSkills();
    return skills
        .where((s) => s.manifest.channelScopes.contains(channel))
        .toList(growable: false);
  }

  Future<void> setSkillEnabled(String skillId, bool enabled) {
    return _runtime.setSkillEnabled(skillId, enabled);
  }

  List<String> listAvailableModels() => _runtime.listAvailableModels();

  Future<void> ensureRemoteConfigLoaded() {
    return _runtime.ensureRemoteConfigLoaded();
  }

  List<String> selectedModels() => _runtime.selectedModels();

  bool setSelectedModels(List<String> modelRefs) =>
      _runtime.setSelectedModels(modelRefs);

  String? currentModel() => _runtime.currentModel();

  bool switchModel(String modelRef) => _runtime.switchModel(modelRef);

  Future<List<Map<String, dynamic>>> listSessions() async {
    return _runtime.listSessions();
  }

  Future<Map<String, dynamic>?> sessionDetail(String sessionId) async {
    return _runtime.sessionDetail(sessionId);
  }

  Future<void> switchSession(String sessionId) {
    return _runtime.switchSession(sessionId);
  }

  Future<AssistantToolResult> invokeSkill({
    required String skillId,
    required Map<String, dynamic> arguments,
    String deviceProfile = 'mobile',
    String channel = 'app',
  }) async {
    final marketSkills = await _runtime.listSkills();
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

    final skills = await _runtime.loadBundledSkills();
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
    return _runtime.invokeSkill(
      skill: skill,
      arguments: arguments,
      deviceProfile: deviceProfile,
    );
  }
}
