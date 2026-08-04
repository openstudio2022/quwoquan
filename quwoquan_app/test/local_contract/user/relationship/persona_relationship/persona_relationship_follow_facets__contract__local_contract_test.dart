// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/user/relationship/persona_relationship/adapters/persona_relationship_follow_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('关注命令与关系列表只经 generated client 并保留 source surface', () async {
    final executor = _RecordingExecutor();
    final contextOperationIds = <String>[];
    final adapter = RemotePersonaRelationshipFollowAdapter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId, canonicalOperationId) {
        contextOperationIds.add(canonicalOperationId);
        return CloudOperationInvocationContext(
          surfaceId: 'userProfile',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'account-1',
            personaId: 'persona-1',
          ),
          idempotencyKey: 'contract-$canonicalOperationId',
        );
      },
    );

    await adapter.follow('persona-2', sourceSurfaceId: 'userProfile');
    await adapter.unfollow('persona-2');
    final following = await adapter.listFollowing(
      personaId: 'persona-1',
      limit: 10,
    );
    final followers = await adapter.listFollowers(
      personaId: 'persona-1',
      limit: 10,
    );

    final expectedOperationIds = <String>[
      AppCloudOperationIds.userPersonaRelationshipFollowUser,
      AppCloudOperationIds.userPersonaRelationshipUnfollowUser,
      AppCloudOperationIds.userPersonaRelationshipListFollowing,
      AppCloudOperationIds.userPersonaRelationshipListFollowers,
    ];
    expect(executor.operationIds, expectedOperationIds);
    expect(contextOperationIds, expectedOperationIds);
    expect(executor.payloads.first.body, <String, Object?>{
      'source': 'userProfile',
    });
    expect(executor.payloads.first.pathParameters, <String, String>{
      'targetPersonaId': 'persona-2',
    });
    expect(following.items.single.personaId, 'persona-2');
    expect(following.nextCursor, 'cursor-2');
    expect(followers.items.single.displayName, '目标分身');
  });
}

final class _RecordingExecutor implements CloudOperationExecutor {
  final List<String> operationIds = <String>[];
  final List<CloudOperationRequestPayload> payloads =
      <CloudOperationRequestPayload>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationIds.add(operation.canonicalOperationId);
    payloads.add(requestEncoder());
    return responseDecoder(_responseFor(operation.canonicalOperationId));
  }
}

Object _responseFor(String operationId) {
  if (operationId == AppCloudOperationIds.userPersonaRelationshipFollowUser ||
      operationId == AppCloudOperationIds.userPersonaRelationshipUnfollowUser) {
    return <String, Object?>{
      'actorPersonaId': 'persona-1',
      'targetPersonaId': 'persona-2',
      'relationState': operationId.endsWith('FollowUser')
          ? 'following'
          : 'not_following',
      'idempotentReplay': false,
      'updatedAt': '2026-07-20T15:00:00Z',
    };
  }
  return <String, Object?>{
    'items': <Object?>[
      <String, Object?>{
        'personaId': 'persona-2',
        'userHandle': 'target',
        'displayName': '目标分身',
        'avatarUrl': '',
        'profileVisibility': 'public',
        'relationState': 'following',
        'followedAt': '2026-07-20T15:00:00Z',
      },
    ],
    'nextCursor': 'cursor-2',
  };
}
