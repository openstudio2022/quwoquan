// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-profile-subject-and-visibility/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-004
// readiness_case: user_account_list_personas_app_local
// readiness_case: user_account_get_persona_management_summary_app_local
// readiness_case: user_account_get_persona_lifecycle_guard_app_local
// readiness_case: user_account_get_persona_profile_app_local
// readiness_case: user_account_get_user_homepage_bundle_app_local
// readiness_case: user_account_get_me_profile_app_local
// readiness_case: user_account_search_social_relations_app_local
// readiness_case: user_account_get_profile_edit_snapshot_app_local
// readiness_case: user_account_get_profile_qr_card_app_local
// readiness_case: user_account_resolve_profile_qr_token_app_local

/// UserAccount 对象级查询契约：production Remote + generated client 的
/// operation、HTTP wire、strict typed decode 与 canonical failure 保持同轨。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/user_profile_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

void main() {
  group('RemoteUserProfileQueryFacet generated HTTP contract', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteUserProfileQueryFacet facet;

    setUp(() {
      log = <CapturedRemoteApiPathRequest>[];
      facet = _buildFacet(log, responseFor: _responseFor);
    });

    test('ListPersonas exact GET wire and typed items', () async {
      final result = await facet.listPersonas(const ListPersonasQuery());

      expect(result.items.single.personaId, 'persona-1');
      expect(result.items.single.status, PersonaStatus.active);
      _expectLastRequest(
        log,
        operationId: AppCloudOperationIds.userUserAccountListPersonas,
        clientPageId: UserRequestPageIds.listPersonas,
        method: 'GET',
      );
    });

    test(
      'GetPersonaManagementSummary exact GET wire and typed quota',
      () async {
        final result = await facet.getPersonaManagementSummary(
          const GetPersonaManagementSummaryQuery(),
        );

        expect(result.quota.ownerUserId, 'owner-1');
        expect(result.quota.remainingCount, 4);
        expect(result.activeContext.personaId, 'persona-1');
        _expectLastRequest(
          log,
          operationId:
              AppCloudOperationIds.userUserAccountGetPersonaManagementSummary,
          clientPageId: UserRequestPageIds.getPersonaManagementSummary,
          method: 'GET',
        );
      },
    );

    test('GetPersonaLifecycleGuard exact path and typed guard', () async {
      final result = await facet.getPersonaLifecycleGuard(
        const GetPersonaLifecycleGuardQuery(personaId: 'persona-2'),
      );

      expect(result.personaId, 'persona-2');
      expect(result.requestedAction, PersonaLifecycleAction.retire);
      expect(result.allowed, isTrue);
      expect(result.reason, PersonaLifecycleGuardReason.allowed);
      _expectLastRequest(
        log,
        operationId:
            AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard,
        clientPageId: UserRequestPageIds.getPersonaLifecycleGuard,
        method: 'GET',
        pathParameters: const <String, String>{'personaId': 'persona-2'},
      );
    });

    test('GetPersonaProfile exact public path and typed profile', () async {
      final result = await facet.getPersonaProfile(
        const GetPersonaProfileQuery(personaId: 'persona-2'),
      );

      expect(result.personaId, 'persona-2');
      expect(result.displayName, '小趣');
      expect(result.profileVisibility, ProfileVisibility.public);
      _expectLastRequest(
        log,
        operationId: AppCloudOperationIds.userUserAccountGetPersonaProfile,
        clientPageId: UserRequestPageIds.getPersonaProfile,
        method: 'GET',
        pathParameters: const <String, String>{'personaId': 'persona-2'},
      );
    });

    test('GetUserHomepageBundle exact path and typed aggregate', () async {
      final result = await facet.getUserHomepageBundle(
        const GetUserHomepageBundleQuery(personaId: 'persona-2'),
      );

      expect(result.profile.personaId, 'persona-2');
      expect(result.stats.followerCount, 10);
      expect(result.relationshipCapability?.canOpenConversation, isTrue);
      expect(result.cacheVersion, 'profile-revision-a');
      _expectLastRequest(
        log,
        operationId: AppCloudOperationIds.userUserAccountGetUserHomepageBundle,
        clientPageId: UserRequestPageIds.getUserHomepageBundle,
        method: 'GET',
        pathParameters: const <String, String>{'personaId': 'persona-2'},
      );
    });

    test('GetMeProfile exact GET wire and typed owner profile', () async {
      final result = await facet.getMeProfile(const GetMeProfileQuery());

      expect(result.personaId, 'persona-1');
      expect(result.displayName, '主分身');
      _expectLastRequest(
        log,
        operationId: AppCloudOperationIds.userUserAccountGetMeProfile,
        clientPageId: UserRequestPageIds.getMeProfile,
        method: 'GET',
      );
    });

    test(
      'SearchSocialRelations exact query wire and typed capability',
      () async {
        final result = await facet.searchSocialRelations(
          SearchSocialRelationsQuery(query: '摄影', cursor: 'cursor-1', limit: 7),
        );

        expect(result.items.single.personaId, 'persona-2');
        expect(
          result.items.single.relationshipCapability.relationState,
          RelationshipState.mutual,
        );
        expect(result.cursor, 'cursor-2');
        _expectLastRequest(
          log,
          operationId:
              AppCloudOperationIds.userUserAccountSearchSocialRelations,
          clientPageId: UserRequestPageIds.searchSocialRelations,
          method: 'GET',
          query: const <String, String>{
            'query': '摄影',
            'cursor': 'cursor-1',
            'limit': '7',
          },
        );
      },
    );

    test(
      'GetProfileEditSnapshot exact GET wire and typed private fields',
      () async {
        final result = await facet.getProfileEditSnapshot(
          const GetProfileEditSnapshotQuery(),
        );

        expect(result.ownerUserId, 'owner-1');
        expect(result.phoneCredential?.isBound, isTrue);
        expect(result.qrCard?.qrTokenId, 'qr-token-1');
        _expectLastRequest(
          log,
          operationId:
              AppCloudOperationIds.userUserAccountGetProfileEditSnapshot,
          clientPageId: UserRequestPageIds.getProfileEditSnapshot,
          method: 'GET',
        );
      },
    );

    test('GetProfileQrCard exact GET wire and typed QR card', () async {
      final result = await facet.getProfileQrCard(
        const GetProfileQrCardQuery(),
      );

      expect(result.qrPayload, 'https://quwoquan.example/u/owner');
      expect(result.qrTokenId, 'qr-token-1');
      _expectLastRequest(
        log,
        operationId: AppCloudOperationIds.userUserAccountGetProfileQrCard,
        clientPageId: UserRequestPageIds.getProfileQrCard,
        method: 'GET',
      );
    });

    test('ResolveProfileQrToken exact query wire and typed target', () async {
      final result = await facet.resolveProfileQrToken(
        const ResolveProfileQrTokenQuery(qr: 'qr-token-1', handle: 'xiaoq'),
      );

      expect(result.personaId, 'persona-2');
      expect(result.scanStatus, 'accepted');
      _expectLastRequest(
        log,
        operationId: AppCloudOperationIds.userUserAccountResolveProfileQrToken,
        clientPageId: UserRequestPageIds.resolveProfileQrToken,
        method: 'GET',
        query: const <String, String>{'qr': 'qr-token-1', 'handle': 'xiaoq'},
      );
    });

    final failureCases =
        <
          ({
            String operationId,
            Future<Object?> Function(RemoteUserProfileQueryFacet) invoke,
          })
        >[
          (
            operationId: AppCloudOperationIds.userUserAccountListPersonas,
            invoke: (target) => target.listPersonas(const ListPersonasQuery()),
          ),
          (
            operationId:
                AppCloudOperationIds.userUserAccountGetPersonaManagementSummary,
            invoke: (target) => target.getPersonaManagementSummary(
              const GetPersonaManagementSummaryQuery(),
            ),
          ),
          (
            operationId:
                AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard,
            invoke: (target) => target.getPersonaLifecycleGuard(
              const GetPersonaLifecycleGuardQuery(personaId: 'persona-2'),
            ),
          ),
          (
            operationId: AppCloudOperationIds.userUserAccountGetPersonaProfile,
            invoke: (target) => target.getPersonaProfile(
              const GetPersonaProfileQuery(personaId: 'persona-2'),
            ),
          ),
          (
            operationId:
                AppCloudOperationIds.userUserAccountGetUserHomepageBundle,
            invoke: (target) => target.getUserHomepageBundle(
              const GetUserHomepageBundleQuery(personaId: 'persona-2'),
            ),
          ),
          (
            operationId: AppCloudOperationIds.userUserAccountGetMeProfile,
            invoke: (target) => target.getMeProfile(const GetMeProfileQuery()),
          ),
          (
            operationId:
                AppCloudOperationIds.userUserAccountSearchSocialRelations,
            invoke: (target) => target.searchSocialRelations(
              SearchSocialRelationsQuery(query: '摄影'),
            ),
          ),
          (
            operationId:
                AppCloudOperationIds.userUserAccountGetProfileEditSnapshot,
            invoke: (target) => target.getProfileEditSnapshot(
              const GetProfileEditSnapshotQuery(),
            ),
          ),
          (
            operationId: AppCloudOperationIds.userUserAccountGetProfileQrCard,
            invoke: (target) =>
                target.getProfileQrCard(const GetProfileQrCardQuery()),
          ),
          (
            operationId:
                AppCloudOperationIds.userUserAccountResolveProfileQrToken,
            invoke: (target) => target.resolveProfileQrToken(
              const ResolveProfileQrTokenQuery(qr: 'qr-token-1'),
            ),
          ),
        ];

    for (final failureCase in failureCases) {
      test(
        '${failureCase.operationId} canonical failure is not swallowed',
        () async {
          final failureLog = <CapturedRemoteApiPathRequest>[];
          final failingFacet = _buildFacet(
            failureLog,
            responseFor: (_) => remoteApiPathJsonResponse(<String, Object?>{
              'code': 'USER.SYSTEM.internal_error',
              'message': 'user dependency unavailable',
            }, statusCode: 503),
          );

          await expectLater(
            failureCase.invoke(failingFacet),
            throwsA(isA<CloudException>()),
          );
          expect(failureLog, isNotEmpty);
          expect(
            failureLog.last.headers['X-Client-Operation-Id'],
            failureCase.operationId,
          );
        },
      );
    }
  });
}

