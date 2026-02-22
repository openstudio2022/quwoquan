import 'dart:io';

import 'package:quwoquan_app/personal_assistant/engine/agent_loop.dart';
import 'package:quwoquan_app/personal_assistant/engine/llm_provider.dart';
import 'package:quwoquan_app/personal_assistant/engine/react_runtime.dart';
import 'package:quwoquan_app/personal_assistant/engine/session_manager.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/memory/objectbox_store.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:test/test.dart';

class _JsonOnlyLlmProvider implements AssistantLlmProvider {
  const _JsonOnlyLlmProvider();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, String>> messages,
    required List<String> availableTools,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '2026.02.18',
    String sessionId = '',
    String runId = '',
    String traceId = '',
  }) async {
    return const AssistantModelOutput(
      text: '''
{
  "result": {
    "interpretation": "仅供娱乐参考，近期更适合稳中求进。",
    "actionHints": ["保持节奏", "控制预期"],
    "uncertainty": "运势解读具有主观不确定性",
    "disclaimer": "仅供娱乐参考，不构成专业建议",
    "positiveGuidance": "把注意力放在可控行动上"
  },
  "reasoningBasis": [{"claim": "建议稳健", "support": "用户目标偏长期"}],
  "selfCheck": {"goalSatisfied": true, "constraintSatisfied": true, "safetyBoundarySatisfied": true, "failedItems": []},
  "diagnostics": {"whyThisAnswer": "遵循娱乐边界", "riskFlags": [], "missingInfo": [], "needMoreInfo": false},
  "modelSelfScore": {"score": 88, "reason": "覆盖目标与约束", "improvementHints": ["增加个性化细节"]},
  "toolCalls": []
}
''',
    );
  }
}

void main() {
  test('agent loop parses json answer and exposes learning/ui fields', () async {
    final tempDir = await Directory.systemTemp.createTemp('pa_json_parse_');
    final runtime = ReactRuntime(
      llmProvider: const _JsonOnlyLlmProvider(),
      toolRegistry: AssistantToolRegistry(),
    );
    final loop = PersonalAssistantAgentLoop(
      runtime,
      sessionManager: AssistantSessionManager(
        storagePath: '${tempDir.path}/sessions.json',
      ),
      memoryRepository: AssistantMemoryRepository(
        ObjectBoxVectorStore(storagePath: '${tempDir.path}/memory.json'),
      ),
    );
    final response = await loop.run(
      const AssistantRunRequest(
        sessionId: 'json-parse',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '帮我看看近期事业运'),
        ],
      ),
    );
    final structured = response.structuredResponse;
    final answerPayload = (structured['answerPayload'] as Map?)?.cast<String, dynamic>();
    expect(answerPayload, isNotNull);
    expect(answerPayload?['parseStatus'], equals('json_parsed'));
    expect(
      ((structured['uiAnswer'] as Map?)?['summaryText'] as String?)?.isNotEmpty,
      isTrue,
    );
    expect(
      ((structured['learningSignals'] as Map?)?['modelSelfScore'] as num?)?.toDouble(),
      greaterThan(80),
    );
    await tempDir.delete(recursive: true);
  });
}

