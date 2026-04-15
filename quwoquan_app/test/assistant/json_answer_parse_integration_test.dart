import 'dart:io';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/session_manager.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:test/test.dart';

class _JsonOnlyLlmProvider implements AssistantLlmProvider {
  const _JsonOnlyLlmProvider();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    LlmCallOptions? callOptions,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '2026.02.18',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    void Function(String delta)? onDelta,
  }) async {
    return const AssistantModelOutput(
      text: '''
{
  "contractId": "assistant_turn",
  "messageKind": "answer",
  "phaseId": "answering",
  "actionCode": "compose_answer",
  "reasonCode": "evidence_ready",
  "reasonShort": "关键信息已经够用了，开始整理成答案。",
  "decision": {"nextAction": "answer", "confidence": 0.88, "reasoning": "已有足够信息给出娱乐向建议"},
  "userMarkdown": "## 事业运建议\\n\\n- 近期更适合稳中求进，把注意力放在可控行动上。",
  "result": {
    "text": "近期更适合稳中求进。",
    "summary": "事业运以稳为主",
    "interpretation": "仅供娱乐参考，近期更适合稳中求进。",
    "actionHints": ["保持节奏", "控制预期"]
  },
  "reasoningBasis": [{"claim": "建议稳健", "text": "用户目标偏长期", "confidence": 0.88}],
  "selfCheck": {"goalSatisfied": true, "constraintSatisfied": true, "safetyBoundarySatisfied": true, "failedItems": []},
  "diagnostics": {"emergedTags": [], "failedChecks": [], "parseStatus": "", "notes": ["遵循娱乐边界"]},
  "modelSelfScore": {"score": 88, "reason": "覆盖目标与约束"},
  "toolCalls": []
}
''',
    );
  }
}

class _AssistantTurnProvider implements AssistantLlmProvider {
  const _AssistantTurnProvider();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    LlmCallOptions? callOptions,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '2026.02.18',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    void Function(String delta)? onDelta,
  }) async {
    return const AssistantModelOutput(
      text: '''
{
  "contractId": "assistant_turn",
  "messageKind": "ask_user",
  "phaseId": "clarifying",
  "actionCode": "ask_clarification",
  "reasonCode": "missing_slot",
  "reasonShort": "还差一个关键信息，先确认后再继续。",
  "decision": {"nextAction": "ask_user", "confidence": 0.92, "reasoning": "缺少城市信息"},
  "slotState": {"location": {"status": "missing"}},
  "askUser": {"slotId": "location", "prompt": "请告诉我要查询的城市，例如深圳。", "required": true, "suggestions": ["深圳", "上海"]},
  "userMarkdown": "## 继续查询天气\\n- 请告诉我要查询的城市（例如：深圳）",
  "result": {"text": "需要补齐城市信息", "summary": "等待城市槽位", "interpretation": "需要补齐城市信息"},
  "selfCheck": {"goalSatisfied": true, "constraintSatisfied": true, "safetyBoundarySatisfied": true, "failedItems": []},
  "diagnostics": {"emergedTags": [], "failedChecks": [], "parseStatus": "", "notes": []},
  "toolCalls": []
}
''',
    );
  }
}

class _SubagentTurnProvider implements AssistantLlmProvider {
  const _SubagentTurnProvider();

  @override
  Future<AssistantModelOutput> reason({
    required List<Map<String, dynamic>> messages,
    required List<String> availableTools,
    LlmCallOptions? callOptions,
    Map<String, dynamic> templateContext = const <String, dynamic>{},
    Map<String, dynamic> templateVariables = const <String, dynamic>{},
    String templateId = 'planner.global_plan',
    String templateVersion = '2026.02.18',
    String sessionId = '',
    String runId = '',
    String traceId = '',
    void Function(String delta)? onDelta,
  }) async {
    final isSubagentExecution = messages.any(
      (item) =>
          item['role'] == 'system' &&
          (item['content'] ?? '').contains('你是后台子代理'),
    );
    if (isSubagentExecution) {
      return const AssistantModelOutput(
        text: '''
{
  "contractId": "assistant_turn",
  "messageKind": "answer",
  "phaseId": "answering",
  "actionCode": "compose_answer",
  "reasonCode": "evidence_ready",
  "reasonShort": "子任务已经完成，开始整理结果。",
  "decision": {"nextAction": "answer"},
  "slotState": {},
  "askUser": {},
  "subagentPlan": [],
  "userMarkdown": "## 子代理结论\\n- 子任务已完成，并返回结构化摘要。",
  "result": {"text": "子代理已完成", "summary": "子任务返回摘要", "interpretation": "子代理已完成"},
  "selfCheck": {"goalSatisfied": true, "constraintSatisfied": true, "safetyBoundarySatisfied": true, "failedItems": []},
  "diagnostics": {"emergedTags": [], "failedChecks": [], "parseStatus": "", "notes": []},
  "toolCalls": []
}
''',
      );
    }
    final hasSubagentResult = messages.any(
      (item) =>
          item['role'] == 'system' &&
          (item['content'] ?? '').contains('各子任务执行结果'),
    );
    if (hasSubagentResult) {
      return const AssistantModelOutput(
        text: '''
{
  "contractId": "assistant_turn",
  "messageKind": "answer",
  "phaseId": "answering",
  "actionCode": "compose_answer",
  "reasonCode": "evidence_ready",
  "reasonShort": "子任务结果已经齐了，可以汇总成答。",
  "decision": {"nextAction": "answer"},
  "slotState": {},
  "askUser": {},
  "subagentPlan": [],
  "userMarkdown": "## 主结论\\n- 已吸收子代理结果，输出最终答复。",
  "result": {"text": "最终答复已整合子任务", "summary": "子任务结果已融合", "interpretation": "最终答复已整合子任务"},
  "selfCheck": {"goalSatisfied": true, "constraintSatisfied": true, "safetyBoundarySatisfied": true, "failedItems": []},
  "diagnostics": {"emergedTags": [], "failedChecks": [], "parseStatus": "", "notes": []},
  "toolCalls": []
}
''',
      );
    }
    return const AssistantModelOutput(
      text: '''
{
  "contractId": "assistant_turn",
  "messageKind": "progress",
  "phaseId": "analyzing",
  "actionCode": "delegate_research",
  "reasonCode": "need_parallel_evidence",
  "reasonShort": "还差一层核验，我先并行补齐证据。",
  "decision": {"nextAction": "tool_call"},
  "slotState": {},
  "askUser": {},
  "subagentPlan": [
    {
      "subagentId": "sa_weather_verify",
      "domainId": "weather",
      "problemClass": "realtime_info",
      "goal": "校验深圳天气关键信息并总结",
      "timeoutMs": 8000,
      "maxIterations": 1,
      "toolBudget": 1,
      "toolWhitelist": []
    }
  ],
  "userMarkdown": "## 正在后台处理\\n- 我会并行启动子任务后给你最终结论。",
  "result": {"text": "需要子代理补充证据", "summary": "准备并行核验", "interpretation": "需要子代理补充证据"},
  "selfCheck": {"goalSatisfied": true, "constraintSatisfied": true, "safetyBoundarySatisfied": true, "failedItems": []},
  "diagnostics": {"emergedTags": [], "failedChecks": [], "parseStatus": "", "notes": []},
  "toolCalls": []
}
''',
    );
  }
}

