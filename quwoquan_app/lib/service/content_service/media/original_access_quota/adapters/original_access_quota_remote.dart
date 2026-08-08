import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef OriginalAccessQuotaInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// OriginalAccessQuota 聚合拥有的 generated client adapter。
final class RemoteContentOriginalAccessQuotaWriter
    implements OriginalAccessQuotaGateway {
  const RemoteContentOriginalAccessQuotaWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final OriginalAccessQuotaInvocationContextFactory invocationContext;

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => client.contentOriginalAccessQuotaReserveOriginalImageAccessGrant(
    command,
    context: invocationContext(
      ContentRequestPageIds.reserveOriginalImageAccessGrant,
      command: true,
    ),
  );
}
