import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_runtime.dart';
import 'package:quwoquan_app/assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/assistant/tools/tool_schema.dart';
import 'package:quwoquan_app/assistant_runtime_legacy_bridge.dart';

typedef AssistantTraceEventSink = void Function(AssistantTraceEvent event);
typedef AssistantRunHandler =
    Future<AssistantRunResponse> Function(
      AssistantRunRequest request, {
      AssistantTraceEventSink? onTraceEvent,
    });
typedef AssistantClassifyDomainHandler =
    Future<String> Function(String query, Map<String, dynamic> contextScopeHint);
typedef AssistantListSessionsHandler = Future<List<Map<String, dynamic>>> Function();
typedef AssistantSessionDetailHandler =
    Future<Map<String, dynamic>?> Function(String sessionId);
typedef AssistantSwitchSessionHandler = Future<void> Function(String sessionId);
typedef AssistantInvokeSkillHandler =
    Future<AssistantToolResult> Function({
      required PersonalAssistantSkillManifest skill,
      required Map<String, dynamic> arguments,
      String deviceProfile,
    });
typedef AssistantEnsureRemoteConfigLoadedHandler = Future<void> Function();
typedef AssistantSwitchModelHandler = bool Function(String modelRef);
typedef AssistantListModelsHandler = List<String> Function();
typedef AssistantSetSelectedModelsHandler =
    bool Function(List<String> modelRefs);
typedef AssistantCurrentModelHandler = String? Function();

class AssistantRuntime {
  AssistantRuntime({
    required AssistantSkillMarketService skillMarketService,
    required PersonalAssistantSkillLoader skillLoader,
    required AssistantRunHandler runHandler,
    required AssistantClassifyDomainHandler classifyDomainHandler,
    required AssistantListSessionsHandler listSessionsHandler,
    required AssistantSessionDetailHandler sessionDetailHandler,
    required AssistantSwitchSessionHandler switchSessionHandler,
    required AssistantInvokeSkillHandler invokeSkillHandler,
    required AssistantEnsureRemoteConfigLoadedHandler
    ensureRemoteConfigLoadedHandler,
    required AssistantSwitchModelHandler switchModelHandler,
    required AssistantListModelsHandler listAvailableModelsHandler,
    required AssistantListModelsHandler selectedModelsHandler,
    required AssistantSetSelectedModelsHandler setSelectedModelsHandler,
    required AssistantCurrentModelHandler currentModelHandler,
  }) : _skillMarketService = skillMarketService,
       _skillLoader = skillLoader,
       _runHandler = runHandler,
       _classifyDomainHandler = classifyDomainHandler,
       _listSessionsHandler = listSessionsHandler,
       _sessionDetailHandler = sessionDetailHandler,
       _switchSessionHandler = switchSessionHandler,
       _invokeSkillHandler = invokeSkillHandler,
       _ensureRemoteConfigLoadedHandler = ensureRemoteConfigLoadedHandler,
       _switchModelHandler = switchModelHandler,
       _listAvailableModelsHandler = listAvailableModelsHandler,
       _selectedModelsHandler = selectedModelsHandler,
       _setSelectedModelsHandler = setSelectedModelsHandler,
       _currentModelHandler = currentModelHandler;

  final AssistantSkillMarketService _skillMarketService;
  final PersonalAssistantSkillLoader _skillLoader;
  final AssistantRunHandler _runHandler;
  final AssistantClassifyDomainHandler _classifyDomainHandler;
  final AssistantListSessionsHandler _listSessionsHandler;
  final AssistantSessionDetailHandler _sessionDetailHandler;
  final AssistantSwitchSessionHandler _switchSessionHandler;
  final AssistantInvokeSkillHandler _invokeSkillHandler;
  final AssistantEnsureRemoteConfigLoadedHandler
  _ensureRemoteConfigLoadedHandler;
  final AssistantSwitchModelHandler _switchModelHandler;
  final AssistantListModelsHandler _listAvailableModelsHandler;
  final AssistantListModelsHandler _selectedModelsHandler;
  final AssistantSetSelectedModelsHandler _setSelectedModelsHandler;
  final AssistantCurrentModelHandler _currentModelHandler;

  static AssistantRuntime createDefault() {
    return createAssistantRuntimeLegacyBridge();
  }

  static AssistantRuntime createForTest({String? storagePath}) {
    return createAssistantRuntimeLegacyBridge(storagePath: storagePath);
  }

  Future<AssistantRunResponse> run(
    AssistantRunRequest request, {
    AssistantTraceEventSink? onTraceEvent,
  }) {
    return _runHandler(request, onTraceEvent: onTraceEvent);
  }

  Future<String> classifyDomain(
    String query,
    Map<String, dynamic> contextScopeHint,
  ) {
    return _classifyDomainHandler(query, contextScopeHint);
  }

  Future<List<Map<String, dynamic>>> listSessions() {
    return _listSessionsHandler();
  }

  Future<Map<String, dynamic>?> sessionDetail(String sessionId) {
    return _sessionDetailHandler(sessionId);
  }

  Future<void> switchSession(String sessionId) {
    return _switchSessionHandler(sessionId);
  }

  Future<List<PersonalAssistantSkillInfo>> listSkills() {
    return _skillMarketService.listSkills();
  }

  Future<void> setSkillEnabled(String skillId, bool enabled) {
    return _skillMarketService.setSkillEnabled(skillId, enabled);
  }

  Future<List<PersonalAssistantSkillManifest>> loadBundledSkills() {
    return _skillLoader.loadBundledSkills();
  }

  Future<AssistantToolResult> invokeSkill({
    required PersonalAssistantSkillManifest skill,
    required Map<String, dynamic> arguments,
    String deviceProfile = 'mobile',
  }) {
    return _invokeSkillHandler(
      skill: skill,
      arguments: arguments,
      deviceProfile: deviceProfile,
    );
  }

  Future<void> ensureRemoteConfigLoaded() {
    return _ensureRemoteConfigLoadedHandler();
  }

  bool switchModel(String modelRef) => _switchModelHandler(modelRef);

  List<String> listAvailableModels() => _listAvailableModelsHandler();

  List<String> selectedModels() => _selectedModelsHandler();

  bool setSelectedModels(List<String> modelRefs) {
    return _setSelectedModelsHandler(modelRefs);
  }

  String? currentModel() => _currentModelHandler();
}
