import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_management_view_data_mapper.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
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
        .map(personaManagementItemViewDataFromWire)
        .toList(growable: false);
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() async {
    final projection = await managementQuery.getPersonaManagementSummary(
      GetPersonaManagementSummaryQuery(),
    );
    return personaManagementSummaryViewDataFromWire(projection);
  }

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() async {
    final projection = await managementQuery.getActivePersonaContext(
      GetActivePersonaContextQuery(),
    );
    return activePersonaContextViewDataFromWire(projection);
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) async {
    final projection = await managementQuery.getPersonaLifecycleGuard(
      GetPersonaLifecycleGuardQuery(personaId: personaId),
    );
    return PersonaLifecycleGuardViewData.fromWire(projection);
  }

  @override
  Future<PersonaProfileViewData> getPersonaProfile(String personaId) async {
    final projection = await publicProfileQuery.getPersonaProfile(
      GetPersonaProfileQuery(personaId: personaId),
    );
    return personaProfileViewDataFromWire(projection);
  }
}
