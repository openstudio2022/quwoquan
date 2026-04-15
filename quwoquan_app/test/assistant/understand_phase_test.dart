import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/understand_phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_runtime.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('UnderstandPhase', () {
    test('planner 输入会剥离上一轮 runArtifacts 噪音字段', () {
      final phase = UnderstandPhase();
      const request = AssistantRunRequest(
        messages: <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: 'Shenzhen tian qi'),
        ],
        contextScopeHint: <String, dynamic>{
          'runArtifacts': <String, dynamic>{
            'displayMarkdown': '旧答案',
            'journey': <String, dynamic>{'summary': '旧过程'},
          },
          'previousRunArtifacts': <String, dynamic>{'displayPlainText': '旧纯文本'},
          'displayMarkdown': '旧 markdown',
          'displayPlainText': '旧 plain text',
          'journey': <String, dynamic>{'summary': '旧 journey'},
          'previousUnderstandingSnapshot': <String, dynamic>{
            'intentSummary': '旧理解',
          },
        },
      );

      final envelope = phase.inputSafeContextEnvelope(null, request, null, null);
      final scopeHint = (envelope['contextScopeHint'] as Map)
          .cast<String, dynamic>();

      expect(scopeHint.containsKey('runArtifacts'), isFalse);
      expect(scopeHint.containsKey('previousRunArtifacts'), isFalse);
      expect(scopeHint.containsKey('displayMarkdown'), isFalse);
      expect(scopeHint.containsKey('displayPlainText'), isFalse);
      expect(scopeHint.containsKey('journey'), isFalse);
      expect(
        scopeHint['previousUnderstandingSnapshot'],
        isA<Map<String, dynamic>>(),
      );
    });

    test('planner 仅保留最近 user turns，并注入最新优先的 recent rounds', () async {
      final provider = _PlannerRecentRoundsCaptureProvider();
      final runtime = ReactRuntime(
        llmProvider: provider,
        toolRegistry: AssistantToolRegistry(),
      );
      final bootstrapContext = AssistantBootstrapContext(
        recentDialogueRoundsLimit: 2,
        recentDialogueRounds: const <Map<String, dynamic>>[
          <String, dynamic>{
            'turnId': 'turn_3',
            'userQuery': '第三问',
            'assistantSummary': '第三答摘要',
          },
          <String, dynamic>{
            'turnId': 'turn_2',
            'userQuery': '第二问',
            'assistantSummary': '第二答摘要',
          },
        ],
      );
      final output = await UnderstandPhase(runtime: runtime).run(
        PhaseInput(
          request: const AssistantRunRequest(
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: '第一问'),
              AssistantRunMessage(role: 'assistant', content: '第一答'),
              AssistantRunMessage(role: 'user', content: '第二问'),
              AssistantRunMessage(role: 'assistant', content: '第二答'),
              AssistantRunMessage(role: 'user', content: '第三问'),
              AssistantRunMessage(role: 'assistant', content: '第三答'),
              AssistantRunMessage(role: 'user', content: '第四问'),
            ],
            contextScopeHint: <String, dynamic>{
              'recentDialogueRoundsLimit': 2,
            },
          ),
          state: AgentExecutionState(bootstrapContext: bootstrapContext),
          runId: 'run_recent_rounds_planner',
          traceId: 'trace_recent_rounds_planner',
        ),
      );

      expect(output.state, isNotNull);
      final plannerMessages = provider.capturedMessages;
      expect(plannerMessages, isNotEmpty);
      expect(plannerMessages.first['role'], 'system');
      final conversationMessages = plannerMessages
          .where(
            (item) =>
                item['role'] == 'user' || item['role'] == 'assistant',
          )
          .map((item) => '${item['role']}:${item['content']}')
          .toList(growable: false);
      // 新话题/未知延续时 planner 消息会压到「仅当前用户句」，避免历史轮次污染规划；
      // 近期轮次仍通过 `recentDialogueRounds` 变量注入（见下方断言）。
      expect(
        conversationMessages,
        equals(const <String>[
          'user:第四问',
        ]),
      );

      final recentRounds = (jsonDecode(
            provider.capturedTemplateVariables['recentDialogueRounds']
                    as String? ??
                '[]',
          ) as List)
          .cast<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false);
      expect(recentRounds, hasLength(2));
      expect(recentRounds.first['turnId'], 'turn_3');
      expect(recentRounds.first['userQuery'], '第三问');
      expect(recentRounds.last['turnId'], 'turn_2');
      expect(
        provider.capturedTemplateVariables['recentDialogueRoundsLimit'],
        2,
      );
    });

    test('天气问题会把默认城市写入 query 与理解解释', () async {
      final runtime = ReactRuntime(
        llmProvider: _WeatherPlannerProvider(expectedQuery: '2026-04-09 天气 预报'),
        toolRegistry: AssistantToolRegistry(),
      );
      final output = await UnderstandPhase(runtime: runtime).run(
        const PhaseInput(
          request: AssistantRunRequest(
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: '明天天气怎么样？'),
            ],
            contextScopeHint: <String, dynamic>{
              'referenceNowIso': '2026-04-08T10:30:00.000',
              'timezone': 'Asia/Shanghai',
              'availableGeoContext': <String, dynamic>{
                'countryCode': 'CN',
                'countryLabel': '中国',
                'regionLabel': '广东',
                'cityLabel': '深圳',
                'timezone': 'Asia/Shanghai',
                'source': 'device_gps',
              },
            },
          ),
          state: AgentExecutionState(),
          runId: 'run_weather_geo_default',
          traceId: 'trace_weather_geo_default',
        ),
      );

      final state = output.state!;
      expect(state.intentGraph?.resolvedGeoScope.cityLabel, '深圳');
      expect(state.intentGraph?.resolvedGeoScope.defaultApplied, isTrue);
      expect(
        state.intentGraph?.queryTasks.first.query,
        contains('深圳'),
      );
      expect(state.intentGraph?.clarificationNeeded, isFalse);
      expect(
        state.understandingSnapshot.resolutionItems.any(
          (item) =>
              item.kind == 'geo_default' &&
              item.detail.contains('深圳') &&
              item.visibleInUnderstanding,
        ),
        isTrue,
      );
    });

    test('天气问题缺少 geography 上下文时会要求补充地点', () async {
      final runtime = ReactRuntime(
        llmProvider: _WeatherPlannerProvider(expectedQuery: '2026-04-09 天气 预报'),
        toolRegistry: AssistantToolRegistry(),
      );
      final output = await UnderstandPhase(runtime: runtime).run(
        const PhaseInput(
          request: AssistantRunRequest(
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: '明天天气怎么样？'),
            ],
            contextScopeHint: <String, dynamic>{
              'referenceNowIso': '2026-04-08T10:30:00.000',
            },
          ),
          state: AgentExecutionState(),
          runId: 'run_weather_geo_clarification',
          traceId: 'trace_weather_geo_clarification',
        ),
      );

      final state = output.state!;
      expect(state.intentGraph?.resolvedGeoScope.resolvedText, isEmpty);
      expect(state.intentGraph?.clarificationNeeded, isTrue);
      expect(
        state.intentGraph?.contextSlots['geoClarificationReason'],
        'missing_geo_context_for_city',
      );
      expect(
        state.understandingSnapshot.resolutionItems.any(
          (item) =>
              item.kind == 'clarification_needed' &&
              item.title.contains('地理范围'),
        ),
        isTrue,
      );
    });
  });
}

