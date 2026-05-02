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

    test('主 prompt 保留稳定主展示字段并去除记录噪音', () {
      const plannerPath =
          'assets/assistant/prompts/global/planner.global_plan.md';
      const synthPath =
          'assets/assistant/prompts/global/synthesizer.final_answer.md';

      final planner = File(plannerPath).readAsStringSync();
      final synth = File(synthPath).readAsStringSync();

      expect(planner, contains('understandingSnapshot.userFacingSummary'));
      expect(planner, contains('search_iteration_state'));
      expect(planner, contains('taskGraph.tasks[*].toolArgs.query'));
      expect(planner, contains('calendarContext'));
      expect(planner, contains('不要在本阶段输出 `decision.nextAction=answer`'));
      expect(synth, contains('retrievalProcessing.processingSummary'));
      expect(synth, contains('`tool_call`'));
      expect(synth, contains('toolCalls'));
      expect(synth, isNot(contains('answerGateAssessment')));
      expect(planner, isNot(contains('understanding.streamText')));
      expect(synth, isNot(contains('answerProcessing.streamText')));
      expect(planner, isNot(contains('uiProcessTimelineV2')));
      expect(synth, isNot(contains('whyThisAnswer')));
      expect(planner, isNot(contains('deviceProfile')));
      expect(planner, isNot(contains('deviceModel')));
      expect(planner, isNot(contains('deviceOs')));
      expect(planner, isNot(contains('gpsLocation')));
      expect(planner, isNot(contains('allowBoundedAnswer')));
      expect(planner, isNot(contains('traceId')));
    });

    test('phase contract 收口为最小动作与叙事字段', () {
      const phasePlanPath =
          'assets/assistant/prompts/global/phase.output_contract.plan.md';
      const phaseAnswerPath =
          'assets/assistant/prompts/global/phase.output_contract.answer.md';

      final phasePlan = File(phasePlanPath).readAsStringSync();
      final phaseAnswer = File(phaseAnswerPath).readAsStringSync();

      expect(phasePlan, contains('decision.nextAction'));
      expect(phasePlan, contains('understandingSnapshot.userFacingSummary'));
      expect(phasePlan, contains('toolArgs.query'));
      expect(phasePlan, contains('toolCalls'));
      expect(phasePlan, contains('reasonShort / result.*'));
      expect(phasePlan, isNot(contains('  - `answer`')));
      expect(phasePlan, isNot(contains('understanding.streamText')));
      expect(phaseAnswer, contains('retrievalProcessing.processingSummary'));
      expect(phaseAnswer, contains('toolCalls'));
      expect(phaseAnswer, isNot(contains('answerGateAssessment')));
      expect(phaseAnswer, isNot(contains('answerProcessing.readinessSummary')));
      expect(phaseAnswer, isNot(contains('answerProcessing.streamText')));
      expect(phaseAnswer, contains('userMarkdown'));
    });
  });
}
