import 'dart:convert';

import 'package:test/test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_metadata_registry.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

class _SequenceProvider implements AssistantLlmProvider {
  int _callCount = 0;
  final List<List<Map<String, dynamic>>> capturedMessages =
      <List<Map<String, dynamic>>>[];

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
    capturedMessages.add(
      messages
          .map(
            (m) => <String, dynamic>{
              'role': m['role'],
              'content': m['content'],
              'tool_call_id': m['tool_call_id'],
              'tool_calls': m['tool_calls'],
            },
          )
          .toList(growable: false),
    );
    _callCount += 1;
    if (_callCount == 1) {
      return const AssistantModelOutput(
        text: '先调用工具',
        toolCalls: <AssistantToolCall>[
          AssistantToolCall(name: 'web_search', arguments: <String, dynamic>{}),
        ],
      );
    }
    return const AssistantModelOutput(text: '最终回答');
  }
}

class _FakeWebSearchTool implements AssistantTool {
  int executeCount = 0;

  @override
  String get name => 'web_search';

  @override
  String get description => 'fake web search';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    executeCount += 1;
    return const AssistantToolResult(
      success: true,
      message: '检索结果：ok',
      data: <String, dynamic>{
        'provider': 'duckduckgo',
        'summary': 'ok',
        'references': <Map<String, dynamic>>[],
      },
    );
  }
}

class _FastConvergenceProvider implements AssistantLlmProvider {
  int _callCount = 0;

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
    _callCount += 1;
    if (_callCount == 1) {
      return const AssistantModelOutput(
        text: '先调用工具',
        toolCalls: <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': '深圳住宿',
              'queryVariants': <String>['深圳酒店 位置 交通'],
            },
          ),
        ],
      );
    }
    return const AssistantModelOutput(text: '最终回答');
  }
}

class _CoverageLowSearchTool implements AssistantTool {
  @override
  String get name => 'web_search';

  @override
  String get description => 'fake web search';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    return const AssistantToolResult(
      success: true,
      message: '检索结果：ok',
      data: <String, dynamic>{
        'provider': 'duckduckgo',
        'summary': 'ok',
        'coverage': 0.2,
        'confidence': 0.9,
        'qualityScore': 0.9,
        'queryCount': 2,
        'referenceCount': 4,
        'references': <Map<String, dynamic>>[
          {'title': 'A', 'url': 'https://a.example.com'},
          {'title': 'B', 'url': 'https://b.example.com'},
          {'title': 'C', 'url': 'https://c.example.com'},
          {'title': 'D', 'url': 'https://d.example.com'},
        ],
      },
    );
  }
}

class _ArgumentCaptureSearchTool implements AssistantTool {
  int executeCount = 0;
  Map<String, dynamic> lastArguments = const <String, dynamic>{};

  @override
  String get name => 'web_search';

  @override
  String get description => 'capture web search args';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    executeCount += 1;
    lastArguments = Map<String, dynamic>.from(arguments);
    return const AssistantToolResult(
      success: true,
      message: '检索结果：ok',
      data: <String, dynamic>{
        'provider': 'duckduckgo',
        'summary': 'ok',
        'coverage': 0.9,
        'confidence': 0.9,
        'qualityScore': 0.9,
        'queryCount': 1,
        'referenceCount': 2,
        'references': <Map<String, dynamic>>[
          {'title': 'A', 'url': 'https://a.example.com'},
          {'title': 'B', 'url': 'https://b.example.com'},
        ],
      },
    );
  }
}

class _ArgumentCaptureUnifiedSearchTool implements AssistantTool {
  int executeCount = 0;
  Map<String, dynamic> lastArguments = const <String, dynamic>{};

  @override
  String get name => 'search';

  @override
  String get description => 'capture unified search args';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    executeCount += 1;
    lastArguments = Map<String, dynamic>.from(arguments);
    return const AssistantToolResult(
      success: true,
      message: '统一检索结果：ok',
      data: <String, dynamic>{
        'summary': 'ok',
        'sections': <Map<String, dynamic>>[],
        'hits': <Map<String, dynamic>>[],
        'references': <Map<String, dynamic>>[],
        'qualityScore': 0.9,
        'queryCount': 1,
        'referenceCount': 0,
      },
    );
  }
}

class _NoToolPlanProvider implements AssistantLlmProvider {
  int callCount = 0;

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
    callCount += 1;
    if (callCount == 1) {
      return const AssistantModelOutput(text: '我先想一下检索方向');
    }
    return const AssistantModelOutput(text: '最终回答');
  }
}

