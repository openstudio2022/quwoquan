import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContactDiscoveryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteContactDiscoveryFacet
    implements ContactDiscoveryCommandWriter, ContactDiscoveryQuery {
  const RemoteContactDiscoveryFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContactDiscoveryInvocationContextFactory invocationContext;

  @override
  Future<ContactDiscoveryResult> initiateContactDiscovery(
    InitiateContactDiscoveryCommand command,
  ) {
    return client.userContactDiscoveryInitiateContactDiscovery(
      command,
      context: invocationContext(UserRequestPageIds.initiateContactDiscovery),
    );
  }

  @override
  Future<ContactDiscoveryResult> getLatestContactDiscovery(
    GetLatestContactDiscoveryQuery query,
  ) {
    return client.userContactDiscoveryGetLatestContactDiscovery(
      query,
      context: invocationContext(UserRequestPageIds.getLatestContactDiscovery),
    );
  }

  @override
  Future<ContactDiscoveryDismissResult> dismissContactDiscovery(
    DismissContactDiscoveryCommand command,
  ) {
    return client.userContactDiscoveryDismissContactDiscovery(
      command,
      context: invocationContext(UserRequestPageIds.dismissContactDiscovery),
    );
  }
}
