import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/engine/agent_loop.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/memory/objectbox_store.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

/// Mock LLM that simulates the full pipeline:
/// - Summarization/classification calls → return simple text
/// - planner.global_plan first call with available tools → return tool call
/// - planner.global_plan after tool results → return final answer
/// - synthesis calls → pass through final answer
class _WeatherPipelineLlm implements AssistantLlmProvider {
  int planCallCount = 0;
  int totalCallCount = 0;
  final List<String> thinkingDeltas = <String>[];

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
    totalCallCount += 1;

    final isPlannerCall =
        templateId == 'planner.global_plan' ||
        templateId == 'planner.postcondition_check';
    final isSynthesisCall =
        templateId.contains('synthesizer') ||
        templateId.contains('final_answer');
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;

    if (!isPlannerCall && !isSynthesisCall) {
      return const AssistantModelOutput(text: '{"summary": "用户在询问深圳的天气情况。"}');
    }

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'primaryDomainId': 'weather',
          'secondaryDomains': <String>[],
          'inferredMotive': '查询深圳实时天气',
          'mode': 'qa',
          'queryNormalization': <String, dynamic>{'query': '深圳天气怎么样'},
        }),
      );
    }

    if (isPlannerCall) {
      planCallCount += 1;

      if (onDelta != null) {
        final thinkText = planCallCount == 1
            ? '用户想了解深圳天气，我需要搜索最新的天气信息。'
            : '搜索结果显示深圳今天晴，温度25°C，我来整理回答。';
        onDelta(thinkText);
        thinkingDeltas.add(thinkText);
      }

      if (planCallCount == 1 && availableTools.contains('web_search')) {
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractVersion': 'assistant_turn_v4',
            'decision': {'nextAction': 'tool_call'},
            'toolCalls': [
              {
                'tool': 'web_search',
                'arguments': {
                  'query': '深圳天气实况 今天 温度 湿度',
                  'queryVariants': <String>['深圳今天天气实况', '深圳当前天气', '深圳天气实时数据'],
                  'freshnessHoursMax': 6,
                  'provider': 'baidu',
                },
              },
            ],
            'thinkingText': '用户想了解深圳天气，我需要搜索最新的天气信息。',
          }),
          toolCalls: const <AssistantToolCall>[
            AssistantToolCall(
              name: 'web_search',
              arguments: <String, dynamic>{
                'query': '深圳天气实况 今天 温度 湿度',
                'queryVariants': <String>['深圳今天天气实况', '深圳当前天气', '深圳天气实时数据'],
                'freshnessHoursMax': 6,
                'provider': 'baidu',
              },
            ),
          ],
        );
      }
    }

    if (onDelta != null) {
      const thinkText = '基于搜索结果整理天气信息。';
      onDelta(thinkText);
      thinkingDeltas.add(thinkText);
    }

    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractVersion': 'assistant_turn_v4',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '## 深圳天气\n\n今天深圳天气晴朗，温度约25°C，适合户外活动。',
        'result': {'text': '今天深圳天气晴朗，温度约25°C。', 'interpretation': '深圳当前天气概况'},
        'evidence': [
          {'claim': '温度25°C', 'source': 'web_search', 'confidence': 'high'},
        ],
        'thinkingText': '搜索结果显示深圳今天晴，温度25°C，我来整理回答。',
        'selfCheck': {
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': {
          'whyThisAnswer': '基于搜索结果整理天气信息',
          'riskFlags': <String>[],
        },
        'modelSelfScore': {'score': 92, 'reason': '准确回答天气查询'},
        'toolCalls': <dynamic>[],
      }),
    );
  }
}

class _FakeWeatherSearchTool implements AssistantTool {
  int executeCount = 0;
  Map<String, dynamic> lastArguments = const <String, dynamic>{};

  @override
  String get name => 'web_search';

  @override
  String get description => '网络搜索';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    executeCount += 1;
    lastArguments = Map<String, dynamic>.from(arguments);
    return const AssistantToolResult(
      success: true,
      message: '搜索完成',
      data: <String, dynamic>{
        'provider': 'duckduckgo',
        'qualityScore': 0.85,
        'summary': '深圳今天天气晴朗，温度25°C',
        'references': <Map<String, dynamic>>[
          {
            'title': '深圳天气预报 - 中国气象局',
            'url': 'https://weather.cma.cn/shenzhen',
            'source': '中国气象局',
            'provider': 'duckduckgo',
            'snippet': '深圳今天晴，最高温度26°C，最低温度18°C。',
          },
          {
            'title': '深圳实时天气 - 天气网',
            'url': 'https://tianqi.com/shenzhen/',
            'source': '天气网',
            'provider': 'duckduckgo',
            'snippet': '深圳当前温度25°C，湿度65%，东南风3级。',
          },
        ],
      },
    );
  }
}

