import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_structured_response_wire.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn.g.dart';

import 'assistant_test_fixture_paths.dart';

void main() {
  test('RunArtifacts 与 assistant_turn 共享 JSON fixture 可 fromJson/toJson 往返', () {
    final runPath = assistantMetadataFixturePath('wire_min_run_artifacts.json');
    final turnPath =
        assistantMetadataFixturePath('wire_min_assistant_turn.json');

    final runJson =
        jsonDecode(File(runPath).readAsStringSync()) as Map<String, dynamic>;
    final run = RunArtifacts.fromJson(runJson);
    expect(run.answerDecision.toWireMap()['_fixtureExtension'], isNotNull);
    expect(run.diagnostics.toWireMap()['_fixtureDiagExtension'], 'retained');
    final adv = run.answerDecisionReadView;
    expect(adv.nextAction, 'answer');
    expect(adv.finalAnswerReady, isTrue);
    expect(adv.evidenceSummary, 'fixture summary');
    final dv = run.diagnosticsReadView;
    expect(dv.domainId, 'fixture.domain');
    expect(dv.evidencePassed, isTrue);
    final runEnc = jsonEncode(run.toJson());
    final round = RunArtifacts.fromJson(jsonDecode(runEnc) as Map<String, dynamic>);
    expect(round.answerDecision.toWireMap()['_fixtureExtension'], isNotNull);

    final turnJson =
        jsonDecode(File(turnPath).readAsStringSync()) as Map<String, dynamic>;
    final turn = AssistantTurnOutput.fromJson(turnJson);
    final turnEnc = jsonEncode(turn.toJson());
    AssistantTurnOutput.fromJson(jsonDecode(turnEnc) as Map<String, dynamic>);
  });

  test('structuredResponse 子树 fixture 可 AssistantStructuredResponseWire 往返', () {
    final path =
        assistantMetadataFixturePath('wire_min_structured_response_subtrees.json');
    final raw =
        jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
    final slice = assistantStructuredWireFromStructuredRoot(raw);
    expect(slice.qualityMetrics['_fixtureExtension'], 'retained');
    expect(slice.decisionParseSuccess, isTrue);
    expect(slice.answerGateReady, isTrue);
    expect(slice.answerGateReasonCode, 'ok');
    expect(slice.dialogueDomainId, 'fixture.domain');
    expect(slice.dialogueRuntime['domainId'], 'fixture.domain');
    expect(slice.uiReferences.length, 1);
    expect(slice.uiReferences.first.url, 'https://example.com');
    final enc = jsonEncode(slice.toJson());
    assistantStructuredWireFromStructuredRoot(
      jsonDecode(enc) as Map<String, dynamic>,
    );
  });
}
