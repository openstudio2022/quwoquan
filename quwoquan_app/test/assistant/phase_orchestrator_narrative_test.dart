import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_orchestrator.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

class _NoopPhase implements Phase {
  const _NoopPhase(this.phaseId);

  @override
  final String phaseId;

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    return PhaseOutput(state: input.state);
  }
}

void main() {
  test('PhaseOrchestrator 为 phase 发用户态 narrative', () async {
    final traces = <AssistantTraceEvent>[];
    final orchestrator = PhaseOrchestrator(
      phases: const <Phase>[
        _NoopPhase('understand'),
        _NoopPhase('retrieval_design'),
        _NoopPhase('execution'),
      ],
    );

    await orchestrator.run(
      PhaseOrchestratorInput(
        request: const <String, dynamic>{},
        runId: 'run_1',
        traceId: 'trace_1',
        onTraceEvent: (event) {
          if (event is AssistantTraceEvent) {
            traces.add(event);
          }
        },
      ),
    );

    final narratives = traces
        .where((event) => event.type == AssistantTraceEventType.lifecycleStart)
        .map((event) => (event.data?['phaseId'] as String?) ?? '')
        .toList(growable: false);
    expect(narratives, containsAll(<String>[
      'bootstrap',
      'understand',
      'retrieval_design',
      'execution',
    ]));
  });
}
