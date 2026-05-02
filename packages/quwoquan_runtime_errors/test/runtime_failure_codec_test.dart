import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:test/test.dart';

void main() {
  test('RuntimeErrorResponse round trips string context attributes', () {
    const failure = RuntimeFailure(
      code: 'ASSISTANT.MIDDLEWARE.llm_timeout',
      origin: RuntimeFailureOrigin.remoteDependency,
      kind: RuntimeFailureKind.timeout,
      nature: RuntimeFailureNature.transient,
      location: RuntimeFailureLocation(
        businessObject: 'assistant_turn',
        functionModule: 'llm_client',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'downstreamStatus', value: '504'),
        ],
      ),
    );
    const response = RuntimeErrorResponse(
      failure: failure,
      requestId: 'request-1',
      traceId: 'trace-1',
    );

    final parsed = RuntimeErrorResponse.fromJson(response.toJson());

    expect(parsed.failure.code, failure.code);
    expect(parsed.failure.location.businessObject, 'assistant_turn');
    expect(parsed.failure.context.attributes.single.value, '504');
  });

  test('missing context defaults to empty attributes', () {
    final response = RuntimeErrorResponse.fromJson(<String, dynamic>{
      'code': 'CLOUD.SYSTEM.unknown_error',
      'origin': 'system',
      'kind': 'internal',
      'nature': 'bug',
      'location': <String, dynamic>{
        'businessObject': 'cloud_request',
        'functionModule': 'mapper',
      },
    });

    expect(response.failure.context.attributes, isEmpty);
  });

  test('current response normalizes details-free runtime failure', () {
    final response = RuntimeErrorResponse.fromCurrentJson(<String, dynamic>{
      'code': 'ASSISTANT.MIDDLEWARE.llm_timeout',
      'kind': 'MIDDLEWARE',
      'module': 'ASSISTANT',
      'reason': 'llm_timeout',
      'requestId': 'request-1',
      'traceId': 'trace-1',
    });

    expect(response.failure.origin, RuntimeFailureOrigin.remoteDependency);
    expect(response.failure.kind, RuntimeFailureKind.timeout);
    expect(response.failure.context.attributes, hasLength(2));
  });

  test('default recovery retries transient failures with remaining budget', () {
    const policy = DefaultRuntimeRecoveryPolicy();
    final decision = policy.decide(
      const RuntimeFailure(
        code: 'APP.NETWORK.offline',
        origin: RuntimeFailureOrigin.environment,
        kind: RuntimeFailureKind.network,
        nature: RuntimeFailureNature.transient,
        location: RuntimeFailureLocation(
          businessObject: 'app_request',
          functionModule: 'network_client',
        ),
        context: RuntimeFailureContext(),
      ),
      const EntryContext(
        kind: 'appPage',
        entryId: 'page-1',
        actorType: 'user',
        actorId: 'user-1',
        surfaceId: 'assistant.chat',
      ),
      const BoundaryContext(boundary: 'http', remainingBudget: 1),
    );

    expect(decision.action, RuntimeRecoveryAction.retry);
  });
}
