import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_agent_loop.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/retrieval/assistant_retrieval_runtime.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_runtime.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:test/test.dart';

Future<AssistantRuntime> _buildLiveRuntime({
  required String storageRoot,
}) async {
  final sessionManager = AssistantSessionManager(
    storagePath: '$storageRoot/sessions.json',
  );
  await sessionManager.load();
  final memoryRepository = AssistantMemoryRepository(
    ObjectBoxVectorStore(storagePath: '$storageRoot/vector_store.json'),
  );
  final toolMetadataRegistry = ToolMetadataRegistry();
  final retrievalBroker = ToolRetrievalBroker();
  final toolRegistry =
      AssistantToolRegistry(metadataRegistry: toolMetadataRegistry)
        ..register(WebSearchTool(broker: retrievalBroker))
        ..register(WebFetchTool(broker: retrievalBroker))
        ..register(MemorySearchTool(memoryRepository: memoryRepository));
  final templateRuntime = PromptTemplateRuntime(registry: TemplateRegistry());
  final llmProvider = SwitchableAssistantLlmProvider(
    fallbackProvider: const HeuristicLocalLlmProvider(),
    templateRuntime: templateRuntime,
    toolMetadataRegistry: toolMetadataRegistry,
    plannerTemplateVersion: '',
  );
  final loader = const AssistantModelConfigLoader();
  var configs = loader.loadFromProjectSync();
  if (configs.isEmpty) {
    configs = loader.loadDefaultSync();
  }
  for (final config in configs) {
    llmProvider.registerRemoteModel(config);
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
  const skillLoader = PersonalAssistantSkillLoader();
  final skillMarketService = AssistantSkillMarketService(loader: skillLoader);

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
        }) async {
          return const AssistantToolResult(
            success: false,
            message: 'invokeSkill is not enabled in live vm test',
            errorCode: AssistantErrorCode.unsupportedTarget,
            degraded: true,
          );
        },
    ensureRemoteConfigLoadedHandler: () async {},
    switchModelHandler: llmProvider.switchModel,
    listAvailableModelsHandler: () => llmProvider.availableModelRefs,
    selectedModelsHandler: () => llmProvider.selectedModelRefs,
    setSelectedModelsHandler: llmProvider.setSelectedModels,
    currentModelHandler: () => llmProvider.activeModelRef,
  );
}

void main() {
  group('Remote live vm e2e weather', () {
    test(
      'switch to preferred remote model and run weather direct answer',
      skip: const bool.fromEnvironment('LIVE_TEST', defaultValue: false)
          ? null
          : 'live test：需要真实远端模型凭证与网络，设置 LIVE_TEST=true 启用',
      () async {
        WidgetsFlutterBinding.ensureInitialized();
        final tempDir = await Directory.systemTemp.createTemp(
          'assistant_live_minimax_vm_',
        );
        addTearDown(() async {
          if (await tempDir.exists()) {
            await tempDir.delete(recursive: true);
          }
        });
        final runtime = await _buildLiveRuntime(storageRoot: tempDir.path);
        final gateway = AssistantGateway(runtime);

        final availableModels = gateway.listAvailableModels();
        expect(
          availableModels,
          isNotEmpty,
          reason: 'runtime 应至少暴露一个可选远端模型',
        );
        final preferredRef = availableModels.first;
        expect(
          gateway.switchModel(preferredRef),
          isTrue,
          reason: '首选远端模型应可在 runtime 中切换',
        );
        expect(gateway.setSelectedModels(<String>[preferredRef]), isTrue);

        final weather = await gateway.run(
          AssistantRunRequest(
            sessionId:
                'minimax_live_weather_${DateTime.now().microsecondsSinceEpoch}',
            userId: 'test_user',
            channel: 'app',
            deviceProfile: 'mobile',
            messages: const <AssistantRunMessage>[
              AssistantRunMessage(
                role: 'user',
                content: '深圳今天天气怎么样？请给我穿衣和出行建议。',
              ),
            ],
          ),
        );
        final weatherRoutingDiagnostics =
            (weather.structuredResponse['phaseOneRoutingDiagnostics'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final weatherUsageStats =
            (weather.structuredResponse['uiUsageStats'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final weatherPrimarySkill =
            (weather.structuredResponse['primarySkill'] as String?) ?? '';
        expect(weather.finalText.trim().isNotEmpty, isTrue);
        expect(
          weather.degraded,
          isFalse,
          reason:
              'live provider 应返回非降级结果；若远端账号不可用，请先更换可用 key 或修复本地模型凭证来源。',
        );
        expect((weather.errorCode ?? '').trim(), isEmpty);
        expect(weatherPrimarySkill, equals('weather'));
        expect(
          weatherRoutingDiagnostics['route'],
          equals('phase_one_direct_answer'),
          reason: '天气 live 路由应直接命中 phase_one_direct_answer',
        );
        expect(
          weatherRoutingDiagnostics['phaseOneNextAction'],
          equals('answer'),
        );
        expect(
          weatherRoutingDiagnostics['phaseOneMessageKind'],
          equals('answer'),
        );
        expect(
          weatherRoutingDiagnostics['phaseOneHasRenderableContent'],
          equals(true),
        );
        expect(
          (weatherUsageStats['modelCallCount'] as num?)?.toInt() ?? 0,
          lessThanOrEqualTo(3),
          reason: '简单天气问句应在有限模型调用内完成收敛',
        );
      },
      timeout: const Timeout(Duration(minutes: 2)),
    );
  });
}
