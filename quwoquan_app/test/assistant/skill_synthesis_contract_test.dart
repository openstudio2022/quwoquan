import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/skill_route_contract.dart';
import 'package:quwoquan_app/assistant/contracts/skill_synthesis_contract.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';

void main() {
  test('SkillSynthesisInput.fromExecution preserves primary and supporting results', () {
    final plans = <SubagentPlan>[
      const SubagentPlan(
        subagentId: 'skill_travel_1',
        domainId: 'travel',
        problemClass: 'realtime_info',
        goal: '补充行程建议',
        role: 'supporting',
        taskBrief: '补充行程建议',
        routeNarrative: '天气确认后，再补充行程建议。',
        localContextSeed: 'seed',
        pendingClarifications: <String>['date'],
      ),
    ];
    final runs = <AssistantSubagentRunRecord>[
      const AssistantSubagentRunRecord(
        version: 'subagent_result',
        subagentId: 'skill_travel_1',
        domainId: 'travel',
        status: 'success',
        goal: '补充行程建议',
        mode: 'qa',
        problemClass: 'realtime_info',
        shell: <String, dynamic>{},
        stopPolicy: 'balanced',
        searchIntensity: 'medium',
        providerPolicy: '',
        freshnessHoursMax: 6,
        answerThreshold: 0.7,
        summary: '行程可判断。',
        userMarkdown: '行程可判断。',
        result: <String, dynamic>{'text': '行程可判断。'},
        answerReady: true,
        references: <Map<String, dynamic>>[],
        acceptedEvidence: <Map<String, dynamic>>[
          <String, dynamic>{'title': '行程'},
        ],
        rejectedEvidence: <Map<String, dynamic>>[],
        nextAction: 'answer',
        missingSlots: <String>[],
        failureReason: '',
        toolCallCount: 1,
        modelCallCount: 1,
        totalTokens: 100,
        maxTokensPerCall: 100,
        tokenSource: 'usage',
        tokenSampleCount: 1,
      ),
    ];

    final route = SkillRouteOutput.fromPrimaryAndSupportingPlans(
      userQuery: '深圳天气怎么样，顺便给我明天的行程建议',
      primaryTarget: SkillRouteTarget.primary(
        skillId: 'weather',
        goal: '核验天气',
        problemClass: 'realtime_info',
        taskBrief: '核验天气',
        routeNarrative: '先确认天气，再补充行程建议。',
        localContextSeed: 'weather_seed',
        pendingClarifications: const <String>['city'],
      ),
      supportingPlans: plans,
      routeNarrative: '先确认天气，再并行补充行程建议。',
      pendingClarifications: const <String>['city', 'date'],
    );
    final input = SkillSynthesisInput.fromExecution(
      userQuery: '深圳天气怎么样，顺便给我明天的行程建议',
      skillRoute: route,
      subagentRuns: runs,
      primarySkillResult: const SkillSynthesisSkillResult(
        skillId: 'weather',
        role: 'primary',
        status: 'success',
        summary: '天气可判断。',
        acceptedEvidence: <Map<String, dynamic>>[
          <String, dynamic>{'title': '天气'},
        ],
        answerReady: true,
      ),
      sessionSummary: '上一轮已确认城市。',
    );

    expect(input.selectedTargets, hasLength(2));
    expect(input.selectedTargets.first.skillId, 'weather');
    expect(input.selectedTargets.last.skillId, 'travel');
    expect(input.skillResults, hasLength(2));
    expect(input.skillResults.first.skillId, 'weather');
    expect(input.skillResults.last.skillId, 'travel');
    expect(input.pendingClarifications, contains('city'));
    expect(input.pendingClarifications, contains('date'));
    expect(input.hasPendingWork, isTrue);
  });

  test('SkillSynthesisOutput.fromStructuredAnswer keeps partial answers distinct', () {
    const input = SkillSynthesisInput(
      userQuery: '深圳天气怎么样',
      routeNarrative: '先查天气，再给出建议。',
      selectedTargets: <SkillSynthesisTarget>[
        SkillSynthesisTarget(skillId: 'weather', role: 'primary', priority: 1),
      ],
      skillResults: <SkillSynthesisSkillResult>[
        SkillSynthesisSkillResult(
          skillId: 'weather',
          role: 'primary',
          status: 'failed',
          summary: '天气仍需补查。',
          missingSlots: <String>['city'],
          failureReason: 'missing_city',
        ),
      ],
      pendingClarifications: <String>['city'],
    );

    final output = SkillSynthesisOutput.fromStructuredAnswer(
      answerPayload: <String, dynamic>{
        'userMarkdown': '先补城市再查天气。',
        'decision': <String, dynamic>{'nextAction': AssistantNextAction.askUser.wireName},
        'skillSynthesis': <String, dynamic>{
          'answerMarkdown': '先补城市再查天气。',
        },
      },
      input: input,
      aggregationState: const AggregationState(canGivePartialAnswer: true),
      synthesisReadiness: const SynthesisReadinessResult(ready: false),
    );

    expect(output.answerMarkdown, '先补城市再查天气。');
    expect(output.partialCompletionState, equals('needs_clarification'));
    expect(output.unresolvedSkills, contains('weather'));
    expect(output.isPartial, isTrue);
  });
}
