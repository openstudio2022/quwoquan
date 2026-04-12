import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_answer_payload_read_view.dart';

void main() {
  test('AssistantAnswerPayloadReadView centralizes map casts', () {
    final raw = <String, dynamic>{
      'decision': <String, dynamic>{'problemClass': 'realtime_info'},
      'diagnostics': <String, dynamic>{
        'emergedTags': <Map<String, dynamic>>[
          <String, dynamic>{'tag': 't1', 'value': 'v1'},
        ],
      },
      'result': <String, dynamic>{'text': ' hello '},
      'askUser': <String, dynamic>{'slotId': 'city'},
      'subagentPlan': <Map<String, dynamic>>[
        <String, dynamic>{'domainId': 'other', 'goal': 'g'},
      ],
      'evidence': <Map<String, dynamic>>[
        <String, dynamic>{'claim': 'c1'},
      ],
    };
    final v = AssistantAnswerPayloadReadView(raw);
    expect(v.decisionMap['problemClass'], 'realtime_info');
    expect(v.asTypedOutput.decision.problemClass, 'realtime_info');
    expect(v.diagnosticsEmergedTagMaps.single['tag'], 't1');
    expect(v.resultMap['text'], ' hello ');
    expect(v.askUserMap['slotId'], 'city');
    expect(v.subagentPlanMaps.single['goal'], 'g');
    expect(v.evidenceMaps.single['claim'], 'c1');
  });

  test('missing branches yield empty maps / lists', () {
    final v = AssistantAnswerPayloadReadView(<String, dynamic>{});
    expect(v.decisionMap, isEmpty);
    expect(v.diagnosticsMap, isEmpty);
    expect(v.diagnosticsEmergedTagMaps, isEmpty);
  });
}
