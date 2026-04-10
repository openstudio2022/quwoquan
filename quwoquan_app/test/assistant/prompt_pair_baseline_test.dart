import 'dart:io';

import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:test/test.dart';

void main() {
  const validator = TemplateValidator();

  group('Two prompt baseline', () {
    test('planner.global_plan 与 synthesizer.final_answer 通过模板校验', () {
      const plannerPath =
          'assets/assistant/prompts/global/planner.global_plan.md';
      const synthPath =
          'assets/assistant/prompts/global/synthesizer.final_answer.md';

      final planner = File(plannerPath).readAsStringSync();
      final synth = File(synthPath).readAsStringSync();

      final plannerResult = validator.validate(
        templateId: 'planner.global_plan',
        content: planner,
      );
      final synthResult = validator.validate(
        templateId: 'synthesizer.final_answer',
        content: synth,
      );

      expect(
        plannerResult.isValid,
        isTrue,
        reason:
            'planner.global_plan 应通过 TemplateValidator: ${plannerResult.errors}',
      );
      expect(
        synthResult.isValid,
        isTrue,
        reason:
            'synthesizer.final_answer 应通过 TemplateValidator: ${synthResult.errors}',
      );
    });

    test('主 prompt 保留稳定主展示字段并去除历史噪音', () {
      const plannerPath =
          'assets/assistant/prompts/global/planner.global_plan.md';
      const synthPath =
          'assets/assistant/prompts/global/synthesizer.final_answer.md';

      final planner = File(plannerPath).readAsStringSync();
      final synth = File(synthPath).readAsStringSync();

      expect(planner, contains('understandingSnapshot.userFacingSummary'));
      expect(planner, contains('search_iteration_state'));
      expect(planner, contains('intentGraph.queryTasks[*].query'));
      expect(planner, contains('calendarContext'));
      expect(synth, contains('retrievalProcessing.processingSummary'));
      expect(synth, contains('answerProcessing.readinessSummary'));
      expect(synth, contains('answerGateAssessment'));
      expect(planner, isNot(contains('understanding.streamText')));
      expect(synth, isNot(contains('answerProcessing.streamText')));
      expect(planner, isNot(contains('uiProcessTimelineV2')));
      expect(synth, isNot(contains('whyThisAnswer')));
    });

    test('phase contract 保留 reasonShort 并只要求稳定主字段', () {
      const phasePlanPath =
          'assets/assistant/prompts/global/phase.output_contract.plan.md';
      const phaseAnswerPath =
          'assets/assistant/prompts/global/phase.output_contract.answer.md';

      final phasePlan = File(phasePlanPath).readAsStringSync();
      final phaseAnswer = File(phaseAnswerPath).readAsStringSync();

      expect(phasePlan, contains('reasonShort'));
      expect(phasePlan, contains('understandingSnapshot.userFacingSummary'));
      expect(phasePlan, contains('queryTasks.query'));
      expect(phasePlan, isNot(contains('understanding.streamText')));
      expect(phaseAnswer, contains('retrievalProcessing.processingSummary'));
      expect(phaseAnswer, contains('answerProcessing.readinessSummary'));
      expect(phaseAnswer, contains('answerGateAssessment'));
      expect(phaseAnswer, isNot(contains('answerProcessing.streamText')));
      expect(phaseAnswer, contains('userMarkdown'));
    });
  });
}
