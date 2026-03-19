import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/domain/conversation/conversation.dart';

void main() {
  group('assistant turn contract roundtrip', () {
    test('typed getters expose canonical process protocol', () {
      final output = AssistantTurnOutput(
        contractId: kAssistantTurnCurrentContractId,
        decision: const AssistantTurnDecisionPayload(
          nextAction: AssistantNextAction.answer,
          confidence: 0.92,
        ),
        messageKind: AssistantMessageKind.answer,
        userMarkdown: '## 已整理',
        result: const AssistantTurnResult(text: '直接答案', interpretation: '摘要结论'),
        slotState: const SlotStateSnapshot(
          domainId: 'weather',
          slotValues: <String, SlotValueSnapshot>{
            'city': SlotValueSnapshot(
              slotId: 'city',
              value: '深圳',
              source: 'user_query',
            ),
          },
        ),
        askUser: const AssistantTurnAskUser(slotId: 'city', prompt: '请告诉我城市'),
        phaseId: PlannerPhaseId.answering,
        actionCode: PlannerActionCode.composeAnswer,
        reasonCode: PlannerReasonCode.evidenceReady,
      );

      expect(output.nextActionType, AssistantNextAction.answer);
      expect(output.messageKindType, AssistantMessageKind.answer);
      expect(output.phaseIdType, PlannerPhaseId.answering);
      expect(output.actionCodeType, PlannerActionCode.composeAnswer);
      expect(output.reasonCodeType, PlannerReasonCode.evidenceReady);
      expect(output.resultText, '直接答案');
      expect(output.interpretation, '摘要结论');
      expect(output.hasRenderableAnswer, isTrue);
      expect(output.askUserPrompt, '请告诉我城市');
      expect(output.askUserSlotId, 'city');
      expect(output.slotStateSnapshot.slotValues['city']?.value, '深圳');
      expect(output.processProtocolCode.toJson(), <String, dynamic>{
        'stage': PlannerPhaseId.answering.wireName,
        'phaseId': PlannerPhaseId.answering.wireName,
        'actionCode': PlannerActionCode.composeAnswer.wireName,
        'reasonCode': PlannerReasonCode.evidenceReady.wireName,
      });
    });

    test('missingContextSlots uses canonical field only', () {
      final parsed = tryParseAssistantTurnOutput(<String, dynamic>{
        'contractId': kAssistantTurnCurrentContractId,
        'decision': <String, dynamic>{
          'nextAction': AssistantNextAction.askUser.wireName,
        },
        'messageKind': AssistantMessageKind.askUser.wireName,
        'userMarkdown': '请补充城市',
        'missingContextSlots': <String>['city'],
      });

      expect(parsed, isNotNull);
      expect(parsed!.missingContextSlots, <String>['city']);
    });

    test('missing messageKind is rejected under strict contract parsing', () {
      final parsed = tryParseAssistantTurnOutput(<String, dynamic>{
        'contractId': kAssistantTurnCurrentContractId,
        'decision': <String, dynamic>{
          'nextAction': AssistantNextAction.answer.wireName,
        },
        'phaseId': PlannerPhaseId.answering.wireName,
        'actionCode': PlannerActionCode.composeAnswer.wireName,
        'reasonCode': PlannerReasonCode.evidenceReady.wireName,
        'userMarkdown': '## 已整理\n\n这是最终回答。',
        'result': const <String, dynamic>{
          'text': '这是最终回答。',
          'summary': '最终回答摘要',
        },
      });

      expect(parsed, isNull);
    });

    test('answer-phase turn keeps explicit messageKind without compatibility rewrite', () {
      final parsed = tryParseAssistantTurnOutput(<String, dynamic>{
        'contractId': kAssistantTurnCurrentContractId,
        'decision': <String, dynamic>{
          'nextAction': AssistantNextAction.answer.wireName,
        },
        'messageKind': AssistantMessageKind.progress.wireName,
        'phaseId': PlannerPhaseId.answering.wireName,
        'actionCode': PlannerActionCode.composeAnswer.wireName,
        'reasonCode': PlannerReasonCode.evidenceReady.wireName,
        'userMarkdown': '## 已整理\n\n这是最终回答。',
        'result': const <String, dynamic>{
          'text': '这是最终回答。',
          'summary': '最终回答摘要',
        },
      });

      expect(parsed, isNotNull);
      expect(parsed!.messageKindType, AssistantMessageKind.progress);
      expect(parsed.nextActionType, AssistantNextAction.answer);
    });
  });
}
