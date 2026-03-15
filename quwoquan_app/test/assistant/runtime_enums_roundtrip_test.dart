import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';

void main() {
  group('runtime enums roundtrip', () {
    test('problem / answer / freshness roundtrip', () {
      expect(parseProblemClass(ProblemClass.realtimeInfo.wireName), ProblemClass.realtimeInfo);
      expect(parseAnswerShape(AnswerShape.comparison.wireName), AnswerShape.comparison);
      expect(parseFreshnessNeed(FreshnessNeed.recent.wireName), FreshnessNeed.recent);
      expect(parseProblemShape(ProblemShape.multiSkill.wireName), ProblemShape.multiSkill);
      expect(parseProviderPolicy(ProviderPolicy.authorityFirst.wireName), ProviderPolicy.authorityFirst);
    });

    test('skill / evidence source / final decision roundtrip', () {
      expect(
        parseSkillExecutionTarget(SkillExecutionTarget.toolChain.wireName),
        SkillExecutionTarget.toolChain,
      );
      expect(
        parseEvidenceSourceTier(EvidenceSourceTier.authority.wireName),
        EvidenceSourceTier.authority,
      );
      expect(parseFinalAnswerMode(FinalAnswerMode.boundedAnswer.wireName), FinalAnswerMode.boundedAnswer);
      expect(parseAnswerEligibility(AnswerEligibility.eligible.wireName), AnswerEligibility.eligible);
    });

    test('planner protocol enums roundtrip', () {
      expect(parsePlannerPhaseId(PlannerPhaseId.searching.wireName), PlannerPhaseId.searching);
      expect(parsePlannerActionCode(PlannerActionCode.startRetrieval.wireName), PlannerActionCode.startRetrieval);
      expect(parsePlannerReasonCode(PlannerReasonCode.sourceUnstable.wireName), PlannerReasonCode.sourceUnstable);
      expect(parseAssessmentType(AssessmentType.needMoreSearch.wireName), AssessmentType.needMoreSearch);
      expect(parseEvidenceStatus(EvidenceStatus.bounded.wireName), EvidenceStatus.bounded);
    });
  });
}
