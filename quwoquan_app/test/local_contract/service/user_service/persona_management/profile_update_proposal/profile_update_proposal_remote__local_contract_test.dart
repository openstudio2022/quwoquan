// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-create-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-confirm-reject/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-apply-audit/spec.md#gwt-001
// readiness_case: profile_update_proposal_create_profile_update_proposal_app_local
// readiness_case: profile_update_proposal_confirm_proposal_app_local
// readiness_case: profile_update_proposal_apply_proposal_app_local
// readiness_case: profile_update_proposal_reject_proposal_app_local
// readiness_case: profile_update_proposal_rollback_proposal_app_local
// readiness_case: profile_update_proposal_get_profile_update_proposal_app_local
// readiness_case: profile_update_proposal_list_profile_update_proposals_app_local
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/profile_update_proposal/adapters/profile_update_proposal_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  test('ProfileUpdateProposal 七项 Remote 只经 generated HTTP contract', () async {
    final requests = <CapturedRemoteApiPathRequest>[];
    final remote = RemoteProfileUpdateProposalFacet(
      client: buildRemoteApiPathOperationClient(
        requests,
        responseFor: _responseFor,
      ),
      invocationContext: _invocationContext,
    );

    final created = await remote.create(
      CreateProfileUpdateProposalCommand(
        personaId: ' persona-1 ',
        proposalId: ' proposal-1 ',
        source: ProposalSource.assistant,
        displayName: '新的展示名',
        reason: ' assistant evidence ',
        evidenceRefs: const <String>['assistant-run:run-1'],
        impactScope: const <String>['displayName'],
      ),
    );
    final confirmed = await remote.confirm(
      ConfirmProfileUpdateProposalCommand(proposalId: ' proposal-1 '),
    );
    final applied = await remote.apply(
      ApplyProfileUpdateProposalCommand(proposalId: ' proposal-1 '),
    );
    final rejected = await remote.reject(
      RejectProfileUpdateProposalCommand(proposalId: ' proposal-1 '),
    );
    final rolledBack = await remote.rollback(
      RollbackProfileUpdateProposalCommand(proposalId: ' proposal-1 '),
    );
    final proposal = await remote.get(
      ProfileUpdateProposalQuery(proposalId: ' proposal-1 '),
    );
    final page = await remote.list(
      ProfileUpdateProposalListQuery(
        personaId: ' persona-1 ',
        cursor: ' cursor-1 ',
        limit: 30,
      ),
    );

    expect(created.status, ProposalStatus.pending);
    expect(confirmed.status, ProposalStatus.confirmed);
    expect(applied.status, ProposalStatus.applied);
    expect(rejected.status, ProposalStatus.rejected);
    expect(rolledBack.status, ProposalStatus.rolledBack);
    expect(proposal.id, 'proposal-1');
    expect(proposal.displayName, '新的展示名');
    expect(proposal.reason, 'assistant evidence');
    expect(proposal.evidenceRefs, <String>['assistant-run:run-1']);
    expect(proposal.impactScope, <String>['displayName']);
    expect(page.items.single.id, 'proposal-1');
    expect(page.items.single.reason, 'assistant evidence');
    expect(page.nextCursor, 'cursor-2');
    expect(requests, hasLength(7));

    final byOperation = <String, CapturedRemoteApiPathRequest>{
      for (final request in requests)
        _requiredHeader(request.headers, 'X-Client-Operation-Id'): request,
    };

    _expectRequest(
      byOperation[AppCloudOperationIds
          .userProfileUpdateProposalCreateProfileUpdateProposal]!,
      operationId: AppCloudOperationIds
          .userProfileUpdateProposalCreateProfileUpdateProposal,
      method: 'POST',
      path: '/user/personas/persona-1/profile-proposals',
      clientPageId: UserRequestPageIds.createProfileUpdateProposal,
      surfaceId: AppUiSurfaces.personalAssistantDialog.id,
      idempotencyKey: _commandIdempotencyKey,
      body: const <String, Object?>{
        'proposalId': 'proposal-1',
        'source': 'assistant',
        'displayName': '新的展示名',
        'reason': 'assistant evidence',
        'evidenceRefs': <String>['assistant-run:run-1'],
        'impactScope': <String>['displayName'],
      },
    );
    _expectRequest(
      byOperation[AppCloudOperationIds
          .userProfileUpdateProposalConfirmProposal]!,
      operationId:
          AppCloudOperationIds.userProfileUpdateProposalConfirmProposal,
      method: 'POST',
      path: '/user/profile/proposals/proposal-1/confirm',
      clientPageId: UserRequestPageIds.confirmProposal,
      surfaceId: AppUiSurfaces.profileEdit.id,
      idempotencyKey: _commandIdempotencyKey,
    );
    _expectRequest(
      byOperation[AppCloudOperationIds.userProfileUpdateProposalApplyProposal]!,
      operationId: AppCloudOperationIds.userProfileUpdateProposalApplyProposal,
      method: 'POST',
      path: '/user/profile/proposals/proposal-1/apply',
      clientPageId: UserRequestPageIds.applyProposal,
      surfaceId: AppUiSurfaces.profileEdit.id,
      idempotencyKey: _commandIdempotencyKey,
    );
    _expectRequest(
      byOperation[AppCloudOperationIds
          .userProfileUpdateProposalRejectProposal]!,
      operationId: AppCloudOperationIds.userProfileUpdateProposalRejectProposal,
      method: 'POST',
      path: '/user/profile/proposals/proposal-1/reject',
      clientPageId: UserRequestPageIds.rejectProposal,
      surfaceId: AppUiSurfaces.profileEdit.id,
      idempotencyKey: _commandIdempotencyKey,
    );
    _expectRequest(
      byOperation[AppCloudOperationIds
          .userProfileUpdateProposalRollbackProposal]!,
      operationId:
          AppCloudOperationIds.userProfileUpdateProposalRollbackProposal,
      method: 'POST',
      path: '/user/profile/proposals/proposal-1/rollback',
      clientPageId: UserRequestPageIds.rollbackProposal,
      surfaceId: AppUiSurfaces.profileEdit.id,
      idempotencyKey: _commandIdempotencyKey,
    );
    _expectRequest(
      byOperation[AppCloudOperationIds
          .userProfileUpdateProposalGetProfileUpdateProposal]!,
      operationId: AppCloudOperationIds
          .userProfileUpdateProposalGetProfileUpdateProposal,
      method: 'GET',
      path: '/user/profile/proposals/proposal-1',
      clientPageId: UserRequestPageIds.getProfileUpdateProposal,
      surfaceId: AppUiSurfaces.profileEdit.id,
    );
    _expectRequest(
      byOperation[AppCloudOperationIds
          .userProfileUpdateProposalListProfileUpdateProposals]!,
      operationId: AppCloudOperationIds
          .userProfileUpdateProposalListProfileUpdateProposals,
      method: 'GET',
      path: '/user/personas/persona-1/profile-proposals',
      clientPageId: UserRequestPageIds.listProfileUpdateProposals,
      surfaceId: AppUiSurfaces.profileEdit.id,
      query: const <String, String>{'cursor': 'cursor-1', 'limit': '30'},
    );
  });
}

