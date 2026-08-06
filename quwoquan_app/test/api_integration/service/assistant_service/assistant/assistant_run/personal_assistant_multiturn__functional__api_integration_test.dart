// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';

import '../../../../../support/service/assistant_service/assistant/assistant_run/assistant_run_remote_api_harness.dart';

void main() {
  test('找私助 beta Remote 多轮上下文 API integration', () async {
    final harness = await AssistantRunRemoteApiHarness.fromEnvironment(
      allowedEnvironments: const {CloudEnvironment.beta},
    );
    addTearDown(harness.close);

    final first = await harness.execute('Shen zhen tian qi');
    expect(first.run.status, 'completed');
    expect(first.snapshot.failure, isNull);
    expect(first.answer, contains('深圳'));
    expect(first.searchedDocumentCount, greaterThanOrEqualTo(1));

    final second = await harness.execute(
      '剩下2天有什么外出推荐，四口之家',
      sessionId: first.sessionId,
    );
    expect(second.sessionId, first.sessionId);
    expect(second.run.status, 'completed');
    expect(second.snapshot.failure, isNull);
    expect(second.answer, isNotEmpty);
    expect(second.searchedDocumentCount, greaterThanOrEqualTo(1));
    expect(second.acceptedDocumentCount, greaterThanOrEqualTo(1));
    expect(second.acceptedReferences, isNotEmpty);
    expect(
      second.acceptedReferences.first.destination.url,
      startsWith('https://'),
    );

    final turns = await harness.composition.listSessionTurns(
      sessionId: first.sessionId,
    );
    expect(
      turns.items.length,
      greaterThanOrEqualTo(2),
      reason: '第二轮必须由同一 Remote session 的 durable turn history 续接',
    );
    expect(
      turns.items.map((turn) => turn.inputText),
      containsAll(<String>['Shen zhen tian qi', '剩下2天有什么外出推荐，四口之家']),
    );
    expect(
      second.eventTypes,
      everyElement(
        isIn(<String>[
          'run_started',
          'process_replace',
          'process_append',
          'process_commit',
          'answer_delta',
          'run_state_changed',
          'task_graph_patch',
          'checkpoint_committed',
          'presentation_snapshot',
          'presentation_patch',
          'presentation_commit',
          'waiting_input',
          'waiting_approval',
          'completed',
          'failed',
          'cancelled',
        ]),
      ),
    );
    for (final event in second.events) {
      expect(event.payload.containsKey('debugTrace'), isFalse);
      expect(event.payload.containsKey('reasoning'), isFalse);
      expect(event.payload.containsKey('toolUse'), isFalse);
      expect(event.payload.containsKey('toolInput'), isFalse);
    }
  });
}
