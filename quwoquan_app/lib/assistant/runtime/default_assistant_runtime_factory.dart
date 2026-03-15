import 'dart:io';

import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/intent_bridge/assistant_intent_bridge_runtime.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_agent_loop.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/retrieval/assistant_retrieval_runtime.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_executor.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_runtime.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';

AssistantRuntime createDefaultAssistantRuntime() {
  return _createAssistantRuntime(
    memoryStore: ObjectBoxVectorStore(),
    registerSyncConfig: true,
  );
}

AssistantRuntime createTestAssistantRuntime({String? storagePath}) {
  final path =
      storagePath ??
      '${Directory.systemTemp.path}/assistant_runtime_${DateTime.now().microsecondsSinceEpoch}/vector_store.json';
  return _createAssistantRuntime(
    memoryStore: ObjectBoxVectorStore(storagePath: path),
    registerSyncConfig: true,
  );
}

AssistantRuntime _createAssistantRuntime({
  required ObjectBoxVectorStore memoryStore,
  required bool registerSyncConfig,
}) {
  final channelAdapter = MethodChannelAdapter();
  final iosAdapter = IOSIntentAdapter(channelAdapter);
  final androidAdapter = AndroidIntentAdapter(channelAdapter);
  final sessionManager = AssistantSessionManager();
  final memoryRepository = AssistantMemoryRepository(memoryStore);
  final toolMetadataRegistry = ToolMetadataRegistry();
  final retrievalBroker = LegacyToolRetrievalBroker();
  final toolRegistry =
      AssistantToolRegistry(metadataRegistry: toolMetadataRegistry)
        ..register(WebSearchTool(broker: retrievalBroker))
        ..register(WebFetchTool(broker: retrievalBroker))
        ..register(MemorySearchTool(memoryRepository: memoryRepository))
        ..register(LocalContextTool(channelAdapter))
        ..register(MediaGalleryTool(channelAdapter))
        ..register(
          IntentBridgeTool(
            iosAdapter: iosAdapter,
            androidAdapter: androidAdapter,
          ),
        )
        ..register(SchedulerTool(channelAdapter))
        ..register(DeepLinkTool())
        ..register(AppActionTool());
  final templateRuntime = PromptTemplateRuntime(registry: TemplateRegistry());
  final llmProvider = SwitchableAssistantLlmProvider(
    fallbackProvider: const HeuristicLocalLlmProvider(),
    templateRuntime: templateRuntime,
    toolMetadataRegistry: toolMetadataRegistry,
    plannerTemplateVersion: '',
  );
  if (registerSyncConfig) {
    final loader = const AssistantModelConfigLoader();
    var configs = loader.loadFromProjectSync();
    if (configs.isEmpty) {
      configs = loader.loadDefaultSync();
    }
    for (final config in configs) {
      llmProvider.registerRemoteModel(config);
    }
  }
  final reactRuntime = ReactRuntime(
    llmProvider: llmProvider,
    toolRegistry: toolRegistry,
    toolMetadataRegistry: toolMetadataRegistry,
  );
  final agentLoop = AssistantAgentLoop(
    runtime: reactRuntime,
    sessionManager: sessionManager,
    memoryRepository: memoryRepository,
    toolMetadataRegistry: toolMetadataRegistry,
  );
  final skillLoader = const PersonalAssistantSkillLoader();
  final skillMarketService = AssistantSkillMarketService(loader: skillLoader);
  final skillExecutor = AssistantSkillExecutor(
    toolRegistry: toolRegistry,
    iosIntentAdapter: iosAdapter,
    androidIntentAdapter: androidAdapter,
    methodChannelAdapter: channelAdapter,
  );

  return AssistantRuntime(
    skillMarketService: skillMarketService,
    skillLoader: skillLoader,
    runHandler: agentLoop.run,
    classifyDomainHandler: agentLoop.classifyDomain,
    listSessionsHandler: agentLoop.listSessions,
    sessionDetailHandler: agentLoop.sessionDetail,
    switchSessionHandler: agentLoop.switchSession,
    invokeSkillHandler: ({
      required skill,
      required arguments,
      String deviceProfile = 'mobile',
    }) {
      return skillExecutor.execute(
        skill: skill,
        arguments: arguments,
        deviceProfile: deviceProfile,
      );
    },
    ensureRemoteConfigLoadedHandler: () => _ensureRemoteConfigLoaded(llmProvider),
    switchModelHandler: llmProvider.switchModel,
    listAvailableModelsHandler: () => llmProvider.availableModelRefs,
    selectedModelsHandler: () => llmProvider.selectedModelRefs,
    setSelectedModelsHandler: llmProvider.setSelectedModels,
    currentModelHandler: () => llmProvider.activeModelRef,
  );
}

Future<void> _ensureRemoteConfigLoaded(
  SwitchableAssistantLlmProvider llmProvider,
) async {
  final loader = const AssistantModelConfigLoader();
  var configs = await loader.loadDefault();
  if (configs.isEmpty) {
    configs = await loader.loadFromAppStorage();
  }
  if (configs.isEmpty) return;
  for (final config in configs) {
    llmProvider.registerRemoteModel(config);
  }
}
