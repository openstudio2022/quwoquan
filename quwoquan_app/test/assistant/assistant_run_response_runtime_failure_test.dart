import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_boundary_outcome.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  test('uses structured assistant boundary outcome when present', () {
    const outcome = AssistantBoundaryOutcome(
      status: AssistantBoundaryStatus.blocked,
      boundary: 'assistant_turn',
      stage: 'stream',
      failure: RuntimeFailure(
        code: 'ASSISTANT.NETWORK.network_unavailable',
        origin: RuntimeFailureOrigin.remoteDependency,
        kind: RuntimeFailureKind.network,
        nature: RuntimeFailureNature.transient,
        location: RuntimeFailureLocation(
          businessObject: 'assistant_turn',
          functionModule: 'remote_entry',
        ),
        context: RuntimeFailureContext(),
      ),
      disruptionLevel: UserDisruptionLevel.inlineCard,
      canContinue: false,
    );

    const response = AssistantRunResponse(
      finalText: '',
      traces: [],
      boundaryOutcome: outcome,
    );

    expect(
      response.assistantBoundaryOutcome?.failure?.code,
      outcome.failure?.code,
    );
    expect(
      ((response.toJson()['structuredResponse']
              as Map)['assistantBoundaryOutcome']
          as Map)['status'],
      'blocked',
    );
  });

  test('current degraded response derives runtime failure facts', () {
    const response = AssistantRunResponse(
      finalText: '',
      traces: [],
      degraded: true,
      errorCode: 'remote_stream_terminal_payload_missing',
    );

    final outcome = response.assistantBoundaryOutcome;

    expect(outcome?.status, AssistantBoundaryStatus.failed);
    expect(
      outcome?.failure?.code,
      'ASSISTANT.SYSTEM.remote_stream_terminal_payload_missing',
    );
    expect(
      outcome?.failure?.context.attributes.single.value,
      'remote_stream_terminal_payload_missing',
    );
  });
}
