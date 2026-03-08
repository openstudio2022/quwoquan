import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/personal_assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/personal_assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/personal_assistant/contracts/user_events.dart';

void main() {
  group('IntentGraph', () {
    test('支持多 skill 解析', () {
      final graph = IntentGraph.fromJson(const <String, dynamic>{
        'userGoal': '看天气并规划旅游',
        'problemShape': 'multi_skill',
        'primarySkill': 'weather',
        'secondarySkills': <String>['travel'],
        'globalConstraints': <String, dynamic>{'freshnessHoursMax': 1},
      });

      expect(graph.primarySkill, 'weather');
      expect(graph.secondarySkills, <String>['travel']);
      expect(graph.isMultiSkill, isTrue);
    });

    test('支持需澄清场景', () {
      final graph = IntentGraph.fromJson(const <String, dynamic>{
        'userGoal': '帮我安排一下',
        'problemShape': 'single_skill',
        'primarySkill': 'fallback_general_search',
        'clarificationNeeded': true,
      });

      expect(graph.clarificationNeeded, isTrue);
    });
  });

  group('AggregationState', () {
    test('支持 needExpansion 解析', () {
      final state = AggregationState.fromJson(const <String, dynamic>{
        'allSkillsReady': false,
        'blockingSkills': <String>['travel'],
        'canGivePartialAnswer': true,
        'needExpansion': true,
        'expansionPlan': <String, dynamic>{'target': 'travel'},
      });

      expect(state.needExpansion, isTrue);
      expect(state.canGivePartialAnswer, isTrue);
      expect(state.blockingSkills, <String>['travel']);
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

  group('AssistantTurnOutput', () {
    test('解析并序列化统一主线字段', () {
      final turn = AssistantTurnOutput.tryParse(const <String, dynamic>{
        'contractVersion': kAssistantTurnCurrentVersion,
        'decision': <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'userMarkdown': '## 深圳天气',
        'intentGraph': <String, dynamic>{
          'userGoal': '查看天气并规划旅游',
          'problemShape': 'multi_skill',
          'primarySkill': 'weather',
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
        'userEvents': <Map<String, dynamic>>[
          <String, dynamic>{
            'type': 'process_replace',
            'scope': 'root',
            'message': '已识别为复合问题',
          },
        ],
        'uiProcessTimelineV2': <Map<String, dynamic>>[
          <String, dynamic>{'scope': 'root', 'summary': '已拆分为 2 个任务'},
        ],
      });

      expect(turn, isNotNull);
      expect(turn!.intentGraph?.primarySkill, 'weather');
      expect(turn.skillRuns.single.domainId, 'weather');
      expect(turn.aggregationState?.canGivePartialAnswer, isTrue);
      expect(turn.userEvents.single.scope, UserEventScope.root);
      expect(turn.uiProcessTimelineV2.single['scope'], 'root');

      final envelope = turn.toEnvelopeMap();
      expect(envelope['intentGraph'], isA<Map<String, dynamic>>());
      expect(envelope['skillRuns'], isA<List<dynamic>>());
      expect(envelope['aggregationState'], isA<Map<String, dynamic>>());
    });
  });
}
