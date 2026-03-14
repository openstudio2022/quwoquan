import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/personal_assistant/engine/agent_loop.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/process_journal_bus.dart';
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
          'problemClass': 'realtime_info',
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
            'contractVersion': 'assistant_turn',
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
            'reasonShort': '用户想了解深圳天气，我需要搜索最新的天气信息。',
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
        'contractVersion': 'assistant_turn',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'answer',
        'slotFillPlan': {
          'city': {'value': '深圳', 'source': 'user_query_llm', 'confidence': 0.98},
        },
        'slotState': {
          'slotValues': {
            'city': {'value': '深圳', 'source': 'user_query'},
          },
        },
        'userMarkdown': '## 深圳天气\n\n今天深圳天气晴朗，温度约25°C，适合户外活动。',
        'result': {'text': '今天深圳天气晴朗，温度约25°C。', 'interpretation': '深圳当前天气概况'},
        'evidence': [
          {'claim': '温度25°C', 'source': 'web_search', 'confidence': 'high'},
        ],
        'reasonShort': '搜索结果显示深圳今天晴，温度25°C，我来整理回答。',
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
        'authorityDomains': <String>['weather.com.cn', 'cma.cn'],
        'totalReferences': 2,
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

class _UsageLedgerWeatherLlm implements AssistantLlmProvider {
  int totalCallCount = 0;
  int totalTokensIssued = 0;

  AssistantModelOutput _withUsage({
    required String text,
    List<AssistantToolCall> toolCalls = const <AssistantToolCall>[],
  }) {
    totalCallCount += 1;
    final entry = <String, dynamic>{
      'provider': 'mock',
      'modelId': 'usage-ledger-model',
      'modelRef': 'usage-ledger-model',
      'source': 'provider',
      'streaming': false,
      'inputTokens': 80 + totalCallCount,
      'outputTokens': 20 + totalCallCount,
      'totalTokens': 100 + totalCallCount * 2,
      'latencyMs': 10,
    };
    totalTokensIssued += entry['totalTokens'] as int;
    return AssistantModelOutput(
      text: text,
      toolCalls: toolCalls,
      usageEntries: <Map<String, dynamic>>[entry],
    );
  }

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
    final isPlannerCall =
        templateId == 'planner.global_plan' ||
        templateId == 'planner.postcondition_check';
    final isSynthesisCall =
        templateId.contains('synthesizer') ||
        templateId.contains('final_answer');
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    final hasToolMessage = messages.any((item) => item['role'] == 'tool');

    if (!isPlannerCall && !isSynthesisCall) {
      return _withUsage(text: '{"summary":"用户想查询深圳天气。"}');
    }
    if (isIntentStage) {
      return _withUsage(
        text: jsonEncode(const <String, dynamic>{
          'primaryDomainId': 'weather',
          'secondaryDomains': <String>[],
          'inferredMotive': '查询深圳实时天气',
          'problemClass': 'realtime_info',
          'mode': 'qa',
          'queryNormalization': <String, dynamic>{'query': '深圳天气怎么样'},
        }),
      );
    }
    if (isPlannerCall && !hasToolMessage) {
      return _withUsage(
        text: jsonEncode(<String, dynamic>{
          'contractVersion': 'assistant_turn',
          'decision': {'nextAction': 'tool_call'},
          'toolCalls': [
            {
              'tool': 'web_search',
              'arguments': {
                'query': '深圳天气实况 今天 温度 湿度',
                'queryVariants': <String>['深圳今天天气实况'],
                'freshnessHoursMax': 6,
              },
            },
          ],
        }),
        toolCalls: const <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': '深圳天气实况 今天 温度 湿度',
              'queryVariants': <String>['深圳今天天气实况'],
              'freshnessHoursMax': 6,
            },
          ),
        ],
      );
    }
    return _withUsage(
      text: jsonEncode(<String, dynamic>{
        'contractVersion': 'assistant_turn',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '深圳天气晴朗，约 25°C。',
        'result': {'text': '深圳天气晴朗，约 25°C。', 'interpretation': '天气概况'},
        'selfCheck': {
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': {'whyThisAnswer': '基于天气结果整理', 'riskFlags': <String>[]},
        'modelSelfScore': {'score': 95, 'reason': '可直接回答'},
        'toolCalls': <dynamic>[],
      }),
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
          'problemClass': 'realtime_info',
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
          'contractVersion': 'assistant_turn',
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
        'contractVersion': 'assistant_turn',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'fallback',
        'slotFillPlan': {
          'city': {'value': '深圳', 'source': 'user_query_llm', 'confidence': 0.98},
        },
        'slotState': {
          'slotValues': {
            'city': {'value': '深圳', 'source': 'user_query'},
          },
        },
        'result': {'text': '搜索服务暂时不可用', 'interpretation': '搜索服务暂时不可用'},
      }),
    );
  }
}

