import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('21 skill eval fixture aligns with app routing catalog', () {
    final routing =
        jsonDecode(
              File(
                'assets/assistant/prompts/domain_routing/domain_routing_catalog.json',
              ).readAsStringSync(),
            )
            as Map<String, dynamic>;
    final fixture =
        jsonDecode(
              File(
                '../quwoquan_service/contracts/metadata/assistant/test_fixtures/scenarios/assistant_skill_eval_scenarios.json',
              ).readAsStringSync(),
            )
            as Map<String, dynamic>;

    final routedDomains =
        ((routing['domains'] as List?) ?? const <dynamic>[])
            .whereType<Map>()
            .map((item) => item['domainId'].toString())
            .toList(growable: false)
          ..sort();
    final scenarios = ((fixture['scenarios'] as List?) ?? const <dynamic>[])
        .whereType<Map>();
    final scenarioDomains =
        scenarios
            .where((item) => item['type'] == 'assistant_turn')
            .map((item) => item['domainId'].toString())
            .toList(growable: false)
          ..sort();

    expect(scenarioDomains, routedDomains);
    expect(scenarioDomains, hasLength(21));

    for (final scenario in scenarios) {
      expect((scenario['id'] ?? '').toString(), isNotEmpty);
      expect((scenario['skillId'] ?? '').toString(), scenario['domainId']);
      expect((scenario['question'] ?? '').toString(), isNotEmpty);
      expect(
        (scenario['expectedAnswerFragments'] as List?) ?? const [],
        isNotEmpty,
      );
      expect((scenario['expectedEvents'] as List?) ?? const [], isNotEmpty);
      expect((scenario['expectedToolNames'] as List?) ?? const [], isNotEmpty);
      expect((scenario['alphaMockStream'] as Map?)?['finalAnswer'], isNotEmpty);
      expect(
        (scenario['remoteExpectations'] as Map?)?['answerFragments'],
        isNotEmpty,
      );
      expect((scenario['environments'] as Map?)?['alpha']?['enabled'], isTrue);
      expect((scenario['environments'] as Map?)?['beta']?['enabled'], isTrue);
    }
  });
}
