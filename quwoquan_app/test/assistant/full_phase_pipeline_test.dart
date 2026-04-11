import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/orchestration/local_phase_execution_owner.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

Map<String, dynamic> _intentPlanningEnvelope({
  required String primarySkill,
  required String inferredMotive,
  required String problemClass,
  String mode = 'qa',
  List<String> secondarySkills = const <String>[],
  String normalizedQuery = '',
  List<String> entityAnchors = const <String>[],
  List<Map<String, dynamic>> queryTasks = const <Map<String, dynamic>>[],
}) {
  return <String, dynamic>{
    'contractId': 'assistant_turn',
    'messageKind': 'progress',
    'phaseId': 'understanding',
    'actionCode': 'frame_problem',
    'reasonCode': 'align_goal',
    'reasonShort': '先确认问题焦点，再组织执行。',
    'decision': <String, dynamic>{
      'nextAction': 'answer',
      'confidence': 0.78,
      'reasoning': '先锁定技能、问题类型和检索意图',
    },
    'userMarkdown': '我先聚焦问题主线，再开始处理。',
    'result': <String, dynamic>{
      'text': '',
      'summary': '进入理解阶段',
      'interpretation': inferredMotive,
      'actionHints': const <String>[],
    },
    'intentGraph': <String, dynamic>{
      'userGoal': inferredMotive,
      'problemShape': secondarySkills.isEmpty ? 'single_skill' : 'multi_skill',
      'primarySkill': primarySkill,
      'problemClass': problemClass,
      'inferredMotive': inferredMotive,
      'secondarySkills': secondarySkills,
      'entityAnchors': entityAnchors,
      'queryNormalization': normalizedQuery.isNotEmpty
          ? <String, dynamic>{'normalizedQuery': normalizedQuery}
          : const <String, dynamic>{},
      'queryTasks': queryTasks,
      'contextSlots': const <String, dynamic>{},
      'globalConstraints': <String, dynamic>{'mode': mode},
      'clarificationNeeded': false,
    },
    'selfCheck': <String, dynamic>{
      'goalSatisfied': true,
      'constraintSatisfied': true,
      'safetyBoundarySatisfied': true,
      'failedItems': const <String>[],
    },
    'diagnostics': <String, dynamic>{
      'emergedTags': const <Map<String, dynamic>>[],
      'failedChecks': const <String>[],
      'parseStatus': '',
      'notes': const <String>[],
    },
  };
}

bool _isFinalAnswerTemplate(String templateId) =>
    templateId == 'synthesizer.final_answer';

bool _hasSubagentRuns(Map<String, dynamic> templateVariables) =>
    templateVariables['subagentRuns'] != null;

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

    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;

    if (!isPlannerCall && !isSynthesisCall) {
      return const AssistantModelOutput(text: '{"summary": "用户在询问深圳的天气情况。"}');
    }

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(
          _intentPlanningEnvelope(
            primarySkill: 'weather',
            inferredMotive: '查询深圳实时天气',
            problemClass: 'realtime_info',
            mode: 'qa',
            normalizedQuery: '深圳天气怎么样',
          ),
        ),
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
            'contractId': 'assistant_turn',
            'decision': {'nextAction': 'tool_call'},
            'toolCalls': [
              {
                'toolName': 'web_search',
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
        'contractId': 'assistant_turn',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'answer',
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
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
          'notes': <String>['基于搜索结果整理天气信息'],
        },
        'modelSelfScore': {'score': 92, 'reason': '准确回答天气查询'},
        'toolCalls': <dynamic>[],
      }),
    );
  }
}

class _ThreeSectionNormalizationWeatherLlm implements AssistantLlmProvider {
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
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    final hasToolMessage = messages.any((item) => item['role'] == 'tool');