const _commandIdempotencyKey = 'profile-proposal-intent-1';

CloudOperationInvocationContext _invocationContext(
  String clientPageId, {
  required bool command,
}) {
  final surface = clientPageId == UserRequestPageIds.createProfileUpdateProposal
      ? AppUiSurfaces.personalAssistantDialog
      : AppUiSurfaces.profileEdit;
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: 'account-1',
      personaId: 'persona-1',
    ),
    idempotencyKey: command ? _commandIdempotencyKey : null,
  );
}

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'POST' &&
      path == '/user/personas/persona-1/profile-proposals') {
    return remoteApiPathJsonResponse(_commandResult('pending', version: 1));
  }
  if (request.method == 'POST' &&
      path == '/user/profile/proposals/proposal-1/confirm') {
    return remoteApiPathJsonResponse(_commandResult('confirmed', version: 2));
  }
  if (request.method == 'POST' &&
      path == '/user/profile/proposals/proposal-1/apply') {
    return remoteApiPathJsonResponse(_commandResult('applied', version: 3));
  }
  if (request.method == 'POST' &&
      path == '/user/profile/proposals/proposal-1/reject') {
    return remoteApiPathJsonResponse(_commandResult('rejected', version: 2));
  }
  if (request.method == 'POST' &&
      path == '/user/profile/proposals/proposal-1/rollback') {
    return remoteApiPathJsonResponse(_commandResult('rolled_back', version: 4));
  }
  if (request.method == 'GET' && path == '/user/profile/proposals/proposal-1') {
    return remoteApiPathJsonResponse(_proposalView(status: 'confirmed'));
  }
  if (request.method == 'GET' &&
      path == '/user/personas/persona-1/profile-proposals') {
    return remoteApiPathJsonResponse(<String, Object?>{
      'items': <Object?>[_proposalView()],
      'nextCursor': 'cursor-2',
    });
  }
  return remoteApiPathJsonResponse(<String, Object?>{
    'error': 'unexpected request',
  }, statusCode: 500);
}

