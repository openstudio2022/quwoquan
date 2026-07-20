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

    expect(me.subAccountId, 'persona-1');
    expect(target.subAccountId, 'persona-2');
    expect(homepage.profile.subAccountId, 'persona-2');
    expect(homepage.relationshipCapability?.canOpenConversation, isTrue);
    expect(search.single.relationshipCapability.relationState, 'mutual');
    expect(
      executor.operationIds,
      containsAll(<String>[
        AppCloudOperationIds.userUserProfileGetMeProfile,
        AppCloudOperationIds.userUserProfileGetSubAccountProfile,
        AppCloudOperationIds.userUserProfileGetUserHomepageBundle,
        AppCloudOperationIds.userUserProfileSearchSocialRelations,
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
    expect(summary.quota.usedSubAccounts, 1);
    expect(summary.activeContext?.displayName, '主分身');
    expect(active.personaContextVersion, '7');
    expect(guard.allowed, isTrue);
    expect(
      executor.operationIds,
      containsAll(<String>[
        AppCloudOperationIds.userUserProfileListPersonas,
        AppCloudOperationIds.userUserProfileGetPersonaManagementSummary,
        AppCloudOperationIds.userUserProfileGetActivePersonaContext,
        AppCloudOperationIds.userUserProfileGetPersonaLifecycleGuard,
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
    expect(resolved.subAccountId, 'persona-2');
    expect(
      executor.operationIds,
      containsAll(<String>[
        AppCloudOperationIds.userUserProfileGetProfileEditSnapshot,
        AppCloudOperationIds.userUserProfileGetProfileQrCard,
        AppCloudOperationIds.userUserProfileResolveProfileQrToken,
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
  AppCloudOperationIds.userUserProfileGetMeProfile: _profile(
    'persona-1',
    '主分身',
  ),
  AppCloudOperationIds.userUserProfileGetSubAccountProfile: _profile(
    'persona-2',
    '小趣',
  ),
  AppCloudOperationIds.userUserProfileListPersonas: <String, Object?>{
    'items': <Object?>[_persona],
  },
  AppCloudOperationIds.userUserProfileGetPersonaManagementSummary:
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
  AppCloudOperationIds.userUserProfileGetActivePersonaContext: _activeContext,
  AppCloudOperationIds.userUserProfileGetPersonaLifecycleGuard:
      <String, Object?>{
        'subAccountId': 'persona-2',
        'requestedAction': 'retire',
        'allowed': true,
        'reason': '',
        'requiresSuccessor': false,
      },
  AppCloudOperationIds.userUserProfileGetProfileEditSnapshot: <String, Object?>{
    'ownerUserId': 'owner-1',
    'subAccountId': 'persona-1',
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
  AppCloudOperationIds.userUserProfileGetProfileQrCard: _qrCard,
  AppCloudOperationIds.userUserProfileResolveProfileQrToken: <String, Object?>{
    'subAccountId': 'persona-2',
    'userHandle': 'xiaoq',
    'publicProfileUrl': 'https://quwoquan.example/u/xiaoq',
    'scanStatus': 'accepted',
  },
  AppCloudOperationIds.userUserProfileSearchSocialRelations: <String, Object?>{
    'items': <Object?>[
      <String, Object?>{
        'subAccountId': 'persona-2',
        'username': 'xiaoq',
        'userHandle': 'xiaoq',
        'displayName': '小趣',
        'chatAvailable': true,
        'relationshipCapability': <String, Object?>{
          'relationState': 'mutual',
          'canFollow': false,
          'canUnfollow': true,
          'canOpenConversation': true,
          'canStartVoiceCall': true,
          'canStartVideoCall': true,
        },
      },
    ],
    'cursor': '',
  },
  AppCloudOperationIds.userUserProfileGetUserHomepageBundle: <String, Object?>{
    'profile': _profile('persona-2', '小趣'),
    'stats': <String, Object?>{
      'followingCount': 8,
      'circleCount': 2,
      'followerCount': 10,
      'likeCount': 20,
      'postCount': 4,
    },
    'relationshipCapability': <String, Object?>{
      'viewerSubAccountId': 'persona-1',
      'targetSubAccountId': 'persona-2',
      'relationState': 'mutual',
      'canOpenConversation': true,
      'canCreateDirectConversation': true,
      'canSendMessage': true,
      'canStartVoiceCall': true,
      'canStartVideoCall': true,
      'isBlocked': false,
      'isBlockedBy': false,
    },
    'cacheVersion': 'profile-v1',
  },
};

const Map<String, Object?> _persona = <String, Object?>{
  'subAccountId': 'persona-1',
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
  'subAccountId': 'persona-1',
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
  'styleVersion': 'v1',
  'avatarUrl': '',
  'avatarVersion': '3',
  'displayName': '主分身',
  'region': '浙江',
  'shareText': '扫一扫认识我',
};

Map<String, Object?> _profile(String subAccountId, String displayName) {
  return <String, Object?>{
    'subAccountId': subAccountId,
    'ownerUserId': 'owner-1',
    'userHandle': subAccountId == 'persona-1' ? 'owner' : 'xiaoq',
    'nickname': displayName,
    'displayName': displayName,
    'username': subAccountId == 'persona-1' ? 'owner' : 'xiaoq',
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
