import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/conversation/orchestration/agent_loop.dart'
    as legacy_agent;
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/memory/assistant_memory_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_agent_loop.dart';
import 'package:quwoquan_app/assistant/orchestration/assistant_orchestration_runtime.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/tools/assistant_tool_runtime.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

Map<String, dynamic> _intentEnvelope({
  required String primarySkill,
  required String inferredMotive,
  required String problemClass,
  String normalizedQuery = '',
}) {
  return <String, dynamic>{
    'contractVersion': 'assistant_turn',
    'messageKind': 'progress',
    'phaseId': 'understanding',
    'actionCode': 'frame_problem',
    'reasonCode': 'align_goal',
    'reasonShort': '先聚焦用户目标，再决定如何获取资料。',
    'decision': <String, dynamic>{
      'nextAction': 'answer',
      'confidence': 0.82,
      'reasoning': '先识别领域与问题类型',
    },
    'userMarkdown': '我先聚焦你的问题主线，再开始处理。',
    'result': <String, dynamic>{
      'text': '',
      'summary': '进入理解阶段',
      'interpretation': inferredMotive,
    },
    'intentGraph': <String, dynamic>{
      'userGoal': inferredMotive,
      'problemShape': 'single_skill',
      'primarySkill': primarySkill,
      'problemClass': problemClass,
      'inferredMotive': inferredMotive,
      'secondarySkills': const <String>[],
      'queryNormalization': normalizedQuery.isNotEmpty
          ? <String, dynamic>{'normalizedQuery': normalizedQuery}
          : const <String, dynamic>{},
      'queryTasks': const <Map<String, dynamic>>[],
      'contextSlots': const <String, dynamic>{},
      'globalConstraints': const <String, dynamic>{'mode': 'qa'},
      'clarificationNeeded': false,
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
      'notes': <String>[],
    },
  };
}

class _DeterministicWeatherLlm implements AssistantLlmProvider {
  int _planCallCount = 0;

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

    if (!isPlannerCall && !isSynthesisCall) {
      return const AssistantModelOutput(text: '{"summary":"用户在查询深圳天气"}');
    }

    if (isIntentStage) {
      return AssistantModelOutput(
        text: jsonEncode(
          _intentEnvelope(
            primarySkill: 'weather',
            inferredMotive: '查询深圳实时天气',
            problemClass: 'realtime_info',
            normalizedQuery: '深圳天气怎么样',
          ),
        ),
      );
    }

    if (isPlannerCall) {
      _planCallCount += 1;
      if (_planCallCount == 1 && availableTools.contains('web_search')) {
        onDelta?.call('我先核对深圳今天的最新天气。');
        return AssistantModelOutput(
          text: jsonEncode(<String, dynamic>{
            'contractVersion': 'assistant_turn',
            'decision': <String, dynamic>{'nextAction': 'tool_call'},
            'toolCalls': const <Map<String, dynamic>>[
              <String, dynamic>{
                'toolName': 'web_search',
                'arguments': <String, dynamic>{
                  'query': '深圳天气实时数据',
                  'freshnessHoursMax': 6,
                  'provider': 'baidu',
                },
              },
            ],
            'reasonShort': '需要先查最新天气实况。',
          }),
          toolCalls: const <AssistantToolCall>[
            AssistantToolCall(
              name: 'web_search',
              arguments: <String, dynamic>{
                'query': '深圳天气实时数据',
                'freshnessHoursMax': 6,
                'provider': 'baidu',
              },
            ),
          ],
        );
      }
    }

    onDelta?.call('资料已经齐了，我来整理成最终答案。');
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractVersion': 'assistant_turn',
        'decision': <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '## 深圳天气\n\n今天深圳天气晴朗，温度约25°C，适合轻装出门。',
        'result': const <String, dynamic>{
          'text': '今天深圳天气晴朗，温度约25°C。',
          'interpretation': '深圳当前天气概况',
        },
        'evidence': const <Map<String, dynamic>>[
          <String, dynamic>{
            'claim': '温度约25°C',
            'source': 'web_search',
            'confidence': 'high',
          },
        ],
        'reasoningBasis': const <Map<String, dynamic>>[],
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
          'notes': <String>['资料已经齐了，我来整理成最终答案。'],
        },
        'modelSelfScore': const <String, dynamic>{
          'score': 94,
          'reason': '准确回答天气问题',
        },
        'toolCalls': const <dynamic>[],
      }),
    );
  }
}

class _FakeWeatherSearchTool implements AssistantTool {
  @override
  String get name => 'web_search';