Map<String, Object?> _commandResult(String status, {required int version}) =>
    <String, Object?>{
      'proposalId': 'proposal-1',
      'version': version,
      'status': status,
      'replayed': false,
    };

Map<String, Object?> _proposalView({String status = 'pending'}) =>
    <String, Object?>{
      'id': 'proposal-1',
      'personaId': 'persona-1',
      'source': 'assistant',
      'reason': 'assistant evidence',
      'evidenceRefs': <String>['assistant-run:run-1'],
      'impactScope': <String>['displayName'],
      'createdBy': 'persona-1',
      'status': status,
      'displayName': '新的展示名',
      'bio': null,
      'avatarMediaAssetId': null,
      'backgroundMediaAssetId': null,
      'isPrivate': null,
      'isolationLevel': null,
      'purposeHint': null,
      'reviewedBy': null,
      'applyAuditId': null,
      'rollbackDeadline': null,
      'rollbackAuditId': null,
      'version': 2,
      'createdAt': '2026-08-08T00:00:00Z',
      'updatedAt': '2026-08-08T00:01:00Z',
      'resolvedAt': null,
    };

void _expectRequest(
  CapturedRemoteApiPathRequest request, {
  required String operationId,
  required String method,
  required String path,
  required String clientPageId,
  required String surfaceId,
  String? idempotencyKey,
  Map<String, Object?> body = const <String, Object?>{},
  Map<String, String> query = const <String, String>{},
}) {
  expect(request.method, method);
  expect(request.path, path);
  expect(request.query, query);
  expect(request.body, body);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: surfaceId,
    operationId: operationId,
  );
  expect(
    _requiredHeader(request.headers, 'Authorization'),
    'Bearer integration-contract-token',
  );
  final actualIdempotencyKey = _header(request.headers, 'Idempotency-Key');
  if (idempotencyKey == null) {
    expect(actualIdempotencyKey, isNull);
  } else {
    expect(actualIdempotencyKey, idempotencyKey);
  }
}

String _requiredHeader(Map<String, String> headers, String name) {
  final value = _header(headers, name);
  if (value == null || value.isEmpty) {
    throw StateError('missing header $name');
  }
  return value;
}

String? _header(Map<String, String> headers, String name) {
  final normalized = name.toLowerCase();
  for (final entry in headers.entries) {
    if (entry.key.toLowerCase() == normalized) {
      return entry.value;
    }
  }
  return null;
}
