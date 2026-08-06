import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/account/credential_binding/application/public/credential_binding_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef CredentialBindingInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteCredentialBindingQuery implements CredentialBindingReader {
  const RemoteCredentialBindingQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CredentialBindingInvocationContextFactory invocationContext;

  @override
  Future<ListCredentialsSlice> listCredentials(ListCredentialsQuery query) =>
      client.userCredentialBindingListCredentials(
        query,
        context: invocationContext(UserRequestPageIds.listCredentials),
      );
}

/// App 商用凭据绑定操作的 production generated-client adapter。
final class RemoteAppCredentialBindingCommandWriter
    implements CredentialBindingWriter {
  const RemoteAppCredentialBindingCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CredentialBindingInvocationContextFactory invocationContext;

  @override
  Future<AuthSessionGrant> completeFederatedPhoneBinding(
    CompleteFederatedPhoneBindingCommand command,
  ) => client.userCredentialBindingCompleteFederatedPhoneBinding(
    command,
    context: invocationContext(
      UserRequestPageIds.completeFederatedPhoneBinding,
    ),
  );

  @override
  Future<CredentialBindingCommandResult> bindPhoneCredential(
    BindPhoneCredentialCommand command,
  ) => client.userCredentialBindingBindPhoneCredential(
    command,
    context: invocationContext(UserRequestPageIds.bindPhoneCredential),
  );

  @override
  Future<CredentialBindingCommandResult> bindCarrierPhoneCredential(
    BindCarrierPhoneCredentialCommand command,
  ) => client.userCredentialBindingBindCarrierPhoneCredential(
    command,
    context: invocationContext(UserRequestPageIds.bindCarrierPhoneCredential),
  );

  @override
  Future<CredentialBindingCommandResult> unbindCredential(
    UnbindCredentialCommand command,
  ) => client.userCredentialBindingUnbindCredential(
    command,
    context: invocationContext(UserRequestPageIds.unbindCredential),
  );
}