    if (!isPlannerCall && !isSynthesisCall) {
      return const AssistantModelOutput(
        text: '{"summary": "用户想确认深圳今天的天气和出门准备。"}',
      );
    }

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          ..._intentPlanningEnvelope(
            primarySkill: 'weather',
            inferredMotive: '确认深圳今天的天气和出门准备',
            problemClass: 'realtime_info',
            mode: 'qa',
            normalizedQuery: '深圳今天下不下雨，要不要带伞',
          ),
          'understandingSnapshot': const <String, dynamic>{
            'userFacingSummary':
                '你现在主要想先确认深圳今天的天气结论，再决定出门要不要带伞。我会先核对今天的降雨情况和最影响出门判断的天气变化。',
            'intentSummary': '你现在主要想确认深圳今天的天气和出门准备',
            'concernPoints': <String>['是否会下雨', '要不要带伞'],
            'emotionSignal': 'neutral',
            'queryDesignSummary': '优先确认今天的降雨情况与出门判断最相关的天气变化。',
          },
        }),
      );
    }

    if (isPlannerCall &&
        !hasToolMessage &&
        availableTools.contains('web_search')) {
      planCallCount += 1;
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'contractId': 'assistant_turn',
          'decision': const <String, dynamic>{'nextAction': 'tool_call'},
          'toolCalls': <Map<String, dynamic>>[
            <String, dynamic>{
              'toolName': 'web_search',
              'arguments': <String, dynamic>{
                'query': '深圳 今日 降雨 带伞 建议',
                'queryVariants': <String>['深圳今天下不下雨', '深圳今天带伞建议'],
                'freshnessHoursMax': 6,
              },
            },
          ],
        }),
        toolCalls: const <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': '深圳 今日 降雨 带伞 建议',
              'queryVariants': <String>['深圳今天下不下雨', '深圳今天带伞建议'],
              'freshnessHoursMax': 6,
            },
          ),
        ],
      );
    }

    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': const <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown':
            '## 深圳天气\n\n- 深圳今天有雨，外出建议带伞。[来源1](https://weather.cma.cn/shenzhen)',
        'result': const <String, dynamic>{
          'text': '深圳今天有雨，外出建议带伞。',
          'summary': '深圳今天有雨，外出建议带伞',
          'interpretation': '确认深圳今天的天气和出门准备',
        },
        'understandingSnapshot': const <String, dynamic>{
          'userFacingSummary':
              'Shenzhen tian qi。\n我会先把最影响判断的关键信息核清，再把能直接支撑回答的依据收拢。',
          'intentSummary': '你现在主要想确认深圳今天的天气和出门准备',
          'concernPoints': <String>['是否会下雨', '要不要带伞'],
        },
        'retrievalProcessing': const <String, dynamic>{
          'processedDocumentCount': 6,
          'acceptedDocumentCount': 1,
          'processingSummary':
              '围绕你最关心的出门判断，已经确认今天有雨，这个信息足以直接决定要不要带伞；其余背景我不会展开。',
          'selectedKeyPoints': <String>['深圳今天有雨', '外出建议带伞'],
          'acceptedReferences': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '深圳天气预报 - 中国气象局',
              'url': 'https://weather.cma.cn/shenzhen',
              'source': '中国气象局',
              'snippet': '深圳今天有雨，外出建议带伞。',
            },
          ],
        },
        'answerProcessing': const <String, dynamic>{
          'readinessSummary': '最终答案会先直接告诉你今天是否下雨，再补一条带伞建议；其它背景不会继续展开。',
          'keyFacts': <String>['深圳今天有雨，外出建议带伞。'],
          'missingDimensions': <String>[],
          'retrieveMoreReason': '',
        },
        'evidence': const <Map<String, dynamic>>[
          <String, dynamic>{
            'evidenceId': 'weather_ev_1',
            'claim': '深圳今天有雨，外出建议带伞。',
            'title': '深圳天气预报 - 中国气象局',
            'url': 'https://weather.cma.cn/shenzhen',
            'source': '中国气象局',
            'snippet': '深圳今天有雨，外出建议带伞。',
            'text': '深圳今天有雨，外出建议带伞。',
          },
        ],
        'reasoningBasis': const <Map<String, dynamic>>[
          <String, dynamic>{
            'evidenceId': 'weather_ev_1',
            'claim': '深圳今天有雨，外出建议带伞。',
            'text': '降雨信息和出门建议已经交叉确认。',
            'confidence': 0.95,
          },
        ],
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
          'notes': <String>['three_section_normalization_fixture'],
        },
        'modelSelfScore': const <String, dynamic>{
          'score': 93,
          'reason': 'weather_evidence_ready',
        },
        'toolCalls': const <dynamic>[],
      }),
    );
  }
}

class _RootLevelIntentWeatherPipelineLlm implements AssistantLlmProvider {
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
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;

