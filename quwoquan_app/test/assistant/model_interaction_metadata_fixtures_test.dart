import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';

import 'assistant_test_fixture_paths.dart';

void main() {
  test('run_artifacts metadata fixture loads and preserves partitioned extensions', () {
    final ra = assistantLoadRunArtifactsFixture('wire_min_run_artifacts.json');
    expect(ra.answerDecision.extensions['_fixtureExtension'], isNotNull);
    expect(ra.diagnostics.extensions['_fixtureDiagExtension'], 'retained');
    final roundTrip = RunArtifacts.fromJson(
      Map<String, dynamic>.from(ra.toJson()),
    );
    expect(
      roundTrip.answerDecision.toWireMap(),
      ra.answerDecision.toWireMap(),
    );
  });

  test('LlmParseResult.tryAssistantTurnOutput 与 metadata fixture + canonical 契约一致', () {
    final path = assistantMetadataFixturePath('wire_min_assistant_turn.json');
    final map = jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
    map['contractId'] = 'assistant_turn';
    map['decision'] = <String, dynamic>{'nextAction': 'answer'};
    final expected = AssistantTurnOutput.fromJson(map);
    final parsed = LlmResponseParser.parse(jsonEncode(map));
    expect(parsed.ok, isTrue);
    expect(parsed.tryAssistantTurnOutput()?.toJson(), expected.toJson());
  });
}
