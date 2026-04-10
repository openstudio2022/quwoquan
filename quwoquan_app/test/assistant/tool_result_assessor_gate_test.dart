import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/protocol/progress_text_policy.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/react_state.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/tool_result_assessor.dart';
import 'package:test/test.dart';

void main() {
  test('freshness unknown 时不会放行当前证据直接成答', () {
    final assessor = ToolResultAssessor()
      ..boundaryPolicy = const AnswerBoundaryPolicy(
        evidenceRequired: true,
        freshnessHoursMax: 6,
      );

    final assessment = assessor.assess(
      state: ReactRunState(goal: 'latest weather', maxIterations: 4, toolBudget: 4),
      lastStepSuccess: true,
      lastObservation: <String, dynamic>{
        'data': <String, dynamic>{
          'summary': '拿到 1 条候选资料',
          'qualityScore': 0.91,
          'referenceCount': 1,
          'totalReferences': 1,
          'freshnessRequired': true,
          'freshnessKnown': false,
          'freshnessSatisfied': false,
          'references': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '天气快讯',
              'url': 'https://example.com/weather',
              'snippet': '页面没有明确发布时间。',
            },
          ],
        },
      },
      shouldReplan: false,
      policy: ReactPolicy.defaults,
    );

    expect(assessment.allowAnswerWithCurrentEvidence, isFalse);
    expect(assessment.referenceCount, 1);
  });

  test('authority 未满足时不会放行 bounded answer', () {
    final assessor = ToolResultAssessor()
      ..boundaryPolicy = const AnswerBoundaryPolicy(
        evidenceRequired: true,
        authorityRequired: true,
        authorityDomains: <String>['gov.cn'],
      );

    final assessment = assessor.assess(
      state: ReactRunState(goal: 'policy notice', maxIterations: 4, toolBudget: 4),
      lastStepSuccess: true,
      lastObservation: <String, dynamic>{
        'data': <String, dynamic>{
          'summary': '拿到 1 条候选资料',
          'qualityScore': 0.88,
          'referenceCount': 1,
          'totalReferences': 1,
          'authoritySatisfied': false,
          'references': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '站外解读',
              'url': 'https://example.com/post',
              'snippet': '非权威转载。',
            },
          ],
        },
      },
      shouldReplan: false,
      policy: ReactPolicy.defaults,
    );

    expect(assessment.allowAnswerWithCurrentEvidence, isFalse);
    expect(assessment.referenceCount, 1);
  });
}
