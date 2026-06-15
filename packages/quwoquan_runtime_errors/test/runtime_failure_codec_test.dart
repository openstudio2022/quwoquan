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
      recovery: RuntimeRecoveryDirective(
        action: 'retry',
        afterSeconds: 5,
        disruptionLevel: 'snackbar',
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
    expect(parsed.failure.recovery.action, 'retry');
    expect(parsed.failure.recovery.afterSeconds, 5);
    expect(parsed.failure.recovery.disruptionLevel, 'snackbar');
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

  test('downlinked recovery directive is parsed from response body', () {
    final response = RuntimeErrorResponse.fromJson(<String, dynamic>{
      'code': 'USER.AUTH.otp_rate_limited',
      'origin': 'user',
      'kind': 'rateLimited',
      'nature': 'permanent',
      'userMessage': '发送过于频繁，请稍后再试',
      'recovery': <String, dynamic>{
        'action': 'retry',
        'afterSeconds': 42,
        'disruptionLevel': 'snackbar',
      },
    });

    expect(response.failure.recovery.isPresent, isTrue);
    expect(response.failure.recovery.action, 'retry');
    expect(response.failure.recovery.afterSeconds, 42);
    expect(response.failure.recovery.disruptionLevel, 'snackbar');
  });

  test('policy consumes downlinked recovery over nature derivation', () {
    const policy = DefaultRuntimeRecoveryPolicy();
    final decision = policy.decide(
      const RuntimeFailure(
        code: 'USER.AUTH.otp_rate_limited',
        origin: RuntimeFailureOrigin.user,
        kind: RuntimeFailureKind.rateLimited,
        nature: RuntimeFailureNature.permanent,
        location: RuntimeFailureLocation(
          businessObject: 'cloud_request',
          functionModule: 'auth',
        ),
        context: RuntimeFailureContext(),
        recovery: RuntimeRecoveryDirective(
          action: 'retry',
          afterSeconds: 60,
          disruptionLevel: 'snackbar',
        ),
      ),
      const EntryContext(
        kind: 'appPage',
        entryId: 'login',
        actorType: 'user',
        actorId: 'user-1',
        surfaceId: 'user.login',
      ),
      const BoundaryContext(boundary: 'http', remainingBudget: 0),
    );

    expect(decision.action, RuntimeRecoveryAction.retry);
    expect(decision.disruptionLevel, UserDisruptionLevel.snackbar);
    expect(decision.policyId, 'downlink.recovery');
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