class _XmlLeakWeatherLlm implements AssistantLlmProvider {
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
    return const AssistantModelOutput(
      text:
          '<tool_call><function=web_search><parameter=query>深圳天气实况 今天 温度 湿度</parameter></function></tool_call>',
    );
  }
}

class _WeatherFallbackLlm implements AssistantLlmProvider {
  int planCallCount = 0;

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
    planCallCount += 1;
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'primaryDomainId': 'weather',
          'secondaryDomains': <String>[],
          'inferredMotive': '查询深圳实时天气',
          'mode': 'qa',
          'queryNormalization': <String, dynamic>{'query': '深圳天气怎么样'},
        }),
      );
    }
    final hasToolFailure = messages.any(
      (item) =>
          item['role'] == 'tool' &&
          (item['content']?.toString().contains('"ok":false') ?? false),
    );
    if (!hasToolFailure && availableTools.contains('web_search')) {
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'contractVersion': 'assistant_turn_v4',
          'decision': {'nextAction': 'tool_call'},
          'toolCalls': [
            {
              'tool': 'web_search',
              'arguments': {'query': '深圳 今天 天气 实时'},
            },
          ],
        }),
        toolCalls: const <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{'query': '深圳 今天 天气 实时'},
          ),
        ],
      );
    }
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractVersion': 'assistant_turn_v4',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'fallback',
        'slotState': {
          'city': {'value': '深圳', 'source': 'user_query'},
        },
        'result': {'text': '搜索服务暂时不可用', 'interpretation': '搜索服务暂时不可用'},
      }),
    );
  }
}

class _FailingWeatherSearchTool implements AssistantTool {
  int executeCount = 0;

  @override
  String get name => 'web_search';

  @override
  String get description => '网络搜索';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    executeCount += 1;
    return const AssistantToolResult(
      success: false,
      message: '搜索服务暂时不可用',
      errorCode: AssistantErrorCode.networkUnavailable,
      degraded: true,
    );
  }
}

