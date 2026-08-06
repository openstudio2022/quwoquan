import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AuthSessionGrant,
        BindCarrierPhoneCredentialCommand,
        BindPhoneCredentialCommand,
        CompleteFederatedPhoneBindingCommand,
        CredentialBindingCommandResult,
        ListCredentialsQuery,
        ListCredentialsSlice,
        UnbindCredentialCommand;

abstract interface class CredentialBindingReader {
  Future<ListCredentialsSlice> listCredentials(ListCredentialsQuery query);
}

abstract interface class CredentialBindingWriter {
  Future<AuthSessionGrant> completeFederatedPhoneBinding(
    CompleteFederatedPhoneBindingCommand command,
  );

  Future<CredentialBindingCommandResult> bindPhoneCredential(
    BindPhoneCredentialCommand command,
  );

  Future<CredentialBindingCommandResult> bindCarrierPhoneCredential(
    BindCarrierPhoneCredentialCommand command,
  );

  Future<CredentialBindingCommandResult> unbindCredential(
    UnbindCredentialCommand command,
  );
}
