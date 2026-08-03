import 'user_operation_contracts.g.dart';

abstract interface class PersonaManagementCommandWriter {
  Future<PersonaManagementItemView> createPersona(CreatePersonaCommand command);
  Future<PersonaManagementItemView> updatePersona(UpdatePersonaCommand command);
  Future<PersonaProfileSyncResult> applyPersonaProfileSync(
    ApplyPersonaProfileSyncCommand command,
  );
  Future<PersonaLifecycleGuardView> retirePersona(RetirePersonaCommand command);
  Future<ActivePersonaContextView> activatePersona(
    ActivatePersonaCommand command,
  );
}

abstract interface class ProfileCommandWriter {
  Future<ProfileUpdateSnapshot> updateUserProfile(
    UpdateUserProfileCommand command,
  );
}