void main() {
  group('Full phase pipeline — mock 深圳天气', () {
    late PersonalAssistantAgentLoop loop;
    late _WeatherPipelineLlm mockLlm;
    late _FakeWeatherSearchTool mockSearch;
    late Directory tempDir;

    setUpAll(() async {
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
    });

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('pa_pipeline_');
      mockLlm = _WeatherPipelineLlm();
      mockSearch = _FakeWeatherSearchTool();
      final toolRegistry = AssistantToolRegistry();
      toolRegistry.register(mockSearch);
      final runtime = ReactRuntime(
        llmProvider: mockLlm,
        toolRegistry: toolRegistry,
      );
      loop = PersonalAssistantAgentLoop(
        runtime,
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
        ),
      );
    });

    tearDown(() async {
      await tempDir.delete(recursive: true);
    });

    test('完整 5 阶段闭环：理解→搜索→评估→分析→回答', () async {
      final traces = <AssistantTraceEvent>[];
      final response = await loop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_weather',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
        onTraceEvent: traces.add,
      );

      // ---- 基本断言 ----
      expect(response.finalText, isNotEmpty);
      expect(response.degraded, isFalse);

      // ---- 工具调用验证 ----
      expect(
        mockSearch.executeCount,
        greaterThan(0),
        reason: 'web_search 工具应被调用',
      );
      expect(
        mockSearch.lastArguments.containsKey('queryVariants'),
        isFalse,
        reason: '天气实时查询应禁止扩搜变体',
      );
      expect(
        mockSearch.lastArguments.containsKey('provider'),
        isFalse,
        reason: 'authority_first 策略下不应把模型自选 provider 透传到工具层',
      );
      expect(
        mockSearch.lastArguments['freshnessHoursMax'],
        equals(1),
        reason: '天气实时查询应强制 freshnessHoursMax=1',
      );
      expect(
        (mockSearch.lastArguments['authorityDomains'] as List?) ??
            const <dynamic>[],
        containsAll(<String>['weather.com.cn', 'cma.cn']),
        reason: '天气实时查询应绑定权威域名白名单',
      );

      // ---- LLM 至少调用 2 轮（plan + answer/synthesis）----
      expect(
        mockLlm.totalCallCount,
        greaterThanOrEqualTo(2),
        reason: '至少 2 轮 LLM 调用（plan + synthesis）',
      );

      // ---- trace 类型覆盖检查 ----
      final traceTypes = traces.map((t) => t.type).toSet();
      expect(
        traceTypes.contains(AssistantTraceEventType.planStarted),
        isTrue,
        reason: '应有 planStarted',
      );
      expect(
        traceTypes.contains(AssistantTraceEventType.thinkingStarted),
        isTrue,
        reason: '应有 thinkingStarted',
      );
      expect(
        traceTypes.contains(AssistantTraceEventType.toolStart),
        isTrue,
        reason: '应有 toolStart',
      );
      expect(
        traceTypes.contains(AssistantTraceEventType.toolResult),
        isTrue,
        reason: '应有 toolResult',
      );
      expect(
        traceTypes.contains(AssistantTraceEventType.lifecycleEnd),
        isTrue,
        reason: '应有 lifecycleEnd',
      );

      // ---- thinkingProgress 流式思考 ----
      final thinkingProgressTraces = traces
          .where((t) => t.type == AssistantTraceEventType.thinkingProgress)
          .toList();
      expect(
        thinkingProgressTraces,
        isNotEmpty,
        reason: 'onDelta 应触发 thinkingProgress trace 事件',
      );
      for (final tp in thinkingProgressTraces) {
        expect(tp.message, isNotEmpty, reason: 'thinkingProgress 应有内容');
        expect(tp.data?['phase'], isNotNull, reason: '应标记 phase');
      }

      // ---- assessment trace（工具后评估）----
      final assessmentTraces = traces
          .where(
            (t) =>
                t.type == AssistantTraceEventType.toolResult &&
                t.data?['isAssessment'] == true,
          )
          .toList();
      expect(assessmentTraces, isNotEmpty, reason: '工具执行后应有 assessment trace');
      for (final at in assessmentTraces) {
        expect(at.data?['assessmentType'], isNotNull);
        expect(at.data?['userMessage'], isNotNull);
      }

      // ---- 阶段时间线验证 ----
      final structured = response.structuredResponse;
      final timeline =
          (structured['uiPhaseTimelineV1'] as List?)
              ?.whereType<Map>()
              .map((p) => p.cast<String, dynamic>())
              .toList() ??
          [];

      expect(
        timeline.length,
        greaterThanOrEqualTo(2),
        reason: '至少应有 understanding + answering 两个阶段',
      );

      final phaseTypes = timeline
          .map((p) => (p['phaseType'] as String?) ?? '')
          .toList();

      // 核心阶段检查
      expect(
        phaseTypes.contains('understanding'),
        isTrue,
        reason: '应有 understanding 阶段',
      );
      expect(phaseTypes.last, equals('answering'), reason: '最后阶段应为 answering');

      // 搜索阶段或工具阶段检查
      final hasSearchPhase = phaseTypes.any(
        (t) => t.contains('search') || t.startsWith('tool:'),
      );
      expect(hasSearchPhase, isTrue, reason: '应有搜索或工具阶段，实际: $phaseTypes');

      // 搜索阶段应有 references
      final searchPhase = timeline.firstWhere((p) {
        final t = (p['phaseType'] as String?) ?? '';
        return t.contains('search') || t.startsWith('tool:');
      }, orElse: () => <String, dynamic>{});
      if (searchPhase.isNotEmpty) {
        final refs = (searchPhase['references'] as List?) ?? [];
        expect(refs, isNotEmpty, reason: '搜索阶段应产出 references');
        final summary = (searchPhase['summary'] as String?) ?? '';
        expect(summary.contains('资料'), isTrue, reason: '搜索阶段 summary 应提及资料数量');
      }

      // 所有阶段标题应为中文
      for (final phase in timeline) {
        final title = (phase['title'] as String?) ?? '';
        expect(title, isNotEmpty, reason: '每个阶段必须有标题');
      }

      // 所有阶段应为 completed
      for (final phase in timeline) {
        expect(
          phase['status'],
          equals('completed'),
          reason: '阶段 "${phase['phaseType']}" 应为 completed',
        );
      }

      // ---- 禁止内部字符串泄露 ----
      for (final phase in timeline) {
        final title = (phase['title'] as String?) ?? '';
        final summary = (phase['summary'] as String?) ?? '';
        final allText = '$title $summary';
        expect(allText.contains('contractVersion'), isFalse);
        expect(allText.contains('AssistantTrace'), isFalse);
        expect(allText.contains('toolStart'), isFalse);
      }

      // ---- 最终答案应包含天气信息 ----
      final uiAnswer =
          (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final mdText = (uiAnswer['markdownText'] as String?) ?? '';
      final summaryText = (uiAnswer['summaryText'] as String?) ?? '';
      final combined = '$mdText $summaryText ${response.finalText}';
      expect(
        combined.contains('天气') ||
            combined.contains('温度') ||
            combined.contains('深圳') ||
            combined.contains('晴'),
        isTrue,
        reason: '最终答案应包含天气相关内容',
      );

      expect(
        structured['processSummaryV1'],
        contains('已核对 2 个天气来源'),
        reason: '应输出统一的一行过程摘要',
      );
      expect(
        structured['processReferenceCountV1'],
        equals(2),
        reason: '应输出可展开来源计数',
      );
      final uiProcessBlocks =
          (structured['uiProcessContentBlocks'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(uiProcessBlocks, isNotEmpty, reason: '应产出统一过程区结构块');
      expect(uiProcessBlocks.first['type'], equals('searchSummary'));
      expect(
        (uiProcessBlocks.first['text'] as String?) ?? '',
        contains('天气来源'),
      );
      final intentGraph =
          (structured['intentGraph'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(intentGraph['primarySkill'], equals('weather'));
      expect(intentGraph['problemShape'], equals('single_skill'));
      final skillRuns =
          (structured['skillRuns'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(skillRuns, isNotEmpty, reason: '应输出 skillRuns[]');
      expect(skillRuns.first['domainId'], equals('weather'));
      final aggregationState =
          (structured['aggregationState'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(aggregationState['finalAnswerReady'], isTrue);
      final userEvents =
          (structured['userEvents'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(userEvents, isNotEmpty, reason: '应输出 userEvents');
      expect(userEvents.first['scope'], equals('root'));
      final uiProcessTimelineV2 =
          (structured['uiProcessTimelineV2'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(uiProcessTimelineV2, isNotEmpty, reason: '应输出 uiProcessTimelineV2');
      expect(
        uiProcessTimelineV2.last['summary'],
        contains('已核对'),
        reason: 'timeline v2 应保留最终过程摘要',
      );
    });

    test('onDelta 流式思考被正确传递和记录', () async {
      final traces = <AssistantTraceEvent>[];
      await loop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_delta',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气'),
          ],
        ),
        onTraceEvent: traces.add,
      );

      expect(mockLlm.thinkingDeltas, isNotEmpty, reason: 'onDelta 回调应被调用');

      final progressEvents = traces
          .where((t) => t.type == AssistantTraceEventType.thinkingProgress)
          .toList();
      expect(
        progressEvents,
        isNotEmpty,
        reason: 'thinkingProgress 事件应通过 trace 流出',
      );

      // 第一轮应为 understanding 阶段
      final firstProgress = progressEvents.first;
      expect(
        firstProgress.data?['phase'],
        equals('understanding'),
        reason: '第一轮思考应标记为 understanding 阶段',
      );
    });

    test('天气搜索失败时生成高质量 fallback 与统一过程摘要', () async {
      final fallbackToolRegistry = AssistantToolRegistry()
        ..register(_FailingWeatherSearchTool());
      final fallbackLoop = PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: _WeatherFallbackLlm(),
          toolRegistry: fallbackToolRegistry,
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions_fallback.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/memory_fallback.json',
          ),
        ),
      );

      final response = await fallbackLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_weather_fallback',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );

      final structured = response.structuredResponse;
      final uiAnswer =
          (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final markdown = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
      expect(markdown, contains('## 🌤️ 深圳 天气'));
      expect(markdown, contains('暂时查不到实时天气数据'));
      expect(markdown, contains('中国天气网'));
      expect(
        structured['processSummaryV1'],
        contains('已尝试获取实时天气'),
        reason: 'fallback 也应给出统一过程摘要',
      );
      expect(structured['processReferenceCountV1'], equals(0));
      final uiProcessBlocks =
          (structured['uiProcessContentBlocks'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(uiProcessBlocks, isNotEmpty);
      expect(uiProcessBlocks.first['type'], equals('text'));
    });

    test('原始 XML tool_call 不会泄漏到最终天气回答', () async {
      final xmlLoop = PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: _XmlLeakWeatherLlm(),
          toolRegistry: AssistantToolRegistry(),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions_xml.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory_xml.json'),
        ),
      );

      final response = await xmlLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_weather_xml',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );

      final structured = response.structuredResponse;
      final uiAnswer =
          (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final markdown = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
      expect(markdown, isNot(contains('<tool_call>')));
      expect(markdown, contains('## 🌤️ 深圳 天气'));
      expect(markdown, contains('暂时查不到实时天气数据'));
    });
  });
}
