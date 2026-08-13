// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-create-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-confirm-reject/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-confirm-reject/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-confirm-reject/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-confirm-reject/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-apply-audit/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-apply-audit/spec.md#gwt-001.t2
// readiness_case: profile_update_proposal_create_profile_update_proposal_app_api
// readiness_case: profile_update_proposal_confirm_proposal_app_api
// readiness_case: profile_update_proposal_apply_proposal_app_api
// readiness_case: profile_update_proposal_get_profile_update_proposal_app_api
// readiness_case: profile_update_proposal_list_profile_update_proposals_app_api
// readiness_case: profile_update_proposal_reject_proposal_app_api
// readiness_case: profile_update_proposal_rollback_proposal_app_api
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/profile_update_proposal/adapters/profile_update_proposal_remote.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:uuid/uuid.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _gatewayUrl = String.fromEnvironment(
  'CLOUD_GATEWAY_BASE_URL',
  defaultValue: '',
);
const _definedAccessToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const _personaId = String.fromEnvironment('TEST_PERSONA_ID');
const _definedEvidencePath = String.fromEnvironment(
  'PROFILE_PROPOSAL_REMOTE_EVIDENCE_PATH',
);
final _accessToken = _definedAccessToken.trim().isNotEmpty
    ? _definedAccessToken
    : Platform.environment['TEST_AUTH_TOKEN']?.trim() ?? '';
final _evidencePath = _definedEvidencePath.trim().isNotEmpty
    ? _definedEvidencePath
    : Platform.environment['PROFILE_PROPOSAL_REMOTE_EVIDENCE_PATH']?.trim() ??
          '';

final class _GammaProfileProposalClientContext
    implements CloudClientContextProvider {
  const _GammaProfileProposalClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gppi',
      deviceActorId: 'gamma-profile-proposal-device',
      platform: 'test',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

void main() {
  setUpAll(() {
    if (_gatewayUrl.trim().isEmpty ||
        _accessToken.isEmpty ||
        _personaId.trim().isEmpty) {
      fail(
        'Profile proposal Remote API verification requires '
        'CLOUD_GATEWAY_BASE_URL, TEST_AUTH_TOKEN and TEST_PERSONA_ID '
        'from the local Gamma '
        'candidate-bound nonprod phone identity pool.',
      );
    }
  });

  test(
    'generated profile proposal Remote applies and rolls back atomically',
    () async {
      final httpClient = _buildGammaHttpClient();
      final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
        clientContextProvider: const _GammaProfileProposalClientContext(),
      );
      addTearDown(httpClient.close);
      addTearDown(telemetry.dispose);
      final generatedClient = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _GammaProfileProposalClientContext(),
        telemetrySink: telemetry.sink,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_gatewayUrl),
        ),
      );
      final identity = const Uuid().v4();
      final proposalId = 'proposal-$identity';
      final remote = _remoteFor(client: generatedClient, intentId: proposalId);
      final createCommand = CreateProfileUpdateProposalCommand(
        personaId: _personaId,
        proposalId: proposalId,
        source: ProposalSource.assistant,
        reason: 'Gamma Assistant profile proposal verification',
        evidenceRefs: <String>['assistant-run:$identity'],
        impactScope: const <String>['bio'],
        bio: 'Gamma proposal $identity',
      );

      final created = await remote.create(createCommand);
      final createReplay = await remote.create(createCommand);
      final confirmed = await remote.confirm(
        ConfirmProfileUpdateProposalCommand(proposalId: proposalId),
      );
      final applied = await remote.apply(
        ApplyProfileUpdateProposalCommand(proposalId: proposalId),
      );
      final appliedView = await remote.get(
        ProfileUpdateProposalQuery(proposalId: proposalId),
      );
      final rolledBack = await remote.rollback(
        RollbackProfileUpdateProposalCommand(proposalId: proposalId),
      );
      final rollbackReplay = await remote.rollback(
        RollbackProfileUpdateProposalCommand(proposalId: proposalId),
      );
      final rolledBackView = await remote.get(
        ProfileUpdateProposalQuery(proposalId: proposalId),
      );
      final rejectedProposalId = 'proposal-reject-$identity';
      final rejectionRemote = _remoteFor(
        client: generatedClient,
        intentId: rejectedProposalId,
      );
      final rejectedCreated = await rejectionRemote.create(
        CreateProfileUpdateProposalCommand(
          personaId: _personaId,
          proposalId: rejectedProposalId,
          source: ProposalSource.assistant,
          reason: 'Gamma rejected profile proposal verification',
          evidenceRefs: <String>['assistant-run:reject-$identity'],
          impactScope: const <String>['bio'],
          bio: 'Rejected Gamma proposal $identity',
        ),
      );
      final proposals = await rejectionRemote.list(
        ProfileUpdateProposalListQuery(personaId: _personaId, limit: 100),
      );
      final rejected = await rejectionRemote.reject(
        RejectProfileUpdateProposalCommand(proposalId: rejectedProposalId),
      );
      final rejectedView = await rejectionRemote.get(
        ProfileUpdateProposalQuery(proposalId: rejectedProposalId),
      );

      expect(created.status, ProposalStatus.pending);
      expect(createReplay.replayed, isTrue);
      expect(confirmed.status, ProposalStatus.confirmed);
      expect(applied.status, ProposalStatus.applied);
      expect(appliedView.applyAuditId, isNotEmpty);
      expect(appliedView.rollbackDeadline, isNotNull);
      expect(rolledBack.status, ProposalStatus.rolledBack);
      expect(rollbackReplay.replayed, isTrue);
      expect(rolledBackView.status, ProposalStatus.rolledBack);
      expect(rolledBackView.rollbackAuditId, isNotEmpty);
      expect(rejectedCreated.status, ProposalStatus.pending);
      expect(
        proposals.items.map((item) => item.id),
        contains(rejectedProposalId),
      );
      expect(rejected.status, ProposalStatus.rejected);
      expect(rejectedView.status, ProposalStatus.rejected);
      expect(
        rejectedView.reason,
        'Gamma rejected profile proposal verification',
      );
      final telemetryEvents = await telemetry.waitForEvents(minimumCount: 12);
      expect(telemetryEvents.every((event) => event.succeeded), isTrue);
      for (final operationId in <String>[
        AppCloudOperationIds
            .userProfileUpdateProposalListProfileUpdateProposals,
        AppCloudOperationIds.userProfileUpdateProposalRejectProposal,
      ]) {
        final matching = telemetryEvents.where(
          (event) => event.canonicalOperationId == operationId,
        );
        expect(matching, isNotEmpty, reason: operationId);
        expect(
          matching.every(
            (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
          ),
          isTrue,
          reason: operationId,
        );
      }

      await _writeRemoteEvidence(<String, Object?>{
        'schema': 'profile-proposal-remote-api-evidence',
        'status': 'passed',
        'proposalId': proposalId,
        'createReplayed': createReplay.replayed,
        'applyAuditId': appliedView.applyAuditId,
        'rollbackAuditId': rolledBackView.rollbackAuditId,
        'rollbackReplayed': rollbackReplay.replayed,
        'finalStatus': rolledBackView.status.name,
        'operations': telemetryEvents
            .map(
              (event) => <String, Object?>{
                'operationId': event.canonicalOperationId,
                'requestId': event.requestId,
                'traceId': event.traceId,
                'succeeded': event.succeeded,
              },
            )
            .toList(growable: false),
      });

      final invalidHttpClient = CloudHttpClient(
        authTokenProvider: const _StaticTokenProvider(
          'invalid-profile-proposal-api-token',
        ),
      );
      addTearDown(invalidHttpClient.close);
      final invalidRemote = _remoteFor(
        client: buildGeneratedCloudOperationClient(
          httpClient: invalidHttpClient,
          clientContextProvider: const _GammaProfileProposalClientContext(),
          telemetrySink: telemetry.sink,
          environment: CloudRuntimeEnvironment(
            environment: CloudEnvironment.gamma,
            gatewayBaseUri: Uri.parse(_gatewayUrl),
          ),
        ),
        intentId: 'unauthorized-$identity',
      );
      await _expectCanonicalAuthFailure(
        invalidRemote.list(
          ProfileUpdateProposalListQuery(personaId: _personaId, limit: 1),
        ),
        AppCloudOperationIds
            .userProfileUpdateProposalListProfileUpdateProposals,
      );
      await _expectCanonicalAuthFailure(
        invalidRemote.reject(
          RejectProfileUpdateProposalCommand(proposalId: rejectedProposalId),
        ),
        AppCloudOperationIds.userProfileUpdateProposalRejectProposal,
      );
    },
  );
}

