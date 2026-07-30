import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/remote/user/persona/persona_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/profile_edit_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/profile_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/user_profile_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  late _UserProfileExecutor executor;
  late RemoteUserProfileQueryFacet facet;

  setUp(() {
    executor = _UserProfileExecutor(_responses);
    facet = RemoteUserProfileQueryFacet(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: (clientPageId, canonicalOperationId) {
        return CloudOperationInvocationContext(
          surfaceId: 'user-profile-contract',
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'owner-1',
            personaId: 'persona-1',
          ),
          idempotencyKey: 'contract-$canonicalOperationId',
        );
      },
    );
  });

  test('公开资料、主页聚合和联系人搜索只经 typed query facet', () async {
    final query = RemoteProfileQuery(
      publicProfileQuery: facet,
      userHomepageQuery: facet,
    );

    final me = await query.getUserProfile('me');
    final target = await query.getUserProfile('persona-2');
    final homepage = await query.getUserHomepageBundle('persona-2');
    final search = await query.searchSocialRelations(query: '小趣');

    expect(me.personaId, 'persona-1');
    expect(target.personaId, 'persona-2');
    expect(homepage.profile.personaId, 'persona-2');
    expect(homepage.relationshipCapability?.canOpenConversation, isTrue);
    expect(search.single.relationshipCapability.relationState, 'mutual');
    expect(search.single.relationshipCapability.targetPersonaId, 'persona-2');
    expect(search.single.relationshipCapability.canGreet, isFalse);
    expect(search.single.relationshipCapability.hasFormalConversation, isTrue);
    expect(
      executor.operationIds,
      containsAll(<String>[
        AppCloudOperationIds.userUserAccountGetMeProfile,
        AppCloudOperationIds.userUserAccountGetPersonaProfile,
        AppCloudOperationIds.userUserAccountGetUserHomepageBundle,
        AppCloudOperationIds.userUserAccountSearchSocialRelations,
      ]),
    );
  });

  test('分身列表、汇总、活动上下文和生命周期守卫同轨映射', () async {
    final query = RemotePersonaQuery(
      managementQuery: facet,
      publicProfileQuery: facet,
    );

    final personas = await query.listPersonas();
    final summary = await query.getPersonaManagementSummary();
    final active = await query.getActivePersonaContext();
    final guard = await query.getPersonaLifecycleGuard('persona-2');

    expect(personas.single.avatarVersion, 3);
    expect(summary.quota.usedPersonas, 1);
    expect(summary.activeContext?.displayName, '主分身');
    expect(active.contextVersion, 7);
    expect(guard.allowed, isTrue);
    expect(
      executor.operationIds,
      containsAll(<String>[
        AppCloudOperationIds.userUserAccountListPersonas,
        AppCloudOperationIds.userUserAccountGetPersonaManagementSummary,
        AppCloudOperationIds.userUserAccountGetActivePersonaContext,
        AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard,
      ]),
    );
  });

  test('编辑快照、二维码名片和扫码解析同轨映射', () async {
    final query = RemoteProfileEditQuery(
      editSnapshotQuery: facet,
      publicProfileQuery: facet,
    );

    final snapshot = await query.getProfileEditSnapshot();
    final card = await query.getProfileQrCard();
    final resolved = await query.resolveProfileQrToken(
      token: 'qr-token-1',
      handle: 'xiaoq',
    );

    expect(snapshot.nickname, '主分身');
    expect(snapshot.phoneCredential?.isBound, isTrue);
    expect(card.qrPayload, 'quwoquan://profile/persona-1');
    expect(resolved.personaId, 'persona-2');
    expect(
      executor.operationIds,
      containsAll(<String>[
        AppCloudOperationIds.userUserAccountGetProfileEditSnapshot,
        AppCloudOperationIds.userUserAccountGetProfileQrCard,
        AppCloudOperationIds.userUserAccountResolveProfileQrToken,
      ]),
    );
    final resolvePayload = executor.payloads.last;
    expect(resolvePayload.queryParameters, <String, String>{
      'qr': 'qr-token-1',
      'handle': 'xiaoq',
    });
  });
}