  @override
  String get description => '网络搜索';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    return const AssistantToolResult(
      success: true,
      message: '搜索完成',
      data: <String, dynamic>{
        'provider': 'duckduckgo',
        'summary': '深圳今天天气晴朗，温度25°C',
        'totalReferences': 1,
        'references': <Map<String, dynamic>>[
          <String, dynamic>{
            'title': '深圳天气预报 - 中国气象局',
            'url': 'https://weather.cma.cn/shenzhen',
            'source': '中国气象局',
            'snippet': '深圳今天晴，温度25°C。',
          },
        ],
      },
    );
  }
}

bool _containsInternalLeak(String text) {
  final normalized = text.trim();
  if (normalized.isEmpty) return false;
  return normalized.contains('assistant_turn') ||
      normalized.contains('contractVersion') ||
      normalized.contains('toolCalls') ||
      normalized.contains('queryTasks') ||
      normalized.contains('runArtifacts') ||
      normalized.contains('machineEnvelope') ||
      normalized.contains('<tool_call>');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('AssistantAgentLoop 与 legacy loop 对齐，并且用户展示层无 internal leak', () async {
    final tempDir = await Directory.systemTemp.createTemp(
      'assistant_agent_loop_parity_',
    );
    addTearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    AssistantToolRegistry buildRegistry() {
      return AssistantToolRegistry()..register(_FakeWeatherSearchTool());
    }

    legacy_agent.PersonalAssistantAgentLoop buildLegacyLoop(String suffix) {
      return legacy_agent.PersonalAssistantAgentLoop(
        ReactRuntime(
          llmProvider: _DeterministicWeatherLlm(),
          toolRegistry: buildRegistry(),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/legacy_${suffix}_sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/legacy_${suffix}_memory.json',
          ),
        ),
      );
    }

    AssistantAgentLoop buildNewLoop(String suffix) {
      return AssistantAgentLoop(
        runtime: ReactRuntime(
          llmProvider: _DeterministicWeatherLlm(),
          toolRegistry: buildRegistry(),
        ),
        sessionManager: AssistantSessionManager(
          storagePath: '${tempDir.path}/new_${suffix}_sessions.json',
        ),
        memoryRepository: AssistantMemoryRepository(
          ObjectBoxVectorStore(
            storagePath: '${tempDir.path}/new_${suffix}_memory.json',
          ),
        ),
      );
    }

    const request = AssistantRunRequest(
      sessionId: 'parity_guard',
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
      ],
      contextScopeHint: <String, dynamic>{
        'problemClass': 'realtime_info',
        'requiresExternalEvidence': true,
      },
    );

    final legacyResponse = await buildLegacyLoop('a').run(request);
    final phasedLoop = buildNewLoop('a');
    final phasedResponse = await phasedLoop.run(request);

    expect(legacyResponse.degraded, isFalse);
    expect(phasedResponse.degraded, isFalse);
    expect(phasedResponse.displayMarkdown, legacyResponse.displayMarkdown);
    expect(phasedResponse.displayPlainText, legacyResponse.displayPlainText);

    final phasedStructured = phasedResponse.structuredResponse;
    expect(phasedStructured.containsKey('qualityMetrics'), isTrue);
    expect(phasedStructured.containsKey('uiAnswer'), isTrue);
    expect(phasedResponse.runArtifacts, isNotNull);
    expect(phasedResponse.runArtifacts!.processJournal, isNotEmpty);
    expect(phasedLoop.executionState.synthesisDraft, isNotNull);
    expect(phasedLoop.executionState.previousRunArtifacts, isNotNull);
    expect(phasedLoop.executionState.evidenceLedger, isNotEmpty);
    expect(phasedLoop.executionState.answerEvidenceBindings, isNotEmpty);
    expect(phasedLoop.executionState.evidenceEvaluation?.entries, isNotEmpty);
    expect(phasedLoop.executionState.synthesisReadiness?.ready, isTrue);
    expect(
      phasedLoop.executionState.conversationStateDecision?.finalAnswerReady,
      isTrue,
    );
    expect(
      phasedLoop.executionState.slotState?.toJson(),
      phasedLoop.executionState.previousRunArtifacts?.slotState.toJson(),
    );
    expect(phasedLoop.executionState.domainPolicyBundle, isNotNull);
    expect(
      phasedResponse.traces.any(
        (trace) => trace.type == AssistantTraceEventType.toolResult,
      ),
      isTrue,
    );

    final quality =
        (phasedStructured['qualityMetrics'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    expect(quality.containsKey('decisionParseSuccess'), isTrue);
    expect(quality.containsKey('heuristicFallbackUsed'), isTrue);
    expect(quality.containsKey('evidenceSufficient'), isTrue);

    expect(_containsInternalLeak(phasedResponse.displayMarkdown), isFalse);
    expect(_containsInternalLeak(phasedResponse.displayPlainText), isFalse);
  });
}
