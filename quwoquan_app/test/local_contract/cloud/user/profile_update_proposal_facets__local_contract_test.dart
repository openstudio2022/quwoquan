import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/remote/user/profile_update_proposal/profile_update_proposal_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('ProfileUpdateProposal Remote uses generated command ABI', () async {
    final executor = _RecordingExecutor(response: _commandResult());
    final remote = RemoteProfileUpdateProposalFacet(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId, {required command}) =>
          CloudOperationInvocationContext(
            surfaceId: 'personalAssistantDialog',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
            idempotencyKey: command ? 'idem-1' : null,
          ),
    );

    final result = await remote.create(
      CreateProfileUpdateProposalCommand(
        personaId: 'persona-1',
        proposalId: 'proposal-1',
        source: ProfileUpdateProposalSource.assistant,
        changes: ProfileChangeSet(
          displayName: 'new name',
          avatarMediaAssetId: 'asset-1',
        ),
      ),
    );

    expect(result.proposalId, 'proposal-1');
    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.userProfileUpdateProposalCreateProfileUpdateProposal,
    );
    expect(executor.pathParameters, <String, String>{'personaId': 'persona-1'});
    expect(executor.body, <String, Object?>{
      'proposalId': 'proposal-1',
      'source': 'assistant',
      'displayName': 'new name',
      'avatarMediaAssetId': 'asset-1',
    });
    expect(executor.body, isNot(contains('actor')));
    expect(executor.body, isNot(contains('subAccountId')));
    expect(executor.body, isNot(contains('media')));
  });

  test('ProfileUpdateProposal list is a strict typed Reader slice', () async {
    final executor = _RecordingExecutor(
      response: <String, Object?>{
        'items': <Object?>[_proposalView()],
        'nextCursor': 'cursor-2',
      },
    );
    final remote = RemoteProfileUpdateProposalFacet(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId, {required command}) =>
          CloudOperationInvocationContext(
            surfaceId: 'profileEdit',
            clientPageId: clientPageId,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
          ),
    );

    final page = await remote.list(
      ProfileUpdateProposalListQuery(
        personaId: 'persona-1',
        cursor: 'cursor-1',
        limit: 30,
      ),
    );

    expect(page.items.single.status, ProfileUpdateProposalStatus.pending);
    expect(page.items.single.changes.displayName, 'new name');
    expect(page.nextCursor, 'cursor-2');
    expect(executor.queryParameters, <String, String>{
      'cursor': 'cursor-1',
      'limit': '30',
    });
    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.userProfileUpdateProposalListProfileUpdateProposals,
    );
  });

  test('ProfileUpdateProposal contract rejects legacy dynamic aliases', () {
    expect(() => ProfileChangeSet(), throwsArgumentError);
    expect(
      () => ProfileChangeSet(isolationLevel: 'legacy'),
      throwsArgumentError,
    );
    expect(
      () => decodeProfileUpdateProposalView(
        _proposalView()
          ..remove('personaId')
          ..['subAccountId'] = 'legacy-persona',
      ),
      throwsFormatException,
    );
    expect(
      () => decodeProfileUpdateProposalView(
        _proposalView()
          ..['displayName'] = null
          ..['bio'] = null,
      ),
      throwsFormatException,
    );
    expect(
      () => decodeProfileUpdateProposalView(<Object?, Object?>{
        1: 'non-string-key',
      }),
      throwsFormatException,
    );
    expect(
      () => decodeProfileUpdateProposalView(
        _proposalView()
          ..['updates'] = <Object?>[
            <String, Object?>{'path': 'displayName', 'newValue': 'dynamic'},
          ],
      ),
      throwsFormatException,
    );
    final confirmPayload = encodeConfirmProfileUpdateProposalCommand(
      ConfirmProfileUpdateProposalCommand(proposalId: 'proposal-1'),
    );
    expect(confirmPayload.body, isNull);
    expect(
      () => decodeProfileUpdateProposalView(
        _proposalView()..['targetPersonaExpectedVersion'] = 1,
      ),
      throwsFormatException,
    );
  });
}

Map<String, Object?> _commandResult() => <String, Object?>{
  'proposalId': 'proposal-1',
  'version': 1,
  'status': 'pending',
  'replayed': false,
};

Map<String, Object?> _proposalView() => <String, Object?>{
  'id': 'proposal-1',
  'personaId': 'persona-1',
  'source': 'assistant',
  'status': 'pending',
  'displayName': 'new name',
  'bio': null,
  'avatarMediaAssetId': null,
  'backgroundMediaAssetId': null,
  'isPrivate': null,
  'isolationLevel': null,
  'purposeHint': null,
  'reviewedBy': null,
  'version': 1,
  'createdAt': '2026-07-16T01:00:00Z',
  'updatedAt': '2026-07-16T01:00:00Z',
  'resolvedAt': null,
};

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  Map<String, String> pathParameters = const <String, String>{};
  Map<String, String> queryParameters = const <String, String>{};
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    final payload = requestEncoder();
    pathParameters = payload.pathParameters;
    queryParameters = payload.queryParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}