RemoteUserProfileQueryFacet _buildFacet(
  List<CapturedRemoteApiPathRequest> log, {
  required RemoteApiPathResponseFactory responseFor,
}) {
  return RemoteUserProfileQueryFacet(
    client: buildRemoteApiPathOperationClient(log, responseFor: responseFor),
    invocationContext: (clientPageId, canonicalOperationId) {
      final operation = appCloudOperationContracts[canonicalOperationId]!;
      final surface = AppUiSurfaces.byId[operation.surfaceIds.first]!;
      return CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        actor: const CloudOperationActorContext(
          accountId: 'owner-1',
          personaId: 'persona-1',
        ),
      );
    },
  );
}

void _expectLastRequest(
  List<CapturedRemoteApiPathRequest> log, {
  required String operationId,
  required String clientPageId,
  required String method,
  Map<String, String> pathParameters = const <String, String>{},
  Map<String, String> query = const <String, String>{},
}) {
  final request = log.last;
  final operation = appCloudOperationContracts[operationId]!;
  final surface = AppUiSurfaces.byId[operation.surfaceIds.first]!;
  expect(request.method, method);
  expect(
    request.path,
    canonicalRemoteApiPath(operationId, pathParameters: pathParameters),
  );
  expect(request.query, query);
  expect(request.body, isEmpty);
  expect(request.headers['Authorization'], 'Bearer integration-contract-token');
  expect(request.headers.containsKey('Idempotency-Key'), isFalse);
  expectRemoteApiPathHeaders(
    request.headers,
    clientPageId: clientPageId,
    surfaceId: surface.id,
    operationId: operationId,
  );
}