class _FallbackAdaptiveLlm implements AssistantLlmProvider {
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
    final isPlannerCall =
        templateId == 'planner.global_plan' ||
        templateId == 'planner.postcondition_check';
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'primaryDomainId': 'fallback_general_search',
          'secondaryDomains': <String>[],
          'inferredMotive': '对比分析科技新闻与 AI 行业走势',
          'problemClass': 'complex_reasoning',
          'mode': 'hybrid',
          'queryNormalization': <String, dynamic>{
            'query': '今天全球科技新闻重点和AI行业走势对比分析',
          },
        }),
      );
    }
    if (isPlannerCall) {
      planCallCount += 1;
      if (planCallCount == 1 && availableTools.contains('web_search')) {
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractVersion': 'assistant_turn',
            'decision': <String, dynamic>{'nextAction': 'tool_call'},
            'toolCalls': <Map<String, dynamic>>[
              <String, dynamic>{
                'tool': 'web_search',
                'arguments': <String, dynamic>{
                  'query': '今天全球科技新闻重点和AI行业走势',
                  'queryVariants': <String>[
                    '今日科技新闻 AI 行业 重点',
                    '全球科技头条 人工智能 行业走势',
                  ],
                },
              },
            ],
            'reasonShort': '我先收集今天的科技新闻和 AI 行业动态，再做对比整理。',
          }),
          toolCalls: const <AssistantToolCall>[
            AssistantToolCall(
              name: 'web_search',
              arguments: <String, dynamic>{
                'query': '今天全球科技新闻重点和AI行业走势',
                'queryVariants': <String>[
                  '今日科技新闻 AI 行业 重点',
                  '全球科技头条 人工智能 行业走势',
                ],
              },
            ),
          ],
        );
      }
    }
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractVersion': 'assistant_turn',
        'decision': <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown':
            '## 科技与 AI 动态\n\n- 今天科技新闻聚焦大模型落地与算力投入。\n- AI 行业走势继续受资金与政策驱动。',
        'result': <String, dynamic>{
          'text': '今天科技新闻聚焦大模型落地与算力投入，AI 行业走势继续受资金与政策驱动。',
        },
        'toolCalls': const <dynamic>[],
        'selfCheck': const <String, dynamic>{},
        'diagnostics': const <String, dynamic>{},
        'modelSelfScore': const <String, dynamic>{'score': 88},
      }),
    );
  }
}

class _InvalidSynthesisNextActionLlm implements AssistantLlmProvider {
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
    final isPlannerCall =
        templateId == 'planner.global_plan' ||
        templateId == 'planner.postcondition_check';
    final isSynthesisCall =
        templateId.contains('synthesizer') ||
        templateId.contains('final_answer');
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    final hasToolMessage = messages.any((item) => item['role'] == 'tool');

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'primaryDomainId': 'weather',
          'secondaryDomains': <String>[],
          'inferredMotive': '查询深圳实时天气',
          'problemClass': 'realtime_info',
          'mode': 'qa',
          'queryNormalization': <String, dynamic>{'query': '深圳天气怎么样'},
        }),
      );
    }

    if (isPlannerCall && !hasToolMessage && availableTools.contains('web_search')) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractVersion': 'assistant_turn',
          'decision': <String, dynamic>{'nextAction': 'tool_call'},
          'toolCalls': <Map<String, dynamic>>[
            <String, dynamic>{
              'tool': 'web_search',
              'arguments': <String, dynamic>{'query': '深圳 今天 天气 实时'},
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

    if (isPlannerCall || isSynthesisCall) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractVersion': 'assistant_turn',
          'decision': <String, dynamic>{'nextAction': 'ask_user'},
          'messageKind': 'ask_user',
          'askUser': <String, dynamic>{
            'slotId': 'time',
            'prompt': '请补充时间范围',
            'suggestions': <String>['今天', '明天'],
          },
          'result': <String, dynamic>{'text': ''},
        }),
      );
    }

    return const AssistantModelOutput(text: '{"summary":"用户想查询天气。"}');
  }
}