    if (!isPlannerCall && !isSynthesisCall) {
      return const AssistantModelOutput(text: '{"summary": "用户在询问深圳的天气情况。"}');
    }

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'userGoal': '查询深圳实时天气',
          'problemShape': 'single_skill',
          'primarySkill': 'weather',
          'problemClass': 'realtime_info',
          'inferredMotive': '查询深圳实时天气',
          'requiresExternalEvidence': true,
          'queryNormalization': <String, dynamic>{'normalizedQuery': '深圳天气怎么样'},
          'queryTasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'latest_signal',
              'dimension': 'latest_signal',
              'label': '最新天气',
              'query': '深圳 今日 最新天气 实况',
              'authorityDomains': <String>['weather.cma.cn'],
              'freshnessHoursMax': 1,
            },
          ],
          'authorityDomains': <String>['weather.cma.cn'],
          'freshnessHoursMax': 1,
          'globalConstraints': <String, dynamic>{'mode': 'qa'},
        }),
      );
    }

    if (isPlannerCall) {
      planCallCount += 1;
      if (planCallCount == 1 && availableTools.contains('web_search')) {
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractId': 'assistant_turn',
            'decision': {'nextAction': 'tool_call'},
            'toolCalls': [
              {
                'toolName': 'web_search',
                'arguments': {
                  'query': '深圳天气 实况 今日',
                  'freshnessHoursMax': 1,
                  'authorityDomains': <String>['weather.cma.cn'],
                },
              },
            ],
          }),
          toolCalls: const <AssistantToolCall>[
            AssistantToolCall(
              name: 'web_search',
              arguments: <String, dynamic>{
                'query': '深圳天气 实况 今日',
                'freshnessHoursMax': 1,
                'authorityDomains': <String>['weather.cma.cn'],
              },
            ),
          ],
        );
      }
    }

    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '深圳今天以晴到多云为主，适合安排外出。',
        'result': <String, dynamic>{
          'text': '深圳今天以晴到多云为主，适合安排外出。',
          'summary': '深圳天气适合外出',
          'interpretation': '深圳当前天气概况',
        },
        'selfCheck': <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
        'diagnostics': <String, dynamic>{
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
          'notes': <String>['root_level_intent_graph_recovered'],
        },
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
        'freshnessKnown': true,
        'freshnessSatisfied': true,
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
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    final hasToolMessage = messages.any((item) => item['role'] == 'tool');

    if (!isPlannerCall && !isSynthesisCall) {
      return _withUsage(text: '{"summary":"用户想查询深圳天气。"}');
    }
    if (isIntentStage) {
      return _withUsage(
        text: jsonEncode(
          _intentPlanningEnvelope(
            primarySkill: 'weather',
            inferredMotive: '查询深圳实时天气',
            problemClass: 'realtime_info',
            mode: 'qa',
            normalizedQuery: '深圳天气怎么样',
          ),
        ),
      );
    }
    if (isPlannerCall && !hasToolMessage) {
      return _withUsage(
        text: jsonEncode(<String, dynamic>{
          'contractId': 'assistant_turn',
          'decision': {'nextAction': 'tool_call'},
          'toolCalls': [
            {
              'toolName': 'web_search',
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
        'contractId': 'assistant_turn',
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
        'diagnostics': {
          'emergedTags': <Map<String, dynamic>>[],
          'failedChecks': <String>[],
          'parseStatus': '',
          'notes': <String>['基于天气结果整理'],
        },
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
        text: jsonEncode(
          _intentPlanningEnvelope(
            primarySkill: 'weather',
            inferredMotive: '查询深圳实时天气',
            problemClass: 'realtime_info',
            mode: 'qa',
            normalizedQuery: '深圳天气怎么样',
          ),
        ),
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
          'contractId': 'assistant_turn',
          'decision': {'nextAction': 'tool_call'},
          'toolCalls': [
            {
              'toolName': 'web_search',
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
        'contractId': 'assistant_turn',
        'decision': {'nextAction': 'answer'},
        'messageKind': 'fallback',
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
    final isPlannerCall = templateId == 'planner.global_plan';
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(
          _intentPlanningEnvelope(
            primarySkill: 'fallback_general_search',
            inferredMotive: '对比分析科技新闻与 AI 行业走势',
            problemClass: 'complex_reasoning',
            mode: 'hybrid',
            normalizedQuery: '今天全球科技新闻重点和AI行业走势对比分析',
          ),
        ),
      );
    }
    if (isPlannerCall) {
      planCallCount += 1;
      if (planCallCount == 1 && availableTools.contains('web_search')) {
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractId': 'assistant_turn',
            'decision': <String, dynamic>{'nextAction': 'tool_call'},
            'toolCalls': <Map<String, dynamic>>[
              <String, dynamic>{
                'toolName': 'web_search',
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
        'contractId': 'assistant_turn',
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
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    final hasToolMessage = messages.any((item) => item['role'] == 'tool');

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(
          _intentPlanningEnvelope(
            primarySkill: 'weather',
            inferredMotive: '查询深圳实时天气',
            problemClass: 'realtime_info',
            mode: 'qa',
            normalizedQuery: '深圳天气怎么样',
          ),
        ),
      );
    }

    if (isPlannerCall &&
        !hasToolMessage &&
        availableTools.contains('web_search')) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractId': 'assistant_turn',
          'decision': <String, dynamic>{'nextAction': 'tool_call'},
          'toolCalls': <Map<String, dynamic>>[
            <String, dynamic>{
              'toolName': 'web_search',
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
          'contractId': 'assistant_turn',
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

class _PhaseOneProcessLeakLlm implements AssistantLlmProvider {
  int synthesisCallCount = 0;

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
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    final hasToolMessage = messages.any((item) => item['role'] == 'tool');

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(
          _intentPlanningEnvelope(
            primarySkill: 'weather',
            inferredMotive: '查询深圳实时天气',
            problemClass: 'realtime_info',
            mode: 'qa',
            normalizedQuery: '深圳天气怎么样',
          ),
        ),
      );
    }

    if (isPlannerCall &&
        !hasToolMessage &&
        availableTools.contains('web_search')) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractId': 'assistant_turn',
          'messageKind': 'progress',
          'phaseId': 'understanding',
          'actionCode': 'frame_problem',
          'reasonCode': 'align_goal',
          'reasonShort': '先查最新深圳天气，再整理成答。',
          'decision': <String, dynamic>{'nextAction': 'tool_call'},
          'toolCalls': <Map<String, dynamic>>[
            <String, dynamic>{
              'toolName': 'web_search',
              'arguments': <String, dynamic>{
                'query': '深圳天气 实时',
                'freshnessHoursMax': 6,
              },
            },
          ],
        }),
        toolCalls: const <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': '深圳天气 实时',
              'freshnessHoursMax': 6,
            },
          ),
        ],
      );
    }

    if (isPlannerCall && hasToolMessage) {
      onDelta?.call('我找到了深圳天气的权威信息来源，包括深圳市气象局官网和中央气象台的天气预报。');
      onDelta?.call('现在我已经获取了足够的天气信息，可以为你提供深圳的天气情况了。');
      return const AssistantModelOutput(
        text:
            '我找到了深圳天气的权威信息来源，包括深圳市气象局官网和中央气象台的天气预报。'
            '这些官方渠道的信息最可靠，能提供准确的实时天气数据。\n\n'
            '现在我已经获取了足够的天气信息，可以为你提供深圳的天气情况了。',
      );
    }

    if (isSynthesisCall) {
      synthesisCallCount += 1;
      return AssistantModelOutput(
        text: jsonEncode(<String, dynamic>{
          'contractId': 'assistant_turn',
          'decision': const <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'phaseId': 'answering',
          'actionCode': 'compose_answer',
          'reasonCode': 'evidence_ready',
          'userMarkdown':
              '深圳当前天气晴，约 25°C，湿度约 65%，东南风 3 级。'
              '如果你现在要出门，可以按偏热体感准备轻薄衣物。',
          'result': const <String, dynamic>{
            'text': '深圳当前天气晴，约 25°C，湿度约 65%，东南风 3 级。如果你现在要出门，可以按偏热体感准备轻薄衣物。',
            'summary': '深圳当前天气晴，约 25°C。',
            'interpretation': '基于检索结果整理出的最终天气回答',
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
            'notes': <String>['formal_synthesis_after_phase_one_process_text'],
          },
          'modelSelfScore': const <String, dynamic>{
            'score': 91,
            'reason': 'final_answer_after_retrieval',
          },
          'toolCalls': const <dynamic>[],
        }),
      );
    }

    return const AssistantModelOutput(
      text: '{"summary":"phase one process leak"}',
    );
  }
}