class _ForceAnswerOnlyProvider implements AssistantLlmProvider {
  int callCount = 0;
  final List<List<String>> availableToolsByCall = <List<String>>[];
  final List<List<Map<String, dynamic>>> capturedMessages =
      <List<Map<String, dynamic>>>[];

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
    callCount += 1;
    availableToolsByCall.add(List<String>.of(availableTools));
    capturedMessages.add(
      messages
          .map(
            (item) => <String, dynamic>{
              'role': item['role'],
              'content': item['content'],
            },
          )
          .toList(growable: false),
    );
    if (callCount == 1) {
      return const AssistantModelOutput(
        text: '先调用工具',
        toolCalls: <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{
              'query': '深圳住宿',
              'queryVariants': <String>['深圳酒店 位置 交通'],
            },
          ),
        ],
      );
    }
    if (availableTools.isNotEmpty) {
      return const AssistantModelOutput(
        text: '继续补充资料',
        toolCalls: <AssistantToolCall>[
          AssistantToolCall(
            name: 'web_search',
            arguments: <String, dynamic>{'query': '深圳住宿 继续补充'},
          ),
        ],
      );
    }
    return const AssistantModelOutput(text: '最终回答');
  }
}

class _ThinkingDeltaProvider implements AssistantLlmProvider {
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
    onDelta?.call('{"partial":"json"}');
    return AssistantModelOutput(
      text: jsonEncode(
        const AssistantTurnOutput(
          contractId: kAssistantTurnCurrentContractId,
          messageKind: AssistantMessageKind.progress,
          userMarkdown: '',
          phaseId: PlannerPhaseId.understanding,
          reasonShort: '我先确认你关心的是深圳当前天气。',
        ).toJson(),
      ),
    );
  }
}