Future<void> _expectCanonicalAuthFailure(
  Future<Object?> request,
  String operationId,
) => expectLater(
  request,
  throwsA(
    isA<CloudException>()
        .having(
          (error) => error.sourceOperationId,
          'sourceOperationId',
          operationId,
        )
        .having((error) => error.statusCode, 'statusCode', anyOf(401, 403))
        .having(
          (error) => error.code,
          'canonical code',
          matches(
            RegExp(r'^[A-Z0-9_]+\.(USER|SYSTEM|MIDDLEWARE)\.[a-z0-9_]+$'),
          ),
        ),
  ),
);

RemoteProfileUpdateProposalFacet _remoteFor({
  required GeneratedCloudOperationClient client,
  required String intentId,
}) => RemoteProfileUpdateProposalFacet(
  client: client,
  invocationContext: (clientPageId, {required command}) {
    final surface =
        clientPageId == UserRequestPageIds.createProfileUpdateProposal
        ? AppUiSurfaces.personalAssistantDialog
        : AppUiSurfaces.profileEdit;
    return CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      actor: const CloudOperationActorContext(
        personaId: _personaId,
        deviceActorId: 'gamma-profile-proposal-device',
      ),
      idempotencyKey: command ? '$intentId:$clientPageId' : null,
    );
  },
);

Future<void> _writeRemoteEvidence(Map<String, Object?> evidence) async {
  if (_evidencePath.isEmpty) return;
  final output = File(_evidencePath);
  await output.parent.create(recursive: true);
  await output.writeAsString('${jsonEncode(evidence)}\n');
}

CloudHttpClient _buildGammaHttpClient() =>
    CloudHttpClient(authTokenProvider: _StaticTokenProvider(_accessToken));

final class _StaticTokenProvider implements CloudAuthTokenProvider {
  const _StaticTokenProvider(this.token);

  final String token;

  @override
  Future<String?> getAccessToken() async => token;
}