class _MultiSkillProblemClassLlm implements AssistantLlmProvider {
  Map<String, dynamic>? lastFusionTemplateVariables;

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
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(
          _intentPlanningEnvelope(
            primarySkill: 'weather',
            inferredMotive: '先看深圳天气，再结合深圳出游场景给建议',
            problemClass: 'complex_reasoning',
            mode: 'hybrid',
            secondarySkills: const <String>['fallback_general_search'],
            entityAnchors: const <String>['深圳'],
            queryTasks: const <Map<String, dynamic>>[
              <String, dynamic>{
                'id': 'fit_scenarios',
                'label': '出游场景',
                'dimension': 'fit_scenarios',
                'query': '深圳 轻松出游 场景 室内备选',
                'entityAnchors': <String>['深圳'],
              },
            ],
          ),
        ),
      );
    }

    if (isSynthesisCall) {
      if (_hasSubagentRuns(templateVariables)) {
        lastFusionTemplateVariables = templateVariables;
      }
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractId': 'assistant_turn',
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
          'contractId': 'assistant_turn',
          'decision': <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'userMarkdown': '## 深圳旅游建议\n\n- 白天可安排城市漫步。\n- 准备一个室内备选点以应对天气变化。',
          'result': <String, dynamic>{'text': '旅游建议以轻量户外活动为主，并准备室内备选。'},
        }),
      );
    }

    return AssistantModelOutput(
      text: jsonEncode(const <String, dynamic>{
        'contractId': 'assistant_turn',
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
            'goal': '结合深圳今天天气，为用户补充轻松步行的出游安排',
            'maxIterations': 4,
            'toolBudget': 2,
          },
          <String, dynamic>{
            'subagentId': 'travel_planner_2',
            'domainId': 'fallback_general_search',
            'problemClass': 'complex_reasoning',
            'mode': 'qa',
            'goal': '结合深圳今天天气，为用户补充室内备选与避雨安排',
            'maxIterations': 4,
            'toolBudget': 2,
          },
        ],
      }),
    );
  }
}

