import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_plan_view.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_subagent_plan_codec.dart';

void main() {
  const codec = AssistantPipelineSubagentPlanCodec();

  test('typed plan alone does not synthesize implicit subagent plans', () {
    const planView = AssistantPlanView(
      userGoal: '看天气并规划旅游',
      primarySkill: 'weather',
      problemShape: ProblemShape.multiSkill,
      problemClass: ProblemClass.complexReasoning,
      entityRefs: <String>['深圳'],
    );

    final plans = codec.buildSkillRunPlans(
      planView: planView,
      answerPayload: const <String, dynamic>{},
      latestUserQuery: '深圳天气怎么样，顺便给我一个旅游建议',
      primaryDomainId: 'weather',
    );

    expect(plans, isEmpty);
  });

  test('normalize explicit plans and fill missing route fields', () {
    final plans = codec.buildSkillRunPlans(
      planView: const AssistantPlanView(
        userGoal: '看天气并规划旅游',
        primarySkill: 'weather',
        problemShape: ProblemShape.multiSkill,
        problemClass: ProblemClass.complexReasoning,
      ),
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
