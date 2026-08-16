// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-002
// readiness_case: get-research-release-readback-app-local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/research_release_readback_remote.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// sha256("subject")
const _subjectDigest =
    'sha256:a9491f4c1bf7b0cffbadcba2db8f028e4b3f2867cb59e1f3a0bc1968f3c51242';

void main() {
  test(
    'Research readback injects the exact issued attestation into generated header',
    () async {
      final executor = _RecordingExecutor();
      final client = GeneratedCloudOperationClient(executor);
      CloudOperationInvocationContext context(String clientPageId) =>
          CloudOperationInvocationContext(
            surfaceId: 'appShell',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(accountId: 'account-1'),
          );
      final readback = RemoteResearchReleaseReadback(
        client: client,
        researchIdentityWriter: RemoteAccountSessionCommandWriter(
          client: client,
          invocationContext: context,
        ),
        invocationContext: context,
      );

      final view = await readback.readCurrentResearchRelease();

      expect(
        executor.calls.map((call) => call.operation.canonicalOperationId),
        <String>[
          AppCloudOperationIds
              .userAccountSessionIssueWhitelistedResearchSession,
          AppCloudOperationIds.contentPostGetResearchReleaseReadback,
        ],
      );
      expect(executor.calls.first.payload.body, isNull);
      expect(executor.calls.first.payload.headers, isEmpty);
      expect(executor.calls.last.payload.body, isNull);
      expect(executor.calls.last.payload.headers, <String, String>{
        'X-Research-Identity-Attestation': 'opaque-attestation-exact',
      });
      expect(executor.calls.last.context.actor.accountId, 'account-1');
      expect(view.releaseId, 'research-release-1');
      expect(view.signatureVerified, isTrue);
      expect(view.researchBadgeVisible, isTrue);
    },
  );
}

final class _RecordedCall {
  const _RecordedCall(this.operation, this.context, this.payload);

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
    calls.add(_RecordedCall(operation, context, requestEncoder()));
    final response = switch (operation.canonicalOperationId) {
      AppCloudOperationIds.userAccountSessionIssueWhitelistedResearchSession =>
        <String, Object?>{
          'subjectHash': _subjectDigest,
          'attestationId': 'opaque-attestation-exact',
          'expiresAt': '2026-08-12T12:15:00Z',
        },
      AppCloudOperationIds.contentPostGetResearchReleaseReadback =>
        <String, Object?>{
          'releaseId': 'research-release-1',
          'manifestDigest': 'sha256:${'a' * 64}',
          'subjectHash': _subjectDigest,
          'attestationIdHash': 'sha256:${'b' * 64}',
          'signatureVerified': true,
          'researchBadgeVisible': true,
          'postIds': <String>['research-post-1'],
          'entityRefs': <String>['research-entity-1'],
          'mediaAssetIds': <String>['research-media-1'],
          'publicCdnDetected': false,
          'anonymousMediaUrlDetected': false,
        },
      _ => throw StateError('unexpected operation'),
    };
    return responseDecoder(response);
  }
}
