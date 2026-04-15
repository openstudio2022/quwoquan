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
        '${response.displayMarkdown} ${response.displayPlainText}'.contains(
          'contractVersion',
        ),
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

    test('本地 stub runtime 会保留三阶段叙事，并确保最终正文不是答案元描述', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_three_stage_quality_e2e_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final runtime = await _buildDeterministicRuntime(
        llmProvider: const _ThreeStageMarketNarrativeLlm(),
        storageRoot: tempDir.path,
      );
      final gateway = AssistantGateway(runtime);

      final response = await gateway.run(
        AssistantRunRequest(
          sessionId:
              'assistant_three_stage_quality_${DateTime.now().millisecondsSinceEpoch}',
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '周三A股为什么大涨'),
          ],
        ),
      );

      expect(response.degraded, isFalse);
      expect(response.displayMarkdown.trim(), isNotEmpty);
      expect(response.displayPlainText.trim(), isNotEmpty);
      final artifacts = response.runArtifacts;
      expect(artifacts, isNotNull);
      final resolvedArtifacts = artifacts!;
      final structuredUnderstanding =
          (response.structuredResponse['understandingSnapshot'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final visibleUnderstanding =
          (structuredUnderstanding['userFacingSummary'] as String?)?.trim() ??
          resolvedArtifacts.understandingSnapshot.userFacingSummary;
      expect(visibleUnderstanding, contains('周三A股大涨'));
      expect(
        resolvedArtifacts.retrievalProcessing.processingSummary,
        isNotEmpty,
      );
      expect(
        resolvedArtifacts.retrievalProcessing.processingSummary,
        isNot(contains('处理了')),
      );
      expect(
        resolvedArtifacts.retrievalProcessing.processingSummary,
        isNot(contains('接纳了')),
      );
      expect(resolvedArtifacts.answerProcessing.readinessSummary, isNotEmpty);
      expect(response.displayMarkdown, contains('结论'));
      expect(response.displayMarkdown, contains('主要驱动 / 依据'));
      expect(response.displayMarkdown, contains('周三那天 A股 明显走强'));
      expect(
        response.displayMarkdown,
        isNot(contains('最终答案会先给出周三A股大涨的核心结论')),
        reason: '最终展示应来自 userMarkdown 正文，而不是把 readinessSummary 当成答案正文',
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
        '${response.displayMarkdown} ${response.displayPlainText}'.contains(
          'contractVersion',
        ),
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
      'contractId': 'assistant_turn',
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

class _ThreeStageMarketNarrativeLlm implements AssistantLlmProvider {
  const _ThreeStageMarketNarrativeLlm();

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
    onDelta?.call('我先把周三落到具体交易日，再把指数、权重和情绪三条线索收拢。');
    return AssistantModelOutput(
      text: jsonEncode(_buildMarketTurn(query)),
      modelPath: 'stub/market-three-stage',
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

  Map<String, dynamic> _buildMarketTurn(String query) {
    final normalizedQuery = query.trim().isEmpty ? '周三A股为什么大涨' : query.trim();
    return <String, dynamic>{
      'contractId': 'assistant_turn',
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '周三那天的盘面主线已经够清楚了，我直接给你结论。',
      'decision': <String, dynamic>{
        'nextAction': 'answer',
        'confidence': 0.94,
        'reasoning': '已经锁定交易日、盘面主线和主要驱动，足以直接成答。',
      },
      'understandingSnapshot': const <String, dynamic>{
        'userFacingSummary':
            '你现在想确认周三那天 A股 为什么明显走强，我会先把“周三”落到具体交易日，再判断是政策预期、权重发力还是情绪修复在起主要作用。',
        'intentSummary': '确认周三A股大涨的主要驱动',
        'concernPoints': <String>['上涨是不是政策预期驱动', '权重板块是不是主升力量'],
        'emotionSignal': 'neutral',
      },
      'retrievalProcessing': const <String, dynamic>{
        'processedDocumentCount': 6,
        'acceptedDocumentCount': 3,
        'processingSummary':
            '围绕你最关心的“周三为什么大涨”，已经确认这波上行主要由政策预期回暖、券商等权重板块走强和风险偏好修复共同推动；零散题材消息只作背景，不会放到结论里。',
        'selectedKeyPoints': <String>[
          '指数放量上行，说明风险偏好明显回暖',
          '券商与大金融权重走强，放大了指数弹性',
          'AI 与科技方向跟涨，强化了情绪扩散',
        ],
        'acceptedReferences': <Map<String, dynamic>>[
          <String, dynamic>{
            'title': '盘后市场综述',
            'url': 'https://example.com/market-close',
            'source': 'example.com',
            'snippet': '券商和大金融走强，带动指数放量上行。',
          },
          <String, dynamic>{
            'title': '板块资金观察',
            'url': 'https://example.com/fund-flow',
            'source': 'example.com',
            'snippet': '科技成长方向跟涨，市场风险偏好继续修复。',
          },
        ],
      },
      'answerProcessing': const <String, dynamic>{
        'readinessSummary':
            '最终答案会先给出周三A股大涨的核心结论，再拆成政策预期、权重板块和情绪修复三条主驱动，最后补不确定项。',
        'keyFacts': <String>[
          '政策预期回暖带动权重板块发力',
          '券商与大金融走强，抬升指数弹性',
          '科技方向跟涨，说明情绪扩散而非单点脉冲',
        ],
        'missingDimensions': <String>[],
        'retrieveMoreReason': '',
      },
      'userMarkdown':
          '## 结论\n'
          '周三那天 A股 明显走强，核心不是单一突发消息，而是政策预期回暖、券商等权重板块发力和风险偏好修复叠加放大的结果。\n\n'
          '## 主要驱动 / 依据\n'
          '- 券商和大金融板块走强，直接抬升了指数弹性。\n'
          '- AI 与科技方向跟涨，说明上涨不只是防御性修复，而是情绪扩散。\n'
          '- 盘面成交放大，说明资金愿意重新承担风险。\n\n'
          '## 证据依据\n'
          '- 核心指数同步走强，说明不是个别小票脉冲。\n'
          '- 券商板块领涨，常见于政策预期改善或风险偏好回升阶段。\n'
          '- 科技成长方向跟随上行，说明资金并非只做避险轮动。\n\n'
          '## 不确定项 / 保留判断\n'
          '如果要进一步区分“政策催化”与“外部市场联动”各自占比，还需要补当日更细的新闻时间线与分时资金数据。',
      'result': const <String, dynamic>{
        'text': '周三A股大涨主要由政策预期回暖、权重板块发力和风险偏好修复共同推动。',
        'summary': '周三A股大涨是政策预期、权重发力和情绪修复的共振结果。',
        'interpretation': '用户要的是周三A股大涨的核心驱动，而不是泛泛市场复盘。',
        'actionHints': <String>[],
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '解释周三A股大涨的主要驱动',
        'problemShape': 'single_skill',
        'primarySkill': 'general_search',
        'problemClass': 'realtime_info',
        'inferredMotive': '想快速判断周三A股大涨背后的主驱动',
        'secondarySkills': const <String>[],
        'targetObject': 'A股盘面',
        'userJobToBeDone': '快速理解周三A股大涨的主因',
        'hardConstraints': const <String>[],
        'softConstraints': const <String>['结论先行', '驱动拆解清楚'],
        'excludedScopes': const <String>[],
        'freshnessNeed': '',
        'answerShape': 'four_section_answer',
        'mustVerifyClaims': false,
        'requiresExternalEvidence': false,
        'entityAnchors': const <String>['A股', '周三'],
        'negativeKeywords': const <String>[],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': normalizedQuery,
          'rewrittenQuery': '',
          'issues': const <String>[],
          'language': 'zh',
          'hints': const <String>[],
        },
        'queryTasks': const <Map<String, dynamic>>[],
        'contextSlots': const <String, dynamic>{'market': 'A股'},
        'globalConstraints': const <String, dynamic>{'mode': 'qa'},
        'clarificationNeeded': false,
        'authorityDomains': const <String>[],
        'freshnessHoursMax': 0,
      },
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
        'notes': <String>['stub_market_three_stage_answer'],
      },
      'modelSelfScore': const <String, dynamic>{
        'score': 94,
        'reason': 'stub_market_three_stage_answer',
      },
    };
  }
}
