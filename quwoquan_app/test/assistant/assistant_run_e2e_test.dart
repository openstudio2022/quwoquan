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
      final processNarrative =
          response.runArtifacts?.displayState.process.blocks
              .map((block) => '${block.title}\n${block.body}'.trim())
              .join('\n') ??
          '';
      expect(processNarrative, contains('天气现状'));
      expect(processNarrative, contains('出门建议'));
      expect(processNarrative, contains('深圳 实时天气 体感温度'));
      final journey =
          (structured['journey'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final journeyEntries =
          (journey['entries'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final searchEntry = journeyEntries.firstWhere(
        (item) => item['stageId'] == 'search',
        orElse: () => const <String, dynamic>{},
      );
      expect((searchEntry['detail'] as String?) ?? '', contains('天气现状'));
      expect(
        (searchEntry['detail'] as String?) ?? '',
        contains('深圳 实时天气 体感温度'),
      );
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
      expect(response.displayMarkdown, contains('结论'));
      expect(response.displayMarkdown, contains('主要驱动 / 依据'));
      expect(response.displayMarkdown, contains('周三那天 A股 明显走强'));
      expect(
        response.displayMarkdown,
        isNot(contains('最终答案会先给出周三A股大涨的核心结论')),
        reason: '最终展示应来自 userMarkdown 正文，而不是把 readinessSummary 当成答案正文',
      );
      final processNarrative = resolvedArtifacts.displayState.process.blocks
          .map((block) => '${block.title}\n${block.body}'.trim())
          .join('\n');
      expect(processNarrative, contains('盘面主线'));
      expect(processNarrative, contains('权重板块'));
      expect(processNarrative, contains('情绪修复'));
      expect(processNarrative, contains('周三 A股 指数 放量 上涨 主因'));
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

    test('M6 最终集成验收：多 skill 并行后应统一成答并落盘到 session 视图', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_m6_final_integration_e2e_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final runtime = await _buildDeterministicRuntime(
        llmProvider: const _M6MultiSkillIntegrationLlm(),
        storageRoot: tempDir.path,
      );
      final gateway = AssistantGateway(runtime);
      final sessionId =
          'assistant_m6_final_integration_${DateTime.now().millisecondsSinceEpoch}';
      final response = await gateway.run(
        AssistantRunRequest(
          sessionId: sessionId,
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '帮我同时比较九寨沟4天路线和住宿取舍'),
          ],
        ),
      );

      expect(response.degraded, isFalse);
      expect(response.finalText.trim(), isNotEmpty);
      expect(response.displayPlainText.trim(), isNotEmpty);
      expect(response.displayPlainText, contains('路线'));
      expect(response.displayPlainText, contains('住宿'));
      expect(response.displayPlainText, contains('沟口'));

      final structured = response.structuredResponse;
      final subagentRuns =
          (structured['subagentRuns'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(
        subagentRuns,
        hasLength(1),
        reason: 'primary skill 由主答承接，subagentRuns 只应包含支持 skill',
      );
      expect(subagentRuns.first['domainId'], equals('hotel'));
      expect(
        response.runArtifacts?.displayState.process.finalAnswerReady,
        isTrue,
        reason: 'M6 收口层应把最终成答状态写入展示过程态',
      );
      expect(
        response.runArtifacts?.processTimeline.isNotEmpty,
        isTrue,
        reason: '最终回放结果应保留完整 processTimeline',
      );

      final sessionDetail = await runtime.sessionDetail(sessionId);
      expect(sessionDetail, isNotNull);
      expect(sessionDetail!.summary.trim(), isNotEmpty);
      expect(sessionDetail.messages, isNotEmpty);
      expect(sessionDetail.messages.last.content, contains('九寨沟'));
      expect(sessionDetail.messages.last.content, contains('沟口'));

      final sessionIds = await runtime.listSessions();
      expect(
        sessionIds.map((item) => item.sessionId).toList(growable: false),
        contains(sessionId),
      );
    });

    test('部分完成场景会保留 skill_route 并向用户一次性展示待补充信息', () async {
      final tempDir = await Directory.systemTemp.createTemp(
        'assistant_partial_clarification_e2e_',
      );
      addTearDown(() async {
        if (await tempDir.exists()) {
          await tempDir.delete(recursive: true);
        }
      });
      final runtime = await _buildDeterministicRuntime(
        llmProvider: const _PartialClarificationSkillLlm(),
        storageRoot: tempDir.path,
      );
      final gateway = AssistantGateway(runtime);
      final sessionId =
          'assistant_partial_clarification_${DateTime.now().millisecondsSinceEpoch}';

      final response = await gateway.run(
        AssistantRunRequest(
          sessionId: sessionId,
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳明天适合出门吗，顺便帮我规划周末行程'),
          ],
        ),
      );

      expect(response.degraded, isFalse);
      expect(response.finalText.trim(), isNotEmpty);
      expect(response.displayPlainText, contains('深圳'));
      expect(response.followupPrompt, contains('一次性补充'));
      expect(response.actionHints, contains('周末具体哪一天'));
      expect(response.actionHints, contains('预算上限'));

      final structured = response.structuredResponse;
      final skillRoute =
          (structured['skillRoute'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(skillRoute['contractId'], equals('skill_route'));
      final selectedTargets =
          (skillRoute['selectedTargets'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(selectedTargets, hasLength(2));
      expect(selectedTargets.first['skillId'], equals('weather'));
      expect(selectedTargets.last['skillId'], equals('travel'));

      final skillSynthesis =
          (structured['skillSynthesis'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final synthesisOutput =
          (skillSynthesis['output'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(
        synthesisOutput['partialCompletionState'],
        equals('needs_clarification'),
      );

      final pendingClarifications =
          (structured['pendingClarifications'] as List?)
              ?.whereType<String>()
              .toList(growable: false) ??
          const <String>[];
      expect(pendingClarifications, contains('周末具体哪一天'));
      expect(pendingClarifications, contains('预算上限'));
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
        'queryTasks': const <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'weather_now',
            'label': '天气现状',
            'query': '深圳 实时天气 体感温度',
            'dimension': 'current_state',
          },
          <String, dynamic>{
            'id': 'go_out_advice',
            'label': '出门建议',
            'query': '深圳 出门建议 降雨概率 通勤',
            'dimension': 'decision_impact',
          },
        ],
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
        'queryTasks': const <Map<String, dynamic>>[
          <String, dynamic>{
            'id': 'market_mainline',
            'label': '盘面主线',
            'query': '周三 A股 指数 放量 上涨 主因',
            'dimension': 'current_state',
          },
          <String, dynamic>{
            'id': 'weight_sector',
            'label': '权重板块',
            'query': '券商 大金融 领涨 原因',
            'dimension': 'decision_impact',
          },
          <String, dynamic>{
            'id': 'sentiment_repair',
            'label': '情绪修复',
            'query': '科技 跟涨 风险偏好 修复',
            'dimension': 'supporting_evidence',
          },
        ],
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

class _M6MultiSkillIntegrationLlm implements AssistantLlmProvider {
  const _M6MultiSkillIntegrationLlm();

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
    final subagentRuns = templateVariables['subagentRuns'];
    final subagentPlan = templateVariables['subagentPlan'];
    if (templateId == 'synthesizer.final_answer' &&
        subagentRuns is List &&
        subagentRuns.isNotEmpty) {
      onDelta?.call('路线和住宿都已经齐了，我来统一成答。');
      return AssistantModelOutput(
        text: jsonEncode(_buildFinalTurn(query)),
        modelPath: 'stub/m6-final-synthesis',
      );
    }
    if (templateId == 'planner.global_plan' && subagentPlan is Map) {
      final plan = subagentPlan.cast<String, dynamic>();
      final subagentId = (plan['subagentId'] as String?)?.trim() ?? '';
      if (subagentId == 'travel_route' || subagentId == 'route_planner') {
        return AssistantModelOutput(
          text: jsonEncode(_buildRouteSubagentTurn(query)),
          modelPath: 'stub/m6-route-subagent',
        );
      }
      return AssistantModelOutput(
        text: jsonEncode(_buildHotelSubagentTurn(query)),
        modelPath: 'stub/m6-hotel-subagent',
      );
    }
    if (templateId == 'planner.global_plan') {
      onDelta?.call('我先把路线和住宿拆成两个并行子任务，再统一给你最终建议。');
      return AssistantModelOutput(
        text: jsonEncode(_buildRoutePlanningTurn(query)),
        modelPath: 'stub/m6-route-planning',
      );
    }
    return AssistantModelOutput(
      text: jsonEncode(_buildFinalTurn(query)),
      modelPath: 'stub/m6-fallback',
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

  Map<String, dynamic> _buildRoutePlanningTurn(String query) {
    final normalizedQuery = query.trim().isEmpty
        ? '帮我同时比较九寨沟4天路线和住宿取舍'
        : query.trim();
    return <String, dynamic>{
      'contractId': 'assistant_turn',
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '路线与住宿可以拆成两个并行子任务。',
      'decision': <String, dynamic>{'nextAction': 'answer'},
      'userMarkdown': '我会把你的问题拆成路线和住宿两条线并行处理，最后统一给你一版可执行建议。',
      'result': <String, dynamic>{
        'text': '进入路线和住宿并行整理。',
        'summary': '拆分路线与住宿两条线并行处理。',
        'interpretation': '多 skill 路由',
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '比较九寨沟4天路线和住宿取舍',
        'problemShape': 'multi_skill',
        'primarySkill': 'travel',
        'problemClass': 'complex_reasoning',
        'inferredMotive': '需要同时权衡路线与住宿',
        'secondarySkills': <String>['hotel'],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': normalizedQuery,
        },
        'queryTasks': <Map<String, dynamic>>[],
        'contextSlots': const <String, dynamic>{},
        'globalConstraints': const <String, dynamic>{'mode': 'qa'},
        'clarificationNeeded': false,
      },
      'subagentPlan': <Map<String, dynamic>>[
        _buildRoutePlan(),
        _buildHotelPlan(),
      ],
      'askUser': const <String, dynamic>{
        'slotId': '',
        'prompt': '',
        'required': false,
        'suggestions': <String>[],
      },
      'missingContextSlots': const <String>[],
      'fillGuidance': const <List<dynamic>>[],
      'answerProcessing': const <String, dynamic>{
        'readinessSummary': '路线与住宿两条线已拆分，后续由并行子任务收齐后统一成答。',
        'missingDimensions': <String>[],
        'retrieveMoreReason': '',
      },
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
        'notes': <String>['m6_route_planning_turn'],
      },
      'modelSelfScore': const <String, dynamic>{
        'score': 92,
        'reason': 'm6_route_planning_turn',
      },
    };
  }

  Map<String, dynamic> _buildRoutePlan() {
    return <String, dynamic>{
      'subagentId': 'travel_route',
      'domainId': 'travel',
      'problemClass': 'complex_reasoning',
      'goal': '梳理九寨沟4天路线主线',
      'role': 'primary',
      'taskBrief': '整理4天行程主线和时间分配',
      'routeNarrative': '路线维度作为主线先稳定，再决定住宿如何配合。',
      'localContextSeed': '用户想要4天九寨沟路线建议。',
      'needClarify': false,
      'pendingClarifications': <String>[],
      'mode': 'qa',
      'timeoutMs': 4000,
      'maxIterations': 1,
      'toolBudget': 1,
      'stopPolicy': 'balanced',
      'searchIntensity': 'medium',
      'providerPolicy': '',
      'freshnessHoursMax': 0,
      'answerThreshold': 0.6,
    };
  }

  Map<String, dynamic> _buildHotelPlan() {
    return <String, dynamic>{
      'subagentId': 'hotel_tradeoff',
      'domainId': 'hotel',
      'problemClass': 'complex_reasoning',
      'goal': '补充九寨沟住宿取舍',
      'role': 'supporting',
      'taskBrief': '整理住宿位置与效率取舍',
      'routeNarrative': '住宿维度作为辅助约束并行评估，优先考虑往返效率。',
      'localContextSeed': '用户在意住宿位置与节省时间。',
      'needClarify': false,
      'pendingClarifications': <String>[],
      'mode': 'qa',
      'timeoutMs': 4000,
      'maxIterations': 1,
      'toolBudget': 1,
      'stopPolicy': 'balanced',
      'searchIntensity': 'medium',
      'providerPolicy': '',
      'freshnessHoursMax': 0,
      'answerThreshold': 0.6,
    };
  }

  Map<String, dynamic> _buildRouteSubagentTurn(String query) {
    final normalizedQuery = query.trim().isEmpty
        ? '帮我同时比较九寨沟4天路线和住宿取舍'
        : query.trim();
    return <String, dynamic>{
      'contractId': 'assistant_turn',
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '路线主线已经整理完毕。',
      'decision': <String, dynamic>{'nextAction': 'answer'},
      'userMarkdown': '路线：优先经典主线，保证 4 天内把核心景点走完。',
      'result': <String, dynamic>{
        'text': '路线优先经典主线。',
        'summary': '路线主线优先。',
        'interpretation': '路线子任务结论',
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '比较九寨沟4天路线和住宿取舍',
        'problemShape': 'single_skill',
        'primarySkill': 'travel',
        'problemClass': 'complex_reasoning',
        'inferredMotive': '需要路线主线结论',
        'secondarySkills': const <String>[],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': normalizedQuery,
        },
        'queryTasks': <Map<String, dynamic>>[],
        'contextSlots': const <String, dynamic>{},
        'globalConstraints': const <String, dynamic>{'mode': 'qa'},
        'clarificationNeeded': false,
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
        'notes': <String>['m6_route_subagent_turn'],
      },
      'modelSelfScore': const <String, dynamic>{
        'score': 91,
        'reason': 'm6_route_subagent_turn',
      },
    };
  }

  Map<String, dynamic> _buildHotelSubagentTurn(String query) {
    final normalizedQuery = query.trim().isEmpty
        ? '帮我同时比较九寨沟4天路线和住宿取舍'
        : query.trim();
    return <String, dynamic>{
      'contractId': 'assistant_turn',
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '住宿取舍已经整理完毕。',
      'decision': <String, dynamic>{'nextAction': 'answer'},
      'userMarkdown': '住宿：优先沟口附近，减少每天往返时间。',
      'result': <String, dynamic>{
        'text': '住宿优先沟口附近。',
        'summary': '住宿优先沟口附近。',
        'interpretation': '住宿子任务结论',
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '比较九寨沟4天路线和住宿取舍',
        'problemShape': 'single_skill',
        'primarySkill': 'hotel',
        'problemClass': 'complex_reasoning',
        'inferredMotive': '需要住宿位置建议',
        'secondarySkills': const <String>[],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': normalizedQuery,
        },
        'queryTasks': <Map<String, dynamic>>[],
        'contextSlots': const <String, dynamic>{},
        'globalConstraints': const <String, dynamic>{'mode': 'qa'},
        'clarificationNeeded': false,
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
        'notes': <String>['m6_hotel_subagent_turn'],
      },
      'modelSelfScore': const <String, dynamic>{
        'score': 90,
        'reason': 'm6_hotel_subagent_turn',
      },
    };
  }

  Map<String, dynamic> _buildFinalTurn(String query) {
    final normalizedQuery = query.trim().isEmpty
        ? '帮我同时比较九寨沟4天路线和住宿取舍'
        : query.trim();
    return <String, dynamic>{
      'contractId': 'assistant_turn',
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '路线与住宿的并行结果已经足够稳定。',
      'decision': <String, dynamic>{'nextAction': 'answer'},
      'userMarkdown':
          '## 九寨沟 4 天建议\n\n'
          '路线先按经典主线走，优先把核心景点串起来；住宿优先选沟口附近，减少每天往返时间。\n\n'
          '- 路线：先稳主线，再微调节奏。\n'
          '- 住宿：以效率优先，尽量减少转场成本。\n'
          '- 取舍：先保证游玩体验，再补更细的住宿偏好。',
      'result': <String, dynamic>{
        'text': '九寨沟4天建议：路线优先经典主线，住宿优先沟口附近。',
        'summary': '路线主线优先，住宿优先沟口附近。',
        'interpretation': '用户要的是路线与住宿的最终折中建议',
        'actionHints': <String>['如果要我继续，我可以再细化每天的景点顺序。'],
      },
      'answerProcessing': const <String, dynamic>{
        'readinessSummary': '路线和住宿两条线都已经收齐，可以直接给最终建议。',
        'keyFacts': <String>['路线主线优先', '住宿优先沟口附近', '先保证效率再细化偏好'],
        'missingDimensions': <String>[],
        'retrieveMoreReason': '',
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '比较九寨沟4天路线和住宿取舍',
        'problemShape': 'multi_skill',
        'primarySkill': 'travel',
        'problemClass': 'complex_reasoning',
        'inferredMotive': '需要一版可执行的最终建议',
        'secondarySkills': <String>['hotel'],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': normalizedQuery,
        },
        'queryTasks': <Map<String, dynamic>>[],
        'contextSlots': const <String, dynamic>{},
        'globalConstraints': const <String, dynamic>{'mode': 'qa'},
        'clarificationNeeded': false,
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
        'notes': <String>['m6_final_synthesis_turn'],
      },
      'modelSelfScore': const <String, dynamic>{
        'score': 96,
        'reason': 'm6_final_synthesis_turn',
      },
    };
  }
}

class _PartialClarificationSkillLlm implements AssistantLlmProvider {
  const _PartialClarificationSkillLlm();

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
    final subagentRuns = templateVariables['subagentRuns'];
    final subagentPlan = templateVariables['subagentPlan'];
    if (templateId == 'synthesizer.final_answer' &&
        subagentRuns is List &&
        subagentRuns.isNotEmpty) {
      onDelta?.call('天气结论已经稳定，我先给你可用建议，再把还缺的信息一次性列出来。');
      return AssistantModelOutput(
        text: jsonEncode(_buildFinalTurn(query)),
        modelPath: 'stub/partial-clarification-final',
      );
    }
    if (templateId == 'planner.global_plan' && subagentPlan is Map) {
      return AssistantModelOutput(
        text: jsonEncode(_buildTravelSubagentTurn(query)),
        modelPath: 'stub/partial-clarification-subagent',
      );
    }
    onDelta?.call('我先确认深圳明天的天气，再并行整理周末行程，但还差日期和预算。');
    return AssistantModelOutput(
      text: jsonEncode(_buildRoutePlanningTurn(query)),
      modelPath: 'stub/partial-clarification-route',
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

  Map<String, dynamic> _buildRoutePlanningTurn(String query) {
    final normalizedQuery = query.trim().isEmpty
        ? '深圳明天适合出门吗，顺便帮我规划周末行程'
        : query.trim();
    return <String, dynamic>{
      'contractId': 'assistant_turn',
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '天气主线已经稳定，周末行程拆成补充子任务继续处理。',
      'decision': <String, dynamic>{'nextAction': 'answer'},
      'userMarkdown': '深圳明天适合出门，我会继续把周末行程补成一版可执行建议。',
      'result': <String, dynamic>{
        'text': '深圳明天适合出门，周末行程进入补充整理。',
        'summary': '天气先给结论，周末行程继续补充。',
        'interpretation': '先给天气结论，再并行整理周末行程。',
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '判断深圳明天是否适合出门，并补充周末行程建议',
        'problemShape': 'multi_skill',
        'primarySkill': 'weather',
        'problemClass': 'complex_reasoning',
        'inferredMotive': '先确认天气，再补行程安排',
        'secondarySkills': <String>['travel'],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': normalizedQuery,
        },
        'queryTasks': <Map<String, dynamic>>[],
        'contextSlots': const <String, dynamic>{},
        'globalConstraints': const <String, dynamic>{'mode': 'qa'},
        'clarificationNeeded': false,
      },
      'subagentPlan': <Map<String, dynamic>>[
        <String, dynamic>{
          'subagentId': 'travel_weekend',
          'domainId': 'travel',
          'problemClass': 'complex_reasoning',
          'goal': '补充周末行程建议',
          'role': 'supporting',
          'taskBrief': '整理周末轻量行程建议',
          'routeNarrative': '天气结论已稳定，周末行程并行补充，但还需要日期和预算。',
          'localContextSeed': '用户需要深圳周末行程建议。',
          'needClarify': true,
          'pendingClarifications': <String>['周末具体哪一天', '预算上限'],
          'mode': 'qa',
          'timeoutMs': 4000,
          'maxIterations': 1,
          'toolBudget': 1,
          'stopPolicy': 'balanced',
          'searchIntensity': 'medium',
          'providerPolicy': '',
          'freshnessHoursMax': 0,
          'answerThreshold': 0.6,
        },
      ],
      'askUser': const <String, dynamic>{
        'slotId': '',
        'prompt': '',
        'required': false,
        'suggestions': <String>[],
      },
      'missingContextSlots': const <String>[],
      'fillGuidance': const <List<dynamic>>[],
      'answerProcessing': const <String, dynamic>{
        'readinessSummary': '天气主线可先成答，周末行程需要再补两个关键条件。',
        'missingDimensions': <String>['周末具体哪一天', '预算上限'],
        'retrieveMoreReason': '缺少日期和预算时，行程建议只能先给轻量框架。',
      },
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
        'notes': <String>['partial_clarification_route_turn'],
      },
      'modelSelfScore': const <String, dynamic>{
        'score': 90,
        'reason': 'partial_clarification_route_turn',
      },
    };
  }

  Map<String, dynamic> _buildTravelSubagentTurn(String query) {
    final normalizedQuery = query.trim().isEmpty
        ? '深圳明天适合出门吗，顺便帮我规划周末行程'
        : query.trim();
    return <String, dynamic>{
      'contractId': 'assistant_turn',
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '周末行程已经有一版轻量框架。',
      'decision': <String, dynamic>{'nextAction': 'answer'},
      'userMarkdown': '周末行程先按轻量出门路线准备，日期和预算确认后再细化。',
      'result': <String, dynamic>{
        'text': '周末行程先给轻量框架。',
        'summary': '周末行程已有轻量框架。',
        'interpretation': '周末行程暂时给框架版建议。',
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '补充周末行程建议',
        'problemShape': 'single_skill',
        'primarySkill': 'travel',
        'problemClass': 'complex_reasoning',
        'inferredMotive': '先给行程框架，再等待补全条件',
        'secondarySkills': const <String>[],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': normalizedQuery,
        },
        'queryTasks': const <Map<String, dynamic>>[],
        'contextSlots': const <String, dynamic>{},
        'globalConstraints': const <String, dynamic>{'mode': 'qa'},
        'clarificationNeeded': false,
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
        'notes': <String>['partial_clarification_subagent_turn'],
      },
      'modelSelfScore': const <String, dynamic>{
        'score': 88,
        'reason': 'partial_clarification_subagent_turn',
      },
    };
  }

  Map<String, dynamic> _buildFinalTurn(String query) {
    final normalizedQuery = query.trim().isEmpty
        ? '深圳明天适合出门吗，顺便帮我规划周末行程'
        : query.trim();
    return <String, dynamic>{
      'contractId': 'assistant_turn',
      'messageKind': 'answer',
      'phaseId': 'answering',
      'actionCode': 'compose_answer',
      'reasonCode': 'evidence_ready',
      'reasonShort': '天气可先成答，周末行程保留为待补全项。',
      'decision': <String, dynamic>{'nextAction': 'answer'},
      'userMarkdown':
          '## 深圳明天出门建议\n\n'
          '深圳明天适合正常出门，穿轻薄外套就够了。\n\n'
          '## 周末行程先给你一个框架\n'
          '- 可以先按半天室内 + 半天户外的轻量安排准备。\n'
          '- 等你补充具体日期和预算后，我再把路线、时长和花费细化到可直接执行。',
      'result': <String, dynamic>{
        'text': '深圳明天适合出门，周末行程先给轻量框架，待补日期和预算后再细化。',
        'summary': '天气可先成答，周末行程等待补全条件。',
        'interpretation': '先交付天气结论和周末行程框架。',
      },
      'answerProcessing': const <String, dynamic>{
        'readinessSummary': '天气已经足够稳定，周末行程还缺日期和预算两个条件。',
        'keyFacts': <String>['深圳明天适合出门', '周末行程已有轻量框架'],
        'missingDimensions': <String>['周末具体哪一天', '预算上限'],
        'retrieveMoreReason': '缺少日期和预算时，无法把周末行程细化到可执行版本。',
      },
      'intentGraph': <String, dynamic>{
        'userGoal': '判断深圳明天是否适合出门，并补充周末行程建议',
        'problemShape': 'multi_skill',
        'primarySkill': 'weather',
        'problemClass': 'complex_reasoning',
        'inferredMotive': '先拿到天气结论，再把周末行程细化',
        'secondarySkills': <String>['travel'],
        'queryNormalization': <String, dynamic>{
          'normalizedQuery': normalizedQuery,
        },
        'queryTasks': const <Map<String, dynamic>>[],
        'contextSlots': const <String, dynamic>{},
        'globalConstraints': const <String, dynamic>{'mode': 'qa'},
        'clarificationNeeded': false,
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
        'notes': <String>['partial_clarification_final_turn'],
      },
      'modelSelfScore': const <String, dynamic>{
        'score': 93,
        'reason': 'partial_clarification_final_turn',
      },
    };
  }
}