final Map<String, Object?> _responses = <String, Object?>{
  AppCloudOperationIds.userUserAccountGetMeProfile: _profile(
    'persona-1',
    '主分身',
  ),
  AppCloudOperationIds.userUserAccountGetPersonaProfile: _profile(
    'persona-2',
    '小趣',
  ),
  AppCloudOperationIds.userUserAccountListPersonas: <String, Object?>{
    'items': <Object?>[_persona],
  },
  AppCloudOperationIds.userUserAccountGetPersonaManagementSummary:
      <String, Object?>{
        'items': <Object?>[_persona],
        'quota': <String, Object?>{
          'ownerUserId': 'owner-1',
          'totalCount': 1,
          'quotaLimit': 5,
          'remainingCount': 4,
        },
        'activeContext': _activeContext,
      },
  AppCloudOperationIds.userUserAccountGetActivePersonaContext: _activeContext,
  AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard:
      <String, Object?>{
        'personaId': 'persona-2',
        'requestedAction': 'retire',
        'allowed': true,
        'reason': '',
        'requiresSuccessor': false,
      },
  AppCloudOperationIds.userUserAccountGetProfileEditSnapshot: <String, Object?>{
    'ownerUserId': 'owner-1',
    'personaId': 'persona-1',
    'nickname': '主分身',
    'displayName': '主分身',
    'userHandle': 'owner',
    'phoneCredential': <String, Object?>{
      'credentialType': 'phone',
      'displayLabel': '138****0000',
      'isBound': true,
    },
    'qrCard': _qrCard,
  },
  AppCloudOperationIds.userUserAccountGetProfileQrCard: _qrCard,
  AppCloudOperationIds.userUserAccountResolveProfileQrToken: <String, Object?>{
    'personaId': 'persona-2',
    'userHandle': 'xiaoq',
    'publicProfileUrl': 'https://quwoquan.example/u/xiaoq',
    'scanStatus': 'accepted',
  },
  AppCloudOperationIds.userUserAccountSearchSocialRelations: <String, Object?>{
    'items': <Object?>[
      <String, Object?>{
        'personaId': 'persona-2',
        'userHandle': 'xiaoq',
        'displayName': '小趣',
        'chatAvailable': true,
        'relationshipCapability': <String, Object?>{
          'viewerPersonaId': 'persona-1',
          'targetPersonaId': 'persona-2',
          'relationState': 'mutual',
          'canFollow': false,
          'canUnfollow': true,
          'canFollowBack': false,
          'canGreet': false,
          'canOpenConversation': true,
          'canCreateDirectConversation': true,
          'canSendMessage': true,
          'hasPendingGreeting': false,
          'hasFormalConversation': true,
          'canStartVoiceCall': true,
          'canStartVideoCall': true,
          'isBlocked': false,
          'isBlockedBy': false,
        },
      },
    ],
    'cursor': '',
  },
  AppCloudOperationIds.userUserAccountGetUserHomepageBundle: <String, Object?>{
    'profile': _profile('persona-2', '小趣'),
    'stats': <String, Object?>{
      'followingCount': 8,
      'circleCount': 2,
      'followerCount': 10,
      'likeCount': 20,
      'postCount': 4,
    },
    'relationshipCapability': <String, Object?>{
      'viewerPersonaId': 'persona-1',
      'targetPersonaId': 'persona-2',
      'relationState': 'mutual',
      'canFollow': false,
      'canUnfollow': true,
      'canFollowBack': false,
      'canGreet': false,
      'canOpenConversation': true,
      'canCreateDirectConversation': true,
      'canSendMessage': true,
      'hasPendingGreeting': false,
      'hasFormalConversation': true,
      'canStartVoiceCall': true,
      'canStartVideoCall': true,
      'isBlocked': false,
      'isBlockedBy': false,
    },
    'cacheVersion': 'profile-revision-a',
  },
};

const Map<String, Object?> _persona = <String, Object?>{
  'personaId': 'persona-1',
  'displayName': '主分身',
  'userHandle': 'owner',
  'avatarVersion': 3,
  'isPrimary': true,
  'isActive': true,
  'status': 'active',
  'hasPublishedContent': true,
  'inheritsProfileFromOwner': false,
  'overriddenProfileFields': <Object?>[],
  'subjectType': 'persona',
};

const Map<String, Object?> _activeContext = <String, Object?>{
  'ownerUserId': 'owner-1',
  'personaId': 'persona-1',
  'subjectType': 'persona',
  'displayName': '主分身',
  'avatarUrl': '',
  'avatarVersion': 3,
  'isPrimary': true,
  'contextVersion': 7,
  'personaSnapshotVersion': 9,
  'sourceSurfaceId': 'appShell',
  'explicitOverride': false,
};

const Map<String, Object?> _qrCard = <String, Object?>{
  'publicProfileUrl': 'https://quwoquan.example/u/owner',
  'qrPayload': 'quwoquan://profile/persona-1',
  'qrTokenId': 'qr-token-1',
  'avatarUrl': '',
  'avatarVersion': '3',
  'displayName': '主分身',
  'region': '浙江',
  'shareText': '扫一扫认识我',
};

Map<String, Object?> _profile(String personaId, String displayName) {
  return <String, Object?>{
    'personaId': personaId,
    'ownerUserId': 'owner-1',
    'userHandle': personaId == 'persona-1' ? 'owner' : 'xiaoq',
    'nickname': displayName,
    'displayName': displayName,
    'subjectType': 'persona',
    'avatarVersion': 3,
    'profileVisibility': 'public',
    'isolationLevel': 'open',
  };
}

final class _UserProfileExecutor implements CloudOperationExecutor {
  _UserProfileExecutor(this.responses);

  final Map<String, Object?> responses;
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
    return responseDecoder(responses[operation.canonicalOperationId]);
  }
}
