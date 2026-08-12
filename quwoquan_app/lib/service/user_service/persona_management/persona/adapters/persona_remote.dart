import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef PersonaInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Persona 生命周期与资料写入的 production generated-client adapter。
final class RemotePersonaCommandWriter
    implements PersonaManagementCommandWriter, ProfileCommandWriter {
  const RemotePersonaCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final PersonaInvocationContextFactory invocationContext;

  @override
  Future<PersonaManagementItemView> createPersona(
    CreatePersonaCommand command,
  ) => client.userPersonaCreatePersona(
    command,
    context: invocationContext(UserRequestPageIds.createPersona),
  );

  @override
  Future<PersonaManagementItemView> updatePersona(
    UpdatePersonaCommand command,
  ) => client.userPersonaUpdatePersona(
    command,
    context: invocationContext(UserRequestPageIds.updatePersona),
  );

  @override
  Future<PersonaProfileSyncResult> applyPersonaProfileSync(
    ApplyPersonaProfileSyncCommand command,
  ) => client.userPersonaApplyPersonaProfileSync(
    command,
    context: invocationContext(UserRequestPageIds.applyPersonaProfileSync),
  );

  @override
  Future<PersonaLifecycleGuardView> retirePersona(
    RetirePersonaCommand command,
  ) => client.userPersonaRetirePersona(
    command,
    context: invocationContext(UserRequestPageIds.retirePersona),
  );

  @override
  Future<ActivePersonaContextView> activatePersona(
    ActivatePersonaCommand command,
  ) => client.userPersonaActivatePersona(
    command,
    context: invocationContext(UserRequestPageIds.activatePersona),
  );

  @override
  Future<ProfileUpdateSnapshot> updateUserProfile(
    UpdateUserProfileCommand command,
  ) => client.userPersonaUpdateUserProfile(
    command,
    context: invocationContext(UserRequestPageIds.updateUserProfile),
  );
}
