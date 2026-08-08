// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-profile-subject-and-visibility/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/user-service-cloud-delivery/remote-profile-delivery/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-004
// readiness_case: user_account_list_personas_app_api
// readiness_case: user_account_get_persona_management_summary_app_api
// readiness_case: user_account_get_active_persona_context_app_api
// readiness_case: user_account_get_persona_lifecycle_guard_app_api
// readiness_case: user_account_get_persona_profile_app_api
// readiness_case: user_account_get_user_homepage_bundle_app_api
// readiness_case: user_account_get_me_profile_app_api
// readiness_case: user_account_search_social_relations_app_api
// readiness_case: user_account_pull_user_sync_app_api
// readiness_case: user_account_get_profile_edit_snapshot_app_api
// readiness_case: user_account_get_profile_qr_card_app_api
// readiness_case: user_account_resolve_profile_qr_token_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  UserApiContractHarness? harness;
  String? activePersonaId;

  UserApiContractHarness activeHarness() {
    return harness ??
        (throw StateError('UserApiContractHarness setup did not complete'));
  }

  String activePersona() {
    return activePersonaId ??
        (throw StateError('disposable account has no active persona'));
  }

  setUpAll(() async {
    final createdHarness = await UserApiContractHarness.create();
    harness = createdHarness;
    final session = await createdHarness.loginDisposableAccount(
      'user-account-queries',
    );
    activePersonaId = session.activePersona?.personaId;
    activePersona();
  });

  tearDownAll(() async {
    await harness?.close();
  });

  test('12-query exposure retains exact generated HTTP wire contracts', () {
    for (final expectation in _wireExpectations) {
      final contract = appCloudOperationContracts[expectation.operationId];
      expect(contract, isNotNull, reason: expectation.operationId);
      expect(contract!.objectId, 'user.user_account');
      expect(contract.method, expectation.method);
      expect(contract.pathTemplate, expectation.pathTemplate);
      expect(contract.requestBodyKind, expectation.requestBodyKind);
      expect(contract.idempotency, expectation.idempotency);
      expect(
        _bindingSignatures(contract.requestPathBindings),
        expectation.pathBindings,
      );
      expect(
        _bindingSignatures(contract.requestQueryBindings),
        expectation.queryBindings,
      );
    }
  });

  test('persona management reads candidate-owned typed state', () async {
    final api = activeHarness();
    final personaId = activePersona();

    final list = await api.userProfiles.listPersonas(const ListPersonasQuery());
    expect(list.items, isNotEmpty);
    expect(list.items.map((item) => item.personaId), contains(personaId));

    final summary = await api.userProfiles.getPersonaManagementSummary(
      const GetPersonaManagementSummaryQuery(),
    );
    expect(summary.quota.ownerUserId, api.session.ownerId);
    expect(summary.quota.activePersonaId, personaId);
    expect(summary.quota.totalCount, summary.items.length);
    expect(summary.activeContext.personaId, personaId);

    final active = await api.userProfiles.getActivePersonaContext(
      const GetActivePersonaContextQuery(),
    );
    expect(active.ownerUserId, api.session.ownerId);
    expect(active.personaId, personaId);
    expect(active.contextVersion, greaterThanOrEqualTo(1));

    final guard = await api.userProfiles.getPersonaLifecycleGuard(
      GetPersonaLifecycleGuardQuery(personaId: personaId),
    );
    expect(guard.personaId, personaId);
    expect(guard.requestedAction, PersonaLifecycleAction.retire);
    expect(guard.reason.wireName, isNotEmpty);

    await _expectSuccessfulTelemetry(api, const <String>{
      AppCloudOperationIds.userUserAccountListPersonas,
      AppCloudOperationIds.userUserAccountGetPersonaManagementSummary,
      AppCloudOperationIds.userUserAccountGetActivePersonaContext,
      AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard,
    });
  });

  test('public and owner profile reads agree on the active persona', () async {
    final api = activeHarness();
    final personaId = activePersona();

    final publicProfile = await api.userProfiles.getPersonaProfile(
      GetPersonaProfileQuery(personaId: personaId),
    );
    expect(publicProfile.personaId, personaId);
    expect(publicProfile.userHandle, isNotEmpty);
    expect(publicProfile.displayName, isNotEmpty);

    final homepage = await api.userProfiles.getUserHomepageBundle(
      GetUserHomepageBundleQuery(personaId: personaId),
    );
    expect(homepage.profile.personaId, personaId);
    expect(homepage.cacheVersion, isNotEmpty);
    expect(homepage.stats.followerCount, greaterThanOrEqualTo(0));

    final ownerProfile = await api.userProfiles.getMeProfile(
      const GetMeProfileQuery(),
    );
    expect(ownerProfile.personaId, personaId);
    expect(ownerProfile.userHandle, publicProfile.userHandle);

    final search = await api.userProfiles.searchSocialRelations(
      SearchSocialRelationsQuery(query: ownerProfile.userHandle, limit: 10),
    );
    expect(
      search.items.every(
        (item) =>
            item.personaId.isNotEmpty &&
            item.userHandle.isNotEmpty &&
            item.displayName.isNotEmpty,
      ),
      isTrue,
    );

    await _expectSuccessfulTelemetry(api, const <String>{
      AppCloudOperationIds.userUserAccountGetPersonaProfile,
      AppCloudOperationIds.userUserAccountGetUserHomepageBundle,
      AppCloudOperationIds.userUserAccountGetMeProfile,
      AppCloudOperationIds.userUserAccountSearchSocialRelations,
    });
  });

  test('profile edit and QR reads round-trip canonical identity', () async {
    final api = activeHarness();
    final personaId = activePersona();

    final snapshot = await api.userProfiles.getProfileEditSnapshot(
      const GetProfileEditSnapshotQuery(),
    );
    expect(snapshot.ownerUserId, api.session.ownerId);
    expect(snapshot.personaId, personaId);
    expect(snapshot.userHandle, isNotEmpty);

    final qrCard = await api.userProfiles.getProfileQrCard(
      const GetProfileQrCardQuery(),
    );
    expect(qrCard.qrTokenId, isNotEmpty);
    expect(qrCard.qrPayload, isNotEmpty);
    expect(Uri.parse(qrCard.publicProfileUrl).scheme, 'https');

    final resolved = await api.userProfiles.resolveProfileQrToken(
      ResolveProfileQrTokenQuery(
        qr: qrCard.qrPayload,
        handle: snapshot.userHandle,
      ),
    );
    expect(resolved.personaId, personaId);
    expect(resolved.userHandle, snapshot.userHandle);
    expect(resolved.publicProfileUrl, qrCard.publicProfileUrl);
    expect(resolved.scanStatus, isNotEmpty);

    await _expectSuccessfulTelemetry(api, const <String>{
      AppCloudOperationIds.userUserAccountGetProfileEditSnapshot,
      AppCloudOperationIds.userUserAccountGetProfileQrCard,
      AppCloudOperationIds.userUserAccountResolveProfileQrToken,
    });
  });

  test(
    'sync is typed and protected reads fail closed with exact telemetry',
    () async {
      final api = activeHarness();
      final sync = await api.userSync.pull(afterSeq: 0, limit: 20);

      expect(sync.latestSyncSeq, greaterThanOrEqualTo(0));
      expect(
        sync.patches.every(
          (patch) => patch.syncSeq > 0 && patch.syncSeq <= sync.latestSyncSeq,
        ),
        isTrue,
      );
      expect(
        sync.patches.map((patch) => patch.syncSeq).toList(),
        orderedEquals(
          sync.patches.map((patch) => patch.syncSeq).toList()..sort(),
        ),
      );

      final protectedContract =
          appCloudOperationContracts[AppCloudOperationIds
              .userUserAccountGetMeProfile]!;
      await expectLater(
        api.withTemporaryAccessToken(
          accessToken: 'invalid-user-account-api-contract-token',
          action: () =>
              api.userProfiles.getMeProfile(const GetMeProfileQuery()),
        ),
        throwsA(
          isA<CloudException>()
              .having(
                (error) => error.sourceOperationId,
                'sourceOperationId',
                AppCloudOperationIds.userUserAccountGetMeProfile,
              )
              .having(
                (error) => error.statusCode,
                'statusCode',
                anyOf(401, 403),
              )
              .having(
                (error) => error.code,
                'canonical code',
                isIn(protectedContract.errorCodes),
              ),
        ),
      );

      await _expectSuccessfulTelemetry(api, const <String>{
        AppCloudOperationIds.userUserAccountPullUserSync,
      });
      final events = await api.telemetry.waitForEvents(minimumCount: 1);
      expect(
        events.any(
          (event) =>
              event.canonicalOperationId ==
                  AppCloudOperationIds.userUserAccountGetMeProfile &&
              !event.succeeded &&
              (event.statusCode == 401 || event.statusCode == 403) &&
              event.requestId.isNotEmpty &&
              event.traceId.isNotEmpty,
        ),
        isTrue,
      );
    },
  );
}

