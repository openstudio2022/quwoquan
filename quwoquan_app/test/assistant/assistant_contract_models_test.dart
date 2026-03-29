import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/domain/agent/agent.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';
import 'package:quwoquan_app/assistant/domain/memory/memory.dart';

void main() {
  group('IntentGraph', () {
    test('支持多 skill 解析', () {
      final graph = IntentGraph.fromJson(const <String, dynamic>{
        'userGoal': '看天气并规划旅游',
        'problemShape': 'multi_skill',
        'primarySkill': 'weather',
        'problemClass': 'complex_reasoning',
        'secondarySkills': <String>['travel'],
        'globalConstraints': <String, dynamic>{'freshnessHoursMax': 1},
      });

      expect(graph.primarySkill, 'weather');
      expect(graph.problemClass, ProblemClass.complexReasoning);
      expect(graph.secondarySkills, <String>['travel']);
      expect(graph.isMultiSkill, isTrue);
    });

    test('支持 authorityDomains 与 freshnessHoursMax 解析', () {
      final graph = IntentGraph.fromJson(const <String, dynamic>{
        'userGoal': '查深圳天气',
        'problemShape': 'single_skill',
        'primarySkill': 'weather',
        'problemClass': 'realtime_info',
        'authorityDomains': <String>['weather.com.cn', 'cma.cn'],
        'freshnessHoursMax': 1,
      });

      expect(graph.authorityDomains, <String>['weather.com.cn', 'cma.cn']);
      expect(graph.freshnessHoursMax, 1);
      expect(graph.toJson()['authorityDomains'], <String>[
        'weather.com.cn',
        'cma.cn',
      ]);
      expect(graph.toJson()['freshnessHoursMax'], 1);
    });

    test('支持需澄清场景', () {
      final graph = IntentGraph.fromJson(const <String, dynamic>{
        'userGoal': '帮我安排一下',
        'problemShape': 'single_skill',
        'primarySkill': 'fallback_general_search',
        'problemClass': 'task_execution',
        'clarificationNeeded': true,
      });

      expect(graph.clarificationNeeded, isTrue);
      expect(graph.problemClass, ProblemClass.taskExecution);
    });
  });

  group('AggregationState', () {
    test('支持 needExpansion 解析', () {
      final state = AggregationState.fromJson(const <String, dynamic>{
        'allSkillsReady': false,
        'blockingSkills': <String>['travel'],
        'blockedBy': <String, dynamic>{
          'travel': <String, dynamic>{'stopReason': 'replan', 'answerReady': false},
        },
        'canGivePartialAnswer': true,
        'needExpansion': true,
        'expansionPlan': <String, dynamic>{
          'targetSkills': <String>['travel'],
          'policy': 'expand_scope_and_requery',
        },
        'answerOwner': 'skill_weather_1',
        'dependencies': <String, dynamic>{
          'skill_weather_1': <String, dynamic>{'runIds': <String>[]},
          'travel_planner_1': <String, dynamic>{
            'runIds': <String>['skill_weather_1'],
          },
        },
      });

      expect(state.needExpansion, isTrue);
      expect(state.canGivePartialAnswer, isTrue);
      expect(state.blockingSkills, <String>['travel']);
      expect(
        state.blockedBy['travel']?.stopReason,
        equals(FinalAnswerMode.replan),
      );
      expect(
        state.expansionPlan.policy,
        equals(ContextScopeExpansionPolicy.expandScopeAndRequery),
      );
      expect(state.answerOwner, equals('skill_weather_1'));
    });
  });

  group('UserEvent', () {
    test('支持 root/skill/aggregation 作用域', () {
      final event = UserEvent.fromJson(const <String, dynamic>{
        'type': 'process_append',
        'scope': 'skill',
        'message': '已核对天气来源',
        'nodeId': 'weather.progress',
        'runId': 'skill_1',
      });

      expect(event.type, UserEventType.processAppend);
      expect(event.scope, UserEventScope.skill);
      expect(event.message, contains('天气'));
    });
  });

  group('Typed contract models', () {
    test('RunArtifacts 支持 journey 契约序列化', () {
      final artifacts = RunArtifacts.fromJson(const <String, dynamic>{
        'journey': <String, dynamic>{
          'stages': <Map<String, dynamic>>[
            <String, dynamic>{
              'stageId': 'analyze',
              'status': 'completed',
              'order': 0,
              'summary': '先确认问题范围',
            },
            <String, dynamic>{
              'stageId': 'search',
              'status': 'completed',
              'order': 1,
              'summary': '已核对 1 个权威来源',
              'referenceCount': 1,
            },
          ],
          'entries': <Map<String, dynamic>>[
            <String, dynamic>{
              'entryId': 'journey.search.1',
              'stageId': 'search',
              'kind': 'reference_bundle',
              'status': 'completed',
              'order': 1,
              'headline': '已核对 1 个权威来源',
              'references': <Map<String, dynamic>>[
                <String, dynamic>{
                  'title': '中国气象局',
                  'url': 'https://weather.cma.cn/',
                },
              ],
            },
          ],
          'summary': '已核对 1 个权威来源',
          'referenceSummary': <String, dynamic>{
            'count': 1,
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '中国气象局',
                'url': 'https://weather.cma.cn/',
              },
            ],
          },
          'readiness': <String, dynamic>{
            'nextAction': 'answer',
            'finalAnswerMode': 'direct',
            'answerEligibility': 'ready',
            'finalAnswerReady': true,
          },
        },
        'slotState': <String, dynamic>{
          'domainId': 'weather',
          'slotValues': <String, dynamic>{
            'city': <String, dynamic>{
              'slotId': 'city',
              'status': 'confirmed',
              'value': '深圳',
            },
          },
          'missingSlots': <String>[],
        },
        'answerDecision': <String, dynamic>{'nextAction': 'answer'},
        'diagnostics': <String, dynamic>{'renderMode': 'fallback_text'},
        'domainPolicyBundle': <String, dynamic>{'domainId': 'weather'},
      });

      expect(artifacts.journey.stages.length, 2);
      expect(artifacts.journey.entries.single.headline, '已核对 1 个权威来源');
      expect(artifacts.journey.referenceSummary.count, 1);
      expect(artifacts.slotState.domainId, equals('weather'));
      expect(artifacts.answerDecision['nextAction'], equals('answer'));
      expect(artifacts.domainPolicyBundle?.domainId, equals('weather'));
      expect(artifacts.toJson()['journey'], isA<Map<String, dynamic>>());
    });

    test('SubagentPlan 支持完整策略字段解析', () {
      final plan = SubagentPlan.fromJson(const <String, dynamic>{
        'subagentId': 'travel_planner_1',
        'domainId': 'fallback_general_search',
        'problemClass': 'complex_reasoning',
        'goal': '结合天气补充旅游建议',
        'stopPolicy': 'explore',
        'searchIntensity': 'high',
        'providerPolicy': 'model_choice',
        'freshnessHoursMax': 6,
        'answerThreshold': 0.8,
      });

      expect(plan.problemClass, equals('complex_reasoning'));
      expect(plan.stopPolicy, equals('explore'));
      expect(plan.searchIntensity, equals('high'));
      expect(plan.freshnessHoursMax, equals(6));
      expect(plan.answerThreshold, closeTo(0.8, 0.001));
    });

    test('PreferenceFact 支持会话与长期事实', () {
      final fact = PreferenceFact.fromJson(const <String, dynamic>{
        'factId': 'session_1',
        'scope': 'session',
        'key': 'feedbackHint',
        'value': '更结构化一点',
      });

      expect(fact.scope, equals('session'));
      expect(fact.key, equals('feedbackHint'));
      expect(fact.value, contains('结构化'));
    });
  });

  group('AssistantTurnOutput', () {
    test('解析并序列化统一主线字段', () {
      final turn = tryParseAssistantTurnOutput(const <String, dynamic>{
        'contractId': kAssistantTurnCurrentContractId,
        'decision': <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '## 深圳天气',
        'intentGraph': <String, dynamic>{
          'userGoal': '查看天气并规划旅游',
          'problemShape': 'multi_skill',
          'primarySkill': 'weather',
          'problemClass': 'complex_reasoning',
          'secondarySkills': <String>['travel'],
        },
        'skillRuns': <Map<String, dynamic>>[
          <String, dynamic>{
            'runId': 'skill_1',
            'domainId': 'weather',
            'goal': '查询深圳天气',
            'problemClass': 'realtime_info',
            'answerReady': true,
          },
        ],
        'aggregationState': <String, dynamic>{
          'allSkillsReady': false,
          'blockingSkills': <String>['travel'],
          'canGivePartialAnswer': true,
        },
        'journey': <String, dynamic>{
          'stages': <Map<String, dynamic>>[
            <String, dynamic>{
              'stageId': 'search',
              'status': 'completed',
              'order': 1,
              'summary': '已核对 1 个天气来源',
              'referenceCount': 1,
            },
          ],
          'entries': <Map<String, dynamic>>[
            <String, dynamic>{
              'entryId': 'journey.search.1',
              'stageId': 'search',
              'kind': 'reference_bundle',
              'status': 'completed',
              'order': 1,
              'headline': '已核对 1 个天气来源',
              'references': <Map<String, dynamic>>[
                <String, dynamic>{
                  'title': '中国气象局',
                  'url': 'https://weather.cma.cn/',
                },
              ],
            },
          ],
          'summary': '已核对 1 个天气来源',
          'referenceSummary': <String, dynamic>{
            'count': 1,
            'references': <Map<String, dynamic>>[
              <String, dynamic>{
                'title': '中国气象局',
                'url': 'https://weather.cma.cn/',
              },
            ],
          },
        },
        'subagentPlan': <Map<String, dynamic>>[
          <String, dynamic>{
            'subagentId': 'travel_planner_1',
            'domainId': 'fallback_general_search',
            'problemClass': 'complex_reasoning',
            'goal': '结合天气补充旅游建议',
            'stopPolicy': 'balanced',
            'searchIntensity': 'medium',
          },
        ],
        'sessionPreferenceFacts': <Map<String, dynamic>>[
          <String, dynamic>{
            'factId': 'session_1',
            'scope': 'session',
            'key': 'feedbackHint',
            'value': '更结构化一点',
          },
        ],
      });

      expect(turn, isNotNull);
      expect(turn!.intentGraph?.primarySkill, 'weather');
      expect(turn.intentGraph?.problemClass, ProblemClass.complexReasoning);
      expect(turn.skillRuns.single.domainId, 'weather');
      expect(turn.aggregationState?.canGivePartialAnswer, isTrue);
      expect(turn.journey.summary, equals('已核对 1 个天气来源'));
      expect(turn.journey.referenceSummary.count, equals(1));
      expect(
        turn.subagentPlan.single.problemClass,
        equals('complex_reasoning'),
      );
      expect(turn.journey.entries.single.references.single.title, equals('中国气象局'));
      expect(turn.sessionPreferenceFacts.single.key, equals('feedbackHint'));

      final envelope = turn.toEnvelopeMap();
      expect(envelope['intentGraph'], isA<Map<String, dynamic>>());
      expect(envelope['skillRuns'], isA<List<dynamic>>());
      expect(envelope['aggregationState'], isA<Map<String, dynamic>>());
      expect(envelope['journey'], isA<Map<String, dynamic>>());
    });
  });
}
