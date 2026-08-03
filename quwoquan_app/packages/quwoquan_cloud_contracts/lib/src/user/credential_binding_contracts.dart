import 'user_operation_contracts.g.dart';

abstract interface class CredentialBindingQuery {
  Future<ListCredentialsSlice> listCredentials(ListCredentialsQuery query);
}

abstract interface class CredentialBindingCommandWriter {
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

abstract interface class AppCredentialBindingCommandWriter
    implements CredentialBindingCommandWriter {}
