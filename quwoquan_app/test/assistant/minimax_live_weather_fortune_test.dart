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

String _resolveDisplayUnderstandingSummary(
  String userFacingSummary,
  List<dynamic> resolutionItems,
) {
  final summary = userFacingSummary.trim();
  final details = <String>[];
  for (final item in resolutionItems) {
    if (item is! Map) continue;
    final visible = item['visibleInUnderstanding'] as bool? ?? true;
    if (!visible) continue;
    final detail = (item['detail'] as String?)?.trim() ?? '';
    final resolved = (item['resolvedValue'] as String?)?.trim() ?? '';
    final text = detail.isNotEmpty ? detail : resolved;
    if (text.isNotEmpty) details.add(text);
  }
  if (summary.isEmpty && details.isEmpty) return '';
  if (details.isEmpty) return summary;
  if (summary.isEmpty) return details.join('；');
  final uncovered = details.where((d) {
    final normalized = d.replaceAll(RegExp(r'\s+'), '');
    final normalizedSummary = summary.replaceAll(RegExp(r'\s+'), '');
    if (normalized.length <= 6) return !normalizedSummary.contains(normalized);
    final datePattern = RegExp(r'\d{4}[-年/]\d{1,2}[-月/日]?\d{0,2}');
    for (final match in datePattern.allMatches(normalized)) {
      if (!normalizedSummary.contains(match.group(0)!)) return true;
    }
    return false;
  }).toList();
  if (uncovered.isEmpty) return summary;
  final base = summary.endsWith('。') || summary.endsWith('.')
      ? summary.substring(0, summary.length - 1)
      : summary;
  return '$base。${uncovered.join('；')}。';
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
        final route =
            weatherRoutingDiagnostics['route'] as String? ?? '';
        expect(
          route == 'phase_one_direct_answer' || route == 'formal_synthesis',
          isTrue,
          reason:
              '天气 live 路由应命中 phase_one_direct_answer 或 formal_synthesis，'
              '实际: $route',
        );
        expect(
          (weatherUsageStats['modelCallCount'] as num?)?.toInt() ?? 0,
          lessThanOrEqualTo(5),
          reason: '天气问句应在有限模型调用内完成收敛',
        );

        final understandingMap =
            (weather.structuredResponse['understandingSnapshot'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final userFacingSummary =
            (understandingMap['userFacingSummary'] as String?)?.trim() ?? '';
        final resolutionItems =
            (understandingMap['resolutionItems'] as List?) ??
            const <dynamic>[];

        final displayProjectionSummary = _resolveDisplayUnderstandingSummary(
          userFacingSummary,
          resolutionItems,
        );
        expect(
          displayProjectionSummary.length,
          greaterThanOrEqualTo(10),
          reason:
              '理解阶段叙事不应过于简短（实际: "$displayProjectionSummary"）',
        );
        expect(
          displayProjectionSummary,
          contains('深圳'),
          reason:
              '理解阶段叙事必须包含区域信息（实际: "$displayProjectionSummary"）',
        );

        final retrievalMap =
            (weather.structuredResponse['retrievalProcessing'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final processingSummary =
            (retrievalMap['processingSummary'] as String?)?.trim() ?? '';
        if (processingSummary.isNotEmpty) {
          const forbiddenPhrases = <String>[
            '处理了',
            '接纳了',
            '命中度',
          ];
          for (final phrase in forbiddenPhrases) {
            expect(
              processingSummary.contains(phrase),
              isFalse,
              reason:
                  'processingSummary 不应包含系统过程句 "$phrase"'
                  '（实际: "$processingSummary"）',
            );
          }
        }
      },
      timeout: const Timeout(Duration(minutes: 2)),
    );
  });
}
