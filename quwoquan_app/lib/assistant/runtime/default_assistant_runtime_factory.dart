import 'dart:io';

import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/intent_bridge/assistant_intent_bridge_runtime.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_agent_loop.dart';
import 'package:quwoquan_app/assistant/session/assistant_session_manager.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/retrieval/assistant_retrieval_runtime.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_executor.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_runtime.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/search_cache.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/integration/integration_repository.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';

final SearchResultCache _sharedAssistantSearchCache = SearchResultCache();

AssistantRuntime createDefaultAssistantRuntime() {
  return _createAssistantRuntime(
    memoryStore: ObjectBoxVectorStore(),
    registerSyncConfig: true,
    searchCache: _sharedAssistantSearchCache,
  );
}

AssistantRuntime createTestAssistantRuntime({String? storagePath}) {
  final path =
      storagePath ??
      '${Directory.systemTemp.path}/assistant_runtime_${DateTime.now().microsecondsSinceEpoch}/vector_store.json';
  return _createAssistantRuntime(
    memoryStore: ObjectBoxVectorStore(storagePath: path),
    registerSyncConfig: true,
    searchCache: SearchResultCache(),
  );
}

AssistantRuntime _createAssistantRuntime({
  required ObjectBoxVectorStore memoryStore,
  required bool registerSyncConfig,
  required SearchResultCache searchCache,
}) {
  final channelAdapter = MethodChannelAdapter();
  final iosAdapter = IOSIntentAdapter(channelAdapter);
  final androidAdapter = AndroidIntentAdapter(channelAdapter);
  final sessionManager = AssistantSessionManager();
  final memoryRepository = AssistantMemoryRepository(memoryStore);
  final toolMetadataRegistry = ToolMetadataRegistry();
  final retrievalBroker = ToolRetrievalBroker();
  final webSearchTool = WebSearchTool(
    broker: retrievalBroker,
    searchCache: searchCache,
  );
  final conversationCache = ConversationCacheService();
  final chatRepository = RemoteChatRepository();
  final circleRepository = RemoteCircleRepository();
  final contentRepository = RemoteContentRepository();
  final homepageRepository = RemoteHomepageRepository();
  final integrationRepository = RemoteIntegrationRepository();
  final userRepository = RemoteUserRepository();
  final localChatSearchStore = LocalChatSearchStore.shared;
  final localCircleGroupSnapshotStore = LocalCircleGroupSnapshotStore.shared;
  final localChatSearchSyncService = LocalChatSearchSyncService(
    chatRepository: chatRepository,
    conversationCache: conversationCache,
    store: localChatSearchStore,
    personaContextLoader: userRepository.getActivePersonaContext,
  );
  final unifiedSearchRepository = buildAppSearchRepository(
    circleRepository: circleRepository,
    contentRepository: contentRepository,
    homepageRepository: homepageRepository,
    integrationRepository: integrationRepository,
    localChatSearchStore: localChatSearchStore,
    localChatSearchSyncService: localChatSearchSyncService,
    localCircleGroupSnapshotStore: localCircleGroupSnapshotStore,
    personaContextLoader: userRepository.getActivePersonaContext,
  );
  final toolRegistry =
      AssistantToolRegistry(metadataRegistry: toolMetadataRegistry)
        ..register(AppSearchTool(searchRepository: unifiedSearchRepository))
        ..register(
          SearchTool(
            searchRepository: unifiedSearchRepository,
            webSearchTool: webSearchTool,
          ),
        )
        ..register(webSearchTool)
        ..register(WebFetchTool(broker: retrievalBroker))
        ..register(MemorySearchTool(memoryRepository: memoryRepository))
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
    invokeSkillHandler:
        ({
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
    ensureRemoteConfigLoadedHandler: () =>
        _ensureRemoteConfigLoaded(llmProvider),
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
