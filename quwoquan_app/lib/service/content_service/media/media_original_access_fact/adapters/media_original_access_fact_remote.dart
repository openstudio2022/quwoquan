import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_original_access_fact/application/media_original_access_gateway.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef MediaOriginalAccessInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// MediaOriginalAccessFact 对象拥有的 generated client adapter。
final class RemoteContentMediaOriginalAccessFactWriter
    implements MediaOriginalAccessGateway {
  const RemoteContentMediaOriginalAccessFactWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final MediaOriginalAccessInvocationContextFactory invocationContext;

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => client.contentMediaOriginalAccessFactRequestOriginalImageAccess(
    command,
    context: invocationContext(
      ContentRequestPageIds.requestOriginalImageAccess,
      command: true,
    ),
  );
}
