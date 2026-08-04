import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';

/// Persona 管理投影与公开分身资料读面。
abstract interface class PersonaQuery {
  Future<List<PersonaManagementItemViewData>> listPersonas();

  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary();

  Future<ActivePersonaContextViewData> getActivePersonaContext();

  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  );

  Future<PersonaProfileViewData> getPersonaProfile(String personaId);
}