http.Response _responseFor(http.Request request) {
  final path = request.url.path;
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountListPersonas,
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'items': <Object?>[_persona],
    });
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetPersonaManagementSummary,
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'items': <Object?>[_persona],
      'quota': <String, Object?>{
        'ownerUserId': 'owner-1',
        'totalCount': 1,
        'quotaLimit': 5,
        'remainingCount': 4,
        'activePersonaId': 'persona-1',
        'primaryPersonaId': 'persona-1',
      },
      'activeContext': _activeContext,
    });
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard,
            pathParameters: const <String, String>{'personaId': 'persona-2'},
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'personaId': 'persona-2',
      'requestedAction': 'retire',
      'allowed': true,
      'reason': 'allowed',
      'requiresSuccessor': false,
    });
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetPersonaProfile,
            pathParameters: const <String, String>{'personaId': 'persona-2'},
          )) {
    return remoteApiPathJsonResponse(_profile('persona-2', '小趣'));
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetUserHomepageBundle,
            pathParameters: const <String, String>{'personaId': 'persona-2'},
          )) {
    return remoteApiPathJsonResponse(_homepageBundle);
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetMeProfile,
          )) {
    return remoteApiPathJsonResponse(_profile('persona-1', '主分身'));
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountSearchSocialRelations,
          )) {
    return remoteApiPathJsonResponse(_socialSearchResult);
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetProfileEditSnapshot,
          )) {
    return remoteApiPathJsonResponse(_profileEditSnapshot);
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountGetProfileQrCard,
          )) {
    return remoteApiPathJsonResponse(_qrCard);
  }
  if (request.method == 'GET' &&
      path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.userUserAccountResolveProfileQrToken,
          )) {
    return remoteApiPathJsonResponse(<String, Object?>{
      'personaId': 'persona-2',
      'userHandle': 'xiaoq',
      'publicProfileUrl': 'https://quwoquan.example/u/xiaoq',
      'scanStatus': 'accepted',
    });
  }
  return remoteApiPathJsonResponse(<String, Object?>{
    'code': 'USER.SYSTEM.internal_error',
    'message': 'unexpected local contract request',
  }, statusCode: 500);
}

