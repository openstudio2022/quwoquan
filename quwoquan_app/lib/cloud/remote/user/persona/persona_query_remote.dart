import 'package:quwoquan_app/application/user/persona/persona_query.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// PersonaQuery 的 production Remote adapter。
///
/// 只负责 pure contract projection → App ViewData 映射；path/auth/retry/deadline
/// 与响应解码全部由 [PersonaManagementQueryFacet]/[PublicProfileQueryFacet]
/// 背后的 generated client 承担。
final class RemotePersonaQuery implements PersonaQuery {
  const RemotePersonaQuery({
    required this.managementQuery,
    required this.publicProfileQuery,
  });

  final PersonaManagementQueryFacet managementQuery;
  final PublicProfileQueryFacet publicProfileQuery;

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() async {
    final result = await managementQuery.listPersonas(ListPersonasQuery());
    return result.items
        .map(PersonaManagementItemViewData.fromPersonaManagementItemProjection)
        .toList(growable: false);
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    final projection = await managementQuery.getPersonaManagementSummary(
      GetPersonaManagementSummaryQuery(),
    );
    return PersonaManagementSummaryViewData.fromProjection(projection);
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    final projection = await managementQuery.getActivePersonaContext(
      GetActivePersonaContextQuery(),
    );
    return ActivePersonaContextViewData.fromActivePersonaContextProjection(
      projection,
    );
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) async {
    final projection = await managementQuery.getPersonaLifecycleGuard(
      GetPersonaLifecycleGuardQuery(personaId: personaId),
    );
    return PersonaLifecycleGuardViewData.fromPersonaLifecycleGuardProjection(
      projection,
    );
  }

  @override
  Future<PersonaProfileViewData> getPersonaProfile(String personaId) async {
    final projection = await publicProfileQuery.getPersonaProfile(
      GetPersonaProfileQuery(personaId: personaId),
    );
    return PersonaProfileViewData.fromPersonaProfileProjection(projection);
  }
}
