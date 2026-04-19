import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/aggregation_state.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/skill_synthesis_contract.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';

void main() {
  test('SkillSynthesisInput.fromExecution preserves selected targets and results', () {
    final plans = <SubagentPlan>[
      const SubagentPlan(
        subagentId: 'skill_weather_1',
        domainId: 'weather',
        problemClass: 'realtime_info',
        goal: '核验天气',
        role: 'primary',
        taskBrief: '核验天气',
        routeNarrative: '先查天气，再给出建议。',
        localContextSeed: 'seed',
        pendingClarifications: <String>['city'],
      ),
    ];
    final runs = <AssistantSubagentRunRecord>[
      const AssistantSubagentRunRecord(
        version: 'subagent_result',
        subagentId: 'skill_weather_1',
        domainId: 'weather',
        status: 'success',
        goal: '核验天气',
        mode: 'qa',
        problemClass: 'realtime_info',
        shell: <String, dynamic>{},
        stopPolicy: 'balanced',
        searchIntensity: 'medium',
        providerPolicy: '',
        freshnessHoursMax: 6,
        answerThreshold: 0.7,
        summary: '天气可判断。',
        userMarkdown: '天气可判断。',
        result: <String, dynamic>{'text': '天气可判断。'},
        answerReady: true,
        references: <Map<String, dynamic>>[],
        acceptedEvidence: <Map<String, dynamic>>[
          <String, dynamic>{'title': '天气'},
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

    final input = SkillSynthesisInput.fromExecution(
      userQuery: '深圳天气怎么样',
      routeNarrative: '先查天气，再给出建议。',
      selectedTargets: plans,
      subagentRuns: runs,
      pendingClarifications: <String>['city'],
      sessionSummary: '上一轮已确认城市。',
    );

    expect(input.selectedTargets, hasLength(1));
    expect(input.skillResults, hasLength(1));
    expect(input.skillResults.first.skillId, 'weather');
    expect(input.pendingClarifications, contains('city'));
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
