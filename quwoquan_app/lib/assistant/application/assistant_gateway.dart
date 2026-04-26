import 'package:quwoquan_app/assistant/observability/logging/app_log_exporter.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/assistant/tools/tool_schema.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

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

  Future<List<AssistantSessionDescriptor>> listSessions() async {
    return _runtime.listSessions();
  }

  Future<AssistantSessionWireDetail?> sessionDetail(String sessionId) async {
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
      return _skillFailureResult(
        code: 'ASSISTANT.NOT_FOUND.skill_not_found',
        kind: RuntimeFailureKind.notFound,
        reason: 'skill_not_found',
        skillId: skillId,
      );
    }
    if (!skillInfo.enabled && !skillInfo.isDefaultFree) {
      return _skillFailureResult(
        code: 'ASSISTANT.PERMISSION.skill_subscription_required',
        kind: RuntimeFailureKind.permission,
        nature: RuntimeFailureNature.requiresUserAction,
        reason: 'skill_subscription_required',
        skillId: skillId,
      );
    }
    if (!skillInfo.manifest.channelScopes.contains(channel)) {
      return _skillFailureResult(
        code: 'ASSISTANT.PERMISSION.skill_channel_unavailable',
        kind: RuntimeFailureKind.permission,
        nature: RuntimeFailureNature.permanent,
        reason: 'skill_channel_unavailable',
        skillId: skillId,
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'channel', value: channel),
        ],
      );
    }
    if (!skillInfo.manifest.deviceScopes.contains(deviceProfile)) {
      return _skillFailureResult(
        code: 'ASSISTANT.PERMISSION.skill_device_unavailable',
        kind: RuntimeFailureKind.permission,
        nature: RuntimeFailureNature.permanent,
        reason: 'skill_device_unavailable',
        skillId: skillId,
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'deviceProfile', value: deviceProfile),
        ],
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
      return _skillFailureResult(
        code: 'ASSISTANT.NOT_FOUND.skill_not_found',
        kind: RuntimeFailureKind.notFound,
        reason: 'skill_not_found',
        skillId: skillId,
      );
    }
    return _runtime.invokeSkill(
      skill: skill,
      arguments: arguments,
      deviceProfile: deviceProfile,
    );
  }

  AssistantToolResult _skillFailureResult({
    required String code,
    required RuntimeFailureKind kind,
    required String reason,
    required String skillId,
    RuntimeFailureNature nature = RuntimeFailureNature.permanent,
    List<RuntimeContextAttribute> attributes =
        const <RuntimeContextAttribute>[],
  }) {
    final sourceErrorCode = kind == RuntimeFailureKind.notFound
        ? AssistantErrorCode.skillNotFound
        : AssistantErrorCode.permissionDenied;
    return AssistantToolResult(
      success: false,
      message: reason,
      errorCode: sourceErrorCode,
      degraded: true,
      runtimeFailure: RuntimeFailure(
        code: code,
        origin: RuntimeFailureOrigin.system,
        kind: kind,
        nature: nature,
        location: const RuntimeFailureLocation(
          businessObject: 'assistant_skill',
          functionModule: 'assistant_gateway',
        ),
        context: RuntimeFailureContext(
          attributes: <RuntimeContextAttribute>[
            RuntimeContextAttribute(key: 'skillId', value: skillId),
            ...attributes,
          ],
        ),
      ),
    );
  }
}