const Map<String, Object?> _persona = <String, Object?>{
  'personaId': 'persona-1',
  'displayName': '主分身',
  'userHandle': 'owner',
  'isolationLevel': 'open',
  'profileVisibility': 'public',
  'isPrimary': true,
  'isActive': true,
  'status': 'active',
  'inheritsProfileFromOwner': false,
  'overriddenProfileFields': <Object?>[],
  'updatedAt': '2026-07-20T00:00:00Z',
};

const Map<String, Object?> _activeContext = <String, Object?>{
  'ownerUserId': 'owner-1',
  'personaId': 'persona-1',
  'subjectType': 'persona',
  'displayName': '主分身',
  'avatarUrl': '',
  'avatarVersion': 3,
  'isPrimary': true,
  'isolationLevel': 'open',
  'profileVisibility': 'public',
  'contextVersion': 7,
  'personaSnapshotVersion': 9,
  'sourceSurfaceId': 'appShell',
  'explicitOverride': false,
  'switchedAt': '2026-07-20T00:00:00Z',
};

const Map<String, Object?> _qrCard = <String, Object?>{
  'publicProfileUrl': 'https://quwoquan.example/u/owner',
  'qrPayload': 'https://quwoquan.example/u/owner',
  'qrTokenId': 'qr-token-1',
  'avatarUrl': '',
  'displayName': '主分身',
  'region': '浙江',
  'shareText': '扫一扫认识我',
};

const Map<String, Object?> _profileEditSnapshot = <String, Object?>{
  'ownerUserId': 'owner-1',
  'personaId': 'persona-1',
  'avatarVersion': 3,
  'nickname': '主分身',
  'displayName': '主分身',
  'userHandle': 'owner',
  'phoneCredential': <String, Object?>{
    'credentialType': 'phone',
    'displayLabel': '138****0000',
    'isBound': true,
  },
  'qrCard': _qrCard,
  'updatedAt': '2026-07-20T00:00:00Z',
};

final Map<String, Object?> _homepageBundle = <String, Object?>{
  'profile': _profile('persona-2', '小趣'),
  'stats': <String, Object?>{
    'followingCount': 8,
    'circleCount': 2,
    'followerCount': 10,
    'likeCount': 20,
    'postCount': 4,
  },
  'relationshipCapability': _relationshipCapability,
  'tabCounts': <String, Object?>{
    'worksCount': 4,
    'likesCount': 20,
    'circlesCount': 2,
    'collectionsCount': 0,
  },
  'viewerContext': <String, Object?>{
    'viewerPersonaId': 'persona-1',
    'isOwner': false,
    'isGuest': false,
    'relationToTarget': 'mutual',
    'canViewFullProfile': true,
  },
  'cacheVersion': 'profile-revision-a',
};

const Map<String, Object?> _socialSearchResult = <String, Object?>{
  'items': <Object?>[
    <String, Object?>{
      'personaId': 'persona-2',
      'userHandle': 'xiaoq',
      'displayName': '小趣',
      'chatAvailable': true,
      'relationshipCapability': _relationshipCapability,
    },
  ],
  'cursor': 'cursor-2',
};

const Map<String, Object?> _relationshipCapability = <String, Object?>{
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
};

Map<String, Object?> _profile(String personaId, String displayName) {
  return <String, Object?>{
    'personaId': personaId,
    'userHandle': personaId == 'persona-1' ? 'owner' : 'xiaoq',
    'displayName': displayName,
    'nicknameCustomized': true,
    'subjectType': 'persona',
    'followerCount': 10,
    'followingCount': 8,
    'postCount': 4,
    'circleCount': 2,
    'likeCount': 20,
    'profileVisibility': 'public',
    'isolationLevel': 'open',
    'inheritsFromOwner': false,
    'overriddenFields': <Object?>[],
    'updatedAt': '2026-07-20T00:00:00Z',
  };
}