class _MultiSkillProblemClassLlm implements AssistantLlmProvider {
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
    final isPlannerCall =
        templateId == 'planner.global_plan' ||
        templateId == 'planner.postcondition_check';
    final isSynthesisCall =
        templateId.contains('synthesizer') ||
        templateId.contains('final_answer');
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'primaryDomainId': 'weather',
          'secondaryDomains': <String>['fallback_general_search'],
          'inferredMotive': '先看天气，再结合出游场景给建议',
          'problemClass': 'complex_reasoning',
          'mode': 'hybrid',
        }),
      );
    }

    if (isSynthesisCall) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractVersion': 'assistant_turn',
          'decision': <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'userMarkdown': '## 深圳天气与出游建议\n\n- 今天天气适合出门。\n- 建议优先安排轻松的城市漫步和室内备选点。',
          'result': <String, dynamic>{
            'text': '深圳今天天气适合出门，旅游安排可优先轻松步行路线并保留室内备选。',
          },
        }),
      );
    }

    if (!isPlannerCall) {
      return const AssistantModelOutput(text: '{"summary":"用户想看天气并规划出游。"}');
    }

    final domainId = (templateVariables['domainId'] as String?)?.trim() ?? '';
    if (domainId == 'fallback_general_search') {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractVersion': 'assistant_turn',
          'decision': <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'userMarkdown': '## 深圳旅游建议\n\n- 白天可安排城市漫步。\n- 准备一个室内备选点以应对天气变化。',
          'result': <String, dynamic>{'text': '旅游建议以轻量户外活动为主，并准备室内备选。'},
        }),
      );
    }

    return AssistantModelOutput(
      text: jsonEncode(const <String, dynamic>{
        'contractVersion': 'assistant_turn',
        'decision': <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '## 深圳天气\n\n- 今天深圳天气温和，适合出门。',
        'result': <String, dynamic>{'text': '今天深圳天气温和，适合出门。'},
        'subagentPlan': <Map<String, dynamic>>[
          <String, dynamic>{
            'subagentId': 'travel_planner_1',
            'domainId': 'fallback_general_search',
            'problemClass': 'complex_reasoning',
            'mode': 'qa',
            'goal': '结合深圳今天天气，为用户补充出游安排与备选方案',
            'maxIterations': 4,
            'toolBudget': 2,
          },
        ],
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

class _JourneyReplayLlm implements AssistantLlmProvider {
  final Map<String, int> _plannerCallsByQuery = <String, int>{};
  final Map<String, List<List<Map<String, dynamic>>>> plannerRequestsByQuery =
      <String, List<List<Map<String, dynamic>>>>{};

  List<List<Map<String, dynamic>>> requestsFor(String query) =>
      plannerRequestsByQuery[query] ?? const <List<Map<String, dynamic>>>[];

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
    final isPlannerCall =
        templateId == 'planner.global_plan' ||
        templateId == 'planner.postcondition_check';
    final isSynthesisCall =
        templateId.contains('synthesizer') ||
        templateId.contains('final_answer') ||
        templateId.contains('output_contract.answer');
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    final query = _latestUserQuery(messages);

    if (isIntentStage) {
      final isTripPlanning = query.contains('九寨沟');
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'primaryDomainId': 'fallback_general_search',
          'secondaryDomains': const <String>[],
          'inferredMotive': isTripPlanning ? '想补齐旅行路线与住宿备选' : '想确认一个更聚焦的观赏时间问题',
          'problemClass': isTripPlanning ? 'complex_reasoning' : 'simple_qa',
          'mode': 'qa',
        }),
      );
    }

    if (!isPlannerCall && !isSynthesisCall) {
      return const AssistantModelOutput(text: '{"summary":"用户在继续追问旅行安排。"}');
    }

    if (isPlannerCall) {
      plannerRequestsByQuery
          .putIfAbsent(query, () => <List<Map<String, dynamic>>>[])
          .add(
            messages
                .map((item) => Map<String, dynamic>.from(item))
                .toList(growable: false),
          );
    }
    final count = isPlannerCall ? (_plannerCallsByQuery[query] ?? 0) + 1 : 0;
    if (isPlannerCall) {
      _plannerCallsByQuery[query] = count;
    }

    if (isPlannerCall && count == 1 && availableTools.contains('web_search')) {
      final reasonShort = query.contains('九寨沟')
          ? '先把路线、住宿和观景时间拆开核对，后面更容易收敛。'
          : '先确认观赏时间和天气窗口，结论才更稳。';
      onDelta?.call(reasonShort);
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'contractVersion': 'assistant_turn',
          'phaseId': 'understanding',
          'actionCode': 'frame_problem',
          'reasonCode': 'align_goal',
          'reasonShort': '用户想了解$query，我需要搜索最新资料。',
          'decision': const <String, dynamic>{'nextAction': 'tool_call'},
          'toolCalls': <Map<String, dynamic>>[
            <String, dynamic>{
              'tool': 'web_search',
              'arguments': <String, dynamic>{
                'query': query,
                'queryTasks': query.contains('九寨沟')
                    ? <Map<String, dynamic>>[
                        <String, dynamic>{'label': '路线可选项'},
                        <String, dynamic>{'label': '住宿备选'},
                        <String, dynamic>{'label': '观景时间'},
                      ]
                    : <Map<String, dynamic>>[
                        <String, dynamic>{'label': '最佳月份'},
                        <String, dynamic>{'label': '天气窗口'},
                      ],
                'provider': 'mock_search',
              },
            },
          ],
        }),
        toolCalls: <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': query,
              'queryTasks': query.contains('九寨沟')
                  ? <Map<String, dynamic>>[
                      <String, dynamic>{'label': '路线可选项'},
                      <String, dynamic>{'label': '住宿备选'},
                      <String, dynamic>{'label': '观景时间'},
                    ]
                  : <Map<String, dynamic>>[
                      <String, dynamic>{'label': '最佳月份'},
                      <String, dynamic>{'label': '天气窗口'},
                    ],
              'provider': 'mock_search',
            },
          ),
        ],
      );
    }

    final answerTitle = query.contains('九寨沟') ? '九寨沟方向备选方案' : '土拨鼠观赏时间建议';
    final answerBody = query.contains('九寨沟')
        ? '- 先看川西主线，再把九寨沟方向作为备选。\n- 住宿优先选交通更稳的节点。'
        : '- 更适合在草甸返青后的稳定天气窗口前往。\n- 先确认当地天气，再决定具体日期。';
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractVersion': 'assistant_turn',
        'phaseId': 'answering',
        'actionCode': 'compose_answer',
        'reasonCode': 'evidence_ready',
        'reasonShort': '搜索结果显示$query相关资料已够用，我来整理回答。',
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '## $answerTitle\n\n$answerBody',
        'result': <String, dynamic>{'text': answerBody},
        'evidence': <Map<String, dynamic>>[
          <String, dynamic>{
            'claim': answerTitle,
            'source': 'mock_search',
            'confidence': 'high',
          },
        ],
        'toolCalls': const <dynamic>[],
      }),
    );
  }

  String _latestUserQuery(List<Map<String, dynamic>> messages) {
    for (var i = messages.length - 1; i >= 0; i--) {
      final role = (messages[i]['role'] as String?)?.trim() ?? '';
      if (role == 'user') {
        final content = (messages[i]['content'] as String?)?.trim() ?? '';
        if (content.isNotEmpty) return content;
      }
    }
    return '';
  }
}