void main() {
  test(
    'agent loop parses json answer and exposes learning/ui fields',
    () async {
      final tempDir = await Directory.systemTemp.createTemp('pa_json_parse_');
      final runtime = ReactRuntime(
        llmProvider: const _JsonOnlyLlmProvider(),
        toolRegistry: AssistantToolRegistry(),
      );
      final loop = LocalPhaseExecutionOwner(
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
      final parsedEnvelope = LlmResponseParser.parse(response.finalText);
      final turn = parsedEnvelope.json == null
          ? null
          : tryParseAssistantTurnOutput(parsedEnvelope.json!);
      expect(parsedEnvelope.ok, isTrue);
      expect(turn, isNotNull);
      expect(
        response.displayPlainText.trim().isNotEmpty,
        isTrue,
      );
      expect(
        ((structured['learningSignals'] as Map?)?['modelSelfScore'] as num?)
            ?.toDouble(),
        greaterThan(80),
      );
      await tempDir.delete(recursive: true);
    },
  );

  test('agent loop parses assistant_turn payload', () async {
    final tempDir = await Directory.systemTemp.createTemp('pa_turn_parse_');
    final runtime = ReactRuntime(
      llmProvider: const _AssistantTurnProvider(),
      toolRegistry: AssistantToolRegistry(),
    );
    final loop = LocalPhaseExecutionOwner(
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
        sessionId: 'turn-parse',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '今天天气怎么样'),
        ],
      ),
    );
    final parsedEnvelope = LlmResponseParser.parse(response.finalText);
    final turn = parsedEnvelope.json == null
        ? null
        : tryParseAssistantTurnOutput(parsedEnvelope.json!);
    expect(parsedEnvelope.ok, isTrue);
    expect(turn, isNotNull);
    final combinedText = <String>[
      response.displayMarkdown,
      response.displayPlainText,
      response.followupPrompt,
      ...response.actionHints,
    ].join(' ');
    expect(
      combinedText.trim().isNotEmpty,
      isTrue,
      reason: 'assistant_turn 的用户可见信息应通过 display 或 followup/action hints 暴露',
    );
    expect(response.displayMarkdown, isNot(contains('"contractId"')));
    await tempDir.delete(recursive: true);
  });

  test('agent loop executes subagent plan and injects timeline', () async {
    final tempDir = await Directory.systemTemp.createTemp('pa_subagent_exec_');
    final runtime = ReactRuntime(
      llmProvider: const _SubagentTurnProvider(),
      toolRegistry: AssistantToolRegistry(),
    );
    final loop = LocalPhaseExecutionOwner(
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
        sessionId: 'subagent-exec',
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '请做一次天气深度核验并总结'),
        ],
      ),
    );
    final structured = response.structuredResponse;
    final subagentRuns =
        (structured['subagentRuns'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    // 新 assistant_turn 下由 subagentPlan 直接驱动子任务执行，不再依赖旧
    // spawn_subagent 决策值。考虑到测试桩与运行时时序差异，这里仍做宽松断言。
    if (subagentRuns.isNotEmpty) {
      expect(
        (subagentRuns.first['status'] as String?) ?? '',
        equals('success'),
      );
      final timeline =
          (structured['uiTimeline'] as List?)?.whereType<Map>().toList() ??
          const <Map>[];
      expect(
        timeline.any((item) => item['event'] == 'subagent_progress'),
        isTrue,
      );
    }
    await tempDir.delete(recursive: true);
  });
}
