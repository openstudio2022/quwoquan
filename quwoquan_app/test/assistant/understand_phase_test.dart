import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/context_continuity_policy.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/system_context_envelope.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
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

      final envelope = phase.inputSafeContextEnvelope(
        null,
        request,
        null,
        null,
      );
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
            contextScopeHint: <String, dynamic>{'recentDialogueRoundsLimit': 2},
          ),
          state: AgentExecutionState(bootstrapContext: bootstrapContext),
          runId: 'run_recent_rounds_planner',
          traceId: 'trace_recent_rounds_planner',
        ),
      );

      expect(output.state, isNotNull);
      final plannerMessages = provider.capturedMessages;
      expect(plannerMessages, isNotEmpty);
      final conversationMessages = plannerMessages
          .where(
            (item) => item['role'] == 'user' || item['role'] == 'assistant',
          )
          .map((item) => '${item['role']}:${item['content']}')
          .toList(growable: false);
      // 新话题/未知延续时 planner 消息会压到「仅当前用户句」，避免记录轮次污染规划；
      // 近期轮次仍通过 `recentDialogueRounds` 变量注入（见下方断言）。
      expect(conversationMessages, equals(const <String>['user:第四问']));

      final recentRounds =
          (jsonDecode(
                    provider.capturedTemplateVariables['recentDialogueRounds']
                            as String? ??
                        '[]',
                  )
                  as List)
              .cast<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false);
      expect(recentRounds, hasLength(2));
      expect(recentRounds.first['turnId'], 'turn_3');
      expect(recentRounds.first['userQuery'], '第三问');
      expect(recentRounds.last['turnId'], 'turn_2');
      expect(
        provider.capturedTemplateVariables.containsKey(
          'recentDialogueRoundsLimit',
        ),
        isFalse,
      );
    });

    test(
      'planner continuity 注入上一轮 typed understanding 与 system context',
      () async {
        final provider = _PlannerRecentRoundsCaptureProvider();
        final runtime = ReactRuntime(
          llmProvider: provider,
          toolRegistry: AssistantToolRegistry(),
        );
        final bootstrapContext = AssistantBootstrapContext(
          systemContextEnvelope: const SystemContextEnvelope(
            time: SystemTimeContext(
              referenceNowIso: '2026-04-24T10:00:00+08:00',
              timezone: 'Asia/Shanghai',
              locale: 'zh_CN',
            ),
            device: DeviceSummary(os: 'ios', model: 'iPhone 17'),
            location: SystemLocationContext(
              countryCode: 'CN',
              countryName: '中国',
              adminAreaLevel1: '广东省',
              adminAreaLevel2: '深圳市',
              timezone: 'Asia/Shanghai',
              granularity: LocationGranularity.city,
            ),
          ),
          contextContinuityPolicy: const ContextContinuityPolicy(
            continuityMode: ContextContinuityMode.explicitFollowUp,
            explicitContinuation: true,
            allowHistorySummary: true,
          ),
          previousUnderstandingResult: const UnderstandingResult(
            intents: <IntentNode>[
              IntentNode(
                intentId: 'intent_prev',
                intentType: 'travel.compare',
                goal: '比较九寨沟路线',
              ),
            ],
            dialogueTransitionDecision: DialogueTransitionDecision(
              nextTurnMode: NextTurnMode.continueExecution,
            ),
          ),
          previousTaskGraph: const TaskGraph(
            tasks: <TaskNode>[
              TaskNode(
                taskId: 'task_prev',
                intentId: 'intent_prev',
                toolName: 'app_search',
              ),
            ],
          ),
        );
        final output = await UnderstandPhase(runtime: runtime).run(
          PhaseInput(
            request: const AssistantRunRequest(
              messages: <AssistantRunMessage>[
                AssistantRunMessage(role: 'user', content: '那如果我只有4天呢？'),
              ],
            ),
            state: AgentExecutionState(bootstrapContext: bootstrapContext),
            runId: 'run_typed_continuity',
            traceId: 'trace_typed_continuity',
          ),
        );

        final dialogueContinuity =
            (jsonDecode(
                      provider.capturedTemplateVariables['dialogueContinuity']
                              as String? ??
                          '{}',
                    )
                    as Map)
                .cast<String, dynamic>();
        final sharedContext =
            (jsonDecode(
                      provider.capturedTemplateVariables['sharedContext']
                              as String? ??
                          '{}',
                    )
                    as Map)
                .cast<String, dynamic>();

        expect(
          (dialogueContinuity['previousUnderstandingResult'] as Map)['intents'],
          isNotEmpty,
        );
        expect(
          ((dialogueContinuity['previousTaskGraph'] as Map)['tasks'] as List),
          isNotEmpty,
        );
        expect(
          (sharedContext['systemContextEnvelope'] as Map)['time'],
          isA<Map<String, dynamic>>(),
        );
        expect(
          output.state!.systemContextEnvelope.time.timezone,
          'Asia/Shanghai',
        );
        expect(
          output.state!.systemContextEnvelope.location.adminAreaLevel2,
          '深圳市',
        );
      },
    );

    test('天气问题不会把设备地点直接写回业务 geo 语义', () async {
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
      expect(state.understandingResult.intents, hasLength(1));
      expect(state.understandingResult.intents.single.goal, '获取天气预报');
      expect(
        state.understandingResult.dialogueTransitionDecision.nextTurnMode,
        NextTurnMode.askUser,
      );
      expect(state.taskGraph.tasks, isNotEmpty);
      expect(state.taskGraph.tasks.first.toolName, isNotEmpty);
      expect(
        state.orchestratorState.interactionDirective.kind,
        InteractionDirectiveKind.clarify,
      );
      expect(
        state.taskGraph.tasks.first.toolArgs.toJson()['query'],
        '2026-04-09 天气 预报',
      );
      expect(state.understandingSnapshot.resolutionItems, isEmpty);
      expect(
        state.understandingSnapshot.retrievalDesignNarrative,
        contains('天气'),
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
      expect(state.understandingResult.intents, hasLength(1));
      expect(
        state.understandingResult.dialogueTransitionDecision.needsClarification,
        isTrue,
      );
      expect(
        state.orchestratorState.interactionDirective.kind,
        InteractionDirectiveKind.clarify,
      );
      expect(state.understandingSnapshot.resolutionItems, isEmpty);
    });

    test('iPad A股寒武纪样例会在理解阶段自然纠错并保留双意图', () async {
      final runtime = ReactRuntime(
        llmProvider: _EntityResolutionPlannerProvider(),
        toolRegistry: AssistantToolRegistry(),
      );
      final output = await UnderstandPhase(runtime: runtime).run(
        const PhaseInput(
          request: AssistantRunRequest(
            messages: <AssistantRunMessage>[
              AssistantRunMessage(
                role: 'user',
                content:
                    'Jin tian zao pan wei sha a gu da Zhang, Han wu ji shi he you zi ma',
              ),
              AssistantRunMessage(
                role: 'assistant',
                content: '我先按 A 股早盘上涨原因回答，但没有把 Han wu ji 的实体说清。',
              ),
              AssistantRunMessage(
                role: 'user',
                content: 'wo shuo de shi Han wu ji, you chan xin pian gong si',
              ),
              AssistantRunMessage(
                role: 'assistant',
                content: '你说的是寒武纪（688256），不是韩武纪或其他公司。',
              ),
              AssistantRunMessage(
                role: 'user',
                content:
                    'Jin tian a gu Wei Shen me da Zhang? Han wu ji xian zai gou mai shi he ma? gei chu ni de Jian yi',
              ),
            ],
          ),
          state: AgentExecutionState(),
          runId: 'run_ipad_stock_entity_resolution',
          traceId: 'trace_ipad_stock_entity_resolution',
        ),
      );

      final state = output.state!;
      final summary = state.understandingSnapshot.userFacingSummary;
      expect(summary, contains('A 股'));
      expect(summary, contains('寒武纪'));
      expect(summary, contains('Han wu ji'));
      expect(summary, contains('688256'));
      expect(summary, contains('不再沿用'));
      expect(
        state.understandingSnapshot.retrievalDesignNarrative,
        allOf(contains('A 股'), contains('寒武纪'), contains('估值'), contains('风险')),
      );

      final resolutions = state.understandingSnapshot.resolutionItems;
      expect(resolutions, hasLength(1));
      expect(resolutions.single.kind, 'entity_resolution');
      expect(resolutions.single.originalValue, 'Han wu ji');
      expect(resolutions.single.resolvedValue, '寒武纪（688256）');
      expect(resolutions.single.visibleInUnderstanding, isTrue);
      expect(state.understandingSnapshot.discardedAssumptions, contains('韩武纪'));

      expect(state.understandingResult.intents, hasLength(2));
      final stockIntent = state.understandingResult.intents.firstWhere(
        (intent) => intent.intentId == 'intent_stock_market',
      );
      final cambriconIntent = state.understandingResult.intents.firstWhere(
        (intent) => intent.intentId == 'intent_cambricon_decision',
      );
      expect(stockIntent.goal, contains('A 股'));
      expect(cambriconIntent.goal, contains('寒武纪'));
      expect(
        cambriconIntent.entityRefs.map((item) => item.displayText),
        contains('寒武纪（688256）'),
      );

      final taskQueries = state.taskGraph.tasks
          .map((task) => task.toolArgs.toJson()['query'] as String? ?? '')
          .toList(growable: false);
      expect(taskQueries, hasLength(2));
      expect(taskQueries.first, contains('A股'));
      expect(taskQueries.last, contains('寒武纪'));
      expect(taskQueries.last, contains('688256'));
      expect(taskQueries.last, isNot(contains('韩武纪')));
      expect(taskQueries.last, isNot(contains('汉武股份')));
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
          'retrievalDesignNarrative': '我会先围绕具体日期对应的天气结论继续检索。',
        },
        'understandingResult': <String, dynamic>{
          'contractId': 'understanding_result',
          'intents': <Map<String, dynamic>>[
            <String, dynamic>{
              'intentId': 'intent_weather',
              'intentType': 'weather.retrieve',
              'goal': '获取天气预报',
              'entityRefs': const <Map<String, dynamic>>[],
              'constraints': <Map<String, dynamic>>[
                <String, dynamic>{'key': 'date', 'value': '2026-04-09'},
              ],
              'requiresEvidence': true,
            },
          ],
          'dialogueTransitionDecision': const <String, dynamic>{
            'nextTurnMode': 'ask_user',
            'needsClarification': true,
            'clarificationTargetIntentId': 'intent_weather',
            'canAnswerPartially': false,
          },
        },
        'taskGraph': <String, dynamic>{
          'contractId': 'task_graph',
          'tasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'taskId': 'task_weather_forecast',
              'intentId': 'intent_weather',
              'toolName': 'web_search',
              'toolArgs': <String, dynamic>{'query': expectedQuery},
              'status': 'pending',
            },
          ],
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
          'retrievalDesignNarrative': '我会沿着最近一轮已确认的上下文继续补查。',
        },
        'understandingResult': const <String, dynamic>{
          'contractId': 'understanding_result',
          'intents': <Map<String, dynamic>>[
            <String, dynamic>{
              'intentId': 'intent_followup',
              'intentType': 'general.retrieve',
              'goal': '沿着上一轮上下文继续追问',
              'requiresEvidence': true,
            },
          ],
          'dialogueTransitionDecision': <String, dynamic>{
            'nextTurnMode': 'continue_execution',
          },
        },
        'taskGraph': const <String, dynamic>{
          'contractId': 'task_graph',
          'tasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'taskId': 'task_followup',
              'intentId': 'intent_followup',
              'toolName': 'web_search',
              'toolArgs': <String, dynamic>{'query': '沿着上一轮上下文继续追问'},
              'status': 'pending',
            },
          ],
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

