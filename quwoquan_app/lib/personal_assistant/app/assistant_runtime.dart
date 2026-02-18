import 'package:quwoquan_app/personal_assistant/engine/agent_loop.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/model_config.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/intent_bridge/android_intent_adapter.dart';
import 'package:quwoquan_app/personal_assistant/intent_bridge/ios_intent_adapter.dart';
import 'package:quwoquan_app/personal_assistant/intent_bridge/method_channel_adapter.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/memory/objectbox_store.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/providers/conversation_retrieval_provider.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/providers/memory_retrieval_provider.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/providers/page_context_retrieval_provider.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/providers/web_retrieval_provider.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_provider.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_router.dart';
import 'package:quwoquan_app/personal_assistant/retrieval/retrieval_service.dart';
import 'package:quwoquan_app/personal_assistant/skills/market/skill_market_service.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_executor.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_loader.dart';
import 'package:quwoquan_app/personal_assistant/tools/intent_bridge_tool.dart';
import 'package:quwoquan_app/personal_assistant/tools/local_context_tool.dart';
import 'package:quwoquan_app/personal_assistant/tools/media_gallery_tool.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/tools/unified_retrieval_tool.dart';
import 'package:quwoquan_app/personal_assistant/tools/websearch_tool.dart';

class AssistantRuntime {
  AssistantRuntime._({
    required this.agentLoop,
    required this.skillMarketService,
    required this.memoryRepository,
    required this.skillLoader,
    required this.skillExecutor,
    required this.llmProvider,
  });

  final PersonalAssistantAgentLoop agentLoop;
  final SkillMarketService skillMarketService;
  final AssistantMemoryRepository memoryRepository;
  final PersonalAssistantSkillLoader skillLoader;
  final PersonalAssistantSkillExecutor skillExecutor;
  final SwitchableAssistantLlmProvider llmProvider;

  /// 供测试使用：使用可注入的存储路径，避免依赖 path_provider 插件。
  static AssistantRuntime createForTest({String? storagePath}) {
    final path =
        storagePath ??
        '${Directory.systemTemp.path}/pa_e2e_${DateTime.now().microsecondsSinceEpoch}/vector_store.json';
    return _create(
      memoryStore: ObjectBoxVectorStore(storagePath: path),
      registerSyncConfig: true,
    );
  }

  static AssistantRuntime createDefault() {
    return _create(
      memoryStore: ObjectBoxVectorStore(),
      registerSyncConfig: true,
    );
  }

  static AssistantRuntime _create({
    required ObjectBoxVectorStore memoryStore,
    required bool registerSyncConfig,
  }) {
    final channelAdapter = MethodChannelAdapter();
    final iosAdapter = IOSIntentAdapter(channelAdapter);
    final androidAdapter = AndroidIntentAdapter(channelAdapter);
    final sessionManager = AssistantSessionManager();
    final memoryRepository = AssistantMemoryRepository(memoryStore);
    final appContentRepository = MockAppContentRepository();
    final retrievalService = AssistentRetrievalService(
      router: const AssistentRetrievalRouter(),
      providers: <AssistentRetrievalProvider>[
        WebRetrievalProvider(),
        MemoryRetrievalProvider(memoryRepository),
        ConversationRetrievalProvider(sessionManager),
        PageContextRetrievalProvider(appContentRepository),
      ],
    );
    final toolRegistry = AssistantToolRegistry()
      ..register(WebSearchTool())
      ..register(UnifiedRetrievalTool(retrievalService))
      ..register(LocalContextTool(channelAdapter))
      ..register(MediaGalleryTool(channelAdapter))
      ..register(
        IntentBridgeTool(
          iosAdapter: iosAdapter,
          androidAdapter: androidAdapter,
        ),
      );
    final switchableProvider = SwitchableAssistantLlmProvider(
      fallbackProvider: const HeuristicLocalLlmProvider(),
    );
    if (registerSyncConfig) {
      final loader = const AssistantModelConfigLoader();
      var configs = loader.loadFromProjectSync();
      if (configs.isEmpty) {
        configs = loader.loadDefaultSync();
      }
      for (final config in configs) {
        switchableProvider.registerRemoteModel(config);
      }
    }
    final runtime = ReactRuntime(
      llmProvider: switchableProvider,
      toolRegistry: toolRegistry,
    );
    final agentLoop = PersonalAssistantAgentLoop(
      runtime,
      sessionManager: sessionManager,
      memoryRepository: memoryRepository,
    );
    final skillLoader = const PersonalAssistantSkillLoader();
    return AssistantRuntime._(
      agentLoop: agentLoop,
      skillMarketService: SkillMarketService(),
      memoryRepository: memoryRepository,
      skillLoader: skillLoader,
      skillExecutor: PersonalAssistantSkillExecutor(
        toolRegistry: toolRegistry,
        iosIntentAdapter: iosAdapter,
        androidIntentAdapter: androidAdapter,
        methodChannelAdapter: channelAdapter,
      ),
      llmProvider: switchableProvider,
    );
  }

  bool switchModel(String modelRef) => llmProvider.switchModel(modelRef);

  List<String> listAvailableModels() => llmProvider.availableModelRefs;

  String? currentModel() => llmProvider.activeModelRef;

  /// 异步加载远程模型配置并注册。优先 bundled asset（App 内 config + .env），再工程目录、应用存储，保证端到端问天气等流程可用。
  Future<void> ensureRemoteConfigLoaded() async {
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
}