void main() {
  test(
    'react runtime emits structured tool_observation on validation error',
    () async {
      final provider = _SequenceProvider();
      final metadata = ToolMetadataRegistry();
      await metadata.ensureLoaded();
      final registry = AssistantToolRegistry(metadataRegistry: metadata);
      final fakeTool = _FakeWebSearchTool();
      registry.register(fakeTool);
      final runtime = ReactRuntime(
        llmProvider: provider,
        toolRegistry: registry,
      );

      await runtime.run(
        messages: <Map<String, dynamic>>[
          const <String, dynamic>{'role': 'user', 'content': '查一下天气'},
        ],
        maxIterations: 2,
        goal: '查一下天气',
      );

      expect(fakeTool.executeCount, equals(0));
      expect(provider.capturedMessages.length, greaterThanOrEqualTo(2));
      final secondCallMessages = provider.capturedMessages[1];
      final toolMsg = secondCallMessages.lastWhere(
        (item) => item['role'] == 'tool',
        orElse: () => const <String, dynamic>{'role': '', 'content': ''},
      );
      expect(toolMsg['role'], equals('tool'));
      expect((toolMsg['tool_call_id'] as String?)?.isNotEmpty, isTrue);
      final observation =
          jsonDecode((toolMsg['content'] as String?) ?? '{}')
              as Map<String, dynamic>;
      expect(observation['toolName'], equals('web_search'));
      expect(observation['ok'], isFalse);
      expect(observation['status'], equals('retrieval_invalid_args'));
      expect(observation['errorClass'], equals('invalid_args'));
      expect(observation['retryable'], isFalse);
    },
  );

  test(
    'fast convergence result no longer emits contradictory replan',
    () async {
      final provider = _FastConvergenceProvider();
      final metadata = ToolMetadataRegistry();
      await metadata.ensureLoaded();
      final registry = AssistantToolRegistry(metadataRegistry: metadata);
      registry.register(_CoverageLowSearchTool());
      final runtime = ReactRuntime(
        llmProvider: provider,
        toolRegistry: registry,
      );

      final result = await runtime.run(
        messages: <Map<String, dynamic>>[
          const <String, dynamic>{'role': 'user', 'content': '查深圳住宿建议'},
        ],
        maxIterations: 2,
        goal: '查深圳住宿建议',
        templateVariables: const <String, dynamic>{
          'problemClass': 'realtime_info',
        },
      );

      final assessment = result.traces.lastWhere(
        (trace) =>
            trace.type == AssistantTraceEventType.toolResult &&
            trace.data?['isAssessment'] == true,
        orElse: () => throw StateError('missing assessment trace'),
      );
      expect(assessment.data?['shouldContinueLoop'], isFalse);
      expect(
        result.traces.any(
          (trace) => trace.type == AssistantTraceEventType.replanTriggered,
        ),
        isFalse,
        reason: '快速收敛问题在 assessment 已判定足够时，不应再发出 replanTriggered',
      );
    },
  );

  test('assessment 判定足够后下一轮切为 answer-only，避免继续工具循环', () async {
    final provider = _ForceAnswerOnlyProvider();
    final metadata = ToolMetadataRegistry();
    await metadata.ensureLoaded();
    final registry = AssistantToolRegistry(metadataRegistry: metadata);
    registry.register(_CoverageLowSearchTool());
    final runtime = ReactRuntime(
      llmProvider: provider,
      toolRegistry: registry,
      toolMetadataRegistry: metadata,
    );

    final result = await runtime.run(
      messages: <Map<String, dynamic>>[
        const <String, dynamic>{'role': 'user', 'content': '查深圳住宿建议'},
      ],
      maxIterations: 3,
      goal: '查深圳住宿建议',
      templateVariables: const <String, dynamic>{
        'problemClass': 'realtime_info',
      },
    );

    expect(result.finalText, equals('最终回答'));
    expect(provider.callCount, equals(2));
    expect(provider.availableToolsByCall.first, contains('web_search'));
    expect(
      provider.availableToolsByCall[1],
      isEmpty,
      reason: 'assessment 已判定证据足够时，下一轮不应再暴露工具',
    );
    expect(
      result.traces
          .where((trace) => trace.type == AssistantTraceEventType.toolStart)
          .length,
      equals(1),
      reason: '不应继续进入第二轮工具调用',
    );
    expect(
      provider.capturedMessages.last.any(
        (item) =>
            item['role'] == 'system' &&
            (item['content'] as String? ?? '').contains('不要继续调用任何工具'),
      ),
      isTrue,
      reason: 'runtime 应显式注入 answer-only 收敛提示',
    );
  });

  test('runtime 不会把裸 queryVariants 自动改写为 typed queryTasks', () async {
    final provider = _FastConvergenceProvider();
    final metadata = ToolMetadataRegistry();
    await metadata.ensureLoaded();
    final registry = AssistantToolRegistry(metadataRegistry: metadata);
    final captureTool = _ArgumentCaptureSearchTool();
    registry.register(captureTool);
    final runtime = ReactRuntime(
      llmProvider: provider,
      toolRegistry: registry,
      toolMetadataRegistry: metadata,
    );

    await runtime.run(
      messages: <Map<String, dynamic>>[
        const <String, dynamic>{'role': 'user', 'content': '查深圳住宿建议'},
      ],
      maxIterations: 2,
      goal: '查深圳住宿建议',
      templateVariables: const <String, dynamic>{
        'problemClass': 'complex_reasoning',
      },
    );

    expect(captureTool.executeCount, equals(1));
    expect(
      captureTool.lastArguments.containsKey('queryTasks'),
      isFalse,
      reason:
          '未显式提供 typed queryTasks 时，runtime 不应从裸 query/queryVariants 自动合成检索任务',
    );
    expect(
      captureTool.lastArguments['queryVariants'],
      equals(<String>['深圳酒店 位置 交通']),
      reason: '模型原始 queryVariants 应原样保留给检索工具处理',
    );
  });

  test('runtime 会优先下发 phase 侧 precomputed typed queryTasks', () async {
    final provider = _FastConvergenceProvider();
    final metadata = ToolMetadataRegistry();
    await metadata.ensureLoaded();
    final registry = AssistantToolRegistry(metadataRegistry: metadata);
    final captureTool = _ArgumentCaptureSearchTool();
    registry.register(captureTool);
    final runtime = ReactRuntime(
      llmProvider: provider,
      toolRegistry: registry,
      toolMetadataRegistry: metadata,
    );

    await runtime.run(
      messages: <Map<String, dynamic>>[
        const <String, dynamic>{'role': 'user', 'content': '查深圳住宿建议'},
      ],
      maxIterations: 2,
      goal: '查深圳住宿建议',
      templateVariables: const <String, dynamic>{
        'problemClass': 'complex_reasoning',
        'skillExecutionShell': <String, dynamic>{
          'variantBudget': 2,
          'preComputedQueryTasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'fit_scenarios',
              'dimension': 'fit_scenarios',
              'label': '适用场景',
              'query': '深圳住宿 通勤 景点 夜生活 适合',
            },
          ],
        },
      },
    );

    expect(captureTool.executeCount, equals(1));
    final queryTasks =
        (captureTool.lastArguments['queryTasks'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    expect(queryTasks, hasLength(1));
    expect(queryTasks.first['id'], equals('fit_scenarios'));
    expect(queryTasks.first['query'], contains('通勤'));
    expect(
      captureTool.lastArguments['queryVariants'],
      equals(<String>['深圳酒店 位置 交通']),
      reason: '即便 phase 侧提供了 typed queryTasks，runtime 也不应篡改模型原始 queryVariants',
    );
  });

  test('phase 侧已有 precomputed queryTasks 时，runtime 不会空手跳过首轮检索', () async {
    final provider = _NoToolPlanProvider();
    final metadata = ToolMetadataRegistry();
    await metadata.ensureLoaded();
    final registry = AssistantToolRegistry(metadataRegistry: metadata);
    final captureTool = _ArgumentCaptureSearchTool();
    registry.register(captureTool);
    final runtime = ReactRuntime(
      llmProvider: provider,
      toolRegistry: registry,
      toolMetadataRegistry: metadata,
    );

    final result = await runtime.run(
      messages: <Map<String, dynamic>>[
        const <String, dynamic>{'role': 'user', 'content': '查深圳住宿建议'},
      ],
      maxIterations: 2,
      goal: '查深圳住宿建议',
      templateVariables: const <String, dynamic>{
        'problemClass': 'complex_reasoning',
        'skillExecutionShell': <String, dynamic>{
          'preComputedQueryTasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'fit_scenarios',
              'dimension': 'fit_scenarios',
              'label': '适用场景',
              'query': '深圳住宿 通勤 景点 夜生活 适合',
            },
          ],
        },
      },
    );

    expect(captureTool.executeCount, equals(1));
    expect(provider.callCount, equals(2), reason: '自动补检索后应继续进入下一轮收敛');
    expect(result.finalText, equals('最终回答'));
    expect(captureTool.lastArguments['query'], equals('深圳住宿 通勤 景点 夜生活 适合'));
    expect(
      result.traces.any(
        (trace) =>
            trace.type == AssistantTraceEventType.searchQueryGenerated &&
            ((trace.data?['query'] as String?)?.contains('深圳住宿') ?? false),
      ),
      isTrue,
      reason: '自动注入检索应产生 searchQueryGenerated 轨迹',
    );
  });

  test('phase 侧已有 precomputed queryTasks 时优先自动注入 search', () async {
    final provider = _NoToolPlanProvider();
    final metadata = ToolMetadataRegistry();
    await metadata.ensureLoaded();
    final registry = AssistantToolRegistry(metadataRegistry: metadata);
    final captureTool = _ArgumentCaptureUnifiedSearchTool();
    registry.register(captureTool);
    final runtime = ReactRuntime(
      llmProvider: provider,
      toolRegistry: registry,
      toolMetadataRegistry: metadata,
    );

    await runtime.run(
      messages: <Map<String, dynamic>>[
        const <String, dynamic>{'role': 'user', 'content': '查深圳住宿建议'},
      ],
      maxIterations: 2,
      goal: '查深圳住宿建议',
      templateVariables: const <String, dynamic>{
        'problemClass': 'complex_reasoning',
        'skillExecutionShell': <String, dynamic>{
          'preComputedQueryTasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'fit_scenarios',
              'dimension': 'fit_scenarios',
              'label': '适用场景',
              'query': '深圳住宿 通勤 景点 夜生活 适合',
            },
          ],
        },
      },
    );

    expect(captureTool.executeCount, equals(1));
    expect(captureTool.lastArguments['query'], equals('深圳住宿 通勤 景点 夜生活 适合'));
    expect(captureTool.lastArguments['mode'], equals('result'));
  });

  test('provider 已产生 delta 时，runtime 仍会上报提取后的 thinkingProgress', () async {
    final metadata = ToolMetadataRegistry();
    await metadata.ensureLoaded();
    final registry = AssistantToolRegistry(metadataRegistry: metadata);
    final runtime = ReactRuntime(
      llmProvider: _ThinkingDeltaProvider(),
      toolRegistry: registry,
      toolMetadataRegistry: metadata,
    );

    final result = await runtime.run(
      messages: <Map<String, dynamic>>[
        const <String, dynamic>{'role': 'user', 'content': '深圳天气怎么样'},
      ],
      maxIterations: 1,
      goal: '深圳天气怎么样',
      onDelta: (_) {},
    );

    expect(
      result.traces.any(
        (trace) =>
            trace.type == AssistantTraceEventType.thinkingProgress &&
            trace.message.contains('深圳当前天气'),
      ),
      isTrue,
      reason: 'JSON token 已经触发 onDelta 时，也不能吞掉提取后的用户语言思考摘要',
    );
  });
}