class _EntityResolutionPlannerProvider implements AssistantLlmProvider {
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
        'understandingSnapshot': <String, dynamic>{
          'intentSummary': '分析今天 A 股上涨原因，并判断寒武纪当前是否适合买入',
          'userFacingSummary':
              '我理解你这轮是在问两件事：今天 A 股为什么上涨，以及寒武纪现在是否适合买。你前面已经说明 Han wu ji 指的是寒武纪，所以这轮我会按寒武纪（688256）来查，不再沿用之前的误听写法；接下来我会分别核对 A 股上涨驱动和寒武纪当前行情、估值、风险。',
          'retrievalDesignNarrative':
              '我会先核对今天 A 股上涨的政策、资金和板块驱动，再单独核对寒武纪（688256）的行情、估值、基本面和风险，这样最终建议能同时解释市场背景和个股是否适合追买。',
          'resolutionItems': const <Map<String, dynamic>>[
            <String, dynamic>{
              'kind': 'entity_resolution',
              'title': '实体纠错',
              'detail': '用户最近一轮已经说明 Han wu ji 指的是寒武纪，这轮按寒武纪（688256）处理。',
              'source': 'recent_dialogue_rounds + current_query',
              'originalValue': 'Han wu ji',
              'resolvedValue': '寒武纪（688256）',
              'defaultApplied': false,
              'visibleInUnderstanding': true,
            },
          ],
          'discardedAssumptions': const <String>['韩武纪', '汉武股份'],
        },
        'understandingResult': <String, dynamic>{
          'contractId': 'understanding_result',
          'intents': const <Map<String, dynamic>>[
            <String, dynamic>{
              'intentId': 'intent_stock_market',
              'intentType': 'finance_consumer.market_analysis',
              'goal': '分析今天 A 股上涨原因',
              'entityRefs': <Map<String, dynamic>>[
                <String, dynamic>{
                  'entityType': 'market',
                  'canonicalKey': 'A股',
                  'displayText': 'A股',
                },
              ],
              'constraints': <Map<String, dynamic>>[
                <String, dynamic>{'key': 'date', 'value': '2026-04-27'},
              ],
              'requiresEvidence': true,
            },
            <String, dynamic>{
              'intentId': 'intent_cambricon_decision',
              'intentType': 'finance_consumer.stock_decision',
              'goal': '判断寒武纪当前是否适合买入',
              'entityRefs': <Map<String, dynamic>>[
                <String, dynamic>{
                  'entityType': 'stock',
                  'canonicalKey': '688256',
                  'displayText': '寒武纪（688256）',
                },
              ],
              'constraints': <Map<String, dynamic>>[
                <String, dynamic>{'key': 'date', 'value': '2026-04-27'},
              ],
              'requiresEvidence': true,
            },
          ],
          'dialogueTransitionDecision': const <String, dynamic>{
            'nextTurnMode': 'continue_execution',
          },
        },
        'taskGraph': const <String, dynamic>{
          'contractId': 'task_graph',
          'tasks': <Map<String, dynamic>>[
            <String, dynamic>{
              'taskId': 'task_stock_market',
              'intentId': 'intent_stock_market',
              'toolName': 'web_search',
              'toolArgs': <String, dynamic>{
                'query': '2026年4月27日 A股 大涨 原因 政策 资金 板块',
              },
              'status': 'pending',
            },
            <String, dynamic>{
              'taskId': 'task_cambricon_decision',
              'intentId': 'intent_cambricon_decision',
              'toolName': 'web_search',
              'toolArgs': <String, dynamic>{
                'query': '寒武纪 688256 2026年4月27日 行情 估值 基本面 风险',
              },
              'status': 'pending',
            },
          ],
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
