import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';

import 'assistant_test_fixture_paths.dart';

void main() {
  test('answerDecision stable/extension partition round-trips', () {
    const full = <String, dynamic>{
      'nextAction': 'answer',
      '_fixtureExtension': <String, dynamic>{'keep': true},
    };
    final s = RunArtifactsMapPartition.answerDecisionStable(full);
    final x = RunArtifactsMapPartition.answerDecisionExtension(full);
    expect(s['nextAction'], 'answer');
    expect(x['_fixtureExtension'], isNotNull);
    final merged = RunArtifactsMapPartition.mergeSlices(s, x);
    expect(merged['nextAction'], 'answer');
    expect(merged['_fixtureExtension'], isNotNull);
  });

  test('RunArtifacts.fromJson preserves extension keys on maps', () {
    final ra = RunArtifacts.fromJson(<String, dynamic>{
      'answerDecision': <String, dynamic>{
        'nextAction': 'answer',
        'custom': 1,
      },
    });
    final ext = RunArtifactsMapPartition.answerDecisionExtension(
      ra.answerDecision.toWireMap(),
    );
    expect(ext['custom'], 1);
  });

  test('metadata wire_min_run_artifacts.json partitions answerDecision', () {
    final raFixture = assistantLoadRunArtifactsFixture('wire_min_run_artifacts.json');
    final adv = raFixture.answerDecision.toWireMap();
    final stable = RunArtifactsMapPartition.answerDecisionStable(adv);
    final ext = RunArtifactsMapPartition.answerDecisionExtension(adv);
    expect(stable['nextAction'], 'answer');
    expect(ext['_fixtureExtension'], isNotNull);
    expect(
      RunArtifactsMapPartition.mergeSlices(stable, ext)['nextAction'],
      'answer',
    );
    expect(raFixture.answerDecision.core.nextAction, 'answer');
  });
}
