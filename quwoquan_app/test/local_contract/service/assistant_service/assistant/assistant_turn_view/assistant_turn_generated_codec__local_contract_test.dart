import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/domain/assistant_turn_contract.dart';

void main() {
  test('generated turn codec decodes and re-encodes current nested values', () {
    final turn = AssistantTurnOutput.fromJson(<String, dynamic>{
      'contractId': kAssistantTurnCurrentContractId,
      'decision': <String, dynamic>{
        'nextAction': 'answer',
        'confidence': 0.75,
        'reasoning': 'enough evidence',
        'problemClass': 'general',
      },
      'messageKind': 'answer',
      'userMarkdown': ' visible ',
      'result': <String, dynamic>{
        'text': ' answer ',
        'summary': ' summary ',
        'interpretation': ' direct ',
        'actionHints': <String>[' retry ', ''],
      },
      'askUser': <String, dynamic>{
        'slotId': ' destination ',
        'prompt': ' Where? ',
        'required': true,
        'suggestions': <String>[' A ', ''],
      },
      'diagnostics': <String, dynamic>{
        'emergedTags': <Map<String, dynamic>>[
          <String, dynamic>{'name': 'fresh'},
        ],
        'failedChecks': <String>[' none ', ''],
        'parseStatus': ' valid ',
        'notes': <String>[' note ', ''],
      },
      'selfCheck': <String, dynamic>{
        'goalSatisfied': true,
        'constraintSatisfied': true,
        'safetyBoundarySatisfied': true,
        'failedItems': <String>[],
      },
      'toolCalls': <Map<String, dynamic>>[
        <String, dynamic>{
          'toolName': ' web_search ',
          'arguments': <String, dynamic>{'query': 'coverage'},
        },
      ],
      'understandingSnapshot': <String, dynamic>{
        'intentSummary': ' inspect coverage ',
        'concernPoints': <String>[' regression ', ''],
        'resolutionItems': <Map<String, dynamic>>[
          <String, dynamic>{
            'kind': 'fact',
            'title': ' owner ',
            'defaultApplied': true,
            'visibleInUnderstanding': false,
          },
        ],
      },
      'answerProcessing': <String, dynamic>{
        'readinessSummary': ' ready ',
        'keyFacts': <String>[' measured ', ''],
        'missingDimensions': <String>[' branch '],
        'retrieveMoreReason': ' gap ',
      },
      'missingContextSlots': <String>[' locale ', ''],
    });

    expect(turn.contractId, kAssistantTurnCurrentContractId);
    expect(turn.decision.confidence, 0.75);
    expect(turn.userMarkdown, 'visible');
    expect(turn.result.actionHints, <String>['retry']);
    expect(turn.askUser.slotId, 'destination');
    expect(turn.diagnostics.emergedTags.single['name'], 'fresh');
    expect(turn.toolCalls.single.toolName, 'web_search');
    expect(
      turn.understandingSnapshot.resolutionItems.single.visibleInUnderstanding,
      isFalse,
    );
    expect(turn.answerProcessing.keyFacts, <String>['measured']);
    expect(turn.missingContextSlots, <String>['locale']);
    expect(turn.toJson()['contractId'], kAssistantTurnCurrentContractId);
  });

  test('generated turn codec rejects unknown and invalid nested fields', () {
    expect(
      () => AssistantTurnOutput.fromJson(<String, dynamic>{'unknown': true}),
      throwsFormatException,
    );
    expect(
      () => AssistantTurnDecisionPayload.fromJson(<String, dynamic>{
        'nextAction': 'answer',
        'confidence': 'high',
      }),
      throwsFormatException,
    );
    expect(
      () => AssistantTurnDiagnostics.fromJson(<String, dynamic>{
        'emergedTags': <Object>['not-a-map'],
      }),
      throwsFormatException,
    );
    expect(
      () => AssistantTurnResult.fromJson(<String, dynamic>{
        'actionHints': <Object>[1],
      }),
      throwsFormatException,
    );
    expect(
      () => AssistantTurnToolCall.fromJson(<String, dynamic>{
        'toolName': 'web_search',
      }),
      throwsFormatException,
    );
  });
}