class _JourneyReplaySearchTool implements AssistantTool {
  int executeCount = 0;

  @override
  String get name => 'web_search';

  @override
  String get description => '网络搜索';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    executeCount += 1;
    final query = (arguments['query'] as String?)?.trim() ?? '';
    final tasks =
        (arguments['queryTasks'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final dimensions = tasks
        .map(
          (task) => ((task['dimension'] as String?)?.trim().isNotEmpty == true
              ? (task['dimension'] as String).trim()
              : (task['label'] as String?)?.trim() ?? ''),
        )
        .where((item) => item.isNotEmpty)
        .toList(growable: false);

    if (query.contains('九寨沟')) {
      return AssistantToolResult(
        success: true,
        message: '搜索完成',
        data: <String, dynamic>{
          'provider': 'mock_search',
          'qualityScore': 0.93,
          'summary': '九寨沟方向可以作为川西主线的备选，关键在路线取舍、住宿节点和观景时间。',
          'totalReferences': 3,
          'referenceCount': 3,
          'queryCount': dimensions.length,
          'queryLabels': dimensions,
          'queryTasks': tasks,
          'coveredDimensions': dimensions,
          'references': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '九寨沟景区游览提示',
              'url': 'https://example.com/jiuzhaigou-route',
              'source': '景区资料',
              'snippet': '旺季建议把主线景点和转场时间拆开规划，避免当天行程过满。',
              'queryTaskId': 'route_options',
              'dimension': '路线可选项',
            },
            <String, dynamic>{
              'title': '川西游线住宿节点整理',
              'url': 'https://example.com/jiuzhaigou-stay',
              'source': '出行攻略',
              'snippet': '住宿更适合卡在交通更稳的中转节点，方便第二天机动调整。',
              'queryTaskId': 'stay_options',
              'dimension': '住宿备选',
            },
            <String, dynamic>{
              'title': '九寨沟观景高峰与时间建议',
              'url': 'https://example.com/jiuzhaigou-timing',
              'source': '游览指南',
              'snippet': '观景时间更适合避开拥挤时段，把核心景观点留在光线更稳的时段。',
              'queryTaskId': 'viewing_window',
              'dimension': '观景时间',
            },
          ],
        },
      );
    }

    return AssistantToolResult(
      success: true,
      message: '搜索完成',
      data: <String, dynamic>{
        'provider': 'mock_search',
        'qualityScore': 0.9,
        'summary': '土拨鼠更适合在草甸返青后、天气稳定的窗口观察。',
        'totalReferences': 2,
        'referenceCount': 2,
        'queryCount': dimensions.length,
        'queryLabels': dimensions,
        'queryTasks': tasks,
        'coveredDimensions': dimensions,
        'references': <Map<String, dynamic>>[
          <String, dynamic>{
            'title': '高原草甸返青期观察建议',
            'url': 'https://example.com/marmot-season',
            'source': '生态观察',
            'snippet': '返青后的草甸食物更稳定，更容易观察到活动频率较高的土拨鼠。',
            'queryTaskId': 'best_month',
            'dimension': dimensions.isNotEmpty ? dimensions.first : '最佳月份',
          },
          <String, dynamic>{
            'title': '高原天气窗口与野生动物活动',
            'url': 'https://example.com/marmot-weather',
            'source': '户外提示',
            'snippet': '连续晴稳天气更适合观察，遇到风雪或强降温时活动明显减少。',
            'queryTaskId': 'weather_window',
            'dimension': dimensions.length > 1 ? dimensions[1] : '天气窗口',
          },
        ],
      },
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
        isTrue,
        reason: 'runtime 不再按问题类型擅自删改模型提供的 queryVariants',
      );
      expect(
        mockSearch.lastArguments.containsKey('queryTasks'),
        isFalse,
        reason: '未显式提供 typed queryTasks 时，runtime 不应根据天气场景自行扩写检索任务',
      );
      expect(
        mockSearch.lastArguments.containsKey('provider'),
        isTrue,
        reason: 'runtime 不再按问题类型或隐式 provider 策略重写模型给出的工具参数',
      );
      expect(
        mockSearch.lastArguments['freshnessHoursMax'],
        equals(6),
        reason: 'runtime 不再根据 query 文本将 freshnessHoursMax 收紧到额外的启发式阈值',
      );
      expect(
        (mockSearch.lastArguments['authorityDomains'] as List?) ??
            const <dynamic>[],
        isEmpty,
        reason: 'runtime 不再按 query 场景自动注入 authorityDomains，权威约束应来自 typed plan 或 tool metadata',
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
      final processJournalRaw =
          ((((structured['runArtifacts'] as Map?)?['processJournal'] as List?) ??
                  const <dynamic>[]))
              .whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false);
      final processJournal = processJournalRaw
          .map(ProcessJournalEvent.fromJson)
          .toList(growable: false);
      final displayJournal = ProcessJournalBus.toDisplaySnapshot(
        processJournal,
      );
      final journalStages = processJournal.map((item) => item.stage).toSet();
      final hasToolStartTrace = traces.any(
        (item) => item.type == AssistantTraceEventType.toolStart,
      );

