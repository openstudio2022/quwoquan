import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_boundary_outcome.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  test('AssistantBoundaryOutcome serializes runtime failure facts', () {
    const outcome = AssistantBoundaryOutcome(
      status: AssistantBoundaryStatus.failed,
      boundary: 'assistant_turn',
      stage: 'stream',
      failure: RuntimeFailure(
        code: 'ASSISTANT.NETWORK.stream_failed',
        origin: RuntimeFailureOrigin.environment,
        kind: RuntimeFailureKind.network,
        nature: RuntimeFailureNature.transient,
        location: RuntimeFailureLocation(
          businessObject: 'assistant_turn',
          functionModule: 'assistant_stream',
        ),
        context: RuntimeFailureContext(
          attributes: <RuntimeContextAttribute>[
            RuntimeContextAttribute(key: 'provider', value: 'local'),
          ],
        ),
      ),
      disruptionLevel: UserDisruptionLevel.inlineCard,
      canContinue: false,
    );

    final parsed = AssistantBoundaryOutcome.fromJson(outcome.toJson());

    expect(parsed.status, AssistantBoundaryStatus.failed);
    expect(parsed.failure?.code, 'ASSISTANT.NETWORK.stream_failed');
    expect(parsed.failure?.context.attributes.single.value, 'local');
  });
}
