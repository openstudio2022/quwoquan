import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef UserProfileQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String canonicalOperationId,
    );

/// UserProfile 对象全部商用查询的 production generated-client adapter。
///
/// path/auth/retry/deadline/decoder 均由 ContractGraph descriptor 与 generated
/// client 承担；上层 Facet 只做 contract projection 到 ViewData 的映射。
final class RemoteUserProfileQueryFacet
    implements
        PersonaManagementQueryFacet,
        ProfileEditSnapshotQueryFacet,
        PublicProfileQueryFacet,
        UserHomepageQueryFacet {
  const RemoteUserProfileQueryFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final UserProfileQueryInvocationContextFactory invocationContext;

  @override
  Future<SubAccountProfileProjection> getMeProfile(GetMeProfileQuery query) {
    return client.userUserProfileGetMeProfile(
      query,
      context: invocationContext(
        UserRequestPageIds.getMeProfile,
        AppCloudOperationIds.userUserProfileGetMeProfile,
      ),
    );
  }

  @override
  Future<ListPersonasResult> listPersonas(ListPersonasQuery query) {
    return client.userUserProfileListPersonas(
      query,
      context: invocationContext(
        UserRequestPageIds.listPersonas,
        AppCloudOperationIds.userUserProfileListPersonas,
      ),
    );
  }

  @override
  Future<PersonaManagementSummaryProjection> getPersonaManagementSummary(
    GetPersonaManagementSummaryQuery query,
  ) {
    return client.userUserProfileGetPersonaManagementSummary(
      query,
      context: invocationContext(
        UserRequestPageIds.getPersonaManagementSummary,
        AppCloudOperationIds.userUserProfileGetPersonaManagementSummary,
      ),
    );
  }

  @override
  Future<ActivePersonaContextProjection> getActivePersonaContext(
    GetActivePersonaContextQuery query,
  ) {
    return client.userUserProfileGetActivePersonaContext(
      query,
      context: invocationContext(
        UserRequestPageIds.getActivePersonaContext,
        AppCloudOperationIds.userUserProfileGetActivePersonaContext,
      ),
    );
  }

  @override
  Future<PersonaLifecycleGuardProjection> getPersonaLifecycleGuard(
    GetPersonaLifecycleGuardQuery query,
  ) {
    return client.userUserProfileGetPersonaLifecycleGuard(
      query,
      context: invocationContext(
        UserRequestPageIds.getPersonaLifecycleGuard,
        AppCloudOperationIds.userUserProfileGetPersonaLifecycleGuard,
      ),
    );
  }

  @override
  Future<SubAccountProfileProjection> getSubAccountProfile(
    GetSubAccountProfileQuery query,
  ) {
    return client.userUserProfileGetSubAccountProfile(
      query,
      context: invocationContext(
        UserRequestPageIds.getSubAccountProfile,
        AppCloudOperationIds.userUserProfileGetSubAccountProfile,
      ),
    );
  }

  @override
  Future<UserHomepageBundleProjection> getUserHomepageBundle(
    GetUserHomepageBundleQuery query,
  ) {
    return client.userUserProfileGetUserHomepageBundle(
      query,
      context: invocationContext(
        UserRequestPageIds.getUserHomepageBundle,
        AppCloudOperationIds.userUserProfileGetUserHomepageBundle,
      ),
    );
  }

  @override
  Future<ProfileEditSnapshotProjection> getProfileEditSnapshot(
    GetProfileEditSnapshotQuery query,
  ) {
    return client.userUserProfileGetProfileEditSnapshot(
      query,
      context: invocationContext(
        UserRequestPageIds.getProfileEditSnapshot,
        AppCloudOperationIds.userUserProfileGetProfileEditSnapshot,
      ),
    );
  }

  @override
  Future<ProfileQrCardProjection> getProfileQrCard(
    GetProfileQrCardQuery query,
  ) {
    return client.userUserProfileGetProfileQrCard(
      query,
      context: invocationContext(
        UserRequestPageIds.getProfileQrCard,
        AppCloudOperationIds.userUserProfileGetProfileQrCard,
      ),
    );
  }

  @override
  Future<ProfileQrResolveProjection> resolveProfileQrToken(
    ResolveProfileQrTokenQuery query,
  ) {
    return client.userUserProfileResolveProfileQrToken(
      query,
      context: invocationContext(
        UserRequestPageIds.resolveProfileQrToken,
        AppCloudOperationIds.userUserProfileResolveProfileQrToken,
      ),
    );
  }

  @override
  Future<SearchSocialRelationsResult> searchSocialRelations(
    SearchSocialRelationsQuery query,
  ) {
    return client.userUserProfileSearchSocialRelations(
      query,
      context: invocationContext(
        UserRequestPageIds.searchSocialRelations,
        AppCloudOperationIds.userUserProfileSearchSocialRelations,
      ),
    );
  }
}