class _WeatherPlannerProvider implements AssistantLlmProvider {
  _WeatherPlannerProvider({required this.expectedQuery});

  final String expectedQuery;

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
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'messageKind': 'progress',
        'phaseId': 'understanding',
        'actionCode': 'frame_problem',
        'reasonCode': 'align_goal',
        'decision': const <String, dynamic>{'nextAction': 'tool_call'},
        'understandingSnapshot': const <String, dynamic>{
          'userFacingSummary': '我先把天气问题落到具体日期再检索。',
        },
        'intentGraph': <String, dynamic>{
          'userGoal': '获取天气预报',
          'problemShape': 'single_skill',
          'primarySkill': 'weather',
          'problemClass': 'realtime_info',
          'secondarySkills': <String>[],
          'queryNormalization': <String, dynamic>{
            'normalizedQuery': expectedQuery,
          },
          'queryTasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'id': 'weather_forecast',
              'query': expectedQuery,
              'dimension': 'forecast',
              'why': '先锁定日期，再检索天气结论。',
            },
          ],
          'contextSlots': <String, dynamic>{},
          'globalConstraints': <String, dynamic>{'mode': 'qa'},
          'clarificationNeeded': false,
          'requiresExternalEvidence': true,
          'answerShape': 'decision_ready',
          'freshnessNeed': 'latest',
          'freshnessHoursMax': 6,
        },
        'selfCheck': const <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
      }),
    );
  }
}

class _PlannerRecentRoundsCaptureProvider implements AssistantLlmProvider {
  List<Map<String, dynamic>> capturedMessages = const <Map<String, dynamic>>[];
  Map<String, dynamic> capturedTemplateVariables = const <String, dynamic>{};

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
    capturedMessages = messages
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
    capturedTemplateVariables = Map<String, dynamic>.from(templateVariables);
    return AssistantModelOutput(
      text: jsonEncode(<String, dynamic>{
        'contractId': 'assistant_turn',
        'messageKind': 'progress',
        'phaseId': 'understanding',
        'actionCode': 'frame_problem',
        'reasonCode': 'align_goal',
        'decision': const <String, dynamic>{'nextAction': 'tool_call'},
        'understandingSnapshot': const <String, dynamic>{
          'userFacingSummary': '我先沿用最近一轮上下文继续理解。',
        },
        'intentGraph': const <String, dynamic>{
          'userGoal': '沿着上一轮上下文继续追问',
          'problemShape': 'single_skill',
          'primarySkill': 'general_search',
          'problemClass': 'realtime_info',
          'secondarySkills': <String>[],
          'contextSlots': <String, dynamic>{},
          'globalConstraints': <String, dynamic>{'mode': 'qa'},
          'clarificationNeeded': false,
          'requiresExternalEvidence': true,
          'answerShape': 'decision_ready',
          'freshnessNeed': 'latest',
          'freshnessHoursMax': 6,
        },
        'selfCheck': const <String, dynamic>{
          'goalSatisfied': true,
          'constraintSatisfied': true,
          'safetyBoundarySatisfied': true,
          'failedItems': <String>[],
        },
      }),
    );
  }
}
