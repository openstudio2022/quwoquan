import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef UserProfileQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String canonicalOperationId,
    );

/// UserAccount 对象全部商用查询的 production generated-client adapter。
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
  Future<PersonaProfileView> getMeProfile(GetMeProfileQuery query) {
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
  Future<PersonaManagementSummaryView> getPersonaManagementSummary(
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
  Future<ActivePersonaContextView> getActivePersonaContext(
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
  Future<PersonaLifecycleGuardView> getPersonaLifecycleGuard(
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
  Future<PersonaProfileView> getPersonaProfile(GetPersonaProfileQuery query) {
    return client.userUserAccountGetPersonaProfile(
      query,
      context: invocationContext(
        UserRequestPageIds.getPersonaProfile,
        AppCloudOperationIds.userUserAccountGetPersonaProfile,
      ),
    );
  }

  @override
  Future<UserHomepageBundleWire> getUserHomepageBundle(
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
  Future<ProfileEditSnapshotWire> getProfileEditSnapshot(
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
  Future<ProfileQrCardWire> getProfileQrCard(GetProfileQrCardQuery query) {
    return client.userUserAccountGetProfileQrCard(
      query,
      context: invocationContext(
        UserRequestPageIds.getProfileQrCard,
        AppCloudOperationIds.userUserAccountGetProfileQrCard,
      ),
    );
  }

  @override
  Future<ProfileQrResolveWire> resolveProfileQrToken(
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