class _MultiSkillFusionAnchorRepairLlm implements AssistantLlmProvider {
  Map<String, dynamic>? lastFusionTemplateVariables;
  int fusionCallCount = 0;
  bool fusionRepairTriggered = false;

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
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    final joined = messages
        .map((item) => (item['content'] ?? '').toString())
        .join('\n');

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(
          _intentPlanningEnvelope(
            primarySkill: 'weather',
            inferredMotive: '先看深圳天气，再融合轻松出游建议',
            problemClass: 'complex_reasoning',
            mode: 'hybrid',
            secondarySkills: const <String>['fallback_general_search'],
            normalizedQuery: '深圳 天气 轻松旅游建议',
            entityAnchors: const <String>['深圳'],
            queryTasks: const <Map<String, dynamic>>[
              <String, dynamic>{
                'id': 'fit_scenarios',
                'label': '出游场景',
                'dimension': 'fit_scenarios',
                'query': '深圳 轻松出游 室内备选 步行路线',
                'entityAnchors': <String>['深圳'],
              },
            ],
          ),
        ),
      );
    }

    if (isSynthesisCall && _hasSubagentRuns(templateVariables)) {
      fusionCallCount += 1;
      lastFusionTemplateVariables = templateVariables;
      if (joined.contains('missing_topic_anchor') ||
          joined.contains('主题锚点') ||
          joined.contains('最终成答契约校验')) {
        fusionRepairTriggered = true;
        return AssistantModelOutput(
          text: jsonEncode(const <String, dynamic>{
            'contractId': 'assistant_turn',
            'decision': <String, dynamic>{'nextAction': 'answer'},
            'messageKind': 'answer',
            'userMarkdown':
                '## 深圳天气与轻松出游建议\n\n- 深圳今天天气适合出门。\n- 深圳出游优先轻松步行路线，并保留室内备选。',
            'result': <String, dynamic>{
              'text': '深圳今天天气适合出门，深圳轻松出游可优先步行路线并保留室内备选。',
              'summary': '深圳天气适合轻松出游',
            },
          }),
        );
      }
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractId': 'assistant_turn',
          'decision': <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'userMarkdown':
              '## 天气与轻松出游建议\n\n- 今天天气适合出门。\n- 建议优先安排轻松城市漫步，并保留室内备选。',
          'result': <String, dynamic>{
            'text': '今天天气适合出门，轻松出游可优先城市漫步并保留室内备选。',
            'summary': '天气适合轻松出游',
          },
        }),
      );
    }

    if (isSynthesisCall) {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractId': 'assistant_turn',
          'decision': <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'userMarkdown': '## 深圳天气初步结论\n\n- 深圳今天天气适合出门。',
          'result': <String, dynamic>{
            'text': '深圳今天天气适合出门。',
            'summary': '深圳天气适合出门',
          },
        }),
      );
    }

    if (!isPlannerCall) {
      return const AssistantModelOutput(text: '{"summary":"用户想融合天气和出游建议。"}');
    }

    final domainId = (templateVariables['domainId'] as String?)?.trim() ?? '';
    if (domainId == 'fallback_general_search') {
      return AssistantModelOutput(
        text: jsonEncode(const <String, dynamic>{
          'contractId': 'assistant_turn',
          'decision': <String, dynamic>{'nextAction': 'answer'},
          'messageKind': 'answer',
          'userMarkdown': '## 深圳轻松出游建议\n\n- 可优先城市漫步。\n- 同时保留室内备选点。',
          'result': <String, dynamic>{
            'text': '深圳轻松出游可优先城市漫步，并保留室内备选点。',
            'summary': '深圳轻松出游建议',
          },
        }),
      );
    }

    return AssistantModelOutput(
      text: jsonEncode(const <String, dynamic>{
        'contractId': 'assistant_turn',
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
            'goal': '结合深圳今天天气，为用户补充轻松步行的出游安排',
            'maxIterations': 4,
            'toolBudget': 2,
          },
          <String, dynamic>{
            'subagentId': 'travel_planner_2',
            'domainId': 'fallback_general_search',
            'problemClass': 'complex_reasoning',
            'mode': 'qa',
            'goal': '结合深圳今天天气，为用户补充室内备选与避雨安排',
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
    final isPlannerCall = templateId == 'planner.global_plan';
    final isSynthesisCall = _isFinalAnswerTemplate(templateId);
    final isIntentStage =
        templateId == 'planner.global_plan' && availableTools.isEmpty;
    final query = _latestUserQuery(messages);

    if (isIntentStage) {
      final isTripPlanning = query.contains('九寨沟');
      return AssistantModelOutput(
        text: jsonEncode(
          _intentPlanningEnvelope(
            primarySkill: 'fallback_general_search',
            inferredMotive: isTripPlanning ? '想补齐旅行路线与住宿备选' : '想确认一个更聚焦的观赏时间问题',
            problemClass: isTripPlanning ? 'complex_reasoning' : 'simple_qa',
            mode: 'qa',
          ),
        ),
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
          'contractId': 'assistant_turn',
          'phaseId': 'understanding',
          'actionCode': 'frame_problem',
          'reasonCode': 'align_goal',
          'reasonShort': '用户想了解$query，我需要搜索最新资料。',
          'decision': const <String, dynamic>{'nextAction': 'tool_call'},
          'toolCalls': <Map<String, dynamic>>[
            <String, dynamic>{
              'toolName': 'web_search',
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
        'contractId': 'assistant_turn',
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
    late LocalPhaseExecutionOwner loop;
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
      loop = LocalPhaseExecutionOwner(
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
        reason:
            'runtime 不再按 query 场景自动注入 authorityDomains，权威约束应来自 typed plan 或 tool metadata',
      );

      // ---- 当前 direct-owner 链路至少包含规划 + synthesis 两类模型调用 ----
      expect(
        mockLlm.totalCallCount,
        greaterThanOrEqualTo(2),
        reason: '至少要经过规划与 synthesis 两类模型调用',
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

      // ---- 用户旅程验证 ----
      final journey = response.runArtifacts?.journey;
      expect(journey, isNotNull);
      final journeyStages = journey!.stages
          .map((item) => item.stageId.name)
          .toSet();
      final hasToolStartTrace = traces.any(
        (item) => item.type == AssistantTraceEventType.toolStart,
      );

      expect(
        journey.entries.isNotEmpty || journey.stages.isNotEmpty,
        isTrue,
        reason: '应输出 canonical journey',
      );
      expect(
        journeyStages.contains('analyze'),
        isTrue,
        reason: '应覆盖 analyze 阶段',
      );
      expect(
        journeyStages.contains('search') ||
            journeyStages.contains('verify') ||
            hasToolStartTrace,
        isTrue,
        reason: '检索阶段应以 journey 或真实 toolStart 证据体现',
      );
      expect(journeyStages.contains('answer'), isTrue, reason: '应覆盖 answer 阶段');
      expect(
        journey.readiness.finalAnswerReady || journeyStages.contains('answer'),
        isTrue,
        reason: '应覆盖完成态阶段',
      );

      final searchUpdates = journey.entries
          .where(
            (item) =>
                item.stageId.name == 'search' || item.stageId.name == 'verify',
          )
          .toList(growable: false);
      if (searchUpdates.isNotEmpty) {
        final referencedUpdate = searchUpdates.firstWhere(
          (item) => item.references.isNotEmpty,
          orElse: () => searchUpdates.first,
        );
        expect(
          referencedUpdate.references,
          isNotEmpty,
          reason: '搜索阶段 sourceUpdate 应带引用',
        );
        expect(
          referencedUpdate.headline.contains('来源') ||
              referencedUpdate.headline.contains('资料') ||
              referencedUpdate.headline.contains('交叉看') ||
              referencedUpdate.detail.contains('来源') ||
              referencedUpdate.detail.contains('资料') ||
              referencedUpdate.detail.contains('交叉看'),
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

      for (final entry in journey.entries) {
        final allText = '${entry.headline} ${entry.detail}';
        expect(allText.contains('contractId'), isFalse);
        expect(allText.contains('AssistantTrace'), isFalse);
        expect(allText.contains('toolStart'), isFalse);
      }

      // ---- 最终答案应包含天气信息 ----
      final structured = response.structuredResponse;
      final mdText = response.displayMarkdown;
      final summaryText = response.displayPlainText;
      final runArtifacts =
          (structured['runArtifacts'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final artifacts = RunArtifacts.fromJson(runArtifacts);
      expect(
        (runArtifacts['machineEnvelope'] as String?)?.trim(),
        anyOf(isEmpty, equals(response.finalText.trim())),
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
        artifacts.evidenceLedger.any((entry) => entry.source.contains('气象局')),
        isTrue,
        reason: '证据账应保留 canonical source 展示名',
      );
      expect(
        artifacts.answerEvidenceBindings,
        isNotEmpty,
        reason: 'M3 应把答案引用绑定写入 runArtifacts',
      );
      expect(
        artifacts.answerEvidenceBindings.any(
          (binding) =>
              binding.source.contains('气象局') || binding.source.contains('天气网'),
        ),
        isTrue,
        reason: '答案引用绑定应沿用 canonical source',
      );
      expect(
        artifacts.slotState.slotValueOf('city')?.value,
        equals('深圳'),
        reason: 'M4 应把关键槽位状态写入 runArtifacts',
      );
      expect(
        artifacts.slotState.slotValueOf('city')?.evidenceIds,
        isNotEmpty,
        reason: 'M5 应将槽位与证据账绑定，避免 replay 只有值没有 grounding',
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
        journey.summary.trim().isNotEmpty ||
            journey.stages.any((item) => item.summary.trim().isNotEmpty) ||
            journey.entries.any(
              (item) =>
                  item.headline.trim().isNotEmpty ||
                  item.detail.trim().isNotEmpty,
            ),
        isTrue,
        reason: '应输出统一用户旅程摘要',
      );
      expect(
        journey.referenceSummary.count,
        greaterThanOrEqualTo(1),
        reason: '应输出可展开来源计数',
      );
      final blockRefs = journey.referenceSummary.references;
      expect(
        blockRefs.length,
        greaterThanOrEqualTo(1),
        reason: '天气过程区应保留至少一个筛选后的权威来源',
      );
      expect(
        blockRefs.any((item) => item.url.contains('weather.cma.cn')),
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
        structured.keys.any(
          (key) =>
              key.startsWith('uiProcessTimeline') && key != 'uiProcessTimeline',
        ),
        isFalse,
        reason: '过程时间线不应再输出额外兼容键',
      );
      expect(
        structured.containsKey('uiProcessTimeline'),
        isFalse,
        reason: 'legacy uiProcessTimeline 不应再作为新结果输出',
      );
      expect(
        structured.containsKey('uiPhaseTimelineV1'),
        isFalse,
        reason: 'legacy uiPhaseTimelineV1 不应再作为新结果输出',
      );
      expect(structured.containsKey('processSummary'), isFalse);
      expect(structured.containsKey('processReferenceCount'), isFalse);
      expect(structured.containsKey('uiProcessContentBlocks'), isFalse);
      final userMessages = <String>[
        ...journey.entries
            .map((item) => '${item.headline} ${item.detail}'.trim())
            .where((item) => item.isNotEmpty),
        if (journey.summary.trim().isNotEmpty) journey.summary.trim(),
        ...journey.stages
            .map((stage) => stage.summary.trim())
            .where((item) => item.isNotEmpty),
      ];
      expect(
        userMessages.any((item) => item.contains('深圳') && item.contains('天气')),
        isTrue,
        reason: '天气过程语言应带当前问题语义，而不是只显示系统状态',
      );
      expect(
        userMessages.any(
          (item) =>
              item.contains('先确认') ||
              item.contains('我在') ||
              item.contains('我先') ||
              item.contains('先把') ||
              item.contains('围绕你') ||
              item.contains('已经能直接确认') ||
              item.contains('最关心') ||
              item.contains('背景线索') ||
              item.contains('更容易看') ||
              item.contains('基本对齐'),
        ),
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
      AssistantJourneyEntry? rootIntentEntry;
      for (final entry
          in response.runArtifacts?.journey.entries ??
              const <AssistantJourneyEntry>[]) {
        if (entry.stageId.name == 'analyze' ||
            entry.provenance.actionCode.name == 'frameProblem') {
          rootIntentEntry = entry;
          break;
        }
      }
      final rootIntentSummary = (() {
        final headline = rootIntentEntry?.headline.trim() ?? '';
        if (headline.isNotEmpty) return headline;
        return rootIntentEntry?.detail.trim() ?? '';
      })();
      expect(
        rootIntentSummary.isNotEmpty,
        isTrue,
        reason: '首个阶段应先向用户解释为什么从这个方向开始处理，而不是只报内部状态',
      );
      expect(rootIntentEntry, isNotNull);
      expect(
        rootIntentEntry!.provenance.actionCode.name != 'unknown' ||
            rootIntentEntry.provenance.reasonCode.name.isNotEmpty ||
            rootIntentEntry.provenance.source.isNotEmpty,
        isTrue,
        reason: '首个阶段至少应保留一条 provenance 线索',
      );
      expect(rootIntentEntry.provenance.reasonCode.name, isNotEmpty);
      expect(rootIntentSummary, isNot(contains('我先帮你把')));
      expect(rootIntentSummary, isNot(contains('收一收')));
      expect(rootIntentSummary, isNot(contains('你更像是想知道')));
      expect(
        journey.entries.any((item) => item.references.isNotEmpty) ||
            hasToolStartTrace,
        isTrue,
        reason: '若过程区不再合成 references 事件，至少要保留真实工具执行证据',
      );
    });

    test('完成态保留自然成答，同时把三阶段快照写入 artifacts', () async {
      final normalizationLoop = LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: _ThreeSectionNormalizationWeatherLlm(),
          toolRegistry: AssistantToolRegistry()
            ..register(_FakeWeatherSearchTool()),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions_three_section_answer.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/memory_three_section_answer.json',
          ),
        ),
      );

      final response = await normalizationLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_three_section_answer',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳今天下不下雨，要不要带伞？'),
          ],
        ),
      );

      final markdown = response.displayMarkdown;
      final plainText = response.displayPlainText;
      final artifacts = response.runArtifacts;

      expect(markdown, contains('深圳天气'));
      expect(markdown, isNot(contains('## 深圳天气')));
      expect(markdown, isNot(contains('## 问题理解')));
      expect(markdown, isNot(contains('## 关键观点')));
      expect(markdown, isNot(contains('## 回答概要')));
      expect(markdown, contains('[来源1](https://weather.cma.cn/shenzhen'));
      expect(plainText, contains('深圳今天有雨'));
      expect(plainText, isNot(contains('问题理解')));
      expect(artifacts, isNotNull);
      expect(artifacts!.displayMarkdown, equals(markdown));
      expect(artifacts.displayPlainText, equals(plainText));
      expect(artifacts.answerEvidenceBindings, isNotEmpty);
      expect(artifacts.understandingSnapshot.intentSummary, isNotEmpty);
      expect(
        artifacts.understandingSnapshot.userFacingSummary,
        equals('你现在主要想先确认深圳今天的天气结论，再决定出门要不要带伞。我会先核对今天的降雨情况和最影响出门判断的天气变化。'),
      );
      expect(
        artifacts.understandingSnapshot.userFacingSummary,
        isNot(contains('Shenzhen tian qi')),
      );
      expect(artifacts.answerProcessing.keyFacts, isNotEmpty);
      expect(artifacts.retrievalProcessing.selectedKeyPoints, isNotEmpty);
      expect(
        artifacts.retrievalProcessing.processedDocumentCount,
        greaterThan(0),
      );
      expect(
        artifacts.retrievalProcessing.processedDocumentCount,
        greaterThanOrEqualTo(
          artifacts.retrievalProcessing.acceptedDocumentCount,
        ),
      );
      expect(artifacts.retrievalProcessing.acceptedDocumentCount, equals(1));
      expect(artifacts.retrievalProcessing.acceptedReferences, isNotEmpty);
      expect(
        artifacts.answerEvidenceBindings.first.url,
        contains('weather.cma.cn/shenzhen'),
      );
    });

    test('root-level typed intent graph 在完整链路中可直接恢复并续传', () async {
      final rootSearch = _FakeWeatherSearchTool();
      final rootToolRegistry = AssistantToolRegistry()..register(rootSearch);
      final rootLoop = LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: _RootLevelIntentWeatherPipelineLlm(),
          toolRegistry: rootToolRegistry,
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions_root_level_intent.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/memory_root_level_intent.json',
          ),
        ),
      );

      final response = await rootLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_root_level_intent',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );

      expect(response.degraded, isFalse);
      expect(rootSearch.executeCount, greaterThan(0));
      final structured = response.structuredResponse;
      final intentGraph =
          (structured['intentGraph'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      expect(intentGraph['primarySkill'], equals('weather'));
      expect(intentGraph['problemClass'], equals('realtime_info'));
      expect(intentGraph['freshnessHoursMax'], equals(1));
      expect(
        (intentGraph['authorityDomains'] as List?) ?? const <dynamic>[],
        contains('weather.cma.cn'),
      );
      final queryTasks =
          (intentGraph['queryTasks'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(queryTasks, hasLength(1));
      expect(queryTasks.first['id'], equals('latest_signal'));
      expect(queryTasks.first['query'], contains('深圳'));
    });

    test('上一轮 slotState 与 domainPolicyBundle 会续转到下一轮', () async {
      final carryLlm = _WeatherPipelineLlm();
      final carrySearch = _FakeWeatherSearchTool();
      final carryLoop = LocalPhaseExecutionOwner(
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

      final secondLoop = LocalPhaseExecutionOwner(
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
      final replayLoop = LocalPhaseExecutionOwner(
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
        'contractId',
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
        'contractId',
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
        'contractId',
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

      final journey = secondResponse.runArtifacts?.journey;
      final narrativeEvents =
          (journey?.entries ?? const <AssistantJourneyEntry>[])
              .where(
                (item) =>
                    item.headline.trim().isNotEmpty ||
                    item.detail.trim().isNotEmpty,
              )
              .toList(growable: false);
      expect(narrativeEvents, isNotEmpty);
      for (final event in narrativeEvents) {
        final summary = event.headline.trim().isNotEmpty
            ? event.headline.trim()
            : event.detail.trim();
        expect(summary, isNotEmpty, reason: '旅程条目应提供短理由');
        expect(event.provenance.actionCode.name, isNotEmpty);
        expect(
          event.provenance.reasonCode.name,
          isNotEmpty,
          reason: '旅程条目应提供 reasonCode',
        );
        expect(event.provenance.source, isNotEmpty, reason: '旅程条目应提供 source');
        expect(summary, isNot(contains('我先帮你把')));
        expect(summary, isNot(contains('收一收')));
        expect(summary, isNot(contains('你更像是想知道')));
        expect(summary, isNot(contains('我先替你')));
      }

      expect(firstResponse.displayMarkdown, contains('九寨沟'));
      expect(firstResponse.displayMarkdown, isNot(contains('先给你当前最稳的部分')));
      expect(secondResponse.displayMarkdown, contains('土拨鼠'));
      expect(secondResponse.displayMarkdown, isNot(contains('先给你当前最稳的部分')));
      expect(secondResponse.displayMarkdown, isNot(contains('contractId')));
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
      final usageLoop = LocalPhaseExecutionOwner(
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
          (response.structuredResponse['uiUsageStats'] as Map?)
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
      final fallbackLoop = LocalPhaseExecutionOwner(
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
      final markdown = response.displayMarkdown.trim();
      expect(markdown, contains('这次生成答案失败'));
      expect(response.degraded, isTrue);
      expect(markdown, isNot(contains('<tool_call>')));
      expect(markdown, isNot(contains('contractId')));
      final journey = response.runArtifacts?.journey;
      expect(
        (journey?.summary.trim().isNotEmpty ?? false) ||
            (journey?.stages.any((item) => item.summary.trim().isNotEmpty) ??
                false) ||
            (journey?.entries.any(
                  (item) =>
                      item.headline.trim().isNotEmpty ||
                      item.detail.trim().isNotEmpty,
                ) ??
                false),
        isTrue,
        reason: 'fallback 也应给出统一用户旅程摘要',
      );
      expect(journey?.referenceSummary.count, equals(0));
      expect(
        journey?.entries.any(
          (item) =>
              item.headline.trim().isNotEmpty || item.detail.trim().isNotEmpty,
        ),
        isTrue,
      );
      expect(structured.containsKey('uiProcessContentBlocks'), isFalse);
    });

    test('原始 XML tool_call 不会泄漏到最终天气回答', () async {
      final xmlLoop = LocalPhaseExecutionOwner(
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

      final markdown = response.displayMarkdown.trim();
      expect(markdown, isNot(contains('<tool_call>')));
      expect(markdown, contains('这次生成答案失败'));
      expect(response.degraded, isTrue);
      expect(markdown, isNot(contains('contractId')));
    });

    test('synthesis 非 answer 输出不会被静默改写成 answer', () async {
      final invalidSynthesisLoop = LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: _InvalidSynthesisNextActionLlm(),
          toolRegistry: AssistantToolRegistry()
            ..register(_FakeWeatherSearchTool()),
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

      final markdown = response.displayMarkdown.trim();
      final plainText = response.displayPlainText.trim();

      expect(response.degraded, isTrue);
      expect(markdown, contains('这次生成答案失败'));
      expect(plainText, contains('这次生成答案失败'));
    });

    test('phase one 检索后若只产出过程性自由文本，必须继续 formal synthesis 成答', () async {
      final llm = _PhaseOneProcessLeakLlm();
      final loop = LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: llm,
          toolRegistry: AssistantToolRegistry()
            ..register(_FakeWeatherSearchTool()),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions_phase_one_process_leak.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/memory_phase_one_process_leak.json',
          ),
        ),
      );

      final response = await loop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_phase_one_process_leak',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: 'Shenzhen tian qi'),
          ],
        ),
      );

      final plainText = response.displayPlainText.trim();
      final markdown = response.displayMarkdown.trim();
      final diagnostics =
          (response.structuredResponse['phaseOneRoutingDiagnostics'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};

      expect(llm.synthesisCallCount, greaterThan(0));
      expect(diagnostics['route'], equals('formal_synthesis'));
      expect(diagnostics['phaseOneExecutionSignalsPresent'], isTrue);
      expect(
        plainText,
        contains('深圳当前天气晴'),
        reason: '检索后的最终展示必须是整理后的回答，而不是过程说明',
      );
      expect(markdown, contains('深圳当前天气晴'));
      expect(plainText, isNot(contains('我找到了深圳天气的权威信息来源')));
      expect(plainText, isNot(contains('现在我已经获取了足够的天气信息')));
    });

    test('fallback 会按问题类型自适应执行壳子，而非固定 simple_qa', () async {
      final adaptiveSearch = _FakeWeatherSearchTool();
      final adaptiveToolRegistry = AssistantToolRegistry()
        ..register(adaptiveSearch);
      final adaptiveLoop = LocalPhaseExecutionOwner(
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
        reason:
            'runtime 不再根据 fallback 壳子自行扩写 queryTasks，应仅消费模型/typed plan 已提供的检索任务',
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
      final multiLlm = _MultiSkillProblemClassLlm();
      final multiLoop = LocalPhaseExecutionOwner(
        ReactRuntime(llmProvider: multiLlm, toolRegistry: multiToolRegistry),
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
        subagentPlan.every(
          (item) => item['problemClass'] == 'complex_reasoning',
        ),
        isTrue,
        reason: '子任务计划必须显式携带自己的 problemClass',
      );

      final skillRuns =
          (structured['skillRuns'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      expect(skillRuns.length, greaterThanOrEqualTo(2));

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
      expect(travelShell['maxIterations'], equals(2));
      expect(travelShell['toolBudget'], equals(2));
      expect(travelShell['variantBudget'], equals(1));
      expect(travelShell['reflectionBudget'], equals(1));

      final fusionVars = multiLlm.lastFusionTemplateVariables;
      expect(fusionVars, isNotNull);
      expect(fusionVars!['userGoal'], contains('深圳'));
      expect(fusionVars['entityAnchors'], contains('深圳'));
      expect((fusionVars['intentGraphJson'] as String?) ?? '', contains('深圳'));
      expect(
        (fusionVars['queryTasksJson'] as String?) ?? '',
        contains('fit_scenarios'),
      );
      expect((fusionVars['queryTasksJson'] as String?) ?? '', contains('深圳'));
    });

    test('multi skill fusion 丢失主题锚点时会走统一 repair 收口', () async {
      final multiToolRegistry = AssistantToolRegistry()
        ..register(_FakeWeatherSearchTool());
      final fusionRepairLlm = _MultiSkillFusionAnchorRepairLlm();
      final multiLoop = LocalPhaseExecutionOwner(
        ReactRuntime(
          llmProvider: fusionRepairLlm,
          toolRegistry: multiToolRegistry,
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/sessions_multiskill_anchor_repair.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/memory_multiskill_anchor_repair.json',
          ),
        ),
      );

      final response = await multiLoop.run(
        const AssistantRunRequest(
          sessionId: 'pipeline_multiskill_anchor_repair',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(
              role: 'user',
              content: '深圳今天天气如何，顺便给我一个轻松点的旅游建议',
            ),
          ],
        ),
      );

      final markdown = response.displayMarkdown.trim();

      expect(fusionRepairLlm.fusionCallCount, greaterThanOrEqualTo(2));
      expect(
        fusionRepairLlm.fusionRepairTriggered,
        isTrue,
        reason: 'fusion 若把主题锚点答丢，必须走统一 repair，而不是静默放过',
      );
      expect(markdown, contains('深圳'));
      expect(response.displayPlainText, contains('深圳'));
      expect(response.degraded, isFalse);
      final fusionVars = fusionRepairLlm.lastFusionTemplateVariables;
      expect(fusionVars, isNotNull);
      expect(fusionVars!['entityAnchors'], contains('深圳'));
    });
  });
}
