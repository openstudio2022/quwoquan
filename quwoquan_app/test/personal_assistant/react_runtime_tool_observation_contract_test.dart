import 'dart:convert';

import 'package:test/test.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/tools/metadata/tool_metadata_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

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

void main() {
  test('react runtime emits structured tool_observation on validation error', () async {
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
        jsonDecode((toolMsg['content'] as String?) ?? '{}') as Map<String, dynamic>;
    expect(observation['toolName'], equals('web_search'));
    expect(observation['ok'], isFalse);
    expect(observation['status'], equals('retrieval_invalid_args'));
    expect(observation['errorClass'], equals('invalid_args'));
    expect(observation['retryable'], isFalse);
  });
}
