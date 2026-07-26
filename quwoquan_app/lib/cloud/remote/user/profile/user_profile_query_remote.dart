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
    return client.userUserAccountGetMeProfile(
      query,
      context: invocationContext(
        UserRequestPageIds.getMeProfile,
        AppCloudOperationIds.userUserAccountGetMeProfile,
      ),
    );
  }

  @override
  Future<ListPersonasResult> listPersonas(ListPersonasQuery query) {
    return client.userUserAccountListPersonas(
      query,
      context: invocationContext(
        UserRequestPageIds.listPersonas,
        AppCloudOperationIds.userUserAccountListPersonas,
      ),
    );
  }

  @override
  Future<PersonaManagementSummaryProjection> getPersonaManagementSummary(
    GetPersonaManagementSummaryQuery query,
  ) {
    return client.userUserAccountGetPersonaManagementSummary(
      query,
      context: invocationContext(
        UserRequestPageIds.getPersonaManagementSummary,
        AppCloudOperationIds.userUserAccountGetPersonaManagementSummary,
      ),
    );
  }

  @override
  Future<ActivePersonaContextProjection> getActivePersonaContext(
    GetActivePersonaContextQuery query,
  ) {
    return client.userUserAccountGetActivePersonaContext(
      query,
      context: invocationContext(
        UserRequestPageIds.getActivePersonaContext,
        AppCloudOperationIds.userUserAccountGetActivePersonaContext,
      ),
    );
  }

  @override
  Future<PersonaLifecycleGuardProjection> getPersonaLifecycleGuard(
    GetPersonaLifecycleGuardQuery query,
  ) {
    return client.userUserAccountGetPersonaLifecycleGuard(
      query,
      context: invocationContext(
        UserRequestPageIds.getPersonaLifecycleGuard,
        AppCloudOperationIds.userUserAccountGetPersonaLifecycleGuard,
      ),
    );
  }

  @override
  Future<SubAccountProfileProjection> getSubAccountProfile(
    GetSubAccountProfileQuery query,
  ) {
    return client.userUserAccountGetSubAccountProfile(
      query,
      context: invocationContext(
        UserRequestPageIds.getSubAccountProfile,
        AppCloudOperationIds.userUserAccountGetSubAccountProfile,
      ),
    );
  }

  @override
  Future<UserHomepageBundleProjection> getUserHomepageBundle(
    GetUserHomepageBundleQuery query,
  ) {
    return client.userUserAccountGetUserHomepageBundle(
      query,
      context: invocationContext(
        UserRequestPageIds.getUserHomepageBundle,
        AppCloudOperationIds.userUserAccountGetUserHomepageBundle,
      ),
    );
  }

  @override
  Future<ProfileEditSnapshotProjection> getProfileEditSnapshot(
    GetProfileEditSnapshotQuery query,
  ) {
    return client.userUserAccountGetProfileEditSnapshot(
      query,
      context: invocationContext(
        UserRequestPageIds.getProfileEditSnapshot,
        AppCloudOperationIds.userUserAccountGetProfileEditSnapshot,
      ),
    );
  }

  @override
  Future<ProfileQrCardProjection> getProfileQrCard(
    GetProfileQrCardQuery query,
  ) {
    return client.userUserAccountGetProfileQrCard(
      query,
      context: invocationContext(
        UserRequestPageIds.getProfileQrCard,
        AppCloudOperationIds.userUserAccountGetProfileQrCard,
      ),
    );
  }

  @override
  Future<ProfileQrResolveProjection> resolveProfileQrToken(
    ResolveProfileQrTokenQuery query,
  ) {
    return client.userUserAccountResolveProfileQrToken(
      query,
      context: invocationContext(
        UserRequestPageIds.resolveProfileQrToken,
        AppCloudOperationIds.userUserAccountResolveProfileQrToken,
      ),
    );
  }

  @override
  Future<SearchSocialRelationsResult> searchSocialRelations(
    SearchSocialRelationsQuery query,
  ) {
    return client.userUserAccountSearchSocialRelations(
      query,
      context: invocationContext(
        UserRequestPageIds.searchSocialRelations,
        AppCloudOperationIds.userUserAccountSearchSocialRelations,
      ),
    );
  }
}
