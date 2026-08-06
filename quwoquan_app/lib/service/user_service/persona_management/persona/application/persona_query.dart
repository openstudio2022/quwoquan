import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_query.dart';

/// Persona 管理投影与公开分身资料读面。
abstract interface class PersonaQuery implements PersonaProfileQuery {
  Future<List<PersonaManagementItemViewData>> listPersonas();

  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary();

  Future<ActivePersonaContextViewData> getActivePersonaContext();

  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  );

  @override
  Future<PersonaProfileViewData> getPersonaProfile(String personaId);
}
