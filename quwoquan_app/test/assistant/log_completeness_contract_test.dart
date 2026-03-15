import 'dart:io';

import 'package:test/test.dart';

void main() {
  test(
    'log payload includes routing, retrieval rounds and proposal lifecycle',
    () {
      final file = File(
        'lib/assistant/conversation/orchestration/agent_loop.dart',
      );
      expect(file.existsSync(), isTrue);
      final text = file.readAsStringSync();
      for (final key in const <String>[
        'domainRouting',
        'candidateDomains',
        'domainScores',
        'selectedDomains',
        'retrievalRounds',
        'singleTopic',
        'profileProposalLifecycle',
        'proposalStatus',
        'idempotencyKey',
        'sensitiveBoundary',
      ]) {
        expect(text.contains(key), isTrue, reason: 'missing log key: $key');
      }
    },
  );
}