      expect(
        processJournal,
        isNotEmpty,
        reason: '应输出 append-only processJournal',
      );
      expect(
        journalStages.contains('understanding'),
        isTrue,
        reason: '应覆盖 understanding 阶段',
      );
      expect(
        journalStages.contains('searching') || hasToolStartTrace,
        isTrue,
        reason: '检索阶段应以 processJournal 或真实 toolStart 证据体现',
      );
      expect(
        journalStages.contains('answering'),
        isTrue,
        reason: '应覆盖 answering 阶段',
      );
      expect(
        journalStages.contains('completed'),
        isTrue,
        reason: '应覆盖 completed 阶段',
      );

      final searchUpdates = displayJournal
          .where(
            (item) =>
                item.type == ProcessJournalEventType.sourceUpdate &&
                item.stage == 'searching',
          )
          .toList(growable: false);
      if (searchUpdates.isNotEmpty) {
        expect(
          searchUpdates.first.references,
          isNotEmpty,
          reason: '搜索阶段 sourceUpdate 应带引用',
        );
        expect(
          searchUpdates.first.message.contains('来源') ||
              searchUpdates.first.message.contains('资料') ||
              searchUpdates.first.message.contains('交叉看'),
          isTrue,
          reason: '搜索阶段叙事应是面向用户语言',
        );
      } else {
        expect(
          hasToolStartTrace,
          isTrue,
          reason: '若不再合成 searching/sourceUpdate，至少应保留真实 toolStart 证据',
        );
      }