Future<void> _expectSuccessfulTelemetry(
  UserApiContractHarness harness,
  Set<String> expectedOperationIds,
) async {
  final events = await harness.telemetry.waitForEvents(minimumCount: 1);
  for (final operationId in expectedOperationIds) {
    expect(
      events.any(
        (event) =>
            event.canonicalOperationId == operationId &&
            event.succeeded &&
            event.statusCode == 200 &&
            event.requestId.isNotEmpty &&
            event.traceId.isNotEmpty,
      ),
      isTrue,
      reason: operationId,
    );
  }
}

List<String> _bindingSignatures(List<CloudOperationRequestBinding> bindings) {
  return <String>[
    for (final binding in bindings)
      '${binding.name}:${binding.field}:${binding.required}',
  ];
}

const _wireExpectations =
    <
      ({
        String operationId,
        String method,
        String pathTemplate,
        String requestBodyKind,
        String idempotency,
        List<String> pathBindings,
        List<String> queryBindings,
      })
    >[
      (
        operationId: AppCloudOperationIds.userUserAccountListPersonas,
        method: 'GET',
        pathTemplate: '/user/personas',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>[],
        queryBindings: <String>[],
      ),
      (
        operationId:
            AppCloudOperationIds.userUserAccountGetPersonaManagementSummary,
        method: 'GET',
        pathTemplate: '/user/personas/summary',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>[],
        queryBindings: <String>[],
      ),
      (
        operationId:
            AppCloudOperationIds.userUserAccountGetActivePersonaContext,
        method: 'GET',
        pathTemplate: '/user/personas/active',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>[],
        queryBindings: <String>[],
      ),
      (
        operationId:
            AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard,
        method: 'GET',
        pathTemplate: '/user/personas/{personaId}/lifecycle-guard',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>['personaId:personaId:true'],
        queryBindings: <String>[],
      ),
      (
        operationId: AppCloudOperationIds.userUserAccountGetPersonaProfile,
        method: 'GET',
        pathTemplate: '/user/{personaId}',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>['personaId:personaId:true'],
        queryBindings: <String>[],
      ),
      (
        operationId: AppCloudOperationIds.userUserAccountGetUserHomepageBundle,
        method: 'GET',
        pathTemplate: '/user/personas/{personaId}/homepage-bundle',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>['personaId:personaId:true'],
        queryBindings: <String>[],
      ),
      (
        operationId: AppCloudOperationIds.userUserAccountGetMeProfile,
        method: 'GET',
        pathTemplate: '/me',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>[],
        queryBindings: <String>[],
      ),
      (
        operationId: AppCloudOperationIds.userUserAccountSearchSocialRelations,
        method: 'GET',
        pathTemplate: '/user/search/social-relations',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>[],
        queryBindings: <String>[
          'query:query:true',
          'cursor:cursor:false',
          'limit:limit:true',
        ],
      ),
      (
        operationId: AppCloudOperationIds.userUserAccountPullUserSync,
        method: 'POST',
        pathTemplate: '/user/sync',
        requestBodyKind: 'object',
        idempotency: 'none',
        pathBindings: <String>[],
        queryBindings: <String>[],
      ),
      (
        operationId: AppCloudOperationIds.userUserAccountGetProfileEditSnapshot,
        method: 'GET',
        pathTemplate: '/user/profile/edit-snapshot',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>[],
        queryBindings: <String>[],
      ),
      (
        operationId: AppCloudOperationIds.userUserAccountGetProfileQrCard,
        method: 'GET',
        pathTemplate: '/user/profile/qr-card',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>[],
        queryBindings: <String>[],
      ),
      (
        operationId: AppCloudOperationIds.userUserAccountResolveProfileQrToken,
        method: 'GET',
        pathTemplate: '/public/profile/qr/resolve',
        requestBodyKind: 'none',
        idempotency: 'none',
        pathBindings: <String>[],
        queryBindings: <String>['qr:qr:true', 'handle:handle:false'],
      ),
    ];
