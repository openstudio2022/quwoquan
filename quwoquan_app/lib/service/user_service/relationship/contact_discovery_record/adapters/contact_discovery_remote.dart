import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/application/public/contact_discovery_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContactDiscoveryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// ContactDiscoveryRecord 对象的 production generated-client adapter。
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
    return client.userContactDiscoveryRecordInitiateContactDiscovery(
      command,
      context: invocationContext(UserRequestPageIds.initiateContactDiscovery),
    );
  }

  @override
  Future<ContactDiscoveryResult> getLatestContactDiscovery(
    GetLatestContactDiscoveryQuery query,
  ) {
    return client.userContactDiscoveryRecordGetLatestContactDiscovery(
      query,
      context: invocationContext(UserRequestPageIds.getLatestContactDiscovery),
    );
  }

  @override
  Future<ContactDiscoveryDismissResult> dismissContactDiscovery(
    DismissContactDiscoveryCommand command,
  ) {
    return client.userContactDiscoveryRecordDismissContactDiscovery(
      command,
      context: invocationContext(UserRequestPageIds.dismissContactDiscovery),
    );
  }
}

final class RemoteContactDiscoveryRepository
    implements ContactDiscoveryRepository {
  const RemoteContactDiscoveryRepository({
    required this.commandWriter,
    required this.query,
  });

  final ContactDiscoveryCommandWriter commandWriter;
  final ContactDiscoveryQuery query;

  @override
  Future<ContactDiscoveryResultView> initiate(List<String> hashedPhones) async {
    final result = await commandWriter.initiateContactDiscovery(
      InitiateContactDiscoveryCommand(hashedPhones: hashedPhones),
    );
    return ContactDiscoveryResultView.fromWire(result);
  }

  @override
  Future<ContactDiscoveryResultView> getLatest() async {
    final result = await query.getLatestContactDiscovery(
      GetLatestContactDiscoveryQuery(),
    );
    if (result.id.trim().isEmpty) {
      throw CloudErrorMapper.invalidResponse(
        message: 'ContactDiscoveryResult.id must not be blank',
        functionModule: 'contact_discovery_remote',
      );
    }
    return ContactDiscoveryResultView.fromWire(result);
  }

  @override
  Future<void> dismiss(String id) async {
    await commandWriter.dismissContactDiscovery(
      DismissContactDiscoveryCommand(discoveryId: id),
    );
  }
}