      for (final event in displayJournal) {
        final allText = '${event.message} ${event.payload}';
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
      final runArtifacts =
          (structured['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final artifacts = RunArtifacts.fromJson(runArtifacts);
      expect(
        (runArtifacts['machineEnvelope'] as String?)?.trim(),
        equals(response.finalText.trim()),
      );
      expect(
        (runArtifacts['displayMarkdown'] as String?)?.trim(),
        equals(mdText.trim()),
      );
      expect(
        ((runArtifacts['displayPlainText'] as String?)?.trim() ?? '')
            .isNotEmpty,
        isTrue,
        reason: 'runArtifacts 应落纯文本展示账',
      );
      expect(
        artifacts.evidenceLedger,
        isNotEmpty,
        reason: 'M3 应将证据账写入 runArtifacts',
      );
      expect(
        artifacts.evidenceLedger.any(
          (entry) => entry.url.contains('weather.cma.cn'),
        ),
        isTrue,
        reason: '证据账应收拢权威天气来源',
      );
      expect(
        artifacts.slotState.slotValueOf('city')?.value,
        equals('深圳'),
        reason: 'M4 应把关键槽位状态写入 runArtifacts',
      );
      expect(
        artifacts.domainPolicyBundle?.domainId,
        equals('weather'),
        reason: 'M4 应同步落 domainPolicyBundle',
      );
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
        structured['processSummary'],
        contains('已核对'),
        reason: '应输出统一的一行过程摘要',
      );
      expect(
        structured['processReferenceCount'],
        greaterThanOrEqualTo(1),
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
      expect((uiProcessBlocks.first['text'] as String?) ?? '', contains('来源'));
      final blockRefs =
          (uiProcessBlocks.first['references'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(
        blockRefs.length,
        greaterThanOrEqualTo(1),
        reason: '天气过程区应保留至少一个筛选后的权威来源',
      );
      expect(
        blockRefs.any(
          (item) => ((item['url'] as String?) ?? '').contains('weather.cma.cn'),
        ),
        isTrue,
        reason: '天气过程区应优先展示权威天气来源',
      );
      final intentGraph =
          (structured['intentGraph'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(intentGraph['primarySkill'], equals('weather'));
      expect(intentGraph['problemClass'], equals('realtime_info'));
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
      final conversationDecision =
          (structured['conversationStateDecision'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(
        conversationDecision['finalAnswerMode'],
        anyOf(equals('full'), equals('bounded_answer')),
      );
      expect(conversationDecision['nextAction'], equals('answer'));
      expect(
        structured.containsKey('userEvents'),
        isFalse,
        reason: 'legacy userEvents 应已清退',
      );
      expect(
        structured.containsKey('uiProcessTimelineV2'),
        isFalse,
        reason: 'legacy uiProcessTimelineV2 不应再作为新结果输出',
      );
      expect(
        structured.containsKey('uiPhaseTimelineV1'),
        isFalse,
        reason: 'legacy uiPhaseTimelineV1 不应再作为新结果输出',
      );
      final userMessages = displayJournal
          .map((item) => item.displayMessage.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
      expect(
        userMessages.any((item) => item.contains('深圳') && item.contains('天气')),
        isTrue,
        reason: '天气过程语言应带当前问题语义，而不是只显示系统状态',
      );
      expect(
        userMessages.any((item) => item.contains('先确认') || item.contains('我在')),
        isTrue,
        reason: '过程事件应解释当前为什么这样收敛，而不是只报系统状态',
      );
      expect(
        userMessages.any(
          (item) => item.contains('用户想了解') || item.contains('我需要搜索'),
        ),
        isFalse,
        reason: '过程事件应尽量避免把内部推理口吻直接暴露给用户',
      );
      expect(
        userMessages.any(
          (item) =>
              item.contains('已识别问题方向，准备开始处理') ||
              item.contains('这部分答案已整理完成') ||
              item.contains('正在补充这一部分信息'),
        ),
        isFalse,
        reason: '过程事件不应退化成通用系统状态文案',
      );
      final rootIntentEntry = displayJournal.firstWhere(
        (item) => item.nodeId.startsWith('root.intent'),
        orElse: () => const ProcessJournalEvent(
          eventId: '',
          type: ProcessJournalEventType.narrativeCommit,
          stage: '',
        ),
      );
      final rootIntentSummary = rootIntentEntry.displayMessage;
      expect(
        rootIntentSummary.isNotEmpty,
        isTrue,
        reason: '首个阶段应先向用户解释为什么从这个方向开始处理，而不是只报内部状态',
      );
      expect(rootIntentEntry.actionCode, equals('frame_problem'));
      expect(rootIntentEntry.reasonCode, isNotEmpty);
      expect(rootIntentSummary, isNot(contains('我先帮你把')));
      expect(rootIntentSummary, isNot(contains('收一收')));
      expect(rootIntentSummary, isNot(contains('你更像是想知道')));
      expect(
        displayJournal.any((item) => item.references.isNotEmpty) || hasToolStartTrace,
        isTrue,
        reason: '若过程区不再合成 references 事件，至少要保留真实工具执行证据',
      );
    });

    test('上一轮 slotState 与 domainPolicyBundle 会续转到下一轮', () async {
      final carryLlm = _WeatherPipelineLlm();
      final carrySearch = _FakeWeatherSearchTool();
      final carryLoop = PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: carryLlm,
          toolRegistry: AssistantToolRegistry()..register(carrySearch),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/carry_sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/carry_memory.json',
          ),
        ),
      );

      final firstResponse = await carryLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_slot_carry',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );
      final firstArtifacts = firstResponse.runArtifacts;
      expect(firstArtifacts, isNotNull);
      expect(
        firstArtifacts!.slotState.slotValueOf('city')?.value,
        equals('深圳'),
      );

      final secondLoop = PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: _WeatherPipelineLlm(),
          toolRegistry: AssistantToolRegistry()
            ..register(_FakeWeatherSearchTool()),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/carry_sessions_second.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/carry_memory_second.json',
          ),
        ),
      );

      final secondResponse = await secondLoop.run(
        AssistantRunRequest(
          sessionId: 'pipeline_slot_carry',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '明天呢'),
          ],
          contextScopeHint: <String, dynamic>{
            'runArtifacts': firstArtifacts.toJson(),
          },
        ),
      );

      final secondArtifacts = secondResponse.runArtifacts;
      expect(secondArtifacts, isNotNull);
      expect(
        secondArtifacts!.slotState.slotValueOf('city')?.value,
        equals('深圳'),
        reason: '未显式再说城市时，也应从上一轮槽位续转',
      );
      expect(secondArtifacts.domainPolicyBundle?.domainId, equals('weather'));

      final structured = secondResponse.structuredResponse;
      final decision =
          (structured['conversationStateDecision'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(decision['nextAction'], equals('answer'));
      expect(
        decision['finalAnswerMode'],
        anyOf(equals('full'), equals('bounded_answer')),
      );
      expect(structured['answerEligibility'], equals('eligible'));
    });

    test('最近两次真实追问样例不会跨轮污染 JSON、tool_call 与模板化过程话术', () async {
      final replayLlm = _JourneyReplayLlm();
      final replayMemory = AssistantMemoryRepository(
        ObjectBoxVectorStore(
          storagePath: '${tempDir.path}/journey_replay_memory.json',
        ),
      );
      final replayLoop = PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: replayLlm,
          toolRegistry: AssistantToolRegistry()
            ..register(_JourneyReplaySearchTool()),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/journey_replay_sessions.json',
        ),
        memoryRepository: replayMemory,
      );

      final firstResponse = await replayLoop.run(
        const AssistantRunRequest(
          sessionId: 'journey_replay_session',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(
              role: 'user',
              content: '如果把九寨沟方向考虑进去，多给我几个备选方案',
            ),
          ],
        ),
      );

      final secondResponse = await replayLoop.run(
        const AssistantRunRequest(
          sessionId: 'journey_replay_session',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '土拨鼠观赏最佳时间'),
          ],
        ),
      );

      final secondPlannerRequests = replayLlm.requestsFor('土拨鼠观赏最佳时间');
      expect(secondPlannerRequests, isNotEmpty, reason: '应记录第二轮规划输入，便于验证跨轮清洗');
      final secondPlannerTranscript = secondPlannerRequests
          .expand((request) => request)
          .map((item) => (item['content'] ?? '').toString())
          .join('\n');
      for (final forbidden in const <String>[
        'assistant_turn',
        'contractVersion',
        '<tool_call>',
        '<session_history>',
        '<memory_recall>',
        '"recentCityMentions"',
        '"gpsCity"',
        '"historySummarySnippet"',
        '"longtermMemorySummary"',
        'machineEnvelope',
        'longtermMemorySummary":"{',
        'historySummarySnippet":"{',
      ]) {
        expect(
          secondPlannerTranscript.contains(forbidden),
          isFalse,
          reason: '第二轮输入不应再带入内部污染片段: $forbidden',
        );
      }

      final sessionManager = AssistantSessionManager(
        storagePath: '${tempDir.path}/journey_replay_sessions.json',
      );
      await sessionManager.load();
      final summary = sessionManager.summarizeRecent('journey_replay_session');
      expect(summary, isNotEmpty);
      for (final forbidden in const <String>[
        'assistant_turn',
        'contractVersion',
        'queryTasks',
        'tool_call',
        '<tool_call>',
        'provider',
        'machineEnvelope',
      ]) {
        expect(
          summary.contains(forbidden),
          isFalse,
          reason: 'session_history 摘要不应再带入内部污染片段: $forbidden',
        );
      }

      final recalledMemory = await replayMemory.recallByText(
        query: '土拨鼠观赏最佳时间',
        limit: 5,
      );
      final recalledText = recalledMemory.map((item) => item.text).join('\n');
      for (final forbidden in const <String>[
        'assistant_turn',
        'contractVersion',
        'queryTasks',
        'tool_call',
        '<tool_call>',
        'provider',
        'machineEnvelope',
      ]) {
        expect(
          recalledText.contains(forbidden),
          isFalse,
          reason: 'longterm_memory 不应再带入内部污染片段: $forbidden',
        );
      }

      final processJournal =
          ((((secondResponse.structuredResponse['runArtifacts'] as Map?)
                          ?['processJournal'] as List?) ??
                  const <dynamic>[]))
              .whereType<Map>()
              .map(
                (item) => ProcessJournalEvent.fromJson(item.cast<String, dynamic>()),
              )
              .toList(growable: false);
      final displayJournal = ProcessJournalBus.toDisplaySnapshot(
        processJournal,
      );
      final narrativeEvents = displayJournal
          .where(
            (item) =>
                item.type == ProcessJournalEventType.narrativeCommit ||
                item.type == ProcessJournalEventType.liveCursor ||
                item.type == ProcessJournalEventType.sourceUpdate,
          )
          .toList(growable: false);
      expect(narrativeEvents, isNotEmpty);
      for (final event in narrativeEvents) {
        expect(event.reasonShort, isNotEmpty, reason: '过程事件应提供短理由');
        expect(event.actionCode, isNotEmpty, reason: '过程事件应提供 actionCode');
        expect(event.reasonCode, isNotEmpty, reason: '过程事件应提供 reasonCode');
        expect(event.source, isNotEmpty, reason: '过程事件应提供 source');
        expect(event.displayMessage, isNot(contains('我先帮你把')));
        expect(event.displayMessage, isNot(contains('收一收')));
        expect(event.displayMessage, isNot(contains('你更像是想知道')));
        expect(event.displayMessage, isNot(contains('我先替你')));
      }

      expect(firstResponse.displayMarkdown, contains('九寨沟'));
      expect(firstResponse.displayMarkdown, isNot(contains('先给你当前最稳的部分')));
      expect(secondResponse.displayMarkdown, contains('土拨鼠'));
      expect(secondResponse.displayMarkdown, isNot(contains('先给你当前最稳的部分')));
      expect(
        secondResponse.displayMarkdown,
        isNot(contains('contractVersion')),
      );
      expect(secondResponse.displayMarkdown, isNot(contains('<tool_call>')));
      expect(secondResponse.displayMarkdown, isNot(contains('九寨沟方向备选方案')));
      expect(
        secondResponse.displayPlainText,
        anyOf(contains('天气'), contains('窗口')),
      );
      expect(secondResponse.displayPlainText, isNot(contains('九寨沟')));
      expect(secondResponse.displayPlainText, isNot(contains('用户在继续追问旅行安排')));
      expect(secondResponse.displayPlainText, isNot(contains('queryTasks')));
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

    test('uiUsageStats 使用 usage ledger 统计真实模型调用与 token', () async {
      final usageLlm = _UsageLedgerWeatherLlm();
      final usageSearch = _FakeWeatherSearchTool();
      final usageLoop = PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: usageLlm,
          toolRegistry: AssistantToolRegistry()..register(usageSearch),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/usage_sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/usage_memory.json',
          ),
        ),
      );

      final response = await usageLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_usage_ledger',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );

      final usage =
          ((response.structuredResponse['uiUsageStats'] as Map?) ??
                  (response.structuredResponse['uiUsageStatsV1'] as Map?))
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final usageLedger = (usage['usageLedger'] as List?) ?? const <dynamic>[];

      expect(usage['modelCallCount'], equals(usageLlm.totalCallCount));
      expect(usage['totalTokens'], equals(usageLlm.totalTokensIssued));
      expect(usage['tokenSampleCount'], equals(usageLlm.totalCallCount));
      expect(((usage['tokenSource'] as String?) ?? '').isNotEmpty, isTrue);
      expect(usageLedger.length, equals(usageLlm.totalCallCount));
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
      expect(markdown, isEmpty);
      expect(response.degraded, isTrue);
      expect(markdown, isNot(contains('<tool_call>')));
      expect(markdown, isNot(contains('contractVersion')));
      expect(
        ((structured['processSummary'] as String?)?.trim() ?? '').isNotEmpty,
        isTrue,
        reason: 'fallback 也应给出统一过程摘要',
      );
      expect(structured['processReferenceCount'], equals(0));
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
      expect(markdown, isEmpty);
      expect(response.degraded, isTrue);
      expect(markdown, isNot(contains('contractVersion')));
    });

    test('synthesis 非 answer 输出不会被静默改写成 answer', () async {
      final invalidSynthesisLoop = PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: _InvalidSynthesisNextActionLlm(),
          toolRegistry: AssistantToolRegistry()..register(_FakeWeatherSearchTool()),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions_invalid_synthesis.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/memory_invalid_synthesis.json',
          ),
        ),
      );

      final response = await invalidSynthesisLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_invalid_synthesis',
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
      final plainText = (uiAnswer['plainText'] as String?)?.trim() ?? '';

      expect(response.degraded, isTrue);
      expect(markdown, isEmpty);
      expect(plainText, contains('模型输出无效'));
    });

    test('fallback 会按问题类型自适应执行壳子，而非固定 simple_qa', () async {
      final adaptiveSearch = _FakeWeatherSearchTool();
      final adaptiveToolRegistry = AssistantToolRegistry()
        ..register(adaptiveSearch);
      final adaptiveLoop = PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: _FallbackAdaptiveLlm(),
          toolRegistry: adaptiveToolRegistry,
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions_fallback_adaptive.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/memory_fallback_adaptive.json',
          ),
        ),
      );

      final response = await adaptiveLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_fallback_adaptive',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(
              role: 'user',
              content: '帮我对比分析今天全球科技新闻重点和AI行业走势',
            ),
          ],
        ),
      );

      final structured = response.structuredResponse;
      final skillRuns =
          (structured['skillRuns'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(skillRuns, isNotEmpty);
      expect(skillRuns.first['domainId'], equals('fallback_general_search'));
      expect(skillRuns.first['problemClass'], equals('complex_reasoning'));
      final shell =
          (skillRuns.first['shell'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(shell['maxIterations'], equals(4));
      expect(shell['toolBudget'], equals(2));
      expect(shell['variantBudget'], equals(1));
      expect(shell['reflectionBudget'], equals(1));
      final queryTasks =
          (adaptiveSearch.lastArguments['queryTasks'] as List?) ??
          const <dynamic>[];
      expect(
        queryTasks.length,
        equals(0),
        reason: 'runtime 不再根据 fallback 壳子自行扩写 queryTasks，应仅消费模型/typed plan 已提供的检索任务',
      );
      expect(
        adaptiveSearch.lastArguments.containsKey('queryVariants'),
        isTrue,
        reason: 'runtime 不再为 fallback 壳子改写检索参数，应保留模型原始 queryVariants',
      );
    });

    test('多 skill 分发时每个 subagent 都带独立 problemClass 并各自收敛', () async {
      final multiToolRegistry = AssistantToolRegistry()
        ..register(_FakeWeatherSearchTool());
      final multiLoop = PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: _MultiSkillProblemClassLlm(),
          toolRegistry: multiToolRegistry,
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions_multiskill_problem_class.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/memory_multiskill_problem_class.json',
          ),
        ),
      );

      final response = await multiLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_multiskill_problem_class',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(
              role: 'user',
              content: '深圳今天天气如何，顺便给我一个轻松点的旅游建议',
            ),
          ],
        ),
      );

      final structured = response.structuredResponse;
      final intentGraph =
          (structured['intentGraph'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(intentGraph['primarySkill'], equals('weather'));
      expect(intentGraph['problemClass'], equals('complex_reasoning'));

      final subagentPlan =
          (structured['subagentPlan'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(subagentPlan, isNotEmpty);
      expect(
        subagentPlan.first['problemClass'],
        equals('complex_reasoning'),
        reason: '子任务计划必须显式携带自己的 problemClass',
      );

      final skillRuns =
          (structured['skillRuns'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(skillRuns.length, equals(2));

      final weatherRun = skillRuns.firstWhere(
        (item) => item['domainId'] == 'weather',
      );
      expect(weatherRun['problemClass'], equals('realtime_info'));

      final travelRun = skillRuns.firstWhere(
        (item) => item['domainId'] == 'fallback_general_search',
      );
      expect(travelRun['domainId'], equals('fallback_general_search'));
      expect(travelRun['problemClass'], equals('complex_reasoning'));
      final travelShell =
          (travelRun['shell'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(travelShell['problemClass'], equals('complex_reasoning'));
      expect(travelShell['maxIterations'], equals(4));
      expect(travelShell['toolBudget'], equals(2));
      expect(travelShell['variantBudget'], equals(1));
      expect(travelShell['reflectionBudget'], equals(1));
    });
  });
}
