import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_subagent_plan_codec.dart';

void main() {
  const codec = AssistantPipelineSubagentPlanCodec();

  test('derive skill plans with milestone 3 inputs', () {
    final intentGraph = IntentGraph.fromJson(const <String, dynamic>{
      'userGoal': '看天气并规划旅游',
      'problemShape': 'multi_skill',
      'primarySkill': 'weather',
      'problemClass': 'complex_reasoning',
      'secondarySkills': <String>['travel'],
      'entityAnchors': <String>['深圳'],
      'clarificationNeeded': false,
    });

    final plans = codec.buildSkillRunPlans(
      intentGraph: intentGraph,
      answerPayload: const <String, dynamic>{},
      latestUserQuery: '深圳天气怎么样，顺便给我一个旅游建议',
      primaryDomainId: 'weather',
    );

    expect(plans, hasLength(1));
    expect(plans.single.hasMilestone3Inputs, isTrue);
    expect(plans.single.role, equals('supporting'));
    expect(plans.single.taskBrief, isNotEmpty);
    expect(plans.single.routeNarrative, isNotEmpty);
    expect(plans.single.localContextSeed, contains('深圳'));
  });

  test('normalize explicit plans and fill missing route fields', () {
    final plans = codec.buildSkillRunPlans(
      intentGraph: IntentGraph.fromJson(const <String, dynamic>{
        'userGoal': '看天气并规划旅游',
        'problemShape': 'multi_skill',
        'primarySkill': 'weather',
        'problemClass': 'complex_reasoning',
        'secondarySkills': <String>['travel'],
      }),
      answerPayload: const <String, dynamic>{
        'contractId': 'assistant_turn',
        'decision': <String, dynamic>{'nextAction': 'answer'},
        'messageKind': 'answer',
        'subagentPlan': <Map<String, dynamic>>[
          <String, dynamic>{
            SubagentPlanFields.subagentId: 'travel_1',
            SubagentPlanFields.domainId: 'travel',
            SubagentPlanFields.problemClass: 'complex_reasoning',
            SubagentPlanFields.goal: '补充旅游建议',
          },
        ],
      },
      latestUserQuery: '深圳天气怎么样，顺便给我一个旅游建议',
      primaryDomainId: 'weather',
    );

    expect(plans, hasLength(1));
    expect(plans.single.taskBrief, equals('补充旅游建议'));
    expect(plans.single.routeNarrative, isNotEmpty);
    expect(plans.single.localContextSeed, isNotEmpty);
    expect(plans.single.problemClass, equals('complex_reasoning'));
  });
}
