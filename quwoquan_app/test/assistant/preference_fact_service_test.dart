import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/preference_fact.dart';
import 'package:quwoquan_app/assistant/memory/preference/preference_fact_service.dart';

void main() {
  test('collectPreferenceFactsFromMessages 去重并保留顺序', () {
    final turn = tryParseAssistantTurnOutput(const <String, dynamic>{
      'contractId': kAssistantTurnCurrentContractId,
      'decision': <String, dynamic>{'nextAction': 'answer'},
      'messageKind': 'answer',
      'userMarkdown': '## 已整理',
      'sessionPreferenceFacts': <Map<String, dynamic>>[
        <String, dynamic>{
          'factId': 'session_1',
          'scope': 'session',
          'key': 'feedbackHint',
          'value': '更结构化一点',
          'source': 'assistant_pipeline_engine',
        },
        <String, dynamic>{
          'factId': 'session_1',
          'scope': 'session',
          'key': 'feedbackHint',
          'value': '更结构化一点',
          'source': 'assistant_pipeline_engine',
        },
      ],
    });
    expect(turn, isNotNull);

    final service = PreferenceFactService();
    final facts = service.collectPreferenceFactsFromMessages(
      <Map<String, dynamic>>[
        <String, dynamic>{
          'role': 'assistant',
          'content': jsonEncode(turn!.toJson()),
        },
      ],
      selector: (parsedTurn) => parsedTurn.sessionPreferenceFacts,
    );

    expect(facts, hasLength(1));
    expect(facts.single.key, equals('feedbackHint'));
    expect(facts.single.value, equals('更结构化一点'));
  });

  test('buildLongTermPreferenceFacts 合并 seed 与 session feedback', () {
    final service = PreferenceFactService();
    final facts = service.buildLongTermPreferenceFacts(
      seedFactsRaw: const <Map<String, dynamic>>[
        <String, dynamic>{
          'factId': 'seed_1',
          'scope': 'long_term',
          'key': 'tone',
          'value': 'concise',
          'source': 'seed',
        },
      ],
      emergedTagMaps: const <Map<String, dynamic>>[
        <String, dynamic>{
          'tag': 'tone',
          'value': 'concise',
        },
      ],
      sessionFacts: const <PreferenceFact>[
        PreferenceFact(
          factId: 'session_feedback_1',
          scope: 'session',
          key: 'feedbackHint',
          value: '更结构化一点',
          source: 'context_scope_hint',
          createdAt: '2026-04-14T00:00:00.000Z',
        ),
      ],
    );

    expect(facts, hasLength(3));
    expect(facts.where((item) => item.key == 'feedbackHint'), isNotEmpty);
    expect(facts.map((item) => item.scope), everyElement(equals('long_term')));
    expect(
      facts.where((item) => item.key == 'feedbackHint').single.value,
      equals('更结构化一点'),
    );
  });
}
