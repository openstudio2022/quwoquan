import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_agent_loop.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_runtime.dart';
import 'package:quwoquan_app/assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:quwoquan_app/assistant/tools/tool_schema.dart';

void main() {
  group('Assistant run E2E', () {
    setUpAll(_installPathProviderMock);

    test('问「深圳天气怎么样」能拿到回复且不出现「未配置可用模型」', () async {
      final runtime = AssistantRuntime.createForTest();
      await runtime.ensureRemoteConfigLoaded();
      final gateway = AssistantGateway(runtime);
      final sessionId =
          'assistant_e2e_test_${DateTime.now().millisecondsSinceEpoch}';

      final response = await gateway.run(
        AssistantRunRequest(
          sessionId: sessionId,
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );

      expect(response.finalText, isNotEmpty);
      expect(
        response.finalText.contains('未配置可用模型'),
        isFalse,
        reason: '小艺私人助手对话中不应展示「未配置可用模型」，应走本地启发式或远程模型',
      );
      expect(
        response.displayMarkdown.trim().isNotEmpty ||
            response.displayPlainText.trim().isNotEmpty,
        isTrue,
      );
      expect(
        '${response.displayMarkdown} ${response.displayPlainText}'
            .contains('contractVersion'),
        isFalse,
      );
      final journey = response.runArtifacts?.journey;
      expect(journey, isNotNull);
      expect(
        journey!.entries.isNotEmpty || journey.stages.isNotEmpty,
        isTrue,
        reason: '简单事实问题也应生成统一用户旅程',
      );
    });

    test('本地 stub runtime 下天气问句应保留 weather 域并产出可展示的 phase-one answer', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_weather_stub_e2e_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final runtime = await _buildDeterministicRuntime(
        llmProvider: const _StableWeatherDirectAnswerLlm(),
        storageRoot: tempDir.path,
      );
      final gateway = AssistantGateway(runtime);

      final response = await gateway.run(
        AssistantRunRequest(
          sessionId:
              'assistant_weather_stub_${DateTime.now().millisecondsSinceEpoch}',
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );

      expect(response.degraded, isFalse);
      expect(response.finalText.trim(), isNotEmpty);
      expect(response.displayPlainText, contains('深圳'));
      final structured = response.structuredResponse;
      final routing =
          (structured['phaseOneRoutingDiagnostics'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final domainRouting =
          (structured['domainRouting'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect((structured['primarySkill'] as String?) ?? '', equals('weather'));
      final selectedDomains =
          (domainRouting['selectedDomains'] as List?)
              ?.whereType<String>()
              .toList(growable: false) ??
          const <String>[];
      if (selectedDomains.isNotEmpty) {
        expect(selectedDomains, contains('weather'));
      }
      expect(routing['phaseOneNextAction'], equals('answer'));
      expect(routing['phaseOneMessageKind'], equals('answer'));
      expect(routing['phaseOneHasRenderableContent'], isTrue);
      final usageStats =
          (structured['uiUsageStats'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(
        (usageStats['modelCallCount'] as num?)?.toInt() ?? 0,
        lessThanOrEqualTo(3),
      );
    });

    test('问「深圳住宿和行程规划」时主过程不串入内部摘要任务', () async {
      final runtime = AssistantRuntime.createForTest();
      await runtime.ensureRemoteConfigLoaded();
      final gateway = AssistantGateway(runtime);
      final sessionId =
          'assistant_trip_e2e_test_${DateTime.now().millisecondsSinceEpoch}';

      final response = await gateway.run(
        AssistantRunRequest(
          sessionId: sessionId,
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(
              role: 'user',
              content: '帮我规划深圳三天两晚住宿和行程，预算4000元',
            ),
          ],
        ),
      );

      expect(response.finalText.trim(), isNotEmpty);
      expect(
        response.finalText.contains('未配置可用模型'),
        isFalse,
        reason: '复杂规划问题也不应回退到未配置模型文案',
      );
      expect(
        response.displayMarkdown.trim().isNotEmpty ||
            response.displayPlainText.trim().isNotEmpty,
        isTrue,
      );
      expect(
        '${response.displayMarkdown} ${response.displayPlainText}'
            .contains('contractVersion'),
        isFalse,
      );
      final journey = response.runArtifacts?.journey;
      expect(journey, isNotNull);
      expect(
        journey!.entries.isNotEmpty || journey.stages.isNotEmpty,
        isTrue,
        reason: '复杂规划问题应输出统一用户旅程',
      );

      final combinedNarrative = journey.entries
          .map((item) => '${item.headline} ${item.detail}'.trim())
          .join(' ');
      expect(combinedNarrative.contains('压缩以上对话历史为简洁摘要'), isFalse);
      expect(combinedNarrative.contains('summarize_session'), isFalse);
    });
  });
}

void _installPathProviderMock() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (
    MethodCall call,
  ) async {
    if (call.method == 'getApplicationDocumentsDirectory') {
      return Directory.systemTemp.path;
    }
    return null;
  });
}

Future<AssistantRuntime> _buildDeterministicRuntime({
  required AssistantLlmProvider llmProvider,
  required String storageRoot,
}) async {
  final sessionManager = AssistantSessionManager(
    storagePath: '$storageRoot/sessions.json',
  );
  await sessionManager.load();
  final memoryRepository = AssistantMemoryRepository(
    ObjectBoxVectorStore(storagePath: '$storageRoot/memory.json'),
  );
  final toolMetadataRegistry = ToolMetadataRegistry();
  final reactRuntime = ReactRuntime(
    llmProvider: llmProvider,
    toolRegistry: AssistantToolRegistry(metadataRegistry: toolMetadataRegistry),
    toolMetadataRegistry: toolMetadataRegistry,
  );
  final loop = AssistantAgentLoop(
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
    runHandler: loop.run,
    classifyDomainHandler: loop.classifyDomain,
    listSessionsHandler: loop.listSessions,
    sessionDetailHandler: loop.sessionDetail,
    switchSessionHandler: loop.switchSession,
    invokeSkillHandler:
        ({
          required PersonalAssistantSkillManifest skill,
          required Map<String, dynamic> arguments,
          String deviceProfile = 'mobile',
        }) async {
          return const AssistantToolResult(
            success: false,
            message: 'deterministic runtime does not wire invokeSkill',
            errorCode: AssistantErrorCode.unsupportedTarget,
            degraded: true,
          );
        },
    ensureRemoteConfigLoadedHandler: () async {},
    switchModelHandler: (_) => false,
    listAvailableModelsHandler: () => const <String>['stub/weather-local'],
    selectedModelsHandler: () => const <String>['stub/weather-local'],
    setSelectedModelsHandler: (_) => false,
    currentModelHandler: () => 'stub/weather-local',
  );
}

class _StableWeatherDirectAnswerLlm implements AssistantLlmProvider {
  const _StableWeatherDirectAnswerLlm();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    LlmCallOptions? callOptions,
    void Function(String delta)? onDelta,
  }) async {
    final query = _latestUserQuery(messages);
    onDelta?.call('天气主线已经够清楚了，我直接给你结论。');
    return AssistantModelOutput(
      text: jsonEncode(_buildWeatherTurn(query)),
      modelPath: 'stub/weather-local',
    );
  }

  String _latestUserQuery(List<Map<String, dynamic>> messages) {
    for (final message in messages.reversed) {
      if ((message['role'] as String?) == 'user') {
        return (message['content'] as String?)?.trim() ?? '';
      }
    }
    return '';
  }

  Map<String, dynamic> _buildWeatherTurn(String query) {
    final normalizedQuery = query.trim().isEmpty ? '深圳天气怎么样' : query.trim();
    return <String, dynamic>{
      'contractVersion': 'assistant_turn',
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '天气主线已经明确，我直接给你结论。',
      'decision': <String, dynamic>{
        'nextAction': 'answer',
        'confidence': 0.95,
        'reasoning': '简单天气问句已定位到 weather，当前信息足以直接成答。',
      },
      'userMarkdown':
          '## 🌤️ 深圳今天天气\n\n今天以多云到晴为主，体感偏温和，正常出门没问题。\n\n- 穿衣：短袖外搭一件薄外套更稳妥\n- 出行：白天通勤压力不大，晚点回家也不用太担心\n- 建议：包里放把轻便伞，主要是防临时阵雨',
      'result': <String, dynamic>{
        'text': '深圳今天以多云到晴为主，正常出门没问题，薄外套加轻便伞更稳妥。',
        'summary': '深圳今天天气温和，适合正常出行',
        'interpretation': '用户想快速知道天气结论、穿衣和出行建议。',
        'actionHints': const <String>[],
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '了解深圳今天天气并获得穿衣和出行建议',
        'problemShape': 'single_skill',
        'primarySkill': 'weather',
        'problemClass': 'realtime_info',
        'inferredMotive': '想快速判断今天出门怎么穿、通勤是否受影响。',
        'secondarySkills': const <String>[],
        'targetObject': '深圳天气',
        'userJobToBeDone': '快速拿到天气结论与实用建议',
        'hardConstraints': const <String>[],
        'softConstraints': const <String>['结论先行', '建议可执行'],
        'excludedScopes': const <String>[],
        'freshnessNeed': '',
        'answerShape': 'direct_answer',
        'mustVerifyClaims': false,
        'requiresExternalEvidence': false,
        'entityAnchors': const <String>['深圳'],
        'negativeKeywords': const <String>[],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': normalizedQuery,
          'rewrittenQuery': '',
          'issues': const <String>[],
          'language': 'zh',
          'hints': const <String>[],
        },
        'queryTasks': const <Map<String, dynamic>>[],
        'contextSlots': const <String, dynamic>{'city': '深圳'},
        'globalConstraints': const <String, dynamic>{'mode': 'hybrid'},
        'clarificationNeeded': false,
        'authorityDomains': const <String>[],
        'freshnessHoursMax': 0,
      },
      'toolPlan': const <List<dynamic>>[],
      'toolCalls': const <List<dynamic>>[],
      'subagentPlan': const <List<dynamic>>[],
      'askUser': const <String, dynamic>{
        'slotId': '',
        'prompt': '',
        'required': false,
        'suggestions': <String>[],
      },
      'missingContextSlots': const <String>[],
      'fillGuidance': const <List<dynamic>>[],
      'selfCheck': const <String, dynamic>{
        'goalSatisfied': true,
        'constraintSatisfied': true,
        'safetyBoundarySatisfied': true,
        'failedItems': <String>[],
      },
      'diagnostics': const <String, dynamic>{
        'emergedTags': <Map<String, dynamic>>[],
        'failedChecks': <String>[],
        'parseStatus': '',
        'notes': <String>['stub_weather_direct_answer'],
      },
      'modelSelfScore': const <String, dynamic>{
        'score': 95,
        'reason': 'stub_weather_direct_answer',
      },
    };
  }
}
