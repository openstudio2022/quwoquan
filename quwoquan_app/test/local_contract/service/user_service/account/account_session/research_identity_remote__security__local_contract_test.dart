// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
// readiness_case: issue-whitelisted-research-session-app-local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// sha256("subject")
const _subjectDigest =
    'sha256:a9491f4c1bf7b0cffbadcba2db8f028e4b3f2867cb59e1f3a0bc1968f3c51242';

void main() {
  test(
    'Research session uses generated operation and cannot spoof accountId',
    () async {
      final executor = _RecordingExecutor();
      final writer = RemoteAccountSessionCommandWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: 'appShell',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(accountId: 'account-real'),
        ),
      );

      final session = await writer.issueWhitelistedResearchSession(
        const IssueWhitelistedResearchSessionCommand(),
      );

      expect(executor.calls, hasLength(1));
      final call = executor.calls.single;
      expect(
        call.operation.canonicalOperationId,
        AppCloudOperationIds.userAccountSessionIssueWhitelistedResearchSession,
      );
      expect(call.payload.body, isNull);
      expect(call.payload.pathParameters, isEmpty);
      expect(call.payload.queryParameters, isEmpty);
      expect(call.payload.headers, isEmpty);
      expect(call.context.actor.accountId, 'account-real');
      expect(
        call.context.clientPageId,
        'user.issue.whitelisted.research.session',
      );
      expect(session.subjectHash, _subjectDigest);
      expect(session.attestationId, 'opaque-signed-attestation');
      expect(session.attestationId, isNot(contains('account-real')));
    },
  );
}

final class _RecordedCall {
  const _RecordedCall({
    required this.operation,
    required this.context,
    required this.payload,
  });

  final CloudOperationContract operation;
  final CloudOperationInvocationContext context;
  final CloudOperationRequestPayload payload;
}

final class _RecordingExecutor implements CloudOperationExecutor {
  final List<_RecordedCall> calls = <_RecordedCall>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    calls.add(
      _RecordedCall(
        operation: operation,
        context: context,
        payload: requestEncoder(),
      ),
    );
    return responseDecoder(<String, Object?>{
      'subjectHash': _subjectDigest,
      'attestationId': 'opaque-signed-attestation',
      'expiresAt': '2026-08-12T12:15:00Z',
    });
  }
}
