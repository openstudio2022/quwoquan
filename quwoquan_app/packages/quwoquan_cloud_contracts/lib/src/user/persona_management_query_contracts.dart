import 'user_operation_contracts.g.dart';

abstract interface class PersonaManagementQueryFacet {
  Future<ListPersonasResult> listPersonas(ListPersonasQuery query);
  Future<PersonaManagementSummaryView> getPersonaManagementSummary(
    GetPersonaManagementSummaryQuery query,
  );
  Future<ActivePersonaContextView> getActivePersonaContext(
    GetActivePersonaContextQuery query,
  );
  Future<PersonaLifecycleGuardView> getPersonaLifecycleGuard(
    GetPersonaLifecycleGuardQuery query,
  );
}
